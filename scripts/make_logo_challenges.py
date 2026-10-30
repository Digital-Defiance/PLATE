"""Author original complex logos and their supersampled PNG inputs.

Run: python scripts/make_logo_challenges.py [outdir]
Targets are authored geometry, never PLATE output. No fonts or external assets.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

from make_complex_scenes import Scene, circle_subpath, star, NAVY, CREAM, TEAL, MINT, GOLD, ORANGE

ROOT = Path(__file__).resolve().parents[1]


def ember_crest():
    s = Scene(800, 960)
    shield = "M100 110L400 40L700 110L670 540Q650 650 400 760Q150 650 130 540Z"
    for x, y in ((400, 59), (122, 150), (678, 150), (400, 739)):
        shield += " " + circle_subpath(x, y, 7)
    s.path("shield-four-transparent-cutouts", shield, NAVY, fill_rule="evenodd")
    s.path("shield-field", "M137 137L400 80L663 137L635 525Q615 620 400 714Q185 620 165 525Z", CREAM)
    # Laurel leaves are separate editable silhouettes, including their hidden bases.
    for side, sign in (("left", -1), ("right", 1)):
        s.stroke(f"{side}-laurel-stem", f"M400 650Q{400+sign*150} 630 {400+sign*190} 470", GOLD, 6)
        for i in range(6):
            x, y = 400 + sign*(80+i*21), 645-i*28
            s.add("ellipse", f"{side}-laurel-leaf-{i+1}", cx=x, cy=y, rx=13, ry=28,
                  fill=TEAL if i % 2 else MINT, transform=f"rotate({sign*(38+i*3)} {x} {y})")
    for i, (x, y, r) in enumerate(((320, 166, 14), (400, 125, 18), (480, 166, 14)), 1):
        s.add("polygon", f"crest-star-{i}", points=star(x, y, r), fill=GOLD)
    s.path("fox-full-silhouette", "M222 210L306 250L400 180L494 250L578 210L553 410L520 480L400 571L280 480L247 410Z", ORANGE)
    s.add("polygon", "left-ear", points="237,230 296,267 258,323", fill=NAVY)
    s.add("polygon", "right-ear", points="563,230 504,267 542,323", fill=NAVY)
    s.add("polygon", "forehead-facet", points="400,201 464,268 400,390 336,268", fill=GOLD)
    s.path("left-cheek", "M252 334L336 379L400 493L344 510L282 465Z", CREAM)
    s.path("right-cheek", "M548 334L464 379L400 493L456 510L518 465Z", CREAM)
    s.add("polygon", "left-eye-mask", points="269,326 357,366 375,404 296,389", fill=NAVY)
    s.add("polygon", "right-eye-mask", points="531,326 443,366 425,404 504,389", fill=NAVY)
    s.path("left-eye", "M290 354L343 374Q318 388 290 354Z", CREAM)
    s.path("right-eye", "M510 354L457 374Q482 388 510 354Z", CREAM)
    s.circle("left-pupil", 323, 373, 5, NAVY)
    s.circle("right-pupil", 477, 373, 5, NAVY)
    s.path("muzzle", "M362 423Q400 408 438 423L459 475L400 527L341 475Z", CREAM)
    s.add("polygon", "nose", points="376,447 424,447 400,473", fill=NAVY)
    s.stroke("mouth", "M400 470V490Q382 505 368 488M400 490Q418 505 432 488", NAVY, 6)
    for side, sign in (("left", -1), ("right", 1)):
        for i in range(2):
            s.stroke(f"{side}-whisker-{i+1}",
                     f"M{400+sign*48} {455+i*17}Q{400+sign*89} {452+i*22} {400+sign*112} {438+i*33}", NAVY, 4)
    s.add("polygon", "left-ribbon-tail", points="70,759 151,776 151,860 55,878 79,819", fill=ORANGE)
    s.add("polygon", "right-ribbon-tail", points="730,759 649,776 649,860 745,878 721,819", fill=ORANGE)
    s.add("polygon", "left-ribbon-fold", points="115,855 151,831 151,879", fill=GOLD)
    s.add("polygon", "right-ribbon-fold", points="685,855 649,831 649,879", fill=GOLD)
    s.rect("name-ribbon", 115, 750, 570, 115, NAVY, rx=8)
    s.word("EMBER", 208, 764, 90, CREAM, "outlined-name")
    for i, x in enumerate((365, 400, 435), 1):
        s.circle(f"rank-dot-{i}", x, 904, 5, GOLD)
    return s


def orbit_wordmark():
    s = Scene(1200, 480)
    ramp = s.gradient("orbital-light", "radialGradient", "#f0cc8a", "#bb6c8f", cx=185, cy=195, r=180)
    ring = circle_subpath(215, 240, 160) + " " + circle_subpath(215, 240, 148)
    for x, y in ((215, 84), (371, 240), (215, 396), (59, 240)):
        ring += " " + circle_subpath(x, y, 4)
    s.path("badge-ring-four-cutouts", ring, NAVY, fill_rule="evenodd")
    s.add("ellipse", "back-orbit", cx=215, cy=240, rx=196, ry=66,
          fill="none", stroke=MINT, stroke_width=8, transform="rotate(-25 215 240)")
    s.circle("gradient-core", 215, 240, 117, ramp)
    s.path("monogram-O", circle_subpath(215, 240, 74)+" "+circle_subpath(215, 240, 53),
           NAVY, fill_rule="evenodd")
    s.stroke("upper-light-arc", "M164 196Q189 166 226 176", CREAM, 8)
    s.stroke("lower-light-arc", "M247 280Q225 306 192 293", CREAM, 8)
    s.add("ellipse", "front-orbit", cx=215, cy=240, rx=190, ry=62,
          fill="none", stroke=GOLD, stroke_width=6, transform="rotate(25 215 240)")
    for name, x, y in (("near", 366, 310), ("far", 64, 170)):
        s.circle(f"{name}-satellite", x, y, 13, NAVY)
        s.circle(f"{name}-satellite-core", x, y, 7, MINT)
    s.add("polygon", "core-spark", points=star(293, 162, 19), fill=CREAM)
    s.word("ORBIT", 450, 110, 150, NAVY, "wordmark")
    s.word("STUDIO", 455, 300, 40, TEAL, "descriptor")
    for i in range(3):
        s.stroke(f"motion-line-{i+1}", f"M755 {307+i*24}H1000Q1070 {307+i*24} 1115 {282+i*24}",
                 (MINT, GOLD, NAVY)[i], (4, 7, 10)[i])
    for i in range(5):
        s.circle(f"descriptor-dot-{i+1}", 460+i*25, 380, 4, GOLD)
    for i in range(3):
        x = 1010+i*32
        s.add("polygon", f"motion-chevron-{i+1}", points=f"{x},390 {x+16},374 {x+26},374 {x+10},390", fill=TEAL)
    return s


def root_seal():
    s = Scene(900, 900)
    s.add("circle", "outer-seal-stroke", cx=450, cy=370, r=300, fill="none", stroke=TEAL, stroke_width=18)
    s.add("circle", "inner-seal-stroke", cx=450, cy=370, r=275, fill="none", stroke=MINT, stroke_width=5)
    roots = ("M450 552Q405 584 299 621", "M450 552Q495 584 601 621",
             "M427 564Q405 610 365 640", "M473 564Q495 610 535 640",
             "M450 562V647", "M414 582Q355 577 276 590")
    for i, d in enumerate(roots, 1):
        s.stroke(f"root-{i}", d, NAVY, 10 if i < 3 else 6)
    branches = ("M425 418Q350 352 300 290", "M475 418Q550 352 600 290",
                "M450 350V180", "M435 320Q385 260 340 220",
                "M465 320Q515 260 560 220", "M426 463Q340 420 275 370",
                "M474 463Q560 420 625 370")
    for i, d in enumerate(branches, 1):
        s.stroke(f"branch-{i}", d, NAVY, 8)
    trunk = ("M407 575Q437 500 420 430L395 391Q432 402 440 430L437 305"
             "Q450 280 463 305L460 430Q468 402 505 391L480 430Q463 500 493 575Z"
             " M443 453Q450 423 457 453L450 482Z")
    s.path("trunk-with-transparent-counter", trunk, NAVY, fill_rule="evenodd")
    leaves = ((300, 290, -50), (340, 220, -35), (395, 190, -15), (450, 180, 0),
              (505, 190, 15), (560, 220, 35), (600, 290, 50), (275, 370, -75),
              (330, 360, -45), (390, 340, -20), (510, 340, 20), (570, 360, 45),
              (625, 370, 75), (330, 460, -60), (570, 460, 60))
    for i, (x, y, angle) in enumerate(leaves, 1):
        transform = f"translate({x} {y}) rotate({angle})"
        s.path(f"leaf-{i}", "M0 0C-50 -5 -65 -70 -12 -100C50 -85 60 -20 0 0Z",
               TEAL if i % 3 else MINT, transform=transform)
        s.path(f"leaf-vein-{i}", "M-1 -13Q-16 -43 -12 -81", "none", stroke=CREAM,
               stroke_width=3, stroke_linecap="round", stroke_linejoin="round", transform=transform)
    for i, (x, y) in enumerate(((350, 315), (550, 315), (405, 250), (495, 250)), 1):
        s.circle(f"berry-{i}", x, y, 8, GOLD)
    s.word("ROOT", 270, 734, 104, NAVY, "outlined-name")
    s.stroke("left-name-rule", "M95 785H225", MINT, 6)
    s.stroke("right-name-rule", "M675 785H805", MINT, 6)
    return s


LOGOS = {"logo_ember_crest": ember_crest, "logo_orbit_wordmark": orbit_wordmark,
         "logo_root_seal": root_seal}


def main(outdir=None):
    import cairosvg

    out = Path(outdir) if outdir else ROOT / "samples/challenges"
    out.mkdir(parents=True, exist_ok=True)
    for name, author in LOGOS.items():
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
