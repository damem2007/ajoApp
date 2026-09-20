"""Versioned business setup; signed contracts retain their frozen configuration."""
from .schemas import CircleSetup
from .services import policy, fail


def circle_setup(db):
    data = policy(db).data
    return {**CircleSetup(**data.get('circle_setup', {})).model_dump(), 'currencies': data['currencies']}


def validate_circle_setup(db, body):
    setup = circle_setup(db)
    if not setup['name_min_length'] <= len(body.name) <= setup['name_max_length']:
        fail(f"Circle name must contain {setup['name_min_length']}–{setup['name_max_length']} characters", 422)
    if body.currency not in setup['currencies']:
        fail('Unsupported currency', 422)
    for key in ['minimum_members', 'planned_members', 'hard_cap']:
        if not setup['members_min'] <= getattr(body, key) <= setup['members_max']:
            fail(f"Member count must be between {setup['members_min']} and {setup['members_max']}", 422)
    if body.target_minor > setup['amount_max_minor'] or (body.contribution_minor or 0) > setup['amount_max_minor']:
        fail('Amount exceeds the configured circle limit', 422)
    if body.contribution_frequency not in setup['contribution_frequencies'] or body.collection_frequency not in setup['collection_frequencies']:
        fail('This frequency is disabled in system setup', 422)
