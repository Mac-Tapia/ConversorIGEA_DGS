"""Spec 004 T28 — los vínculos del proyecto de un ``.pfd`` con los ficheros de su expediente, por su contenido y con
la evidencia de cada uno (004:RF-109, RF-110).

Proyecto, casos, escenarios, alimentadores y SET sorteados; ficheros sintéticos (Word, Excel, CSV y texto) en una
carpeta temporal. Ningún nombre de una empresa real.
"""
from __future__ import annotations

import importlib
import importlib.util
import random
import string

import pytest

SEMILLA = 4_28


def _vinculos():
    """El módulo de la T28: su ausencia es la falla de la aserción, no un error de importación."""
    assert importlib.util.find_spec('convertersmartgrid.pfd_vinculos') is not None, \
        'falta convertersmartgrid.pfd_vinculos (004 T28)'
    return importlib.import_module('convertersmartgrid.pfd_vinculos')


def _nombre(rng, prefijo):
    return prefijo + ''.join(rng.choice(string.ascii_uppercase) for _ in range(3)) + str(rng.randint(10, 99))


def _diagnostico(rng):
    caso, otro = _nombre(rng, 'Caso '), _nombre(rng, 'Caso ')
    return {'proyecto': _nombre(rng, 'PRJ-'), 'casos': [{'caso': caso}, {'caso': otro}],
            'escenarios': [{'escenario': _nombre(rng, 'Esc ')}], 'variaciones': [{'variacion': _nombre(rng, 'Var ')}],
            'red': {'redes': [{'red': 'R1', 'alimentadores': [_nombre(rng, 'AL')]}], 'alimentadores_sin_red': [],
                    'alimentadores': []}}


def _expediente(tmp_path, diag, set_nombre):
    from docx import Document
    from openpyxl import Workbook
    carpeta = tmp_path / 'expediente'
    carpeta.mkdir()
    caso = diag['casos'][0]['caso']
    alim = diag['red']['redes'][0]['alimentadores'][0]
    doc = Document()
    doc.add_paragraph(f'Se estudió el {caso.upper()} con el escenario {diag["escenarios"][0]["escenario"]}.')
    doc.save(carpeta / 'memoria.docx')
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Cargas'
    hoja['A1'], hoja['B2'] = 'Alimentador', alim
    hoja['C3'] = f'Subestación {set_nombre}'
    libro.save(carpeta / 'cargas.xlsx')
    (carpeta / 'notas.csv').write_text(f'proyecto;nota\n{diag["proyecto"]};revisado\n', encoding='utf-8')
    # Se llama como el otro caso y no lo nombra dentro: no basta para el vínculo.
    (carpeta / f'{diag["casos"][1]["caso"]}.txt').write_text('Acta sin nombres del proyecto.', encoding='utf-8')
    # Un nombre que contiene al del alimentador no es el alimentador.
    (carpeta / 'otro.txt').write_text(f'Ver {alim}X0 y el {alim}9.', encoding='utf-8')
    (carpeta / 'copia.pfd').write_bytes(b'\x00\x01binario de PowerFactory')
    return carpeta


def test_004_rf109_el_proyecto_se_vincula_con_los_ficheros_que_nombran_sus_casos_escenarios_alimentadores_y_set(tmp_path):
    """004:RF-109 — el contenido de cada fichero del expediente (Word, Excel con el lector común, CSV, texto) que nombra
    un caso, escenario, alimentador, SET o el proyecto lo vincula, como palabra entera y sin distinguir mayúsculas."""
    mod = _vinculos()
    rng = random.Random(SEMILLA)
    diag = _diagnostico(rng)
    set_nombre = _nombre(rng, 'SET ')
    carpeta = _expediente(tmp_path, diag, set_nombre)
    nombres = mod.nombres_del_diagnostico(diag, sets=[set_nombre])
    assert nombres['caso'] == {c['caso'] for c in diag['casos']} and nombres['set'] == {set_nombre}
    salida = mod.vincular(nombres, carpeta)
    por = {(v['tipo'], v['nombre']): v for v in salida['vinculos']}
    caso, alim = diag['casos'][0]['caso'], diag['red']['redes'][0]['alimentadores'][0]
    assert por[('caso', caso)]['fichero'] == 'memoria.docx'
    assert por[('escenario', diag['escenarios'][0]['escenario'])]['fichero'] == 'memoria.docx'
    assert por[('alimentador', alim)]['fichero'] == 'cargas.xlsx' and por[('set', set_nombre)]['fichero'] == 'cargas.xlsx'
    assert por[('proyecto', diag['proyecto'])]['fichero'] == 'notas.csv'
    assert not [v for v in salida['vinculos'] if v['fichero'] == 'otro.txt'], 'un nombre más largo no es el nombre'
    assert f'variacion «{diag["variaciones"][0]["variacion"]}»' in salida['sin_vinculo']


def test_004_rf110_cada_vinculo_lleva_su_evidencia_y_el_nombre_del_fichero_no_basta(tmp_path):
    """004:RF-110 — cada vínculo lleva el fichero con su huella, la hoja o la página y el texto que nombra; un fichero
    que solo se llama como un caso no se vincula, y uno que no se puede leer se dice aparte con su motivo."""
    mod = _vinculos()
    rng = random.Random(SEMILLA + 1)
    diag = _diagnostico(rng)
    set_nombre = _nombre(rng, 'SET ')
    carpeta = _expediente(tmp_path, diag, set_nombre)
    salida = mod.vincular(mod.nombres_del_diagnostico(diag, sets=[set_nombre]), carpeta)
    otro_caso = diag['casos'][1]['caso']
    assert ('caso', otro_caso) not in {(v['tipo'], v['nombre']) for v in salida['vinculos']}
    assert f'caso «{otro_caso}»' in salida['sin_vinculo']
    for v in salida['vinculos']:
        assert len(v['sha256']) == 64 and v['ubicacion'] and v['texto']
        assert v['nombre'].lower() in v['texto'].lower(), v
    alim = diag['red']['redes'][0]['alimentadores'][0]
    del_libro = next(v for v in salida['vinculos'] if v['nombre'] == alim)
    assert 'Cargas' in str(del_libro['ubicacion'])
    pfd = next(f for f in salida['ficheros'] if f['fichero'] == 'copia.pfd')
    assert pfd['estado'] != 'ok' and pfd['motivo'] and pfd['vinculos'] == 0


def test_004_rf109_un_nombre_demasiado_corto_se_dice_y_un_tipo_desconocido_se_rechaza(tmp_path):
    """004:RF-109 — un nombre de una letra casaría con cualquier texto: se avisa y no se busca; un tipo de nombre que
    no es del proyecto se rechaza."""
    mod = _vinculos()
    (tmp_path / 'a.txt').write_text('A B C', encoding='utf-8')
    salida = mod.vincular({'caso': {'A'}}, tmp_path)
    assert salida['vinculos'] == [] and any('demasiado corto' in a for a in salida['avisos'])
    with pytest.raises(ValueError, match='desconocidos'):
        mod.vincular({'cliente': {'X1'}}, tmp_path)
