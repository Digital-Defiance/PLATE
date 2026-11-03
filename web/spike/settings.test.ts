/**
 * Unit tests for the Settings_Panel's settings-to-config serialisation
 * (web/src/settings.ts, task 16.2; Requirement 6.1/6.2 and the advanced LM
 * Studio serialisation from Requirement 10.1/10.2/10.3).
 *
 * The one thing these tests pin is the SERIALISATION CONTRACT the panel shares
 * with the engine glue `build_config` in `src/plate/web.py`. The glue resolves
 * defaults -> preset -> explicit-override, so the panel's job is to emit ONLY
 * what the user explicitly chose and let the glue fill the rest:
 *
 *   - An untouched panel serialises to `{}` (no lever keys at all); the glue
 *     then applies pure engine defaults. The panel must NOT re-send defaults.
 *   - Selecting a preset emits `{ preset }` and NOT the preset's lever values
 *     (the glue applies the preset). Untouched levers stay unemitted after a
 *     preset is chosen.
 *   - A touched numeric lever is emitted with its clamped value; out-of-range
 *     values clamp to the engine-sane bound (NUMERIC_SPECS, mirroring the
 *     glue's NUMERIC_RANGES: maxColors 1..256, simplify/smooth 0..10, workSize
 *     64..8192). Integer levers (maxColors/workSize) stay integers.
 *   - A touched boolean lever is emitted with its boolean value.
 *   - LM Studio naming: toggle OFF emits no vlmUrl/vlmModel; toggle ON with a
 *     blank/whitespace URL emits nothing (naming stays disabled, mirroring the
 *     glue's blank-vlm_url-is-disabled rule); toggle ON with a non-blank URL
 *     emits a trimmed vlmUrl (+ trimmed vlmModel only when non-empty, never a
 *     model without a URL).
 *   - reset() returns to `{}` (no preset, nothing touched, naming off).
 *
 * Both the pure `stateToConfig` (driven with SettingsState literals) and the
 * `SettingsPanel` (driven through a tiny fake DOM, mirroring warnings.test.ts)
 * are exercised, so the pure mapping AND the DOM wiring that mutates state and
 * emits onChange are both covered.
 *
 * The LM Studio fallback/enable-decision logic (naming.ts) is task 17.2's; here
 * we only pin what `toConfig` EMITS for the on/off/blank-URL cases.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type { PlateConfig } from "../src/protocol.js";
import {
  BOOLEAN_SPECS,
  NUMERIC_SPECS,
  PRESETS,
  SettingsPanel,
  stateToConfig,
  type BooleanLever,
  type NamingState,
  type NumericLever,
  type SettingsState,
} from "../src/settings.js";

/* -------------------------------------------------------------------------- */
/* SettingsState builders (for the pure stateToConfig tests)                   */
/* -------------------------------------------------------------------------- */

function defaultNumeric(): Record<NumericLever, number> {
  return {
    maxColors: NUMERIC_SPECS.maxColors.default,
    simplify: NUMERIC_SPECS.simplify.default,
    smooth: NUMERIC_SPECS.smooth.default,
    workSize: NUMERIC_SPECS.workSize.default,
  };
}

function defaultBoolean(): Record<BooleanLever, boolean> {
  return {
    snapPrimitives: BOOLEAN_SPECS.snapPrimitives.default,
    strokes: BOOLEAN_SPECS.strokes.default,
    gradients: BOOLEAN_SPECS.gradients.default,
    removeBackground: BOOLEAN_SPECS.removeBackground.default,
  };
}

function noneTouched(): SettingsState["touched"] {
  return {
    numeric: { maxColors: false, simplify: false, smooth: false, workSize: false },
    boolean: {
      snapPrimitives: false,
      strokes: false,
      gradients: false,
      removeBackground: false,
    },
  };
}

function defaultNaming(): NamingState {
  return { enabled: false, vlmUrl: "", vlmModel: "" };
}

