#!/usr/bin/env python3
"""Day 6 icons for homelab_diagram.py --day 6 (run once after build_icons.py).

  * mcp_logo.png       official Model Context Protocol mark (Iconify simple-icons/modelcontextprotocol)
  * mcp_deploy.png     MCP mark + official Kubernetes Deployment badge   -> mcp-server
  * mcptest_job.png    Python logo + official Kubernetes Job badge        -> mcp-test (MCP Python client)
  * fomock_deploy.png  Python logo + Deployment badge + "MOCK" tag        -> fo-mock (fake demo FO OData)
"""
from PIL import Image, ImageDraw, ImageFont
from build_icons import ICONS, SRC, RES, fetch, svg_png, logo_with_badge, badge, fit, paste_c, FONT_B

K8S = RES / "k8s"

def main():
    mcp_svg = fetch("https://api.iconify.design/simple-icons/modelcontextprotocol.svg?color=%23111111&height=512",
                    SRC / "modelcontextprotocol.svg")
    mcp = svg_png(mcp_svg, 512)
    mcp.save(ICONS / "mcp_logo.png")
    logo_with_badge(mcp, K8S / "compute/deploy.png", "mcp_deploy.png", 0.70)
    py = Image.open(RES / "programming/language/python.png").convert("RGBA")
    logo_with_badge(py, K8S / "compute/job.png", "mcptest_job.png", 0.70)
    # fo-mock: Python (stdlib http.server) + Deployment badge + a red MOCK tag, so it can't be mistaken for real D365
    c = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    paste_c(c, fit(py, int(512 * 0.66)), 512 * 0.44, 512 * 0.48)
    c = badge(c, K8S / "compute/deploy.png")
    d = ImageDraw.Draw(c)
    f = ImageFont.truetype(FONT_B, 92)
    tw = d.textlength("MOCK", font=f)
    x0, y0 = 14, 6
    d.rounded_rectangle([x0, y0, x0 + tw + 36, y0 + 118], radius=26, fill=(200, 40, 40, 255), outline=(255, 255, 255, 255), width=8)
    d.text((x0 + 18, y0 + 10), "MOCK", font=f, fill=(255, 255, 255, 255))
    c.save(ICONS / "fomock_deploy.png")
    print("day 6 icons written")

if __name__ == "__main__":
    main()
