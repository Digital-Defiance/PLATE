"""Author four complex SVG targets and supersample their matching PNG inputs.

Run with the render extra: python scripts/make_complex_scenes.py [outdir]
No fonts, random seeds, external assets, or PLATE pipeline output are used.
"""
from __future__ import annotations

import io
import math
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CREAM = "#f5edda"
NAVY = "#182e4c"
TEAL = "#267d83"
MINT = "#a9d1b5"
ORANGE = "#e88040"
GOLD = "#e9bc59"
RED = "#bb4b45"

# Purpose-built outlined lettering in a 44 x 60 em. Each letter is ONE editable
# compound path, including counters. Leaf transforms are retained by the oracle.
GLYPHS = {
    "O": "M12 0H30Q42 0 42 12V48Q42 60 30 60H12Q0 60 0 48V12Q0 0 12 0Z M14 11Q12 11 12 14V46Q12 49 15 49H27Q30 49 30 46V14Q30 11 27 11Z",
    "R": "M0 0H27Q42 0 42 17Q42 30 29 33L44 60H30L16 35H12V60H0Z M12 11V24H25Q30 24 30 17Q30 11 25 11Z",
    "B": "M0 0H27Q41 0 41 15Q41 25 34 29Q44 33 44 45Q44 60 28 60H0Z M12 11V24H24Q29 24 29 17Q29 11 24 11Z M12 35V49H25Q31 49 31 42Q31 35 25 35Z",
    "I": "M2 0H40V11H27V49H40V60H2V49H15V11H2Z",
    "T": "M0 0H44V12H28V60H16V12H0Z",
    "S": "M42 0V12H15Q12 12 12 17Q12 22 17 23L29 27Q43 31 43 44Q43 60 27 60H0V48H27Q31 48 31 43Q31 39 26 37L14 33Q0 29 0 16Q0 0 16 0Z",
    "U": "M0 0H12V44Q12 49 18 49H25Q31 49 31 44V0H43V45Q43 60 27 60H16Q0 60 0 45Z",
    "D": "M0 0H24Q44 0 44 20V40Q44 60 24 60H0Z M12 12V48H23Q32 48 32 39V21Q32 12 23 12Z",
    "Y": "M0 0H14L23 23L32 0H46L29 36V60H17V36Z",
    "E": "M0 0H42V12H12V24H35V36H12V48H42V60H0Z",
    "M": "M0 60V0H13L23 28L33 0H46V60H34V23L23 49L12 23V60Z",
    "F": "M0 0H42V12H12V26H35V38H12V60H0Z",
}


class Scene:
    def __init__(self, width, height):
        self.root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                               width=str(width), height=str(height),
                               viewBox=f"0 0 {width} {height}")
        self.width, self.height = width, height

    def add(self, tag, name, **attrs):
        return ET.SubElement(self.root, tag, id=name, **{
            k.replace("_", "-"): str(v) for k, v in attrs.items()})

    def rect(self, name, x, y, w, h, fill, **attrs):
        return self.add("rect", name, x=x, y=y, width=w, height=h, fill=fill, **attrs)

    def circle(self, name, x, y, r, fill, **attrs):
        return self.add("circle", name, cx=x, cy=y, r=r, fill=fill, **attrs)

    def path(self, name, d, fill, **attrs):
        return self.add("path", name, d=d, fill=fill, **attrs)

    def stroke(self, name, d, color, width=5):
        return self.path(name, d, "none", stroke=color, stroke_width=width,
                         stroke_linecap="round", stroke_linejoin="round")

    def word(self, text, x, y, size, color, prefix):
        scale = size / 60
        for i, letter in enumerate(text):
            self.path(f"{prefix}-{i + 1}-{letter}", GLYPHS[letter], color,
                      fill_rule="evenodd",
                      transform=f"translate({x + i * 54 * scale:g} {y:g}) scale({scale:g})")

    def gradient(self, name, kind, start, end, **coords):
        defs = self.root.find("defs")
        if defs is None:
            defs = ET.Element("defs")
            self.root.insert(0, defs)
        gradient = ET.SubElement(defs, kind, id=name, gradientUnits="userSpaceOnUse",
                                 **{k: str(v) for k, v in coords.items()})
        for offset, color in (("0", start), ("1", end)):
            ET.SubElement(gradient, "stop", offset=offset, **{"stop-color": color})
        return f"url(#{name})"

    def svg(self):
        ET.indent(self.root)
        return ET.tostring(self.root, encoding="unicode") + "\n"