/** A fresh, untouched state (no preset, engine-default positions, naming off). */
function freshState(): SettingsState {
  return {
    preset: undefined,
    numeric: defaultNumeric(),
    boolean: defaultBoolean(),
    touched: noneTouched(),
    naming: defaultNaming(),
  };
}

/* -------------------------------------------------------------------------- */
/* Minimal fake DOM (so SettingsPanel builds under Node, like warnings.test.ts)*/
/* -------------------------------------------------------------------------- */

/** A tiny stand-in for the slice of an element SettingsPanel touches. */
class FakeElement {
  id = "";
  className = "";
  textContent = "";
  htmlFor = "";
  type = "";
  value = "";
  checked = false;
  disabled = false;
  min = "";
  max = "";
  step = "";
  title = "";
  placeholder = "";
  readonly children: FakeElement[] = [];
  private readonly attrs = new Map<string, string>();
  private readonly handlers = new Map<string, Array<() => void>>();

  constructor(readonly tagName: string) {}

  setAttribute(name: string, value: string): void {
    this.attrs.set(name, value);
  }

  getAttribute(name: string): string | null {
    return this.attrs.has(name) ? (this.attrs.get(name) as string) : null;
  }

  appendChild(child: FakeElement): FakeElement {
    this.children.push(child);
    return child;
  }

  addEventListener(event: string, handler: () => void): void {
    const list = this.handlers.get(event) ?? [];
    list.push(handler);
    this.handlers.set(event, list);
  }

  /** Fire the registered handlers for an event, mimicking a user interaction. */
  dispatch(event: string): void {
    for (const handler of this.handlers.get(event) ?? []) handler();
  }
}

/** A fake `document` that only needs to mint fake elements. */
class FakeDocument {
  createElement(tag: string): FakeElement {
    return new FakeElement(tag);
  }
}

function asDocument(doc: FakeDocument): Document {
  return doc as unknown as Document;
}

/**
 * Build a panel against the fake DOM and expose the raw fake controls so a test
 * can simulate user interaction (set `.value`/`.checked`, then `dispatch`). The
 * controls are reached by their stable ids (`plate-<lever>`, `plate-preset`,
 * `plate-vlm*`), which the panel assigns in `build()`.
 */
function buildPanel() {
  const doc = new FakeDocument();
  const panel = new SettingsPanel({ document: asDocument(doc) });
  return { panel, root: panel.element as unknown as FakeElement };
}

/** Depth-first search for a control by its assigned id. */
function findById(root: FakeElement, id: string): FakeElement {
  const stack: FakeElement[] = [root];
  while (stack.length > 0) {
    const el = stack.pop() as FakeElement;
    if (el.id === id) return el;
    for (const child of el.children) stack.push(child);
  }
  throw new Error(`no control with id ${id}`);
}

/* -------------------------------------------------------------------------- */
/* stateToConfig — untouched panel (Requirement 6.1/6.2)                       */
/* -------------------------------------------------------------------------- */

test("an untouched state serialises to {} (no preset, no lever keys emitted)", () => {
  const config = stateToConfig(freshState());
  assert.deepEqual(config, {});
  // Belt-and-braces: assert NO lever key leaked through default-re-emission.
  assert.equal(Object.keys(config).length, 0);
});

/* -------------------------------------------------------------------------- */
/* stateToConfig — preset selection (Requirement 6.1)                          */
/* -------------------------------------------------------------------------- */

for (const preset of PRESETS) {
  test(`selecting preset '${preset}' emits { preset } and no lever values`, () => {
    const state = freshState();
    state.preset = preset;
    const config = stateToConfig(state);
    assert.deepEqual(config, { preset });
    // The glue applies the preset's levers; the panel must not re-send them.
    assert.equal(Object.keys(config).length, 1);
  });
}

test("a preset with untouched levers still emits only { preset }", () => {
  const state = freshState();
  state.preset = "logo";
  // levers sit at their displayed positions but are NOT marked touched
  state.numeric.maxColors = 8;
  state.boolean.strokes = false;
  const config = stateToConfig(state);
  assert.deepEqual(config, { preset: "logo" });
});

