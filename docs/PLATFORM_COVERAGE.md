# Platform coverage and remaining integration boundaries

Updated 2026-09-15. Source: `esusu-ajo-app-requirements.md`.

This is a substantial functional sandbox implementation, not an assertion that every production acceptance criterion has been met. External verification, regulated money movement, legal enforceability, native app-store distribution and availability targets cannot be established by local application code alone.

| Requirement area | Implemented in v0.2 | Remaining boundary |
|---|---|---|
| Registration and authentication | Email/phone registration, PBKDF2 password hashing, independent expiring OTPs, persistent attempt limits, short-lived bearer sessions, rotating refresh tokens, logout, TOTP MFA with replay protection | External OTP delivery adapter; production OIDC/passkeys/recovery are not implemented. Current sessions are opaque tokens, not JWTs. |
| KYC | Verified-channel upload gate, encrypted document/selfie storage, metadata capture, keyed duplicate-ID/device signals, reviewer decisions/reasons, unique permanent pseudonyms, notification outbox | Real OCR, liveness, biometric comparison, carrier/IP signals and provider-side bank-name matching need selected providers. Sandbox manual approval is explicitly labelled. |
| Circle configuration | Draft/publish, description/privacy/premium, hidden identities, minimum/planned/hard cap, contribution/collection frequencies, manual/random order, invite permissions, trust thresholds | Other currencies/timezones and alternate overflow strategies remain explicit policy extensions. |
| Recruitment | Public eligible marketplace, search/currency/frequency/amount API filters, direct invitations, hashed one-/multi-use codes, expiry, revocation, recipient binding, join/leave and reproration | Invitations produce a shareable code/link; the app does not send unsolicited messages to contacts. |
| Finalization | Close recruitment, manual permutation or committed random order, immutable versioned proposal, schedule and policy snapshot, unanimous typed sandbox assent, timestamp/IP/device audit, downloadable stored PDF and hashes | Real signature provider and jurisdiction-approved legal terms. PDF represents the immutable proposal; signature evidence is stored separately. |
| Contract revisions | Pre-activation withdrawal/re-versioning preserves all old agreements and signatures and requires new unanimous assent | Active-contract amendment/unwind policy remains gated. |
| Calendar | Daily, weekly, fortnightly, monthly, every-two-months, quarterly, half-yearly and yearly schedules; independent frequencies; month-end clipping; exact integer allocation in payout windows | UTC civil-date semantics are the available policy. Bank holidays, local cutoffs, settlement-day shifts, fixed-installment reserves and windows without contributions require additional policies. |
| Fees | Configurable zero-fee or separately collected flat-plus-basis-point contribution fees; separate fee accounts | Fee placement/subscription alternatives are not inferred. |
| Payments | Persistent scheduled obligations, worker/manual tick, retries with exponential day backoff, stable attempt keys, pending/failed/settled/reversed states, reservations for pending payouts, current-window funding checks | Provider-specific submission/webhooks and settlement statements are not connected. Worker currently executes only the sandbox adapter. No real payments are enabled. |
| Ledger | Balanced signed postings per event, contribution/collection/fee totals, remaining obligations, distinct net positions, append-only SQL guards, reversal entries, CSV export, replay checks | Full custodial accounting, settlement-return recovery and production database-role controls require integration and operational sign-off. |
| Delinquency | Failed attempts, frozen retry/grace policy, trust penalty, inviter factor, delinquent flag, payout hold and disputed state | Removal, reserve/insurance absorption, default recovery and funded cancellation remain unresolved policies. No automatic debt forgiveness. |
| Notifications | In-app inbox/read state, email/SMS/push outbox, preferences, templates, reminder keys, delivery statuses, bounded attempts and staff resend | Real email/SMS/FCM/APNs adapters and credentials. Sandbox does not transmit messages. |
| Trust and limits | Trust event history, completion points, default/resolved-report penalties, inviter penalty factor, configurable score/cap tiers, reasoned admin overrides | Inviter time decay and tier-specific maximum amounts are not implemented. Existing obligations survive cap downgrades. |
| Complaints | Report circle/member, category/description, canonical review transitions, assignment API, evidence bundle, resolved penalty, status notifications and SLA indicator | Messaging attachments and richer investigative case tooling are future extensions. |
| Administration | Account search, suspension, role management/session revocation, KYC evidence/review, circle state/curation, payment reconciliation/retry, policies, notification delivery, audit, metrics, CSV and scheduler kill switch | Production staff access requires MFA; detailed cohort analytics, platform-wide reconciliation imports and external alerting remain work. |
| Data rights | Member data export, export/deletion request queue and retention decision records | Destructive deletion is deliberately not performed without a retention/unwind policy. No request is falsely marked fulfilled. |
| Client | Working member and operations web screens, responsive layout, installable mobile-web manifest, no offline caching of financial/identity data | Native React Native/Flutter builds and app-store release are not included. Formal accessibility and mobile install verification remain pending. |
| Infrastructure | Docker application, optional worker profile, SQLAlchemy PostgreSQL support, Alembic initial migration, test CI, request IDs, latency logs, health/readiness routes | PostgreSQL/Docker execution, cloud IaC deployment, backups, centralized telemetry, load/security audits and the 99.9% availability objective remain unverified. |

## Open questions are policy, not hidden assumptions

`PolicyInput` provides versioned launch countries, currencies, ID types, terms/legal approval, calendar and mixed-frequency strategies, overflow/random/default policies, fees, retry/grace rules, trust tiers, notifications, retention and incident pause controls. Unresolved strategy values can remain `null`; finalization rejects missing required policies. Sandbox initialization supplies clearly identified example values to exercise workflows.

Each agreement stores its complete policy version and schedule. Later policy edits do not rewrite signed obligations. The scheduler pause is intentionally global and immediate.

Current overflow policy is `extend_rotation`: M finalized members each collect the target once over M payout windows; their per-window share decreases with M. This preserves total funding of M × target. The alternative description “same duration, smaller share, bigger pool” is not mathematically complete enough to implement without further decisions.

Server-commitment randomness is reproducible from the published seed and member IDs. It does not prove the server selected its original seed without bias; a future independent beacon/commit-reveal provider can replace that policy.

## Safe operating boundary

Use fictional data in sandbox mode. The sandbox supplies manual KYC approval, self-verified sandbox bank tokens, typed sandbox assent and synthetic settlements. These are developer exercises, not production financial services. Do not expose sandbox mode on a public interface. Live adapters deliberately fail closed.
