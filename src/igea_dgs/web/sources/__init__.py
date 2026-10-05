"""Registro de adaptadores de fuente del conversor web."""

from __future__ import annotations

from .base import SourceAdapter, SourceLoadResult, SourceModeError
from .mdb import MdbSourceAdapter
from .txt import TxtSourceAdapter


def adapter_for(mode: str) -> SourceAdapter:
    if mode == 'txt':
        return TxtSourceAdapter()
    if mode == 'mdb':
        return MdbSourceAdapter()
    if mode == 'vnr':
        try:
            from .vnr import VnrSourceAdapter
        except ImportError as exc:
            raise SourceModeError('El adaptador VNR-GIS todavía no está disponible.') from exc
        return VnrSourceAdapter()
    raise SourceModeError(f'Modo de entrada desconocido: {mode!r}.')


__all__ = ['SourceAdapter', 'SourceLoadResult', 'SourceModeError', 'adapter_for']
