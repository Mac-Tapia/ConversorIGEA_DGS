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


def test_017_rf150_calibracion_cuadrada_con_aviso_de_kvar_es_valida_y_dice_su_aviso():
    """017:RF-150 — Pisco (2026-11-25): 16 de 17 salían «sin validar» por su aviso de kvar, y todos con el aviso del
    primero, porque la lista de avisos es la del sistema entero."""
    sistema = ['F1: la red da 410 kVAR frente a 350 medidos.', 'F2: la red da 1 473 kVAR frente a 307 medidos.']
    informes = [{'feeder': 'F1', 'objetivo': {'kw': 10.0}, 'cuadrado': True, 'status': 'AVISO_KVAR', 'avisos': sistema},
                {'feeder': 'F2', 'objetivo': {'kw': 20.0}, 'cuadrado': True, 'status': 'AVISO_KVAR', 'avisos': sistema},
                {'feeder': 'F3', 'objetivo': {'kw': 30.0}, 'cuadrado': True, 'status': 'NO_CONVERGE', 'avisos': sistema}]
    r = rc.resumen('sin_proyecto', informes=informes)
    por = {f[0]: f for f in r['filas']}
    assert por['F1'][3] == 'válida' and por['F2'][3] == 'válida' and por['F3'][3] == 'sin validar'
    assert por['F1'][4].startswith('F1:') and por['F2'][4].startswith('F2:') and not por['F3'][4].startswith('F1')
    assert any('2 con la calibración válida' in c for c in r['conclusiones'])


def test_017_rf151_con_proyecto_dice_lo_aplicado_con_su_costo_una_vez():
    """017:RF-151 — Pisco (2026-11-25): las alternativas guardadas, de corridas distintas, daban la terna de 117 641
    como aplicada en PA217 cuando estaba la sección de 73 727, y SI112 salía sin su obra."""
    guardadas = {'F1': [{'numero': 1, 'nombre': 'terna T', 'costo_anual': 117641.0, 'elegida': True}],
                 'F4': []}
    aplicadas = {'F1': [{'nombre': 'sección S', 'costo_anual': 73727.0, 'ubicacion': ['sección S desde el nodo A'],
                         'origen': 'escalera'}],
                 'F4': [{'nombre': 'sección Q', 'costo_anual': 41158.0, 'ubicacion': [], 'origen': 'escalera'}],
                 'F5': [{'nombre': 'terna R', 'costo_anual': 100151.0, 'ubicacion': ['terna desde el nodo X'],
                         'origen': 'escalera'},
                        {'nombre': 'Obra_expreso_F5', 'costo_anual': None, 'ubicacion': [], 'origen': 'operador'}]}
    r = rc.resumen('con_proyecto', alternativas=guardadas, aplicadas=aplicadas, sin_obra=['F2'])
    f1 = [f for f in r['filas'] if f[0] == 'F1']
    assert [(f[2], f[6]) for f in f1] == [('sección S', 'sí'), ('terna T', '')]
    assert any(f[0] == 'F4' and f[2] == 'sección Q' and f[6] == 'sí' for f in r['filas'])
    f5 = [f for f in r['filas'] if f[0] == 'F5']
    assert any('del operador' in f[2] and f[6] == 'sí' for f in f5)
    assert '3 alimentadores con obra' in r['conclusiones'][0]
    # 73 727 + 41 158 + 100 151, cada una una vez; el separador de miles es el espacio fino.
    assert '215 036' in r['conclusiones'][0]


def test_017_rf152_nodos_de_cada_tramo_desde_la_lectura_guardada():
    """017:RF-152 — la sección aplicada de un alimentador con el nodo de inicio y fin de sus tramos, sin DIgSILENT."""
    obra = {'clase': 'seccion', 'tipo': {'nombre': 'AA'}, 'tramos': ['T1', 'T2', 'T9']}
    nodos = {'T1': ('N1', 'N2'), 'T2': ('N2', 'N3')}
    texto = rc.ubicacion_de_obra(obra, nodos)
    assert 'desde el nodo N1' in texto and 'T1 N1→N2' in texto and 'T2 N2→N3' in texto and 'T9' in texto
    assert rc.ubicacion_de_obra({'clase': 'condensador', 'barra': 'B7', 'q_kvar': 450}, {}) \
        == 'banco de 450 kvar en el nodo de MT B7'


