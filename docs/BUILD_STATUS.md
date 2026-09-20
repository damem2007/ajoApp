## Native architecture and environment follow-up

Every active screen uses TSX and named typed API resources. Legacy frontend controllers and backend HTML/static renderers are retired and archived outside production serving. Database/API addresses and runtime preferences are validated environment settings without URL fallbacks. PostgreSQL connectivity and migration head are verified. All 43 Python regression tests pass. See [architecture](ARCHITECTURE.md), [configuration](CONFIGURATION.md) and [latest checkpoint](NATIVE_FRONTEND_CHECKPOINT.md).

The sections below record earlier delivery stages.

## 2026-09-17 native frontend checkpoint

The approved Next.js migration now uses native member and backoffice routes, shared session/toast providers, and named typed API resources. CMS is a backoffice submodule. New cycles accept fixed per-member contributions and derive funded payouts from actual calendar dates. All 38 Python tests and four production browser suites pass. Historical signed contracts remain untouched. See [native checkpoint](NATIVE_FRONTEND_CHECKPOINT.md) for the compatibility-handler cleanup blocked by automatic approval review.

# Current checkpoint - 2026-09-16

Workspace moved to `/Users/damidahunsi/Projects/Ajo`. The original workspace path in the task metadata is stale.

Implemented and connected the v0.2 platform: account/OTP/MFA, encrypted identity submission and staff review, sandbox bank mandates, circle configuration/recruitment/invitations/privacy, independent calendar schedules, versioned PDF agreements and unanimous sandbox assent, durable due processing, balanced append-only ledger/reversals, notification outbox/preferences, trust/limits, complaints, staff administration, policy versions and member/admin web client.

Verification: 26 tests passing; JavaScript syntax checks passing; initial Alembic migration applied to an isolated database and `alembic check` reports no drift. Local HTTP health returns v0.2.0 with sandbox=true and live_payments=false.

Production/provider-dependent criteria remain unfulfilled, explicitly itemized in PLATFORM_COVERAGE.md. Do not describe this as production-ready or claim native mobile distribution, actual OCR/liveness, real settlements, or delivered external messages. No cloud deployment was made.

Final handoff checks completed: 42-payment HTTP smoke rotation, health/static routes, personal export and both agreement pages verified. Preview restarted on localhost:8000. Fictional member/admin sign-in details are in .ajo-data/demo-access.txt (restricted permissions, ignored by Git). Subsequent development should address PLATFORM_COVERAGE.md rather than restart the bootstrap.


## Public experience checkpoint — 2026-09-16

Root `/` now serves the public landing page and searchable marketplace. Anonymous listings contain aggregate circle information only, exclude private/premium/full circles, and explain that joining is subject to authenticated eligibility. Filters cover currency, payout amount, frequency, payout rounds and remaining slots. The calculator displays payout, contributions by turn, and contributions still owed afterward.

The app remains at `/app`; registration supports `?view=register`. Added descriptive dismissible toasts, safe validation responses with field guidance, QR enrollment that reuses the pending MFA secret, a top-right notification bell patterned after stockData’s header, owner-only deletion of read notifications via ellipsis or right swipe, and a four-step circle wizard. Dismissed notifications retain their deduplication record. Circle joins enforce planned membership even for older overflow configurations; new overflow configurations are rejected.

Verification: existing 26 tests passed; five focused public-experience tests and calculator boundary checks added. No interactive browser verification was available in this session. Live-provider and production limitations above continue to apply.

Frequency consistency: added shared requirements vocabulary (all eight frequencies) for public calculator, public/authenticated marketplace filters and circle setup. Calculator wording uses payout round and selected frequency for all cadences. Generated visual review mockup saved at output/design/marketplace-v1.png; its sample listings are illustrative and it is not a browser screenshot. Served HTML frequency options and scripts verified over HTTP.


## Adopted marketplace design — 2026-09-16

Adopted the supplied `files (4).zip` design in the public and authenticated marketplaces. Source preserved under docs/design-reference/marketplace. Ported CSS module classes with a prefix and shared UI logic into the existing FastAPI static frontend; no Next.js service or React dependency introduced. Bundled Fraunces/Inter fonts locally with their OFL licenses.

Implemented live search, circle categories, collapsible advanced filters, applied filter counts, sorting, device-local saved circles, real loading skeletons, empty/retry states and member-slot rings. Added an optional/defaulted category to CircleInput (stored in the existing config JSON; no database schema change) and category selection to the circle wizard. All eight frequencies and GBP support remain available. Public listings expose public IDs and aggregate config, not legal identities. Recruiting cards show next payout as after agreement; sorting by planned start uses declared start dates and does not claim guaranteed payouts. Example data and fabricated trust/urgency timing from the ZIP are not treated as real listings.

