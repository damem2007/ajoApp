# Verification - v0.2 platform

Checked 2026-09-15; preview and PDF handoff checked again 2026-09-16.

- **26 tests passed** in the final regression run (63.76 seconds). Includes seven preserved original tests and nineteen platform/boundary tests.
- JavaScript syntax and Python compilation checks passed.
- Initial Alembic migration successfully applied to an isolated SQLite database; `alembic check` reported no pending schema changes.
- Dependency consistency: no broken requirements.
- Real HTTP smoke test against localhost: four fictional accounts authenticated; a weekly-contribution/monthly-payout circle recruited three members; the agreement was generated and accepted unanimously; 42 synthetic scheduled payments processed; the circle completed with zero pool balance and zero remaining obligation.
- Personal-data export succeeded over HTTP. Static app/JavaScript/CSS routes served successfully.
- The generated agreement has two pages. Both pages were visually inspected. Poppler had local font configuration issues on page two, so PDFium was used to confirm that the actual document has intact dates, layout and footer.
- Local health returns v0.2.0, sandbox=true, live_payments=false.

## Limits of verification

The v0.2 interface was served and syntax-checked but not interactively browser-tested because browser-control tools were unavailable in the final session. The prior v0.1 browser test does not validate the new interface. Native mobile installation, formal accessibility, PostgreSQL, Docker, CI execution, live providers, security/load testing and production operational readiness remain unverified.

Use the running app at http://127.0.0.1:8000/app. The app must be served through FastAPI; opening its HTML file directly is unsupported.


## Public experience — 2026-09-16

- Existing regression suite: 26 passed. New targeted tests: 5 passed (safe validation, stable QR setup, notification read/ownership permissions, public listing privacy, fixed cap on legacy overflow configuration).
- Node calculator checks passed for early/final payouts, decimal minor-unit arithmetic and invalid bounds. Both frontend scripts passed syntax checks.
- Restarted FastAPI on localhost:8000. HTTP checks passed for public root, authenticated app shell, assets, public listings and redacted validation.
- Interactive browser layout, QR scanning with a device, and touch swipe behavior remain unverified because browser-control tools were unavailable.


## Supplied marketplace UI adoption

31 backend regression tests pass. Marketplace category, frequency, amount, availability, saved-circle and sort checks pass. Browser verification now uses the bundled Playwright runtime with installed Chrome in a fresh headless session. Desktop/mobile, live empty-state and authenticated marketplace checks pass, including keyboard filter access, persistent device-local bookmarks, dark/reduced-motion modes and no page errors or horizontal mobile overflow. Card interaction screenshots use explicitly named QA fixtures via intercepted requests, without modifying application data. Public shell screenshot captures the actual local empty marketplace. Fonts are self-hosted and reference files are preserved under docs/design-reference/marketplace.

Screenshot-fidelity correction: browser tests now verify the actual public sandbox page displays the nine supplied illustrative cards when there are no real recruiting listings. Six dropdown filters and all eight frequency choices are checked. At the reference viewport/DPR, captures and visual inspection verify marketplace-first layout, original data order, card formatting and filter drawer. Preview eligibility opens an example-only explanation; calculator is accessible in a modal. Mobile bounds, keyboard closing, bookmarks and no page errors pass.

Landing/CMS checkpoint: 33 backend tests pass. CMS migration upgrade and Alembic drift checks pass on an isolated SQLite database. Fresh headless Chrome checks cover screenshot-based landing sections, calculator sliders and remaining obligations, all eight frequencies, currencies, marketplace navigation, mobile layout bounds, CMS field editing and saved-draft preview/save/publication using intercepted fixtures. Actual preview opens a same-origin blob window and loads the working calculator. Public content was not modified by UI tests. Desktop hero and lower sections visually reviewed against the six references.


### Next.js / FastAPI migration checks — 2026-09-17

33 existing backend regression tests pass after relocating the Python package to `backend/app/`. An additional redirect/API-boundary regression passes with the public-experience suite (6 tests). Alembic upgrade/check pass against an isolated database; no new upgrade operations are detected.

Frontend TypeScript checking and the Next.js production build pass. Headless Chrome checks cover landing sections, calculator math and frequency options, CMS draft/preview/publish using intercepted fixtures, public/member catalogue parity, join eligibility errors, notification deletion, KYC form, one-time MFA QR rendering and the fixed-capacity circle wizard. Existing workflow code is retained and split by feature; the whole client has not yet been rewritten into native React. No live sandbox financial records were modified during these checks. Separate Docker/Compose definitions are provided but have not been executed locally.
