"""Canonical FastAPI entry point; implementation lives in platform modules."""
from .platform.application import app, create_platform

__all__ = ['app', 'create_platform']
