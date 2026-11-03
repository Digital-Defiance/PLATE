/**
 * Power-user links + beta label wiring for the Browser_Shell (main thread;
 * design Component 1 / Phase 4 "Polish": "links to the CLI (for batch) and to
 * LM Studio naming (for power users)").
 *
 * The web page is a thin shell: batch work and the optional LM Studio naming
 * step stay with the CLI. For power users the shell can offer two outbound
 * links back to those CLI capabilities. Whether to show them is an explicit
 * owner decision (Requirement 13.4 / 13.5):
 *   - 13.4 WHERE the owner decides to show power-user links, the shell displays
 *          a link to the CLI for batch work and a link to LM Studio naming.
 *   - 13.5 WHERE the owner has not decided to show power-user links, the shell
 *          omits BOTH the CLI batch-work link and the LM Studio naming link.
 * So the two links are all-or-nothing: either both render or neither does.
 *
 * The visible "beta" label is a separate, always-on element (Requirement 13.1:
 * the page is labelled "beta" in a visible page element). The static shell
 * (`web/index.html`, task 6.1) already carries `<span class="beta-badge"
 * id="beta-badge">beta</span>` in the header, so this module does NOT create a
 * second badge. Instead {@link ensureBetaLabel} confirms the static badge is
 * present and visible (and, only as a fallback for a shell that lacks it,
 * injects one) so 13.1 holds regardless of how the shell is assembled.
 *
 * Design decisions that matter:
 *   - Plain DOM, no framework; `document` is injectable so the branches can be
 *     exercised in Node without a real browser (mirrors `settings.ts`).
 *   - Pure where it can be: {@link renderPowerUserLinks} takes a container and
 *     `{ enabled }`, clears the container, and renders both links or nothing.
 *     It returns the rendered anchors (or an empty array) so a test can assert
 *     the enabled/omitted branches directly.
 *   - Link targets are the repo's real references, not invented URLs. Batch
 *     work points at the CLI usage docs in the repo README; LM Studio naming
 *     points at the same README (the project's own LM Studio naming
 *     documentation), never a guessed third-party endpoint. The repo homepage
 *     is pinned from `pyproject.toml` (`[project.urls] Homepage`).
 *
 * Power-user links default to OMITTED (Requirement 13.5): the owner has not, by
 * default, decided to show them, and the optional LM Studio naming path is
 * off-by-default throughout the design. The beta label defaults to VISIBLE.
 */

/** The repo homepage, pinned from `pyproject.toml` `[project.urls] Homepage`. */
export const REPO_HOME = "https://github.com/Digital-Defiance/PLATE";

/**
 * Link back to the CLI for batch work. The repo README's "Use" section
 * documents the `plate` CLI (per-image `plate trace`, batch, `plate sweep`,
 * `plate bench`) — the tool that stays the home for batch conversion.
 */
export const CLI_BATCH_URL = `${REPO_HOME}#use`;

/**
 * Link to LM Studio naming. No third-party URL is specified for naming, so this
 * points at the project's own LM Studio naming documentation (the README "Use"
 * section's `--vlm-url http://localhost:1234/v1` example), not a guessed
 * external site.
 */
export const LM_STUDIO_NAMING_URL = `${REPO_HOME}#use`;

/** The id of the container the shell reserves for the power-user links. */
export const LINKS_CONTAINER_ID = "power-user-links";

/** The id of the always-visible beta label in the shell header. */
export const BETA_LABEL_ID = "beta-badge";

/**
 * One power-user link's static definition: where it points, the visible text,
 * an accessible label, and a stable id/rel so the shell and tests can find it.
 */
export interface LinkSpec {
  readonly id: string;
  readonly href: string;
  readonly text: string;
  /** `aria-label` / `title`, giving the link fuller context than its text. */
  readonly label: string;
}

/**
 * The two power-user links, in render order: CLI batch work first, then LM
 * Studio naming (Requirement 13.4 lists them in that order). Both render
 * together or not at all.
 */
export const POWER_USER_LINKS: readonly LinkSpec[] = [
  {
    id: "link-cli-batch",
    href: CLI_BATCH_URL,
    text: "Use the CLI for batch work",
    label: "PLATE command-line tool for batch conversion (opens the repository)",
  },
  {
    id: "link-lm-studio",
    href: LM_STUDIO_NAMING_URL,
    text: "LM Studio naming",
    label: "Optional local LM Studio naming via the PLATE CLI (opens the repository)",
  },
] as const;

/** Resolve a usable `document`, erroring clearly in a non-DOM environment. */
function resolveDocument(doc?: Document): Document {
  const resolved = doc ?? globalThis.document;
  if (!resolved) {
    throw new Error(
      "links.ts needs a document; pass one explicitly in a non-DOM environment",
    );
  }
  return resolved;
}

