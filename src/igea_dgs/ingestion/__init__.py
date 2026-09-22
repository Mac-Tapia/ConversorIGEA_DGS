"""Ingestion estricta y trazable de exportaciones IGEA."""

from .contracts import LOADS_CONTRACT, RED_CONTRACT, FileContract, TableContract
from .parser import parse_igea_file
from .records import ParsedFile, RawRecord

__all__ = [
    "LOADS_CONTRACT",
    "RED_CONTRACT",
    "FileContract",
    "ParsedFile",
    "RawRecord",
    "TableContract",
    "parse_igea_file",
]
