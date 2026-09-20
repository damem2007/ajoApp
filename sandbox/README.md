# Archived UI artifacts

This directory retains historical UI comparison artifacts only. It is not a
sandbox backend or a separate source of users/circles. Legacy prototype API
fixtures and models now live under `tests/legacy_reference` and `tests/store.py`.

Sandbox payments, identity and notifications are selectable providers in the
canonical backend. They operate on the configured PostgreSQL or SQLite data
through the same API and services as future live adapters. Database mode and
provider selection remain independent; simulations never transfer real funds.