def test_017_rf151_rf152_el_servicio_lee_lo_aplicado_y_los_nodos_guardados(tmp_path):
    """017:RF-151, RF-152 — del registro de obras aplicadas, una fila por elección aunque vaya en dos variaciones, y los
    nodos de sus tramos de la lectura más reciente guardada en el espacio."""
    import os
    import types

    from convertersmartgrid.presentacion.web import services as s

    salida = tmp_path / 'runs' / 'r1' / 'salida'
    salida.mkdir(parents=True)
    vieja = salida / 'escalera_datos_a.json'
    vieja.write_text(json.dumps({'alimentadores': {'F1': {'troncal': [
        {'nombre': 'T1', 'desde': 'X', 'hasta': 'Y'}]}}}), encoding='utf-8')
    nueva = salida / 'escalera_datos_b.json'
    nueva.write_text(json.dumps({'alimentadores': {'F1': {
        'troncal': [{'nombre': 'T1', 'desde': 'N1', 'hasta': 'N2'}],
        'caminos': {'B9': [{'nombre': 'T2', 'desde': 'N2', 'hasta': 'N3'}]}}}}), encoding='utf-8')
    os.utime(vieja, (1, 1))
    eleccion = {'nombre': 'terna R', 'costo_anual': 100.0}
    ws = types.SimpleNamespace(root=tmp_path, obras_aplicadas=[
        {'project': 'P', 'variacion': 'Obra_terna_F1', 'origen': 'escalera', 'eleccion': eleccion,
         'obra': {'alimentador': 'F1', 'clase': 'terna', 'tramos': ['T1']}},
        {'project': 'P', 'variacion': 'Obra_terna_F1_2', 'origen': 'escalera', 'eleccion': eleccion,
         'obra': {'alimentador': 'F1', 'clase': 'terna', 'tramos': ['T2']}},
        {'project': 'otro', 'variacion': 'Obra_x', 'obra': {'alimentador': 'F1', 'clase': 'terna'}}])
    ap = s._obras_aplicadas_para_resumen(ws, 'P')
    assert list(ap) == ['F1'] and len(ap['F1']) == 1
    fila = ap['F1'][0]
    assert fila['variaciones'] == ['Obra_terna_F1', 'Obra_terna_F1_2'] and fila['costo_anual'] == 100.0
    assert 'T1 N1→N2' in fila['ubicacion'][0] and 'T2 N2→N3' in fila['ubicacion'][1]


def test_017_rf153_la_obra_que_digsilent_ya_no_tiene_no_se_da_por_aplicada(tmp_path):
    """017:RF-153 — Pisco (2026-11-25): el expreso y la SET nueva de AL209 se retiraron en DIgSILENT cuando se cortó la
    web, antes de guardar el espacio, y el resumen los seguía dando por aplicados."""
    import os
    import types

    from convertersmartgrid.presentacion.web import services as s

    salida = tmp_path / 'runs' / 'r1' / 'salida'
    salida.mkdir(parents=True)
    lectura = salida / 'escalera_datos_a.json'
    lectura.write_text(json.dumps({'project': 'P', 'variaciones_activas': ['Obra_seccion_F2'],
                                   'alimentadores': {}}), encoding='utf-8')
    os.utime(lectura, (200, 200))
    ws = types.SimpleNamespace(root=tmp_path, obras_aplicadas=[
        {'project': 'P', 'variacion': 'Obra_expreso_F1', 'origen': 'operador', 'aplicada': 100,
         'obra': {'alimentador': 'F1', 'clase': 'expreso'}},
        {'project': 'P', 'variacion': 'Obra_seccion_F2', 'origen': 'escalera', 'aplicada': 100,
         'eleccion': {'nombre': 'sección S', 'costo_anual': 5.0}, 'obra': {'alimentador': 'F2', 'clase': 'seccion'}},
        {'project': 'P', 'variacion': 'Obra_terna_F1', 'origen': 'escalera', 'aplicada': 300,
         'eleccion': {'nombre': 'terna T', 'costo_anual': 9.0}, 'obra': {'alimentador': 'F1', 'clase': 'terna'}}])
    avisos: list[str] = []
    ap = s._obras_aplicadas_para_resumen(ws, 'P', avisos)
    assert [a['nombre'] for a in ap['F1']] == ['terna T'] and [a['nombre'] for a in ap['F2']] == ['sección S']
    assert len(avisos) == 1 and 'Obra_expreso_F1' in avisos[0]


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


