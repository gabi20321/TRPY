import math
import random
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from devices import Device, Host, Router, Switch
from manager import NetworkManager

BG, PANEL, PANEL2, BORDER = "#0d1117", "#161b22", "#21262d", "#30363d"
TXT, MUTED = "#e6edf3", "#8b949e"
ACCENT, OK, WARN, BAD = "#2f81f7", "#3fb950", "#d29922", "#f85149"
FONT = "Segoe UI"


def rand_mac():
    return ":".join(f"{random.randint(0, 255):02X}" for _ in range(6))


def mkbtn(parent, text, cmd, color=PANEL2, fg=TXT, **kw):
    return tk.Button(parent, text=text, command=cmd, bg=color, fg=fg, activebackground=ACCENT,
                     activeforeground="white", relief="flat", bd=0, padx=10, pady=6,
                     font=(FONT, 9, "bold"), cursor="hand2", **kw)


class TRPYApp:
    def __init__(self, root):
        self.root = root
        root.title("TRPY — Simulator Topologie Rețea L2/L3 (VLAN & LPM Routing)")
        root.geometry("1420x840")
        root.minsize(1160, 700)
        root.configure(bg=BG)

        self.manager = NetworkManager()
        self.pos = {}
        self.packets = []
        self.effects = []
        self._drag = None

        self._style()
        self._build_header()
        body = tk.PanedWindow(root, orient=tk.HORIZONTAL, bg=BG, sashwidth=5, bd=0)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        left = tk.Frame(body, bg=BG)
        right = tk.Frame(body, bg=BG)
        body.add(left, width=420)
        body.add(right)
        self._build_left(left)
        self._build_right(right)

        self.refresh_all()
        self.log("Simulator L2/L3 pregătit. Dublu-click pe Switch pentru porturi/VLAN sau pe Router pentru tabela LPM.", "info")
        self.tick()

    def _style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("Treeview", background=PANEL, foreground=TXT, fieldbackground=PANEL,
                     rowheight=28, borderwidth=0, font=(FONT, 9))
        st.configure("Treeview.Heading", background=PANEL2, foreground=MUTED, relief="flat", font=(FONT, 9, "bold"))
        st.map("Treeview", background=[("selected", ACCENT)])
        st.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TXT,
                     arrowcolor=TXT, bordercolor=BORDER)
        st.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TXT)])
        self.root.option_add("*TCombobox*Listbox.background", PANEL2)
        self.root.option_add("*TCombobox*Listbox.foreground", TXT)

    def _build_header(self):
        h = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        h.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(h, text="🌐  TRPY", font=(FONT, 16, "bold"), fg=TXT, bg=PANEL).pack(side=tk.LEFT, padx=14, pady=8)
        tk.Label(h, text="Comutare L2 (CAM / 802.1Q VLAN)  &  Rutare L3 (IPv4 Longest Prefix Match)", font=(FONT, 10), fg=MUTED, bg=PANEL).pack(side=tk.LEFT)

        mkbtn(h, "🏗️ Încarcă Topologie Standard (R1 ➔ SW1 ➔ Hosts)", self.load_preset_topology, "#238636", "white").pack(side=tk.RIGHT, padx=10, pady=8)

    def _build_left(self, f):
        tk.Label(f, text="Tabel Echipamente (L2 / L3 / Endpoints)", font=(FONT, 10, "bold"), fg=TXT, bg=BG).pack(anchor=tk.W, pady=(0, 4))
        cont = tk.Frame(f, bg=BORDER, padx=1, pady=1)
        cont.pack(fill=tk.BOTH, expand=True)
        cols = ("Hostname", "IP", "MAC", "Tip", "Status")
        self.tree = ttk.Treeview(cont, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (90, 95, 110, 75, 50)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.draw_topology())
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        row = tk.Frame(f, bg=BG)
        row.pack(fill=tk.X, pady=6)
        for text, cmd, col in (
            ("➕ Adaugă", self.open_add_window, OK),
            ("🔗 Link", self.open_link_window, ACCENT),
            ("🔌 VLAN", self.open_ports_window, "#db6d28"),
            ("🗺️ Rute", self.open_selected_routes, "#6e40c9"),
            ("📡 Ping", self.ping_device, PANEL2),
            ("🗑️", self.delete_device, BAD),
        ):
            mkbtn(row, text, cmd, col, "white").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        box = tk.Frame(f, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=10, pady=10)
        box.pack(fill=tk.X, pady=(4, 0))
        tk.Label(box, text="Test Traseu Pachet L2 / L3 (Traceroute)", font=(FONT, 10, "bold"), fg=TXT, bg=PANEL).pack(anchor=tk.W, pady=(0, 6))

        tk.Label(box, text="Sursă:", font=(FONT, 8), fg=MUTED, bg=PANEL).pack(anchor=tk.W)
        self.cb_src = ttk.Combobox(box, state="readonly")
        self.cb_src.pack(fill=tk.X, pady=(2, 6))

        tk.Label(box, text="Destinație:", font=(FONT, 8), fg=MUTED, bg=PANEL).pack(anchor=tk.W)
        self.cb_dst = ttk.Combobox(box, state="readonly")
        self.cb_dst.pack(fill=tk.X, pady=(2, 8))

        mkbtn(box, "📨 Trimite Pachet pe Rută", self.send_route_test, ACCENT, "white").pack(fill=tk.X)

    def _build_right(self, f):
        self.canvas = tk.Canvas(f, bg="#0a0e14", highlightthickness=1, highlightbackground=BORDER)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw_topology())
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        for b in ("<Button-3>", "<Button-2>"):
            self.canvas.bind(b, self.on_right_click)

        tk.Label(f, text="Jurnal Evenimente L2/L3 (network_events.log)", font=(FONT, 10, "bold"), fg=MUTED, bg=BG).pack(anchor=tk.W, pady=(8, 2))
        self.log_box = tk.Text(f, height=9, bg="#0a0e14", fg=TXT, font=("Consolas", 9), state=tk.DISABLED,
                               relief="flat", highlightthickness=1, highlightbackground=BORDER)
        self.log_box.pack(fill=tk.X)
        for tag, col in (("ok", OK), ("bad", BAD), ("warn", WARN), ("info", MUTED)):
            self.log_box.tag_configure(tag, foreground=col)

    def load_preset_topology(self):
        self.packets.clear()
        self.manager.build_standard_enterprise_topology()
        w = max(self.canvas.winfo_width(), 900)
        h = max(self.canvas.winfo_height(), 520)
        self.pos = {
            "192.168.1.1":  (w * 0.20, h * 0.50),
            "192.168.1.2":  (w * 0.50, h * 0.50),
            "192.168.1.10": (w * 0.80, h * 0.22),
            "192.168.1.20": (w * 0.80, h * 0.50),
            "192.168.1.50": (w * 0.80, h * 0.78),
        }
        self.refresh_all()
        self.log("[TOPOLOGIE] Inițializat: R1-Gateway (L3) ➔ SW1-Access (802.1Q) ➔ 3x Hosts.", "ok")

    def on_tree_double_click(self, _event=None):
        dev = self.selected_dev()
        if isinstance(dev, Switch):
            self.open_ports_window()
        elif isinstance(dev, Router):
            self.open_routes_window(dev)

    def open_selected_routes(self):
        dev = self.selected_dev()
        if isinstance(dev, Router):
            self.open_routes_window(dev)
        else:
            messagebox.showwarning("Atenție", "Selectează un Router din listă!")

    def log(self, msg, tag="info"):
        self.log_box.config(state=tk.NORMAL)
        self.log_box.insert(tk.END, msg + "\n", tag)
        self.log_box.see(tk.END)
        self.log_box.config(state=tk.DISABLED)

    def selected_ip(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def selected_dev(self):
        ip = self.selected_ip()
        return self.manager.find_device(ip) if ip else None

    def dialog(self, title, w, h):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(f"{w}x{h}")
        win.configure(bg=PANEL)
        win.transient(self.root)
        win.grab_set()
        return win

    def field(self, parent, label):
        tk.Label(parent, text=label, font=(FONT, 9), fg=MUTED, bg=PANEL).pack(anchor=tk.W, padx=20, pady=(8, 2))

    def entry(self, parent, value=""):
        e = tk.Entry(parent, bg=PANEL2, fg=TXT, insertbackground=TXT, relief="flat", font=(FONT, 10))
        e.insert(0, value)
        e.pack(fill=tk.X, padx=20, ipady=4)
        return e

    def dev_label(self, d):
        return f"{d.hostname} ({d.ip_address})"

    def refresh_all(self):
        keep = self.selected_ip()
        self.tree.delete(*self.tree.get_children())
        labels = []
        for ip, d in self.manager.devices.items():
            if isinstance(d, Router):
                t = "Router"
            elif isinstance(d, Switch):
                t = f"Switch {d.total_ports}P"
            elif isinstance(d, Host):
                t = "Server" if d.role == "server" else "Host / PC"
            else:
                t = "Host / PC"
            self.tree.insert("", tk.END, iid=ip, values=(d.hostname, ip, d.mac_address, t, d.status))
            labels.append(self.dev_label(d))
        if keep and keep in self.manager.devices:
            self.tree.selection_set(keep)

        self.cb_src["values"] = labels
        self.cb_dst["values"] = labels
        if labels:
            if not self.cb_src.get() or self.cb_src.get() not in labels:
                self.cb_src.current(0)
            if not self.cb_dst.get() or self.cb_dst.get() not in labels:
                self.cb_dst.current(min(1, len(labels) - 1))

        self.draw_topology()

    def ensure_positions(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        devs = list(self.manager.devices)
        self.pos = {ip: p for ip, p in self.pos.items() if ip in self.manager.devices}
        n = len(devs)
        for i, ip in enumerate(devs):
            if ip not in self.pos:
                a = 2 * math.pi * i / max(n, 1) - math.pi / 2
                r = min(w, h) * 0.34
                self.pos[ip] = (w / 2 + r * math.cos(a), h / 2 + r * math.sin(a))

    def draw_topology(self):
        c = self.canvas
        w, h = c.winfo_width(), self.canvas.winfo_height()
        if w < 100:
            return
        c.delete("topo")
        for x in range(0, w, 40):
            c.create_line(x, 0, x, h, fill="#0f141b", tags="topo")
        for y in range(0, h, 40):
            c.create_line(0, y, w, y, fill="#0f141b", tags="topo")
        if not self.manager.devices:
            c.create_text(w / 2, h / 2, text="Niciun dispozitiv.\nApasă „🏗️ Încarcă Topologie Standard” sau „➕ Adaugă”.",
                          fill=MUTED, font=(FONT, 13), justify=tk.CENTER, tags="topo")
            return
        self.ensure_positions()
        drawn = set()
        for ip, d in self.manager.devices.items():
            for iface, t in d.connected_neighbors.items():
                key = frozenset((ip, t.ip_address))
                if t.ip_address not in self.pos or (key, iface) in drawn:
                    continue
                drawn.add((key, iface))
                x1, y1 = self.pos[ip]
                x2, y2 = self.pos[t.ip_address]
                up = d.status == "UP" and t.status == "UP"
                c.create_line(x1, y1, x2, y2, fill="#2ea043" if up else "#484f58", width=2, tags="topo")
                c.create_text(x1 + (x2 - x1) * .28, y1 + (y2 - y1) * .28 - 9, text=iface, fill="#e3b341",
                              font=(FONT, 8), tags="topo")
                tif = d.link_ifaces.get(iface, "")
                c.create_text(x1 + (x2 - x1) * .72, y1 + (y2 - y1) * .72 - 9, text=tif, fill="#e3b341",
                              font=(FONT, 8), tags="topo")
        for ip, d in self.manager.devices.items():
            self.draw_node(d, *self.pos[ip])

    def draw_node(self, d, x, y):
        c, ip = self.canvas, d.ip_address
        edge = OK if d.status == "UP" else BAD
        w = 4 if ip == self.selected_ip() else 2
        kw = dict(fill=PANEL2, outline=edge, width=w, tags="topo")
        if isinstance(d, Switch):
            c.create_rectangle(x - 38, y - 24, x + 38, y + 24, **kw)
            occ = sum(1 for p in d.port_config.values() if p.get("device_ip") and p.get("enabled", True))
            lit = round(8 * occ / d.total_ports) if occ else 0
            for i in range(8):
                c.create_rectangle(x - 30 + i * 8, y + 12, x - 26 + i * 8, y + 18,
                                   fill=ACCENT if i < lit else BORDER, outline="", tags="topo")
            icon, r = "🔀", 24
        elif isinstance(d, Router):
            c.create_oval(x - 30, y - 30, x + 30, y + 30, **kw)
            icon, r = "🌐", 30
        elif isinstance(d, Host) and d.role == "server":
            c.create_rectangle(x - 26, y - 28, x + 26, y + 28, **kw)
            icon, r = "🗄️", 28
        else:
            c.create_oval(x - 25, y - 25, x + 25, y + 25, **kw)
            icon, r = "💻", 25
        c.create_text(x, y - 3, text=icon, font=(FONT, 16), fill=TXT, tags="topo")
        c.create_text(x, y + r + 12, text=d.hostname, fill=TXT, font=(FONT, 9, "bold"), tags="topo")
        c.create_text(x, y + r + 25, text=ip, fill=MUTED, font=(FONT, 8), tags="topo")
        c.create_text(x, y + r + 38, text=d.status, fill=edge, font=(FONT, 8, "bold"), tags="topo")

    def node_at(self, x, y):
        for ip, (px, py) in self.pos.items():
            if abs(x - px) <= 38 and abs(y - py) <= 38:
                return ip
        return None

    def on_press(self, e):
        ip = self.node_at(e.x, e.y)
        self._drag = ip
        if ip:
            self.tree.selection_set(ip)

    def on_drag(self, e):
        if self._drag:
            self.pos[self._drag] = (e.x, e.y)
            self.draw_topology()

    def on_right_click(self, e):
        ip = self.node_at(e.x, e.y)
        if not ip:
            return
        self.tree.selection_set(ip)
        d = self.manager.find_device(ip)
        m = tk.Menu(self.root, tearoff=0, bg=PANEL2, fg=TXT, activebackground=ACCENT, font=(FONT, 9))
        m.add_command(label="📡 Ping ICMP", command=self.ping_device)
        if isinstance(d, Switch):
            m.add_command(label="🔌 Configurează porturi & 802.1Q VLAN", command=self.open_ports_window)
        if isinstance(d, Router):
            m.add_command(label="🗺️ Tabelă de rutare L3 (LPM)", command=lambda: self.open_routes_window(d))
        m.add_separator()
        m.add_command(label="🗑️ Șterge", command=self.delete_device)
        m.tk_popup(e.x_root, e.y_root)

    def send_route_test(self):
        devs = list(self.manager.devices.values())
        if len(devs) < 2:
            self.log("Adaugă cel puțin 2 dispozitive conectate.", "warn")
            return
        i1, i2 = self.cb_src.current(), self.cb_dst.current()
        if i1 < 0 or i2 < 0 or i1 == i2:
            self.log("Selectează o sursă și o destinație diferite.", "warn")
            return
        s, t = devs[i1], devs[i2]
        path, reason = self.manager.find_valid_path(s, t)
        if not path:
            if reason == "VLAN_MISMATCH":
                self.log(f"[802.1Q VLAN DROP] {s.hostname} -> {t.hostname}: VLAN-uri diferite fără Router L3!", "warn")
            else:
                self.log(f"[EROARE RUTĂ] Nu există legătură fizică între {s.hostname} și {t.hostname}.", "bad")
            return

        ttl = 64 - sum(1 for node in path[1:] if isinstance(node, Router))
        route_names = " ➔ ".join(d.hostname for d in path)
        self.packets.append(dict(path=[d.ip_address for d in path], seg=0, t=0.0, src=s, dst=t, ttl=ttl))
        self.log(f"[RUTĂ L2/L3] {s.ip_address} ({s.mac_address}) -> {t.ip_address} | Traseu: {route_names}", "info")

    def tick(self):
        c = self.canvas
        c.delete("pkt")
        alive = []
        for p in self.packets:
            if any(ip not in self.pos for ip in p["path"]):
                continue
            p["t"] += 0.05
            last = len(p["path"]) - 2
            while p["t"] >= 1 and p["seg"] < last:
                p["t"] -= 1
                p["seg"] += 1
            if p["seg"] >= last and p["t"] >= 1:
                self.on_arrival(p)
                continue
            x1, y1 = self.pos[p["path"][p["seg"]]]
            x2, y2 = self.pos[p["path"][p["seg"] + 1]]
            px, py = x1 + (x2 - x1) * p["t"], y1 + (y2 - y1) * p["t"]
            c.create_oval(px - 6, py - 6, px + 6, py + 6, fill=OK, outline="white", tags="pkt")
            alive.append(p)
        self.packets = alive

        fx = []
        for e in self.effects:
            e["age"] += 1
            if e["age"] < 14:
                r = 24 + e["age"] * 2
                c.create_oval(e["x"] - r, e["y"] - r, e["x"] + r, e["y"] + r, outline=e["color"], width=2, tags="pkt")
                fx.append(e)
        self.effects = fx
        self.root.after(40, self.tick)

    def on_arrival(self, p):
        x, y = self.pos[p["path"][-1]]
        self.effects.append(dict(x=x, y=y, color=OK, age=0))
        self.log(f"[LIVRAT] Cadru recepționat de {p['dst'].hostname} ({p['dst'].ip_address}) | TTL={p['ttl']}", "ok")

    def open_routes_window(self, router: Router):
        win = self.dialog(f"Rutare L3 (LPM) — {router.hostname}", 440, 380)
        tk.Label(win, text=f"🌐 Tabelă de Rutare L3 ({router.hostname})", font=(FONT, 12, "bold"), fg=TXT, bg=PANEL).pack(pady=8)
        cols = ("Prefix CIDR", "Next-Hop IP")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=7)
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=190, anchor=tk.W)
        tv.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

        def reload_routes():
            tv.delete(*tv.get_children())
            for net, hop in router.routing_table.items():
                tv.insert("", tk.END, values=(net, hop))

        reload_routes()
        self.field(win, "Adaugă rută (CIDR, ex: 192.168.1.0/24)")
        e_net = self.entry(win, "192.168.1.0/24")
        self.field(win, "Next-Hop IP")
        e_hop = self.entry(win)

        def add_rt():
            net, hop = e_net.get().strip(), e_hop.get().strip()
            if not (self.manager.is_valid_network(net) and self.manager.is_valid_ip(hop)):
                return messagebox.showerror("Eroare", "Rețea CIDR sau Next-Hop IP invalid!", parent=win)
            router.add_route(net, hop)
            self.manager.save_to_file()
            reload_routes()
            self.log(f"[L3 LPM] Rută adăugată pe {router.hostname}: {net} -> {hop}", "ok")

        mkbtn(win, "➕ Adaugă Rută LPM", add_rt, OK, "white").pack(fill=tk.X, padx=20, pady=10)

    def open_add_window(self):
        win = self.dialog("Adaugă dispozitiv", 350, 430)
        self.field(win, "Tip Echipament")
        tvar = tk.StringVar(value="PC / Workstation")
        ttk.Combobox(
            win,
            textvariable=tvar,
            state="readonly",
            values=["PC / Workstation", "Server", "Switch", "Router"]
        ).pack(fill=tk.X, padx=20)
        self.field(win, "Hostname (ex: PC-3, SRV-Web)")
        eh = self.entry(win)
        self.field(win, "Adresă IP (ex: 192.168.1.15)")
        ei = self.entry(win)
        self.field(win, "Adresă MAC")
        row = tk.Frame(win, bg=PANEL)
        row.pack(fill=tk.X, padx=20)
        em = tk.Entry(row, bg=PANEL2, fg=TXT, insertbackground=TXT, relief="flat", font=(FONT, 10))
        em.insert(0, rand_mac())
        em.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        mkbtn(row, "🎲", lambda: (em.delete(0, tk.END), em.insert(0, rand_mac()))).pack(side=tk.LEFT, padx=(6, 0))
        self.field(win, "Număr porturi (doar pentru Switch)")
        sp = tk.Spinbox(win, from_=4, to=48, bg=PANEL2, fg=TXT, relief="flat", buttonbackground=PANEL2)
        sp.delete(0, tk.END)
        sp.insert(0, "24")
        sp.pack(fill=tk.X, padx=20, ipady=3)

        def save():
            t, h, ip, mac = tvar.get(), eh.get().strip(), ei.get().strip(), em.get().strip()
            if not (h and ip and mac):
                return messagebox.showerror("Eroare", "Completează toate câmpurile!", parent=win)
            if t == "Router":
                dev = Router(h, ip, mac)
            elif t == "Switch":
                dev = Switch(h, ip, mac, total_ports=int(sp.get()) if sp.get().isdigit() else 24)
            elif t == "Server":
                dev = Host(h, ip, mac, role="server")
            else:
                dev = Host(h, ip, mac, role="pc")

            if self.manager.add_device(dev):
                self.log(f"[+] Adăugat {t} „{h}” ({ip})", "ok")
                self.refresh_all()
                win.destroy()
            else:
                messagebox.showerror("Eroare", "IP invalid sau deja folosit.", parent=win)

        mkbtn(win, "Salvează", save, OK, "white").pack(pady=16, padx=20, fill=tk.X)

    def open_link_window(self):
        devs = list(self.manager.devices.values())
        if len(devs) < 2:
            return messagebox.showwarning("Atenție", "Ai nevoie de cel puțin două dispozitive!")
        win = self.dialog("Conectează dispozitive", 360, 360)
        names = [self.dev_label(d) for d in devs]
        self.field(win, "Dispozitiv 1")
        c1 = ttk.Combobox(win, values=names, state="readonly")
        c1.current(0)
        c1.pack(fill=tk.X, padx=20)
        self.field(win, "Interfață 1")
        e1 = self.entry(win, "Gi0/0")
        self.field(win, "Dispozitiv 2")
        c2 = ttk.Combobox(win, values=names, state="readonly")
        c2.current(1)
        c2.pack(fill=tk.X, padx=20)
        self.field(win, "Interfață 2")
        e2 = self.entry(win, "Gi0/1")
        tk.Label(win, text="Tip: pentru switch folosește „🔌 VLAN”.", font=(FONT, 8), fg=MUTED, bg=PANEL).pack(pady=6)

        def go():
            a, b = devs[c1.current()], devs[c2.current()]
            if a is b:
                return messagebox.showerror("Eroare", "Alege două dispozitive diferite.", parent=win)
            if self.manager.connect_devices(a.ip_address, e1.get().strip(), b.ip_address, e2.get().strip()):
                self.log(f"[L1 LINK] {a.hostname}({e1.get()}) ↔ {b.hostname}({e2.get()})", "ok")
                self.refresh_all()
                win.destroy()

        mkbtn(win, "Conectează", go, ACCENT, "white").pack(pady=8, padx=20, fill=tk.X)

    def ping_device(self):
        d = self.selected_dev()
        if not d:
            return messagebox.showwarning("Atenție", "Selectează un dispozitiv!")
        self.log(f"[ICMP] Se trimite Echo Request către {d.ip_address}...", "info")

        def worker():
            ok = d.ping()
            self.manager.save_to_file()
            self.root.after(0, lambda: (
                self.log(f"[ICMP] {d.hostname} ({d.ip_address}) este {'UP' if ok else 'DOWN'}", "ok" if ok else "bad"),
                self.refresh_all()
            ))

        threading.Thread(target=worker, daemon=True).start()

    def delete_device(self):
        d = self.selected_dev()
        if not d:
            return messagebox.showwarning("Atenție", "Selectează un dispozitiv!")
        if messagebox.askyesno("Confirmare", f"Ștergi „{d.hostname}” ({d.ip_address})?"):
            self.manager.remove_device(d.ip_address)
            self.log(f"[-] Șters {d.hostname}", "warn")
            self.refresh_all()

    def apply_port(self, sw, p, label, target_ip, vlan, enabled):
        iface = f"Fa0/{p}"
        sw.disconnect(iface)
        sw.mac_table = {m: pp for m, pp in sw.mac_table.items() if pp != p}
        sw.assign_port(p, label, target_ip, vlan, enabled)
        t = self.manager.find_device(target_ip) if target_ip else None
        if t and enabled:
            for i, n in list(sw.connected_neighbors.items()):
                if n is t:
                    sw.disconnect(i)
            for q, cfg in sw.port_config.items():
                if q != p and cfg.get("device_ip") == target_ip:
                    cfg["device_ip"] = ""
            k = 0
            while f"eth{k}" in t.connected_neighbors:
                k += 1
            sw.connect_to(iface, t, f"eth{k}")
            sw.learn_mac(t.mac_address, p)
        self.manager.save_to_file()

    def open_ports_window(self):
        sw = self.selected_dev()
        if not isinstance(sw, Switch):
            return messagebox.showwarning("Atenție", "Selectează un Switch din listă!")
        win = self.dialog(f"Porturi & 802.1Q VLAN — {sw.hostname}", 800, 650)
        head = tk.Frame(win, bg=PANEL)
        head.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(head, text=f"🔀 {sw.hostname}", font=(FONT, 14, "bold"), fg=TXT, bg=PANEL).pack(side=tk.LEFT)
        summary = tk.Label(head, font=(FONT, 10), fg=MUTED, bg=PANEL)
        summary.pack(side=tk.RIGHT)
        leg = tk.Frame(win, bg=PANEL)
        leg.pack(fill=tk.X, padx=16)
        for col, txt in ((PANEL2, "liber"), (ACCENT, "conectat (VLAN activ)"), (OK, "configurat"), (BAD, "dezactivat")):
            tk.Label(leg, text="  ", bg=col).pack(side=tk.LEFT)
            tk.Label(leg, text=txt, font=(FONT, 8), fg=MUTED, bg=PANEL).pack(side=tk.LEFT, padx=(4, 12))
        grid = tk.Frame(win, bg=PANEL)
        grid.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        def render():
            for w in grid.winfo_children():
                w.destroy()
            used = 0
            for p in range(1, sw.total_ports + 1):
                cfg = sw.port_config.get(p)
                vlan_id = cfg.get("vlan", 1) if cfg else 1
                if cfg and not cfg.get("enabled", True):
                    col, sub = BAD, "OFF"
                elif cfg and cfg.get("device_ip"):
                    dv = self.manager.find_device(cfg["device_ip"])
                    name = dv.hostname if dv else cfg["device_ip"]
                    col, sub = ACCENT, f"{name[:7]} V{vlan_id}"
                elif cfg:
                    col, sub = OK, f"VLAN {vlan_id}"
                else:
                    col, sub = PANEL2, "liber"
                used += cfg is not None
                b = tk.Button(grid, text=f"{p}\n{sub[:11]}", width=9, height=2, bg=col, fg="white", relief="flat",
                              font=(FONT, 9, "bold"), cursor="hand2", command=lambda p=p: edit(p))
                b.grid(row=(p - 1) // 8, column=(p - 1) % 8, padx=3, pady=3, sticky="nsew")
            summary.config(text=f"{used}/{sw.total_ports} porturi configurate")

        def edit(p):
            cfg = sw.port_config.get(p, {})
            dlg = self.dialog(f"{sw.hostname} — Port Fa0/{p}", 360, 400)
            self.field(dlg, "Descriere / nume port")
            el = self.entry(dlg, cfg.get("label", ""))
            self.field(dlg, "Dispozitiv conectat la acest port")
            others = [d for d in self.manager.devices.values() if d is not sw]
            cb = ttk.Combobox(dlg, state="readonly", values=["— niciunul —"] + [self.dev_label(d) for d in others])
            cb.current(next((i + 1 for i, d in enumerate(others) if d.ip_address == cfg.get("device_ip")), 0))
            cb.pack(fill=tk.X, padx=20)
            self.field(dlg, "802.1Q VLAN ID (1-4094)")
            ev = self.entry(dlg, str(cfg.get("vlan", 1)))
            en = tk.BooleanVar(value=cfg.get("enabled", True))
            tk.Checkbutton(dlg, text="Port activ", variable=en, bg=PANEL, fg=TXT, selectcolor=PANEL2,
                           activebackground=PANEL, activeforeground=TXT).pack(anchor=tk.W, padx=20, pady=8)

            def save():
                v = ev.get().strip()
                if not (v.isdigit() and 1 <= int(v) <= 4094):
                    return messagebox.showerror("Eroare", "VLAN trebuie să fie între 1 și 4094.", parent=dlg)
                i = cb.current()
                self.apply_port(sw, p, el.get().strip(), others[i - 1].ip_address if i > 0 else "", int(v), en.get())
                self.log(f"[L2 PORT] {sw.hostname} Fa0/{p} configurat în VLAN {v}.", "ok")
                dlg.destroy()
                render()
                self.refresh_all()

            def free():
                sw.disconnect(f"Fa0/{p}")
                sw.clear_port(p)
                self.manager.save_to_file()
                dlg.destroy()
                render()
                self.refresh_all()

            mkbtn(dlg, "Salvează", save, OK, "white").pack(fill=tk.X, padx=20, pady=(6, 4))
            mkbtn(dlg, "Eliberează portul", free, BAD, "white").pack(fill=tk.X, padx=20)

        def auto():
            used = {c.get("device_ip") for c in sw.port_config.values()}
            free = [p for p in range(1, sw.total_ports + 1) if p not in sw.port_config]
            n = 0
            for d in self.manager.devices.values():
                if d is sw or isinstance(d, Router) or d.ip_address in used or not free:
                    continue
                self.apply_port(sw, free.pop(0), d.hostname, d.ip_address, 1, True)
                n += 1
            self.log(f"[L2 PORT] {n} dispozitive atribuite automat pe {sw.hostname} (VLAN 1).", "ok")
            render()
            self.refresh_all()

        mkbtn(win, "✨ Atribuie automat dispozitivele libere (VLAN 1)", auto, "#6e40c9", "white").pack(fill=tk.X, padx=16, pady=(0, 14))
        render()


if __name__ == "__main__":
    root = tk.Tk()
    TRPYApp(root)
    root.mainloop()
