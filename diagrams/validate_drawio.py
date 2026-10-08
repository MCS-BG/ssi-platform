#!/usr/bin/env python3
"""Validate homelab-architecture.drawio: well-formed, edge endpoints exist, image data URIs decode."""
import base64, binascii, io, re, sys
import xml.etree.ElementTree as ET
from PIL import Image

path = sys.argv[1] if len(sys.argv) > 1 else "history/homelab-architecture.drawio"
tree = ET.parse(path)                       # raises on malformed XML
cells = tree.getroot().findall(".//mxCell")
ids = [c.get("id") for c in cells]
assert len(ids) == len(set(ids)), "duplicate ids"
idset = set(ids)
errors = []
for c in cells:
    p = c.get("parent")
    if p is not None and p not in idset: errors.append(f"{c.get('id')}: missing parent {p}")
edges = [c for c in cells if c.get("edge") == "1"]
connected = [e for e in edges if not e.get("id").startswith("legend_")]
for e in connected:
    for k in ("source", "target"):
        if e.get(k) is None: errors.append(f"{e.get('id')}: no {k}")
        elif e.get(k) not in idset: errors.append(f"{e.get('id')}: {k} {e.get(k)} does not exist")
    if "orthogonalEdgeStyle" not in e.get("style", ""): errors.append(f"{e.get('id')}: not orthogonal")
imgs = 0
for c in cells:
    m = re.search(r"image=data:image/png,([^;]+)", c.get("style", ""))
    if "image=" in c.get("style", "") and not m: errors.append(f"{c.get('id')}: image not a data:image/png, URI")
    if m:
        try:
            raw = base64.b64decode(m.group(1), validate=True)
            Image.open(io.BytesIO(raw)).verify()
            imgs += 1
        except (binascii.Error, Exception) as ex:
            errors.append(f"{c.get('id')}: image does not decode ({ex})")
containers = [c for c in cells if "container=1" in (c.get("style") or "")]
print(f"cells={len(cells)} vertices={sum(c.get('vertex')=='1' for c in cells)} edges={len(edges)} "
      f"(connected={len(connected)}, legend={len(edges)-len(connected)}) containers={len(containers)} images_ok={imgs}")
print("\n".join(errors) if errors else "OK: well-formed, all edge source/target ids exist, all image data URIs decode")
sys.exit(1 if errors else 0)
