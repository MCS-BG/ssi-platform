#!/usr/bin/env python3
"""Sovereign Super Intelligence — real-world control layer (READABLE poster).

Large fonts, short labels, ~12 primary boxes.
Observability (Langfuse · Grafana) is a quiet lane, not a spotlight.
No Copilot UI path. Power BI is reporting only.

    python si_control_layer_real_world.py
"""
import base64, html, io, re, subprocess
from pathlib import Path
import diagrams

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
RES = Path(diagrams.__file__).resolve().parent.parent / "resources"
OUT = HERE / "si-control-layer-real-world"

# Large canvas; rsvg-convert -z 2 → ~11200×8000 PNG
W, H = 5600, 4000
FONT = "InterEmbedded, Inter, 'Noto Sans', 'DejaVu Sans', sans-serif"

# High-contrast palette
BLACK = "#0b1220"
MUTED = "#334155"
LINE = "#94a3b8"
LIVE = "#15803d"
TARGET = "#7c3aed"
STROKE_SOFT = "#cbd5e1"
STORE = "#c2410c"
REPORT = "#0e7490"
TS = "#111827"
STRIKE = "#b91c1c"
BG_PAGE = "#ffffff"
BG_SOFT = "#f8fafc"
BG_PEOPLE = "#eff6ff"
BG_CTRL = "#f5f3ff"
BG_STORE = "#fff7ed"
BG_REPORT = "#ecfeff"
BG_STRIKE = "#fef2f2"
BG_LIVE = "#f0fdf4"

out = []
SHOWN = []


def icon(name):
    p = ICONS / name if (ICONS / name).exists() else RES / name
    if not p.exists():
        raise SystemExit(f"missing icon {name}")
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def esc(s):
    return html.escape(s, quote=True)


def text(x, y, s, size=24, weight=400, color=BLACK, anchor="middle", halo=False):
    SHOWN.append(s)
    st = ' stroke="#ffffff" stroke-width="6" stroke-linejoin="round" paint-order="stroke"' if halo else ""
    out.append(
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}" text-anchor="{anchor}"{st}>{esc(s)}</text>'
    )


def box(x0, y0, x1, y1, fill=BG_SOFT, stroke=STROKE_SOFT, width=3, dash=False, rx=20):
    d = ' stroke-dasharray="14 8"' if dash else ""
    out.append(
        f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{d}/>'
    )


def badge(x, y, label, fill=LIVE, fs=20):
    bw = 28 + 11 * len(label)
    out.append(f'<rect x="{x - bw}" y="{y - 18}" width="{bw}" height="32" rx="16" fill="{fill}"/>')
    text(x - bw / 2, y + 4, label, fs, 700, "#ffffff")


N = {}
out_nodes = []


def node(key, x, y, ico, label, size=96):
    """label: list of short lines. First line is bold."""
    N[key] = (x, y, size)
    out_nodes.append((x, y, ico, label, size))


def draw_nodes():
    for x, y, ico, label, size in out_nodes:
        out.append(
            f'<image href="{icon(ico)}" x="{x - size/2}" y="{y - size/2}" '
            f'width="{size}" height="{size}" preserveAspectRatio="xMidYMid meet"/>'
        )
        ly = y + size / 2 + 28
        for i, line in enumerate(label):
            text(
                x, ly + i * 31, line,
                26 if i == 0 else 22,
                700 if i == 0 else 500,
                BLACK if i == 0 else MUTED,
                halo=True,
            )


def P(key, side, off=0, gap=10):
    x, y, s = N[key]
    h = s / 2 + gap
    return {
        "l": (x - h, y + off),
        "r": (x + h, y + off),
        "t": (x + off, y - h),
        "b": (x + off, y + h),
    }[side]


markers = set()
edges_svg = []
labels_svg = []


def edge(pts, color, label=None, lpos=None, dashed=False, width=3.5, anchor="middle", arrow=True):
    r = 16
    d = f"M{pts[0][0]},{pts[0][1]}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]

        def towards(ax, ay, bx, by, dist):
            L = max(abs(bx - ax), abs(by - ay)) or 1
            dd = min(dist, L / 2)
            return ax + (bx - ax) / L * dd, ay + (by - ay) / L * dd

        a = towards(x1, y1, x0, y0, r)
        b = towards(x1, y1, x2, y2, r)
        d += f" L{a[0]:.1f},{a[1]:.1f} Q{x1},{y1} {b[0]:.1f},{b[1]:.1f}"
    d += f" L{pts[-1][0]},{pts[-1][1]}"
    markers.add(color)
    da = ' stroke-dasharray="12 8"' if dashed else ""
    me = f' marker-end="url(#arr{color.strip("#")})"' if arrow else ""
    edges_svg.append(
        f'<path d="{d}" fill="none" stroke="#ffffff" stroke-opacity="0.95" stroke-width="{width + 7}"/>'
    )
    edges_svg.append(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da}{me}/>'
    )
    if label and lpos:
        lx, ly = lpos
        for i, line in enumerate(label.split("\n")):
            labels_svg.append((lx, ly + i * 29, line, color, anchor))


