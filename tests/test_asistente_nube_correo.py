"""Spec 070, T16: el asistente prepara la nube y el correo, y el clic del operador en su tarjeta lo hace (RF-79 a RF-83).

El asistente lee las cuentas y los recibos y pide la vista previa del correo; enviar, publicar, compartir, importar y
conectar siguen siendo rutas que solo acepta el navegador (109:RF-15, 110:RF-5, RF-6). La prueba recorre la web real con
la nube simulada: la orden escrita, el borrador en la tarjeta, el rechazo de un programa y el clic que lo envía.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from correo_simulado import sin_red  # noqa: F401
from nube_simulada import CONFIG_PRUEBA, NubeSimulada
from test_correo_web import ORIGEN

from convertersmartgrid.dominio import salidas_red
from convertersmartgrid.aplicacion.asistente import tareas
from convertersmartgrid.aplicacion.asistente.equipo import GobiernoEquipo, PermisoDenegado
from convertersmartgrid.aplicacion.asistente.interprete import _por_frase_literal
from convertersmartgrid.presentacion.web import services

ORDENES = {
    'enviar_informe': ('envía el informe por correo a cliente@otra.test', 'mándale por mail el informe al revisor'),
    'publicar_nube': ('publica la salida en google drive', 'sube los resultados a onedrive'),
    'compartir_nube': ('comparte el expediente publicado con revisor@otra.test', 'dale acceso al expediente en drive'),
    'importar_nube': ('trae el libro de clientes desde google drive', 'importa el archivo desde onedrive'),
    'conectar_nube': ('conecta mi cuenta de google', 'vincula mi onedrive'),
}
ACCIONES = ('/nube/importar', '/nube/publicar', '/nube/compartir', '/nube/google/conectar',
            '/api/workspaces/w1/nube/vinculos/v/aceptar', '/nube/versiones', '/nube/vinculos/v/traer')


def test_070_rf79_cinco_tareas_que_solo_leen_y_se_reconocen_por_su_frase():
    """070:RF-79, 070:RF-84 — enviar, publicar, compartir, importar y conectar están en el catálogo, solo leen (el asistente no
    espera a nadie para prepararlas) y se reconocen por su frase mientras el modelo en uso no las conozca."""
    assert set(ORDENES) == set(getattr(tareas, 'TAREAS_107_112_NUBE', ())) <= set(tareas.TAREAS)
    for tarea, ordenes in ORDENES.items():
        assert tareas.EFECTOS[tarea] == (tareas.LEE,) and not tareas.TAREAS[tarea].escribe, tarea
        assert not tareas.requiere_confirmacion(tarea), tarea
        for orden in ordenes:
            assert _por_frase_literal(orden, None) == tarea, orden


def _gobierno(tarea: str) -> GobiernoEquipo:
    g = object.__new__(GobiernoEquipo)
    g.rol, g.tarea, g.listo, g.confirmado, g.lectura = 'operador', tarea, True, True, True
    g._activa = False
    g._validar = lambda: None        # sin espacio de prueba: tras la frontera de la nube decide la regla de siempre
    return g


@pytest.mark.parametrize('tarea', sorted(ORDENES))
def test_070_rf81_el_asistente_solo_lee_la_nube_y_pide_previas(tarea):
    """070:RF-81, 109:RF-15 — en sus tareas de la nube, el asistente pasa la frontera de la nube solo para leer y pedir
    previas; conectar, importar, publicar, compartir y aceptar se cortan aunque el plan esté confirmado."""
    lectura_de_la_nube = getattr(salidas_red, 'lectura_de_la_nube', None)
    assert callable(lectura_de_la_nube), 'falta lo que dice qué puede leer de la nube el asistente'
    g = _gobierno(tarea)
    for ruta in ACCIONES:
        with pytest.raises(PermisoDenegado, match='nube'):
            g.autorizar_peticion('POST', ruta, {'json': {}})
    with pytest.raises(PermisoDenegado, match='nube'):
        g.autorizar_peticion('DELETE', '/nube/google', {})
    for metodo, ruta in (('GET', '/nube/cuentas'), ('GET', '/api/nube/proveedores'), ('GET', '/nube/recibos'),
                         ('POST', '/nube/publicar/previa'), ('POST', '/nube/compartir/previa')):
        assert lectura_de_la_nube(metodo, ruta), ruta
        with pytest.raises(PermisoDenegado) as fuera_de_paso:          # sin paso activo, lo corta la regla de siempre
            g.autorizar_peticion(metodo, ruta, {'json': {}} if metodo == 'POST' else {})
        assert 'nube' not in str(fuera_de_paso.value), (ruta, fuera_de_paso.value)


def test_070_rf81_las_demas_tareas_no_leen_la_nube_y_nada_se_cuela_por_la_ruta():
    """070:RF-81 — una tarea que no es de la nube no la lee; y una ruta torcida no pasa por lectura."""
    lectura_de_la_nube = getattr(salidas_red, 'lectura_de_la_nube', None)
    assert callable(lectura_de_la_nube), 'falta lo que dice qué puede leer de la nube el asistente'
    with pytest.raises(PermisoDenegado, match='nube'):
        _gobierno('estado').autorizar_peticion('GET', '/nube/cuentas', {})
    for metodo, ruta in (('GET', '/nube/copias/ab12'), ('GET', '/nube/selector/google'), ('POST', '/nube/cuentas'),
                         ('GET', '/api/workspaces/w/nube/../nube/cuentas'), ('PUT', '/nube/publicar/previa')):
        assert not lectura_de_la_nube(metodo, ruta), (metodo, ruta)


# ------------------------------------------------------------------ la web real, de la orden al clic
@pytest.fixture
def web(tmp_path, monkeypatch, sin_red):  # noqa: F811
    from convertersmartgrid.adaptadores.nube import cuentas as modulo_cuentas
    from convertersmartgrid.presentacion.web.app import create_app

    sim = NubeSimulada()
    ruta_config = tmp_path / 'config' / 'nube.json'
    ruta_config.parent.mkdir(parents=True)
    ruta_config.write_text(json.dumps(CONFIG_PRUEBA), encoding='utf-8')
    original = modulo_cuentas.Cuentas.__init__

    def iniciar(self, *, config=None, cofre=None, adaptador=None, dormir=None):
        original(self, config=config or ruta_config, cofre=cofre or tmp_path / 'cofre', adaptador=adaptador or sim,
                 dormir=dormir or (lambda _s: None))

    monkeypatch.setattr(modulo_cuentas.Cuentas, '__init__', iniciar)
    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))     # sin modelo: la frase literal
    services._ASISTENTE_PLANES.clear()
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app, sim
    services._ASISTENTE_PLANES.clear()


def _esperar(cliente, trabajo: dict) -> dict:
    limite = time.monotonic() + 60
    while time.monotonic() < limite:
        r = cliente.get(f"/api/jobs/{trabajo['id']}").json()
        if r['status'] in ('done', 'failed', 'cancelled', 'parcial'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def _orden(cliente, wid: str, texto: str) -> dict:
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    return fin['result']


def _conectar_para_enviar(cliente, sim, wid: str) -> None:
    url = cliente.post(f'/api/workspaces/{wid}/nube/google/conectar', json={'alcance': 'enviar'}, headers=ORIGEN)
    assert url.status_code == 200, url.text
    r = cliente.get('/nube/retorno', params=sim.autorizar(url.json()['url'], 'operador@ejemplo.org'),
                    follow_redirects=False)
    assert 'nube=conectada' in r.headers['location'], r.headers['location']


def _informe(tmp_path, app, wid: str) -> str:
    from test_informe_docx import _config, _factibilidad

    from convertersmartgrid.adaptadores.informe_docx import escribir_informe_factibilidad

    ws = app.state.store.get(wid)
    Path(ws.out_dir).mkdir(parents=True, exist_ok=True)
    destino = Path(ws.out_dir) / 'informe_factibilidad_AL02_X.docx'
    escribir_informe_factibilidad(_config(tmp_path), destino, _factibilidad(tmp_path))
    return destino.name


def test_070_rf80_rf81_rf82_la_orden_deja_el_borrador_y_solo_el_clic_lo_envia(web, tmp_path):
    """070:RF-80, 070:RF-81, 070:RF-82, 110:RF-6 — «envía el informe por correo a …» deja en la tarjeta el borrador exacto (cuenta,
    destinatario, adjuntos con huella y firma) sin enviar nada; el ejecutor no puede confirmarlo, y el clic del navegador
    con esa firma lo envía y deja su recibo."""
    cliente, app, sim = web
    wid = cliente.post('/api/workspaces').json()['id']
    _conectar_para_enviar(cliente, sim, wid)
    informe = _informe(tmp_path, app, wid)

    r = _orden(cliente, wid, 'envía el informe por correo a cliente@otra.test')
    plan = r['plan']
    assert plan['tarea'] == 'enviar_informe' and plan['listo'], plan
    assert 'trabajo' in r, 'preparar el borrador no espera a nadie: solo lee'
    hecho = _esperar(cliente, r['trabajo'])
    assert hecho['status'] == 'done', hecho.get('error')
    tarjeta = hecho['result']['tarjeta']
    previa = tarjeta['previa']
    assert tarjeta['tipo'] == 'enviar_informe' and previa['para'] == ['cliente@otra.test']
    assert previa['cuenta'] == 'operador@ejemplo.org' and len(previa['firma']) == 64
    assert previa['adjuntos'] and all(len(a['sha256']) == 64 for a in previa['adjuntos'])
    assert 'Confirmar y enviar' in hecho['result']['texto']
    historial = cliente.get(f'/api/workspaces/{wid}/correo/historial', params={'informe': informe}).json()
    assert historial['envios'] == [], 'sin el clic no sale nada'

    # El ejecutor (un programa, con el token de la web) no confirma aunque tenga la firma.
    programa = cliente.post(f"/api/workspaces/{wid}/correo/{previa['borrador']}/confirmar",
                            json={'firma': previa['firma']}, headers={'X-CSG-Token': 'tok-prog'})
    assert programa.status_code == 403, programa.text

    # El clic del operador en la tarjeta: el navegador, con su Origin y la firma que vio.
    clic = cliente.post(f"/api/workspaces/{wid}/correo/{previa['borrador']}/confirmar", json={'firma': previa['firma']},
                        headers=ORIGEN)
    assert clic.status_code == 200, clic.text
    assert _esperar(cliente, clic.json()['trabajo'])['status'] == 'done'
    recibo = cliente.get(f"/api/workspaces/{wid}/correo/envios/{clic.json()['clave']}").json()
    assert recibo['borrador'] == previa['borrador'] and recibo['estado'] in ('aceptado', 'rechazado', 'desconocido')
    envios = cliente.get(f'/api/workspaces/{wid}/correo/historial', params={'informe': informe}).json()['envios']
    assert [e['clave'] for e in envios] == [clic.json()['clave']]


def test_070_rf80_sin_destinatario_o_sin_informe_lo_dice_el_plan(web):
    """070:RF-80 — sin dirección en la orden o sin informe cerrado, el plan dice qué falta y no prepara nada."""
    cliente, _app, _sim = web
    wid = cliente.post('/api/workspaces').json()['id']
    plan = _orden(cliente, wid, 'envía el informe por correo')['plan']
    assert plan['tarea'] == 'enviar_informe' and not plan['listo']
    faltan = ' '.join(plan['faltan'])
    assert 'informe cerrado' in faltan and 'dirección de correo' in faltan


@pytest.mark.parametrize('tarea, texto', [('publicar_nube', 'publica la salida en google drive'),
                                           ('compartir_nube', 'comparte el expediente publicado con revisor@otra.test'),
                                           ('importar_nube', 'trae el libro de clientes desde google drive'),
                                           ('conectar_nube', 'conecta mi cuenta de google')])
def test_070_rf80_rf81_las_tarjetas_de_la_nube_no_publican_ni_conectan_solas(web, tarea, texto):
    """070:RF-80, RF-81 — la orden deja su tarjeta (con lo que dijo: proveedor y direcciones) y ningún trabajo de la nube:
    publicar, compartir, importar y conectar esperan el clic del operador."""
    cliente, app, sim = web
    wid = cliente.post('/api/workspaces').json()['id']
    r = _orden(cliente, wid, texto)
    assert r['plan']['tarea'] == tarea and 'trabajo' in r, r['plan']
    hecho = _esperar(cliente, r['trabajo'])
    assert hecho['status'] == 'done', hecho.get('error')
    tarjeta = hecho['result']['tarjeta']
    # La orden de compartir no nombra proveedor: la tarjeta no lo supone (lo elige el operador en la ventana).
    assert tarjeta['tipo'] == tarea and tarjeta['proveedor'] == (None if tarea == 'compartir_nube' else 'google')
    if tarea == 'compartir_nube':
        assert tarjeta['para'] == ['revisor@otra.test']
    if tarea == 'conectar_nube':
        assert {p['nombre'] for p in tarjeta['proveedores']} == {'google', 'microsoft'}
    assert not [j for j in app.state.jobs.list(wid) if str(j.kind).startswith('nube_')]
    assert sim.subidas_completadas == 0 and not sim.codigos, 'ni sube ni conecta sin el clic'


def test_070_rf80_la_tarjeta_del_panel_solo_pinta_sus_cinco_formas():
    """070:RF-80, 070:RF-81 — la lógica de la tarjeta (cinco tipos, cada uno de su tarea y con su forma; el borrador con su
    firma) se prueba en node (frontend/test/tarjetaOperador.test.mjs); aquí se corre para que la suite la cubra."""
    import shutil
    import subprocess

    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    if shutil.which('node') is None or not (frontend / 'node_modules').is_dir():
        pytest.skip('Falta Node.js o `npm ci` en frontend: la prueba de la tarjeta no se puede ejecutar.')
    r = subprocess.run(['node', '--test', 'test/tarjetaOperador.test.mjs'], cwd=frontend, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert 'fail 0' in r.stdout and 'pass 0' not in r.stdout, r.stdout[-1000:]
