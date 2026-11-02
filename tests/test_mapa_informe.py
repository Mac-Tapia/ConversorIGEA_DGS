"""Spec 017, RF-11b — imágenes del informe con el GPS y los resultados del flujo."""
from __future__ import annotations

import pytest
from PIL import Image

from convertersmartgrid.mapa_informe import MapaError, dibujar, imagenes_del_estado

GEO = {'cabecera': 'CAB',
       'barras': [['CAB', -14.0, -75.70, 1.0, 10.0], ['N1', -14.01, -75.69, 0.97, 10.0],
                  ['SED1_BT', -14.02, -75.68, 0.80, 0.22]],
       'tramos': [['L1', [[-14.0, -75.70], [-14.01, -75.69]], 40.0],
                  ['L2', [[-14.01, -75.69], [-14.015, -75.685], [-14.02, -75.68]], 112.0]]}


def test_tres_imagenes_de_un_estado(tmp_path):
    """017:RF-11b / 017:RF-116 — ubicación, tensión y cargabilidad en PNG, con las bandas."""
    rutas = imagenes_del_estado(GEO, tmp_path, 'CA', estado='estado actual', alimentador='AL01',
                                bandas_tension=(85, 90, 95, 105), bandas_carga=(80, 90, 95, 105, 150))
    assert set(rutas) == {'ubicacion', 'tension', 'cargabilidad'}
    for ruta in rutas.values():
        with Image.open(ruta) as img:
            assert img.format == 'PNG' and img.size == (1600, 1150)
            colores = {c for _, c in img.getcolors(1 << 20)}
            assert len(colores) > 3, 'la imagen tiene dibujo, no solo fondo'


def test_la_tension_baja_sale_en_rojo_y_la_sobrecarga_tambien(tmp_path):
    """017:RF-116 — la barra a 0,80 p.u. (banda < 85 %) y el tramo al 112 % (105–150 %)."""
    for modo in ('tension', 'cargabilidad'):
        ruta = dibujar(GEO, modo, tmp_path / f'{modo}.png', titulo=modo)
        with Image.open(ruta) as img:
            colores = {c for _, c in img.getcolors(1 << 20)}
        assert (200, 30, 30) in colores


def test_sin_geografia_lo_dice(tmp_path):
    """017:RF-11b — sin GPS guardado no se inventa una imagen."""
    with pytest.raises(MapaError, match='geografía'):
        dibujar({'barras': [], 'tramos': []}, 'tension', tmp_path / 'x.png', titulo='x')


def test_planos_muestran_obras_y_problemas_residuales_en_los_tres_modos(tmp_path):
    """063:RF-35 — una salida nueva sobrecargada conserva obra y alarma simultáneas."""
    import copy
    import json

    geo = copy.deepcopy(GEO)
    geo['barras'].append(['SET_MT', -14.004, -75.695, 1.0, 10.0])
    geo['tramos'].append(['SALIDA', [[-14.004, -75.695], [-14.01, -75.69]], 40,
                          'SET_MT', 'N1', 'TIPO', 1.0])
    red = {'tensiones_por_nivel': {'mt': [
        {'nombre': 'N1', 'u_pu': 0.97, 'fases': {'A': 0.94, 'B': 0.97, 'C': 1.06}}]},
        'medida': {'elementos': [['SALIDA', 'ElmLne', 120.0], ['NO_GPS', 'ElmTr2', 110.0]],
                   'bancos': [{'nombre': 'B1', 'barra': 'SED1_BT', 'kvar': 300,
                               'escalones': 2, 'en_servicio': True}]}}
    rutas = imagenes_del_estado(geo, tmp_path, 'con', estado='Con proyecto', alimentador='F',
                               red=red, referencia={'geo_proyecto': GEO, 'red_proyecto': {'medida': {}}},
                               limites=(0.95, 1.05, 100), obras_activas=['O'],
                               obras_aplicadas=[{'variacion': 'O', 'obra': {'clase': 'terna', 'tramos': ['L1']}}],
                               cliente=('N1', 'Cliente de prueba'))
    assert 'detalle' in rutas
    for modo in ('ubicacion', 'tension', 'cargabilidad'):
        with Image.open(rutas[modo]) as img:
            colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
            evidencia = json.loads(img.info['evidencia_plano'])
        assert (200, 0, 160) in colores, 'la obra sigue visible en las vistas de resultados'
        assert (190, 20, 20) in colores, 'la sobrecarga sigue visible sobre una salida nueva'
        assert evidencia['tension_fuera'] == ['N1']
        assert evidencia['sobrecargas'] == ['SALIDA', 'NO_GPS']
        assert evidencia['sin_localizar'] == ['NO_GPS']
        assert any('tensión fuera' in x for x in evidencia['leyenda'])
        assert any('sobrecarga' in x for x in evidencia['leyenda'])
        assert any('cliente' in x for x in evidencia['leyenda'])


