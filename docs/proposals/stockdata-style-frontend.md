# Ajo frontend architecture — approved implementation

Status: approved by the user and implemented as native routed React screens with typed API resources. Sandbox regression suite: 43 passing tests. The comparisons below record the original migration baseline. Backend HTML/static handlers have been retired after verification; legacy UI sources are archived outside production serving.

## What exists now and why

The preceding change was a staged migration, not a complete conversion to StockData's architecture. It placed the frontend in Next.js and preserved the sandbox screens through JavaScript controllers to avoid losing functionality. The result still has two rendering models and duplicated request/session handling. Keeping that as the final architecture would make maintenance harder.

The landing page, calculator, marketplace, legal pages and CMS already have React components in `frontend/src/components/`. Public and signed-in marketplaces use `/api/v1/public/marketplace`. However, `/app` is one React shell that loads `frontend/public/assets/workspace/*.js`. Those controllers build DOM elements, switch screens and call endpoints themselves. Remaining screens do not have independent Next.js routes or typed resource services.

The compatibility templates are physically under `frontend/public/assets/`, not embedded in the Python domain package. Nevertheless, FastAPI still renders published home/CMS-preview/legal HTML and serves compatibility templates in `backend/app/platform/cms.py` and `application.py`. Moving template files to a frontend folder did not remove this backend rendering responsibility. The current sandbox redirects normal public/UI requests to Next.js, but the old rendering path still exists, including the authenticated CMS HTML preview.

## Comparison with the actual StockData project

Inspected source: `/Users/damidahunsi/Projects/stockData/frontend/src/`.

| Concern | Current Ajo | StockData | Proposed Ajo |
| --- | --- | --- | --- |
| Pages | Native public routes; one `/app` shell for remaining screens | App Router route groups and resource/detail routes | Public, member and back-office route groups; one route per feature |
| Navigation | Legacy screen switcher and query parameters inside workspace | Next.js pages/layouts and navigation components | Next.js links/router; compatibility redirects for old URLs |
| Requests | Generic `api.ts`, direct fetches and controller-owned API helper | Typed `apiFetch<T>`, endpoint functions in `lib/api.ts`, shared `types.ts` | One typed transport and domain resource modules under `lib/api/` |
| Session | Controller globals/session storage plus a second React helper | `SessionProvider`, token utilities and `AuthGuard` | One session provider with Ajo refresh-token behavior and server-enforced RBAC |
| Feedback | Controller toast plus component-local errors | `ToastProvider`, `ToastStack`, shared feedback components | Shared toast/field errors/loading/empty states |
| UI ownership | React plus imperative DOM controllers and FastAPI HTML rendering | React feature components under routed pages | React exclusively; FastAPI returns data and domain-generated documents |
| API origin | Next.js same-origin proxy | Configured `API_BASE_URL` in the browser | Keep Ajo's same-origin proxy with a runtime backend origin |
| Back office | Legacy module buttons; React CMS mounted inside them | Shared workspace composition pattern | Staff layout, role gates and routed modules; CMS remains a submodule |

Adopt StockData's application structure rather than its trading-specific providers or API schemas. Retain the same-origin Ajo proxy: browser requests use `/api/v1`, and only the Next.js server needs the backend address. StockData currently uses a configured browser API origin; copying that networking choice is not necessary to adopt its route/component/service architecture.

## Proposed directory and route layout

```text
frontend/src/
  app/
    (public)/
      page.tsx                     # /
      marketplace/page.tsx
      sign-in/page.tsx
      register/page.tsx
      verify/page.tsx
      terms/page.tsx
      privacy/page.tsx
    (member)/
      layout.tsx                   # session + member guard + app chrome
      app/circles/page.tsx
      app/circles/new/page.tsx
      app/circles/[circleId]/page.tsx
      app/invitations/page.tsx
      app/account/page.tsx
      app/account/security/page.tsx
      app/notifications/page.tsx
      app/trust/page.tsx
      app/reports/page.tsx
    (staff)/
      backoffice/layout.tsx         # staff guard + back-office navigation
      backoffice/page.tsx           # overview
      backoffice/users/page.tsx
      backoffice/kyc/page.tsx
      backoffice/circles/page.tsx
      backoffice/payments/page.tsx
      backoffice/complaints/page.tsx
      backoffice/policies/page.tsx
      backoffice/jobs/page.tsx
      backoffice/deliveries/page.tsx
      backoffice/data-requests/page.tsx
      backoffice/audit/page.tsx
      backoffice/cms/page.tsx
      backoffice/cms/preview/page.tsx
    api/[...path]/route.ts          # transparent FastAPI proxy
  components/
    navigation/                    # header, notification bell, guards
    circles/                       # wizard, detail, schedule, agreement
    account/                       # KYC, banks, MFA, verification, privacy
    notifications/
    backoffice/                    # routed administrative modules
    cms/                           # editor + published/draft renderer
    ui/                            # forms, field errors, toast, dialog, tables
  providers/
    session-provider.tsx
    toast-provider.tsx
    notification-provider.tsx
  lib/
    types.ts
    frequencies.ts
    money.ts
    api/
      client.ts                    # typed JSON/FormData/blob transport
      auth.ts
      circles.ts
      contracts.ts
      kyc.ts
      banks.ts
      notifications.ts
      trust.ts
      complaints.ts
      admin.ts
      cms.ts
```

