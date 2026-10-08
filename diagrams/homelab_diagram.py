#!/usr/bin/env python3
"""ssi-platform architecture diagram, after Day 5 (Open WebUI live) or Day 6 (MCP server live).

Hand-laid-out SVG using real icons: official Kubernetes icons and k3s/PostgreSQL/Python/Helm
logos (bundled with the mingrammer `diagrams` package), plus official vendor/project logos
fetched by build_icons.py (Ollama, Open WebUI, NVIDIA, Meta, Nomic, Ubuntu) and generic device icons.

    python build_icons.py      # once: fetch logos and compose icons into ./icons
    python homelab_diagram.py  # writes homelab-architecture.svg and .png (Day 5, the default)
    python build_icons_day06.py            # once: MCP / fo-mock / mcp-test icons
    python homelab_diagram.py --day 6      # writes homelab-architecture-day06.svg and .png
    python build_icons_day06b.py           # once: monitoring-node laptop + flannel icons
    python homelab_diagram.py --day 6b     # writes homelab-architecture-day06b.svg and .png (second node)
    python build_icons_day07.py            # once: OpenTelemetry / Prometheus / Grafana / Loki / Tempo / Langfuse icons
    python homelab_diagram.py --day 7      # writes homelab-architecture-day07.svg and .png (observability)
    python build_icons_day08.py            # once: Tailscale / GitHub / phone icons
    python homelab_diagram.py --day 8      # writes homelab-architecture-day08.svg and .png (tailnet ingress, guard, GHCR)

Requires: rsvg-convert (librsvg2-bin), the Inter font, pip packages diagrams + pillow.
"""
import base64, html, re, subprocess, sys
from pathlib import Path
import diagrams

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
RES = Path(diagrams.__file__).resolve().parent.parent / "resources"
DAY_S = sys.argv[sys.argv.index("--day") + 1] if "--day" in sys.argv else "5"  # build_drawio.py execs this -> Day 5
DAY = int(re.match(r"\d+", DAY_S).group())
TWO_NODES = DAY_S == "6b" or DAY >= 7   # Day 6b: second k3s node (monitoring node) to the right of the lab host
D7 = DAY >= 7                 # Day 7: observability stack on the monitoring node, OTLP from the lab host
D8 = DAY >= 8                 # Day 8: private Tailscale ingress, Prompt Guard on the request path, GHCR images
OUT = HERE / "history" / ("homelab-architecture" if DAY == 5 else f"homelab-architecture-day{DAY:02d}{DAY_S[len(str(DAY)):]}")
DY = 450 if DAY >= 6 else 0   # Day 6 adds an MCP band inside si-lab; everything below it moves down by DY
GX = 180 if DAY >= 6 else 0   # ... and gpu-system / GPU move right so the 1x GPU path clears the band
W, H = (4320 if D7 else 3300, 1815 + DY + 90 + (80 if D8 else 0)) if TWO_NODES else (2490, 1815 + DY)
FONT = "InterEmbedded, Inter, 'Noto Sans', 'DejaVu Sans', sans-serif"  # InterEmbedded = @font-face in the SVG

C = dict(access="#1f6feb", app="#34404c", gpu="#4f9a00", store="#d9730d", cfg="#7d8793", day5="#8e44ad", live="#2f8f3a",
         lan="#0e7490", otel="#d6336c", ts="#111827")

def icon(name):
    p = ICONS / name if (ICONS / name).exists() else RES / name
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()

K8S = {k: f"k8s/{v}.png" for k, v in dict(svc="network/svc", pvc="storage/pvc", pv="storage/pv", sc="storage/sc",
       secret="podconfig/secret", cm="podconfig/cm", node="infra/node", api="controlplane/api", ns="group/ns").items()}
K8S.update(helm="k8s/ecosystem/helm.png", k3s="onprem/container/k3s.png")

out = []
esc = lambda s: html.escape(s, quote=True)

def text(x, y, s, size=15, weight=400, color="#1f2a33", anchor="middle", halo=False, italic=False):
    st = ' stroke="#ffffff" stroke-width="5" stroke-linejoin="round" paint-order="stroke"' if halo else ""
    it = ' font-style="italic"' if italic else ""
    out.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
               f'fill="{color}" text-anchor="{anchor}"{st}{it}>{s}</text>')

# ---------------------------------------------------------------- clusters
def cluster(x0, y0, x1, y1, title, sub="", fill="#ffffff", stroke="#c5ced8", dash=False, ico=None, ico_size=34,
            title_color="#1b2733", badge=None, width=2):
    d = ' stroke-dasharray="10 6"' if dash else ""
    out.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{d}/>')
    tx = x0 + 16
    if ico:
        out.append(f'<image href="{icon(ico)}" x="{tx}" y="{y0+10}" width="{ico_size}" height="{ico_size}" preserveAspectRatio="xMidYMid meet"/>')
        tx += ico_size + 10
    ty = y0 + 30 if not sub else y0 + 27
    text(tx, ty, esc(title), 18, 700, title_color, "start")
    if badge:
        bw = 12 + 8.6 * len(badge)
        bx = tx + 10.8 * len(title) + 14
        out.append(f'<rect x="{bx}" y="{ty-17}" width="{bw}" height="24" rx="12" fill="{C["live"]}"/>')
        text(bx + bw / 2, ty, esc(badge), 13, 700, "#ffffff")
    if sub:
        text(tx, ty + 20, sub, 13.5, 400, "#5b6570", "start")

# ---------------------------------------------------------------- nodes
N = {}
def node(key, x, y, ico, label, size=84, sub=None):
    """label: list of lines; first line bold. Icon centred at (x, y)."""
    N[key] = (x, y, size)
    out_nodes.append((x, y, ico, label, size))

