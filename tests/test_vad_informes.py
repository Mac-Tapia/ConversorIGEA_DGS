"""Spec 108 T21 — Informe de Resultados Relevantes (108:RF-14) e Informe del Estudio en Word y PDF (108:RF-15).

Apartados y estructura sintéticos (otro número de apartados que el TdR 2026) y dos empresas sintéticas. El PDF se pide
a un exportador de prueba: la prueba no abre Word.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document

from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad.informes import (Cifra, apartados, escribir_informe_estudio,
                                             escribir_resultados_relevantes)

RAIZ = Path(__file__).resolve().parents[1]
EMPRESAS = ('Distribuidora Sintética Norte', 'Eléctrica Ficticia del Sur')
ANEXO3 = [{'numero': '1', 'titulo': 'Presentación'}, {'numero': '2', 'titulo': 'Cifras'},
          {'numero': '3', 'titulo': 'Cierre'}]
ESTRUCTURA = [{'numero': '1', 'titulo': 'OBJETO'},
              {'numero': '2', 'titulo': 'CÁLCULO', 'subapartados': ['Primera parte', 'Segunda parte']},
              {'numero': '3', 'titulo': 'RESULTADOS'}]


def _registro(tmp_path):
    reglas = [{'clave': 'vad.anexo3.apartados', 'valor': ANEXO3, 'cita_literal': '«anexo»', 'lineas': '7-9',
               'articulo_o_anexo': 'Anexo sintético'},
              {'clave': 'vad.informe_estudio.estructura', 'valor': ESTRUCTURA, 'cita_literal': '«estructura»',
               'lineas': '20-30', 'articulo_o_anexo': 'Numeral sintético'}]
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': 'vigente_comprobada',
        'sha256': '2' * 64, 'reglas': reglas}]}
    ruta = tmp_path / 'reg' / 'tdr.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(ruta.parent)


def _titulos(ruta):
    return [p.text for p in Document(str(ruta)).paragraphs if p.style.name.startswith('Heading')]


def _texto(ruta):
    return '\n'.join(p.text for p in Document(str(ruta)).paragraphs)


def _pdf_bien(docx):
    pdf = docx.with_suffix('.pdf')
    pdf.write_bytes(b'%PDF-1.4 prueba')
    return pdf, ''


@pytest.mark.parametrize('empresa', EMPRESAS)
def test_resultados_relevantes_con_los_apartados_del_registro(tmp_path, empresa):
    """108:RF-14 — el informe tiene los apartados del anexo 3 registrado, en su orden; cada cifra con su origen y la
    que no sale del estudio, como hueco nombrado."""
    contenido = {'1': ['Reseña del estudio.'],
                 '2': [Cifra('VNR total', 1234.5, 'miles XUS', 'tabla sintética 2'), Cifra('Clientes', None)]}
    r = escribir_resultados_relevantes(_registro(tmp_path), contenido, tmp_path / 'rr.docx', empresa=empresa)
    assert _titulos(r.docx) == ['1. Presentación', '2. Cifras', '3. Cierre']
    texto = _texto(r.docx)
    assert empresa in texto and 'VNR total: 1234.5 miles XUS (origen: tabla sintética 2)' in texto
    assert '[Hueco: Clientes]' in texto and '[Hueco: «3. Cierre» sin contenido del estudio]' in texto
    assert any('Clientes' in h for h in r.huecos) and any('Cierre' in h for h in r.huecos)


def test_informe_del_estudio_con_su_indice_y_pdf(tmp_path):
    """108:RF-15 — el índice del Word coincide con la estructura registrada (apartados y subapartados) y el PDF
    integrado sale con el exportador."""
    contenido = {'1': ['Objeto.'], '2.a': ['Uno.'], '2.b': ['Dos.'], '3': [Cifra('VAD', 3.2, 'XUS/kW.año', 'T16')]}
    r = escribir_informe_estudio(_registro(tmp_path), contenido, tmp_path / 'ie.docx', empresa=EMPRESAS[0],
                                 exportar_pdf=_pdf_bien)
    esperado = ['1. OBJETO', '2. CÁLCULO', 'a. Primera parte', 'b. Segunda parte', '3. RESULTADOS']
    assert _titulos(r.docx) == esperado
    assert [a.titulo for a in r.apartados] == esperado
    assert r.pdf is not None and r.pdf.is_file() and not r.motivo_pdf and not r.huecos


def test_pdf_que_no_sale_se_dice_y_el_word_queda(tmp_path):
    """108:RF-15 — si el PDF no sale, el Word queda hecho y se dice el motivo."""
    r = escribir_informe_estudio(_registro(tmp_path), {}, tmp_path / 'ie.docx', empresa=EMPRESAS[1],
                                 exportar_pdf=lambda docx: (None, 'sin Word en esta máquina'))
    assert r.docx.is_file() and r.pdf is None and r.motivo_pdf == 'sin Word en esta máquina'
    callado = escribir_informe_estudio(_registro(tmp_path), {}, tmp_path / 'ie2.docx', empresa=EMPRESAS[1],
                                       exportar_pdf=lambda docx: (None, ''))
    assert callado.motivo_pdf


def test_subapartado_sin_contenido_es_hueco(tmp_path):
    """108:RF-15 — un subapartado sin contenido es un hueco nombrado; el apartado padre no se duplica como hueco."""
    r = escribir_informe_estudio(_registro(tmp_path), {'1': ['x'], '2.a': ['y'], '3': ['z']}, tmp_path / 'i.docx',
                                 empresa=EMPRESAS[0], exportar_pdf=_pdf_bien)
    assert [h.split(' ')[0] for h in r.huecos] == ['2.b']


@pytest.mark.parametrize('contenido,texto', [
    ({'9': ['x']}, 'no tiene'), ({'1': 'texto suelto'}, 'lista'), ({'1': [3.5]}, 'lista'),
])
def test_contenido_invalido_se_rechaza(tmp_path, contenido, texto):
    """108:RF-14 — contenido para un apartado que el registro no tiene, o que no es una lista de párrafos y cifras,
    se rechaza y no deja fichero."""
    destino = tmp_path / 'no.docx'
    with pytest.raises(VadError, match=texto):
        escribir_resultados_relevantes(_registro(tmp_path), contenido, destino, empresa=EMPRESAS[0])
    assert not destino.exists()


def test_cifra_sin_origen_y_empresa_vacia_se_rechazan(tmp_path):
    """108:RF-14 — una cifra con valor y sin origen no entra; sin empresa no se supone ninguna."""
    with pytest.raises(VadError, match='origen'):
        Cifra('VNR', 10.0)
    with pytest.raises(VadError, match='valor no admitido'):
        Cifra('VNR', float('nan'), origen='x')
    with pytest.raises(VadError, match='empresa'):
        escribir_resultados_relevantes(_registro(tmp_path), {}, tmp_path / 'e.docx', empresa=' ')


def test_registro_real_trae_anexo3_y_estructura():
    """108:RF-14, 108:RF-15 — el TdR registrado trae los apartados del anexo 3 y la estructura del numeral 9, y las
    dos reglas obligan."""
    reg = cargar_registro(RAIZ / 'config' / 'vad')
    for clave in ('vad.anexo3.apartados', 'vad.informe_estudio.estructura'):
        lista, rv = apartados(reg, clave)
        assert lista and rv.obligatoria
