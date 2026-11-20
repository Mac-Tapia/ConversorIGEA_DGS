"""109:RF-26 — revisión de la web en navegador real (ce, 19-11, orden del usuario): un estado esperado de un espacio
recién creado no es un error. Estudio VNR y Estudio PIT pedían la red del espacio al abrirse y la web respondía 404, que el
navegador apuntaba como error de consola en cada pestaña.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nube_simulada import sin_sockets  # noqa: F401  (fixture: ninguna prueba sale de la máquina)


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    from convertersmartgrid.presentacion.web import services
    from convertersmartgrid.presentacion.web.app import create_app

    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def test_109_rf26_un_espacio_sin_red_responde_que_no_la_tiene_sin_error(cliente):
    """109:RF-26: GET /fuentes/red de un espacio sin red da 200 con «disponible» falso y su motivo, no un 404."""
    wid = cliente.post('/api/workspaces', json={'name': 'revision'}).json()['id']
    r = cliente.get(f'/api/workspaces/{wid}/fuentes/red')
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json().get('disponible') is False and r.json().get('motivo')


def test_109_rf26_un_espacio_que_no_existe_sigue_siendo_404(cliente):
    """109:RF-26: lo que sí es un error lo sigue siendo: un espacio que no existe."""
    assert cliente.get('/api/workspaces/noexiste/fuentes/red').status_code == 404


def test_107_rf19_un_perfil_sin_areas_del_pit_no_es_un_error(cliente, monkeypatch):
    """107:RF-19: GET /api/pit/areas con un perfil sin áreas da 200 con la lista vacía y su motivo, no un 422."""
    from convertersmartgrid.presentacion.web import rutas_pit

    def sin_areas(_datos):
        raise rutas_pit.PitError('el perfil no declara las áreas de demanda del PIT')

    monkeypatch.setattr(rutas_pit, 'areas_del_perfil', sin_areas)
    r = cliente.get('/api/pit/areas')
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json().get('areas') == [] and r.json().get('motivo')


@pytest.fixture
def lecturas(monkeypatch):
    """Cuenta las lecturas de cada workspace.json."""
    from pathlib import Path

    cuenta: dict[str, int] = {}
    original = Path.read_text

    def contar(self, *a, **k):
        if self.name == 'workspace.json':
            cuenta[self.parent.name] = cuenta.get(self.parent.name, 0) + 1
        return original(self, *a, **k)

    monkeypatch.setattr(Path, 'read_text', contar)
    return cuenta


def test_086_rf118_el_listado_lee_cada_espacio_una_sola_vez(tmp_path, lecturas):
    """086:RF-118: un workspace.json real pesa hasta 12 MB; el listado lo lee una vez, no dos."""
    from convertersmartgrid.presentacion.web.workspace import WorkspaceStore

    store = WorkspaceStore(tmp_path / 'web')
    wid = store.create().id
    lecturas.clear()
    assert [d['id'] for d in store.list()] == [wid]
    assert lecturas == {wid: 1}, lecturas


def test_086_rf118_el_segundo_listado_no_relee_lo_que_no_cambio(tmp_path, lecturas):
    """086:RF-118: sin cambios en el fichero, el resumen sale de lo ya leído (la web tardaba 11 s cada vez)."""
    from convertersmartgrid.presentacion.web.workspace import WorkspaceStore

    store = WorkspaceStore(tmp_path / 'web')
    wid = store.create().id
    store.list()
    lecturas.clear()
    assert store.list()[0]['id'] == wid
    assert lecturas == {}, lecturas


def test_086_rf118_un_cambio_del_espacio_se_ve_en_el_listado(tmp_path):
    """086:RF-118: el caché no esconde cambios: un fichero nuevo del espacio sale en el siguiente listado."""
    import json

    from convertersmartgrid.presentacion.web.workspace import WorkspaceStore

    store = WorkspaceStore(tmp_path / 'web')
    wid = store.create().id
    assert store.list()[0]['inputs'] == {}
    meta = tmp_path / 'web' / wid / 'workspace.json'
    datos = json.loads(meta.read_text(encoding='utf-8'))
    datos['inputs'] = {'txt': {'name': 'red_sintetica.txt'}}
    meta.write_text(json.dumps(datos), encoding='utf-8')
    assert store.list()[0]['inputs'] == {'txt': 'red_sintetica.txt'}


def test_086_rf118_un_espacio_danado_sigue_saliendo_con_su_motivo(tmp_path):
    """086:RF-118: con un solo análisis, el espacio dañado sigue en la lista con estado y motivo."""
    from convertersmartgrid.presentacion.web.workspace import WorkspaceStore

    store = WorkspaceStore(tmp_path / 'web')
    wid = store.create().id
    (tmp_path / 'web' / wid / 'workspace.json').write_text('{roto', encoding='utf-8')
    fila = store.list()[0]
    assert fila['id'] == wid and fila['estado'] == 'danado' and fila['motivo']


def test_086_rf110_el_registro_nombra_la_casilla_como_la_ve_el_operador(cliente, tmp_path):
    """086:RF-110 (T89): al soltar un TXT, el Registro decía «Archivo asignado a loads»; dice la casilla de la pantalla."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from synthetic_export import ExportSpec, write_export

    wid = cliente.post('/api/workspaces').json()['id']
    _red, cargas, _equipo = write_export(ExportSpec(feeders=1, seed=3), tmp_path / 'export')
    with cargas.open('rb') as fh:
        assert cliente.post(f'/api/workspaces/{wid}/inputs/loads', files={'file': (cargas.name, fh)}).status_code == 200
    import json

    textos = [json.dumps(e, ensure_ascii=False) for e in cliente.get(f'/api/workspaces/{wid}/events').json()]
    asignado = [t for t in textos if 'Archivo asignado' in t]
    assert asignado and all('loads' not in t for t in asignado), asignado
    assert any('«CARGA»' in t for t in asignado), asignado



