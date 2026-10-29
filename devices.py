import logging
import platform
import subprocess

logging.basicConfig(
    filename="network_events.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8"
)


def ipv4_to_int(ip_str: str) -> int | None:
    parts = ip_str.strip().split(".")
    if len(parts) != 4:
        return None
    val = 0
    for p in parts:
        if not p.isdigit():
            return None
        octet = int(p)
        if octet < 0 or octet > 255:
            return None
        val = (val << 8) | octet
    return val


def parse_cidr(cidr_str: str) -> tuple[int, int, int] | None:
    if "/" not in cidr_str:
        return None
    ip_part, pref_part = cidr_str.strip().split("/", 1)
    if not pref_part.isdigit():
        return None
    prefix = int(pref_part)
    if prefix < 0 or prefix > 32:
        return None
    ip_int = ipv4_to_int(ip_part)
    if ip_int is None:
        return None
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix > 0 else 0
    return ip_int & mask, mask, prefix


class Device:
    def __init__(self, hostname: str, ip_address: str, mac_address: str, status: str = "UP"):
        self.hostname = hostname
        self.ip_address = ip_address
        self.mac_address = mac_address
        self.status = status
        self.connected_neighbors = {}
        self.link_ifaces = {}

    def connect_to(self, interface: str, target_device, target_interface: str):
        self.connected_neighbors[interface] = target_device
        self.link_ifaces[interface] = target_interface
        target_device.connected_neighbors[target_interface] = self
        target_device.link_ifaces[target_interface] = interface
        logging.info(f"L1 LINK UP: {self.hostname}({interface}) <-> {target_device.hostname}({target_interface})")

    def disconnect(self, interface: str):
        target = self.connected_neighbors.pop(interface, None)
        t_if = self.link_ifaces.pop(interface, None)
        if target is not None and target.connected_neighbors.get(t_if) is self:
            target.connected_neighbors.pop(t_if, None)
            target.link_ifaces.pop(t_if, None)
            logging.info(f"L1 LINK DOWN: {self.hostname}({interface}) <-> {target.hostname}({t_if})")

    def disconnect_all(self):
        for iface in list(self.connected_neighbors.keys()):
            self.disconnect(iface)

    def ping(self) -> bool:
        is_windows = platform.system().lower() == "windows"
        count_flag = "-n" if is_windows else "-c"
        timeout_flag = "-w" if is_windows else "-W"
        timeout_value = "1000" if is_windows else "1"

        command = ["ping", count_flag, "1", timeout_flag, timeout_value, self.ip_address]

        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0 and "ttl=" in result.stdout.lower():
                self.status = "UP"
                logging.info(f"ICMP ECHO REPLY: {self.hostname} ({self.ip_address})")
                return True
            else:
                self.status = "DOWN"
                logging.warning(f"ICMP TIMEOUT: {self.hostname} ({self.ip_address})")
                return False
        except Exception as e:
            self.status = "DOWN"
            logging.error(f"ICMP ERROR on {self.ip_address}: {e}")
            return False

    def get_info(self) -> str:
        links = ", ".join(self.connected_neighbors.keys()) if self.connected_neighbors else "Niciunul"
        return f"[{self.status}] {self.hostname} | IP: {self.ip_address} | MAC: {self.mac_address} | Interfețe: {links}"

    def to_dict(self) -> dict:
        return {
            "type": "device",
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "status": self.status,
            "links": {
                i: {"ip": n.ip_address, "iface": self.link_ifaces.get(i, "")}
                for i, n in self.connected_neighbors.items()
            },
        }


class Host(Device):
    def __init__(self, hostname: str, ip_address: str, mac_address: str, role: str = "pc", status: str = "UP"):
        super().__init__(hostname, ip_address, mac_address, status)
        self.role = role

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["type"] = "server" if self.role == "server" else "host"
        data["role"] = self.role
        return data