def draw_edges():
    out.append("<defs>")
    for c in markers:
        out.append(
            f'<marker id="arr{c.strip("#")}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            f'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
        )
    out.append("</defs>")
    out.extend(edges_svg)


def draw_edge_labels():
    for x, y, s, c, a in labels_svg:
        text(x, y, s, 22, 650, c, a, halo=True)


# =============================================================================
# LAYOUT — top to bottom, short labels only
# =============================================================================

# Title
text(80, 90, "Sovereign Super Intelligence — control layer", 62, 800, BLACK, "start")
text(80, 150, "One agent loop · MCP to systems of record · Power BI on the same data", 29, 500, MUTED, "start")

# Legend (compact, large type)
leg_y = 210
items = [
    ("live", LIVE, False),
    ("target (not deployed)", TARGET, True),
    ("data / warehouse", STORE, False),
    ("reporting", REPORT, False),
    ("private network", TS, False),
]
lx = 80
for lab, col, dash in items:
    da = ' stroke-dasharray="12 8"' if dash else ""
    out.append(f'<line x1="{lx}" y1="{leg_y}" x2="{lx + 56}" y2="{leg_y}" stroke="{col}" stroke-width="5"{da}/>')
    out.append(f'<path d="M{lx+56},{leg_y-8} L{lx+70},{leg_y} L{lx+56},{leg_y+8} z" fill="{col}"/>')
    text(lx + 84, leg_y + 8, lab, 24, 500, MUTED, "start")
    lx += 84 + 12 * len(lab) + 48

# -----------------------------------------------------------------------------
# ROW 1 — People | Open WebUI | Control layer | Model
# -----------------------------------------------------------------------------
# People
box(60, 280, 720, 780, BG_PEOPLE, "#93c5fd", 4)
text(100, 340, "People", 37, 800, BLACK, "start")
text(100, 385, "private network — VPN in the lab ·", 24, 500, MUTED, "start")
text(100, 420, "Private Link / VPN at work", 24, 500, MUTED, "start")

# Open WebUI
box(760, 280, 1680, 780, BG_LIVE, "#86efac", 4)
text(800, 340, "Open WebUI", 37, 800, BLACK, "start")
text(800, 385, "human chat", 24, 500, MUTED, "start")
badge(1640, 340, "live", LIVE, 20)

# Control layer
box(1760, 280, 3400, 780, BG_LIVE, "#86efac", 4)
text(1800, 340, "Control layer", 37, 800, BLACK, "start")
text(1800, 385, "the only agent loop", 24, 500, MUTED, "start")
badge(3360, 340, "live", LIVE, 20)
text(1800, 460, "Choose tool → read JSON → call model", 24, 500, BLACK, "start")
text(1800, 500, "Budget · fail closed with Guard", 24, 500, BLACK, "start")

# Model
box(3480, 280, 4340, 780, BG_SOFT, STROKE_SOFT, 4)
text(3520, 340, "Model", 37, 800, BLACK, "start")
text(3520, 385, "Ollama · local slot", 24, 500, MUTED, "start")
badge(4300, 340, "live", LIVE, 20)

# Power BI column (right)
box(4440, 280, 5540, 1480, BG_REPORT, REPORT, 4)
text(4480, 340, "Reporting", 37, 800, BLACK, "start")
text(4480, 385, "not the agent loop", 24, 500, MUTED, "start")

# -----------------------------------------------------------------------------
# ROW 2 — Prompt Guard (full band under chat/control)
# -----------------------------------------------------------------------------
box(60, 840, 4340, 1120, "#ffffff", "#93c5fd", 4)
text(100, 910, "Prompt Guard", 37, 800, BLACK, "start")
text(100, 960, "In front of chat and every MCP call · fail closed", 26, 500, MUTED, "start")
badge(4300, 910, "live", LIVE, 20)

