import json
import os
from collections import deque
from devices import Device, Host, Router, Switch, ipv4_to_int, parse_cidr


class NetworkManager:
    def __init__(self, filename: str = "topology.json"):
        self.devices = {}
        self.filename = filename
        self.load_from_file()

    @staticmethod
    def is_valid_ip(ip_str: str) -> bool:
        return ipv4_to_int(ip_str) is not None

    @staticmethod
    def is_valid_network(net_str: str) -> bool:
        return parse_cidr(net_str) is not None

    def save_to_file(self) -> None:
        data = {ip: dev.to_dict() for ip, dev in self.devices.items()}
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load_from_file(self) -> None:
        if not os.path.exists(self.filename):
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            for ip, info in data.items():
                dev_type = info.get("type")
                if dev_type == "router":
                    r = Router(info["hostname"], info["ip_address"], info["mac_address"], info["status"])
                    r.routing_table = info.get("routing_table", {})
                    self.devices[ip] = r
                elif dev_type == "switch":
                    s = Switch(
                        info["hostname"],
                        info["ip_address"],
                        info["mac_address"],
                        total_ports=info.get("total_ports", 24),
                        status=info["status"],
                    )
                    s.mac_table = info.get("mac_table", {})
                    s.port_config = {int(k): v for k, v in info.get("ports", {}).items()}
                    self.devices[ip] = s
                elif dev_type in ("host", "server"):
                    role = "server" if dev_type == "server" or info.get("role") == "server" else "pc"
                    h = Host(info["hostname"], info["ip_address"], info["mac_address"], role=role, status=info["status"])
                    self.devices[ip] = h
                else:
                    d = Device(info["hostname"], info["ip_address"], info["mac_address"], info["status"])
                    self.devices[ip] = d
            for ip, info in data.items():
                dev = self.devices.get(ip)
                for iface, link in info.get("links", {}).items():
                    other = self.devices.get(link.get("ip"))
                    if dev and other:
                        dev.connect_to(iface, other, link.get("iface") or "eth0")
        except Exception as e:
            print(f"[X] Eroare la încărcare: {e}")

    def add_device(self, device_obj: Device) -> bool:
        if not self.is_valid_ip(device_obj.ip_address):
            return False
        if device_obj.ip_address in self.devices:
            return False

        self.devices[device_obj.ip_address] = device_obj
        self.save_to_file()
        return True

    def remove_device(self, ip: str) -> bool:
        if ip in self.devices:
            removed = self.devices.pop(ip)
            removed.disconnect_all()
            for dev in self.devices.values():
                if isinstance(dev, Switch):
                    for p, cfg in list(dev.port_config.items()):
                        if cfg.get("device_ip") == ip:
                            dev.clear_port(p)
            self.save_to_file()
            return True
        return False

    def build_standard_enterprise_topology(self) -> None:
        self.devices.clear()

        r_wan = Router("R1-Gateway", "192.168.1.1", "AA:BB:CC:00:01:01")
        sw_lan = Switch("SW1-Access", "192.168.1.2", "AA:BB:CC:00:01:02", total_ports=24)

        pc1 = Host("PC-1", "192.168.1.10", "AA:BB:CC:00:01:10", role="pc")
        pc2 = Host("PC-2", "192.168.1.20", "AA:BB:CC:00:01:20", role="pc")
        srv = Host("SRV-Data", "192.168.1.50", "AA:BB:CC:00:01:50", role="server")

        for d in (r_wan, sw_lan, pc1, pc2, srv):
            self.devices[d.ip_address] = d

        r_wan.add_route("192.168.1.0/24", "192.168.1.2")

        sw_lan.assign_port(1, "R1-Uplink", r_wan.ip_address, vlan=1, enabled=True)
        sw_lan.connect_to("Fa0/1", r_wan, "Gi0/0")
        sw_lan.learn_mac(r_wan.mac_address, 1)

        endpoints = [(2, pc1), (3, pc2), (4, srv)]
        for port_num, ep in endpoints:
            sw_lan.assign_port(port_num, ep.hostname, ep.ip_address, vlan=1, enabled=True)
            sw_lan.connect_to(f"Fa0/{port_num}", ep, "eth0")
            sw_lan.learn_mac(ep.mac_address, port_num)

        self.save_to_file()

    def find_device(self, ip: str) -> Device | None:
        return self.devices.get(ip)

    def connect_devices(self, ip1: str, if1: str, ip2: str, if2: str) -> bool:
        dev1 = self.find_device(ip1)
        dev2 = self.find_device(ip2)
        if not dev1 or not dev2:
            return False
        dev1.connect_to(if1, dev2, if2)
        self.save_to_file()
        return True

    def find_valid_path(self, src: Device, dst: Device) -> tuple[list[Device] | None, str]:
        q = deque([[src]])
        seen = {src.ip_address}
        vlan_blocked = False

        while q:
            path = q.popleft()
            curr = path[-1]
            if curr is dst:
                return path, "OK"

            neighbors = list(curr.connected_neighbors.values())

            if isinstance(curr, Router) and curr.routing_table:
                nh_ip = curr.lookup_route(dst.ip_address)
                if nh_ip:
                    nh_dev = self.find_device(nh_ip)
                    if nh_dev in neighbors:
                        neighbors = [nh_dev] + [n for n in neighbors if n is not nh_dev]

            for nxt in neighbors:
                if nxt.ip_address in seen or nxt.ip_address not in self.devices:
                    continue

                if isinstance(curr, Switch) and len(path) >= 2:
                    prev_dev = path[-2]
                    if not curr.can_forward_l2(prev_dev, nxt):
                        vlan_blocked = True
                        continue

                seen.add(nxt.ip_address)
                q.append(path + [nxt])

        if vlan_blocked:
            return None, "VLAN_MISMATCH"
        return None, "NO_LINK"

    def simulate_packet_transfer(self, src_ip: str, dst_ip: str) -> bool:
        src = self.find_device(src_ip)
        dst = self.find_device(dst_ip)
        if not src or not dst:
            print("[X] Sursa sau destinația nu există în rețea.")
            return False

        path, reason = self.find_valid_path(src, dst)
        if not path:
            if reason == "VLAN_MISMATCH":
                print("[X] Drop L2 (802.1Q): Dispozitivele sunt în VLAN-uri diferite fără rutare L3!")
            else:
                print("[X] Nu există legătură fizică activă între sursă și destinație!")
            return False

        ttl = 64
        for node in path[1:]:
            if isinstance(node, Router):
                ttl -= 1

        route_str = " -> ".join(d.hostname for d in path)
        print(f"\n[*] Rută L2/L3 calculată: {route_str}")
        print(f"[OK] Cadru livrat de la {src.ip_address} ({src.mac_address}) la {dst.ip_address} ({dst.mac_address}) | TTL={ttl}")
        return True

    def list_all(self) -> None:
        if not self.devices:
            print("\nNu există echipamente în rețea.")
            return
        print("\n" + "=" * 84)
        print(f"{'HOSTNAME':<16} {'IP':<16} {'TIP':<14} {'STATUS':<10} {'INTERFEȚE':<24}")
        print("-" * 84)
        for ip, dev in self.devices.items():
            if isinstance(dev, Router):
                dev_type = "Router (L3)"
            elif isinstance(dev, Switch):
                dev_type = f"Switch ({dev.total_ports}P)"
            elif isinstance(dev, Host):
                dev_type = "Server" if dev.role == "server" else "Host / PC"
            else:
                dev_type = "Device"

            links = ", ".join(dev.connected_neighbors.keys()) if dev.connected_neighbors else "Niciunul"
            print(f"{dev.hostname:<16} {dev.ip_address:<16} {dev_type:<14} {dev.status:<10} {links:<24}")
        print("=" * 84)
