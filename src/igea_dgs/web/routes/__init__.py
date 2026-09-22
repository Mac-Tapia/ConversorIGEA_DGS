"""Rutas HTTP de la aplicación local."""

from .dialogs import NativeDialogPort, TkNativeDialog
from .dialogs import router as dialogs_router
from .projects import router as projects_router

__all__ = ["NativeDialogPort", "TkNativeDialog", "dialogs_router", "projects_router"]
