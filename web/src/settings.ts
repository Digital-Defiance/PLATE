/**
 * Settings_Panel — maps a small, friendly UI onto the engine's `Config` levers
 * (Browser_Shell, main thread; design Component 4).
 *
 * The panel is the primary control a visitor uses to steer a conversion: a
 * preset dropdown plus a curated handful of sliders and toggles. It produces a
 * {@link PlateConfig} (imported from `./protocol.js`, never redefined) that the
 * shell hands to `PlateClient.convert()`. The defaults -> preset -> override
 * resolution is NOT done here; it is the glue's job (`plate.web.build_config`
 * in `src/plate/web.py`), so this panel only reports the preset plus the levers
 * the user explicitly changed. Everything the panel omits keeps the engine
 * default exactly as `build_config` treats an absent key.
 *
 * Design decisions that matter:
 *   - Plain DOM, no framework (design: "a few sliders", Component 1/4). The
 *     panel builds its own elements and holds its own state; the shell mounts
 *     it and reads {@link SettingsPanel.toConfig}.
 *   - Only the curated subset is user-facing: presets `logo`/`illustration`/
 *     `lineart`/`compact`; numeric `maxColors`/`simplify`/`smooth`/`workSize`;
 *     toggles `snapPrimitives`/`strokes`/`gradients`/`removeBackground`. The
 *     advanced LM Studio fields (`vlmUrl`/`vlmModel`) live in a separate,
 *     collapsed "advanced" section that is OFF by default (task 17.1): a single
 *     enable toggle gates a `vlmUrl` text field (and an optional `vlmModel`),
 *     with a visible CORS note. When the toggle is off, or the URL is blank,
 *     `toConfig()` emits NO `vlmUrl` at all, so LM Studio naming stays disabled
 *     exactly as the glue's `build_config` treats an absent/blank `vlm_url`
 *     (Requirement 10.1/10.2/10.3). This mirrors `build_config`'s contract so
 *     the panel can never half-enable naming.
 *   - Control ranges/step/defaults mirror the engine-sane ranges the glue
 *     enforces (`NUMERIC_RANGES` + `Config` defaults in the engine), so the
 *     panel can never emit a value the glue would clamp or reject. The numbers
 *     below are pinned to those engine values, not guessed.
 *   - A lever is emitted only when the user explicitly set it (tracked per
 *     lever). Selecting a preset does NOT emit the preset's lever values — the
 *     glue applies the preset — it only moves the sliders' displayed positions
 *     so the UI reflects what the preset will do. Changing a slider marks that
 *     one lever as user-set; it is then emitted verbatim.
 */

import type { PlateConfig } from "./protocol.js";
import { isNamingEnabled } from "./naming.js";

/** Engine presets plus the browser small-text recipe (smooth + 2× analysis). */
export type Preset = NonNullable<PlateConfig["preset"]> | "logo-detail";

/** Ordered list of offered presets (drives the dropdown + validation). */
export const PRESETS: readonly Preset[] = [
  "logo",
  "smooth",
  "logo-detail",
  "illustration",
  "lineart",
  "compact",
  "max",
] as const;

/** A human-readable label for each preset (the dropdown option text). */
export const PRESET_LABELS: Record<Preset, string> = {
  logo: "Flat logo",
  smooth: "Clean JPEG logo",
  "logo-detail": "Logo with small text (2×, slower)",
  max: "Maximum detail (slower)",
  illustration: "Illustration",
  lineart: "Line art",
  compact: "Compact",
};

/** Visible lever values for the engine presets; hidden levers stay owned by Python. */
const PRESET_DISPLAY: Record<Preset, Partial<PlateConfig>> = {
  logo: { maxColors: 8, simplify: 0.6 },
  illustration: { maxColors: 24, simplify: 0.9 },
  lineart: { maxColors: 2, simplify: 0.5, snapPrimitives: false },
  compact: { maxColors: 12, simplify: 1.6, smooth: 1 },
  smooth: {},
  "logo-detail": {},
  max: { workSize: 3072, simplify: 0.35, smooth: 0.7, maxColors: 32 },
};

/** The numeric lever keys the panel exposes (subset of `PlateConfig`). */
export type NumericLever = "maxColors" | "simplify" | "smooth" | "workSize";

