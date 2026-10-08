#!/usr/bin/env python3
"""Convert homelab_diagram.py's layout into a native, editable draw.io file.

Reuses the layout data in homelab_diagram.py (cluster boxes, icon nodes, edges, labels) by executing
its definitions and layout section with recording versions of cluster()/edge()/text(), then emits
uncompressed mxGraph XML:
  * every icon  -> image vertex (base64 PNG data URI) with its label underneath
  * every box   -> rounded container; children are parented to the smallest enclosing box
  * every edge  -> mxCell edge with source/target ids, pinned ports (exitX/exitDx...), waypoints
Run with the diagrams venv:  .venv/bin/python build_drawio.py
"""
import base64, html, re
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "homelab_diagram.py").read_text()
OUT = HERE / "history" / "homelab-architecture.drawio"
FONT = "Inter"

defs_src, rest = SRC.split("# ================================================================ LAYOUT")
layout_src = rest.split("# ================================================================ render")[0]

ns = {"__file__": str(HERE / "homelab_diagram.py"), "__name__": "homelab_layout"}
exec(compile(defs_src, "homelab_diagram.py", "exec"), ns)

# ---------------------------------------------------------------- recorders
CLUSTERS, EDGES, TEXTS = [], [], []
def rec_cluster(x0, y0, x1, y1, title, sub="", fill="#ffffff", stroke="#c5ced8", dash=False, ico=None, ico_size=34,
                title_color="#1b2733", badge=None, width=2):
    CLUSTERS.append(dict(x0=x0, y0=y0, x1=x1, y1=y1, title=title, sub=sub, fill=fill, stroke=stroke, dash=dash,
                         ico=ico, ico_size=ico_size, title_color=title_color, badge=badge, width=width))
def rec_edge(pts, color, label=None, lpos=None, dashed=False, dotted=False, width=2.4, anchor="middle", lcolor=None, arrow=True):
    EDGES.append(dict(pts=[tuple(p) for p in pts], color=color, label=label, lpos=lpos, dashed=dashed, dotted=dotted,
                      width=width, anchor=anchor, lcolor=lcolor, arrow=arrow))
def rec_text(x, y, s, size=15, weight=400, color="#1f2a33", anchor="middle", halo=False, italic=False):
    TEXTS.append(dict(x=x, y=y, s=s, size=size, weight=weight, color=color, anchor=anchor))
ns.update(cluster=rec_cluster, edge=rec_edge, text=rec_text)
exec(compile(layout_src, "homelab_diagram.py", "exec"), ns)

N, out_nodes, C, icon_uri = ns["N"], ns["out_nodes"], ns["C"], ns["icon"]
LEGEND_SVG = [s for s in ns["out"] if s.startswith("<line")]

def png_uri(ico):
    # homelab_diagram.icon() returns data:image/png;base64,... ; draw.io wants data:image/png,<b64>
    return icon_uri(ico).replace("data:image/png;base64,", "data:image/png,")

# ---------------------------------------------------------------- helpers
from PIL import ImageFont
INTER = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
_fonts = {}
def measure(s, size, bold=False):
    """Approximate rendered width of a text line in Inter (used for snug label/text boxes, which keeps
    left-aligned text in place when draw.io exports to VSDX)."""
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    f = _fonts.get(size) or _fonts.setdefault(size, ImageFont.truetype(INTER, size))
    return f.getlength(s) * (1.07 if bold else 1.0)

def rich(s):  # svg tspan bold -> html
    return re.sub(r"<tspan font-weight='700'>(.*?)</tspan>", r"<b>\1</b>", s)

def style(**kw):
    return ";".join(k if v is None else f"{k}={v}" for k, v in kw.items()) + ";"

def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

# ---------------------------------------------------------------- containers / parenting
BOX_IDS = {"Terminal": "box_terminal", "Lab host": "box_lab_host", "k3s": "box_k3s", "namespace: si-lab": "ns_ai_lab",
           "namespace: gpu-system": "ns_gpu_system", "Open WebUI": "box_open_webui", "RAG worker": "box_rag_worker",
           "pgvector": "box_pgvector", "Ollama": "box_ollama", "cluster-scoped storage": "box_cluster_storage",
           "Host disks": "box_host_disks", "GPU stack": "box_gpu_stack"}