class Router(Device):
    def __init__(self, hostname: str, ip_address: str, mac_address: str, status: str = "UP"):
        super().__init__(hostname, ip_address, mac_address, status)
        self.routing_table = {}

    def add_route(self, network: str, next_hop: str):
        self.routing_table[network] = next_hop
        logging.info(f"L3 ROUTE ADDED on {self.hostname}: {network} via {next_hop}")

    def lookup_route(self, dst_ip: str) -> str | None:
        target_int = ipv4_to_int(dst_ip)
        if target_int is None:
            return None

        best_hop = None
        best_prefix_len = -1

        for net_str, next_hop in self.routing_table.items():
            parsed = parse_cidr(net_str)
            if parsed is None:
                continue
            net_int, mask, prefix_len = parsed
            if (target_int & mask) == net_int and prefix_len > best_prefix_len:
                best_prefix_len = prefix_len
                best_hop = next_hop
        return best_hop

    def show_routes(self) -> None:
        if not self.routing_table:
            print(" Tabela de rutare L3 este goală.")
            return
        print(f" Tabela de rutare L3 (Longest Prefix Match) — {self.hostname}:")
        for net, hop in self.routing_table.items():
            print(f"  Prefix: {net:<18} -> Next-Hop: {hop}")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["type"] = "router"
        data["routing_table"] = self.routing_table
        return data


class Switch(Device):
    def __init__(self, hostname: str, ip_address: str, mac_address: str, total_ports: int = 24, status: str = "UP"):
        super().__init__(hostname, ip_address, mac_address, status)
        self.mac_table = {}
        self.total_ports = total_ports
        self.port_config = {}

    def learn_mac(self, mac: str, port: int):
        if 1 <= port <= self.total_ports:
            self.mac_table[mac] = port
        else:
            print(f" Portul {port} nu este valid (1-{self.total_ports}).")

    def assign_port(self, port: int, label: str = "", device_ip: str = "", vlan: int = 1, enabled: bool = True):
        if not 1 <= port <= self.total_ports:
            return False
        self.port_config[port] = {"label": label, "device_ip": device_ip, "vlan": vlan, "enabled": enabled}
        logging.info(f"L2 PORT CONFIG {self.hostname} Fa0/{port}: dev={device_ip}, 802.1Q VLAN={vlan}, enabled={enabled}")
        return True

    def clear_port(self, port: int):
        self.port_config.pop(port, None)
        self.mac_table = {m: p for m, p in self.mac_table.items() if p != port}

    def get_device_vlan(self, device_ip: str) -> int | None:
        for cfg in self.port_config.values():
            if cfg.get("device_ip") == device_ip:
                return int(cfg.get("vlan", 1))
        return None

    def is_port_enabled_for(self, device_ip: str) -> bool:
        for cfg in self.port_config.values():
            if cfg.get("device_ip") == device_ip:
                return bool(cfg.get("enabled", True))
        return True

    def can_forward_l2(self, prev_dev: Device, next_dev: Device) -> bool:
        if not self.is_port_enabled_for(prev_dev.ip_address) or not self.is_port_enabled_for(next_dev.ip_address):
            return False

        if isinstance(prev_dev, Router) or isinstance(next_dev, Router):
            return True

        v1 = self.get_device_vlan(prev_dev.ip_address)
        v2 = self.get_device_vlan(next_dev.ip_address)
        if v1 is not None and v2 is not None and v1 != v2:
            return False
        return True

    def show_mac_table(self) -> None:
        if not self.mac_table:
            print(" Tabela CAM (MAC) este goală.")
            return
        print(f" Tabela CAM (MAC) — {self.hostname}:")
        for mac, port in self.mac_table.items():
            vlan = self.port_config.get(port, {}).get("vlan", 1)
            print(f"  MAC: {mac} -> Fa0/{port} (802.1Q VLAN {vlan})")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["type"] = "switch"
        data["mac_table"] = self.mac_table
        data["total_ports"] = self.total_ports
        data["ports"] = self.port_config
        return data
