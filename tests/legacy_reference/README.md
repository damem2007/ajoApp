# Legacy regression fixtures

The retired unauthenticated prototype API and `tests/store.py` models exist only
for `tests/test_platform.py`. The factory requires an explicit fixture database
and demo flag; it has no global ASGI app and never selects deployment data.

The actual sandbox is the selectable provider implementation in
`backend/app/platform/providers.py`. It uses canonical application services and
the configured PostgreSQL or SQLite data, including the certified fallback.
