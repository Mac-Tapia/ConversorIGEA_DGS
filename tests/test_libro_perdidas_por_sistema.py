"""063:RF-41, 063:RF-42: libro de pérdidas en dos hojas y PDF del informe, sin Word en las pruebas."""
from __future__ import annotations

import os
import random
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from convertersmartgrid.informe_docx import exportar_pdf
from convertersmartgrid.libros_informe import ColumnasPerdidas, LibroError, leer_libro_perdidas

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
CONFIG = {'hoja_alimentadores': 'Radial', 'columna_alimentador': 'Codigo Alim', 'columna_codigo': 'Codigo Sist.',
          'columna_nombre': 'Nombre Sist.', 'hoja_perdidas': 'Perdidas', 'columna_clave': 'Código',
          'letra_kw_pct': 'E', 'letra_kwh_pct': 'D'}
PERFIL = {'informes': {'libro_perdidas': {'por_sistema': CONFIG}}}


def _libro(tmp_path, rng):
    alimentador, codigo = f'AL{rng.randint(100, 999)}', f'SE{rng.randint(1000, 9999)}'
    kw, kwh = round(rng.uniform(1, 9), 2), round(rng.uniform(1, 9), 2)
    wb = openpyxl.Workbook()
    r = wb.active
    r.title = 'Radial'
    r.append(['título'])
    r.append([None, 'Codigo Sist.', 'Nombre\nSist.', 'Codigo\nAlim'])
    r.append([None, codigo, 'SISTEMA X', alimentador])
    r.append([None, 'SE0000', 'OTRO', 'AL000'])
    p = wb.create_sheet('Perdidas')
    p.append(['título'])
    p.append(['Ítem', 'Código', None, 'Energía', 'Potencia'])
    p.append([1, 'SE0000', None, 9.9, 9.9])
    p.append([2, codigo, None, kwh, kw])
    p.append([3, codigo, None, 1.003, 1.0055])          # el libro repite el código con factores
    ruta = tmp_path / 'libro.xlsx'
    wb.save(ruta)
    return ruta, alimentador, codigo, kw, kwh


def test_el_alimentador_da_el_sistema_y_el_sistema_sus_perdidas(tmp_path):
    """063:RF-41 — con el libro cargado, el botón fallaba: el lector solo sabía de una hoja."""
    ruta, alimentador, codigo, kw, kwh = _libro(tmp_path, random.Random(SEMILLA))
    d = leer_libro_perdidas(ruta, alimentador, ColumnasPerdidas.de_perfil(PERFIL))
    assert (d.codigo_sistema, d.sistema_electrico) == (codigo, 'SISTEMA X')
    assert (d.reconocido_kw_pct, d.reconocido_kwh_pct) == (kw, kwh), 'la primera fila, no la de factores'
    assert d.precio_compra is None and any('precio' in x for x in d.faltan), 'el hueco se dice'


def test_un_alimentador_que_no_esta_no_es_un_error(tmp_path):
    """063:RF-41, 017:RF-64 — el informe sale con el hueco señalado."""
    ruta, *_ = _libro(tmp_path, random.Random(SEMILLA))
    d = leer_libro_perdidas(ruta, 'NO_ESTA', ColumnasPerdidas.de_perfil(PERFIL))
    assert d.reconocido_kw_pct is None and 'NO_ESTA' in d.faltan[0]


def test_perfil_incompleto_y_hoja_ausente_lo_dicen(tmp_path):
    """063:RF-41 — lo que falta se nombra, para corregir el perfil."""
    ruta, alimentador, *_ = _libro(tmp_path, random.Random(SEMILLA))
    with pytest.raises(LibroError, match='letra_kw_pct'):
        ColumnasPerdidas.de_perfil({'informes': {'libro_perdidas': {'por_sistema': {
            k: v for k, v in CONFIG.items() if k != 'letra_kw_pct'}}}})
    malo = {**PERFIL['informes']['libro_perdidas']['por_sistema'], 'hoja_perdidas': 'Otra'}
    with pytest.raises(LibroError, match="'Otra'"):
        leer_libro_perdidas(ruta, alimentador, ColumnasPerdidas.de_perfil(
            {'informes': {'libro_perdidas': {'por_sistema': malo}}}))