for i, c in enumerate(CLUSTERS):
    c["id"] = next(v for k, v in BOX_IDS.items() if c["title"].startswith(k))
    c["idx"] = i

def area(c): return (c["x1"] - c["x0"]) * (c["y1"] - c["y0"])
def inside(x, y, c): return c["x0"] <= x <= c["x1"] and c["y0"] <= y <= c["y1"]

def fill_at(x, y):
    p = parent_of_point(x, y)
    return p["fill"] if p else "#ffffff"

def parent_of_point(x, y, exclude=None):
    cands = [c for c in CLUSTERS if c is not exclude and inside(x, y, c)]
    return min(cands, key=area) if cands else None

for c in CLUSTERS:
    cands = [p for p in CLUSTERS if p is not c and p["x0"] <= c["x0"] and p["y0"] <= c["y0"]
             and p["x1"] >= c["x1"] and p["y1"] >= c["y1"]]
    c["parent"] = min(cands, key=area) if cands else None

ORIGIN = {"1": (0, 0)}
PARENT = {}
for c in CLUSTERS:
    ORIGIN[c["id"]] = (c["x0"], c["y0"])
    PARENT[c["id"]] = c["parent"]["id"] if c["parent"] else "1"
NODE_PARENT = {}
for key, (x, y, s) in N.items():
    p = parent_of_point(x, y)
    NODE_PARENT[key] = p["id"] if p else "1"
    PARENT[key] = NODE_PARENT[key]

def chain(cid):
    out = [cid]
    while cid != "1":
        cid = PARENT[cid]; out.append(cid)
    return out

def lca(a, b):
    ca, cb = chain(PARENT[a]), chain(PARENT[b])
    for x in ca:
        if x in cb: return x
    return "1"

# ---------------------------------------------------------------- edge endpoints -> node ports
GAP = 6
def match_port(pt):
    px, py = pt
    for key, (x, y, s) in N.items():
        h = s / 2 + GAP
        if abs(px - (x - h)) < 0.01 and abs(py - y) <= s / 2: return key, "l", (px, py)
        if abs(px - (x + h)) < 0.01 and abs(py - y) <= s / 2: return key, "r", (px, py)
        if abs(py - (y - h)) < 0.01 and abs(px - x) <= s / 2: return key, "t", (px, py)
        if abs(py - (y + h)) < 0.01 and abs(px - x) <= s / 2: return key, "b", (px, py)
    return None

# Endpoints in homelab_diagram.py that are not on an icon's port ring (branch points off another edge, or
# arrows that stop at a box border below a label). Map them to the real node they belong to.
P = ns["P"]
START_FIX = {  # start point -> (node, side, offset, extra waypoints to insert after the port)
    (200, 720): ("terminal", "r", -10, [(200, 710)]),       # helm branch of the terminal edge
    (1262, 1005): ("rag", "r", 0, []),                 # rag-worker fan-out branches
    (760, 1598): ("toolkit", "t", 0, None),            # toolkit top edge (icon has transparent padding)
}
END_FIX = {  # end point -> (node, side): keep the exact point, pinned relative to that node
    (1425, 1205): ("svc_ollama", "b"),                 # port-forward 11435 -> 11434, stops below label
    (760, 1512): ("node_d", "b"),                      # nvidia runtime -> node gpu-node
    (1580, 1506): ("devplugin", "b"),                  # nvidia.com/gpu -> device plugin (gpu-system ns)
    (1580, 1212): ("ollama", "b"),                     # 1x GPU -> ollama
}

def constraint(key, side, pt, prefix):
    x, y, s = N[key]
    h = s / 2
    base = {"l": (0, .5, x - h, y), "r": (1, .5, x + h, y), "t": (.5, 0, x, y - h), "b": (.5, 1, x, y + h)}[side]
    fx, fy, bx, by = base
    return {f"{prefix}X": fx, f"{prefix}Y": fy, f"{prefix}Dx": round(pt[0] - bx, 2), f"{prefix}Dy": round(pt[1] - by, 2),
            f"{prefix}Perimeter": 0}