# -----------------------------------------------------------------------------
# ROW 3 — Four MCP slots
# -----------------------------------------------------------------------------
MCP_Y0, MCP_Y1 = 1200, 1880
slots = [
    (60, 1080, "Microsoft 365 MCP", "Productivity · Microsoft Graph", "live", LIVE, BG_LIVE),
    (1160, 2180, "ERP MCP", "D365 / Dataverse", "sample live", LIVE, BG_LIVE),
    (2260, 3280, "Engineering MCP", "GitHub · ADO", "sample live", LIVE, BG_LIVE),
    (3360, 4340, "Data MCP", "Postgres facts", "design", TARGET, BG_STORE),
]
for (x0, x1, title, sub, bad, bfill, fill) in slots:
    dash = bad in ("design", "target")
    box(x0, MCP_Y0, x1, MCP_Y1, fill, bfill if dash else "#86efac", 4, dash=dash)
    text(x0 + 40, MCP_Y0 + 60, title, 33, 800, BLACK, "start")
    text(x0 + 40, MCP_Y0 + 110, sub, 24, 500, MUTED, "start")
    badge(x1 - 20, MCP_Y0 + 60, bad, bfill, 20)

# Productivity slot detail (Day 14 m365-mcp)
text(100, MCP_Y0 + 150, "Read-only: mail · calendar · OneDrive", 24, 500, BLACK, "start")

# -----------------------------------------------------------------------------
# ROW 4 — Systems of record (one band, four short labels)
# -----------------------------------------------------------------------------
box(60, 1960, 4340, 2480, "#f1f5f9", "#93c5fd", 4)
text(100, 2030, "Systems of record", 37, 800, BLACK, "start")
text(100, 2080, "What the MCP tools call · cluster secrets · not Copilot", 24, 500, MUTED, "start")

# -----------------------------------------------------------------------------
# Nodes
# -----------------------------------------------------------------------------
node("term", 390, 520, "onprem/client/client.png", ["Terminal"], 100)
node("ts", 390, 680, "private_network.png", ["Private", "network"], 72)

node("owui", 1220, 560, "openwebui_deploy.png", ["Open WebUI"], 100)
node("ctrl", 2580, 560, "k8s/controlplane/api.png", ["Control layer"], 96)
node("ollama", 3910, 560, "ollama_deploy.png", ["Ollama"], 96)

node("pguard", 2200, 1000, "promptguard_deploy.png", ["Prompt Guard"], 100)

node("mcp_prod", 570, 1480, "mcp_deploy.png", ["M365 · m365_*"], 88)
node("mcp_erp", 1670, 1480, "mcp_deploy.png", ["ERP · fo_*"], 88)
node("mcp_eng", 2770, 1480, "github.png", ["Engineering"], 88)
node("mcp_data", 3850, 1480, "mcp_deploy.png", ["Data"], 88)

node("graph", 570, 2260, "azure/identity/app-registrations.png", ["Microsoft Graph", "mail · calendar · OneDrive"], 80)
node("d365", 1670, 2260, "azure/web/power-platform.png", ["D365 / Dataverse"], 80)
node("ghado", 2770, 2260, "github.png", ["GitHub · ADO"], 80)
node("pgfacts", 3850, 2260, "onprem/database/postgresql.png", ["Postgres facts"], 80)

node("pbi", 4990, 560, "onprem/analytics/powerbi.png", ["Power BI", "Desktop"], 110)
node("pgwh", 4990, 1100, "onprem/database/postgresql.png", ["Postgres", "warehouse"], 100)

# Short system credential hints under systems icons
text(570, 2420, "Entra app · delegated, read-only", 22, 500, MUTED)
text(1670, 2420, "Entra app", 22, 500, MUTED)
text(2770, 2420, "token / App / PAT", 22, 500, MUTED)
text(3850, 2420, "DB read role", 22, 500, MUTED)

# Power BI body text (short)
text(4480, 760, "SQL query · paints charts", 24, 500, BLACK, "start")
text(4480, 800, "Does not choose tools", 24, 500, MUTED, "start")
text(4480, 1280, "Same warehouse the", 24, 500, BLACK, "start")
text(4480, 1320, "data MCP can read", 24, 500, BLACK, "start")

# -----------------------------------------------------------------------------
# Cross-share note (one line band)
# -----------------------------------------------------------------------------
box(60, 2560, 4340, 2780, BG_SOFT, STROKE_SOFT, 3)
text(100, 2640, "Cross-share", 33, 800, BLACK, "start")
text(100, 2700, "MCPs do not peer · the control layer accumulates results in one loop", 26, 500, MUTED, "start")

# -----------------------------------------------------------------------------
# Copilot banner (ONE short banner)
# -----------------------------------------------------------------------------
box(60, 2860, 5540, 3100, BG_STRIKE, STRIKE, 3, dash=True)
text(100, 2960, "Copilot UIs not used", 37, 800, STRIKE, "start")
text(100, 3020, "M365 Copilot · GitHub Copilot · Copilot Studio  →  replaced by Control layer + Open WebUI", 26, 500, MUTED, "start")

