"""Reexportación temporal de ``convertersmartgrid.sources.vnr``; la retira la spec 002 (RF-21)."""

from ...sources.vnr import VnrSourceAdapter

__all__ = ['VnrSourceAdapter']