def _terna_ll202():
    """La terna de LL202 del 2026-11-27, reducida a tres tramos: uno de 50 mm², uno de 35 y uno que ya era de 120."""
    obra = {'clase': 'terna', 'alimentador': 'LL202', 'tramos': ['T1', 'T2', 'T3'],
            'tipo': {'nombre': 'AA12003D_FICHA', 'clase': 'TypLne'}}
    elementos = [
        {'elemento': 'T1', 'clase': 'ElmLne', 'cambio': 'typ_id AA05003D_FICHA → AA12003D_FICHA, nlnum 1 → 2',
         'tipo': 'AA12003D_FICHA', 'largo_m': 1500.0},
        {'elemento': 'T2', 'clase': 'ElmLne', 'cambio': 'typ_id AA03503D_FICHA → AA12003D_FICHA, nlnum 1 → 2',
         'tipo': 'AA12003D_FICHA'},
        {'elemento': 'T3', 'clase': 'ElmLne', 'cambio': 'nlnum 1 → 2', 'largo_m': 500.0}]
    ubicacion = [
        {'elemento': 'T1', 'puntos': [{'barra': 'CABECERA', 'lat': -14.5810052, 'lon': -75.2081686, 'crs': 'EPSG:32718',
                                       'este': 477577.29, 'norte': 8388005.59}, {'barra': 'N1'}]},
        {'elemento': 'T3', 'puntos': [{'barra': 'N2'}, {'barra': '12703', 'lat': -14.6449388, 'lon': -75.0567225,
                                                         'crs': 'EPSG:32718', 'este': 493891.96, 'norte': 8380943.98}]}]
    return obra, elementos, ubicacion


def test_017_rf155_la_ficha_de_la_terna_con_sus_extremos_conductor_y_longitud(tmp_path):
    """017:RF-155 — la ficha de una terna: nueva terna con cambio de conductor, extremos con coordenadas, longitud por
    conductor existente (el largo que falta, de la conversión) y conductor final con su sección; en el Word y el libro."""
    from convertersmartgrid.adaptadores.informe_docx import escribir_resumen_caso

    obra, elementos, ubicacion = _terna_ll202()
    ficha = rc.ficha_obra_de_linea(obra, elementos, ubicacion, {'T2': 0.25})
    assert ficha['obra'] == 'Nueva terna en paralelo con cambio de conductor'
    assert ficha['longitud_km'] == 2.25 and ficha['km_cambio'] == 1.75 and ficha['km_terna'] == 2.25
    assert ficha['conductor_final'] == 'AA 120 mm² (AA12003D_FICHA)'
    assert ficha['inicio']['barra'] == 'CABECERA' and ficha['fin']['barra'] == '12703'
    utm = 'E 477 577.3 · N 8 388 005.6'                     # miles con espacio fino, como ``_num``
    assert rc.texto_punto(ficha['inicio']) == f'CABECERA: UTM EPSG:32718 {utm} (lat -14.581005, lon -75.208169)'
    assert ('AA 50 mm² (AA05003D_FICHA)', 1.5, 'Cambio a AA 120 mm² (AA12003D_FICHA) + nueva terna AA 120 mm² (AA12003D_FICHA)') \
        in ficha['por_conductor']
    assert ('el existente, de igual o más sección', 0.5, 'Solo nueva terna AA 120 mm² (AA12003D_FICHA)') in ficha['por_conductor']
    assert rc.ficha_obra_de_linea({'clase': 'condensador', 'barra': 'X'}, [], []) is None
    datos = rc.resumen('con_proyecto', alternativas={}, aplicadas={'LL202': [
        {'nombre': 'terna hasta T3', 'inversion': 2441107, 'costo_anual': 303048, 'fichas': [ficha]}]})
    assert [f['alimentador'] for f in datos['fichas_de_linea']] == ['LL202']
    assert any('nueva terna en paralelo con cambio de conductor de 2.25 km, de CABECERA a 12703' in c
               for c in datos['conclusiones'])
    hecho = escribir_resumen_caso(tmp_path / 'r.docx', datos, project='P', libro=True)
    from docx import Document
    texto = '\n'.join(c.text for t in Document(tmp_path / 'r.docx').tables for f in t.rows for c in f.cells)
    assert 'Punto de inicio' in texto and utm in texto and 'Qué se hace' in texto
    from openpyxl import load_workbook
    celdas = [c for fila in load_workbook(tmp_path / hecho['xlsx']).active.iter_rows(values_only=True) for c in fila if c]
    assert 'Punto final' in celdas


