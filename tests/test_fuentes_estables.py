"""034:RF-20; 065:RF-18: exclusión real de escritura durante una lectura identificada."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

import pytest


def test_guardia_expone_descriptor_y_hash_de_mismos_bytes_sin_copia(tmp_path):
    """034:RF-20 — texto Unicode/#/% conserva identidad y stream readonly seekable."""
    from convertersmartgrid.adaptadores.fuentes_estables import abrir_fuente_estable

    path = tmp_path / 'fuente ñ # 100%.dat'
    content = b'fuente de contrato, no datos aceptados\r\n'
    path.write_bytes(content)
    with abrir_fuente_estable(path) as held:
        assert held.path == path.resolve()
        assert held.sha256 == hashlib.sha256(content).hexdigest()
        assert held.size == len(content) == held.stat.st_size
        assert held.stream.read() == content
        assert held.stream.seekable() and not held.stream.writable()
        held.stream.seek(0)
        assert os.fstat(held.stream.fileno()).st_ino == held.stat.st_ino
        assert sorted(tmp_path.iterdir()) == [path]
    assert held.stream.closed


@pytest.mark.parametrize('operation', ['write', 'replace', 'delete'])
def test_guardia_impide_ABA_y_reemplazo_hasta_salir_del_contexto(tmp_path, operation):
    """034:RF-20 — la exclusión OS impide escribir incluso antes de que el lector abra."""
    from convertersmartgrid.adaptadores.fuentes_estables import abrir_fuente_estable

    path = tmp_path / 'fuente.dat'
    path.write_bytes(b'original')
    replacement = tmp_path / 'otro.dat'
    replacement.write_bytes(b'alterado')
    with abrir_fuente_estable(path) as held:
        with pytest.raises(OSError):
            if operation == 'write':
                path.write_bytes(b'alterado')
            elif operation == 'replace':
                replacement.replace(path)
            else:
                path.unlink()
        assert path.read_bytes() == held.stream.read() == b'original'
    path.write_bytes(b'liberado')
    assert path.read_bytes() == b'liberado'


def test_guardia_rechaza_escritor_ya_abierto_y_libera_tras_excepcion(tmp_path):
    """034:RF-20 — no declara estable un descriptor incompatible ya abierto."""
    from convertersmartgrid.adaptadores.fuentes_estables import abrir_fuente_estable

    path = tmp_path / 'fuente.dat'
    path.write_bytes(b'original')
    with path.open('r+b'):
        with pytest.raises(OSError):
            with abrir_fuente_estable(path):
                pytest.fail('acepto un escritor concurrente')
    with pytest.raises(RuntimeError):
        with abrir_fuente_estable(path):
            raise RuntimeError('fallo del consumidor')
    path.unlink()


def test_guardia_no_declara_exclusion_en_plataforma_no_verificada(tmp_path, monkeypatch):
    """034:RF-20 — no hay fallback de exclusión aparente."""
    from convertersmartgrid.adaptadores.fuentes_estables import abrir_fuente_estable

    path = tmp_path / 'fuente.dat'
    path.write_bytes(b'original')
    monkeypatch.setattr(sys, 'platform', 'linux')
    with pytest.raises(OSError, match='plataforma|Windows'):
        with abrir_fuente_estable(path):
            pytest.fail('acepto una guarda no verificada')
