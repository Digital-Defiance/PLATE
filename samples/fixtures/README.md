# Real-artwork regression fixtures

| file | what it is | what it guards |
|---|---|---|
| `research_force_logo.jpeg` | The Research Force logo (1170x1207 JPEG) | `tests/test_research_force_logo.py` |

**Licence:** included with the logo owner's permission as a regression fixture for PLATE.
It is *not* covered by this repository's MIT licence; do not reuse it outside PLATE's tests.

The Research Force logo is the image that found most of the `smooth` preset work (see
`docs/BAKEOFF.md`): wobbly outlines from JPEG ringing, faceted 14-gon arcs, a 2 px tagline that
vanished, and dark specks pinched off the tapering gaps between the book's page lines. The test
runs `--preset smooth --set upscale=2` and checks fidelity, that no extra or missing pieces
appear (bake-off `topology`), and that the tagline periods and the dot in the V survive.