def resolve(e):
    pts = list(e["pts"])
    s0 = tuple(pts[0])
    if s0 in START_FIX:
        key, side, off, extra = START_FIX[s0]
        if extra is None:            # keep the exact start point, pinned to that node
            src = (key, side, s0)
        else:                        # branch point: start at the node's port, keep the branch point as a waypoint
            src = (key, side, P(key, side, off))
            pts = [src[2]] + extra + pts
    else:
        src = match_port(s0)
        assert src, f"unmatched start {s0}"
    t0 = tuple(pts[-1])
    if t0 in END_FIX:
        key, side = END_FIX[t0]; tgt = (key, side, t0)
    else:
        tgt = match_port(t0)
        assert tgt, f"unmatched end {t0}"
    return src, tgt, pts   # pts: full absolute polyline incl. endpoints

def polyline_mid(pts):
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lens = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in segs]
    half = sum(lens) / 2
    for (a, b), L in zip(segs, lens):
        if half <= L and L > 0:
            t = half / L
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        half -= L
    return pts[-1]

# ---------------------------------------------------------------- XML
mxfile = ET.Element("mxfile", host="Electron", agent="build_drawio.py", type="device")
diagram = ET.SubElement(mxfile, "diagram", id="homelab-architecture", name="ssi-platform architecture")
model = ET.SubElement(diagram, "mxGraphModel", dx="2490", dy="1815", grid="1", gridSize="10", guides="1", tooltips="1",
                      connect="1", arrows="1", fold="1", page="1", pageScale="1", pageWidth="2490", pageHeight="1815",
                      math="0", shadow="0", background="#ffffff")
root = ET.SubElement(model, "root")
ET.SubElement(root, "mxCell", id="0")
ET.SubElement(root, "mxCell", id="1", parent="0")

def geom(cell, x, y, w, h, **extra):
    g = ET.SubElement(cell, "mxGeometry", x=f"{x:g}", y=f"{y:g}", width=f"{w:g}", height=f"{h:g}", **extra)
    g.set("as", "geometry")
    return g

def vertex(cid, value, sty, parent, x, y, w, h):
    """x, y are absolute canvas coordinates; converted to parent-relative."""
    ox, oy = ORIGIN[parent]
    cell = ET.SubElement(root, "mxCell", id=cid, value=value, style=sty, vertex="1", parent=parent)
    geom(cell, x - ox, y - oy, w, h)
    return cell

LH = 1.2
def text_box(size, baseline):  # top of an html text line whose baseline is at `baseline`
    return baseline - size * 0.97 - size * (LH - 1) / 2

# --- header texts (title, subtitle) and legend
legend_texts = [t for t in TEXTS if t["size"] == 14.5]
for i, t in enumerate([t for t in TEXTS if t["size"] != 14.5]):
    w = round(measure(t["s"], t["size"], t["weight"] >= 600) + 2)
    sty = style(text=None, html=1, align="left", verticalAlign="top", spacing=0, spacingTop=0, whiteSpace=None,
                fontFamily=FONT, fontSize=t["size"], fontColor=t["color"], fontStyle=1 if t["weight"] >= 600 else 0)
    val = f'<span style="font-weight:{t["weight"]}">{t["s"]}</span>'
    vertex("title" if i == 0 else "subtitle", val, sty, "1", t["x"], text_box(t["size"], t["y"]), w, t["size"] * LH)

lx0 = min(t["x"] for t in legend_texts) - 62
ly0 = legend_texts[0]["y"] - 18
lw = max(t["x"] + 7.6 * len(t["s"]) for t in legend_texts) - lx0
legend = vertex("legend", "", style(group=None, container=1, collapsible=0, fillColor="none", strokeColor="none",
                                    connectable=0, recursiveResize=0), "1", lx0, ly0, lw, 24)