def circle_subpath(x, y, r):
    return f"M{x-r:g} {y:g}a{r:g} {r:g} 0 1 0 {2*r:g} 0a{r:g} {r:g} 0 1 0 {-2*r:g} 0Z"


def star(x, y, r):
    points = []
    for i in range(8):
        a = i * math.pi / 4 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.24
        points.append(f"{x + rr * math.cos(a):.2f},{y + rr * math.sin(a):.2f}")
    return " ".join(points)


def mission_patch():
    s = Scene(960, 960)
    planet = s.gradient("planet-light", "radialGradient", "#ecd494", "#997698",
                        cx=430, cy=350, r=205)
    hull = s.gradient("hull-light", "linearGradient", CREAM, "#a9c6c8",
                      x1=535, y1=0, x2=635, y2=0)
    # Transparent bolt holes remain outside the inner sky, rather than being
    # simulated by painting cream circles on a solid background.
    rim = circle_subpath(480, 460, 420)
    for angle in (-145, -115, -85, -55, -25, 55, 85, 115, 155):
        a = math.radians(angle)
        rim += " " + circle_subpath(480 + 390 * math.cos(a), 460 + 390 * math.sin(a), 7)
    s.path("patch-rim-nine-cutouts", rim, NAVY, fill_rule="evenodd")
    s.circle("sky", 480, 460, 360, TEAL)
    for i, (x, y, r) in enumerate(((285, 220, 15), (380, 150, 10), (550, 160, 14),
                                  (700, 260, 12), (230, 430, 11), (730, 470, 15),
                                  (250, 725, 12), (650, 710, 10))):
        s.add("polygon", f"star-{i+1}", points=star(x, y, r), fill=CREAM)
    s.add("ellipse", "back-orbit", cx=465, cy=420, rx=280, ry=90, fill="none",
          stroke=MINT, stroke_width=8, transform="rotate(-24 465 420)")
    s.circle("shaded-planet", 460, 400, 182, planet)
    for i, (x, y, rx, ry) in enumerate(((385, 325, 27, 18), (405, 450, 35, 22), (515, 470, 19, 12))):
        s.add("ellipse", f"crater-{i+1}", cx=x, cy=y, rx=rx, ry=ry, fill="#b18c9e")
    s.circle("small-moon", 675, 340, 48, GOLD)
    s.add("ellipse", "front-orbit", cx=465, cy=420, rx=270, ry=73, fill="none",
          stroke=CREAM, stroke_width=5, transform="rotate(24 465 420)")
    s.rect("left-solar-array", 455, 325, 68, 115, NAVY)
    s.rect("right-solar-array", 647, 325, 68, 115, NAVY)
    for side, x in (("left", 467), ("right", 659)):
        for i in range(3):
            s.stroke(f"{side}-panel-cell-{i+1}", f"M{x} {350+i*30}h44", MINT, 4)
    s.stroke("left-array-strut", "M515 385H555", CREAM, 10)
    s.stroke("right-array-strut", "M615 385H655", CREAM, 10)
    s.path("exhaust", "M563 458Q550 500 585 551Q620 500 607 458Z", ORANGE)
    s.path("left-fin", "M553 390L520 465L560 448Z", ORANGE)
    s.path("right-fin", "M617 390L650 465L610 448Z", ORANGE)
    s.path("spacecraft-hull", "M585 240Q535 298 553 435L585 470L617 435Q635 298 585 240Z", hull)
    s.circle("porthole-rim", 585, 350, 29, NAVY)
    s.circle("porthole-glass", 585, 350, 18, TEAL)
    s.circle("porthole-highlight", 578, 343, 5, CREAM)
    s.add("polygon", "crossing-ribbon", points="125,565 835,565 810,685 150,685", fill=ORANGE)
    s.word("ORBIT", 315, 587, 76, CREAM, "outlined-title")
    s.circle("left-ribbon-rivet", 192, 625, 10, NAVY)
    s.circle("right-ribbon-rivet", 768, 625, 10, NAVY)
    for i, x in enumerate((430, 480, 530)):
        s.circle(f"rank-dot-{i+1}", x, 757, 9, GOLD)
    return s


