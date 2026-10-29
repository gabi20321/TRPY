import os
import unittest
from devices import Device, Router, Switch, ipv4_to_int, parse_cidr
from manager import NetworkManager


class TestTRPYNetwork(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_topology_temp.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        self.manager = NetworkManager(filename=self.test_file)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_bitwise_ipv4_and_cidr(self):
        self.assertEqual(ipv4_to_int("192.168.1.1"), 0xC0A80101)
        self.assertIsNone(ipv4_to_int("999.168.1.1"))
        net_int, mask, prefix = parse_cidr("192.168.1.55/24")
        self.assertEqual(net_int, 0xC0A80100)
        self.assertEqual(mask, 0xFFFFFF00)
        self.assertEqual(prefix, 24)

    def test_router_longest_prefix_match(self):
        r = Router("R1", "10.0.0.1", "AA:BB:CC:00:00:01")
        r.add_route("0.0.0.0/0", "10.0.0.254")
        r.add_route("192.168.0.0/16", "10.0.0.2")
        r.add_route("192.168.1.0/24", "10.0.0.3")

        self.assertEqual(r.lookup_route("192.168.1.55"), "10.0.0.3")
        self.assertEqual(r.lookup_route("192.168.2.55"), "10.0.0.2")
        self.assertEqual(r.lookup_route("8.8.8.8"), "10.0.0.254")

    def test_vlan_isolation_on_switch(self):
        sw = Switch("SW1", "192.168.1.2", "AA:BB:CC:00:00:02", total_ports=24)
        pc1 = Device("PC-1", "192.168.1.10", "AA:BB:CC:00:00:10")
        pc2 = Device("PC-2", "192.168.1.20", "AA:BB:CC:00:00:20")
        for d in (sw, pc1, pc2):
            self.manager.add_device(d)

        sw.assign_port(1, "PC-1", pc1.ip_address, vlan=10, enabled=True)
        sw.assign_port(2, "PC-2", pc2.ip_address, vlan=20, enabled=True)
        sw.connect_to("Fa0/1", pc1, "eth0")
        sw.connect_to("Fa0/2", pc2, "eth0")

        path, reason = self.manager.find_valid_path(pc1, pc2)
        self.assertIsNone(path)
        self.assertEqual(reason, "VLAN_MISMATCH")

        sw.assign_port(2, "PC-2", pc2.ip_address, vlan=10, enabled=True)
        path_ok, reason_ok = self.manager.find_valid_path(pc1, pc2)
        self.assertIsNotNone(path_ok)
        self.assertEqual(reason_ok, "OK")


if __name__ == "__main__":
    unittest.main()
