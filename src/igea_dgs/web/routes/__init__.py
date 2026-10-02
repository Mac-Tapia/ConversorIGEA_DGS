"""Rutas HTTP de la aplicación local."""

from .dialogs import NativeDialogPort, TkNativeDialog
from .dialogs import router as dialogs_router
from .pipeline import router as pipeline_router
from .projects import router as projects_router
from .revisions import router as revisions_router

__all__ = [
    "NativeDialogPort",
    "TkNativeDialog",
    "dialogs_router",
    "projects_router",
    "pipeline_router",
    "revisions_router",
]
