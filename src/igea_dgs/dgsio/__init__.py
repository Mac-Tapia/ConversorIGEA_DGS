"""Construccion, escritura y lectura DGS estrictas."""

from .builder import DgsDocument, build_dgs_document
from .parser import parse_dgs
from .writer import write_dgs_document

__all__ = ["DgsDocument", "build_dgs_document", "parse_dgs", "write_dgs_document"]
