"""Reexportación temporal de ``igea_dgs.sources``; la retira la spec 002 (RF-21).

Los adaptadores salieron de ``web/`` para que el CLI los use sin importar FastAPI
(spec 001, RF-1). El código del proyecto ya importa de ``igea_dgs.sources``.
"""

from ...sources import SourceAdapter, SourceLoadResult, SourceModeError, adapter_for

__all__ = ['SourceAdapter', 'SourceLoadResult', 'SourceModeError', 'adapter_for']