ORIGIN["legend"] = (lx0, ly0)
for i, (line, t) in enumerate(zip(LEGEND_SVG, legend_texts)):
    a = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', line))
    x1, y1, x2 = float(a["x1"]), float(a["y1"]), float(a["x2"])
    col = a["stroke"]
    dash = a.get("stroke-dasharray")
    sty = dict(endArrow="block", endFill=1, endSize=6, html=1, strokeColor=col, strokeWidth=3)
    if dash: sty.update(dashed=1, dashPattern=dash, fixDash=1)
    cell = ET.SubElement(root, "mxCell", id=f"legend_line_{i+1}", value="", style=style(**sty), edge="1", parent="legend")
    g = ET.SubElement(cell, "mxGeometry", relative="1"); g.set("as", "geometry")
    sp = ET.SubElement(g, "mxPoint", x=f"{x1 - lx0:g}", y=f"{y1 - ly0:g}"); sp.set("as", "sourcePoint")
    tp = ET.SubElement(g, "mxPoint", x=f"{x2 + 10 - lx0:g}", y=f"{y1 - ly0:g}"); tp.set("as", "targetPoint")
    tsty = style(text=None, html=1, align="left", verticalAlign="top", spacing=0, fontFamily=FONT, fontSize=t["size"],
                 fontColor=t["color"], connectable=0)
    vertex(f"legend_text_{i+1}", html.unescape(t["s"]), tsty, "legend", t["x"], text_box(t["size"], t["y"]),
           round(measure(t["s"], t["size"]) + 2), t["size"] * LH)

# --- containers, back to front (outer first so draw order matches the SVG)
def depth(c):
    d = 0
    while c["parent"]: c = c["parent"]; d += 1
    return d

EDGE_CELLS_BY_PARENT = {}
for c in sorted(CLUSTERS, key=lambda c: (depth(c), c["idx"])):
    tx = 16 + (c["ico_size"] + 10 if c["ico"] else 0)
    ty = 30 if not c["sub"] else 27             # title baseline offset from box top
    top = text_box(18, ty)
    val = f'<b>{html.escape(c["title"])}</b>'
    if c["sub"]:
        val += f'<br><span style="font-size:13.5px;color:#5b6570;font-weight:normal;line-height:1.48">{rich(c["sub"])}</span>'
    sty = dict(rounded=1, absoluteArcSize=1, arcSize=32, html=1, container=1, collapsible=0, recursiveResize=0,
               fillColor=c["fill"], strokeColor=c["stroke"], strokeWidth=c["width"], align="left", verticalAlign="top",
               spacingLeft=tx, spacingTop=round(top, 1), spacing=0, fontFamily=FONT, fontSize=18,
               fontColor=c["title_color"],
               labelWidth=round(max(measure(c["title"], 18, True), measure(c["sub"], 13.5)) + 4))
    if c["dash"]: sty.update(dashed=1, dashPattern="10 6", fixDash=1)
    vertex(c["id"], val, style(**sty), PARENT[c["id"]], c["x0"], c["y0"], c["x1"] - c["x0"], c["y1"] - c["y0"])

# children of each container, in order: header icon, badge, then (edges), then nodes
def emit_header_bits(c):
    if c["ico"]:
        vertex(c["id"] + "_icon", "", style(shape="image", html=1, image=png_uri(c["ico"]), imageAspect=1, aspect="fixed",
                                           verticalLabelPosition="bottom", verticalAlign="top", connectable=0),
               c["id"], c["x0"] + 16, c["y0"] + 10, c["ico_size"], c["ico_size"])
    if c["badge"]:
        b = c["badge"]
        tx = c["x0"] + 16 + (c["ico_size"] + 10 if c["ico"] else 0)
        ty = c["y0"] + (30 if not c["sub"] else 27)
        bw = 12 + 8.6 * len(b); bx = tx + 10.8 * len(c["title"]) + 14
        vertex(c["id"] + "_badge", html.escape(b),
               style(rounded=1, arcSize=50, html=1, fillColor=C["live"], strokeColor="none", fontColor="#ffffff",
                     fontStyle=1, fontSize=13, fontFamily=FONT, align="center", verticalAlign="middle", connectable=0,
                     spacing=0), c["id"], bx, ty - 17, bw, 24)

for c in CLUSTERS:
    emit_header_bits(c)