/** The boolean lever keys the panel exposes (subset of `PlateConfig`). */
export type BooleanLever =
  | "snapPrimitives"
  | "strokes"
  | "gradients"
  | "removeBackground";

/**
 * Engine-sane range and default for one numeric slider. `min`/`max` mirror
 * `plate.web.NUMERIC_RANGES` so the panel never emits a value the glue would
 * clamp; `default` mirrors the engine `Config` default so a freshly reset panel
 * shows the engine's own starting point. `step` keeps `maxColors`/`workSize`
 * integer (they are typed `int` on `Config`) and gives the error/sigma sliders
 * a fine step.
 */
export interface NumericSpec {
  min: number;
  max: number;
  step: number;
  default: number;
  /** Short label shown next to the control. */
  label: string;
  /** One-line hint shown as the control's title/tooltip. */
  hint: string;
}

/**
 * Numeric lever specs. Ranges are pinned to `plate.web.NUMERIC_RANGES`
 * (`max_colors` 1..256, `simplify` 0..10, `smooth` 0..10, `work_size`
 * 64..8192) and defaults to the engine `Config` (`max_colors=16`,
 * `simplify=0.8`, `smooth=0.8`, `work_size=1536`). Keeping both in sync with
 * the engine is what makes the panel's output always acceptable to the glue.
 */
export const NUMERIC_SPECS: Record<NumericLever, NumericSpec> = {
  maxColors: {
    min: 1,
    max: 256,
    step: 1,
    default: 16,
    label: "Max colors",
    hint: "Palette cap (flat art usually auto-detects fewer).",
  },
  simplify: {
    min: 0,
    max: 10,
    step: 0.1,
    default: 0.8,
    label: "Simplify",
    hint: "Curve-fitting error in px; higher means fewer anchors.",
  },
  smooth: {
    min: 0,
    max: 10,
    step: 0.1,
    default: 0.8,
    label: "Smooth",
    hint: "Contour smoothing sigma in px before fitting.",
  },
  workSize: {
    min: 64,
    max: 8192,
    step: 1,
    default: 1536,
    label: "Work size",
    hint: "Internal longest side in px; larger is finer but slower.",
  },
};

/**
 * Boolean lever specs: label, tooltip, and the engine `Config` default so a
 * reset panel shows the engine's own starting state (`snap_primitives=True`,
 * `strokes=True`, `gradients=True`, `remove_background=False`).
 */
export interface BooleanSpec {
  default: boolean;
  label: string;
  hint: string;
}

/** Boolean toggle specs, defaults pinned to the engine `Config`. */
export const BOOLEAN_SPECS: Record<BooleanLever, BooleanSpec> = {
  snapPrimitives: {
    default: true,
    label: "Snap primitives",
    hint: "Turn circles/ellipses/rects/polygons into real elements.",
  },
  strokes: {
    default: true,
    label: "Strokes",
    hint: "Emit round-capped lines, open curves and thin loops.",
  },
  gradients: {
    default: true,
    label: "Gradients",
    hint: "Detect smooth ramps as a single linear/radial gradient fill.",
  },
  removeBackground: {
    default: false,
    label: "Remove background",
    hint: "Drop the full-canvas background shape.",
  },
};

/**
 * The advanced LM Studio naming section's state (off by default).
 *
 *   - `enabled`: the advanced toggle. While false, naming is disabled and
 *     `toConfig()` emits no `vlmUrl`/`vlmModel` regardless of the field text.
 *   - `vlmUrl`: the user's LM Studio endpoint. Only a non-empty, non-whitespace
 *     URL (with `enabled` true) actually enables naming — mirroring
 *     `build_config`, which clamps a blank/whitespace `vlm_url` to "disabled".
 *   - `vlmModel`: an optional model id, emitted only alongside an enabled URL so
 *     a model can never ride along without an endpoint to point at.
 */
export interface NamingState {
  enabled: boolean;
  vlmUrl: string;
  vlmModel: string;
}

/** A fresh (off) naming section: disabled, with empty endpoint/model fields. */
function defaultNaming(): NamingState {
  return { enabled: false, vlmUrl: "", vlmModel: "" };
}

/**
 * The CORS note shown next to the advanced toggle (Requirement 10.1): LM Studio
 * must enable CORS for the browser origin or the naming call will be rejected
 * and the shell falls back to classical names. Pinned here so the panel and any
 * test assert the same wording; `naming.ts` owns the runtime fallback notes.
 */
