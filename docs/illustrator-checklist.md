# Illustrator verification checklist (do on the Mac; ~10 minutes)

Generate: `plate trace samples/face.png -o /tmp/face.svg` and `plate trace samples/badge.png -o /tmp/badge.svg`.
Open each in Adobe Illustrator (File ▸ Open), then record PASS/FAIL + notes in STATUS.md.

1. [ ] Layers panel shows layers/sub-layers named like "Yellow circle", "Black ellipse" (not `<Group>`/`<Path>`).
2. [ ] Names with spaces show correctly (we emit `id="Black_ellipse"` + `data-name="Black ellipse"`). If only underscored names appear, change emit.py to prefer data-name or accept underscores.
3. [ ] Top-level groups appear as layers (we add `inkscape:groupmode="layer"`; Illustrator may ignore it and show `<g>` as groups—note which).
4. [ ] Circle selected shows 4 anchors; ellipse 4; rect 4; rounded rect — live corner widget or 8 anchors?
5. [ ] Eye ellipses are tall (taller than wide) and aligned; mouth/face stack correct.
6. [ ] Stacking: hidden shapes (e.g. `overlap.png` red circle) are complete circles under the blue rect: select and move the rect away.
7. [ ] No hairline gaps between adjacent shapes at 400% zoom.
8. [ ] File ▸ Save As .ai opens again with names intact.
If layers fail: try variants in `stages/emit.py` (id only; `<g id>` only; Illustrator-style `data-name`) and re-test; keep whichever passes.
