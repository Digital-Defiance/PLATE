/**
 * Browser_Shell entry point — composes the finished Phase 2/4 modules into a
 * working page (main thread). This is the `./main.js` module `web/index.html`
 * references: it wires the static shell's DOM ids to the modules that already
 * exist, keeping every byte of CPU-heavy work in the Conversion_Worker behind
 * `PlateClient` (Property 5: non-blocking main thread).
 *
 * It introduces NO conversion logic of its own — it only connects the pieces:
 *   - intake.ts        validates a dropped/picked file (pre-decode checks)
 *   - settings.ts      maps presets/levers to a `PlateConfig`
 *   - PlateClient      posts the convert request to the worker and awaits it
 *   - preview.ts       renders source + SVG + layer list + result warnings
 *   - warnings.ts      shares the `#messages` area (beta JPEG warning composes)
 *   - errors.ts        surfaces runtime/input/platform failures + long-run
 *   - download.ts      saves the result SVG as `<base>.svg`
 *   - links.ts         beta label + (owner-gated, default-off) power-user links
 *
 * The flow, as a user drives it:
 *   drop/pick a file → intake.validateFile → (reject → errors surface) →
 *   settings.toConfig → PlateClient.convert (worker) → preview.render +
 *   download.setResult. Progress events drive the staged bar; a conversion that
 *   runs past the long-run threshold surfaces the continue/cancel notice.
 *
 * The composition is intentionally thin and injectable (document/client
 * factory) so it stays testable and so the smoke test can drive the same page.
 */

import { PlateClient, PlateClientError } from "./client.js";
import type { ProgressListener } from "./client.js";
import {
  clearAllErrorSurfaces,
  renderClientError,
  renderLongRunNotice,
  surfacePlatformCheck,
  LONG_RUN_THRESHOLD_MS,
} from "./errors.js";
import { LiveConversion } from "./live-conversion.js";
import { validateFile } from "./intake.js";
import type { FileLike } from "./intake.js";
import { mountShellLinks } from "./links.js";
import { Preview } from "./preview.js";
import type { ConvertResult, ProgressUpdate } from "./protocol.js";
import { SettingsPanel } from "./settings.js";
import { DownloadControl } from "./download.js";
import type { DocumentLike as DownloadControlDoc } from "./download.js";
import { mountMessageArea } from "./warnings.js";

/** The shell DOM ids this entry point wires (see `web/index.html`). */
export const SHELL_IDS = {
  dropZone: "drop-zone",
  fileInput: "file-input",
  progress: "progress",
  progressStage: "progress-stage",
  progressPct: "progress-pct",
  progressBar: "progress-bar",
  settingsHost: "settings-host",
} as const;

/** A friendly label for each coarse pipeline stage, shown in the progress bar. */
const STAGE_LABELS: Record<ProgressUpdate["stage"], string> = {
  "load-pyodide": "Loading runtime",
  "load-packages": "Loading packages",
  "install-plate": "Installing engine",
  import: "Starting engine",
  segment: "Segmenting",
  order: "Ordering layers",
  trace: "Tracing contours",
  emit: "Writing SVG",
  done: "Done",
};

/** Options for {@link mountApp}; all injectable so the app is testable. */
export interface MountAppOptions {
  /** Document to wire; defaults to the global `document`. */
  document?: Document;
  /** Factory for the worker-backed client; defaults to a real `PlateClient`. */
  createClient?: () => PlateClient;
  /** Owner decision: show power-user links (default off, Requirement 13.5). */
  powerUserLinks?: boolean;
}

/** The running app; exposed mainly so a test/harness can observe/dispose it. */
export interface MountedApp {
  readonly client: PlateClient;
  readonly settings: SettingsPanel;
  readonly preview: Preview;
  /** The last conversion result, if any (handy for the smoke test). */
  lastResult(): ConvertResult | null;
  dispose(): void;
}

function requireElement<T extends HTMLElement = HTMLElement>(
  doc: Document,
  id: string,
): T {
  const el = doc.getElementById(id);
  if (!el) throw new Error(`main.ts: missing shell element #${id}`);
  return el as T;
}

/**
 * Compose the finished modules against the static shell and start the runtime.
 * Returns a {@link MountedApp} handle. The heavy work stays in the worker; this
 * only wires DOM events to module calls and renders their results.
 */