def test_comparacion_no_atribuye_obra_inactiva_ni_carga_nueva_a_refuerzo(tmp_path):
    """063:RF-35 — cargas ya presentes en la referencia no son obras de la solución."""
    import json

    rutas = imagenes_del_estado(GEO, tmp_path, 'sin', estado='Actual', alimentador='F',
                               red={'medida': {'elementos': [], 'bancos': []}},
                               referencia={'geo_proyecto': GEO, 'red_proyecto': {'medida': {}}},
                               obras_activas=[], obras_aplicadas=[
                                   {'variacion': 'INACTIVA', 'obra': {'clase': 'terna', 'tramos': ['L1']}}],
                               limites=(0.95, 1.05, 100), cliente=('N1', 'Punto evaluado'))
    with Image.open(rutas['ubicacion']) as img:
        colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
        evidencia = json.loads(img.info['evidencia_plano'])
    assert (200, 0, 160) not in colores
    assert not evidencia['obras_tramos']
    assert evidencia['cliente'] == 'N1'


def test_planos_comparten_encuadre_y_no_modifican_datos_guardados(tmp_path):
    """063:RF-35 — los tres casos conservan escala y la evidencia nativa intacta."""
    import copy
    import json

    original = copy.deepcopy(GEO)
    encuadre = {'barras': GEO['barras'] + [['EXTREMO', -14.04, -75.66, 1.0, 10]], 'tramos': []}
    rutas = imagenes_del_estado(GEO, tmp_path, 'a', estado='A', alimentador='F',
                               encuadre=encuadre, limites=(0.95, 1.05, 100))
    with Image.open(rutas['ubicacion']) as img:
        evidencia = json.loads(img.info['evidencia_plano'])
    assert evidencia['encuadre'] == [-14.04, -75.7, -14.0, -75.66]
    assert GEO == original


def test_transformador_se_localiza_solo_por_su_terminal_nativo(tmp_path):
    """063:RF-35 — un vínculo explícito localiza la sobrecarga de la SED."""
    import json

    rutas = imagenes_del_estado(GEO, tmp_path, 'tr', estado='Con proyecto', alimentador='F',
                               red={'medida': {'elementos': [['TR', 'ElmTr2', 120]]}},
                               limites=(0.95, 1.05, 100),
                               vinculos_equipos={'TR': {'barra': 'N1'}})
    with Image.open(rutas['ubicacion']) as img:
        evidencia = json.loads(img.info['evidencia_plano'])
        colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
    assert evidencia['sobrecargas'] == ['TR']
    assert evidencia['sin_localizar'] == []
    assert (190, 20, 20) in colores


def test_obra_corta_sobrecargada_conserva_ambos_canales_visuales(tmp_path):
    """063:RF-35 — una alarma no borra el refuerzo aunque mida menos de un guion."""
    import copy

    geo = copy.deepcopy(GEO)
    geo['tramos'].append(['NUEVA', [[-14.004, -75.7], [-14.00401, -75.7]], 120])
    rutas = imagenes_del_estado(geo, tmp_path, 'corta', estado='Con proyecto', alimentador='F',
                               referencia={'geo_proyecto': GEO}, obras_activas=['O'],
                               limites=(0.95, 1.05, 100))
    with Image.open(rutas['ubicacion']) as img:
        colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
    assert (200, 0, 160) in colores
    assert (190, 20, 20) in colores


