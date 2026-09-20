# Requirements analysis and bootstrap boundary

Source: `/Users/damidahunsi/Downloads/esusu-ajo-app-requirements.md`, reviewed 2026-09-11.
The source was treated as product input. Its instructions to coding agents were not treated as user authorization for external actions or production launch.

## Assessment

The pack clearly describes a rotating obligation ledger, equal participant rights, membership-dependent proration, unanimous contracting, and independently scheduled debit/credit flows. It is a useful product baseline, but it is not yet an unambiguous executable financial specification.

### 1. Contribution frequencies conflict with the formula

FR-3.2's `T / M` is the total per-member funding requirement **per payout window**. When weekly debits fund a monthly payout, charging that amount every week overcollects. A proposed schedule model allocates a target across the members and then across the actual debit dates in each payout window. Four- and five-debit months need different installment allocations unless the product instead chooses a fixed installment model with explicit carry/reserve rules.

Required decisions: first debit and payout dates, scheme timezone, calendar anchor, month-end clipping, holiday/business-day handling, cutoffs, settlement delays, catch-up behavior, and what happens if a payout window contains no debit dates. “Bi-monthly” also needs an explicit meaning (twice monthly or every two months).

Bootstrap: matching frequencies only, manually advanced numbered periods, no due-date scheduler. Unsupported mixed frequencies return 422 rather than guessing a policy.

### 2. Overflow examples are financially underspecified

For M members collecting T once each, total contributions must equal `M × T`. Changing membership, duration, installment size, or payout size cannot be treated independently. Holding all but installment size fixed may not conserve funds. Minimum and planned count are also separate concepts but the proposed schema lacks an explicit minimum and hard cap.

Bootstrap: fixed membership, no overflow. Reaching planned count makes a scheme finalizable. Overflow is rejected until an approved conservation-preserving rule is supplied.

### 3. Rounding must conserve money and fairness

Use integer minor units, never binary float in the financial domain. For target 10,001 and three members, the first allocation is `[3334, 3334, 3333]`; the remainder recipients rotate each period. Each pool is exactly 10,001 and each member contributes exactly 10,001 over three periods.

Bootstrap policy: rotating remainder allocation, included explicitly in the hashed proposal before assent. Supported example currencies all use two decimal places. Currency exponent metadata and FX are future work; no cross-currency pooling is supported.

### 4. Signing and finalization have competing freeze boundaries

Section 2.2 mentions freezing once signed; FR-3.5 freezes when pending signatures begins. The latter is necessary to prevent members signing different obligations. Manual order authority also conflicts with equal participant write access unless changing the order is a proposal requiring unanimous assent.

Bootstrap: any member can propose an explicit payout permutation at finalization; all members must assent to the identical hash. No post-freeze mutation endpoint exists. Re-versioning, rejection/withdrawal, signature expiry, and recovery from an abandoned proposal remain to be specified. The simulated proposal is not a legal contract PDF.

### 5. Payment success is not necessarily settled funds

Provider acceptance, pending debit, settlement, return, refund, and reversal need separate immutable events. A retry must reuse provider idempotency identity. Payout eligibility depends on settled available funds minus reserved/in-flight payouts; a callback marked “success” alone is insufficient.

Bootstrap: one transaction writes synthetic settled contributions and a synthetic payout. This exercises allocation and replay invariants only. It does not model provider timing, failures, bank mandates, reversals, payout reservations, or real reconciliation.

### 6. Trust, complaints, and identity decisions need precision

The pack uses several complaint status vocabularies; one canonical transition table is needed. A facial hash is not an exact identity uniqueness key: biometric matching is probabilistic and belongs with the selected provider and review process. Device/IP signals should be risk flags rather than sufficient proof of duplicate identity. Inviter penalties and cap downgrades need explicit effective dates and rules for existing obligations.

Bootstrap: approved/pending fictional identities and a cap of one. Recruiting and pending-signature commitments reserve a slot, preventing a user joining many drafts before activation. This is a conservative proposed cap policy, not a finalized trust model.

## Coverage

| Requirement | Bootstrap implementation | Still required |
|---|---|---|
| FR-1 / FR-2 | Demo KYC gate, fixed pseudonyms | Registration, channel verification, OIDC/MFA, provider verification, duplicate review |
| FR-3 | Create/join, exact reproration, fixed count, manual order, freeze | Leave/cancel policies, private/premium access, invitations, overflow, random order proof |
| FR-4 | Hashed immutable proposal and unanimous simulated assent | Legal terms, verified signatures, PDF/versioned object storage, recovery/re-versioning |
| FR-5 | Synthetic settled ledger, remaining obligations, atomic period replay | Calendar engine, durable jobs, mandates, provider adapters, webhook inbox, reconciliation/returns |
| FR-6 | UI action feedback only | Durable notification outbox, channel adapters, preferences, delivery tracking |
| FR-7 | Fixed cap with reserved recruiting slots | Trust events, scoring policy, inviter attribution, downgrades |
| FR-8 | Not implemented | Complaints and audited operations workflows |
| FR-9 | Local circle list and creation UI | Eligible marketplace, search/filtering, private resources, production web application |
| FR-10 | Member-scoped lifecycle audit API | Staff RBAC, admin workflows, exports, kill switch, operational analytics |
| NFRs | Transaction boundaries and targeted invariant tests | Migrations, database-enforced append-only access, security hardening, accessibility audit, performance/availability testing |

The audit and ledger APIs expose no update/delete operations; database administrators can still edit records. They are not yet database-enforced tamper-proof stores. Auto-create tables is demo-only; it is not a migration strategy.

## Decisions to obtain before the next milestone

1. Launch country and currency, legal operating model, custody/payment provider, KYC provider and document set.
2. Calendar and mixed-frequency allocation policy; minimum, planned count and overflow semantics.
3. Fees, failed-debit grace/retry policy, payout shortfall handling, and who bears losses.
4. Manual/random ordering governance, random draw verification, and unsigned/abandoned contract recovery.
5. Privacy/access rules, retention, staff roles, canonical dispute statuses and trust penalty rules.

These decisions do not block this local bootstrap. The corresponding production behavior remains unimplemented rather than silently resolved.

## Delivery sequence

1. **Domain approval:** resolve the policy decisions; add calendar examples and property/invariant tests, including mixed-frequency and return scenarios.
2. **Identity/persistence:** PostgreSQL migrations and constraints, real authentication, channel verification, KYC adapters, authorization/privacy tests, encrypted document references and staff audit.
3. **Contracted recruitment:** invitations, departures, agreed ordering, contract versions, real signature provider and verified bank mandates.
4. **Payment sandbox:** durable workflow runner, transactional outbox/inbox, stable provider keys, signed webhook verification, settlement/reversal ledger, payout reservations, reconciliation and kill switch. Exercise duplicate, delayed and reordered callbacks.
5. **Operations and client:** notifications, disputes, trust, admin roles, Next.js member UI; mobile after the API stabilizes.
6. **Launch readiness:** jurisdiction/provider approval, security review, retention policy, backup restore drills, PostgreSQL concurrency/load testing, monitoring and incident exercises.