export const LM_STUDIO_CORS_NOTE =
  "Advanced: LM Studio must have CORS enabled for this page's origin, or naming " +
  "falls back to classical color-and-shape names.";

/**
 * The live state of the panel. `preset` is the selected preset (or `undefined`
 * for engine defaults with no preset). `numeric`/`boolean` hold the current
 * control values; `touched` records which levers the user explicitly changed —
 * only touched levers are emitted so an untouched panel mirrors
 * defaults -> preset exactly as `build_config` resolves them. `naming` holds the
 * advanced LM Studio section (off by default; see {@link NamingState}).
 */
export interface SettingsState {
  preset: Preset | undefined;
  numeric: Record<NumericLever, number>;
  boolean: Record<BooleanLever, boolean>;
  touched: {
    numeric: Record<NumericLever, boolean>;
    boolean: Record<BooleanLever, boolean>;
  };
  naming: NamingState;
}

/** A plain (non-DOM) snapshot of the default control positions. */
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

/** The ordered numeric levers (drives DOM building and iteration). */
const NUMERIC_LEVERS: readonly NumericLever[] = [
  "maxColors",
  "simplify",
  "smooth",
  "workSize",
];

/** The ordered boolean levers (drives DOM building and iteration). */
const BOOLEAN_LEVERS: readonly BooleanLever[] = [
  "snapPrimitives",
  "strokes",
  "gradients",
  "removeBackground",
];

/** Clamp a numeric value into its lever's engine-sane range, then snap to step. */
function clampNumeric(lever: NumericLever, value: number): number {
  const spec = NUMERIC_SPECS[lever];
  if (!Number.isFinite(value)) return spec.default;
  const bounded = Math.min(Math.max(value, spec.min), spec.max);
  // Integer levers (max_colors / work_size) must stay integers for the engine.
  return spec.step >= 1 ? Math.round(bounded) : bounded;
}

/**
 * Turn a panel state into a {@link PlateConfig}. Emits `preset` when one is
 * selected, and each lever ONLY when the user explicitly touched it (so an
 * untouched lever stays at its default/unset and the glue keeps the engine or
 * preset value). Numeric values are clamped into the engine-sane range as a
 * belt-and-braces guard even though the controls already constrain them. This
 * is the pure, testable core task 16.2 exercises.
 */
export function stateToConfig(state: SettingsState): PlateConfig {
  const config: PlateConfig = {};
  if (state.preset === "logo-detail") {
    config.preset = "smooth";
    config.upscale = 2;
  } else if (state.preset !== undefined) {
    config.preset = state.preset;
  }

  for (const lever of NUMERIC_LEVERS) {
    if (state.touched.numeric[lever]) {
      config[lever] = clampNumeric(lever, state.numeric[lever]);
    }
  }
  for (const lever of BOOLEAN_LEVERS) {
    if (state.touched.boolean[lever]) {
      config[lever] = state.boolean[lever];
    }
  }

  // Advanced LM Studio naming. Emit `vlmUrl` ONLY when the advanced toggle is on
  // AND the URL is non-blank — i.e. when naming is actually enabled by the same
  // trimmed-non-empty test the glue's `build_config` applies (checked through
  // `isNamingEnabled`). Off, or on-with-blank-URL, emits nothing so naming stays
  // disabled and the panel can never half-enable it (Requirement 10.1/10.2/10.3).
  // `vlmModel` rides along only with an enabled URL, never alone, so a model id
  // can never half-enable naming either. The URL/model are emitted trimmed to
  // match exactly what the glue would honour.
  if (state.naming.enabled) {
    const url = state.naming.vlmUrl.trim();
    if (isNamingEnabled({ vlmUrl: url })) {
      config.vlmUrl = url;
      const model = state.naming.vlmModel.trim();
      if (model.length > 0) config.vlmModel = model;
    }
  }
  return config;
}

/** The DOM handles the panel keeps so it can read/update controls. */
interface Controls {
  presetSelect: HTMLSelectElement;
  numeric: Record<NumericLever, HTMLInputElement>;
  boolean: Record<BooleanLever, HTMLInputElement>;
  resetButton: HTMLButtonElement;
  /** Advanced LM Studio naming controls (off by default). */
  namingEnable: HTMLInputElement;
  namingUrl: HTMLInputElement;
  namingModel: HTMLInputElement;
}

