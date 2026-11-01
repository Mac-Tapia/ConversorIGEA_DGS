"""Interfaz web: API FastAPI + front React (``frontend/``) sobre el motor ``convertersmartgrid``."""

from .app import create_app

__all__ = ['create_app']