def storefront():
    s = Scene(960, 800)
    s.rect("background", 0, 0, 960, 800, CREAM)
    s.circle("sun", 790, 125, 55, GOLD)
    s.rect("pavement", 0, 670, 960, 130, "#d4c5ac")
    s.rect("building", 170, 175, 620, 495, TEAL)
    s.add("polygon", "roof", points="145,175 480,60 815,175", fill=NAVY)
    for i, x in enumerate((220, 360, 500, 640)):
        s.rect(f"upper-window-frame-{i+1}", x, 205, 100, 92, CREAM)
        s.rect(f"upper-window-glass-{i+1}", x+10, 215, 80, 69, NAVY)
        s.rect(f"upper-window-sill-{i+1}", x-8, 297, 116, 10, ORANGE)
    for i, x in enumerate((205, 610)):
        s.rect(f"display-frame-{i+1}", x, 465, 145, 155, CREAM)
        s.rect(f"display-glass-{i+1}", x+10, 475, 125, 135, NAVY)
        s.circle(f"display-sun-{i+1}", x+70, 525, 28, GOLD)
        s.rect(f"display-plinth-{i+1}", x+35, 570, 70, 22, MINT)
    s.rect("door-frame", 405, 455, 150, 215, ORANGE)
    s.rect("door", 419, 469, 122, 201, NAVY)
    s.rect("door-glass", 431, 482, 98, 125, MINT)
    s.circle("door-handle", 525, 635, 6, GOLD)
    # Each alternating panel is one continuous stripe + scallop, so the target
    # does not demand an invisible division between touching same-colour parts.
    for i in range(14):
        x = 130+i*50
        s.path(f"awning-panel-{i+1}",
               f"M{x} 375h50v64q-2.5 27 -25 27q-22.5 0 -25 -27Z",
               RED if i%2==0 else CREAM)
    s.rect("shop-sign", 277, 317, 406, 82, NAVY, rx=10)
    s.word("STUDIO", 355, 334, 48, CREAM, "shop-letter")
    for i, x in enumerate((125, 835)):
        s.stroke(f"lamp-arm-{i+1}", f"M{x} 515V355q0 -30 {25 if i==0 else -25} -30", NAVY, 8)
        s.circle(f"lamp-{i+1}", x+(25 if i==0 else -25), 333, 20, GOLD)
    for i, x in enumerate((140, 820)):
        for j, (dx, angle) in enumerate(((-20, -25), (18, 25), (0, 0))):
            s.add("ellipse", f"plant-{i+1}-leaf-{j+1}", cx=x+dx, cy=610-j*15,
                  rx=17, ry=53, fill=MINT if j==1 else TEAL,
                  transform=f"rotate({angle} {x+dx} {610-j*15})")
        s.add("polygon", f"planter-{i+1}", points=f"{x-38},640 {x+38},640 {x+27},701 {x-27},701", fill=ORANGE)
    s.stroke("paving-joint-left", "M250 716L210 790", CREAM, 4)
    s.stroke("paving-joint-right", "M710 716L750 790", CREAM, 4)
    return s


