"""Spec 027, RF-72 (T33): «el proyecto entero» llega hasta los entregables de todos los módulos. Tras el informe, el PIT,
el VAD y el VNR son etapas opcionales con lo que requieren; si falta su dato (sin libro PIT, sin datos VAD, sin los del
VNR), se saltan con su motivo, nunca con un error, y el proyecto sigue con las demás y con sus puntos de control.

Es la prueba del orquestador, con una web falsa que hace de API y datos sintéticos (P13). La lista que ve el operador
antes del clic sale de la misma orden con lo que leen las órdenes sueltas de cada módulo.
"""
from __future__ import annotations

from types import SimpleNamespace

from convertersmartgrid.aplicacion.asistente.ejecutor import ClienteWeb

VNR = {'sector': 'urbano_media_baja', 'sector_sicodi': '2', 'resolucion': '158-2023-OS/CD', 'anio': 2025, 'moneda': 'USD'}
CONTEXTO = {'workspace_id': 'w', 'source_fingerprint': 'f1', 'source_mode': 'txt'}


class _Respuesta:
    def __init__(self, codigo, datos):
        self.status_code, self._datos, self.content, self.text = codigo, datos, b'x', str(datos)

    def json(self):
        return self._datos


class WebFalsa:
    """Cada POST es un trabajo que termina bien."""

    def __init__(self):
        self.llamadas = []

    def request(self, metodo, url, **kw):
        ruta = url.split('/api/workspaces/w', 1)[-1] if '/api/workspaces/w' in url else url.split('/api', 1)[-1]
        self.llamadas.append((metodo, ruta, kw.get('json') or kw.get('data')))
        if ruta.startswith('/jobs/'):
            return _Respuesta(200, {'id': ruta[6:], 'status': 'done', 'result': {'vnr_total': 10.0, 'ok': ruta}})
        return _Respuesta(202, {'id': ruta.strip('/').replace('/', '_'), 'status': 'queued'})


def _orquestador():
    from convertersmartgrid.aplicacion.asistente import orquestador

    assert hasattr(orquestador, 'ETAPAS_PROYECTO_ENTERO'), 'el proyecto entero no llega a los módulos (PIT, VAD, VNR)'
    return orquestador


def test_027_rf72_el_proyecto_entero_sigue_con_el_pit_el_vad_y_el_vnr_opcionales():
    """027:RF-72 — tras el informe, las tres etapas de los módulos, opcionales y con lo que requieren."""
    o = _orquestador()
    assert o.ETAPAS_PROYECTO_ENTERO[:len(o.ETAPAS)] == o.ETAPAS
    modulos = o.ETAPAS_PROYECTO_ENTERO[len(o.ETAPAS):]
    assert [(e.nombre, e.tarea) for e in modulos] == [('pit', 'pit_expediente'), ('vad', 'vad_empresa_modelo'),
                                                      ('vnr', 'vnr_estudio')]
    assert all(e.opcional and e.requiere == (e.nombre,) for e in modulos)


def test_070_rf51_la_lista_del_proyecto_entero_no_ensena_citas_internas():
    """070:RF-51 — la lista que lee el operador antes del clic no lleva las citas del catálogo de tareas (la e2e F04 del
    proyecto entero las encontraba a la vista); la descripción del catálogo no cambia, porque entra en las huellas."""
    import re

    o = _orquestador()
    lista = o.lista_de_etapas({'sistema': 'S1', 'periodo': '2026-07', 'vnr': VNR}, {}, CONTEXTO,
                              etapas=o.ETAPAS_PROYECTO_ENTERO)
    cita = re.compile(r'RF-\d|\b\d{3}:RF|\(specs? \d{3}\b|\b\d{3}, T\d+')
    vistas = [f['descripcion'] for f in lista['etapas'] if cita.search(f['descripcion'])]
    assert vistas == [], vistas
    assert any(cita.search(o.TAREAS[e.tarea].descripcion) for e in o.ETAPAS_PROYECTO_ENTERO), 'el catálogo cambió'


def test_027_rf72_sin_su_dato_un_modulo_se_salta_con_su_motivo_y_sigue_con_los_demas(tmp_path):
    """027:RF-72 — sin libro PIT y con el VAD a medias, los dos se saltan con su motivo y el VNR, que tiene lo suyo, va
    por su ruta; nada falla. El punto de control guarda cada omisión y, al retomar, nada se repite."""
    o = _orquestador()
    web = WebFalsa()
    control = o.PuntoDeControl.abrir(tmp_path / 'agente.json')
    datos = {'vad': {'estudio': 'E1'}, 'vnr': VNR}
    r = o.ejecutar_proyecto(datos, cliente=ClienteWeb(web, 'http://x', 'w', intervalo_s=0), control=control,
                            proceso=lambda *_a: {'codigo': 0}, etapas=o.ETAPAS_MODULOS)
    assert r['completo'] is True
    etapas = r['etapas']
    assert etapas['pit']['estado'] == 'omitida' and 'libro PIT' in etapas['pit']['resultado']['motivo']
    assert etapas['vad']['estado'] == 'omitida' and 'ficheros' in etapas['vad']['resultado']['motivo']
    assert etapas['vnr']['estado'] == 'hecha'
    posts = [(ruta, cuerpo) for metodo, ruta, cuerpo in web.llamadas if metodo == 'POST']
    assert [ruta for ruta, _c in posts] == ['/vnr/estudio'] and posts[0][1]['sector_sicodi'] == '2'
    web2 = WebFalsa()
    o.ejecutar_proyecto(datos, cliente=ClienteWeb(web2, 'http://x', 'w', intervalo_s=0),
                        control=o.PuntoDeControl.abrir(tmp_path / 'agente.json'), proceso=lambda *_a: {'codigo': 0},
                        etapas=o.ETAPAS_MODULOS)
    assert not [m for m, *_r in web2.llamadas if m == 'POST'], 'al retomar se repitió un módulo'


