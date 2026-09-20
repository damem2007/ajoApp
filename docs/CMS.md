# Website content management

The screenshot-based landing page is at `/`. The full marketplace is at `/marketplace`.

Sign in as an administrator or operations user and open **Back office → Website CMS** in the app navigation, or `/app?view=backoffice&module=cms` on the Next.js frontend (port 3000).

1. Expand a section and edit its fields. Hero copy, navigation labels, calculator labels, steps, safeguards, circle-preview copy, FAQs, closing actions, footer, search metadata and terms/privacy draft text are editable.
2. Add a change note and select **Save draft**. Saving creates a revision; the public website stays on its published revision.
3. Select **Preview saved draft**. This opens an authenticated preview in a separate window. It displays the last saved draft, including the working calculator.
4. Administrators select **Publish saved draft** to make that revision public. Operations users can edit and preview, but cannot publish.
5. Use **Revision history** to restore and publish an earlier revision. Restoration creates a new revision; older history remains intact. Unsaved changes should be saved before restoring another revision.

The editor uses structured plain-text fields rather than raw HTML. Content is escaped in server-rendered HTML, and unknown field structures are rejected. Links remain controlled application destinations. Every save/publication/restoration is recorded in the staff audit trail. Concurrent edits and stale publication attempts return a conflict instead of overwriting newer content.

The CMS controls editorial content. Circle records, membership counts, payment data and frequency options remain controlled by their domain services. Illustrative circles appear only in an empty sandbox marketplace and are identified as examples; they cannot be joined. The landing page shows up to three circles from that same source.

## Database and API

Migration `7bb13c20a6f9` adds `content_pages` and `content_revisions`. Sandbox startup creates missing tables; migrated environments should run `alembic upgrade head` with their configured database URL. Initial home content is seeded atomically when the page is first requested.

- `GET /api/v1/content/home`: published content only.
- `GET /api/v1/admin/content/home`: current draft and publication state.
- `PUT /api/v1/admin/content/home/draft`: structured `content`, `expected_draft` revision ID and `reason`.
- `GET /api/v1/admin/content/home/preview`: authenticated HTML preview of the saved draft.
- `POST /api/v1/admin/content/home/publish`: current draft `revision_id`, `expected_published` revision ID and `reason`.
- `GET /api/v1/admin/content/home/revisions`: revision metadata.
- `GET /api/v1/admin/content/home/revisions/{id}`: revision content for staff.
- `POST /api/v1/admin/content/home/restore`: source `revision_id`, `expected_published` revision ID and `reason`.

The footer terms/privacy pages are explicitly labelled sandbox draft information. Approved launch policies and live provider delivery remain open product decisions.
