"""Headless guards for the opt-in Illustrator checker; never launch the desktop app."""
import copy
from xml.etree import ElementTree as ET

import pytest

from plate.illustrator import evaluate_case, prepare_case, structure_checks

SVG = '''<svg xmlns="http://www.w3.org/2000/svg"
 xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="64" height="64">
 <defs><linearGradient id="ramp"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs>
 <g id="Design_Layer" inkscape:groupmode="layer">
 <rect id="R" x="1" y="1" width="20" height="20" fill="#ff0000"/>
 <rect id="G" x="30" y="1" width="20" height="20" fill="url(#ramp)"/>
 <circle id="C" cx="20" cy="40" r="5" fill="#00ff00"/>
 <path id="S" d="M5 55L55 55" fill="none" stroke="#000000" stroke-width="2"/>
 </g></svg>'''


def _case(tmp_path):
    source = tmp_path/'source.svg'
    source.write_text(SVG)
    return prepare_case(source, tmp_path/'case')


def _snapshot():
    return {'width': 64, 'height': 64, 'layers': ['Design Layer'], 'shapes': 4,
            'rasters': 0, 'strokes': 1, 'gradients': 1,
            'items': [{'name': n, 'type': 'PathItem', 'anchors': 4,
                       'parent_name': 'Design Layer',
                       'geometry': [[0, 0, 0, 0, 1, 1]]} for n in ('S', 'C', 'G', 'R')]
            + [{'name': 'Design Layer', 'type': 'GroupItem', 'parent_name': None}]}


def test_preparation_generates_independent_edits_and_preserves_original(tmp_path):
    case = _case(tmp_path)
    assert case['expected']['names'] == ['C', 'G', 'R', 'S']
    assert case['expected']['layers'] == ['Design Layer']
    assert case['expected']['strokes'] == case['expected']['gradients'] == 1
    assert case['expected']['primitives'] == {'C': 4}
    ns = {'s': 'http://www.w3.org/2000/svg'}
    recolour = ET.parse(tmp_path/'case/recolour.svg').getroot()
    assert recolour.find('.//s:circle', ns).get('fill') == '#ff00ff'
    stroke = ET.parse(tmp_path/'case/stroke.svg').getroot()
    assert stroke.find('.//s:path', ns).get('stroke-width') == '3.0'
    translated = ET.parse(tmp_path/'case/translate.svg').getroot()
    assert translated.find('.//s:circle', ns).get('transform').strip() == 'translate(10 0)'
    assert (tmp_path/'source.svg').read_text() == SVG