def test_109_rf24_el_entregable_del_pit_se_publica_desde_su_carpeta_del_espacio(tmp_path, sin_sockets):
    """109:RF-24 (W9): «Publicar» del PIT manda una ruta de `expedientes_pit/`, fuera de la salida; la previa la contaba
    como 0 ficheros y el trabajo no encontraba nada que publicar. Ahora se publica ese fichero y solo ese."""
    from pathlib import Path

    from nube_simulada import montar_web_nube

    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google', publicar=True)
        raiz = Path(web.store.get(wid).root)
        diag = raiz / 'expedientes_pit' / 'A1' / 'diagnostico_de_trabajo.json'
        diag.parent.mkdir(parents=True)
        diag.write_text('{"completo": true}', encoding='utf-8')
        (raiz / 'expedientes_pit' / 'A1' / 'otro.json').write_text('{}', encoding='utf-8')
        carpeta = web.sim.crear('google', 'Expedientes', carpeta=True)
        cuerpo = {'proveedor': 'google', 'carpeta_destino': carpeta, 'nombre': 'Diagnóstico PIT',
                  'seleccion': ['expedientes_pit/A1/diagnostico_de_trabajo.json']}
        previa = web.nube.post(f'/api/workspaces/{wid}/nube/publicar/previa', json=cuerpo)
        assert previa.status_code == 200, previa.text
        assert previa.json()['ficheros'] == 1, previa.json()
        estado = web.esperar(web.nube.post(f'/api/workspaces/{wid}/nube/publicar',
                                           json={**cuerpo, 'confirmacion': previa.json()['confirmacion']}).json())
        assert estado['status'] == 'done', (estado.get('error'), estado.get('result'))


def test_109_rf24_una_carpeta_de_modulo_no_abre_el_resto_del_espacio(cliente):
    """109:RF-24 (W9): solo las carpetas del PIT y del VAD; lo demás del espacio sigue fuera de la publicación."""
    wid = cliente.post('/api/workspaces').json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/nube/publicar/previa',
                     json={'proveedor': 'google', 'carpeta_destino': 'x', 'nombre': 'n', 'seleccion': ['workspace.json']})
    assert r.status_code == 200 and r.json()['ficheros'] == 0, r.text