/**
 * A listener fired whenever the panel state changes (preset pick, slider move,
 * toggle, or reset), handed the freshly serialised config so the shell can keep
 * a conversion request's config in sync without re-reading the DOM.
 */
export type SettingsChangeListener = (config: PlateConfig) => void;

/**
 * Options for {@link SettingsPanel}. `document` is injectable so the panel can
 * be built against a DOM-like stub in tests (task 16.2) without a real browser;
 * it defaults to the ambient `document` when one exists.
 */
export interface SettingsPanelOptions {
  /** Document used to create elements; defaults to the global `document`. */
  document?: Document;
  /** Initial preset to select; defaults to no preset (engine defaults). */
  initialPreset?: Preset;
}

/**
 * The Settings_Panel: builds its own DOM, holds its own state, and serialises
 * to a {@link PlateConfig}. Construct it, append {@link SettingsPanel.element}
 * to the shell, register {@link SettingsPanel.onChange}, and read
 * {@link SettingsPanel.toConfig} when building a {@link ConvertRequest}.
 *
 * Interaction model:
 *   - Picking a preset sets `state.preset` and moves every slider/toggle to
 *     that preset's effective position for display, and resets `touched` (the
 *     preset now owns those levers via the glue). The user then fine-tunes from
 *     there; any control they move is marked touched and emitted on top of the
 *     preset.
 *   - Reset returns to no preset + engine defaults with nothing touched.
 */
export class SettingsPanel {
  /** The panel's root element; append this to the shell. */
  readonly element: HTMLElement;

  private readonly doc: Document;
  private readonly controls: Controls;
  private readonly listeners = new Set<SettingsChangeListener>();
  private readonly state: SettingsState;

  constructor(options: SettingsPanelOptions = {}) {
    const doc = options.document ?? globalThis.document;
    if (!doc) {
      throw new Error(
        "SettingsPanel needs a document; pass one via options.document in a non-DOM environment",
      );
    }
    this.doc = doc;
    this.state = {
      preset: options.initialPreset,
      numeric: defaultNumeric(),
      boolean: defaultBoolean(),
      touched: noneTouched(),
      naming: defaultNaming(),
    };

    const built = this.build();
    this.element = built.root;
    this.controls = built.controls;
    this.selectPreset(options.initialPreset);
  }

  /**
   * Serialise the current panel state to a {@link PlateConfig}. Pure read: it
   * never touches the DOM (state is kept in sync as controls change), so the
   * shell can call it at convert time and task 16.2 can assert its mapping.
   */
  toConfig(): PlateConfig {
    return stateToConfig(this.state);
  }

