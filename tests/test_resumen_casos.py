"""017:RF-144 a RF-148 — el resumen ejecutivo por caso con lo guardado en el espacio, sin DIgSILENT."""
from __future__ import annotations

import json

import pytest

from convertersmartgrid.aplicacion import resumen_casos as rc


INFORMES = [{'feeder': 'F2', 'objetivo': {'kw': 1520.0}, 'factor_escala': 0.987, 'cuadrado': True, 'status': 'OK'},
            {'feeder': 'F1', 'objetivo': {'kw': 18.8}, 'factor_escala': 0.031, 'cuadrado': False, 'status': 'FALLO',
             'motivo': 'factor bajo de sus escaladas'}]
CARGAS = [{'alimentador': 'F1', 'sed': 'C_1', 'kw': 1200.0, 'barra': 'B1', 'variacion': 'Carga_C_1'},
          {'alimentador': 'F2', 'sed': 'C_2', 'kw': 300.0, 'barra': 'B7', 'variacion': 'Carga_C_2'},
          {'alimentador': 'F1', 'sed': 'C_3', 'kw': 500.0, 'barra': 'B3', 'variacion': 'Carga_C_3'}]
ALTERNATIVAS = {'F1': [
    {'numero': 1, 'nombre': 'sección AA en 3 tramos', 'costo_anual': 73727.0, 'inversion': 500000.0, 'elegida': True,
     'ubicacion': ['sección AA desde el nodo N1 hasta el nodo N4 (3 tramos: T1 N1→N2, T2 N2→N3, T3 N3→N4)']},
    {'numero': 2, 'nombre': 'terna en 2 tramos + bancos 1×450 kvar', 'costo_anual': 117641.0, 'elegida': False,
     'ubicacion': ['terna desde el nodo N1 hasta el nodo N3 (2 tramos: T1 N1→N2, T2 N2→N3)',
                   'banco de 450 kvar en el nodo de MT N3']}]}


def test_017_rf153_sin_proyecto_por_alimentador_con_su_calibracion():
    """017:RF-145 — la máxima, el factor, si es válida y el motivo de la que no; en orden de alimentador."""
    r = rc.resumen('sin_proyecto', informes=INFORMES)
    assert [f[0] for f in r['filas']] == ['F1', 'F2']
    assert r['filas'][0][3] == 'sin validar' and 'factor bajo' in r['filas'][0][4]
    assert r['filas'][1][3] == 'válida' and r['filas'][1][2] == '0.987'
    assert any('Sin validar: F1' in c for c in r['conclusiones'])


def test_017_rf154_cargas_nuevas_por_alimentador_con_su_total():
    """017:RF-146 — cada carga con su potencia y su barra; el total y el alimentador con más carga."""
    r = rc.resumen('cargas_nuevas', cargas=CARGAS)
    assert [(f[0], f[1]) for f in r['filas']] == [('F1', 'C_1'), ('F1', 'C_3'), ('F2', 'C_2')]
    assert any('3 cargas nuevas en 2 alimentadores' in c for c in r['conclusiones'])
    assert any('F1' in c and '1' in c for c in r['conclusiones'][1:])


def test_017_rf155_con_proyecto_alternativas_con_sus_nodos_y_la_que_se_aplica():
    """017:RF-147 — usuario (2026-11-25): «identificar los bancos e indicar los nodos, y el nodo de inicio y fin en los
    tramos de cables y terna, reforzamiento»; y los que no llevan obra, dichos."""
    r = rc.resumen('con_proyecto', alternativas=ALTERNATIVAS, sin_obra=['F2'])
    f1 = [f for f in r['filas'] if f[0] == 'F1']
    assert [f[1] for f in f1] == ['1', '2'] and f1[0][6] == 'sí' and f1[1][6] == ''
    assert 'desde el nodo N1 hasta el nodo N4' in f1[0][3]
    assert 'banco de 450 kvar en el nodo de MT N3' in f1[1][3] and 'desde el nodo N1 hasta el nodo N3' in f1[1][3]
    assert any(f[0] == 'F2' and 'sin obra' in f[2] for f in r['filas'])
    assert '73' in r['conclusiones'][0]


@pytest.mark.parametrize('caso,datos,frase', [('otro', {}, 'Caso desconocido'),
                                               ('sin_proyecto', {}, 'no tiene calibración'),
                                               ('cargas_nuevas', {}, 'no tiene cargas nuevas'),
                                               ('con_proyecto', {}, 'no tiene obras evaluadas')])
def test_017_rf152_sin_nada_que_resumir_se_dice(caso, datos, frase):
    """017:RF-144 — un caso que no existe o sin nada guardado no da un resumen vacío: se dice qué falta."""
    with pytest.raises(rc.ResumenError, match=frase):
        rc.resumen(caso, **datos)


def test_017_rf156_la_web_escribe_el_word_de_una_hoja_sin_digsilent(tmp_path):
    """017:RF-148 — el Word del caso con su ficha, sus conclusiones y la tabla; su JSON par dice lo que lleva."""
    from convertersmartgrid.adaptadores.informe_docx import escribir_resumen_caso

    destino = tmp_path / 'resumen_ejecutivo_con_proyecto_P.docx'
    hecho = escribir_resumen_caso(destino, rc.resumen('con_proyecto', alternativas=ALTERNATIVAS), project='P',
                                  libro=True)
    assert destino.is_file() and (tmp_path / hecho['xlsx']).is_file()
    par = json.loads(destino.with_suffix('.json').read_text(encoding='utf-8'))
    assert par['tipo'] == 'resumen_caso' and par['caso'] == 'Con proyecto' and par['filas'] == 2
    from docx import Document

    texto = '\n'.join(c.text for t in Document(destino).tables for fila in t.rows for c in fila.cells)
    assert 'desde el nodo N1 hasta el nodo N4' in texto


def test_017_rf149_un_solo_resumen_del_sistema_con_los_tres_casos(tmp_path):
    """017:RF-149 — usuario (2026-11-25): «tiene que ser un solo resumen ejecutivo; es un solo proyecto de sistema»."""
    from convertersmartgrid.adaptadores.informe_docx import escribir_resumen_caso
    from docx import Document

    r = rc.resumen_del_sistema(informes=INFORMES, cargas=CARGAS, alternativas=ALTERNATIVAS, sin_obra=['F2'])
    assert [s['caso'] for s in r['secciones']] == ['Sin proyecto', 'Cargas nuevas', 'Con proyecto']
    assert any(c.startswith('Sin proyecto:') for c in r['conclusiones'])
    assert any(c.startswith('Con proyecto:') for c in r['conclusiones'])
    destino = tmp_path / 'resumen_ejecutivo_sistema_P.docx'
    escribir_resumen_caso(destino, r, project='P', libro=True)
    texto = '\n'.join(p.text for p in Document(destino).paragraphs)
    assert 'Sin proyecto · por alimentador' in texto and 'Con proyecto · por alimentador' in texto
    # Sin nada de un caso, se dice y el resto sale.
    parcial = rc.resumen_del_sistema(cargas=CARGAS)
    assert [s['caso'] for s in parcial['secciones']] == ['Cargas nuevas']
    assert any('no tiene calibración' in c for c in parcial['conclusiones'])
    with pytest.raises(rc.ResumenError, match='nada guardado'):
        rc.resumen_del_sistema()
