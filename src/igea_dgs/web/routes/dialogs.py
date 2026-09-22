"""Puertos de selección nativa; la UI web nunca inventa rutas."""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from typing import Protocol

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel


class NativeDialogPort(Protocol):
    def select_file(self, patterns: tuple[str, ...]) -> Path | None: ...

    def select_folder(self) -> Path | None: ...


class TkNativeDialog:
    """Ejecuta cada diálogo en su propio hilo STA de Windows."""

    @staticmethod
    def _run(callback: Callable[[], str]) -> Path | None:
        result: Queue[str | None | Exception] = Queue(maxsize=1)

        def worker() -> None:
            initialized = False
            try:
                if hasattr(ctypes, "windll"):
                    initialized = ctypes.windll.ole32.OleInitialize(None) >= 0
                result.put(callback())
            except Exception as exc:  # noqa: BLE001  # pragma: no cover - puente de hilo
                result.put(exc)
            finally:
                if initialized:
                    ctypes.windll.ole32.OleUninitialize()

        thread = threading.Thread(target=worker, name="igea-native-dialog")
        thread.start()
        thread.join()
        value = result.get()
        if isinstance(value, Exception):
            raise value
        return Path(value).resolve(strict=True) if value else None

    def select_file(self, patterns: tuple[str, ...]) -> Path | None:
        def choose() -> str:
            from tkinter import Tk, filedialog

            root = Tk()
            root.withdraw()
            try:
                return filedialog.askopenfilename(
                    title="Seleccionar entrada IGEA",
                    filetypes=[("Entradas permitidas", " ".join(patterns)), ("Todos", "*.*")],
                )
            finally:
                root.destroy()

        return self._run(choose)

    def select_folder(self) -> Path | None:
        def choose() -> str:
            from tkinter import Tk, filedialog

            root = Tk()
            root.withdraw()
            try:
                return filedialog.askdirectory(title="Seleccionar carpeta")
            finally:
                root.destroy()

        return self._run(choose)


class FileDialogRequest(BaseModel):
    patterns: tuple[str, ...]


router = APIRouter(prefix="/api/dialog", tags=["dialogs"])


@router.post("/file", response_model=None)
def select_file(payload: FileDialogRequest, request: Request) -> dict[str, str] | Response:
    selected = request.app.state.native_dialog.select_file(payload.patterns)
    return {"path": str(selected)} if selected else Response(status_code=204)


@router.post("/folder", response_model=None)
def select_folder(request: Request) -> dict[str, str] | Response:
    selected = request.app.state.native_dialog.select_folder()
    return {"path": str(selected)} if selected else Response(status_code=204)
