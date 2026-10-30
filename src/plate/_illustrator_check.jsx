/* Desktop-only PLATE check. Open and close only copies listed in this job. */
(function () {
    var job = __PLATE_JOB__;
    var prior = app.documents.length ? app.activeDocument : null;
    var ui = app.userInteractionLevel;
    var result = {version: app.version, cases: [], errors: []};
    function quote(s) {
        return '"' + String(s).replace(/[\\"\x00-\x1f]/g, function(c) {
            if (c === '"' || c === '\\') return '\\' + c;
            return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
        }) + '"';
    }
    function encode(v) {
        if (v === null || v === undefined) return 'null';
        if (typeof v === 'string') return quote(v);
        if (typeof v === 'number') return isFinite(v) ? String(v) : 'null';
        if (typeof v === 'boolean') return String(v);
        var parts = [], k;
        if (v instanceof Array) {
            for (k=0; k<v.length; k++) parts.push(encode(v[k]));
            return '[' + parts.join(',') + ']';
        }
        for (k in v) if (v.hasOwnProperty(k)) parts.push(quote(k) + ':' + encode(v[k]));
        return '{' + parts.join(',') + '}';
    }
    function write() {
        var f = new File(job.report);
        f.encoding = 'UTF-8';
        if (!f.open('w')) throw new Error('Cannot write report: ' + f.error);
        try { f.write(encode(result)); } finally { f.close(); }
    }
    function rounded(n) { return Math.round(Number(n)*1000)/1000; }
    function snapshot(d) {
        var s = {width: rounded(d.width), height: rounded(d.height), layers: [], layer_items: [], items: [],
                 shapes: 0, rasters: d.rasterItems.length + d.placedItems.length,
                 strokes: 0, gradients: 0, anchors: 0, compounds: d.compoundPathItems.length};
        var i, p, row, b, j;
        for (i=0; i<d.layers.length; i++) {
            var layer = d.layers[i];
            s.layers.push(layer.name);
            s.layer_items.push({name: layer.name, parent_name: null,
                                opacity: rounded(layer.opacity), visible: layer.visible, locked: layer.locked});
        }
        for (i=0; i<d.pageItems.length; i++) {
            p = d.pageItems[i];
            // Compound children share one style and one logical SVG object.
            if (p.parent.typename === 'CompoundPathItem') continue;
            b = p.geometricBounds;
            row = {name: p.name, type: p.typename, parent: p.parent.typename,
                   parent_name: p.parent.typename === 'GroupItem' || p.parent.typename === 'Layer' ? p.parent.name : null,
                   opacity: rounded(p.opacity), hidden: p.hidden, locked: p.locked,
                   bounds: [rounded(b[0]), rounded(b[1]), rounded(b[2]), rounded(b[3])]};
            if (p.typename !== 'GroupItem') s.shapes++;
            // ExtendScript can return undefined for a host object inside [p]
            // in a conditional expression. Copy explicitly into a JS array.
            var paths = [];
            if (p.typename === 'PathItem') paths.push(p);
            else if (p.typename === 'CompoundPathItem') {
                for (j=0; j<p.pathItems.length; j++) paths.push(p.pathItems[j]);
            }
            row.anchors = 0; row.geometry = [];
            for (j=0; j<paths.length; j++) {
                row.anchors += paths[j].pathPoints.length;
                var geometry = [];
                for (var n=0; n<paths[j].pathPoints.length; n++) {
                    var point = paths[j].pathPoints[n];
                    geometry.push([rounded(point.anchor[0]), rounded(point.anchor[1]),
                                   rounded(point.leftDirection[0]), rounded(point.leftDirection[1]),
                                   rounded(point.rightDirection[0]), rounded(point.rightDirection[1])]);
                }
                row.geometry.push({closed: paths[j].closed, points: geometry});
            }
            s.anchors += row.anchors;
            if (paths.length) {
                var style = paths[0];
                row.stroke = style.stroked ? rounded(style.strokeWidth) : 0;
                row.fill = style.filled ? style.fillColor.typename : 'none';
                row.closed = style.closed;
                if (style.stroked) s.strokes++;
                if (row.fill === 'GradientColor') {
                    s.gradients++;
                    row.gradient = String(style.fillColor.gradient.type);
                }
                if (p.typename === 'CompoundPathItem') row.parts = paths.length;
            }
            s.items.push(row);
        }
        return s;
    }
    function exportPNG(d, base) {
        var options = new ExportOptionsPNG24();
        options.artBoardClipping = true;
        options.transparency = true;
        options.antiAliasing = true;
        options.horizontalScale = 100; options.verticalScale = 100;
        d.exportFile(new File(base), ExportType.PNG24, options);
    }
    function find(d, name) {
        for (var i=0; i<d.pageItems.length; i++) {
            if (d.pageItems[i].name === name && d.pageItems[i].parent.typename !== 'CompoundPathItem')
                return d.pageItems[i];
        }
        throw new Error('Imported item not found: ' + name);
    }
    try {
        app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
        for (var i=0; i<job.cases.length; i++) {
            var c = job.cases[i], r = {name: c.name, edits: []}, doc = null;
            result.cases.push(r);
            try {
                doc = app.open(new File(c.svg));
                r.imported = snapshot(doc);
                exportPNG(doc, c.directory + '/imported');
                doc.saveAs(new File(c.directory + '/roundtrip.ai'), new IllustratorSaveOptions());
                doc.close(SaveOptions.DONOTSAVECHANGES); doc = null;
                doc = app.open(new File(c.directory + '/roundtrip.ai'));
                r.reopened = snapshot(doc);
                exportPNG(doc, c.directory + '/reopened');
                for (var e=0; e<c.edits.length; e++) {
                    var edit = c.edits[e], item = find(doc, edit.item), saved, applied = false;
                    var target = item.typename === 'CompoundPathItem' ? item.pathItems[0] : item;
                    if (edit.kind === 'translate') {
                        saved = item.geometricBounds[0]; item.translate(10, 0);
                        applied = Math.abs(item.geometricBounds[0] - saved - 10) < .01;
                        try { exportPNG(doc, c.directory + '/' + edit.kind); }
                        finally { item.translate(-10, 0); }
                    } else if (edit.kind === 'recolour') {
                        saved = target.fillColor;
                        var colour = new RGBColor(); colour.red=255; colour.green=0; colour.blue=255;
                        target.fillColor = colour;
                        applied = target.fillColor.typename === 'RGBColor' && target.fillColor.red === 255 && target.fillColor.green === 0;
                        try { exportPNG(doc, c.directory + '/' + edit.kind); }
                        finally { target.fillColor = saved; }
                    } else if (edit.kind === 'stroke') {
                        saved = target.strokeWidth; target.strokeWidth = saved * 1.5;
                        applied = Math.abs(target.strokeWidth - saved*1.5) < .01;
                        try { exportPNG(doc, c.directory + '/' + edit.kind); }
                        finally { target.strokeWidth = saved; }
                    }
                    r.edits.push({kind: edit.kind, item: edit.item, applied: applied});
                }
            } catch (error) {
                r.error = String(error) + ' (line ' + error.line + ')';
            } finally {
                if (doc) {
                    try { doc.close(SaveOptions.DONOTSAVECHANGES); }
                    catch (closeError) { result.errors.push('Closing test copy: ' + closeError); }
                }
                write();
            }
        }
    } catch (error) {
        result.errors.push(String(error) + ' (line ' + error.line + ')');
    } finally {
        app.userInteractionLevel = ui;
        if (prior) {
            try { app.activeDocument = prior; }
            catch (restoreError) { result.errors.push('Restoring original document: ' + restoreError); }
        }
        write();
    }
    return 'PLATE Illustrator check complete';
})();
