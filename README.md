# 🌐 TRPY — L2/L3 Network Topology Simulator

Simulator interactiv în Python pentru modelarea și testarea fluxului de date pe nivelurile L2 (Comutare) și L3 (Rutare)[cite: 7, 8].

---

### ✨ Funcționalități
* **L2 Switching & 802.1Q VLAN:** Învățare adrese MAC (tabelă CAM), alocare porturi pe VLAN-uri și izolare automată a traficului între VLAN-uri fără rutare[cite: 6, 7].
* **L3 Routing (LPM):** Rutare IPv4 bazată pe *Longest Prefix Match* cu suport pentru măști CIDR și decrementare TTL hop-by-hop[cite: 6, 7].
* **Diagnoză & Traseu:** Testare cale pachete (BFS pathfinding) și verificare stare noduri prin ICMP Echo (Ping)[cite: 6, 9].
* **Interfețe duale:** GUI interactiv în Tkinter (canvas dark-mode cu drag-and-drop și animație de pachete) și mod consolă (CLI)[cite: 7, 8].
* **Persistență:** Salvare și încărcare completă a topologiei în `topology.json`[cite: 9].

---

### 🚀 Rulare rapidă

1. **Interfață grafică (GUI):**
   ```bash
   python gui.py
