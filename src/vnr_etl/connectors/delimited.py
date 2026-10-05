"""Adaptador de texto delimitado (CSV/TXT) con descubrimiento de codificación y delimitador. No leer es peor que leer mal: una codificación equivocada produce datos silenciosamente corruptos. Aquí se detecta la codificación sin adivinar el resto.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .base import LayerInfo, SourceProbe, VNRSourceAdapter

try:
    import chardet
except ImportError:  # pragma: no cover
    chardet = None


@dataclass
class DelimitedTextAdapter(VNRSourceAdapter):
    """Lee un CSV/TXT, manteniendo fidelidad de encoding y delimitación."""

    path: str = ''

    def _open(self, encoding=None):
        path = Path(self.path)
        if encoding is None:
            encoding, _src = self._detect_encoding(path)
        return path.open('r', encoding=encoding, newline='')

    def _detect_encoding(self, path: Path):
        """Codificación por BOM (UTF-8/16/32), fallback a ``chardet`` y, por último, latin-1."""
        with path.open('rb') as fh:
            raw = fh.read(16)
        for bom, name in (
            ((raw[:3], b'\xef\xbb\xbf'), 'utf-8-sig'),
            ((raw[:2], b'\xff\xfe'), 'utf-16-le'),
            ((raw[:2], b'\xfe\xff'), 'utf-16-be'),
            ((raw[:4], b'\xff\xfe\x00\x00'), 'utf-32'),
        ):
            if bom[0] == bom[1]:
                return name, 'bom'
        if chardet is not None:
            with path.open('rb') as fh:
                guess = chardet.detect(fh.read(8192))
            if guess and guess.get('encoding'):
                return guess['encoding'], 'chardet'
        return 'utf-8', 'default'

    def _detect_delimiter(self, sample: str) -> str:
        try:
            return csv.Sniffer().sniff(sample, delimiters=',;\t|').delimiter
        except csv.Error:
            # Fallback por recuento de separadores en la primera línea no vacía.
            for candidate in (';', '\t', ',', '|'):
                if candidate in sample.splitlines()[0]:
                    return candidate
            return ','

    def probe(self, source) -> SourceProbe:
        path = Path(self.path or source)
        if not path.is_file():
            return SourceProbe(family='DELIMITED_TEXT', ok=False, reason=f'No existe {path}')
        return SourceProbe(family='DELIMITED_TEXT', ok=True)

    def metadata(self) -> dict:
        return {'path': self.path, 'family': 'DELIMITED_TEXT'}

    def list_layers(self) -> list[LayerInfo]:
        rows = self.read_layer('__self__')
        fields = sorted(rows[0].keys()) if rows else []
        return [LayerInfo(name=Path(self.path).name, fields=[{'name': f, 'type': ''} for f in fields])]

    def read_layer(self, layer, filters=None) -> list[dict]:
        del filters
        path = Path(self.path)
        encoding, _ = self._detect_encoding(path)
        with path.open('r', encoding=encoding, newline='') as fh:
            sample = fh.read(4096)
            fh.seek(0)
            delim = self._detect_delimiter(sample)
            reader = csv.DictReader(fh, delimiter=delim)
            rows = [dict(row) for row in reader]
        return rows
