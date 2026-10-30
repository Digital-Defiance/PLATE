"""Author PLATE's registration-P identity and its independent tracing challenge.

Run: DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python scripts/make_plate_brand.py
An optional output root keeps regeneration separate from the checkout. No fonts,
external assets, or traced geometry are used in the actual logo files.
"""
from __future__ import annotations

import copy
import io
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
INK, TEAL, VERMILION, PAPER = "#16343b", "#45a995", "#f0784a", "#f5f2ea"
NS = "http://www.w3.org/2000/svg"
INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"
ET.register_namespace("", NS)
ET.register_namespace("inkscape", INKSCAPE)

# Original lettering, on a 100-unit cap height. Counters belong to their letters.
LETTERS = {
    "P": "M0 100V0H44C69 0 84 15 84 38S69 76 44 76H24V100Z M24 22V54H42C54 54 60 48 60 38S54 22 42 22Z",
    "L": "M102 0H126V78H174V100H102Z",
    "A": "M186 100L221 0H247L282 100H257L251 81H217L211 100Z M224 60H244L234 28Z",
    "T": "M281 0H369V22H337V100H313V22H281Z",
    "E": "M387 0H461V22H411V39H455V60H411V78H461V100H387Z",
}


def add(parent, tag, **attrs):
    return ET.SubElement(parent, f"{{{NS}}}{tag}", {
        k.replace("_", "-"): str(v) for k, v in attrs.items()})


def layer(parent, name):
    group = add(parent, "g", id=name, data_name=name.replace("-", " ").title())
    group.set(f"{{{INKSCAPE}}}groupmode", "layer")
    group.set(f"{{{INKSCAPE}}}label", name.replace("-", " ").title())
    return group


def logo(*, foreground=INK, mark=False, mono=False):
    root = ET.Element(f"{{{NS}}}svg", width="312" if mark else "1200",
                      height="312" if mark else "400",
                      viewBox="40 36 312 312" if mark else "0 0 1200 400",
                      role="img", **{"aria-labelledby": "logo-title logo-description"})
    add(root, "title", id="logo-title").text = "PLATE — registration P"
    description = ("A solid P with a transparent counter. " if mono else
                   "Three offset printing plates form a P with a shared transparent counter. ")
    description += "A registration cross marks the upper right."
    if not mark:
        description += " Custom outlined letters spell PLATE."
    add(root, "desc", id="logo-description").text = description
    # Every plate has a real circular hole. Their holes share registration, while
    # their outer P silhouettes are offset. No background-colour paint or masks.
    for name, x, y, color in (("back-plate", 64, 92, TEAL),
                               ("middle-plate", 80, 76, VERMILION),
                               ("front-plate", 96, 60, foreground)):
        if mono and name != "front-plate":
            continue
        d = (f"M{x} {y+240}V{y}H{x+110}"
             f"C{x+169} {y} {x+206} {y+37} {x+206} {y+88}"
             f"S{x+169} {y+176} {x+110} {y+176}H{x+56}V{y+240}Z "
             "M166 148a40 40 0 1 0 80 0a40 40 0 1 0 -80 0Z")
        add(layer(root, name), "path", id=f"{name}-P", d=d,
            fill=color, fill_rule="evenodd")
    registration = layer(root, "registration")
    color = foreground if mono else VERMILION
    add(registration, "circle", id="registration-ring", cx=313, cy=69, r=13,
        fill="none", stroke=color, stroke_width=3)
    for name, d in (("horizontal", "M293 69H333"), ("vertical", "M313 49V89")):
        add(registration, "path", id=f"registration-{name}", d=d,
            fill="none", stroke=color, stroke_width=3, stroke_linecap="round")
    if not mark:
        wordmark = layer(root, "wordmark")
        for letter, d in LETTERS.items():
            add(wordmark, "path", id=f"letter-{letter}", d=d, fill=foreground,
                fill_rule="evenodd", transform="translate(400 133) scale(1.55)")
    return root


def serialize(root):
    ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n"


def raster(svg, size):
    import cairosvg

    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as high:
        return high.convert("RGBA").resize(size, Image.Resampling.LANCZOS)


def preview():
    """Presentation only: text here is not part of the logo or tracing oracle."""
    root = ET.Element(f"{{{NS}}}svg", width="1200", height="820", viewBox="0 0 1200 820")
    add(root, "rect", width=1200, height=440, fill=PAPER)
    add(root, "rect", y=440, width=790, height=380, fill=INK)
    add(root, "rect", x=790, y=440, width=410, height=380, fill="#e8e4da")
    label = add(root, "text", x=64, y=49, fill=INK, font_family="sans-serif", font_size=13,
                letter_spacing=2)
    label.text = "PLATE / REGISTRATION P"
    primary = copy.deepcopy(logo())
    primary.set("y", "26")
    root.append(primary)
    reverse = copy.deepcopy(logo(foreground=PAPER))
    reverse.set("x", "20")
    reverse.set("y", "495")
    reverse.set("width", "750")
    reverse.set("height", "250")
    root.append(reverse)
    stamp = copy.deepcopy(logo(mono=True, mark=True))
    stamp.set("x", "902")
    stamp.set("y", "496")
    stamp.set("width", "176")
    stamp.set("height", "176")
    root.append(stamp)
    for x, y, text, color in ((64, 410, "THREE PLATES. ONE TRANSPARENT COUNTER.", INK),
                              (64, 787, "REVERSED", PAPER),
                              (846, 787, "ONE-COLOR MARK", INK)):
        add(root, "text", x=x, y=y, fill=color, font_family="sans-serif",
            font_size=11, letter_spacing=2).text = text
    return serialize(root)


def main(output_root=ROOT):
    root = Path(output_root)
    brand, challenges = root / "assets/brand", root / "samples/challenges"
    brand.mkdir(parents=True, exist_ok=True)
    challenges.mkdir(parents=True, exist_ok=True)
    for name, artwork in (("plate-logo", logo()), ("plate-mark", logo(mark=True)),
                           ("plate-logo-reversed", logo(foreground=PAPER)),
                           ("plate-logo-mono", logo(mono=True)),
                           ("plate-mark-mono", logo(mono=True, mark=True))):
        svg = serialize(artwork)
        (brand / f"{name}.svg").write_text(svg, encoding="utf-8")
        size = int(artwork.get("width")), int(artwork.get("height"))
        image = raster(svg, size)
        image.save(brand / f"{name}.png")
        if name == "plate-logo":
            (challenges / "logo_plate.target.svg").write_text(svg, encoding="utf-8")
            image.save(challenges / "logo_plate.png")
    proof = preview()
    raster(proof, (1200, 820)).save(brand / "plate-preview.png")
    print(brand / "plate-preview.png")


if __name__ == "__main__":
    main(*sys.argv[1:2])