def instrument_panel():
    s = Scene(960, 800)
    s.rect("background", 0, 0, 960, 800, CREAM)
    s.rect("chassis", 40, 50, 880, 700, NAVY, rx=36)
    s.rect("inset", 75, 200, 810, 405, "#24475c", rx=20)
    for i, (x, y) in enumerate(((78, 88), (882, 88), (78, 712), (882, 712))):
        s.circle(f"mount-rim-{i+1}", x, y, 13, MINT)
        s.stroke(f"mount-slot-{i+1}", f"M{x-6} {y}h12", NAVY, 3)
    s.word("SYSTEM", 120, 114, 48, CREAM, "panel-title")
    s.rect("title-rule", 465, 145, 350, 5, MINT)
    for i, x in enumerate((250, 480, 710)):
        s.circle(f"gauge-{i+1}-bezel", x, 365, 99, GOLD)
        s.circle(f"gauge-{i+1}-face", x, 365, 85, NAVY)
        for j in range(6):
            a = math.radians(145+j*50)
            x0, y0 = x+65*math.cos(a), 365+65*math.sin(a)
            x1, y1 = x+75*math.cos(a), 365+75*math.sin(a)
            s.stroke(f"gauge-{i+1}-tick-{j+1}", f"M{x0:.2f} {y0:.2f}L{x1:.2f} {y1:.2f}", CREAM, 5)
        a = math.radians((-135, -60, -20)[i])
        s.stroke(f"gauge-{i+1}-needle", f"M{x} 365L{x+54*math.cos(a):.2f} {365+54*math.sin(a):.2f}", ORANGE, 7)
        s.circle(f"gauge-{i+1}-hub", x, 365, 10, CREAM)
        s.rect(f"gauge-{i+1}-label", x-36, 490, 72, 8, MINT)
    s.stroke("left-signal-route", "M250 515v25q0 20 20 20h165q20 0 20 20v40", MINT, 7)
    s.stroke("right-signal-route", "M710 515v25q0 20 -20 20H525q-20 0 -20 20v40", GOLD, 7)
    for i, (x, color) in enumerate(((360, RED), (480, ORANGE), (600, MINT))):
        s.rect(f"status-housing-{i+1}", x-38, 625, 76, 50, "#24475c", rx=9)
        s.circle(f"status-light-{i+1}", x, 650, 13, color)
    return s


def event_poster():
    s = Scene(960, 960)
    wash = s.gradient("poster-wash", "linearGradient", "#edba68", "#d17d79",
                      x1=210, y1=0, x2=750, y2=0)
    s.rect("background", 0, 0, 960, 960, CREAM)
    s.circle("gradient-disc-behind-title", 480, 468, 260, wash)
    s.add("ellipse", "mint-ellipse", cx=650, cy=650, rx=190, ry=102, fill=MINT,
          transform="rotate(-26 650 650)")
    ring = circle_subpath(285, 620, 148) + " " + circle_subpath(285, 620, 88)
    s.path("open-ring", ring, NAVY, fill_rule="evenodd")
    for i in range(6):
        y = 440+i*24
        s.stroke(f"crossing-line-{i+1}", f"M510 {y}H865", NAVY, 5)
    s.circle("foreground-disc", 265, 680, 78, ORANGE)
    s.add("polygon", "diagonal-ribbon", points="90,490 800,344 828,418 110,564", fill=RED)
    s.add("polygon", "ribbon-cap", points="800,344 870,333 851,376 890,406 828,418", fill=NAVY)
    for row in range(3):
        for col in range(4):
            s.circle(f"dot-{row+1}-{col+1}", 705+col*43, 555+row*43, 8, TEAL)
    for i, (x, y) in enumerate(((105, 110), (845, 740), (90, 730))):
        s.add("polygon", f"spark-{i+1}", points=star(x, y, 22), fill=ORANGE)
    s.word("FORM", 94, 173, 180, NAVY, "headline")
    s.rect("top-rule", 95, 85, 585, 7, NAVY)
    s.rect("top-rule-short", 720, 85, 145, 7, ORANGE)
    s.rect("footer", 60, 810, 840, 100, NAVY)
    s.word("STUDIO", 85, 833, 51, CREAM, "footer-letter")
    for i in range(3):
        s.rect(f"footer-detail-{i+1}", 665, 839+i*17, 190-i*30, 5, MINT)
    return s


SCENES = {
    "complex_mission_patch": mission_patch,
    "complex_storefront": storefront,
    "complex_instrument_panel": instrument_panel,
    "complex_event_poster": event_poster,
}


def main(outdir=None):
    import cairosvg

    out = Path(outdir) if outdir else ROOT / "samples" / "challenges"
    out.mkdir(parents=True, exist_ok=True)
    for name, author in SCENES.items():
        scene = author()
        svg = scene.svg()
        (out / f"{name}.target.svg").write_text(svg)
        png = cairosvg.svg2png(bytestring=svg.encode(), scale=4)
        with Image.open(io.BytesIO(png)) as high:
            image = high.convert("RGBA").resize((scene.width, scene.height), Image.Resampling.LANCZOS)
            image.save(out / f"{name}.png")
        print(out / f"{name}.png")


if __name__ == "__main__":
    main(*sys.argv[1:2])