/**
 * Confirm a visible "beta" label exists (Requirement 13.1). The static shell
 * already ships `#beta-badge`; this returns that element when present. Only as
 * a fallback — a shell assembled without the badge — does it create and attach
 * one so the page is never left unlabelled.
 *
 * @param options.document  DOM to use (defaults to the global `document`).
 * @param options.host      Where to attach a fallback badge if one must be
 *                          created; defaults to `document.body`.
 * @returns the beta label element (existing or freshly created).
 */
export function ensureBetaLabel(
  options: { document?: Document; host?: HTMLElement | null } = {},
): HTMLElement {
  const doc = resolveDocument(options.document);
  const existing = doc.getElementById(BETA_LABEL_ID);
  if (existing) return existing;

  // Fallback: the shell lacks the static badge, so inject one so 13.1 holds.
  const badge = doc.createElement("span");
  badge.id = BETA_LABEL_ID;
  badge.className = "beta-badge";
  badge.textContent = "beta";
  const host = options.host ?? doc.body;
  if (host) host.appendChild(badge);
  return badge;
}

/**
 * Render (or omit) the power-user links into `container`.
 *
 * Idempotent: the container is cleared first, so calling this again with a
 * different `enabled` flips cleanly between the two states without stacking
 * duplicates.
 *
 *   - `enabled: true`  -> renders the CLI batch link and the LM Studio naming
 *                         link (Requirement 13.4), returning both anchors.
 *   - `enabled: false` -> renders nothing and returns `[]` (Requirement 13.5).
 *
 * @returns the rendered `<a>` elements in order, or an empty array when omitted.
 */
export function renderPowerUserLinks(
  container: HTMLElement,
  options: { enabled: boolean; document?: Document },
): HTMLAnchorElement[] {
  const doc = resolveDocument(options.document);

  // Clear any previously rendered links so the state is authoritative.
  container.replaceChildren();
  container.setAttribute("data-enabled", String(options.enabled));

  if (!options.enabled) {
    // Requirement 13.5: omit BOTH links. Nothing is rendered.
    container.hidden = true;
    return [];
  }

  // Requirement 13.4: show the CLI batch link AND the LM Studio naming link.
  container.hidden = false;
  const anchors: HTMLAnchorElement[] = [];
  for (const spec of POWER_USER_LINKS) {
    const anchor = doc.createElement("a");
    anchor.id = spec.id;
    anchor.className = "power-user-link";
    anchor.href = spec.href;
    anchor.textContent = spec.text;
    anchor.setAttribute("aria-label", spec.label);
    anchor.title = spec.label;
    // External links open in a new tab; rel guards the opener for security.
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    container.appendChild(anchor);
    anchors.push(anchor);
  }
  return anchors;
}

/** Options for {@link mountShellLinks}. */
export interface ShellLinksOptions {
  /** Whether the owner enabled power-user links; defaults to `false` (13.5). */
  enabled?: boolean;
  /** Document used to resolve elements; defaults to the global `document`. */
  document?: Document;
  /** Container id for the power-user links; defaults to {@link LINKS_CONTAINER_ID}. */
  containerId?: string;
}

/** The handles {@link mountShellLinks} returns so the shell can re-render later. */
export interface ShellLinksHandles {
  /** The always-visible beta label (Requirement 13.1). */
  betaLabel: HTMLElement;
  /** The power-user links container. */
  container: HTMLElement;
  /** The rendered link anchors (empty when power-user links are omitted). */
  links: HTMLAnchorElement[];
  /** Re-render the links in a new enabled/omitted state. */
  setEnabled(enabled: boolean): HTMLAnchorElement[];
}

/**
 * Wire the shell's beta label and power-user links against `document`. Confirms
 * the beta label is present (13.1), finds (or creates) the links container, and
 * renders the links in the owner's chosen state (default omitted, 13.5). The
 * returned {@link ShellLinksHandles.setEnabled} lets the owner-decision toggle
 * flip the links on later without touching the DOM directly.
 */
export function mountShellLinks(
  options: ShellLinksOptions = {},
): ShellLinksHandles {
  const doc = resolveDocument(options.document);
  const enabled = options.enabled ?? false;
  const containerId = options.containerId ?? LINKS_CONTAINER_ID;

  const betaLabel = ensureBetaLabel({ document: doc });

  let container = doc.getElementById(containerId);
  if (!container) {
    // Fallback for a shell without the reserved container: create one next to
    // the beta label so the links sit in the header region.
    container = doc.createElement("nav");
    container.id = containerId;
    container.className = "power-user-links";
    container.setAttribute("aria-label", "Power-user links");
    const header = betaLabel.parentElement ?? doc.body;
    if (header) header.appendChild(container);
  }

  const links = renderPowerUserLinks(container as HTMLElement, {
    enabled,
    document: doc,
  });

  return {
    betaLabel,
    container: container as HTMLElement,
    links,
    setEnabled: (next: boolean) =>
      renderPowerUserLinks(container as HTMLElement, {
        enabled: next,
        document: doc,
      }),
  };
}