@pytest.mark.parametrize('carga', [80.0, 120.0])
def test_transformador_reforzado_visible_con_y_sin_alarma(tmp_path, carga):
    """063:RF-35 — sustituir el TR sigue siendo una obra cuando ya cumple capacidad."""
    import json

    rutas = imagenes_del_estado(
        GEO, tmp_path, 'refuerzo', estado='Con proyecto', alimentador='F',
        red={'medida': {'elementos': [['TR_NATIVO', 'ElmTr2', carga]]}},
        limites=(0.95, 1.05, 100), vinculos_equipos={'TR_NATIVO': {'barra': 'N1'}},
        obras_activas=['O_TR'], obras_aplicadas=[
            {'variacion': 'O_TR', 'obra': {'clase': 'transformador', 'elemento': 'TR_NATIVO'}}])
    for modo in ('ubicacion', 'tension', 'cargabilidad'):
        with Image.open(rutas[modo]) as img:
            colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
            evidencia = json.loads(img.info['evidencia_plano'])
        assert (115, 55, 150) in colores
        assert evidencia['obras_transformadores'] == ['TR_NATIVO']
        assert any('TR reforzado' in x for x in evidencia['leyenda'])
        assert ((190, 20, 20) in colores) == (carga > 100)


def test_transformador_sin_vinculo_no_inventa_posicion(tmp_path):
    """063:RF-35 — el nombre del TR no sustituye un vínculo nativo de terminal."""
    import json

    rutas = imagenes_del_estado(
        GEO, tmp_path, 'sin_geo', estado='Con proyecto', alimentador='F', limites=(0.95, 1.05, 100),
        obras_activas=['O_TR'], obras_aplicadas=[
            {'variacion': 'O_TR', 'obra': {'clase': 'transformador', 'elemento': 'N1'}}])
    with Image.open(rutas['ubicacion']) as img:
        colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
        evidencia = json.loads(img.info['evidencia_plano'])
    assert (115, 55, 150) not in colores
    assert evidencia['obras_sin_localizar'] == ['N1']


@pytest.mark.parametrize('activa', [True, False])
def test_cargas_nuevas_por_variacion_y_terminal_explicito(tmp_path, activa):
    """063:RF-35 — cada carga activa tiene marcador propio sin ocultar la tensión fuera."""
    import json

    rutas = imagenes_del_estado(
        GEO, tmp_path, 'cargas', estado='Cargas nuevas' if activa else 'Actual', alimentador='F',
        limites=(0.95, 1.05, 100), vinculos_equipos={'NUEVO_CLIENTE': {'barra': 'SED1_BT'}},
        obras_activas=['CARGA'] if activa else [], obras_aplicadas=[
            {'variacion': 'CARGA', 'obra': {'clase': 'carga_nueva', 'elemento': 'NUEVO_CLIENTE'}}])
    with Image.open(rutas['ubicacion']) as img:
        colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
        evidencia = json.loads(img.info['evidencia_plano'])
    assert ((0, 110, 75) in colores) == activa
    assert evidencia['cargas_nuevas'] == (['NUEVO_CLIENTE'] if activa else [])
    assert (235, 110, 0) in colores


