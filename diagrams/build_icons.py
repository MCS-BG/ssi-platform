#!/usr/bin/env python3
"""Fetch official logos and compose device/workload icons for homelab_diagram.py.

Sources (downloaded into icons/src):
  * Ollama, Nomic AI         -> official GitHub org avatars / Ollama logo (via selfh.st icon set)
  * Open WebUI               -> official favicon from github.com/open-webui/open-webui
  * NVIDIA, Meta, Kubernetes,
    Ubuntu                   -> brand logos via Iconify (logos / simple-icons / selfh.st sets)
  * k8s kind badges, k3s, containerd, Python, PostgreSQL, Helm -> bundled with the `diagrams` package
Device icons (terminal laptop, lab host laptop, external USB drive, NVMe SSD, GPU chip, SSH terminal)
are generic illustrations: no device vendor or model branding.
"""
import io, os, re, subprocess, urllib.request
from pathlib import Path
import diagrams
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"; SRC = ICONS / "src"
RES = Path(diagrams.__file__).resolve().parent.parent / "resources"
SRC.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (ssi-platform diagram builder)"}
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_M = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

ICONIFY = {
    "nvidia_mark": "selfhst/nvidia.svg",
    "nvidia_wordmark": "logos/nvidia.svg",
    "meta": "logos/meta-icon.svg",
    "kubernetes": "logos/kubernetes.svg",
    "ubuntu": "logos/ubuntu.svg",
    "ollama": "selfhst/ollama.svg",
    "laptop": "fluent-emoji-flat/laptop.svg",
    "key": "fluent-emoji-flat/key.svg",
    "globe": "fluent-emoji-flat/globe-with-meridians.svg",
}
RAW = {
    "open-webui_favicon.png": "https://raw.githubusercontent.com/open-webui/open-webui/main/static/favicon.png",
    "nomic_github.png": "https://github.com/nomic-ai.png?size=460",
    "ollama_github.png": "https://github.com/ollama.png?size=460",
}

