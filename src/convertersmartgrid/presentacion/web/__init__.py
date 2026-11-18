"""Interfaz web: API FastAPI + front React (``frontend/``) sobre el motor ``convertersmartgrid``."""

def __getattr__(nombre: str):
    """Permite comprobar dependencias sin importar FastAPI antes del diagnóstico."""
    if nombre == 'create_app':
        from .app import create_app
        return create_app
    raise AttributeError(f'El módulo {__name__!r} no tiene el atributo {nombre!r}')

__all__ = ['create_app']