  /** Register a change listener; returns an unsubscribe function. */
  onChange(listener: SettingsChangeListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /**
   * Programmatically select a preset (or clear it with `undefined`). Moves the
   * controls to the preset's displayed positions and clears the touched flags,
   * mirroring a user picking the preset from the dropdown.
   */
  selectPreset(preset: Preset | undefined): void {
    this.state.preset = preset;
    this.state.touched = noneTouched();
    this.state.numeric = defaultNumeric();
    this.state.boolean = defaultBoolean();
    const display = preset === undefined ? {} : PRESET_DISPLAY[preset];
    for (const lever of NUMERIC_LEVERS) {
      const value = display[lever];
      if (typeof value === "number") this.state.numeric[lever] = value;
    }
    for (const lever of BOOLEAN_LEVERS) {
      const value = display[lever];
      if (typeof value === "boolean") this.state.boolean[lever] = value;
    }
    this.controls.presetSelect.value = preset ?? "";
    this.syncControlsFromState();
    this.emitChange();
  }

  /**
   * Reset to no preset + engine defaults with nothing touched (equivalent to a
   * fresh panel). Emits a change so the shell's request config follows.
   */
  reset(): void {
    this.state.preset = undefined;
    this.state.numeric = defaultNumeric();
    this.state.boolean = defaultBoolean();
    this.state.touched = noneTouched();
    this.state.naming = defaultNaming();
    this.controls.presetSelect.value = "";
    this.syncControlsFromState();
    this.emitChange();
  }

  /* ---------------------------------------------------------------------- */
  /* DOM construction                                                        */
  /* ---------------------------------------------------------------------- */

  private build(): { root: HTMLElement; controls: Controls } {
    const root = this.el("section");
    root.className = "plate-settings";
    root.setAttribute("aria-label", "Conversion settings");

    // --- preset ---
    const presetField = this.field("Preset");
    const presetSelect = this.el("select") as HTMLSelectElement;
    presetSelect.className = "plate-settings__preset";
    presetSelect.id = "plate-preset";

    const noneOption = this.el("option") as HTMLOptionElement;
    noneOption.value = "";
    noneOption.textContent = "Balanced — start here";
    presetSelect.appendChild(noneOption);
    for (const preset of PRESETS) {
      const option = this.el("option") as HTMLOptionElement;
      option.value = preset;
      option.textContent = PRESET_LABELS[preset];
      presetSelect.appendChild(option);
    }
    presetSelect.addEventListener("change", () => {
      const value = presetSelect.value;
      this.selectPreset(value === "" ? undefined : (value as Preset));
    });
    presetField.label.htmlFor = presetSelect.id;
    presetField.row.appendChild(presetSelect);
    root.appendChild(presetField.row);

    const note = this.el("p");
    note.className = "plate-settings__note";
    note.textContent = "Changes update your preview automatically. For logos like Research Force, choose Logo with small text; 2× analysis uses more memory and takes longer.";
    root.appendChild(note);
    const tuning = this.el("details");
    tuning.className = "plate-settings__tuning";
    const tuningSummary = this.el("summary");
    tuningSummary.textContent = "Fine-tune colors, curves and background";
    tuning.appendChild(tuningSummary);
    root.appendChild(tuning);

    // --- numeric sliders ---
    const numeric = {} as Record<NumericLever, HTMLInputElement>;
    for (const lever of NUMERIC_LEVERS) {
      const spec = NUMERIC_SPECS[lever];
      const field = this.field(spec.label);
      const input = this.el("input") as HTMLInputElement;
      input.type = "range";
      input.className = "plate-settings__numeric";
      input.id = `plate-${lever}`;
      input.min = String(spec.min);
      input.max = String(spec.max);
      input.step = String(spec.step);
      input.title = spec.hint;
      input.addEventListener("input", () => {
        const parsed = Number(input.value);
        this.state.numeric[lever] = clampNumeric(lever, parsed);
        this.state.touched.numeric[lever] = true;
        this.emitChange();
      });
      field.label.htmlFor = input.id;
      field.row.appendChild(input);
      tuning.appendChild(field.row);
      numeric[lever] = input;
    }

    // --- boolean toggles ---
    const boolean = {} as Record<BooleanLever, HTMLInputElement>;
    for (const lever of BOOLEAN_LEVERS) {
      const spec = BOOLEAN_SPECS[lever];
      const field = this.field(spec.label);
      const input = this.el("input") as HTMLInputElement;
      input.type = "checkbox";
      input.className = "plate-settings__boolean";
      input.id = `plate-${lever}`;
      input.title = spec.hint;
      input.addEventListener("change", () => {
        this.state.boolean[lever] = input.checked;
        this.state.touched.boolean[lever] = true;
        this.emitChange();
      });
      field.label.htmlFor = input.id;
      field.row.appendChild(input);
      tuning.appendChild(field.row);
      boolean[lever] = input;
    }

    // --- advanced: LM Studio naming (off by default) ---
    const advanced = this.el("details") as HTMLDetailsElement;
    advanced.className = "plate-settings__advanced";
    const summary = this.el("summary");
    summary.className = "plate-settings__advanced-summary";
    summary.textContent = "Advanced: LM Studio naming";
    advanced.appendChild(summary);

    const corsNote = this.el("p");
    corsNote.className = "plate-settings__note";
    corsNote.textContent = LM_STUDIO_CORS_NOTE;
    advanced.appendChild(corsNote);

    // Enable toggle.
    const enableField = this.field("Enable LM Studio naming");
    const namingEnable = this.el("input") as HTMLInputElement;
    namingEnable.type = "checkbox";
    namingEnable.className = "plate-settings__naming-enable";
    namingEnable.id = "plate-vlmEnabled";
    namingEnable.title =
      "Off by default. Requires CORS enabled in LM Studio for this origin.";
    enableField.label.htmlFor = namingEnable.id;
    enableField.row.appendChild(namingEnable);
    advanced.appendChild(enableField.row);

    // Endpoint URL.
    const urlField = this.field("LM Studio URL");
    const namingUrl = this.el("input") as HTMLInputElement;
    namingUrl.type = "url";
    namingUrl.className = "plate-settings__naming-url";
    namingUrl.id = "plate-vlmUrl";
    namingUrl.placeholder = "http://localhost:1234/v1";
    namingUrl.title =
      "LM Studio OpenAI-compatible endpoint. Blank keeps naming disabled.";
    urlField.label.htmlFor = namingUrl.id;
    urlField.row.appendChild(namingUrl);
    advanced.appendChild(urlField.row);

    // Optional model id.
    const modelField = this.field("LM Studio model (optional)");
    const namingModel = this.el("input") as HTMLInputElement;
    namingModel.type = "text";
    namingModel.className = "plate-settings__naming-model";
    namingModel.id = "plate-vlmModel";
    namingModel.placeholder = "(engine default)";
    namingModel.title = "Optional model id; only used when a URL is set.";
    modelField.label.htmlFor = namingModel.id;
    modelField.row.appendChild(namingModel);
    advanced.appendChild(modelField.row);

    namingEnable.addEventListener("change", () => {
      this.state.naming.enabled = namingEnable.checked;
      this.syncNamingDisabled();
      this.emitChange();
    });
    namingUrl.addEventListener("input", () => {
      this.state.naming.vlmUrl = namingUrl.value;
      this.emitChange();
    });
    namingModel.addEventListener("input", () => {
      this.state.naming.vlmModel = namingModel.value;
      this.emitChange();
    });

    root.appendChild(advanced);

    // --- reset ---
    const resetButton = this.el("button") as HTMLButtonElement;
    resetButton.type = "button";
    resetButton.className = "plate-settings__reset";
    resetButton.textContent = "Reset to defaults";
    resetButton.addEventListener("click", () => {
      this.reset();
    });
    root.appendChild(resetButton);

    const presetValue = this.state.preset ?? "";
    presetSelect.value = presetValue;

    return {
      root,
      controls: {
        presetSelect,
        numeric,
        boolean,
        resetButton,
        namingEnable,
        namingUrl,
        namingModel,
      },
    };
  }

  /** Build a labelled row: a wrapper holding a `<label>` plus (later) a control. */
  private field(labelText: string): { row: HTMLElement; label: HTMLLabelElement } {
    const row = this.el("div");
    row.className = "plate-settings__field";
    const label = this.el("label") as HTMLLabelElement;
    label.className = "plate-settings__label";
    label.textContent = labelText;
    row.appendChild(label);
    return { row, label };
  }

  private el(tag: string): HTMLElement {
    return this.doc.createElement(tag);
  }

  /* ---------------------------------------------------------------------- */
  /* State <-> controls                                                      */
  /* ---------------------------------------------------------------------- */

  /** Push the current state's values onto the DOM controls (display only). */
  private syncControlsFromState(): void {
    for (const lever of NUMERIC_LEVERS) {
      this.controls.numeric[lever].value = String(this.state.numeric[lever]);
    }
    for (const lever of BOOLEAN_LEVERS) {
      this.controls.boolean[lever].checked = this.state.boolean[lever];
    }
    this.controls.namingEnable.checked = this.state.naming.enabled;
    this.controls.namingUrl.value = this.state.naming.vlmUrl;
    this.controls.namingModel.value = this.state.naming.vlmModel;
    this.syncNamingDisabled();
  }

  /**
   * Visually gate the URL/model inputs on the enable toggle: when naming is off,
   * the endpoint and model fields are disabled so a visitor cannot type a URL
   * that would be ignored. This is display-only; `toConfig()`'s emit rule is the
   * real gate, so even a stale URL with the toggle off emits nothing.
   */
  private syncNamingDisabled(): void {
    const off = !this.state.naming.enabled;
    this.controls.namingUrl.disabled = off;
    this.controls.namingModel.disabled = off;
  }

  /** Notify listeners with the freshly serialised config. */
  private emitChange(): void {
    const config = this.toConfig();
    for (const listener of this.listeners) listener(config);
  }
}
