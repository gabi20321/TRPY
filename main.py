from devices import Host, Router, Switch
from manager import NetworkManager


def print_menu():
    print("""
========================================
        TRPY — CONSOLĂ REȚEA L2/L3
========================================
1. Adaugă dispozitiv (Host/Server/Switch/Router)
2. Afișează dispozitive & Topologie
3. Caută dispozitiv după IP
4. Ping ICMP
5. Configurare (Rute L3 LPM / CAM & VLAN Switch)
6. Conectează două dispozitive (L1 Link)
7. Testează rută pachet L2/L3 (Sursă -> Destinație)
8. Șterge dispozitiv
9. Generează topologia standard (R1 ➔ SW1 ➔ Hosts)
0. Ieșire & Salvare
----------------------------------------""")


def main():
    manager = NetworkManager()

    while True:
        print_menu()
        opt = input("Alege o opțiune: ").strip()

        if opt == "1":
            print("\nTipuri: 1. Router | 2. Switch | 3. Host (PC) | 4. Server")
            tip = input("Alegere tip: ").strip().lower()
            hostname = input(" Hostname: ").strip()
            ip = input(" Adresa IP: ").strip()
            mac = input(" Adresa MAC (ex: AA:BB:CC:11:22:33): ").strip()

            if tip in ["1", "router", "r"]:
                ok = manager.add_device(Router(hostname, ip, mac))
            elif tip in ["2", "switch", "sw"]:
                ports = input(" Număr porturi (default 24): ").strip()
                ports = int(ports) if ports.isdigit() else 24
                ok = manager.add_device(Switch(hostname, ip, mac, total_ports=ports))
            elif tip in ["3", "pc", "host"]:
                ok = manager.add_device(Host(hostname, ip, mac, role="pc"))
            elif tip in ["4", "server", "srv"]:
                ok = manager.add_device(Host(hostname, ip, mac, role="server"))
            else:
                print("[X] Tip invalid.")
                continue
            print("[+] Dispozitiv adăugat." if ok else "[X] Eroare: IP invalid sau duplicat.")

        elif opt == "2":
            manager.list_all()

        elif opt == "3":
            ip = input(" Adresa IP căutată: ").strip()
            device = manager.find_device(ip)
            if device:
                print(f"\nDispozitiv găsit:\n  {device.get_info()}")
            else:
                print(f"[X] Echipamentul cu IP {ip} nu există.")

        elif opt == "4":
            ip = input(" Introdu IP-ul pentru Ping: ").strip()
            device = manager.find_device(ip)
            if device:
                print(f"[*] Se trimite ICMP Echo Request către {ip}...")
                if device.ping():
                    print(f"[OK] {device.hostname} ({ip}) este UP")
                else:
                    print(f"[TIMEOUT] {device.hostname} ({ip}) este DOWN")
                manager.save_to_file()
            else:
                print(f"[X] Dispozitivul cu IP {ip} nu este înregistrat.")

        elif opt == "5":
            ip = input(" Introdu IP-ul echipamentului: ").strip()
            device = manager.find_device(ip)
            if not device:
                print(f"[X] Echipamentul cu IP {ip} nu a fost găsit.")
                continue

            if isinstance(device, Router):
                print(f"\n--- Configurare Router L3 {device.hostname} ---")
                print("1. Afișează tabela LPM | 2. Adaugă rută CIDR | 3. Testează LPM pentru IP")
                sub = input("Alegere: ").strip()
                if sub == "1":
                    device.show_routes()
                elif sub == "2":
                    dest = input(" Prefix CIDR (ex: 192.168.1.0/24): ").strip()
                    nh = input(" Next-Hop IP: ").strip()
                    if manager.is_valid_network(dest) and manager.is_valid_ip(nh):
                        device.add_route(dest, nh)
                        manager.save_to_file()
                        print("[+] Rută adăugată.")
                    else:
                        print("[X] Prefix sau Next-Hop invalid.")
                elif sub == "3":
                    test_ip = input(" IP destinație: ").strip()
                    hop = device.lookup_route(test_ip)
                    print(f"[LPM] Next-Hop pentru {test_ip}: {hop or 'Nicio rută găsită'}")

            elif isinstance(device, Switch):
                print(f"\n--- Configurare Switch L2 {device.hostname} ---")
                print("1. Afișează tabela CAM (MAC) | 2. Înregistrează MAC pe port")
                sub = input("Alegere: ").strip()
                if sub == "1":
                    device.show_mac_table()
                elif sub == "2":
                    mac = input(" Adresă MAC: ").strip()
                    port = input(f" Port (1-{device.total_ports}): ").strip()
                    if port.isdigit():
                        device.learn_mac(mac, int(port))
                        manager.save_to_file()
                    else:
                        print("[X] Port invalid.")
            else:
                print("[X] Acest echipament nu are tabele L2/L3.")

        elif opt == "6":
            ip1 = input(" IP Dispozitiv 1: ").strip()
            if1 = input(" Interfață 1 (ex: Fa0/1): ").strip()
            ip2 = input(" IP Dispozitiv 2: ").strip()
            if2 = input(" Interfață 2 (ex: Gi0/0): ").strip()
            if manager.connect_devices(ip1, if1, ip2, if2):
                print("[+] Conexiune realizată.")
            else:
                print("[X] Eroare la conectare.")

        elif opt == "7":
            src = input(" IP Sursă: ").strip()
            dst = input(" IP Destinație: ").strip()
            manager.simulate_packet_transfer(src, dst)

        elif opt == "8":
            ip = input(" Adresa IP a dispozitivului de șters: ").strip()
            if manager.remove_device(ip):
                print(f"[-] Dispozitivul {ip} a fost șters.")
            else:
                print("[X] Dispozitivul nu a fost găsit.")

        elif opt == "9":
            manager.build_standard_enterprise_topology()
            print("[+] Topologia standard (R1-Gateway ➔ SW1-Access ➔ Hosts) a fost generată.")

        elif opt == "0":
            manager.save_to_file()
            print("\nDatele au fost salvate în topology.json.")
            break

        else:
            print("[X] Opțiune invalidă.")


if __name__ == "__main__":
    main()