def test_027_rf72_un_fichero_del_modulo_que_no_esta_lo_salta_con_su_nombre(tmp_path):
    """027:RF-72 — el PIT con su libro y su proyección nombrados, pero sin el libro en la máquina: se salta, y el
    motivo nombra el fichero, en la lista que ve el operador antes del clic."""
    o = _orquestador()
    proyeccion = tmp_path / 'proyeccion.json'
    proyeccion.write_text('{}', encoding='utf-8')
    pit = {'workspace_id': 'w', 'libro_red': str(tmp_path / 'red_area.xlsx'), 'proyeccion': str(proyeccion),
           'area': 'AD99', 'anios': [2027, 2028], 'periodo': '2027-2028'}
    lista = o.lista_de_etapas({'sistema': 'S1', 'periodo': '2026-07', 'pit': pit, 'vnr': VNR}, {}, CONTEXTO,
                              etapas=o.ETAPAS_PROYECTO_ENTERO)
    por = {e['nombre']: e for e in lista['etapas']}
    assert por['pit']['estado'] == 'se_omitira' and 'red_area.xlsx' in por['pit']['motivo']
    assert por['vad']['estado'] == 'se_omitira' and por['vad']['motivo'] == o.MOTIVO_SIN_DATO['vad']
    assert por['vnr']['estado'] == 'pendiente' and 'vnr' in lista['etapas_escritura']
    (tmp_path / 'red_area.xlsx').write_bytes(b'libro')
    otra = o.lista_de_etapas({'sistema': 'S1', 'periodo': '2026-07', 'pit': pit, 'vnr': VNR}, {}, CONTEXTO,
                             etapas=o.ETAPAS_PROYECTO_ENTERO)
    assert {e['nombre']: e['estado'] for e in otra['etapas']}['pit'] == 'pendiente'
    assert otra['confirmacion'] != lista['confirmacion'], 'la huella no ata lo que el operador vio'


def _plan(texto, datos):
    from convertersmartgrid.aplicacion.asistente.plan import Plan

    return Plan('p1', texto, 'proyecto_entero', True, 'etapas', datos=dict(datos))


def _svc(o):
    return SimpleNamespace(carpeta_de_libros=lambda ws: None, agente_proyecto_lista=lambda ws, datos, omitir=None: (
        o.lista_de_etapas(datos, {}, CONTEXTO, etapas=o.ETAPAS_PROYECTO_ENTERO, omitir=omitir)))


def test_027_rf72_la_orden_del_proyecto_entero_lee_los_modulos_y_ensena_su_camino(tmp_path):
    """027:RF-72 / 026:RF-48 — de la orden: sin datos de los módulos, la lista los salta con su motivo; con los del VNR
    en la orden, el VNR va. El plan lleva el camino entero con su motivo, y lo que falta a un módulo no impide el resto."""
    o = _orquestador()
    from convertersmartgrid.presentacion.web import asistente_operacion as ao

    ws = SimpleNamespace(id='w', root=tmp_path)
    datos = {'sistema': 'S1', 'periodo': '2026-07', 'ruta': str(tmp_path / 'libros')}
    plan, extras = _plan('haz el proyecto entero del sistema S1 con 2026-07', datos), {}
    ao._proyecto_entero(_svc(o), ws, plan, extras)
    assert plan.faltan == [], plan.faltan
    palabras = ' | '.join(extras['etapas_en_palabras'])
    for nombre in ('pit', 'vad', 'vnr'):
        assert f'{nombre} (se omitirá: {o.MOTIVO_SIN_DATO[nombre]}' in palabras, palabras
    camino = extras.get('camino') or {}
    assert camino.get('siguiente') == 'fuente' and camino['motivo'] in plan.razonamiento
    con_vnr = _plan('haz el proyecto entero del sistema S1 con 2026-07, el vnr con sector SICODI 2, '
                    'resolución 158-2023-OS/CD y año 2025', datos)
    extras = {}
    ao._proyecto_entero(_svc(o), ws, con_vnr, extras)
    vnr = next(f for f in extras['camino']['etapas'] if f['etapa'] == 'vnr')
    assert vnr['estado'] == 'pendiente' and vnr['entradas']['vnr']['sector_sicodi'] == '2'
    assert 'vnr' in extras['camino']['confirma_el_operador']


def test_027_rf72_026_rf48_la_lista_de_la_web_trae_los_modulos_saltados_con_su_motivo_y_el_camino(tmp_path, monkeypatch):
    """027:RF-72 y 026:RF-48 (revisión del montaje, ce 19-11): «Ver las etapas» del proyecto entero, que no necesita el
    intérprete, trae los módulos sin su dato como «se_omitira» con su motivo, y el camino que propone el asistente
    (siguiente etapa y por qué), para que la web los enseñe sin modelo."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        wid = c.post('/api/workspaces').json()['id']
        lista = c.post(f'/api/workspaces/{wid}/agente/proyecto/lista',
                       json={'sistema': 'Sistema sintético', 'periodo': '2026-07', 'reiniciar': True}).json()
    modulos = {e['nombre']: e for e in lista['etapas'] if e['nombre'] in ('pit', 'vad', 'vnr')}
    assert set(modulos) == {'pit', 'vad', 'vnr'}, [e['nombre'] for e in lista['etapas']]
    assert all(e['estado'] == 'se_omitira' and e['motivo'] for e in modulos.values()), modulos
    camino = lista.get('camino')
    assert camino and camino['motivo'].startswith(('Siguiente etapa', 'Nada que hacer')), camino
    assert camino['calcula'] is False