/* -------------------------------------------------------------------------- */
/* stateToConfig — numeric levers, emission + clamping (Requirement 6.2)       */
/* -------------------------------------------------------------------------- */

const NUMERIC_LEVERS: NumericLever[] = ["maxColors", "simplify", "smooth", "workSize"];

for (const lever of NUMERIC_LEVERS) {
  test(`touched numeric lever '${lever}' is emitted with its in-range value`, () => {
    const spec = NUMERIC_SPECS[lever];
    // A value comfortably inside the range (integer for int levers).
    const inRange = spec.step >= 1
      ? Math.round((spec.min + spec.max) / 2)
      : (spec.min + spec.max) / 2;
    const state = freshState();
    state.numeric[lever] = inRange;
    state.touched.numeric[lever] = true;
    const config = stateToConfig(state);
    assert.deepEqual(Object.keys(config), [lever]);
    assert.equal(config[lever], inRange);
  });

  test(`numeric lever '${lever}' clamps a below-min value to its min`, () => {
    const spec = NUMERIC_SPECS[lever];
    const state = freshState();
    state.numeric[lever] = spec.min - 1000;
    state.touched.numeric[lever] = true;
    const config = stateToConfig(state);
    assert.equal(config[lever], spec.min);
  });

  test(`numeric lever '${lever}' clamps an above-max value to its max`, () => {
    const spec = NUMERIC_SPECS[lever];
    const state = freshState();
    state.numeric[lever] = spec.max + 1000;
    state.touched.numeric[lever] = true;
    const config = stateToConfig(state);
    assert.equal(config[lever], spec.max);
  });
}

test("integer levers (maxColors/workSize) stay integers after clamping/snapping", () => {
  const state = freshState();
  state.numeric.maxColors = 12.7;
  state.numeric.workSize = 1500.4;
  state.touched.numeric.maxColors = true;
  state.touched.numeric.workSize = true;
  const config = stateToConfig(state);
  assert.ok(Number.isInteger(config.maxColors), "maxColors must be an integer");
  assert.ok(Number.isInteger(config.workSize), "workSize must be an integer");
  assert.equal(config.maxColors, 13);
  assert.equal(config.workSize, 1500);
});

test("the engine-sane numeric ranges match the glue's NUMERIC_RANGES", () => {
  // Pins the panel's ranges to src/plate/web.py's NUMERIC_RANGES so the panel
  // can never emit a value the glue would clamp differently.
  assert.equal(NUMERIC_SPECS.maxColors.min, 1);
  assert.equal(NUMERIC_SPECS.maxColors.max, 256);
  assert.equal(NUMERIC_SPECS.simplify.min, 0);
  assert.equal(NUMERIC_SPECS.simplify.max, 10);
  assert.equal(NUMERIC_SPECS.smooth.min, 0);
  assert.equal(NUMERIC_SPECS.smooth.max, 10);
  assert.equal(NUMERIC_SPECS.workSize.min, 64);
  assert.equal(NUMERIC_SPECS.workSize.max, 8192);
});

/* -------------------------------------------------------------------------- */
/* stateToConfig — boolean levers (Requirement 6.2)                            */
/* -------------------------------------------------------------------------- */

const BOOLEAN_LEVERS: BooleanLever[] = [
  "snapPrimitives",
  "strokes",
  "gradients",
  "removeBackground",
];

for (const lever of BOOLEAN_LEVERS) {
  test(`touched boolean lever '${lever}' is emitted with its boolean value (true)`, () => {
    const state = freshState();
    state.boolean[lever] = true;
    state.touched.boolean[lever] = true;
    const config = stateToConfig(state);
    assert.deepEqual(Object.keys(config), [lever]);
    assert.equal(config[lever], true);
  });

  test(`touched boolean lever '${lever}' is emitted with its boolean value (false)`, () => {
    const state = freshState();
    state.boolean[lever] = false;
    state.touched.boolean[lever] = true;
    const config = stateToConfig(state);
    assert.deepEqual(Object.keys(config), [lever]);
    assert.equal(config[lever], false);
  });
}

