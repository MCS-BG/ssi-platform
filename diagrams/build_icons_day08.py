#!/usr/bin/env python3
"""Day 8 icons for homelab_diagram.py --day 8 (run once after the earlier build_icons scripts).

Official marks, same fetch path as the other build_icons scripts (Iconify CDN):
  * Tailscale   simple-icons/tailscale   -> operator (Deployment badge) and the ingress proxies
  * GitHub      simple-icons/github      -> GitHub Actions / GHCR image pull
  * phone       fluent-emoji-flat/mobile-phone

If a fetch fails, a drawn shield or handset is written instead so the diagram still renders.
"""
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw

from build_icons import ICONS, SRC, RES, svg_png, logo_with_badge

UA = {"User-Agent": "Mozilla/5.0 (ssi-platform diagram builder)"}
K8S = RES / "k8s"


def fetch(url, dest: Path):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        dest.write_bytes(r.read())
    return dest


def shield(dest: Path, label=""):
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(256, 36), (430, 120), (404, 300), (256, 470), (108, 300), (82, 120)], fill=(17, 24, 39, 255))
    d.polygon([(256, 78), (390, 146), (370, 286), (256, 424), (142, 286), (122, 146)], fill=(255, 255, 255, 255))
    if label:
        d.text((256, 250), label, fill=(17, 24, 39, 255), anchor="mm")
    im.save(dest)
    return im


def phone_fallback(dest: Path):
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([156, 28, 356, 484], radius=48, fill=(17, 24, 39, 255))
    d.rounded_rectangle([176, 64, 336, 420], radius=12, fill=(255, 255, 255, 255))
    d.ellipse([236, 436, 276, 468], outline=(255, 255, 255, 255), width=6)
    im.save(dest)
    return im


def load_svg(url, name, fallback):
    dest = SRC / f"{name}.svg"
    try:
        fetch(url, dest)
        return svg_png(dest, 512)
    except Exception as exc:
        print(f"fetch failed for {name}: {exc}; using a drawn mark")
        png = ICONS / f"{name}_fallback.png"
        fallback(png)
        return Image.open(png).convert("RGBA")


def main():
    SRC.mkdir(parents=True, exist_ok=True)
    ts = load_svg(
        "https://api.iconify.design/simple-icons/tailscale.svg?color=%23111827&height=512",
        "tailscale", shield)
    gh = load_svg(
        "https://api.iconify.design/simple-icons/github.svg?color=%23111827&height=512",
        "github", lambda p: shield(p))
    phone = load_svg(
        "https://api.iconify.design/fluent-emoji-flat/mobile-phone.svg?height=512",
        "phone", phone_fallback)
    ts.save(ICONS / "tailscale.png")
    gh.save(ICONS / "github.png")
    phone.save(ICONS / "phone.png")
    logo_with_badge(ts, K8S / "compute/deploy.png", "tailscale_deploy.png", 0.70)
    print("day 8 icons written")


if __name__ == "__main__":
    main()
