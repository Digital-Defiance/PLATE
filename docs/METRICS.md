# Editability metrics

"Editable" must be measured. For each output SVG:

| Metric | Meaning | Direction |
|---|---|---|
| anchors_per_shape | median anchor count per path | lower |
| primitive_ratio | fraction of shapes emitted as true primitives where a primitive fits | higher |
| layer_count / tree_depth | named layers and nesting | task-dependent; report |
| unnamed_ratio | layers with generic names ("path123") | lower |
| completeness | occluded shapes whose hidden part is restored (manual label on bench set) | higher |
| fidelity | SSIM/LPIPS between render and source | higher (guard rail, not the goal) |
| seam_gaps | hairline gaps between adjacent fills | 0 |
| file_size | bytes | lower |

Controls to beat: plain VTracer (`--baseline`), Illustrator Image Trace, Vectorizer.AI
(the latter two run manually on the bench set). Bench set lives in `samples/bench/`
with a manifest of hand-labelled expectations.
