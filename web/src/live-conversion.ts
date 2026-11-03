/** Keep one selected image and serialize debounced, latest-settings conversions. */
import type { IntakeAccepted } from "./intake.js";
import { toConvertRequest } from "./intake.js";
import type { ConvertRequest, ConvertResult, PlateConfig } from "./protocol.js";

export const SETTINGS_DEBOUNCE_MS = 350;

export interface LiveConversionOptions {
  convert(request: ConvertRequest): Promise<ConvertResult>;
  getConfig(): PlateConfig;
  onInvalidate(): void;
  onStart(): void;
  onResult(result: ConvertResult, source: IntakeAccepted): void;
  onError(error: unknown): void;
  onSettled(): void;
}

export class LiveConversion {
  private source: IntakeAccepted | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private revision = 0;
  private running = false;
  private ready = false;
  private disposed = false;

  constructor(private readonly options: LiveConversionOptions) {}

  setImage(source: IntakeAccepted): void {
    if (this.disposed) return;
    this.source = source;
    this.schedule(0);
  }

  settingsChanged(): void {
    if (!this.disposed && this.source) this.schedule(SETTINGS_DEBOUNCE_MS);
  }

  cancel(): void {
    clearTimeout(this.timer);
    this.ready = false;
    this.revision++;
  }

  dispose(): void {
    this.disposed = true;
    clearTimeout(this.timer);
    this.source = null;
    this.ready = false;
    this.revision++;
  }

  private schedule(delay: number): void {
    this.revision++;
    clearTimeout(this.timer);
    this.ready = false;
    // Disable downloads immediately, including during the debounce window.
    this.options.onInvalidate();
    if (delay === 0) {
      this.ready = true;
      void this.drain();
    } else {
      this.timer = setTimeout(() => {
        this.timer = undefined;
        this.ready = true;
        void this.drain();
      }, delay);
    }
  }

  private async drain(): Promise<void> {
    if (this.disposed || this.running || !this.ready || !this.source) return;
    const source = this.source;
    const revision = this.revision;
    this.ready = false;
    this.running = true;
    this.options.onStart();
    try {
      // PlateClient transfers/detaches request bytes; retain the original for
      // future settings changes and the source preview. Only one request runs.
      const request = toConvertRequest(
        { ...source, imageBytes: source.imageBytes.slice() },
        this.options.getConfig(),
      );
      const result = await this.options.convert(request);
      if (!this.disposed && revision === this.revision) this.options.onResult(result, source);
    } catch (error) {
      if (!this.disposed && revision === this.revision) this.options.onError(error);
    } finally {
      this.running = false;
      if (!this.disposed) {
        this.options.onSettled();
        void this.drain();
      }
    }
  }
}
