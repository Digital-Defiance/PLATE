"""Opt-in, local Illustrator integration: python -m plate.illustrator --output DIR.

Requires macOS, Illustrator, and Automation permission. Never runs during ordinary
pytest. All imported documents are fresh copies in a new output directory.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

DRAWABLES = {'path', 'circle', 'ellipse', 'rect', 'polygon', 'polyline', 'line'}
ADOBE_LAYER = '{http://ns.adobe.com/AdobeIllustrator/10.0/}layer'
INKSCAPE_LAYER = '{http://www.inkscape.org/namespaces/inkscape}groupmode'
APPLE_SCRIPT = '''on run argv
    with timeout of 600 seconds
        tell application id "com.adobe.illustrator"
            return do javascript (POSIX file (item 1 of argv) as alias)
        end tell
    end timeout
end run
'''


def _tag(e):
    return e.tag.rsplit('}', 1)[-1]


def _name(e):
    # Illustrator's SVG importer displays underscores in IDs as spaces.
    return e.get('id', '').replace('_', ' ')


def prepare_case(source: Path, directory: Path) -> dict:
    """Copy or generate SVG, plus independent expected edits, in an empty folder."""
    if source.suffix.lower() == '.svg':
        svg = source.read_text()
    else:
        from .pipeline import run
        svg = run(source).svg
    root = ET.fromstring(svg)
    width, height = [float(root.get(key, '').removesuffix('px')) for key in ('width', 'height')]
    if width <= 0 or height <= 0:
        raise ValueError('SVG dimensions must be positive pixels')
    leaves = [e for e in root.iter() if _tag(e) in DRAWABLES]
    if not leaves or any(not e.get('id') for e in leaves):
        raise ValueError('Input SVG must have named vector objects')
    parents = {}

    def walk(element, parent=None):
        if _tag(element) in DRAWABLES | {'g'}:
            name = _name(element)
            if not name or name in parents:
                raise ValueError('Input SVG must have unique names for objects and groups')
            parents[name] = parent
            parent = name
        for child in element:
            walk(child, parent)

    walk(root)
    directory.mkdir()
    (directory/'input.svg').write_text(svg)
    expected = {
        'width': width, 'height': height, 'shapes': len(leaves),
        'strokes': sum(e.get('stroke', 'none') != 'none' for e in leaves),
        'gradients': sum(e.get('fill', '').startswith('url(') for e in leaves),
        'names': sorted(_name(e) for e in leaves),
        'paint_order': [_name(e) for e in reversed(leaves)],
        'parents': parents,
        'layers': [_name(e) for e in reversed(root) if e.get(INKSCAPE_LAYER) == 'layer' or e.get(ADOBE_LAYER) == 'yes'],
        'native_layers': [_name(e) for e in root if e.get(ADOBE_LAYER) == 'yes'],
        'primitives': {_name(e): 4 for e in leaves if _tag(e) in ('circle', 'ellipse')},
    }
    edits = []
    fill = next((e for e in reversed(leaves) if e.get('fill', '').startswith('#')), None)
    stroke = next((e for e in reversed(leaves) if e.get('stroke', '').startswith('#')), None)
    for kind, target in [('translate', fill), ('recolour', fill), ('stroke', stroke)]:
        if target is None:
            continue
        edited = copy.deepcopy(root)
        e = next(e for e in edited.iter() if e.get('id') == target.get('id'))
        if kind == 'translate':
            e.set('transform', 'translate(10 0) '+e.get('transform', ''))
        elif kind == 'recolour':
            e.set('fill', '#ff00ff')
        else:
            e.set('stroke-width', str(float(e.get('stroke-width', '1'))*1.5))
        (directory/(kind+'.svg')).write_text(ET.tostring(edited, encoding='unicode'))
        edits.append({'kind': kind, 'item': _name(target)})
    return {'name': source.stem, 'svg': str(directory/'input.svg'), 'directory': str(directory),
            'expected': expected, 'edits': edits}


def structure_checks(case: dict, observed: dict) -> dict[str, bool]:
    """Strict import and AI roundtrip checks, including the known real-layer gap."""
    if 'error' in observed or 'imported' not in observed or 'reopened' not in observed:
        return {'script_completed': False}
    expected, before, after = case['expected'], observed['imported'], observed['reopened']
    named = {p['name']: p for p in before['items'] if p['type'] != 'GroupItem'}
    parents = {}
    for p in before['items']:
        parent = p.get('parent_name')
        # A plain SVG's synthetic "Layer 1" is not a semantic SVG parent. A
        # declared native layer is: membership must be checked, not discarded.
        if p.get('parent') == 'Layer' and parent not in expected['native_layers']:
            parent = None
        parents[p['name']] = parent
    for layer in before.get('layer_items', []):
        if layer['name'] in expected['native_layers']:
            parents[layer['name']] = layer['parent_name']
    return {
        'script_completed': True,
        'canvas': all(abs(before[k]-expected[k]) < .01 for k in ('width', 'height')),
        'vector_only': before['rasters'] == 0,
        'object_count': before['shapes'] == expected['shapes'],
        'object_names': sorted(p['name'] for p in before['items'] if p['type'] != 'GroupItem') == expected['names'],
        'group_hierarchy': parents == expected['parents'],
        'paint_order': [p['name'] for p in before['items'] if p['type'] != 'GroupItem'] == expected['paint_order'],
        'editable_strokes': before['strokes'] == expected['strokes'],
        'gradient_fills': before['gradients'] == expected['gradients'],
        'primitive_anchors': all(named.get(name, {}).get('anchors') == count for name, count in expected['primitives'].items()),
        'named_illustrator_layers': before['layers'] == expected['layers'] if expected['layers'] else True,
        'ai_roundtrip_structure': before == after,
    }


def evaluate_case(case: dict, observed: dict, min_ssim: float) -> dict:
    checks = structure_checks(case, observed)
    report = {'name': case['name'], 'checks': checks, 'scores': {}}
    if not checks['script_completed']:
        report['error'] = observed.get('error', 'Missing result')
        return report
    try:
        report['scores'] = _render_checks(case, observed, checks, min_ssim)
    except (OSError, ValueError, KeyError) as error:
        checks['render_evaluation'] = False
        report['error'] = str(error)
    return report


def _render_checks(case: dict, observed: dict, checks: dict, min_ssim: float) -> dict:
    import numpy as np
    from PIL import Image

    from .metrics import fidelity
    scores = {}
    directory = Path(case['directory'])
    svg = (directory/'input.svg').read_text()
    for stage in ('imported', 'reopened'):
        with Image.open(directory/(stage+'.png')) as im:
            rgba = np.asarray(im.convert('RGBA'))
        for label, bg in [('white', (255, 255, 255)), ('dark', (24, 24, 24))]:
            score = fidelity(svg, rgba, bg=bg)['ssim']
            scores[stage+'_'+label] = score
            checks[stage+'_'+label] = score >= min_ssim
    with Image.open(directory/'imported.png') as im:
        imported = np.asarray(im.convert('RGBA'))
    with Image.open(directory/'reopened.png') as im:
        reopened = np.asarray(im.convert('RGBA'))
    checks['ai_roundtrip_pixels'] = np.array_equal(imported, reopened)
    edits = {edit['kind']: edit for edit in observed.get('edits', [])}
    for edit in case['edits']:
        kind = edit['kind']
        if kind not in edits:
            checks[kind+'_applied'] = False
            continue
        checks[kind+'_applied'] = edits[kind]['applied']
        with Image.open(directory/(kind+'.png')) as im:
            rgba = np.asarray(im.convert('RGBA'))
        checks[kind+'_visible_change'] = not np.array_equal(reopened, rgba)
        for label, bg in [('white', (255, 255, 255)), ('dark', (24, 24, 24))]:
            score = fidelity((directory/(kind+'.svg')).read_text(), rgba, bg=bg)['ssim']
            scores[kind+'_'+label] = score
            checks[kind+'_'+label] = score >= min_ssim
    return scores


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='*', type=Path, help='PLATE SVGs or raster inputs')
    parser.add_argument('--output', required=True, type=Path, help='New directory; existing paths are refused')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--min-ssim', type=float, default=.98)
    args = parser.parse_args(argv)
    if sys.platform != 'darwin':
        parser.error('This opt-in integration requires macOS and Illustrator')
    if not 0 < args.min_ssim <= 1 or args.timeout <= 0:
        parser.error('Invalid timeout or SSIM threshold')
    inputs = args.inputs or [Path(p) for p in (
        'samples/face.png', 'samples/overlap.png', 'samples/donut_alpha.png', 'samples/shaded.png',
        'samples/challenges/perforated_plate.png', 'samples/challenges/gradient_badge.png',
        'samples/challenges/stroked_route.png', 'samples/challenges/logo_orbit_wordmark.png')]
    out = args.output.resolve()
    # Never open an existing user document or overwrite outputs from another run.
    out.mkdir(parents=True, exist_ok=False)
    cases = [prepare_case(p.resolve(), out/(f'{i:02d}-'+re.sub(r'[^A-Za-z0-9_-]', '_', p.stem))) for i, p in enumerate(inputs)]
    job = {'cases': cases, 'report': str(out/'illustrator.json')}
    (out/'manifest.json').write_text(json.dumps(job, indent=2))
    jsx = Path(__file__).with_name('_illustrator_check.jsx').read_text()
    script = out/'check.jsx'
    script.write_text(jsx.replace('__PLATE_JOB__', json.dumps(job, ensure_ascii=True)))
    bridge = out/'bridge.applescript'
    bridge.write_text(APPLE_SCRIPT)
    try:
        subprocess.run(['osascript', str(bridge), str(script)], capture_output=True, text=True,
                       check=True, timeout=args.timeout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        message = getattr(error, 'stderr', '') or str(error)
        print(f'Illustrator bridge failed: {message}', file=sys.stderr)
        print(f'Artifacts: {out}. A timeout does not cancel an in-app script; check Illustrator before retrying.', file=sys.stderr)
        return 2
    result = json.loads((out/'illustrator.json').read_text())
    observed = result['cases']
    reports = [evaluate_case(c, observed[i] if i < len(observed) else {}, args.min_ssim) for i, c in enumerate(cases)]
    report = {'illustrator_version': result['version'], 'errors': result['errors'], 'cases': reports}
    (out/'report.json').write_text(json.dumps(report, indent=2))
    failed = 0
    for case in reports:
        failures = [k for k, passed in case['checks'].items() if not passed]
        failed += bool(failures)
        print(case['name']+': '+(', '.join(failures) if failures else 'PASS'))
    print(f'Illustrator {result["version"]}: {len(reports)-failed} passed, {failed} failed. Report: {out / "report.json"}')
    return 1 if failed or result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