test("an untouched boolean lever is NOT emitted even when its value differs from default", () => {
  const state = freshState();
  state.boolean.removeBackground = true; // differs from default (false) but untouched
  const config = stateToConfig(state);
  assert.deepEqual(config, {});
});

/* -------------------------------------------------------------------------- */
/* stateToConfig — LM Studio naming serialisation (Requirement 10.1/10.2/10.3) */
/* -------------------------------------------------------------------------- */

test("naming toggle OFF emits no vlmUrl/vlmModel (even with a URL typed)", () => {
  const state = freshState();
  state.naming = { enabled: false, vlmUrl: "http://localhost:1234/v1", vlmModel: "m" };
  const config = stateToConfig(state);
  assert.equal(config.vlmUrl, undefined);
  assert.equal(config.vlmModel, undefined);
  assert.deepEqual(config, {});
});

test("naming ON with a blank URL emits nothing (naming stays disabled)", () => {
  const state = freshState();
  state.naming = { enabled: true, vlmUrl: "", vlmModel: "" };
  const config = stateToConfig(state);
  assert.deepEqual(config, {});
});

test("naming ON with a whitespace-only URL emits nothing (mirrors build_config)", () => {
  const state = freshState();
  state.naming = { enabled: true, vlmUrl: "   \t  ", vlmModel: "some-model" };
  const config = stateToConfig(state);
  assert.deepEqual(config, {});
});

test("naming ON with a non-blank URL emits a trimmed vlmUrl", () => {
  const state = freshState();
  state.naming = { enabled: true, vlmUrl: "  http://localhost:1234/v1  ", vlmModel: "" };
  const config = stateToConfig(state);
  assert.equal(config.vlmUrl, "http://localhost:1234/v1");
  assert.equal(config.vlmModel, undefined);
});

test("naming ON with URL + model emits trimmed vlmUrl and trimmed vlmModel", () => {
  const state = freshState();
  state.naming = {
    enabled: true,
    vlmUrl: "http://localhost:1234/v1",
    vlmModel: "  qwen2-vl  ",
  };
  const config = stateToConfig(state);
  assert.equal(config.vlmUrl, "http://localhost:1234/v1");
  assert.equal(config.vlmModel, "qwen2-vl");
});

test("naming never emits a vlmModel without a vlmUrl (blank URL, model set)", () => {
  const state = freshState();
  state.naming = { enabled: true, vlmUrl: "", vlmModel: "orphan-model" };
  const config = stateToConfig(state);
  assert.equal(config.vlmModel, undefined);
  assert.equal(config.vlmUrl, undefined);
});

test("naming with a whitespace-only model drops the model but keeps the URL", () => {
  const state = freshState();
  state.naming = {
    enabled: true,
    vlmUrl: "http://localhost:1234/v1",
    vlmModel: "    ",
  };
  const config = stateToConfig(state);
  assert.equal(config.vlmUrl, "http://localhost:1234/v1");
  assert.equal(config.vlmModel, undefined);
});

/* -------------------------------------------------------------------------- */
/* SettingsPanel — touched/preset/reset behaviour through the DOM wiring       */
/* -------------------------------------------------------------------------- */

test("a freshly built panel serialises to {}", () => {
  const { panel } = buildPanel();
  assert.deepEqual(panel.toConfig(), {});
});

test("moving a numeric slider marks it touched and emits the clamped value", () => {
  const { panel, root } = buildPanel();
  const input = findById(root, "plate-maxColors");
  input.value = "7";
  input.dispatch("input");
  assert.deepEqual(panel.toConfig(), { maxColors: 7 });
});

test("a slider dragged past its max emits the clamped max (engine-sane bound)", () => {
  const { panel, root } = buildPanel();
  const input = findById(root, "plate-workSize");
  input.value = "99999";
  input.dispatch("input");
  assert.equal(panel.toConfig().workSize, NUMERIC_SPECS.workSize.max);
});

test("toggling a checkbox marks it touched and emits its boolean", () => {
  const { panel, root } = buildPanel();
  const box = findById(root, "plate-removeBackground");
  box.checked = true;
  box.dispatch("change");
  assert.deepEqual(panel.toConfig(), { removeBackground: true });
});