# -----------------------------------------------------------------------------
# Request path footer (readable steps, large type)
# -----------------------------------------------------------------------------
box(60, 3180, 5540, 3900, BG_SOFT, STROKE_SOFT, 3)
text(100, 3260, "One request", 33, 800, BLACK, "start")
steps = [
    "1. Person opens Open WebUI over a private network — VPN in the lab · Private Link / VPN at work",
    "2. Prompt Guard checks the message",
    "3. Control layer runs the agent loop",
    "4. Guard → chosen MCP → JSON back",
    "5. Result saved · model called again",
    "6. Other MCP slots as needed · then answer",
]
# Two columns of steps
for i, s in enumerate(steps):
    col = 0 if i < 3 else 1
    row = i if i < 3 else i - 3
    x = 100 + col * 2700
    y = 3340 + row * 78
    text(x, y, s, 26, 500, BLACK, "start")

text(100, 3620, "Power BI path (separate): Postgres warehouse → Power BI Desktop → charts", 26, 600, REPORT, "start")
text(100, 3680, "Observability (quiet): Langfuse traces hops · Grafana ops — not the agent loop", 24, 500, MUTED, "start")
text(100, 3740, "Credentials: Entra apps / tokens in cluster secrets · no Copilot seats", 26, 500, MUTED, "start")
text(100, 3820, "Lab today: Open WebUI, Prompt Guard, Microsoft 365 MCP, ERP MCP sample, Engineering MCP sample, Control layer, Ollama, Langfuse, Grafana live in si-lab", 24, 500, MUTED, "start")

# -----------------------------------------------------------------------------
# Edges
# -----------------------------------------------------------------------------
edge([P("term", "b"), P("ts", "t")], TS, arrow=False)
edge([P("ts", "r"), (720, 680), (720, 560), P("owui", "l")], TS,
     "private network —\nVPN in the lab ·\nPrivate Link / VPN at work",
     (780, 600), anchor="start")

edge([P("owui", "b"), (1220, 780), (1220, 1000), P("pguard", "l")], LIVE, "chat", (1180, 900), anchor="end")
edge([P("ctrl", "b"), (2580, 780), (2580, 920), (2400, 920), P("pguard", "r")], LIVE, "loop", (2680, 900))

# Guard fan-out to MCPs
edge([P("pguard", "b"), (2200, 1160), (570, 1160), P("mcp_prod", "t")], LIVE)
edge([(2200, 1160), (1670, 1160), P("mcp_erp", "t")], LIVE, "Guard → MCP", (2200, 1140))
edge([(2200, 1160), (2770, 1160), P("mcp_eng", "t")], LIVE)
edge([(2200, 1160), (3850, 1160), P("mcp_data", "t")], STORE, dashed=True)

# MCP → systems
edge([P("mcp_prod", "b"), P("graph", "t")], LIVE)
edge([P("mcp_erp", "b"), P("d365", "t")], LIVE)
edge([P("mcp_eng", "b"), P("ghado", "t")], LIVE)
edge([P("mcp_data", "b"), P("pgfacts", "t")], STORE)

# Control ↔ model (conceptual)
edge([P("ctrl", "r"), P("ollama", "l")], LIVE, "asks model", (3200, 540))

# Same warehouse → Power BI
edge([P("pgfacts", "r"), (4340, 2260), (4600, 2260), (4600, 1100), P("pgwh", "l")], STORE, "same data", (4480, 2000), dashed=True)
edge([P("pgwh", "t"), P("pbi", "b")], REPORT, "SQL · charts", (5120, 860))

# =============================================================================
# Render
# =============================================================================
body = out[:]
out.clear()
draw_edges()
edges_part = out[:]
out.clear()
draw_nodes()
nodes_part = out[:]
out.clear()
draw_edge_labels()
labels_part = out[:]
out.clear()


def font_face():
    from fontTools import subset
    from fontTools.ttLib import TTFont
    src = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
    chars = set(
        html.unescape(
            re.sub(r"<[^>]+>", "", "".join(t for t in body + labels_part if "<text" in t))
        )
    )
    font = TTFont(src)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(chars) + " ")
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (
        f'<style>@font-face{{font-family:"InterEmbedded";font-weight:100 900;'
        f'src:url(data:font/woff2;base64,{b64}) format("woff2");}}</style>'
    )


svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
    font_face(),
    f'<rect width="{W}" height="{H}" fill="{BG_PAGE}"/>',
]
svg += body + edges_part + nodes_part + labels_part + ["</svg>"]
OUT.with_suffix(".svg").write_text("\n".join(svg))
subprocess.run(
    [
        "rsvg-convert",
        "-z",
        "2",
        "-b",
        "white",
        "-o",
        str(OUT.with_suffix(".png")),
        str(OUT.with_suffix(".svg")),
    ],
    check=True,
)
print("wrote", OUT.with_suffix(".svg"), OUT.with_suffix(".png"))
print("---LABELS---")
for s in SHOWN:
    print(s)
