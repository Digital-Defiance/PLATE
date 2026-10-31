"""Independent artwork/perturbation sweep: python -m plate.robustness --output DIR.

An opt-in diagnostic, requiring the render extra. Its targets are authored below,
never generated from PLATE output. The full suite deliberately includes stress
cases; failed contracts stay visible in report.json/index.html and return exit 1.
"""
from __future__ import annotations

import argparse
import copy
import html
import io
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment

from .config import Config
from .metrics import analyze_svg, fidelity

SVG = 'http://www.w3.org/2000/svg'
DRAWABLES = {'circle', 'ellipse', 'rect', 'path', 'polygon', 'polyline', 'line'}
MARKS = '''<circle id="disc" cx="42" cy="43" r="22" fill="#1e5fc3"/>
<rect id="panel" x="88" y="24" width="52" height="36" fill="#d43740"/>
<path id="ring" d="M166 44A24 24 0 1 0 214 44A24 24 0 1 0 166 44Z M179 44A11 11 0 1 0 201 44A11 11 0 1 0 179 44Z" fill="#199364" fill-rule="evenodd"/>
<path id="route" d="M20 106L104 106" fill="none" stroke="#141e2d" stroke-width="4" stroke-linecap="round"/>
<circle id="marker" cx="145" cy="106" r="4" fill="#eaac23"/>'''
PANELS = '''<rect id="background" width="256" height="144" fill="#f0f4f8"/>
<circle id="disc" cx="48" cy="64" r="26" fill="#1e5fc3"/>
<rect id="panel" x="98" y="34" width="54" height="62" fill="#d43740"/>
<rect id="detail" x="184" y="52" width="34" height="18" fill="#199364"/>'''


@dataclass(frozen=True)
class SweepCase:
    family: str = 'marks'
    scale: float = 1
    angle: float = 0
    noise: float = 0
    blur: float = 0
    contrast: float = 1
    seed: int = 17
    work_size: int = 1536
    route_width: float = 4
    tier: str = 'core'

    @property
    def name(self):
        return (f'{self.family}-s{self.scale:g}-r{self.angle:g}-n{self.noise:g}'
                f'-b{self.blur:g}-c{self.contrast:g}-w{self.work_size}'
                f'-line{self.route_width:g}-seed{self.seed}').replace('.', 'p')


def cases():
    result = [SweepCase(family=family, scale=scale, angle=angle)
              for family, scales in [('marks', (1, 2, 4)), ('panels', (.5, 1, 2, 4))]
              for scale in scales for angle in (0, 90, 180, 270)]
    result += [SweepCase(scale=s, angle=a, work_size=256) for s in (2, 4) for a in (0, 90, 180, 270)]
    result += [SweepCase(scale=s, angle=a, tier='stress') for s in (.25, .5) for a in (0, 90, 180, 270)]
    for family in ('marks', 'panels'):
        result += [SweepCase(family=family, angle=a, tier='stress') for a in (15, 37, 123)]
        result += [SweepCase(family=family, noise=n, seed=s, tier='stress') for n in (1, 2, 4, 8) for s in (17, 204)]
        result += [SweepCase(family=family, blur=b, tier='stress') for b in (.35, .7, 1.2)]
    result += [SweepCase(family='panels', contrast=c, tier='stress') for c in (.5, .25, .125, .0625)]
    result += [SweepCase(route_width=w, tier='stress') for w in (1, 2)]
    return result


def target_svg(case: SweepCase):
    """Apply a known uniform scale/rotation, fitting the whole canvas without clipping."""
    angle = math.radians(case.angle)
    cosine, sine = math.cos(angle), math.sin(angle)
    if abs(cosine) < 1e-12:
        cosine = 0
    if abs(sine) < 1e-12:
        sine = 0
    width = math.ceil(case.scale*(256*abs(cosine)+144*abs(sine)))
    height = math.ceil(case.scale*(256*abs(sine)+144*abs(cosine)))
    a, b, c, d = case.scale*cosine, case.scale*sine, -case.scale*sine, case.scale*cosine
    tx, ty = width/2-a*128-c*72, height/2-b*128-d*72
    matrix = 'matrix('+ ' '.join(f'{v:.12g}' for v in (a, b, c, d, tx, ty))+')'
    root = ET.fromstring(f'<svg xmlns="{SVG}" width="{width}" height="{height}" '
                         f'viewBox="0 0 {width} {height}">{MARKS if case.family == "marks" else PANELS}</svg>')
    for element in root:
        element.set('transform', matrix)
        for attribute in ('fill', 'stroke'):
            color = element.get(attribute, '')
            if color.startswith('#'):
                rgb = np.array(list(bytes.fromhex(color[1:])))
                rgb = np.rint(128+(rgb-128)*case.contrast).clip(0, 255).astype('uint8')
                element.set(attribute, '#'+rgb.tobytes().hex())
        if element.get('id') == 'route':
            element.set('stroke-width', str(case.route_width))
    return ET.tostring(root, encoding='unicode')