Route groups organize source without adding `(member)` or `(staff)` to URLs. `/app` redirects to `/app/circles`. Old `?view=...` URLs resolve to their canonical routes; `/app?view=backoffice&module=cms` resolves to `/backoffice/cms`. Deep links remain usable.

## Responsibilities and API resource contract

Pages compose components; they do not contain raw endpoint strings or construct domain schedules. Components use named, typed service functions. One transport handles authorization, refresh coordination, safe error conversion, uploads, downloads, cancellation and HTTP responses without JSON bodies. Ajo's refresh-token revocation and MFA behavior are retained rather than replaced with StockData's token-expiry strategy.

Examples of proposed service interfaces (not implemented): `listPublicCircles()`, `getCircle(id)`, `createCircle(input)`, `finalizeCircle(id, order)`, `getAgreement(id)`, `downloadAgreement(id)`, `submitKyc(input)`, `linkBank(input)`, `setupMfa()`, `listNotifications()`, `deleteReadNotification(id)`, `getCmsDraft()`, `saveCmsDraft(input)`, `publishCmsDraft(input)`.

Type responses explicitly. Monetary amounts remain integer minor units; calendar dates remain UTC civil dates. The shared catalogue is independent of join eligibility. Join calls retain FastAPI validation for KYC, mandates, trust, commitments and circle capacity.

FastAPI retains authentication, KYC/document authorization, schedules, agreements/PDFs, signatures, bank mandates, ledger/payment state, workers, trust, notifications, complaints, policies, administrative permissions, audit history and CMS data/publication. Next.js owns all page HTML, including legal pages and CMS draft previews. Backend-generated contract PDFs remain backend resources because they represent immutable domain documents.

The CMS preview uses the same React renderer as the published page, with authorized saved-draft data. Remove HTML/blob preview generation and the Python marketing/legal renderers after their React equivalents and URL transitions are verified. CMS remains inside the back office, with admin/ops editing and admin-only publishing/restoration enforced by FastAPI.

## Sandbox functionality to preserve

- Registration, email/SMS verification, sandbox inbox, sign-in/out/refresh and stable QR-based MFA.
- Circle wizard and fixed cycle capacity, edit/publish/leave/cancel, public discovery, direct/invitation joins and invitation permissions.
- Manual/random payout ordering, full rules/schedule review, immutable agreement versions, signatures/revisions and PDF download.
- Contribution/payout history, remaining obligations, trust history and member/circle reporting.
- KYC documents, review/resubmission, linked bank mandates and mandate revocation.
- Notification bell/page, read markers, read-only deletion, swipe/menu actions and preferences.
- Data export/deletion requests and PWA shell without caching financial/identity data.
- Back-office overview, users/roles/trust changes, KYC evidence/decisions, circles/curation, payments/retries/reconciliation, complaints/evidence/SLA, policies, jobs/ledger export, delivery oversight, data requests and audit.
- CMS draft isolation, saved preview, optimistic edit/publication conflicts, publishing/history/restoration, and plain-text rendering safety.

## Implementation sequence after approval

1. Establish typed resources, session/toast providers, guards and route compatibility; retain current backend contracts.
2. Port account/security/verification, notifications and member navigation.
3. Port circle creation/detail/agreements/invitations, trust and reports.
4. Port back-office navigation and administrative modules; place CMS under its routed staff layout.
5. Reuse React published/draft/terms/privacy rendering and retire FastAPI HTML and legacy workspace scripts.
6. Verify all preserved workflows against sandbox fixtures and existing backend tests; build/typecheck and desktop/mobile checks must pass before removing compatibility code.

The schedule policy decision is a separate backend bug fix. Changing contribution rules does not authorize altering already signed or completed agreements. Provider adapters and unresolved launch/jurisdiction questions remain as defined in the existing sandbox.

## Requested approval

Approve adopting this route/provider/component/typed-resource architecture while retaining FastAPI and the current sandbox feature set. Implementation begins only after approval. Separately choose the fixed-debit rounding rule in the contribution schedule proposal.