def test_matching_import_and_native_roundtrip_pass(tmp_path):
    snapshot = _snapshot()
    checks = structure_checks(_case(tmp_path), {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert all(checks.values())


def test_imported_groups_do_not_count_as_true_illustrator_layers(tmp_path):
    snapshot = _snapshot()
    snapshot['layers'] = ['Layer 1']
    checks = structure_checks(_case(tmp_path), {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert [key for key, value in checks.items() if not value] == ['named_illustrator_layers']


@pytest.mark.parametrize('field,value,check', [
    ('rasters', 1, 'vector_only'), ('strokes', 0, 'editable_strokes'),
    ('gradients', 0, 'gradient_fills'), ('shapes', 5, 'object_count'),
    ('width', 65, 'canvas'), ('anchors', 8, 'primitive_anchors'),
    ('name', 'Lost circle', 'object_names'),
])
def test_checker_rejects_lost_editability_even_with_a_successful_save(tmp_path, field, value, check):
    snapshot = _snapshot()
    if field in ('anchors', 'name'):
        snapshot['items'][1][field] = value
    else:
        snapshot[field] = value
    checks = structure_checks(_case(tmp_path), {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert not checks[check]


def test_roundtrip_checks_hidden_geometry_not_just_item_counts(tmp_path):
    before = _snapshot()
    after = copy.deepcopy(before)
    after['items'][0]['geometry'][0][0] = 20
    checks = structure_checks(_case(tmp_path), {'imported': before, 'reopened': after})
    assert checks['object_count'] and not checks['ai_roundtrip_structure']


def test_existing_output_is_never_overwritten(tmp_path):
    case = _case(tmp_path)
    marker = tmp_path/'case/keep.ai'
    marker.write_bytes(b'user document')
    with pytest.raises(FileExistsError):
        prepare_case(tmp_path/'source.svg', tmp_path/'case')
    assert marker.read_bytes() == b'user document'
    assert case['directory'] == str(tmp_path/'case')


def test_flattened_groups_are_detected_even_when_names_and_counts_survive(tmp_path):
    snapshot = _snapshot()
    snapshot['items'][0]['parent_name'] = None
    checks = structure_checks(_case(tmp_path), {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert checks['object_names'] and checks['object_count']
    assert not checks['group_hierarchy']


def test_missing_desktop_export_is_a_reported_failure(tmp_path):
    snapshot = _snapshot()
    report = evaluate_case(_case(tmp_path), {'imported': snapshot, 'reopened': snapshot}, .98)
    assert not report['checks']['render_evaluation']
    assert 'imported.png' in report['error']


def test_duplicate_names_are_rejected_before_desktop_edits(tmp_path):
    source = tmp_path/'duplicate.svg'
    source.write_text(SVG.replace('id="C"', 'id="R"'))
    with pytest.raises(ValueError, match='unique names'):
        prepare_case(source, tmp_path/'case')
    assert not (tmp_path/'case').exists()


def _native_case(tmp_path):
    source = tmp_path/'native.svg'
    svg = SVG.replace('xmlns:inkscape=',
                      'xmlns:i="http://ns.adobe.com/AdobeIllustrator/10.0/" xmlns:inkscape=')
    source.write_text(svg.replace('inkscape:groupmode="layer"', 'inkscape:groupmode="layer" i:layer="yes"'))
    case = prepare_case(source, tmp_path/'case')
    snapshot = _snapshot()
    snapshot['items'] = snapshot['items'][:-1]  # the root SVG group becomes a real Layer
    for item in snapshot['items']:
        item['parent'] = 'Layer'
    snapshot['layer_items'] = [{'name': 'Design Layer', 'parent_name': None}]
    return case, snapshot


def test_native_layer_membership_and_hierarchy_survive_group_to_layer_import(tmp_path):
    case, snapshot = _native_case(tmp_path)
    checks = structure_checks(case, {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert all(checks.values())


def test_correct_layer_name_cannot_hide_wrong_object_membership(tmp_path):
    case, snapshot = _native_case(tmp_path)
    snapshot['items'][0]['parent_name'] = 'Wrong Layer'
    checks = structure_checks(case, {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert checks['named_illustrator_layers']
    assert not checks['group_hierarchy']


def test_native_layer_is_required_even_if_a_same_named_group_survives(tmp_path):
    case, _ = _native_case(tmp_path)
    snapshot = _snapshot()
    snapshot['layers'] = ['Layer 1']
    checks = structure_checks(case, {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert not checks['named_illustrator_layers']


def test_hidden_paint_order_change_fails_even_when_counts_names_and_parents_match(tmp_path):
    case, snapshot = _native_case(tmp_path)
    snapshot['items'][0], snapshot['items'][1] = snapshot['items'][1], snapshot['items'][0]
    checks = structure_checks(case, {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert checks['object_names'] and checks['object_count'] and checks['group_hierarchy']
    assert not checks['paint_order']


def test_extra_native_layer_is_not_silently_accepted(tmp_path):
    case, snapshot = _native_case(tmp_path)
    snapshot['layers'].append('Unexpected empty layer')
    checks = structure_checks(case, {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert not checks['named_illustrator_layers']


@pytest.mark.parametrize('reverse_layers', [False, True])
def test_actual_layer_order_is_checked_independently_of_object_order(tmp_path, reverse_layers):
    _native_case(tmp_path)
    source = tmp_path/'native.svg'
    source.write_text(source.read_text().replace('<g id="Design_Layer"',
        '<g id="Back_layer" i:layer="yes"><rect id="B" width="64" height="64" fill="#ffffff"/></g>'
        '<g id="Design_Layer"'))
    case = prepare_case(source, tmp_path/'two-layer-case')
    snapshot = _snapshot()
    snapshot['items'] = snapshot['items'][:-1]
    for item in snapshot['items']:
        item['parent'] = 'Layer'
    snapshot['items'].append({'name': 'B', 'type': 'PathItem', 'parent': 'Layer', 'parent_name': 'Back layer'})
    snapshot['shapes'] += 1
    snapshot['layers'] = ['Design Layer', 'Back layer']
    snapshot['layer_items'] = [{'name': name, 'parent_name': None} for name in snapshot['layers']]
    if reverse_layers:
        snapshot['layers'].reverse()
    checks = structure_checks(case, {'imported': snapshot, 'reopened': copy.deepcopy(snapshot)})
    assert checks['paint_order'] and checks['group_hierarchy']
    assert checks['named_illustrator_layers'] is not reverse_layers