@pytest.mark.parametrize('geometria', [[], [[-14.01, -75.69], [-14.015, -75.685]]])
def test_transferencia_abierta_no_representa_red_energizada_sin_geometria(tmp_path, geometria):
    """063:RF-35 — una apertura declarada se registra sin inventar un trazado de la obra."""
    import json

    rutas = imagenes_del_estado(
        GEO, tmp_path, 'transferencia', estado='Con proyecto', alimentador='F', limites=(0.95, 1.05, 100),
        obras_activas=['O_TRANSFERIR'], obras_aplicadas=[
            {'variacion': 'O_TRANSFERIR', 'obra': {'clase': 'transferencia', 'elemento': 'L2',
                                               'outserv': 1, 'geometria': geometria}}])
    with Image.open(rutas['ubicacion']) as img:
        evidencia = json.loads(img.info['evidencia_plano'])
        colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
    assert evidencia['transferencias'] == [{'elemento': 'L2', 'dibujada': bool(geometria)}]
    assert ((85, 95, 110) in colores) == bool(geometria)
    assert any('abierto por transferencia' in x for x in evidencia['leyenda'])


def test_variacion_de_carga_no_convierte_su_acometida_en_refuerzo(tmp_path):
    """063:RF-35 — distinguir cargas de obras al recibir todas las variaciones activas."""
    import copy
    import json

    geo = copy.deepcopy(GEO)
    geo['tramos'].append(['ACOMETIDA', [[-14.004, -75.7], [-14.00401, -75.7]], 20])
    rutas = imagenes_del_estado(
        geo, tmp_path, 'solo_carga', estado='Cargas nuevas', alimentador='F',
        limites=(0.95, 1.05, 100), referencia={'geo_proyecto': GEO},
        vinculos_equipos={'CARGA': {'barra': 'N1'}}, obras_activas=['V_CARGA'], obras_aplicadas=[
            {'variacion': 'V_CARGA', 'obra': {'clase': 'carga_nueva', 'elemento': 'CARGA'}}])
    with Image.open(rutas['ubicacion']) as img:
        evidencia = json.loads(img.info['evidencia_plano'])
    assert evidencia['obras_tramos'] == []


def test_carga_del_solicitante_conserva_marcador_junto_al_rombo(tmp_path):
    """063:RF-35 — el rombo del solicitante no tapa el marcador de su carga nueva."""
    rutas = imagenes_del_estado(
        GEO, tmp_path, 'cliente_carga', estado='Con proyecto', alimentador='F',
        limites=(0.95, 1.05, 100), cliente=('N1', 'Solicitante'),
        vinculos_equipos={'CARGA': {'barra': 'N1'}}, obras_activas=['V_CARGA'], obras_aplicadas=[
            {'variacion': 'V_CARGA', 'obra': {'clase': 'carga_nueva', 'elemento': 'CARGA'}}])
    with Image.open(rutas['ubicacion']) as img:
        colores = {c for _, c in img.crop((0, 70, 1260, 1150)).getcolors(1 << 20)}
        # N1 está en el centro de la geografía de esta fixture: (635, 595).
        marcador = {c for _, c in img.crop((622, 582, 648, 608)).getcolors(1 << 20)}
    assert (0, 110, 75) in marcador
    assert (0, 110, 75) in colores
    assert (220, 0, 0) in colores


def test_esquema_no_convergente_no_declara_cero_violaciones(tmp_path):
    """063:RF-11, RF-35: una referencia fallida conserva conexiones, sin métricas falsas."""
    import json

    rutas = imagenes_del_estado(
        GEO, tmp_path, 'no_converge', estado='Cargas nuevas: no converge', alimentador='F',
        limites=(0.95, 1.05, 100), red={'medida': {'converge': False}},
        vinculos_equipos={'CARGA': {'barra': 'N1'}}, obras_activas=['V_CARGA'], obras_aplicadas=[
            {'variacion': 'V_CARGA', 'obra': {'clase': 'carga_nueva', 'elemento': 'CARGA'}}])
    assert set(rutas) == {'ubicacion'}
    with Image.open(rutas['ubicacion']) as img:
        evidencia = json.loads(img.info['evidencia_plano'])
    assert evidencia['sin_resultados'] is True
    assert evidencia['tension_fuera'] is None and evidencia['sobrecargas'] is None
    assert not any('tensión fuera' in texto or 'sobrecarga' in texto for texto in evidencia['leyenda'])
    assert len(evidencia['cargas_nuevas']) == 1