export function mountApp(options: MountAppOptions = {}): MountedApp {
  const doc = options.document ?? globalThis.document;
  if (!doc) {
    throw new Error("main.ts needs a document; this module runs in the browser");
  }

  // Beta label + (owner-gated) power-user links.
  mountShellLinks({ document: doc, enabled: options.powerUserLinks ?? false });

  // Shared message area (beta JPEG warning, result warnings, errors compose here).
  const messages = mountMessageArea({ document: doc });

  // On-load platform pre-check: a hard miss disables intake; Safari is a soft note.
  const platform = surfacePlatformCheck({ document: doc, container: messages.container });

  // Settings panel: mount into its host if the shell provides one, else create
  // a holder so a conversion always has a resolvable config.
  const settings = new SettingsPanel({ document: doc });
  const settingsHost = doc.getElementById(SHELL_IDS.settingsHost);
  if (settingsHost) settingsHost.appendChild(settings.element);

  // Result view + download control.
  const preview = new Preview({ document: doc });
  // A real `Document` provides everything DownloadControl's `DocumentLike`
  // needs (getElementById / createElement("a") / body); the interface is
  // narrower by design, so bridge it explicitly.
  const download = new DownloadControl(
    doc as unknown as DownloadControlDoc,
  );

  const client = options.createClient ? options.createClient() : new PlateClient();

  const dropZone = requireElement(doc, SHELL_IDS.dropZone);
  const fileInput = requireElement<HTMLInputElement>(doc, SHELL_IDS.fileInput);
  const chooseImageButton = doc.getElementById("choose-image") as HTMLButtonElement | null;
  const progress = requireElement(doc, SHELL_IDS.progress);
  const progressStage = requireElement(doc, SHELL_IDS.progressStage);
  const progressPct = requireElement(doc, SHELL_IDS.progressPct);
  const progressBar = requireElement(doc, SHELL_IDS.progressBar);

  let lastResult: ConvertResult | null = null;
  let converting = false;
  let disposed = false;
  let intakeRevision = 0;
  let longRunTimer: ReturnType<typeof setTimeout> | undefined;
  const resultPanel = doc.getElementById("result");
  const previewStatus = doc.getElementById("preview-status");

  /* -- progress bar (driven by the worker's staged events) ----------------- */
  const setProgress = (stage: ProgressUpdate["stage"], pct: number): void => {
    progress.setAttribute("data-active", "true");
    progressStage.textContent = STAGE_LABELS[stage] ?? stage;
    progressPct.textContent = `${Math.round(pct)}%`;
    progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  };
  const hideProgress = (): void => {
    progress.setAttribute("data-active", "false");
  };
  const onProgress: ProgressListener = (event) => setProgress(event.stage, event.pct);
  const unsubscribe = client.onProgress(onProgress);

  /* -- conversion flow ----------------------------------------------------- */
  const live = new LiveConversion({
    convert: (request) => client.convert(request),
    getConfig: () => settings.toConfig(),
    onInvalidate: () => {
      lastResult = null;
      download.reset();
      resultPanel?.setAttribute("aria-busy", "true");
      if (previewStatus) previewStatus.textContent = "Updating your SVG preview…";
    },
    onStart: () => {
      converting = true;
      clearAllErrorSurfaces({ document: doc, container: messages.container });
      setProgress("segment", 0);
      longRunTimer = setTimeout(() => {
        renderLongRunNotice(
          { onCancel: () => {
            live.cancel();
            client.dispose();
            resultPanel?.setAttribute("aria-busy", "false");
            if (previewStatus) previewStatus.textContent = "Conversion cancelled. Adjust a setting or choose another image to try again.";
          } },
          { document: doc, container: messages.container },
        );
      }, LONG_RUN_THRESHOLD_MS);
    },
    onResult: (result, source) => {
      lastResult = result;
      preview.render(result, { imageBytes: source.imageBytes, filename: source.filename });
      download.setResult(result, source.filename);
      messages.showResultWarnings(result);
      resultPanel?.setAttribute("aria-busy", "false");
      if (previewStatus) previewStatus.textContent = "Preview ready. Download your layered SVG, or adjust the settings to update it.";
    },
    onError: (err) => {
      const error = err instanceof PlateClientError ? err
        : new PlateClientError(err instanceof Error ? err.message : String(err));
      renderClientError(error, { document: doc, container: messages.container });
      resultPanel?.setAttribute("aria-busy", "false");
      if (previewStatus) previewStatus.textContent = "The preview could not be updated. Adjust a setting or choose another image to try again.";
    },
    onSettled: () => {
      clearTimeout(longRunTimer);
      converting = false;
      hideProgress();
    },
  });
  const unsubscribeSettings = settings.onChange(() => live.settingsChanged());

  /* -- intake wiring (drag-drop + file picker) ----------------------------- */
  const handleFile = async (file: FileLike, revision = ++intakeRevision): Promise<void> => {
    const result = await validateFile(file);
    if (disposed || revision !== intakeRevision) return;
    if (result.ok) {
      live.setImage(result);
    } else {
      renderClientError(new PlateClientError(result.message, { recoverable: true }),
        { document: doc, container: messages.container });
    }
  };

  const onDrop = (event: DragEvent): void => {
    event.preventDefault();
    dropZone.setAttribute("data-dragover", "false");
    const file = event.dataTransfer?.files?.[0];
    if (file) void handleFile(file);
  };
  const onDragOver = (event: DragEvent): void => {
    event.preventDefault();
    dropZone.setAttribute("data-dragover", "true");
  };
  const onDragLeave = (): void => dropZone.setAttribute("data-dragover", "false");
  const onClick = (): void => fileInput.click();
  const onKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  };
  const onFileChange = (): void => {
    const file = fileInput.files?.[0];
    if (file) void handleFile(file);
    // Reset so selecting the same file again re-fires change.
    fileInput.value = "";
  };

  const exampleButton = doc.getElementById("try-example") as HTMLButtonElement | null;
  const onExample = async (): Promise<void> => {
    const revision = ++intakeRevision;
    if (exampleButton) exampleButton.disabled = true;
    try {
      const response = await fetch(new URL("./examples/badge.png", import.meta.url));
      if (!response.ok) throw new Error("The example could not be loaded. Please choose your own image.");
      const blob = await response.blob();
      if (!disposed && revision === intakeRevision) await handleFile(new File([blob], "example-badge.png", { type: "image/png" }), revision);
    } catch (err) {
      if (!disposed && revision === intakeRevision) renderClientError(new PlateClientError(err instanceof Error ? err.message : String(err),
        { recoverable: true }), { document: doc, container: messages.container });
    } finally {
      if (exampleButton && !disposed) exampleButton.disabled = false;
    }
  };
  const onExampleClick = (): void => { void onExample(); };

  // A hard platform miss leaves intake disabled (the notice already shows why).
  if (platform.supported) {
    chooseImageButton?.addEventListener("click", onClick);
    exampleButton?.addEventListener("click", onExampleClick);
    dropZone.addEventListener("drop", onDrop as EventListener);
    dropZone.addEventListener("dragover", onDragOver as EventListener);
    dropZone.addEventListener("dragleave", onDragLeave as EventListener);
    dropZone.addEventListener("click", onClick);
    dropZone.addEventListener("keydown", onKeydown as EventListener);
    fileInput.addEventListener("change", onFileChange);
    // Warm the runtime up front so the first conversion is faster; a bring-up
    // failure surfaces as a non-recoverable runtime error.
    client.init().then(() => {
      if (!disposed && !converting) hideProgress();
    }).catch((err: unknown) => {
      if (disposed) return;
      const e = err instanceof PlateClientError
        ? err
        : new PlateClientError(err instanceof Error ? err.message : String(err));
      renderClientError(e, { document: doc, container: messages.container });
    });
  }

  return {
    client,
    settings,
    preview,
    lastResult: () => lastResult,
    dispose: () => {
      disposed = true;
      live.dispose();
      unsubscribeSettings();
      clearTimeout(longRunTimer);
      unsubscribe();
      dropZone.removeEventListener("drop", onDrop as EventListener);
      dropZone.removeEventListener("dragover", onDragOver as EventListener);
      dropZone.removeEventListener("dragleave", onDragLeave as EventListener);
      dropZone.removeEventListener("click", onClick);
      dropZone.removeEventListener("keydown", onKeydown as EventListener);
      fileInput.removeEventListener("change", onFileChange);
      exampleButton?.removeEventListener("click", onExampleClick);
      chooseImageButton?.removeEventListener("click", onClick);
      preview.dispose();
      download.dispose();
      client.dispose();
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Auto-start when loaded as the page's module (browser only).                */
/* -------------------------------------------------------------------------- */

/**
 * In the browser, mount the app once the DOM is ready. Guarded so importing
 * this module under Node (tests) does not try to touch a DOM. The mounted app
 * is exposed on `window.__plateApp` so the headless smoke test can read the
 * last conversion result straight off the page.
 */
if (typeof document !== "undefined" && typeof window !== "undefined") {
  const start = (): void => {
    const app = mountApp();
    (window as unknown as { __plateApp?: MountedApp }).__plateApp = app;
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
}
