"""063:RF-36, RF-38: salidas nuevas de una SET existente, sin recrear la SET."""
from __future__ import annotations

import fake_pf
import pytest
from apoyo import cargar_herramienta

guion = cargar_herramienta('obras_pf.py', 'obras_salidas_set_063', tools_en_path=True)


def _contexto():
    app = fake_pf.proyecto(alimentadores=('AL',), cargas_por_alim=1)
    app.proyecto.Activate()
    barras = app.proyecto.GetContents('*.ElmTerm', 1)
    origen = next(b for b in barras if b.loc_name == 'AL_B0')
    destino = next(b for b in barras if b.loc_name == 'AL_B1')
    tipo = app.carpetas['equip'].GetContents('*.TypLne')[0]
    tipo.uline = 10.0
    _variacion, etapa = guion.crear_variacion(app, 'Salida_propia', '1')
    ruta = [[-14.0, -75.7], [-13.9995, -75.6995], [-14.0, -75.699]]
    app.escrituras.clear()
    app.creados.clear()
    return app, origen, destino, tipo, etapa, ruta


def test_salida_nueva_solo_crea_linea_cubiculos_y_feeder_en_etapa_del_caller():
    """063:RF-36, 063:RF-38 — conserva SET, GPS y estado del operador; ruta completa."""
    app, origen, destino, tipo, etapa, ruta = _contexto()
    estado = (app.GetActiveProject(), app.GetActiveStudyCase(), app.GetActiveScenario(),
              tuple(app.GetActiveNetworkVariations()), app.GetRecordingStage())
    informe = guion.construir_salida_set_existente(
        app, app.proyecto, origen, destino, tipo, 'Salida_MT', 2, ruta)
    assert sorted(o.GetClassName() for o in app.creados) == ['ElmFeeder', 'ElmLne', 'StaCubic', 'StaCubic']
    linea = next(o for o in app.creados if o.GetClassName() == 'ElmLne')
    feeder = next(o for o in app.creados if o.GetClassName() == 'ElmFeeder')
    assert linea.typ_id is tipo and linea.nlnum == 2 and linea.outserv == 0
    assert linea.GPScoords == ruta
    assert .150 < linea.dline < .160, 'la curva mide unos 155 m, no la recta de unos 108 m'
    cubiculos = sorted((o for o in app.creados if o.GetClassName() == 'StaCubic'), key=lambda c: c.obj_bus)
    assert [c.GetParent() for c in cubiculos] == [origen, destino]
    assert all(c.obj_id is linea for c in cubiculos)
    assert feeder.obj_id is cubiculos[0] and feeder.iorient == 0
    assert all(obj in app.creados and grabando is etapa for obj, _, _, grabando, _ in app.escrituras)
    assert estado == (app.GetActiveProject(), app.GetActiveStudyCase(), app.GetActiveScenario(),
                      tuple(app.GetActiveNetworkVariations()), app.GetRecordingStage())
    assert informe['linea'] == linea.GetFullName()
    assert informe['feeder'] == feeder.GetFullName()
    assert informe['cubiculos'] == [c.GetFullName() for c in cubiculos]
    assert informe['origen'] == origen.GetFullName() and informe['destino'] == destino.GetFullName()
    assert informe['tipo'] == tipo.GetFullName() and informe['circuitos'] == 2
    assert informe['longitud_km'] == linea.dline and informe['GPScoords'] == ruta


def test_preflight_sin_etapa_y_con_escenario_no_escribe_nada():
    """063:RF-36, 063:RF-38 — todas las salidas se validan antes de abrir una etapa."""
    app, origen, destino, tipo, _, ruta = _contexto()
    app.grabando = None
    escenario = app.proyecto.CreateObject('IntScenario', 'Operacion_actual')
    app.escenario = escenario
    app.creados.clear()
    app.escrituras.clear()
    datos = guion.validar_salida_set_existente(app.proyecto, origen, destino, tipo, 'Salida_MT', 2, ruta)
    assert not app.creados and not app.escrituras
    assert app.GetRecordingStage() is None and app.GetActiveScenario() is escenario
    assert datos['red'] == origen.GetParent().GetFullName()
    assert datos['origen'] == origen.GetFullName() and datos['destino'] == destino.GetFullName()
    assert datos['GPScoords'] == ruta and .150 < datos['longitud_km'] < .160
    assert datos['nombres_cubiculos'] == ['Cub_0_Salida_MT', 'Cub_1_Salida_MT']


@pytest.mark.parametrize('fallo,mensaje', [
    ('circuitos', 'entero positivo'), ('tension_destino', 'misma tensión nominal'),
    ('tension_tipo', 'misma tensión nominal'), ('ruta_extremo', 'extremos de la ruta'),
    ('ruta_nan', 'coordenadas GPS'), ('ruta_corta', 'al menos dos puntos'),
    ('fuera_proyecto', 'no pertenece al proyecto'), ('sin_etapa', 'etapa propia'),
    ('colision', 'Ya existe'), ('sin_GPS', 'coordenadas nativas'),
    ('escenario_activo', 'escenario debe estar inactivo'), ('etapa_ajena', 'etapa propia'),
    ('mismo_terminal', 'deben ser distintos'), ('nombre_invalido', 'nombre explícito'),
])
def test_rechaza_antes_de_crear_salida_con_datos_no_verificables(fallo, mensaje):
    """063:RF-36, 063:RF-38 — no publica obra parcial por datos de entrada inválidos."""
    app, origen, destino, tipo, _, ruta = _contexto()
    circuitos = 2
    nombre = 'Salida_MT'
    if fallo == 'circuitos':
        circuitos = True
    elif fallo == 'tension_destino':
        destino.uknom = 22.9
    elif fallo == 'tension_tipo':
        tipo.uline = 22.9
    elif fallo == 'ruta_extremo':
        ruta[-1] = [-14.1, -75.6]
    elif fallo == 'ruta_nan':
        ruta[1][0] = float('nan')
    elif fallo == 'ruta_corta':
        ruta = ruta[:1]
    elif fallo == 'fuera_proyecto':
        otro = fake_pf.nuevo_proyecto(app, app.usuario, 'Ajeno')
        tipo = otro.CreateObject('TypLne', 'Tipo_ajeno')
        tipo.uline = 10.0
    elif fallo == 'sin_etapa':
        app.grabando = None
    elif fallo == 'colision':
        origen.GetParent().CreateObject('ElmLne', 'Salida_MT')
    elif fallo == 'sin_GPS':
        destino.GPSlat, destino.GPSlon = 0., 0.
    elif fallo == 'escenario_activo':
        app.escenario = app.proyecto.CreateObject('IntScenario', 'Operacion_activa')
    elif fallo == 'etapa_ajena':
        otro = fake_pf.nuevo_proyecto(app, app.usuario, 'Ajeno')
        app.grabando = otro.CreateObject('IntSstage', 'Etapa_ajena')
    elif fallo == 'mismo_terminal':
        destino = origen
    elif fallo == 'nombre_invalido':
        nombre = 'Salida con espacios'
    app.creados.clear()
    app.escrituras.clear()
    with pytest.raises(ValueError, match=mensaje):
        guion.construir_salida_set_existente(
            app, app.proyecto, origen, destino, tipo, nombre, circuitos, ruta)
    assert not app.creados and not app.escrituras