def test_el_pdf_queda_junto_al_word(tmp_path):
    """063:RF-42 — con Word, el PDF al lado; se le pide el formato 17, el PDF de Word."""
    docx = tmp_path / 'informe.docx'
    docx.write_bytes(b'x')
    ordenes = []

    def word(orden):
        ordenes.append(orden)
        docx.with_suffix('.pdf').write_bytes(b'%PDF')
        return SimpleNamespace(returncode=0, stderr='')

    pdf, motivo = exportar_pdf(docx, ejecutar=word)
    assert pdf == docx.with_suffix('.pdf') and motivo == ''
    assert '[ref]17' in ordenes[0] and str(Path(docx).resolve()) in ordenes[0]


@pytest.mark.parametrize('fallo', ['codigo', 'excepcion', 'sin_fichero'])
def test_sin_pdf_se_dice_el_motivo_y_el_word_sigue(tmp_path, fallo):
    """063:RF-42 — sin Word instalado o si falla, no se pierde el informe ni se calla."""
    docx = tmp_path / 'informe.docx'
    docx.write_bytes(b'x')

    def word(_orden):
        if fallo == 'excepcion':
            raise OSError('sin PowerShell')
        return SimpleNamespace(returncode=1 if fallo == 'codigo' else 0, stderr='sin Word' if fallo == 'codigo' else '')

    pdf, motivo = exportar_pdf(docx, ejecutar=word)
    assert pdf is None and motivo and docx.is_file()


@pytest.mark.skipif(not os.environ.get('CSG_DEMANDA_DIR'), reason='CSG_DEMANDA_DIR no definida')
def test_libro_real_de_la_empresa():
    """063:RF-41 — el libro real con el perfil de la empresa: SM218 → SE2044 → 1,69 % y 2,75 %."""
    import json

    ruta = Path(os.environ['CSG_DEMANDA_DIR']) / 'informeModeloperdidas.xlsx'
    perfil = json.loads((Path(__file__).resolve().parents[1] / 'config/perfiles/electro_dunas.json').read_text(encoding='utf-8'))
    d = leer_libro_perdidas(ruta, 'SM218', ColumnasPerdidas.de_perfil(perfil))
    assert d.codigo_sistema == 'SE2044' and d.sistema_electrico == 'SANTA MARGARITA'
    assert (d.reconocido_kwh_pct, d.reconocido_kw_pct) == (1.69, 2.75)


def test_el_perfil_local_no_pierde_el_libro_del_heredado(tmp_path):
    """063:RF-41 — el perfil local cambia un rótulo de ``informes`` y conserva lo demás del heredado."""
    import json

    from convertersmartgrid.perfil_empresa import datos_perfil

    carpeta = tmp_path / 'perfiles'
    carpeta.mkdir()
    (carpeta / 'empresa.json').write_text(json.dumps(
        {'crs_origen': 'EPSG:32718', 'escala': 2, 'informes': {'norma': 'A', 'libro_perdidas': {'por_sistema': CONFIG}}}),
        encoding='utf-8')
    local = tmp_path / 'perfil.json'
    local.write_text(json.dumps({'perfil': 'empresa', 'escala': 3, 'informes': {'norma': 'B'}}), encoding='utf-8')
    datos = datos_perfil(local, carpeta=carpeta)
    assert datos['escala'] == 3, 'fuera de informes, la clave local pisa la heredada'
    assert datos['informes']['norma'] == 'B' and datos['informes']['libro_perdidas']['por_sistema'] == CONFIG


def test_word_que_cae_al_cerrarse_no_pierde_el_pdf(tmp_path):
    """063:RF-50 — T7 en SM218: Word guardó el PDF y falló en ``Quit``; el informe decía que no había PDF."""
    docx = tmp_path / 'informe.docx'
    docx.write_bytes(b'x')

    def word(_orden):
        docx.with_suffix('.pdf').write_bytes(b'%PDF')
        return SimpleNamespace(returncode=1, stderr='Error en la llamada a procedimiento remoto')

    assert exportar_pdf(docx, ejecutar=word) == (docx.with_suffix('.pdf'), '')


def test_un_pdf_vacio_o_de_otra_vez_no_cuenta(tmp_path):
    """063:RF-50 — solo vale el PDF de esta exportación y con contenido."""
    docx = tmp_path / 'informe.docx'
    docx.write_bytes(b'x')
    pdf = docx.with_suffix('.pdf')
    pdf.write_bytes(b'%PDF')
    os.utime(pdf, (1, 1))
    falla = lambda _orden: SimpleNamespace(returncode=1, stderr='sin Word')
    assert exportar_pdf(docx, ejecutar=falla) == (None, 'sin Word')
    vacia = lambda _orden: (pdf.write_bytes(b''), SimpleNamespace(returncode=0, stderr=''))[1]
    assert exportar_pdf(docx, ejecutar=vacia)[0] is None
