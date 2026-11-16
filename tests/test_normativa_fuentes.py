"""Tarjeta GEN (spec 107, 107:RF-7): la comprobación permanente de las fuentes oficiales de tools/normativa/fuentes.py.

Un generador compara el sha256 de cada fuente con el registrado antes de leerla y se para si no coincide; y el
registro que escribe no lleva rutas de la máquina. Ficheros sintéticos en tmp_path: ninguna fuente real.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('normativa_fuentes', RAIZ / 'tools' / 'normativa' / 'fuentes.py')
fuentes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fuentes)


def _carpeta(tmp_path):
    d = tmp_path / 'oficiales'
    d.mkdir()
    for nombre, contenido in (('a.xls', b'libro A'), ('b.xls', b'libro B')):
        (d / nombre).write_bytes(contenido)
    (d / 'SHA256SUMS.txt').write_text(''.join(f'{fuentes.sha256(d / n)} *{n}\n' for n in ('a.xls', 'b.xls')),
                                      encoding='utf-8')
    return d


def test_los_originales_pasan(tmp_path):
    """107:RF-7 — las fuentes iguales a su SHA256SUMS.txt pasan."""
    assert [p.name for p in fuentes.comprobar_carpeta(_carpeta(tmp_path), '*.xls')] == ['a.xls', 'b.xls']


def test_una_fuente_alterada_para_con_el_fichero_y_los_dos_sha(tmp_path):
    """107:RF-7 — una fuente con un byte cambiado para el generador, con el fichero y los dos sha en el error."""
    d = _carpeta(tmp_path)
    tabla = fuentes.sumas(d)
    assert 'a.xls' in tabla, f'SHA256SUMS.txt leído sin la suma de a.xls: {tabla}'
    registrado = tabla['a.xls']
    (d / 'a.xls').write_bytes(b'libro A alterado')
    with pytest.raises(fuentes.FuenteAlterada) as exc:
        fuentes.comprobar_carpeta(d, '*.xls')
    mensaje = str(exc.value)
    assert 'FUENTE ALTERADA' in mensaje and 'a.xls' in mensaje and registrado in mensaje
    assert fuentes.sha256(d / 'a.xls') in mensaje


def test_una_fuente_sin_suma_para(tmp_path):
    """107:RF-7 — un fichero que no está en SHA256SUMS.txt no se lee."""
    d = _carpeta(tmp_path)
    (d / 'c.xls').write_bytes(b'otro')
    with pytest.raises(fuentes.FuenteAlterada, match='FUENTE SIN SUMA'):
        fuentes.comprobar_carpeta(d, '*.xls')


def test_comprobar_contra_el_sha_registrado(tmp_path):
    """107:RF-7 — una fuente suelta, contra el sha del registro: igual pasa y distinto para."""
    f = tmp_path / 'norma.pdf'
    f.write_bytes(b'norma')
    assert fuentes.comprobar(f, fuentes.sha256(f)) == f
    with pytest.raises(fuentes.FuenteAlterada):
        fuentes.comprobar(f, '0' * 64)


def test_el_registro_sale_sin_rutas_de_la_maquina(tmp_path):
    """107:RF-7 — ``sin_rutas`` deja fichero_local relativo a la carpeta de fuentes, cita la raíz como <fuentes>/ y
    para si queda una ruta absoluta."""
    raiz = (tmp_path / 'fuentes').resolve()
    datos = {'normas': [{'fichero_local': (raiz / 'COES_SEIN' / 'x.pdf').as_posix(),
                         'nota': f'copia en {raiz.as_posix()}/COES_SEIN'}]}
    limpio = fuentes.sin_rutas(datos, raiz)
    assert limpio['normas'][0]['fichero_local'] == 'COES_SEIN/x.pdf'
    assert limpio['normas'][0]['nota'] == 'copia en <fuentes>/COES_SEIN'
    with pytest.raises(fuentes.FuenteAlterada, match='RUTA DE LA MÁQUINA'):
        fuentes.sin_rutas({'nota': 'ver D:/otra/carpeta'}, raiz)
