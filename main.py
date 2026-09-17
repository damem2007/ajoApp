"""Deployment entry point; Python domain modules retain stable package imports."""
from app.platform.application import app, create_platform
__all__ = ['app', 'create_platform']
