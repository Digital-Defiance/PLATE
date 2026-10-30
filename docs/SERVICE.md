# PLATE as a donation-supported hosted service — design

Status: **DESIGN / NOT BUILT.** This records the agreed direction for turning PLATE
into a hosted PNG→SVG converter for Jessica's 501(c)(3), funded by optional recurring
donations. No service code exists yet. The PLATE engine (this repo) is unchanged and
remains the open-source MIT core; the service is a SEPARATE LAYER on top of it.

> **Compliance boundary (read first).** This doc describes software. Whether a recurring
> charge is a deductible donation, how donor receipts must read, and whether a
> donation-for-perks arrangement creates a "quid pro quo" (only the amount above the
> perk's fair value is deductible) are determinations for the nonprofit's tax/legal
> advisor — NOT for an engineer or an AI to decide. Build the system so the
> donation-vs-subscription FRAMING (labels, receipt wording, perk gating) is
> configuration, not architecture, so it can be finalized/changed after advisor review
> without a rewrite.

## Product shape (decided with Jessica)

- **Free tier:** **7 conversions per day** (daily reset), FULL quality — no watermark,
  no resolution cap. Rationale: casual users never hit it; a pro mid-project hits it and
  is nudged to support; "resets daily" feels generous. Daily beats monthly (a monthly cap
  walls the project user at the worst moment). The number is a config value — easy to
  raise later (raising delights, lowering angers), so start here and loosen if needed.
- **No-account instant demo:** 1–2 conversions with no sign-up, so people try before
  committing. The daily count applies once they have an account.
- **Supporter tier (recurring donation):** removes the daily limit; later adds batch/bulk,
  priority, and AI semantic naming. Framed as "supporters keep PLATE free for everyone and
  get these perks as thanks" — the tool is NOT locked behind payment. The real conversion
  levers are batch + AI as supporter perks, not a stingy free count.
- **AI naming is a LATER supporter perk, not in the launch.** It is cosmetic (names/groups,
  never geometry) and needs a vision model served somewhere — a recurring GPU/API cost. Gate
  it behind the supporter tier precisely because it carries compute cost; ship classical-only
  first so donation revenue exists before taking on that cost.

## Why the engine already fits this

- **Classical core runs anywhere, CPU-only, no GPU/model deps** → cheap, predictable hosting
  (critical for a nonprofit budget). A typical conversion is well under a second, so even a
  few thousand free conversions/day is cheap. The real cost lever is total CPU, not per-user
  count — hence affording a generous free tier.
- **AI is already optional and cleanly separated** (`vlm.py`, off unless `vlm_url` set,
  graceful fallback) → the AI perk tier is a config/routing concern, not new engine work.

## Architecture (proposed)

Keep the engine as the library; wrap it. Four parts:

1. **Engine** — this repo, imported as a library (`plate.pipeline.run`). Unchanged.
2. **Job queue + worker** — conversion is CPU-bound and must not block a web request. A
   worker process pulls upload jobs, runs `pipeline.run`, stores the SVG. (Even sub-second
   jobs benefit from a queue for backpressure/abuse control and concurrency.)
3. **API/web app** — upload endpoint, auth, usage metering (free vs supporter), Stripe
   webhooks, result download. Thin; delegates conversion to the worker.
4. **Frontend** — upload UI, before/after preview (the engine already has a report/render
   path), account + donation pages.

Containerize so hosting isn't locked in. The Python+opencv+cairo+vtracer stack is painful
on serverless (packaging, cold starts), so AVOID serverless/Lambda and usage-based
autoscaling billing (surprise costs are bad for a nonprofit). Prefer a flat, predictable box.

## Hosting (recommendation)

- **Recommended: a managed container platform (Render or Fly.io).** Flat, predictable,
  low-ops — a nonprofit usually has no one to babysit a VPS. Run the web app + a worker;
  cheap at low/bursty traffic.
- **Cheapest alternative: a single small VPS** (Hetzner/DigitalOcean, ~$5–12/mo) running
  web + worker + queue, if someone will patch and operate it.
- Containerize either way to avoid lock-in.

## Payments — Stripe (decided)

- The nonprofit is already on Stripe. Apply for Stripe's nonprofit discounted rate.
- Stripe bills a monthly recurring donation or a monthly subscription with nearly identical
  code — the difference is labels and receipt wording, which is the advisor-reviewed framing
  layer above. Build it framing-agnostic.
- Handle Stripe **webhooks** as the source of truth for entitlement (don't trust the client):
  on successful recurring charge → mark the account a supporter; on cancellation/failure →
  revert to free tier at period end.

## Accounts

- Start with **magic-link email or OAuth (Google/GitHub)** — less to build and, crucially,
  less to secure than storing passwords. Add password auth later only if needed.
- Store the minimum: an identifier, tier/entitlement state, and daily-usage counter.

## Security / abuse (REQUIREMENTS, not polish — a public upload service)

- Validate file type and MAGIC BYTES, not just extension; enforce a max upload size and max
  image dimensions before decoding (guard against decompression bombs).
- Treat every upload as untrusted input; run conversion in the isolated worker, not in the
  web process. Time-limit and memory-limit each job.
- Rate-limit by account AND by IP (the no-account demo especially). The daily free cap is a
  product limit, not a security control — keep a separate abuse rate limit.
- Strict per-user isolation of uploads/results; never let one account read another's files.
  Expire/delete stored uploads and results on a short schedule (storage cost + privacy).
- Don't log image contents or secrets; scrub filenames.

## Launch scope (recommended sequencing)

1. **Classical converter as the donation service** — free (7/day) + no-account demo +
   supporter tier (unlimited) via Stripe recurring donation. This is the whole value, it's
   cheap to run, and it de-risks launch (no GPU/API cost on day one).
2. **Then** add supporter perks that cost more to serve: batch/bulk, priority.
3. **Then** AI naming as a supporter perk, once donation revenue can cover the vision-model
   compute. Decide hosted-GPU vs paid-API at that point based on volume.

## Open decisions for Jessica (before building)

- Confirm the donation-vs-subscription framing + receipt wording WITH THE NONPROFIT ADVISOR.
- Pick hosting (Render vs Fly vs VPS) — affects deploy/CI setup.
- Confirm the free number (7/day assumed) and whether the no-account demo ships at launch.
- Confirm auth method (magic-link vs OAuth provider).

## Hard invariants to preserve (from prior sessions)

- PLATE engine stays the **open-source MIT classical core**; the service is a separate layer,
  not a fork. Do not close-source or entangle the engine with the web app.
- Engine stays **CPU-only, no GPU/heavy-ML deps** (see HANDOFF). The service hosting choice
  must not push GPU into the engine.
- AI stays **cosmetic and optional** in the engine; in the service it is a gated perk, never
  a requirement for a correct conversion.