Verification: 31 pytest tests passed, marketplace pure filter/sort checks passed, JavaScript syntax checks passed. Fresh headless Chrome/Playwright checks passed for public and signed-in components, desktop/mobile layout, all eight frequencies, categories, draft/applied filters, sorting, persistent bookmarks, keyboard filter closing, dark/reduced-motion modes and no page errors/horizontal mobile overflow. Live empty-state screenshot and screenshots with intercepted QA listings saved under output/design/marketplace-adopted-*.png. No financial or identity data mutated during browser checks. Local preview running at localhost:8000.


## Screenshot-fidelity correction — 2026-09-16

Supersedes the previous visual-adoption checkpoint: the public root is now marketplace-first, without the old hero/how-it-works sections above it. Calculator remains accessible through the top navigation in a keyboard-accessible dialog. Rebased marketplace CSS on the separately attached source, preserving supplied typography, spacing, six dropdown fields, card layout, whole-currency amount formatting and the six original category chips.

When the sandbox has no public recruiting circles, it displays the nine exact supplied design examples in source order. All example cards are marked by the supplied illustrative UI-mockup disclaimer, and Check eligibility opens an example explanation rather than a join request. Real public listings replace this fallback when present. The example fallback is disabled outside sandbox mode. Authenticated listings continue to use real eligible circles. Source payout-day and organizer labels are used only for illustrative examples; real unscheduled payouts remain pending.

Browser verified at 1257x752 with device scale 2 to capture at the attached screenshot dimensions: nine supplied cards/order, marketplace near top, six dropdown filters, all eight frequencies, category/filter/sort/bookmark interactions, calculator/example dialogs, mobile drawer access, Escape closing and no horizontal overflow or page errors. Compared desktop screenshot visually and corrected inherited sort-label margins and header spacing. Final captures: output/design/marketplace-reference-matched.png, marketplace-reference-filters.png, marketplace-reference-mobile.png. No backend/financial data changed in this correction.


## Landing page and CMS checkpoint — 2026-09-16

Built the six supplied landing-page screens at `/`: hero with an SVG savings-circle calculator and three sliders, sage how-it-works section, written safeguards panel, three compact circle previews, FAQ accordion, green closing CTA and footer. Full marketplace remains at `/marketplace`. All eight frequency options and four illustrative currencies are available in the calculator’s extra controls; obligation-after-payout remains visible there. Editorial copy follows the screens while accurately describing the sandbox’s external-delivery and live-payment limitations.

Added a first-party structured CMS with server-rendered, escaped published content; admin/ops field editing, saved-draft preview, admin-only publication/restoration, immutable revision history through the API, audit events and optimistic conflict checks. Terms/privacy draft text is also editable and served via footer routes. No raw HTML editing or uncontrolled external links. Database migration 7bb13c20a6f9 tested on an isolated database; Alembic check reports no drift. Staff workflow documented in docs/CMS.md.

Verification: 33 backend tests pass, including CMS draft isolation, permission checks, publication, stale edits/publications, rollback, audit history and safe rendering. Browser checks pass for six sections, slider arithmetic/clamping, frequency/currency changes, marketplace navigation, mobile overflow bounds, dark/reduced-motion, and CMS edit/save/preview/publish controls using intercepted test fixtures. No live editorial revisions were changed by browser verification. Desktop/mobile landing and CMS-editor captures saved under output/design/landing-cms-*.png and content-editor-qa.png. Desktop sections visually inspected against supplied screenshots. Local sandbox running on localhost:8000.


## Next.js / FastAPI separation — 2026-09-17

- Next.js App Router and React client added under `frontend/`; FastAPI domain package moved under `backend/app/`. Root `app` is a compatibility symlink for existing tests/scripts.
- Native React landing page, calculator, shared marketplace, legal pages and back-office CMS. Both marketplace views load the public catalogue; eligibility is enforced by the FastAPI join action. Sandbox examples appear consistently and never join.
- All existing sandbox member and operations workflows retained through a frontend-owned compatibility controller boundary. These controllers are not yet fully rewritten as native React components. This deliberate boundary preserves contracts, KYC, MFA, bank mandates, trust, reports, notifications and operational actions.
- Runtime same-origin API proxy supports authenticated JSON, uploads and downloads. PWA manifest and no-cache service worker retained.
- Separate Dockerfiles/Compose services and frontend CI build/typecheck added. Docker execution remains unverified locally because Docker is unavailable.
- Existing backend regression suite passes (33 tests) after the move. React browser checks cover published landing page, calculator, CMS save/publish/preview, catalogue parity, eligibility failure, notification deletion, KYC form, one-time MFA QR setup and fixed-capacity circle wizard. Browser writes use intercepted fixtures, never live sandbox accounts.