test("selecting a preset via the dropdown emits { preset } and not lever values", () => {
  const { panel, root } = buildPanel();
  const select = findById(root, "plate-preset");
  select.value = "illustration";
  select.dispatch("change");
  assert.deepEqual(panel.toConfig(), { preset: "illustration" });
});

test("selecting a preset clears previously-touched levers", () => {
  const { panel, root } = buildPanel();
  // Touch a lever first.
  const input = findById(root, "plate-simplify");
  input.value = "3.5";
  input.dispatch("input");
  assert.deepEqual(panel.toConfig(), { simplify: 3.5 });
  // Now pick a preset: it owns the levers, so the touched flag is cleared.
  const select = findById(root, "plate-preset");
  select.value = "logo";
  select.dispatch("change");
  assert.deepEqual(panel.toConfig(), { preset: "logo" });
});

test("fine-tuning a lever after a preset emits { preset, lever }", () => {
  const { panel } = buildPanel();
  panel.selectPreset("compact");
  // selectPreset resets touched; a subsequent change is emitted on top.
  const root = panel.element as unknown as FakeElement;
  const box = findById(root, "plate-strokes");
  box.checked = false;
  box.dispatch("change");
  assert.deepEqual(panel.toConfig(), { preset: "compact", strokes: false });
});

test("enabling naming through the DOM emits a trimmed vlmUrl (+ model)", () => {
  const { panel, root } = buildPanel();
  const enable = findById(root, "plate-vlmEnabled");
  const url = findById(root, "plate-vlmUrl");
  const model = findById(root, "plate-vlmModel");

  enable.checked = true;
  enable.dispatch("change");
  url.value = "  http://localhost:1234/v1 ";
  url.dispatch("input");
  model.value = " qwen2-vl ";
  model.dispatch("input");

  assert.deepEqual(panel.toConfig(), {
    vlmUrl: "http://localhost:1234/v1",
    vlmModel: "qwen2-vl",
  });
});

test("naming URL typed while the toggle is OFF emits nothing", () => {
  const { panel, root } = buildPanel();
  const url = findById(root, "plate-vlmUrl");
  url.value = "http://localhost:1234/v1";
  url.dispatch("input");
  assert.deepEqual(panel.toConfig(), {});
});

test("onChange fires with the freshly serialised config on each interaction", () => {
  const { panel, root } = buildPanel();
  const seen: PlateConfig[] = [];
  panel.onChange((c) => seen.push(c));

  const input = findById(root, "plate-maxColors");
  input.value = "5";
  input.dispatch("input");

  assert.ok(seen.length >= 1, "listener should fire on a slider move");
  assert.deepEqual(seen[seen.length - 1], { maxColors: 5 });
});

test("reset() returns the panel to {} (no preset, nothing touched, naming off)", () => {
  const { panel, root } = buildPanel();

  // Dirty the panel: preset, a lever, a toggle, and naming.
  const select = findById(root, "plate-preset");
  select.value = "logo";
  select.dispatch("change");
  const input = findById(root, "plate-smooth");
  input.value = "4.2";
  input.dispatch("input");
  const enable = findById(root, "plate-vlmEnabled");
  enable.checked = true;
  enable.dispatch("change");
  const url = findById(root, "plate-vlmUrl");
  url.value = "http://localhost:1234/v1";
  url.dispatch("input");
  assert.notDeepEqual(panel.toConfig(), {});

  panel.reset();
  assert.deepEqual(panel.toConfig(), {});
});

test("the reset button wired in the DOM also returns the panel to {}", () => {
  const { panel, root } = buildPanel();
  const input = findById(root, "plate-maxColors");
  input.value = "3";
  input.dispatch("input");
  assert.notDeepEqual(panel.toConfig(), {});

  const resetButton = root.children.find((c) => c.className === "plate-settings__reset");
  assert.ok(resetButton, "the panel must render a reset button");
  resetButton!.dispatch("click");
  assert.deepEqual(panel.toConfig(), {});
});