out_nodes = []
def draw_nodes():
    for x, y, ico, label, size in out_nodes:
        out.append(f'<image href="{icon(ico)}" x="{x-size/2}" y="{y-size/2}" width="{size}" height="{size}" preserveAspectRatio="xMidYMid meet"/>')
        ly = y + size / 2 + 18
        for i, line in enumerate(label):
            text(x, ly + i * 18, line, 15 if i == 0 else 13.5, 650 if i == 0 else 400, "#1f2a33" if i == 0 else "#4b5661", halo=True)

def P(key, side, off=0, gap=6):
    x, y, s = N[key]
    h = s / 2 + gap
    return {"l": (x - h, y + off), "r": (x + h, y + off), "t": (x + off, y - h), "b": (x + off, y + h)}[side]

# ---------------------------------------------------------------- edges
markers = set()
edges_svg = []
labels_svg = []
def edge(pts, color, label=None, lpos=None, dashed=False, dotted=False, width=2.4, anchor="middle", lcolor=None, arrow=True,
         both=False):
    """pts: list of (x, y); orthogonal polyline with rounded corners."""
    r = 12
    d = f"M{pts[0][0]},{pts[0][1]}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        def towards(ax, ay, bx, by, dist):
            L = max(abs(bx - ax), abs(by - ay)) or 1
            dd = min(dist, L / 2)
            return ax + (bx - ax) / L * dd, ay + (by - ay) / L * dd
        a = towards(x1, y1, x0, y0, r); b = towards(x1, y1, x2, y2, r)
        d += f" L{a[0]:.1f},{a[1]:.1f} Q{x1},{y1} {b[0]:.1f},{b[1]:.1f}"
    d += f" L{pts[-1][0]},{pts[-1][1]}"
    mid = color.strip("#")
    markers.add(color)
    da = ' stroke-dasharray="9 6"' if dashed else (' stroke-dasharray="2 5" stroke-linecap="round"' if dotted else "")
    me = (f' marker-end="url(#arr{mid})"' if arrow else "") + (f' marker-start="url(#arr{mid})"' if both else "")
    edges_svg.append(f'<path d="{d}" fill="none" stroke="#ffffff" stroke-opacity="0.9" stroke-width="{width+5}"/>')
    edges_svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da}{me}/>')
    if label:
        lx, ly = lpos
        for i, line in enumerate(label.split("\n")):
            labels_svg.append((lx, ly + i * 16, line, lcolor or color, anchor))

