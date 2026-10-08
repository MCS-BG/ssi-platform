#!/usr/bin/env python3
"""Day 6b icons for homelab_diagram.py --day 6b (run once after build_icons.py).

  * monitoring_laptop.png  generic laptop (Fluent Emoji laptop) with the Ubuntu logo on screen -> monitoring node
  * flannel.png            official flannel logo (Iconify logos/flannel)                        -> VXLAN endpoints
Generic network stencils (router, firewall) come straight from the mingrammer `diagrams` package.
"""
from build_icons import ICONS, SRC, fetch, svg_png, fit, paste_c, shadow

def main():
    lap = (SRC / "laptop.svg").read_text()
    grad = ('<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4b5563"/>'
            '<stop offset="1" stop-color="#1f2937"/></linearGradient></defs><g fill="none">')
    (SRC / "laptop_monitoring.svg").write_text(lap.replace('<g fill="none">', grad))
    im = svg_png(SRC / "laptop_monitoring.svg", 512, text_sub=[("#7167a4", "#1d1d1f"), ("#26c9fc", "url(#g)")])
    ubuntu = svg_png(SRC / "ubuntu.svg", 150)
    paste_c(im, fit(ubuntu, 130), 256, 172)
    shadow(im, 8, (0, 6), 60).save(ICONS / "monitoring_laptop.png")
    fl = fetch("https://api.iconify.design/logos/flannel.svg?height=512", SRC / "flannel.svg")
    svg_png(fl, 512).save(ICONS / "flannel.png")
    print("day 6b icons written")

if __name__ == "__main__":
    main()