def test_017_rf156_cuadro_de_perdidas_con_tramo_mas_cargado_y_caida_en_media():
    """017:RF-156 — una fila por proyecto, alimentador y caso: pérdidas en kW y %, el tramo más cargado (no un
    transformador) y la barra de MT más baja con su caída en % de la nominal; dice qué casos faltan y entra como sección
    del resumen del sistema."""
    assert hasattr(rc, 'cuadro_de_perdidas'), 'falta 017:RF-156'
    m = {'converge': True, 'cabecera_kw': 9109.5, 'perdidas_kw': 545.2,
         'elementos': [['TR_SE70050', 'ElmTr2', 120.0], ['SEC_A', 'ElmLne', 88.4], ['SEC_B', 'ElmLne', 61.0]],
         'barras': [['12703', 0.960], ['SE70022_BT', 0.895], ['12869', 1.02], ['8674', 0.0]],
         'barras_mt': ['12703', '12869', '8674'], 'sin_tension': ['8674']}
    sin = {**m, 'cabecera_kw': 9276.1, 'perdidas_kw': 1711.7, 'barras': [['12703', 0.705], ['12869', 1.0]]}
    cuadro = rc.cuadro_de_perdidas([{'project': 'P', 'caso': 'Con proyecto', 'medidas': {'LL202': m}},
                                    {'project': 'P', 'caso': 'Sin proyecto', 'medidas': {'LL202': sin}}])
    assert [r['caso'] for r in cuadro['filas']] == ['Sin proyecto', 'Con proyecto']
    con = cuadro['filas'][1]
    assert con['tramo'] == 'SEC_A' and con['cargabilidad_pct'] == pytest.approx(88.4)
    assert con['barra_mt'] == '12703' and con['u_min_pu'] == pytest.approx(0.96) and con['caida_pct'] == pytest.approx(4.0)
    assert con['perdidas_pct'] == pytest.approx(100 * 545.2 / 9109.5)
    assert cuadro['faltan'] == [{'proyecto': 'P', 'caso': 'Cargas nuevas'}]
    assert con['barras_sin_tension'] == 1, 'la isla a 0 p.u. (063:RF-43) no es la caída: se cuenta aparte'
    datos = rc.resumen_del_sistema(perdidas=cuadro)
    seccion = next(s for s in datos['secciones'] if s['caso'] == 'Pérdidas por caso')
    assert seccion['cabecera'][7] == 'Cargabilidad (%)' and seccion['cabecera'][10] == 'Caída de tensión (%)'
    assert any('sin estudio de flujo en «Cargas nuevas»' in c for c in datos['conclusiones'])


def test_017_rf157_el_cuadro_avisa_si_la_cabecera_se_aparta_de_la_calibrada():
    """017:RF-157 — PA217 (27-11): «Sin proyecto» daba 12 411 kW calibrado a 9 447 kW (una SED cambiada a mano)."""
    m = {'cabecera_kw': 12411.0, 'perdidas_kw': 793.0, 'elementos': [], 'barras': [], 'barras_mt': []}
    cuadro = rc.cuadro_de_perdidas([{'project': 'P', 'caso': 'Sin proyecto', 'medidas': {'PA217': m}},
                                    {'project': 'P', 'caso': 'Con proyecto', 'medidas': {'PA217': m}}],
                                   {('P', 'PA217'): 9447.0})
    sin, con = cuadro['filas']
    assert sin['aviso'] and '9,447' in sin['aviso'] and sin['cabecera_calibrada_kw'] == 9447.0
    assert con['aviso'] is None, 'solo «Sin proyecto» se calibra'
    assert rc.cuadro_de_perdidas([{'project': 'P', 'caso': 'Sin proyecto', 'medidas': {'PA217': {**m, 'cabecera_kw': 9500.0}}}],
                                 {('P', 'PA217'): 9447.0})['filas'][0]['aviso'] is None