# --- edges (after all containers so a box's fill never hides an edge routed across it)
edge_report = []
for i, e in enumerate(EDGES, 1):
    (sk, sside, spt), (tk, tside, tpt), pts = resolve(e)
    parent = lca(sk, tk)
    ox, oy = ORIGIN[parent]
    sty = dict(edgeStyle="orthogonalEdgeStyle", rounded=1, arcSize=24, orthogonalLoop=1, jettySize="auto", html=1,
               endArrow="block" if e["arrow"] else "none", endFill=1, endSize=6, strokeColor=e["color"],
               strokeWidth=e["width"])
    sty.update(constraint(sk, sside, spt, "exit")); sty.update(constraint(tk, tside, tpt, "entry"))
    if e["dashed"]: sty.update(dashed=1, dashPattern="9 6", fixDash=1)
    if e["dotted"]: sty.update(dashed=1, dashPattern="2 5", fixDash=1)
    value = ""
    if e["label"]:
        lines = e["label"].split("\n")
        value = "<br>".join(html.escape(l) for l in lines)
        sty.update(fontFamily=FONT, fontSize=13.5, fontStyle=1, fontColor=e["lcolor"] or e["color"],
                   labelBackgroundColor=fill_at(*e["lpos"]), align={"start": "left", "end": "right"}.get(e["anchor"], "center"),
                   verticalAlign="top", spacing=0)
    cell = ET.SubElement(root, "mxCell", id=f"e{i:02d}_{sk}_{tk}", value=value, style=style(**sty), edge="1",
                         parent=parent, source=sk, target=tk)
    g = ET.SubElement(cell, "mxGeometry", relative="1"); g.set("as", "geometry")
    if e["label"]:
        mx, my = polyline_mid(pts)
        lx, ly = e["lpos"]
        off = ET.SubElement(g, "mxPoint", x=f"{lx - mx:.1f}", y=f"{text_box(13.5, ly) - my:.1f}"); off.set("as", "offset")
    wps = pts[1:-1]
    if wps:
        arr = ET.SubElement(g, "Array"); arr.set("as", "points")
        for (x, y) in wps:
            ET.SubElement(arr, "mxPoint", x=f"{x - ox:g}", y=f"{y - oy:g}")
    edge_report.append((cell.get("id"), parent))

# --- icon nodes (last, so icons + labels sit on top of edges like the SVG)
for key, (x, y, s) in N.items():
    ico, label, size = next((o[2], o[3], o[4]) for o in out_nodes if o[0] == x and o[1] == y)
    val = f"<b>{label[0]}</b>"
    for line in label[1:]:
        val += f'<br><span style="font-size:13.5px;color:#4b5661;font-weight:normal">{line}</span>'
    sty = style(shape="image", html=1, image=png_uri(ico), imageAspect=1, aspect="fixed", verticalLabelPosition="bottom",
                verticalAlign="top", labelPosition="center", align="center", spacing=0, spacingTop=-2, fontFamily=FONT,
                fontSize=15, fontStyle=1, fontColor="#1f2a33", labelBackgroundColor=fill_at(x, y),
                labelWidth=round(max([s] + [measure(label[0], 15, True) + 8] + [measure(l, 13.5) + 8 for l in label[1:]])))
    vertex(key, val, sty, NODE_PARENT[key], x - s / 2, y - s / 2, s, s)

# model order: mxGraph draws in document order within a parent. Move container-children so that, within
# each parent, sub-containers come first, then edges, then the icon vertices.
cells = list(root)
rank = {}
for el in cells:
    cid = el.get("id")
    if cid in ("0", "1"): r = 0
    elif el.get("edge") == "1" and not cid.startswith("legend"): r = 3
    elif cid.startswith(("box_", "ns_")) and not cid.endswith(("_icon", "_badge")): r = 1
    elif cid in N: r = 4
    else: r = 2
    rank[cid] = r
for el in cells: root.remove(el)
for el in sorted(cells, key=lambda el: rank[el.get("id")]): root.append(el)

ET.indent(mxfile, space="  ")
OUT.write_text(ET.tostring(mxfile, encoding="unicode"))
print("wrote", OUT, "clusters", len(CLUSTERS), "nodes", len(N), "edges", len(EDGES))