def _render(svg, size=None):
    import cairosvg
    options = {} if size is None else {'output_width': size[0], 'output_height': size[1]}
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), **options))) as image:
        return image.convert('RGBA')


def make_input(case: SweepCase):
    target = target_svg(case)
    root = ET.fromstring(target)
    size = tuple(int(root.get(k)) for k in ('width', 'height'))
    image = _render(target, (size[0]*4, size[1]*4)).resize(size, Image.Resampling.LANCZOS)
    if case.noise:
        pixels = np.array(image)
        noise = np.random.default_rng(case.seed).normal(0, case.noise, pixels[..., :3].shape)
        pixels[..., :3] = np.rint(pixels[..., :3].astype(float)+noise).clip(0, 255)
        image = Image.fromarray(pixels)
    if case.blur:
        image = image.convert('RGBa').filter(ImageFilter.GaussianBlur(case.blur)).convert('RGBA')
    return image, target


def _elements(root):
    return [e for e in root.iter() if e.tag.rsplit('}', 1)[-1] in DRAWABLES]


def _mask(root, element, size):
    isolated = ET.Element(root.tag, root.attrib)
    for child in root:
        if child.tag.rsplit('}', 1)[-1] == 'defs':
            isolated.append(copy.deepcopy(child))
    isolated.append(copy.deepcopy(element))
    return np.asarray(_render(ET.tostring(isolated, encoding='unicode'), size))[..., 3] >= 128


def _topology(mask):
    return (int(ndi.label(mask, np.ones((3, 3)))[1]),
            int(ndi.label(ndi.binary_fill_holes(mask) & ~mask)[1]))


def _color(element):
    return element.get('stroke') if element.get('fill') == 'none' else element.get('fill', '#000000')


def _lab_color(value):
    rgb = np.array(list(bytes.fromhex(value[1:])), np.float32).reshape(1, 1, 3)/255
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[0, 0]


def evaluate(case: SweepCase, actual_svg: str, target: str, observed: Image.Image):
    """Match complete object masks in authored-base-pixel coordinates, not by names."""
    actual, expected = ET.fromstring(actual_svg), ET.fromstring(target)
    got, want = _elements(actual), _elements(expected)
    size = tuple(round(float(expected.get(k))/case.scale) for k in ('width', 'height'))
    gm, wm = [_mask(actual, e, size) for e in got], [_mask(expected, e, size) for e in want]
    ious = np.array([[np.count_nonzero(a & b)/max(1, np.count_nonzero(a | b)) for a in gm] for b in wm])
    matches = {}
    if got:
        rows, cols = linear_sum_assignment(-ious)
        matches = dict(zip(rows, cols))
    checks = {'object_count': len(got) == len(want),
              'canvas': all(abs(float(actual.get(k))-float(expected.get(k))) < .01 for k in ('width', 'height'))}
    objects = []
    for wi, element in enumerate(want):
        label = element.get('id')
        if wi not in matches or ious[wi, matches[wi]] < .1:
            objects.append({'name': label, 'checks': {'present': False}})
            continue
        gi = matches[wi]
        boundary = wm[wi] & ~ndi.binary_erosion(wm[wi])
        deviation = np.count_nonzero(wm[wi] ^ gm[gi])/max(1, boundary.sum())
        recall = np.count_nonzero(wm[wi] & gm[gi])/max(1, wm[wi].sum())
        actual_color = _color(got[gi])
        color_error = (float(np.linalg.norm(_lab_color(_color(element))-_lab_color(actual_color)))
                       if actual_color and actual_color.startswith('#') and len(actual_color) == 7 else None)
        object_checks = {'present': True, 'silhouette': bool(ious[wi, gi] >= .96 or deviation <= .75),
                         'detail_coverage': bool(recall >= .9), 'topology': _topology(gm[gi]) == _topology(wm[wi]),
                         'color': color_error is not None and color_error <= 8}
        kind = element.tag.rsplit('}', 1)[-1]
        if kind in ('circle', 'rect') and not (label == 'marker' and wm[wi].sum()*case.scale**2 < 30):
            object_checks['primitive'] = got[gi].tag.rsplit('}', 1)[-1] == kind
        if label == 'route':
            object_checks['editable_stroke'] = got[gi].get('fill') == 'none' and got[gi].get('stroke') is not None
            object_checks['stroke_width'] = abs(float(got[gi].get('stroke-width', 0))/case.scale-case.route_width) <= 1
        ceiling = {'disc': 4, 'panel': 4, 'ring': 16, 'route': 4, 'marker': 12, 'background': 4, 'detail': 4}[label]
        isolated = ET.Element(actual.tag, actual.attrib)
        isolated.append(got[gi])
        object_checks['anchors'] = analyze_svg(ET.tostring(isolated, encoding='unicode'))['anchors'] <= ceiling
        objects.append({'name': label, 'actual_name': got[gi].get('id'), 'checks': object_checks,
                        'iou': round(float(ious[wi, gi]), 4), 'boundary_error': round(float(deviation), 4),
                        'coverage': round(float(recall), 4),
                        'color_delta_e': round(color_error, 4) if color_error is not None else None})
    checks['objects'] = all(all(o['checks'].values()) for o in objects)
    checks['paint_order'] = all(matches[lo] < matches[hi] for lo in range(len(want)) for hi in range(lo+1, len(want))
                                if lo in matches and hi in matches and np.count_nonzero(wm[lo] & wm[hi]) > 16)
    reference = np.asarray(_render(target, size))
    degraded = np.asarray(observed.resize(size, Image.Resampling.LANCZOS))
    scores = {}
    for label, bg in [('white', (255, 255, 255)), ('dark', (24, 24, 24))]:
        scores['reference_'+label] = fidelity(actual_svg, reference, bg=bg)['ssim']
        scores['observed_'+label] = fidelity(actual_svg, degraded, bg=bg)['ssim']
        checks['reference_'+label] = scores['reference_'+label] >= .97
    return {'name': case.name, 'parameters': asdict(case), 'checks': checks, 'objects': objects,
            'scores': scores, 'passed': all(checks.values())}


