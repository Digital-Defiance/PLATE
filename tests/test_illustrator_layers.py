"""Layer interchange contracts, independent of the desktop Illustrator installation."""
from xml.etree import ElementTree as ET

from plate.scene import Node
from plate.stages.emit import write_svg

SVG = 'http://www.w3.org/2000/svg'
ADOBE = 'http://ns.adobe.com/AdobeIllustrator/10.0/'
INKSCAPE = 'http://www.inkscape.org/namespaces/inkscape'


def _nodes():
    return [
        Node('Background', 'rect', (255, 255, 255), params={'cx': 32, 'cy': 32, 'rx': 32, 'ry': 32}),
        Node('Artwork', 'group', children=[
            Node('Disc', 'circle', (255, 0, 0), params={'cx': 32, 'cy': 32, 'r': 20}),
            Node('Detail', 'group', children=[
                Node('Eye', 'circle', (0, 0, 0), params={'cx': 30, 'cy': 25, 'r': 4}),
            ]),
        ]),
    ]


def test_every_top_level_object_has_a_real_layer_container():
    nodes = _nodes()
    root = ET.fromstring(write_svg(nodes, (64, 64)))
    assert [e.tag for e in root] == ['{'+SVG+'}g']*2
    assert [e.get('id') for e in root] == ['Background_layer', 'Artwork']
    assert all(e.get('{'+ADOBE+'}layer') == 'yes' for e in root)
    assert all(e.get('{'+INKSCAPE+'}groupmode') == 'layer' for e in root)
    assert root[0][0].get('id') == 'Background'
    assert root[1][0].get('id') == 'Disc'
    assert root[1][1].get('id') == 'Detail'
    assert root[1][1].get('{'+ADOBE+'}layer') is None  # nested semantic groups stay groups
    assert nodes[0].kind == 'rect' and nodes[1].children[1].kind == 'group'


def test_layer_wrappers_cannot_steal_existing_object_ids():
    nodes = [Node(name, 'circle', (20, 80, 200), params={'cx': 30, 'cy': 30, 'r': 10})
             for name in ('Disc', 'Disc layer', 'Disc layer 2')]
    root = ET.fromstring(write_svg(nodes, (64, 64)))
    assert [e[0].get('id') for e in root] == ['Disc', 'Disc_layer', 'Disc_layer_2']
    ids = [e.get('id') for e in root.iter() if e.get('id')]
    assert len(ids) == len(set(ids))


def test_disabled_layers_keep_the_original_ungrouped_output():
    root = ET.fromstring(write_svg(_nodes(), (64, 64), layers=False))
    assert root[0].tag == '{'+SVG+'}rect'
    assert root[1].tag == '{'+SVG+'}g'
    assert all(e.get('{'+ADOBE+'}layer') is None and e.get('id') is None for e in root.iter())


def test_empty_artwork_has_no_synthetic_layer_or_object():
    assert len(ET.fromstring(write_svg([], (64, 64)))) == 0