def fetch(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        dest.write_bytes(r.read())
    return dest

def svg_png(svg: Path, size: int, out: Path = None, text_sub=None) -> Image.Image:
    data = svg.read_text()
    if text_sub:
        for a, b in text_sub: data = data.replace(a, b)
    p = subprocess.run(["rsvg-convert", "-w", str(size), "-a", "-f", "png"], input=data.encode(),
                       capture_output=True, check=True)
    im = Image.open(io.BytesIO(p.stdout)).convert("RGBA")
    if out: im.save(out)
    return im

def fit(im, box):
    im = im.copy(); im.thumbnail((box, box), Image.LANCZOS); return im

def paste_c(canvas, im, cx, cy):
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

def shadow(canvas, radius=10, offset=(0, 8), alpha=70):
    a = canvas.split()[-1]
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: v * alpha // 255))
    sh = sh.filter(ImageFilter.GaussianBlur(radius))
    base = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    base.alpha_composite(sh, offset); base.alpha_composite(canvas)
    return base

def badge(base: Image.Image, badge_png: Path, size=0.46, pad=0.0):
    W = base.width
    b = fit(Image.open(badge_png).convert("RGBA"), int(W * size))
    # white halo so the badge separates from the logo
    halo = Image.new("RGBA", b.size, (0, 0, 0, 0)); halo.putalpha(b.split()[-1])
    halo = Image.merge("RGBA", (*[Image.new("L", b.size, 255)] * 3, b.split()[-1].filter(ImageFilter.MaxFilter(9))))
    out = base.copy()
    x, y = int(W - b.width - pad * W), int(W - b.height - pad * W)
    out.alpha_composite(halo, (x, y)); out.alpha_composite(b, (x, y))
    return out

def logo_with_badge(logo: Image.Image, badge_png: Path, name: str, logo_box=0.78):
    c = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    paste_c(c, fit(logo, int(512 * logo_box)), 512 * 0.44, 512 * 0.44)
    c = badge(c, badge_png)
    c.save(ICONS / name); return c

def main():
    src = {}
    for k, q in ICONIFY.items():
        sep = "&" if "?" in q else "?"
        src[k] = fetch(f"https://api.iconify.design/{q}{sep}height=512", SRC / f"{k}.svg")
    for fn, url in RAW.items():
        src[fn] = fetch(url, SRC / fn)
    K8S = RES / "k8s"

    # ---- laptops: fluent laptop illustration, black bezel, generic screen (no vendor logo)
    def laptop(screen_fill, logo_key, name, extra_badge=None, logo_w=150):
        im = svg_png(src["laptop"], 512, text_sub=[("#7167a4", "#1d1d1f"), ("#26c9fc", screen_fill)])
        if logo_key:
            logo = svg_png(src[logo_key], logo_w)
            paste_c(im, fit(logo, logo_w), 256, 172)
        else:  # terminal prompt glyph
            ImageDraw.Draw(im).text((256, 172), ">_", font=ImageFont.truetype(FONT_M, 110), fill="#ffffff", anchor="mm")
        if extra_badge:
            b = fit(svg_png(src[extra_badge], 150), 150)
            im.alpha_composite(b, (512 - 150 - 4, 512 - 150 - 36))
        shadow(im, 8, (0, 6), 60).save(ICONS / name)
    # gradient screens via small svg edit
    lap = src["laptop"].read_text()
    def lap_grad(c1, c2):
        return lap.replace("<g fill=\"none\">", f"<defs><linearGradient id=\"g\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\"><stop offset=\"0\" stop-color=\"{c1}\"/><stop offset=\"1\" stop-color=\"{c2}\"/></linearGradient></defs><g fill=\"none\">")
    (SRC / "laptop_terminal.svg").write_text(lap_grad("#3a6ea5", "#1b2a4a"))
    (SRC / "laptop_labhost.svg").write_text(lap_grad("#e95420", "#5e2750"))
    src["laptop"] = SRC / "laptop_terminal.svg"; laptop("url(#g)", None, "terminal_laptop.png")
    src["laptop"] = SRC / "laptop_labhost.svg"; laptop("url(#g)", "ubuntu", "labhost_laptop.png", logo_w=150)

    # ---- external USB drive (generic black slab, no vendor branding)
    c = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    # USB cable
    d.line([(256, 20), (256, 70)], fill="#3a3a3a", width=16)
    d.rounded_rectangle([236, 60, 276, 96], 6, fill="#5a5a5a")
    d.rounded_rectangle([96, 90, 416, 496], 34, fill="#1a1a1a")
    d.rounded_rectangle([104, 98, 408, 488], 28, fill="#262626")
    d.rounded_rectangle([104, 98, 408, 180], 28, fill="#303030")
    d.text((256, 290), "USB", font=ImageFont.truetype(FONT_B, 72), fill="#ffffff", anchor="mm")
    d.text((256, 380), "data disk", font=ImageFont.truetype(FONT_B, 34), fill="#bdbdbd", anchor="mm")
    d.ellipse([370, 450, 384, 464], fill="#4fc3f7")  # activity LED
    shadow(c, 10, (0, 8), 80).save(ICONS / "usb_drive.png")

    # ---- NVMe M.2 SSD (internal) drawn at an angle
    s = Image.new("RGBA", (560, 170), (0, 0, 0, 0)); d = ImageDraw.Draw(s)
    d.rounded_rectangle([40, 10, 548, 160], 10, fill="#14301f")
    d.pieslice([520, 70, 560, 100], 90, 270, fill=(0, 0, 0, 0))
    d.ellipse([524, 71, 552, 99], fill=(0, 0, 0, 0))
    d.rounded_rectangle([2, 10, 60, 160], 6, fill="#14301f")
    for i in range(0, 13):  # gold edge contacts
        y0 = 18 + i * 11
        if i in (4,): continue  # key notch
        d.rectangle([2, y0, 44, y0 + 7], fill="#e0b020")
    d.rectangle([0, 18 + 4 * 11 - 2, 30, 18 + 4 * 11 + 9], fill=(0, 0, 0, 0))
    d.rounded_rectangle([70, 32, 170, 138], 6, fill="#1e1e1e")  # controller
    d.rounded_rectangle([200, 26, 330, 144], 6, fill="#262626")
    d.rounded_rectangle([350, 26, 480, 144], 6, fill="#262626")
    d.text((265, 85), "NVMe", font=ImageFont.truetype(FONT_B, 34), fill="#e0e0e0", anchor="mm")
    d.text((415, 85), "SSD", font=ImageFont.truetype(FONT_B, 34), fill="#e0e0e0", anchor="mm")
    s = s.rotate(20, expand=True, resample=Image.BICUBIC)
    c = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); paste_c(c, fit(s, 500), 256, 256)
    shadow(c, 8, (0, 8), 70).save(ICONS / "nvme_ssd.png")

    # ---- GPU chip (mobile GPU = soldered die, not a card)
    c = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    for i in range(9):
        p = 104 + i * 38
        d.rounded_rectangle([p, 36, p + 18, 90], 4, fill="#c9a227"); d.rounded_rectangle([p, 422, p + 18, 476], 4, fill="#c9a227")
        d.rounded_rectangle([36, p, 90, p + 18], 4, fill="#c9a227"); d.rounded_rectangle([422, p, 476, p + 18], 4, fill="#c9a227")
    d.rounded_rectangle([76, 76, 436, 436], 26, fill="#1b1b1b")
    d.rounded_rectangle([96, 96, 416, 416], 18, outline="#76b900", width=6, fill="#232323")
    mark = fit(svg_png(src["nvidia_mark"], 200), 190); paste_c(c, mark, 256, 222)
    d.text((256, 368), "GPU", font=ImageFont.truetype(FONT_B, 54), fill="#ffffff", anchor="mm")
    shadow(c, 8, (0, 6), 70).save(ICONS / "gpu_chip.png")

    # ---- SSH tunnel: terminal window + key
    c = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    d.rounded_rectangle([40, 70, 472, 420], 30, fill="#1e1e2e")
    d.rounded_rectangle([40, 70, 472, 130], 30, fill="#3b3b4f"); d.rectangle([40, 110, 472, 130], fill="#3b3b4f")
    for i, col in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        d.ellipse([72 + i * 42, 88, 96 + i * 42, 112], fill=col)
    mono = ImageFont.truetype(FONT_M, 64)
    d.text((80, 190), ">_ ssh", font=mono, fill="#50fa7b")
    d.text((80, 280), "-L 6443", font=ImageFont.truetype(FONT_M, 46), fill="#8be9fd")
    key = fit(svg_png(src["key"], 220), 210); c.alpha_composite(key, (290, 290))
    shadow(c, 8, (0, 6), 70).save(ICONS / "ssh_tunnel.png")

    # ---- private network: generic padlock (no VPN vendor branding)
    c = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    d.arc([146, 40, 366, 300], 180, 360, fill="#475569", width=44)
    d.line([(168, 170), (168, 240)], fill="#475569", width=44); d.line([(344, 170), (344, 240)], fill="#475569", width=44)
    d.rounded_rectangle([96, 220, 416, 480], 36, fill="#1e3a8a")
    d.ellipse([226, 300, 286, 360], fill="#ffffff"); d.rectangle([246, 340, 266, 410], fill="#ffffff")
    shadow(c, 8, (0, 6), 70).save(ICONS / "private_network.png")

    # ---- workloads: real app logos + official k8s kind badge
    logo_with_badge(svg_png(src["ollama"], 400), K8S / "compute/deploy.png", "ollama_deploy.png", 0.74)
    owui = Image.open(src["open-webui_favicon.png"]).convert("RGBA")
    # favicon is a white rounded square; give it a subtle border so it reads on white
    ow = owui.copy(); ImageDraw.Draw(ow).rounded_rectangle([40, 40, owui.width - 41, owui.height - 41], 100, outline="#c8c8c8", width=6)
    logo_with_badge(ow, K8S / "compute/deploy.png", "openwebui_deploy.png", 0.76)
    logo_with_badge(Image.open(RES / "onprem/database/postgresql.png").convert("RGBA"), K8S / "compute/sts.png", "pgvector_sts.png", 0.80)
    logo_with_badge(Image.open(RES / "programming/language/python.png").convert("RGBA"), K8S / "compute/deploy.png", "ragworker_deploy.png", 0.74)
    logo_with_badge(svg_png(src["nvidia_mark"], 400), K8S / "compute/ds.png", "nvidia_device_plugin_ds.png", 0.74)
    tk = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    paste_c(tk, fit(svg_png(src["nvidia_wordmark"], 500), 480), 256, 200)
    dd = ImageDraw.Draw(tk); dd.rounded_rectangle([40, 320, 472, 440], 24, fill="#76b900")
    dd.text((256, 380), "Container Toolkit", font=ImageFont.truetype(FONT_B, 44), fill="#ffffff", anchor="mm")
    tk.save(ICONS / "nvidia_container_toolkit.png")

    # ---- simple logo icons
    svg_png(src["meta"], 512, ICONS / "meta_llama.png")
    nom = Image.open(src["nomic_github.png"]).convert("RGBA")
    m = Image.new("L", nom.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, nom.width - 1, nom.height - 1], 90, fill=255)
    nb = Image.new("RGBA", nom.size, (0, 0, 0, 0)); nb.paste(nom, (0, 0), m)
    ImageDraw.Draw(nb).rounded_rectangle([2, 2, nom.width - 3, nom.height - 3], 90, outline="#d0d0d0", width=5)
    nb.save(ICONS / "nomic.png")
    svg_png(src["kubernetes"], 512, ICONS / "kubectl.png")
    svg_png(src["globe"], 512, ICONS / "browser.png")
    svg_png(src["ubuntu"], 512, ICONS / "ubuntu.png")
    print("icons written to", ICONS)

if __name__ == "__main__":
    main()