def run_case(case: SweepCase, directory: Path):
    from .pipeline import run
    directory.mkdir()
    image, target = make_input(case)
    source = directory/'input.png'
    image.save(source)
    (directory/'target.svg').write_text(target)
    result = run(source, Config(work_size=case.work_size))
    (directory/'actual.svg').write_text(result.svg)
    report = evaluate(case, result.svg, target, image)
    report['stats'] = result.stats
    (directory/'report.json').write_text(json.dumps(report, indent=2))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New directory; existing paths are refused')
    parser.add_argument('--suite', choices=['all', 'core'], default='all')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    selected = [c for c in cases() if args.suite == 'all' or c.tier == 'core']
    reports, cards = [], []
    for case in selected:
        report = run_case(case, args.output/case.name)
        reports.append(report)
        failures = [key for key, passed in report['checks'].items() if not passed]
        print(case.name+': '+(', '.join(failures) if failures else 'PASS'), flush=True)
        detail = [(o['name'], [k for k, passed in o['checks'].items() if not passed]) for o in report['objects']]
        images = ''.join(f'<figure><img width="256" src="{case.name}/{file}"><figcaption>{label}</figcaption></figure>'
                         for file, label in [('input.png', 'Observed PNG'), ('target.svg', 'Intended SVG'), ('actual.svg', 'PLATE SVG')])
        cards.append(f'<article><h2>{html.escape(case.name)}: {"PASS" if report["passed"] else "FAIL"}</h2>'
                     f'<div>{images}</div><pre>{html.escape(json.dumps(detail))}</pre></article>')
    summary = {'cases': reports, 'passed': sum(r['passed'] for r in reports), 'total': len(reports)}
    (args.output/'report.json').write_text(json.dumps(summary, indent=2))
    (args.output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>PLATE robustness</title>'
        '<style>body{font:14px sans-serif;margin:24px}article{border-top:1px solid #bbb}article div{display:flex}'
        'figure{margin:8px}img{background:#eee}pre{white-space:pre-wrap}</style>'
        f'<h1>PLATE robustness: {summary["passed"]}/{summary["total"]} pass</h1>'
        '<p>Independent source geometry; metrics use authored base pixels. Stress failures stay red. '
        'Reference SSIM uses the intended clean artwork; observed SSIM is diagnostic.</p>'+''.join(cards))
    print(f'{summary["passed"]}/{summary["total"]} pass. Report: {args.output / "report.json"}')
    return 0 if summary['passed'] == summary['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