def draw_edges():
    out.append("<defs>")
    for c in markers:
        out.append(f'<marker id="arr{c.strip("#")}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                   f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    out.append("</defs>")
    out.extend(edges_svg)

def draw_edge_labels():
    for x, y, s, c, a in labels_svg:
        text(x, y, esc(s), 13.5, 600, c, a, halo=True)

# ================================================================ LAYOUT
# --- title + legend
def header():
    text(40, 62, f"ssi-platform: architecture after Day {DAY_S}", 36, 800, "#14202b", "start")
    sub = ("Day 8 adds a private Tailscale ingress (no Funnel), Prompt Guard on the request path, and GHCR images pinned to a commit SHA."
           if D8 else
           "Day 7: an observability stack on the monitoring node (OTel collector, Prometheus, Grafana, Loki, Tempo, Langfuse). "
           "mcp-server and rag-worker on the lab host send OTLP; otel-agent ships pod logs from both nodes. Prompt Guard 2 runs on the lab host, CPU only."
           if D7 else
           "Local AI stack on a single-node k3s cluster: Ollama on the GPU, pgvector, a rag-worker, and the Open WebUI chat UI, driven from the terminal over an SSH tunnel to the k3s API."
           if DAY == 5 else
           "Two-node k3s: the lab host (node gpu-node: control plane, GPU, all si-lab workloads) and a CPU-only monitoring node (node obs-node), tainted and reserved for Day 7 observability."
           if TWO_NODES else
           "Local AI stack on a single-node k3s cluster: Ollama on the GPU, pgvector, rag-worker, Open WebUI, and now an MCP tool server with a mock FO OData service (fake demo data).")
    text(40, 96, sub, 17, 400, "#5b6570", "start")
    x, y = 40, 132
    items = [("access: SSH tunnel over Tailscale / k8s API" if D8 else "access: SSH tunnel / k8s API / port-forward", C["access"], ""), ("app traffic", C["app"], ""),
             ("GPU", C["gpu"], ""), ("storage", C["store"], ""), ("config / secret mount", C["cfg"], "dot")]
    if DAY >= 6:
        items.append(("phase 2 (not configured yet)", C["day5"], "dash"))
    if TWO_NODES:
        items.append(("node-to-node k3s traffic (home LAN)", C["lan"], ""))
    if D7:
        items.append(("telemetry: OTLP traces / metrics / logs", C["otel"], ""))
    if D8:
        items.append(("private tailnet (no Funnel)", C["ts"], ""))
    for lab, col, sty in items:
        da = ' stroke-dasharray="9 6"' if sty == "dash" else (' stroke-dasharray="2 5" stroke-linecap="round"' if sty == "dot" else "")
        out.append(f'<line x1="{x}" y1="{y-5}" x2="{x+44}" y2="{y-5}" stroke="{col}" stroke-width="3"{da}/>')
        out.append(f'<path d="M{x+44},{y-10} L{x+54},{y-5} L{x+44},{y} z" fill="{col}"/>')
        text(x + 62, y, esc(lab), 14.5, 500, "#34404c", "start")
        x += 62 + 8.1 * len(lab) + 40

header()

# --- clusters (drawn back to front)
cluster(30, 430, 362, 930, "Terminal", "kubectl + helm + browser only",
        fill="#f2f7fe", stroke="#9dbbe6", ico="terminal_laptop.png", ico_size=40)
cluster(520, 175, 2460, 1790 + DY, "Lab host",
        "Ubuntu 26.04 LTS · k3s server" if TWO_NODES else "Ubuntu 26.04 LTS · single-node k3s",
        fill="#fafbfc", stroke="#aab4bf", ico="labhost_laptop.png", ico_size=44, width=2.5)
cluster(690, 250, 2115, 1520 + DY, "k3s v1.36 · server node gpu-node (control plane)" if TWO_NODES else "k3s v1.36 · single node gpu-node",
        "secrets encryption on · Traefik disabled · API bound to 127.0.0.1:6443",
        fill="#fffaf0", stroke="#f0b429", ico=K8S["k3s"], ico_size=38, width=2.5)
cluster(890, 330, 1805, 1318 + DY, "namespace: si-lab", "Pod Security Standard: baseline",
        fill="#eef4ff", stroke="#5b8def", ico=K8S["ns"], ico_size=32)
cluster(920, 400, 1455, 678, "Open WebUI", "", fill="#ffffff", stroke="#c3d3ee",
        badge="DAY 5 · live")
cluster(920, 708, 1212, 1118 if D7 else 1300, "RAG worker", "ingest + ask", fill="#ffffff", stroke="#c3d3ee")
cluster(1290, 708, 1795, 988, "pgvector", "", fill="#ffffff", stroke="#c3d3ee")
cluster(1290, 1022, 1795, 1300, "Ollama", "", fill="#ffffff", stroke="#c3d3ee")
cluster(1460 + GX, 1338 + DY, 1700 + GX, 1506 + DY, "namespace: gpu-system", "", fill="#f1f9e8", stroke="#8cc152", ico=K8S["ns"], ico_size=26)
cluster(1825, 690, 2105, 1318, "cluster-scoped storage", "PVs · StorageClasses", fill="#fff3e6", stroke="#f0a35e")
cluster(2135, 720, 2445, 1318, "Host disks", "", fill="#f3f5f7", stroke="#c3cbd4")
cluster(560, 1545 + DY, 1805 + GX // 2 + (15 if GX else 0), 1772 + DY, "GPU stack (host)", "", fill="#f1f9e8", stroke="#a9d18e")

# --- nodes
node("browser", 110, 530, "browser.png", ["browser", "tailnet HTTPS"] if D8 else ["browser", "localhost:3000/3001/3002" if D7 else "http://127.0.0.1:3000"], 72)
node("kubectl", 270, 610, "kubectl.png", ["kubectl"], 74)
node("terminal", 110, 720, "terminal_laptop.png", ["terminal", "Tailscale"] if D8 else ["terminal"], 92)
node("helm", 270, 810, K8S["helm"], ["helm"], 74)
node("ssh", 440, 690, "ssh_tunnel.png", ["SSH tunnel :6443", "over Tailscale" if D8 else "terminal → lab host"], 84)
node("lab_host", 620, 690, "labhost_laptop.png", ["lab host", "sshd · Tailscale" if D8 else "sshd"], 90)
node("api", 790, 690, K8S["api"], ["k3s API server", "127.0.0.1:6443"], 80)
node("node_d", 760, 1420 + DY, K8S["node"], ["node gpu-node", "containerd +", "nvidia runtime"], 76)

node("svc_owui", 1005, 470, K8S["svc"], ["svc open-webui", "ClusterIP :8080"], 66)
node("sec_owui", 1005, 592, K8S["secret"], ["Secret", "open-webui-secret"], 48)
node("owui", 1185, 525, "openwebui_deploy.png", ["open-webui", "Deployment"], 80)
node("pvc_owui", 1375, 525, K8S["pvc"], ["PVC", "open-webui-data", "5Gi · local-path"], 66)

node("cm", 990, 1005, K8S["cm"], ["ConfigMap", "rag-scripts"], 62)
node("rag", 1122, 1005, "ragworker_deploy.png", ["rag-worker", "Deployment", "ingest.py · ask.py"], 84)

node("svc_pg", 1425, 785, K8S["svc"], ["svc pgvector", ":5432"], 66)
node("sec_pg", 1425, 905, K8S["secret"], ["Secret", "pgvector-auth"], 48)
node("pg", 1590, 845, "pgvector_sts.png", ["pgvector StatefulSet", "pgvector/pgvector:pg17", "table chunks · HNSW"], 84)
node("pvc_pg", 1735, 845, K8S["pvc"], ["PVC", "data-pgvector-0", "10Gi"], 62)

node("svc_ollama", 1425, 1110, K8S["svc"], ["svc ollama", ":11434"], 66)
node("ollama", 1585, 1110, "ollama_deploy.png", ["ollama", "Deployment", "1× GPU"], 84)
node("llama", 1730, 1080, "meta_llama.png", ["llama3.2:3b", "chat"], 54)
node("nomic", 1730, 1235, "nomic.png", ["nomic-embed-text", "embeddings"], 48)

node("devplugin", 1580 + GX, 1420 + DY, "nvidia_device_plugin_ds.png", ["nvidia-device-plugin", "DaemonSet (Helm)"], 60)

node("sc_local", 2050, 845, K8S["sc"], ["StorageClass", "local-path"], 64)
node("pv_docs", 1895, 1005, K8S["pv"], ["PV rag-docs-pv", "/mnt/ailab-data/", "ai-ops-homelab/docs"], 60)
node("pv_models", 1895, 1185, K8S["pv"], ["PV: Ollama models", "/mnt/ailab-data/", "ai-ops-homelab/ollama"], 60)
node("sc_ext", 2050, 1095, K8S["sc"], ["StorageClass", "ailab-external"], 64)

node("nvme", 2290, 845, "nvme_ssd.png", ["internal NVMe SSD", "local-path"], 120)
node("wd", 2290, 1095, "usb_drive.png", ["external USB drive", "exFAT", "/mnt/ailab-data"], 96)

node("toolkit", 760, 1650 + DY, "nvidia_container_toolkit.png", ["NVIDIA Container Toolkit", "nvidia runtime → k3s containerd"], 128)
node("gpu", 1580 + GX, 1650 + DY, "gpu_chip.png", ["NVIDIA laptop GPU", "4 GB VRAM · driver 595"], 92)

# --- edges: access path (terminal -> tunnel -> API)
a = C["access"]
edge([P("browser", "r"), (270, 530), P("kubectl", "t")], a, None if D8 else "127.0.0.1:3000", (200, 520))
edge([P("terminal", "r", -10), (200, 710), (200, 610), P("kubectl", "l")], a, "runs", (206, 670), anchor="start")
edge([(200, 720), (200, 810), P("helm", "l")], a)
edge([P("kubectl", "r"), (372, 610), (372, 675), P("ssh", "l", -15)], a, "API + port-fwds", (380, 603), anchor="start")
edge([P("helm", "r"), (372, 810), (372, 705), P("ssh", "l", 15)], a, "API", (380, 835), anchor="start")
edge([P("ssh", "r"), P("lab_host", "l")], a, "tailnet" if D8 else "SSH", (530, 672))
edge([P("lab_host", "r"), P("api", "l")], a, ":6443", (697, 680), anchor="start")
# port-forwards ride the tunnel through the API server
edge([P("api", "t"), (790, 470), P("svc_owui", "l")], a, "port-forward\n3000 → 8080\nover SSH tunnel", (780, 560), anchor="end")
edge([P("api", "r"), (868, 690), (868, 1338), (1425, 1338), (1425, 1205)], a, "port-forward 11435 → 11434", (900, 1360) if D8 else (1080, 1360))
edge([P("api", "r", 22), (850, 712), (850, 1445 + DY), P("devplugin", "l", 25)], a, "helm install", (1170, 1437 + DY), dotted=True)

# --- GPU path
g = C["gpu"]
edge([P("gpu", "l"), P("toolkit", "r")], g, "GPU access", (1170, 1640 + DY))
edge([(760, 1598 + DY), (760, 1512 + DY)], g, "nvidia runtime", (772, 1540 + DY), anchor="start")
edge([P("gpu", "t"), (1580 + GX, 1506 + DY)], g, "nvidia.com/gpu", (1592 + GX, 1540 + DY), anchor="start")
if DAY == 5:
    edge([P("devplugin", "t"), (1580, 1212)], g, "1× GPU", (1592, 1292), anchor="start")
else:  # around the Day 6 band: up the right edge of si-lab, then left into ollama
    edge([P("devplugin", "t"), (1760, 1345), (1580, 1345), (1580, 1212)], g, "1× GPU", (1672, 1337))

# --- Ollama
ap = C["app"]
edge([P("svc_ollama", "r"), P("ollama", "l")], ap)
edge([P("ollama", "r", -30), P("llama", "l")], ap, "serves", (1668, 1070))
edge([P("ollama", "r", 28), (1655, 1138), (1655, 1235), P("nomic", "l")], ap, "serves", (1662, 1225), anchor="start")
edge([P("ollama", "r", 2), (1682, 1112), (1682, 1185), P("pv_models", "l")], C["store"], "models", (1770, 1177))

# --- RAG worker
edge([P("cm", "r"), P("rag", "l")], C["cfg"], dotted=True)
edge([P("rag", "r"), (1262, 1005), (1262, 785), P("svc_pg", "l")], ap, "store / search\nchunks", (1325, 757))
edge([(1262, 1005), (1262, 1095), P("svc_ollama", "l", -15)], ap, "embed / generate", (1325, 1087))
edge([(1262, 1005), P("pv_docs", "l")], C["store"], "docs", (1790, 997))

# --- pgvector
edge([P("svc_pg", "r"), (1500, 785), (1500, 830), P("pg", "l", -15)], ap)
edge([P("sec_pg", "r"), (1500, 905), (1500, 860), P("pg", "l", 15)], C["cfg"], dotted=True)
edge([P("pg", "r"), P("pvc_pg", "l")], C["store"])
edge([P("pvc_pg", "r"), P("sc_local", "l")], C["store"], "10Gi PVC", (1905, 835))

# --- Open WebUI (Day 5, live)
edge([P("svc_owui", "r"), (1092, 470), (1092, 510), P("owui", "l", -15)], ap)
edge([P("sec_owui", "r"), (1092, 592), (1092, 540), P("owui", "l", 15)], C["cfg"], dotted=True)
edge([P("owui", "r", -10), (P("pvc_owui", "l")[0], 515)], C["store"])
edge([P("pvc_owui", "r"), (2050, 525), P("sc_local", "t")], C["store"], "5Gi PVC", (1700, 515))
edge([P("owui", "r", 22), (1236, 547), (1236, 1125), P("svc_ollama", "l", 15)], ap, "chat API", (1228, 697), anchor="end")

# --- PVs / StorageClasses -> disks
s = C["store"]
edge([P("pv_docs", "r"), (1990, 1005), (1990, 1080), P("sc_ext", "l", -15)], s)
edge([P("pv_models", "r"), (1990, 1185), (1990, 1110), P("sc_ext", "l", 15)], s)
edge([P("sc_local", "r"), P("nvme", "l")], s, "backed by", (2180, 835))
edge([P("sc_ext", "r"), P("wd", "l")], s, "backed by", (2180, 1085))

# --- Day 6: MCP server + mock FO OData (fake demo data) + test Job
if DAY >= 6:
    cluster(920, 1380, 1722, 1752, "Day 6 · MCP", "tool server + mock FO OData",
            fill="#ffffff", stroke="#c3d3ee", ico="mcp_logo.png", ico_size=34, badge="live")
    node("svc_mcp", 1135, 1490, K8S["svc"], ["svc mcp-server", "ClusterIP :8000 /mcp"], 66)
    node("mcp", 1310, 1490, "mcp_deploy.png", ["mcp-server", "Deployment · MCP SDK 2.2.0",
         "search_notes · fo_list_entities", "fo_get_entity_metadata · fo_query"], 84)
    node("np_fo", 1610, 1490, "k8s/network/netpol.png", ["NetworkPolicy", "→ fo-mock :8080", "from mcp-server only"], 48)
    node("job", 985, 1665, "mcptest_job.png", ["mcp-test", "Job · checks passed"], 70)
    node("np_mcp", 1150, 1665, "k8s/network/netpol.png", ["NetworkPolicy", "→ mcp-server :8000", "from si-lab pods"], 48)
    node("svc_fo", 1450, 1665, K8S["svc"], ["svc fo-mock", "ClusterIP :8080"], 62)
    node("fo", 1610, 1665, "fomock_deploy.png", ["fo-mock (fake demo data)", "mock FO OData v4"], 76)
    edge([P("job", "t"), (985, 1505), P("svc_mcp", "l", 15)], ap, "MCP tests", (992, 1560), anchor="start")
    edge([P("svc_mcp", "r"), P("mcp", "l")], ap)
    # search_notes: joins the rag-worker bus to pgvector + ollama (same queries as ask.py)
    edge([P("mcp", "t", -48), (1262, 1095)], ap, "search_notes:\nembed + vector search", (1272, 1418), anchor="start", arrow=False)
    edge([P("mcp", "r"), (1450, 1490), P("svc_fo", "t")], ap, "fo_* tools", (1404, 1510) if D7 else (1400, 1480))
    edge([P("svc_fo", "r"), P("fo", "l")], ap)
    # Phase 2: Open WebUI -> MCP (External Tool Server, MCP Streamable HTTP) - not configured yet
    edge([(920, 650), (905, 650), (905, 1475), P("svc_mcp", "l", -15)], C["day5"], "phase 2", (1000, 1467), dashed=True)

# --- Day 6b: second node (monitoring node), joined as a CPU-only k3s agent, tainted for Day 7
if TWO_NODES:
    ln = C["lan"]
    cluster(2480, 1420 if D7 else 1340, 2690, 2215, "home LAN", "Wi-Fi · one subnet", fill="#f3f7f9", stroke="#9fb3c8", dash=True)
    if D7:
        cluster(2740, 175, 4290, 2240, "Monitoring node", "Ubuntu 26.04.1 · 16 GB RAM · Wi-Fi",
                fill="#fafbfc", stroke="#aab4bf", ico="monitoring_laptop.png", ico_size=44, width=2.5)
        cluster(2765, 410, 4265, 2215, "k3s agent v1.36.4", "node obs-node · CPU only · every Day 7 chart sets the nodeSelector + toleration",
                fill="#fffaf0", stroke="#f0b429", ico=K8S["k3s"], ico_size=34, width=2.5)
        cluster(2790, 1965, 3240, 2195, "scheduling", "label + taint from Day 6b", fill="#ffffff", stroke="#9aa5b1")
        text(3015, 2062, "only pods that tolerate", 14, 500, "#5b6570")
        text(3015, 2082, "ailab/role=observability:NoSchedule", 14, 600, "#34404c")
        text(3015, 2102, "are scheduled here", 14, 500, "#5b6570")
    else:
        cluster(2740, 1330, 3260, 2240, "Monitoring node", "Ubuntu 26.04.1 · 16 GB RAM · Wi-Fi",
                fill="#fafbfc", stroke="#aab4bf", ico="monitoring_laptop.png", ico_size=44, width=2.5)
        cluster(2765, 1590, 3240, 2215, "k3s agent v1.36.4", "node obs-node · CPU only",
                fill="#fffaf0", stroke="#f0b429", ico=K8S["k3s"], ico_size=34, width=2.5)
        cluster(2790, 1985, 3215, 2195, "reserved for Day 7", "observability stack · empty for now",
                fill="#ffffff", stroke="#9aa5b1", dash=True)
        text(3002, 2112, "only pods that tolerate", 14, 500, "#5b6570")
        text(3002, 2132, "ailab/role=observability:NoSchedule", 14, 600, "#34404c")
        text(3002, 2152, "are scheduled here", 14, 500, "#5b6570")

    node("router", 2585, 2010 if D7 else 1455, "generic/network/router.png", ["home router", "DHCP reservations", "no port forwarding"], 64)
    node("mon_host", 2880 if D7 else 2870, 300 if D7 else 1470, "monitoring_laptop.png",
         ["monitoring node", "sshd · Tailscale" if D8 else "sshd (keys only)"], 90)
    node("ufw_s", 3130 if D7 else 3110, 292 if D7 else 1462, "generic/network/firewall.png", ["ufw", "deny incoming, allow SSH;", "8472/udp + 10250 from lab host"], 56)
    node("node_s", 3065, 1745, K8S["node"], ["node obs-node", "agent (worker)", "label ailab/role=observability",
         "taint ailab/role=observability:NoSchedule"], 76)
    node("kubelet_s", 2850, 1720, "k8s/controlplane/kubelet.png", ["kubelet", ":10250"], 56)
    node("flannel_s", 2850, 1880, "flannel.png", ["flannel VXLAN", "Wi-Fi interface"], 52)
    # node gpu-node's side of the node-to-node links, inside the k3s box
    node("kubelet_d", 1995, 1720, "k8s/controlplane/kubelet.png", ["kubelet (node gpu-node)", ":10250"], 56)
    node("flannel_d", 1995, 1880, "flannel.png", ["flannel VXLAN", "(node gpu-node)"], 52)
    node("ufw_d", 2290, 2060, "generic/network/firewall.png", ["ufw (lab host)", "from monitoring node only:", "6443 · 8472/udp · 10250 · 9100"], 56)

    # agent -> API server (supervisor + API), 6443/tcp
    edge([P("node_s", "t"), (3065, 1662), (2715, 1662), (2715, 314), (820, 314), P("api", "t", 30)], ln,
         "6443/tcp · k3s agent → API server", (1700, 306))
    edge([P("kubelet_d", "r"), P("kubelet_s", "l")], ln, "10250/tcp · kubelet", (2585, 1710), both=True)
    edge([P("flannel_d", "r"), P("flannel_s", "l")], ln, "8472/udp · flannel VXLAN", (2585, 1870), both=True)
    edge([P("kubelet_s", "r"), P("node_s", "l", -25)], C["cfg"], dotted=True, arrow=False)
    edge([P("flannel_s", "r"), (2960, 1880), (2960, 1765), P("node_s", "l", 20)], C["cfg"], dotted=True, arrow=False)
    # terminal -> monitoring node: admin SSH (keys only), same as the lab host
    if D8:
        # phone + GHCR sit in the column under the terminal, so this line skirts the lab host border
        edge([(196, 930), (488, 930), (488, 2290), (3000, 2290), (3000, 2240)], C["access"],
             "SSH (admin, keys only): terminal → monitoring node", (1600, 2274))
    else:
        edge([(196, 930), (196, 2290), (3000, 2290), (3000, 2240)], C["access"],
             "SSH (admin, keys only): terminal → monitoring node", (1500, 2282))

# --- Day 7: observability on the monitoring node; OTLP from mcp-server + rag-worker on the lab host
if D7:
    o = C["otel"]
    # lab host side: Prompt Guard (Part 2, live, CPU only) and the monitoring-host DaemonSets on node gpu-node
    cluster(920, 1138, 1180, 1300, "Prompt Guard 2",
            "model on PVC · not in image" if D8 else "Part 2 · classifier",
            fill="#ffffff", stroke="#c3d3ee", badge="live")
    node("pguard", 1050, 1222, "promptguard_deploy.png",
         ["prompt-guard (22M)", "fail closed · threshold 0.5"] if D8 else ["prompt-guard (22M)", "svc :8080 · CPU only"], 44)
    cluster(1822, 1400, 2105, 1614, "monitoring-host", "DaemonSets · privileged", fill="#ffffff", stroke="#e599b4")
    node("nodeexp_d", 1895, 1515, "nodeexporter_ds.png", ["node-exporter", ":9100 (scraped)"], 56)
    node("agent_d", 2035, 1515, "otelagent_ds.png", ["otel-agent", "pod logs"], 56)

    # monitoring node: header row + measured memory
    cluster(3330, 205, 4250, 390, "measured memory, all stages running", "kubectl top + free -m on the monitoring node",
            fill="#ffffff", stroke="#9aa5b1")
    text(3346, 288, "stage A 0.9 GiB · stage B 1.9 GiB · stage C 0.2 GiB = about 3 GiB (estimate was 3.4–5.3 GiB)", 14.5, 500, "#34404c", "start")
    text(3346, 314, "node: 15,298 MiB total · 4,845 used · 10,452 available · 0 swap used", 14.5, 500, "#34404c", "start")
    text(3346, 340, "Langfuse at about 1/5 of its documented minimums: fine for one user, not for production", 14.5, 500, "#34404c", "start")

    cluster(2790, 470, 3765, 1640, "namespace: monitoring", "baseline · kube-prometheus-stack 91.5.3 · collector 0.173.1 · Loki · Tempo",
            fill="#fdf2f6", stroke="#e599b4", ico=K8S["ns"], ico_size=32)
    cluster(3790, 470, 4240, 1640, "namespace: langfuse", "baseline · chart 2.1.2 (Langfuse v4)",
            fill="#fdf2f6", stroke="#e599b4", ico=K8S["ns"], ico_size=32)
    cluster(3280, 1680, 3765, 1930, "namespace: monitoring-host", "privileged · DaemonSets on both nodes", fill="#ffffff", stroke="#e599b4")
    cluster(3790, 1680, 4240, 1930, "Langfuse prerequisites", "own namespaces · baseline", fill="#ffffff", stroke="#e599b4")
    cluster(3280, 1965, 4240, 2195, "what the Day 7 checks showed", "", fill="#ffffff", stroke="#9aa5b1")
    text(3296, 2030, "Tempo: TraceQL {resource.service.name=\"mcp-server\"} found the trace (root service rag-worker, 2.68 s cold model reload)", 14, 500, "#34404c", "start")
    text(3296, 2058, "Loki: {k8s_namespace_name=\"si-lab\"} != \"healthz\" != \"GIN\" cut 1,000 lines to 20 real ones", 14, 500, "#34404c", "start")
    text(3296, 2086, "Prometheus: {job=\"si-lab/mcp-server\"} 74 series · p50 about 9 ms, p95 about 4.3 s (one cold reload, small sample)", 14, 500, "#34404c", "start")
    text(3296, 2114, "Langfuse: POST → POST /mcp → search_notes (TOOL) → Ollama embed + pgvector SELECT, 0.04 s", 14, 500, "#34404c", "start")
    text(3296, 2150,
         "Open WebUI, Grafana and Langfuse are tailnet HTTPS. kubectl still uses the SSH tunnel, now over Tailscale, for the API."
         if D8 else
         "Grafana and Langfuse are reached with kubectl port-forward (localhost:3001 / :3002) over the SSH tunnel.",
         13.5, 400, "#5b6570", "start", italic=True)

    node("promop", 2950, 605, "promop_deploy.png", ["kps-operator", "Prometheus operator"], 60)
    node("ksm", 2950, 800, "ksm_deploy.png", ["kube-state-metrics"], 60)
    node("np_mon", 2950, 1010, "k8s/network/netpol.png", ["NetworkPolicies", "otel-collector / loki /", "tempo ingress"], 48)
    node("otelcol", 2950, 1368, "otelcol_deploy.png", ["otel-collector (gateway)", "Deployment · OTLP :4317/:4318", "own metrics :8888"], 84)
    node("prom", 3330, 700, "prometheus_sts.png", ["Prometheus", "3 d / 3 GB retention", "OTLP receiver /api/v1/otlp"], 84)
    node("tempo", 3330, 990, "tempo_sts.png", ["Tempo (monolithic)", "traces · 48 h"], 80)
    node("loki", 3330, 1270, "loki_sts.png", ["Loki (monolithic)", "logs · 48 h"], 80)
    node("grafana", 3620, 990, "grafana_deploy.png", ["Grafana", "256Mi req / 1Gi limit", "port-forward → :3001"], 84)

    node("lf_web", 3905, 650, "langfuse_deploy.png", ["langfuse-web", "UI + OTLP ingest :3000", "port-forward → :3002"], 72)
    node("lf_worker", 4130, 650, "langfuse_deploy.png", ["langfuse-worker"], 72)
    node("lf_ch", 3905, 900, "clickhouse_sts.png", ["ClickHouse", "via operator · trimmed", "system log tables"], 72)
    node("lf_keeper", 4130, 900, "clickhouse_sts.png", ["ClickHouse Keeper", "1 replica"], 72)
    node("lf_pg", 3905, 1160, "lfpg_sts.png", ["Postgres", "StatefulSet"], 72)
    node("lf_s3", 4130, 1160, "seaweedfs_deploy.png", ["SeaweedFS", "S3 blob store"], 72)
    node("lf_redis", 3905, 1410, "valkey_deploy.png", ["Valkey", "Redis-compatible queue"], 72)
    node("lf_np", 4130, 1410, "k8s/network/netpol.png", ["NetworkPolicies", "same-namespace +", "web :3000 ingress"], 48)

    node("nodeexp_s", 3420, 1812, "nodeexporter_ds.png", ["node-exporter", ":9100 (scraped)"], 60)
    node("agent_s", 3630, 1812, "otelagent_ds.png", ["otel-agent", "pod logs"], 60)
    node("certmgr", 3905, 1812, "certmanager_deploy.png", ["cert-manager", "v1.20.2"], 60)
    node("chop", 4130, 1812, "chop_deploy.png", ["ClickHouse operator", "0.0.5"], 60)

    # OTLP from the lab host: rag-worker + mcp-server -> collector (zero-code instrumentation)
    edge([P("rag", "r", 25), (1195, 1030), (1195, 1368), P("otelcol", "l")], o, "OTLP/HTTP :4318 · traces + metrics",
         (2280, 1346) if D8 else (2585, 1360), width=2.8)
    edge([P("mcp", "r", -28), (1470, 1462), (1470, 1368)], o, arrow=False, width=2.8)
    labels_svg.append((1620, 1396, "zero-code OTel → otel-collector", o, "middle"))
    # collector fan-out
    edge([P("otelcol", "r"), (3130, 1368), (3130, 700), P("prom", "l")], o, "metrics", (3230, 692))
    edge([(3130, 1368), (3130, 990), P("tempo", "l")], o, "traces", (3230, 982))
    edge([(3130, 1368), (3130, 1270), P("loki", "l")], o, "logs", (3230, 1262))
    edge([(3130, 700), (3130, 540), (3905, 540), P("lf_web", "t")], o, "traces → Langfuse (OTLP/HTTP /api/public/otel)", (3450, 532))
    # pod logs from both nodes -> Loki
    edge([P("agent_d", "r"), (2150, 1515), (2150, 1600), (3630, 1600)], o, "pod logs (node gpu-node) → Loki", (2585, 1592), arrow=False)
    edge([P("agent_s", "t"), (3630, 1300), P("loki", "r", 30)], o, "pod logs", (3620, 1450), anchor="end")
    # Grafana queries its three datasources
    edge([P("grafana", "l"), P("tempo", "r")], ap, "queries", (3475, 982))
    edge([P("grafana", "l", -25), (3470, 965), (3470, 700), P("prom", "r")], ap)
    edge([P("grafana", "l", 25), (3470, 1015), (3470, 1270), P("loki", "r")], ap)

# --- Day 8: Tailscale ingress, Prompt Guard on the request path, GHCR images pinned to a SHA
if D8:
    ts = C["ts"]
    # phone, under the terminal, in the empty left column
    cluster(40, 968, 460, 1196, "Phone", "Tailscale · same private tailnet",
            fill="#f4f5f7", stroke="#111827", ico="phone.png", ico_size=32)
    node("phone", 250, 1084, "phone.png", ["phone", "Tailscale"], 78)
    # images built by GitHub Actions, pulled from GHCR. The gated model is not in the image.
    cluster(40, 1248, 470, 1724, "GHCR", "GitHub Actions on main",
            fill="#f4f5f7", stroke="#111827", ico="github.png", ico_size=32)
    node("gh", 118, 1390, "github.png", ["GitHub Actions", "builds the images"], 64)
    text(210, 1352, "pulled from GHCR", 14, 600, "#1f2a33", "start")
    text(210, 1376, "pinned to commit SHA", 14, 500, "#34404c", "start")
    text(210, 1400, "not the latest tag", 14, 500, "#34404c", "start")
    text(58, 1544, "rag-worker", 15, 700, "#1f2a33", "start")
    text(188, 1544, "mcp-server", 15, 700, "#1f2a33", "start")
    text(328, 1544, "prompt-guard", 15, 700, "#1f2a33", "start")
    text(58, 1580, "node gpu-node pulls these three images.", 14, 500, "#34404c", "start")
    text(58, 1604, "The gated model stays on the PVC,", 14, 500, "#34404c", "start")
    text(58, 1628, "not in the image.", 14, 500, "#34404c", "start")
    edge([(400, 1468), (448, 1468), (448, 1688), (820, 1688)], ts,
         "SHA-pinned image pull", (548, 1676), anchor="start")

    # operator + one proxy pod per Ingress. Pods run on node gpu-node (monitoring node is tainted).
    cluster(2476, 248, 2724, 1312, "tailscale", "namespace · node gpu-node · privileged",
            fill="#f4f5f7", stroke="#111827", ico="tailscale.png", ico_size=30, width=2.5)
    node("ts_op", 2600, 430, "tailscale_deploy.png", ["operator", "Helm chart 1.102.4"], 60)
    node("ts_web", 2600, 640, "tailscale.png", ["webui", "Ingress proxy"], 56)
    node("ts_graf", 2600, 850, "tailscale.png", ["grafana", "Ingress proxy"], 56)
    node("ts_lf", 2600, 1060, "tailscale.png", ["langfuse", "Ingress proxy"], 56)
    text(2600, 1188, "private tailnet only", 13.5, 650, "#1f2a33")
    text(2600, 1210, "no Funnel · no public ingress", 13, 500, "#34404c")
    text(2600, 1234, "Let's Encrypt on the tailnet", 13, 500, "#34404c")
    text(2600, 1268, "NetworkPolicy lets these", 12.5, 500, "#5b6570")
    text(2600, 1288, "proxies reach langfuse-web", 12.5, 500, "#5b6570")

    # clients → the tailscale namespace. Left margin, then under both hosts, then up the gap.
    edge([(110, 934), (18, 934), (18, 2390), (2704, 2390), (2704, 1336), (2600, 1336), (2600, 1312)],
         ts, "private tailnet · terminal and phone", (980, 2374))
    edge([P("phone", "b"), (250, 1222), (18, 1222)], ts, arrow=False)
    # proxies → the three ClusterIP services (orthogonal routes through open gaps)
    edge([P("ts_web", "l"), (2488, 640), (2488, 448), (1280, 448), (1185, 448), P("owui", "t")], ts,
         "webui · tailnet HTTPS → :8080", (1860, 436))
    edge([P("ts_graf", "r"), (2810, 850), (2810, 900), (3620, 900), P("grafana", "t")], ts,
         "grafana · tailnet HTTPS", (3240, 888))
    edge([P("ts_lf", "r"), (2810, 1060), (2810, 1520), (4265, 1520), (4265, 568), (3905, 568), P("lf_web", "t")], ts,
         "langfuse · tailnet HTTPS", (3400, 1506))

    # Prompt Guard is already a pod. Day 8 puts it on the request path.
    edge([(1236, 1105), (1236, 1222), P("pguard", "r")], C["app"],
         "OWUI filter: each user message", (908, 1204), anchor="end")
    edge([P("mcp", "t"), (1310, 1364), (1050, 1364), P("pguard", "b")], C["app"],
         "args + chunks\nbefore Ollama", (1088, 1304), anchor="start")

# ================================================================ render
body = out[:]  # clusters + header so far
out.clear()
draw_edges(); edges_part = out[:]; out.clear()
draw_nodes(); nodes_part = out[:]; out.clear()
draw_edge_labels(); labels_part = out[:]; out.clear()

def font_face():
    """Embed a subset of Inter (woff2, variable weight) so the SVG renders the same in browsers/Notion
    without Inter installed. rsvg-convert ignores @font-face and falls back to the installed Inter."""
    import io, re as _re
    from fontTools import subset
    from fontTools.ttLib import TTFont
    src = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
    chars = set(html.unescape(_re.sub(r"<[^>]+>", "", "".join(t for t in body + labels_part if "<text" in t))))
    font = TTFont(src)
    opts = subset.Options(); opts.flavor = "woff2"; opts.layout_features = ["*"]
    sub = subset.Subsetter(opts); sub.populate(text="".join(chars) + " "); sub.subset(font)
    buf = io.BytesIO(); font.flavor = "woff2"; font.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (f'<style>@font-face{{font-family:"InterEmbedded";font-weight:100 900;'
            f'src:url(data:font/woff2;base64,{b64}) format("woff2");}}</style>')

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       font_face(), f'<rect width="{W}" height="{H}" fill="#ffffff"/>'] + body + edges_part + nodes_part + labels_part + ["</svg>"]
OUT.with_suffix(".svg").write_text("\n".join(svg))
subprocess.run(["rsvg-convert", "-z", "2", "-b", "white", "-o", str(OUT.with_suffix(".png")), str(OUT.with_suffix(".svg"))], check=True)
print("wrote", OUT.with_suffix(".svg"), OUT.with_suffix(".png"))
