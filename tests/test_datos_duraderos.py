"""Spec 086, F1: un corte, una unidad ausente o un fichero dañado no pierden los datos de un espacio."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _entorno(tmp_path, monkeypatch):
    """Sin raíces reales: ni una prueba puede escribir en los datos del operador."""
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('CSG_WEB_DATA', str(tmp_path / 'aislado'))
    yield


def _store(tmp_path, nombre='web'):
    from convertersmartgrid.web.workspace import WorkspaceStore

    return WorkspaceStore(tmp_path / nombre)


def _leer(ws):
    return json.loads((ws.root / 'workspace.json').read_text(encoding='utf-8'))


def _matar_de_golpe(proceso: subprocess.Popen) -> None:
    """Con sus hijos, y hasta que no quede ninguno: el Python de un venv en Windows es un lanzador,
    y matarlo solo deja vivo un momento al proceso real, que seguiría escribiendo."""
    import psutil

    arbol = psutil.Process(proceso.pid).children(recursive=True)
    proceso.kill()
    proceso.wait()
    for hijo in arbol:
        try:
            hijo.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(arbol, timeout=10)


# ---------------------------------------------------------------- RF-1
def test_fsync_antes_de_sustituir_el_fichero(tmp_path, monkeypatch):
    """086:RF-1 — los datos llegan al disco antes de cambiar el nombre: al revés, un corte deja un fichero vacío."""
    from convertersmartgrid.util import write_json_atomic

    orden = []
    fsync, sustituir = os.fsync, Path.replace
    monkeypatch.setattr(os, 'fsync', lambda fd: (orden.append('fsync'), fsync(fd))[1])
    monkeypatch.setattr(Path, 'replace', lambda s, d: (orden.append('replace'), sustituir(s, d))[1])
    write_json_atomic(tmp_path / 'estado.json', {'a': 1})
    assert orden[:2] == ['fsync', 'replace']
    assert json.loads((tmp_path / 'estado.json').read_text(encoding='utf-8')) == {'a': 1}


def test_sustituir_reintenta_un_bloqueo_pasajero_de_windows(tmp_path, monkeypatch):
    """086:RF-54 — un ``PermissionError`` pasajero se reintenta; uno que no pasa, sube tras el último intento."""
    from convertersmartgrid import util

    monkeypatch.setattr(util.os, 'name', 'nt')
    monkeypatch.setattr(util, 'ESPERAS_SUSTITUIR_S', (0.0, 0.0, 0.0))
    sustituir, intentos = Path.replace, []

    def bloqueado(veces):
        def replace(s, d):
            intentos.append(d)
            if len(intentos) <= veces:
                raise PermissionError(32, 'El proceso no tiene acceso al archivo porque está siendo utilizado')
            return sustituir(s, d)
        return replace

    monkeypatch.setattr(Path, 'replace', bloqueado(2))
    util.write_json_atomic(tmp_path / 'estado.json', {'a': 1})
    assert len(intentos) == 3 and json.loads((tmp_path / 'estado.json').read_text(encoding='utf-8')) == {'a': 1}
    intentos.clear()
    monkeypatch.setattr(Path, 'replace', bloqueado(99))
    with pytest.raises(PermissionError):
        util.write_json_atomic(tmp_path / 'estado.json', {'a': 2})
    assert len(intentos) == 4                     # el primero y uno por cada espera
    assert json.loads((tmp_path / 'estado.json').read_text(encoding='utf-8')) == {'a': 1}


def test_registro_de_vinculos_y_almacen_tambien_sincronizan(tmp_path, monkeypatch):
    """086:RF-1 — el registro compartido de vínculos y lo del asistente son estado igual que un espacio."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.powerfactory_binding import _escribir_registro

    llamadas = []
    fsync = os.fsync
    monkeypatch.setattr(os, 'fsync', lambda fd: (llamadas.append(fd), fsync(fd))[1])
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    _escribir_registro(tmp_path / 'vinculos.json', {})
    assert len(llamadas) == 1
    almacen.guardar_json('x', {'a': 1})
    assert len(llamadas) == 2
    almacen.anotar('decisiones', {'a': 1})
    assert len(llamadas) == 3


def test_matar_el_proceso_a_mitad_de_guardar_deja_un_espacio_legible(tmp_path):
    """086:RF-1 — el proceso muere mientras guarda sin parar; lo que queda se abre y no es un trozo."""
    from convertersmartgrid.web.workspace import Workspace

    wid = 'c' * 16
    root = tmp_path / 'web' / wid
    guion = tmp_path / 'guardar.py'
    guion.write_text(textwrap.dedent(f'''
        from pathlib import Path
        from convertersmartgrid.web.workspace import Workspace
        ws = Workspace(id={wid!r}, root=Path({str(root)!r}))
        ws.calibraciones = {{'P': {{'F': {{'relleno': 'x' * 200000}}}}}}
        n = 0
        while True:
            ws.sin_licencia = [str(n)]
            ws.save()
            n += 1
            if n == 3:
                print('guardando', flush=True)
    '''), encoding='utf-8')
    entorno = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    proceso = subprocess.Popen([sys.executable, str(guion)], stdout=subprocess.PIPE, text=True, env=entorno)
    try:
        assert proceso.stdout.readline().strip() == 'guardando'
    finally:
        _matar_de_golpe(proceso)
    ws = Workspace.load(root)
    assert ws.calibraciones['P']['F']['relleno'] == 'x' * 200000


# ---------------------------------------------------------------- RF-2
def _espacio_con_dos_guardados(tmp_path):
    store = _store(tmp_path)
    ws = store.create()
    ws.sin_licencia = ['anterior']
    ws.save()
    ws.sin_licencia = ['ultimo']
    ws.save()
    return store, ws


@pytest.mark.parametrize('contenido', ['{"id": "trunc', '[1, 2]', '{"sin": "id"}', ''])
def test_json_danado_se_ve_y_se_restaura(tmp_path, contenido):
    """086:RF-2 — truncado, otra forma o vacío: se ve como dañado con la opción de restaurar, no desaparece."""
    _, ws = _espacio_con_dos_guardados(tmp_path)
    (ws.root / 'workspace.json').write_text(contenido, encoding='utf-8')
    store = _store(tmp_path)
    assert store.get(ws.id) is None
    fila = next(f for f in store.list() if f['id'] == ws.id)
    assert fila['estado'] == 'danado' and fila['restaurable'] is True and fila['motivo']
    assert store.problema(ws.id)['estado'] == 'danado'
    restaurado = store.restaurar_copia(ws.id)
    assert restaurado.sin_licencia == ['anterior'] and restaurado.avisos_datos
    apartados = list(ws.root.glob('workspace.danado-*.json'))
    assert len(apartados) == 1 and apartados[0].read_text(encoding='utf-8') == contenido
    assert next(f for f in store.list() if f['id'] == ws.id)['estado'] == 'ok'


def test_un_fichero_danado_no_pisa_la_copia_que_lo_arregla(tmp_path):
    """086:RF-2 — guardar con un fichero dañado en disco deja la copia buena donde estaba."""
    from convertersmartgrid.util import write_json_atomic

    ruta = tmp_path / 'estado.json'
    write_json_atomic(ruta, {'v': 1}, copia=True)
    write_json_atomic(ruta, {'v': 2}, copia=True)
    assert json.loads((tmp_path / 'estado.json.bak').read_text(encoding='utf-8')) == {'v': 1}
    ruta.write_text('{roto', encoding='utf-8')
    write_json_atomic(ruta, {'v': 3}, copia=True)
    assert json.loads((tmp_path / 'estado.json.bak').read_text(encoding='utf-8')) == {'v': 1}


def test_danado_sin_copia_se_ve_y_no_se_finge_restaurable(tmp_path):
    """086:RF-2 — sin copia lo dice, y no borra lo dañado: alguien puede querer rescatarlo a mano."""
    from convertersmartgrid.web.workspace import EspacioDanado

    store = _store(tmp_path)
    ws = store.create()
    (ws.root / 'workspace.json').write_text('{roto', encoding='utf-8')
    otro = _store(tmp_path)
    assert next(f for f in otro.list() if f['id'] == ws.id)['restaurable'] is False
    with pytest.raises(EspacioDanado):
        otro.restaurar_copia(ws.id)
    assert (ws.root / 'workspace.json').read_text(encoding='utf-8') == '{roto'


def test_conversiones_danadas_recuperan_su_copia(tmp_path):
    """086:RF-2 — antes se leía vacío y el siguiente guardado pisaba lo que quedaba."""
    from convertersmartgrid.web.workspace import Workspace

    ws = _store(tmp_path).create()
    ws.conversions['F1'] = {'status': 'ok'}
    ws.save()
    ws.conversions['F2'] = {'status': 'ok'}
    ws.save()
    (ws.root / 'conversiones.json').write_text('{roto', encoding='utf-8')
    otra = Workspace.load(ws.root)
    assert list(otra.conversions) == ['F1'] and any('conversiones' in a for a in otra.avisos_datos)
    assert [p.read_text(encoding='utf-8') for p in ws.root.glob('conversiones.danado-*.json')] == ['{roto']


def test_api_de_un_espacio_danado(tmp_path):
    """086:RF-2 — por la web: la lista lo muestra, abrirlo dice por qué y se puede restaurar."""
    from convertersmartgrid.web.app import create_app

    _, ws = _espacio_con_dos_guardados(tmp_path)
    (ws.root / 'workspace.json').write_text('{roto', encoding='utf-8')
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as cliente:
        fila = next(f for f in cliente.get('/api/workspaces').json() if f['id'] == ws.id)
        assert fila['estado'] == 'danado' and fila['restaurable'] is True
        respuesta = cliente.get(f'/api/workspaces/{ws.id}')
        assert respuesta.status_code == 409 and 'no se puede leer' in respuesta.json()['detail']
        assert cliente.delete(f'/api/workspaces/{ws.id}').status_code == 409
        assert ws.root.is_dir()
        restaurado = cliente.post(f'/api/workspaces/{ws.id}/restaurar-copia')
        assert restaurado.status_code == 200 and restaurado.json()['avisos_datos']
        assert cliente.get(f'/api/workspaces/{ws.id}').status_code == 200
        assert cliente.post(f'/api/workspaces/{ws.id}/restaurar-copia').status_code == 409


# ---------------------------------------------------------------- RF-3
def _espacio_con_todo_fuera(tmp_path):
    fuera = tmp_path / 'unidad'
    fuera.mkdir()
    ws = _store(tmp_path).create()
    rutas = {n: fuera / n for n in ('RED.txt', 'cabecera.xlsx', 'perdidas.xlsx', 'empresa.xlsx', 'catalogo.xlsx')}
    for ruta in rutas.values():
        ruta.write_text('x', encoding='utf-8')
    ws.set_input('red', rutas['RED.txt'], origin='server')
    ws.demanda['cabecera'] = {'path': str(rutas['cabecera.xlsx']), 'name': 'cabecera.xlsx'}
    ws.informes['libro_perdidas'] = {'path': str(rutas['perdidas.xlsx']), 'name': 'perdidas.xlsx'}
    ws.datos_empresa['P'] = {'path': str(rutas['empresa.xlsx']), 'nombre': 'empresa.xlsx'}
    ws.catalog_file = str(rutas['catalogo.xlsx'])
    ws.save()
    return ws, fuera, rutas


def test_unidad_ausente_no_borra_las_referencias_al_guardar(tmp_path):
    """086:RF-3 — con la unidad fuera se conserva todo marcado; al guardar y volver, sigue ahí."""
    from convertersmartgrid.web.workspace import Workspace

    ws, fuera, rutas = _espacio_con_todo_fuera(tmp_path)
    oculta = fuera.with_name('unidad_desconectada')
    fuera.rename(oculta)
    otra = Workspace.load(ws.root)
    assert not otra.inputs and not otra.demanda and not otra.datos_empresa
    assert otra.catalog_file is None and 'libro_perdidas' not in otra.informes
    publico = otra.public()
    assert {f['campo'] for f in publico['no_disponibles']} == {
        'inputs', 'demanda', 'datos_empresa', 'libro_perdidas', 'catalog_file'}
    assert {f['nombre'] for f in publico['no_disponibles']} == set(rutas)
    assert all(f['ruta'] for f in publico['no_disponibles'])
    otra.save()  # lo que antes borraba las rutas
    oculta.rename(fuera)
    vuelta = Workspace.load(ws.root)
    assert not vuelta.no_disponibles and vuelta.public()['no_disponibles'] == []
    assert Path(vuelta.input_path('red')) == rutas['RED.txt']
    assert Path(vuelta.demanda['cabecera']['path']) == rutas['cabecera.xlsx']
    assert Path(vuelta.informes['libro_perdidas']['path']) == rutas['perdidas.xlsx']
    assert Path(vuelta.datos_empresa['P']['path']) == rutas['empresa.xlsx']
    assert Path(vuelta.catalog_file) == rutas['catalogo.xlsx']
    assert vuelta.options['input_mode'] == 'txt'


def test_la_unidad_que_vuelve_con_la_web_abierta_repone_lo_suyo(tmp_path):
    """086:RF-3 — sin reiniciar: reconectar el disco basta para que vuelva."""
    from convertersmartgrid.web.workspace import REVISION_NO_DISPONIBLES_S, Workspace

    ws, fuera, rutas = _espacio_con_todo_fuera(tmp_path)
    oculta = fuera.with_name('unidad_desconectada')
    fuera.rename(oculta)
    otra = Workspace.load(ws.root)
    assert otra.options['input_mode'] is None
    otra.reponer_disponibles(ahora=REVISION_NO_DISPONIBLES_S + 1)
    assert 'inputs' in otra.no_disponibles
    oculta.rename(fuera)
    otra.reponer_disponibles(ahora=REVISION_NO_DISPONIBLES_S + 2)  # aún dentro del intervalo: no mira
    assert 'inputs' in otra.no_disponibles
    otra.reponer_disponibles(ahora=2 * REVISION_NO_DISPONIBLES_S + 2)
    assert not otra.no_disponibles and Path(otra.input_path('red')) == rutas['RED.txt']
    assert otra.options['input_mode'] == 'txt'
    assert Path(otra.catalog_file) == rutas['catalogo.xlsx']


def test_la_ejecucion_activa_sin_su_carpeta_tampoco_se_pierde_al_guardar(tmp_path):
    """086:RF-3 — hallado al migrar una copia sin ``runs``: se olvidaba cuál era la activa para siempre."""
    from convertersmartgrid.web.workspace import REVISION_NO_DISPONIBLES_S, Workspace

    run = '20261101T101010-abcdefabcdef'
    ws = _store(tmp_path).create()
    manifiesto = ws.root / 'runs' / run / 'source_manifest.json'
    manifiesto.parent.mkdir(parents=True)
    manifiesto.write_text('{}', encoding='utf-8')
    ws.active_run_id = run
    ws.save()
    apartada = manifiesto.parent.with_name('apartada')
    manifiesto.parent.rename(apartada)
    otra = Workspace.load(ws.root)
    assert otra.active_run_id is None and otra.public()['no_disponibles'][0]['campo'] == 'active_run_id'
    otra.save()
    assert _leer(ws)['active_run_id'] == run
    apartada.rename(manifiesto.parent)
    otra.reponer_disponibles(ahora=REVISION_NO_DISPONIBLES_S + 1)
    assert otra.active_run_id == run and not otra.no_disponibles
    # Cargar otra fuente la deja sin sentido: no vuelve al guardar.
    manifiesto.parent.rename(apartada)
    tercera = Workspace.load(ws.root)
    tercera.invalidate()
    tercera.save()
    assert _leer(ws)['active_run_id'] is None


def test_elegir_o_quitar_otra_entrada_olvida_la_no_disponible(tmp_path):
    """086:RF-3 — lo que decide el operador manda: la vieja no vuelve a la casilla al guardar."""
    from convertersmartgrid.web.workspace import Workspace

    ws, fuera, _ = _espacio_con_todo_fuera(tmp_path)
    shutil.rmtree(fuera)
    otra = Workspace.load(ws.root)
    nueva = tmp_path / 'NUEVA.txt'
    nueva.write_text('x', encoding='utf-8')
    otra.set_input('red', nueva, origin='server')
    assert 'inputs' not in otra.no_disponibles
    assert Path(Workspace.load(ws.root).input_path('red')) == nueva
    otra.clear_input('red')
    disco = _leer(otra)
    assert 'red' not in disco['inputs']


def test_descartar_por_api_y_aviso_en_el_espacio(tmp_path):
    """086:RF-3 — la API dice qué no está; descartarlo lo quita de verdad, también de disco."""
    from convertersmartgrid.web.app import create_app

    ws, fuera, _ = _espacio_con_todo_fuera(tmp_path)
    shutil.rmtree(fuera)
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as cliente:
        publico = cliente.get(f'/api/workspaces/{ws.id}').json()
        assert {f['clave'] for f in publico['no_disponibles']} >= {'red', 'cabecera'}
        ruta = f'/api/workspaces/{ws.id}/no-disponibles/descartar'
        assert cliente.post(ruta, json={'campo': 'inputs', 'clave': 'red'}).status_code == 200
        assert cliente.post(ruta, json={'campo': 'inputs', 'clave': 'red'}).status_code == 404
        assert cliente.post(ruta, json={'campo': 'catalog_file', 'clave': ''}).status_code == 200
    disco = _leer(ws)
    assert 'red' not in disco['inputs'] and disco['catalog_file'] is None and 'cabecera' in disco['demanda']


# ---------------------------------------------------------------- RF-4, RF-5
def _version_2(root: Path, wid: str, **campos) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / 'workspace.json').write_text(json.dumps({
        'version': 2, 'id': wid, 'created_at': 1.0, 'options': {}, **campos}), encoding='utf-8')


def test_migra_con_copia_previa_y_por_pasos(tmp_path):
    """086:RF-4 — de la 2 a la vigente: copia intacta, versión escrita, y lo que había sigue."""
    from convertersmartgrid.web.workspace import MIGRACIONES, VERSION_ESPACIO, Workspace

    wid = 'd' * 16
    root = tmp_path / wid
    _version_2(root, wid, sin_licencia=['flujo'], calibraciones={'P': {'F': {'nombre': 'x'}}})
    original = (root / 'workspace.json').read_bytes()
    ws = Workspace.load(root)
    assert (root / 'workspace.v2.json').read_bytes() == original
    assert json.loads((root / 'workspace.json').read_text(encoding='utf-8'))['version'] == VERSION_ESPACIO
    assert ws.sin_licencia == ['flujo'] and ws.calibraciones == {'P': {'F': {'nombre': 'x'}}}
    assert any('versión 2' in a for a in ws.avisos_datos)
    assert sorted(MIGRACIONES) == list(range(1, VERSION_ESPACIO))
    # Abrirla otra vez no vuelve a migrar ni pisa la copia.
    (root / 'workspace.v2.json').write_bytes(b'marcada')
    assert not Workspace.load(root).avisos_datos
    assert (root / 'workspace.v2.json').read_bytes() == b'marcada'


def test_un_paso_que_falla_no_toca_el_fichero(tmp_path, monkeypatch):
    """086:RF-4 — una migración que revienta deja el fichero como estaba, y su copia."""
    from convertersmartgrid.web import workspace

    wid = 'e' * 16
    root = tmp_path / wid
    _version_2(root, wid)
    original = (root / 'workspace.json').read_bytes()

    def falla(_datos, _root):
        raise ValueError('paso roto')

    monkeypatch.setitem(workspace.MIGRACIONES, 2, falla)
    with pytest.raises(ValueError, match='paso roto'):
        workspace.Workspace.load(root)
    assert (root / 'workspace.json').read_bytes() == original


def test_fichero_sin_version_se_trata_como_el_primero(tmp_path):
    """086:RF-4 — los primeros espacios no llevaban versión, y su copia dice de cuál venían."""
    from convertersmartgrid.web.workspace import VERSION_ESPACIO, Workspace

    root = tmp_path / ('f' * 16)
    root.mkdir()
    (root / 'workspace.json').write_text(json.dumps({'id': 'f' * 16}), encoding='utf-8')
    Workspace.load(root)
    assert (root / 'workspace.v1.json').is_file()
    assert json.loads((root / 'workspace.json').read_text(encoding='utf-8'))['version'] == VERSION_ESPACIO


def test_version_futura_no_se_sobrescribe_y_lo_dice(tmp_path):
    """086:RF-5 — antes se cargaba, y el siguiente guardado rebajaba la versión y perdía sus campos."""
    from convertersmartgrid.web.app import create_app
    from convertersmartgrid.web.workspace import EspacioVersionFutura, Workspace

    ws = _store(tmp_path).create()
    futuro = {**_leer(ws), 'version': 99, 'campo_del_futuro': 'x'}
    (ws.root / 'workspace.json').write_text(json.dumps(futuro), encoding='utf-8')
    antes = (ws.root / 'workspace.json').read_bytes()
    with pytest.raises(EspacioVersionFutura, match='más nueva'):
        Workspace.load(ws.root)
    # También el que ya estaba abierto cuando otro proceso más nuevo lo actualizó.
    with pytest.raises(EspacioVersionFutura):
        ws.save()
    store = _store(tmp_path)
    fila = next(f for f in store.list() if f['id'] == ws.id)
    assert fila['estado'] == 'version_futura' and 'más nueva' in fila['motivo'] and not fila['restaurable']
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as cliente:
        respuesta = cliente.get(f'/api/workspaces/{ws.id}')
        assert respuesta.status_code == 409 and 'más nueva' in respuesta.json()['detail']
        assert cliente.post(f'/api/workspaces/{ws.id}/restaurar-copia').status_code == 409
    assert (ws.root / 'workspace.json').read_bytes() == antes


# ---------------------------------------------------------------- RF-6
def test_rutas_de_dentro_relativas_y_las_de_fuera_enteras(tmp_path):
    """086:RF-6 — en disco, lo del espacio sin la carpeta; lo de fuera con su ruta entera."""
    ws = _store(tmp_path).create()
    subido = ws.upload_target('red', 'RED.txt')
    subido.write_text('x', encoding='utf-8')
    fuera = tmp_path / 'fuera.txt'
    fuera.write_text('x', encoding='utf-8')
    ws.set_input('red', subido, origin='upload')
    ws.set_input('loads', fuera, origin='server')
    ws.groups['G'] = {'dgs': str(ws.root / 'salida' / 'G.dgs'), 'source_run_id': 'r'}
    ws.conversions['F'] = {'dgs': str(ws.root / 'salida' / 'F.dgs')}
    ws.save()
    disco = _leer(ws)
    assert disco['inputs']['red']['path'] == 'espacio:entradas/red/RED.txt'
    assert disco['inputs']['loads']['path'] == str(fuera)
    assert disco['groups']['G']['dgs'] == 'espacio:salida/G.dgs'
    assert json.loads((ws.root / 'conversiones.json').read_text(encoding='utf-8'))['F']['dgs'] == 'espacio:salida/F.dgs'
    assert str(tmp_path) not in json.dumps({k: disco[k] for k in ('groups',)}).replace('\\\\', '\\')


def test_vinculos_e_inventario_no_se_reescriben(tmp_path):
    """086:RF-6 — llevan su huella; lo guardado no se toca (058:RF-6), aunque parezca una ruta de dentro."""
    ws = _store(tmp_path).create()
    ruta = str(ws.root / 'salida' / 'x.dgs')
    ws.pf_project_bindings['P'] = {'native_reread': {'dgs': ruta}}
    ws.pf_inventory = {'projects': [{'dgs': ruta}]}
    ws.save()
    disco = _leer(ws)
    assert disco['pf_project_bindings']['P']['native_reread']['dgs'] == ruta
    assert disco['pf_inventory']['projects'][0]['dgs'] == ruta


def test_mover_la_carpeta_de_datos_conserva_los_espacios(tmp_path):
    """086:RF-6 — con rutas relativas, mover todo no pierde ni una entrada subida."""
    store = _store(tmp_path)
    ws = store.create()
    subido = ws.upload_target('red', 'RED.txt')
    subido.write_text('x', encoding='utf-8')
    ws.set_input('red', subido, origin='upload')
    ws.demanda['cabecera'] = {'path': str(ws.inputs_dir / 'red' / 'RED.txt'), 'name': 'c'}
    ws.save()
    shutil.move(str(tmp_path / 'web'), str(tmp_path / 'movida'))
    otra = _store(tmp_path, 'movida').get(ws.id)
    assert otra is not None and not otra.no_disponibles
    assert Path(otra.input_path('red')) == tmp_path / 'movida' / ws.id / 'entradas' / 'red' / 'RED.txt'
    assert Path(otra.input_path('red')).read_text(encoding='utf-8') == 'x'
    assert Path(otra.demanda['cabecera']['path']).is_file()


def test_espacio_de_la_version_2_ya_movido_recupera_sus_rutas(tmp_path):
    """086:RF-6, 086:RF-4 — las absolutas de antes llevan su ``<id>``: de ahí en adelante es lo suyo."""
    from convertersmartgrid.web.workspace import Workspace

    wid = 'a1' * 8
    raiz_nueva = tmp_path / 'nueva' / wid
    fichero = raiz_nueva / 'entradas' / 'red' / 'RED.txt'
    fichero.parent.mkdir(parents=True)
    fichero.write_text('x', encoding='utf-8')
    fuera = tmp_path / 'fuera.txt'
    fuera.write_text('x', encoding='utf-8')
    antigua = f'D:/antes/output/web/{wid}/entradas/red/RED.txt'
    _version_2(raiz_nueva, wid,
               inputs={'red': {'path': antigua, 'name': 'RED.txt', 'origin': 'upload'},
                       'loads': {'path': str(fuera), 'name': 'fuera.txt', 'origin': 'server'}},
               groups={'G': {'dgs': f'D:/antes/output/web/{wid}/salida/G.dgs'}})
    (raiz_nueva / 'conversiones.json').write_text(json.dumps(
        {'F': {'dgs': f'D:\\antes\\output\\web\\{wid}\\salida\\F.dgs'}}), encoding='utf-8')
    ws = Workspace.load(raiz_nueva)
    assert Path(ws.input_path('red')) == fichero and Path(ws.input_path('loads')) == fuera
    assert Path(ws.groups['G']['dgs']) == raiz_nueva / 'salida' / 'G.dgs'
    assert Path(ws.conversions['F']['dgs']) == raiz_nueva / 'salida' / 'F.dgs'
    assert not ws.no_disponibles


def test_adoptar_de_otro_espacio_lee_sus_rutas_enteras(tmp_path):
    """086:RF-6 — quien lee el fichero de otro espacio no ve ``espacio:…``, o perdería su demanda."""
    from convertersmartgrid.web.workspace import leer_metadatos_espacio

    ws = _store(tmp_path).create()
    libro = ws.root / 'demanda' / 'cab.xlsx'
    libro.parent.mkdir()
    libro.write_text('x', encoding='utf-8')
    ws.demanda['cabecera'] = {'path': str(libro), 'name': 'cab.xlsx'}
    ws.save()
    assert _leer(ws)['demanda']['cabecera']['path'].startswith('espacio:')
    assert Path(leer_metadatos_espacio(ws.root)['demanda']['cabecera']['path']) == libro


def test_una_ruta_relativa_que_sale_del_espacio_no_se_sigue(tmp_path):
    """086:RF-6 — ``espacio:`` no es una forma de apuntar fuera: queda como no disponible."""
    from convertersmartgrid.web.workspace import Workspace

    wid = 'b2' * 8
    root = tmp_path / wid
    secreto = tmp_path / 'secreto.txt'
    secreto.write_text('x', encoding='utf-8')
    root.mkdir()
    (root / 'workspace.json').write_text(json.dumps({'version': 3, 'id': wid, 'inputs': {
        'red': {'path': 'espacio:../secreto.txt', 'name': 's'}}}), encoding='utf-8')
    ws = Workspace.load(root)
    assert not ws.inputs and ws.no_disponibles['inputs']['red']['path'] == 'espacio:../secreto.txt'


def test_retencion_ve_las_referencias_relativas(tmp_path):
    """086:RF-6 — la limpieza no toma por libre un automático que un espacio usa con ruta relativa."""
    from convertersmartgrid.web.jobs import JobManager
    from convertersmartgrid.web.retencion import RetencionDiaria

    store = _store(tmp_path)
    ws = store.create()
    usado = ws.inputs_dir / '_auto' / 'usado.txt'
    usado.parent.mkdir(parents=True)
    usado.write_text('x', encoding='utf-8')
    os.utime(usado, (1.0, 1.0))
    ws.groups['G'] = {'fuente': str(usado)}
    ws.save()
    assert _leer(ws)['groups']['G']['fuente'].startswith('espacio:')
    resultado = RetencionDiaria(store, JobManager(lambda *a: None)).revisar_si_vence()
    assert resultado['estado'] == 'completada' and usado.is_file()


# ---------------------------------------------------------------- RF-7
def test_renombrar_la_carpeta_no_cambia_la_identidad(tmp_path, monkeypatch):
    """086:RF-7 — el hash de la ruta hacía que renombrar dejara los datos atrás."""
    from convertersmartgrid.runtime_paths import FICHERO_INSTALACION, fijar_identidad, rutas_runtime

    entorno = {'LOCALAPPDATA': str(tmp_path / 'local')}
    a = tmp_path / 'ConversorViejo'
    a.mkdir()
    antes = rutas_runtime(a, entorno)
    fijar_identidad(antes)
    assert (a / FICHERO_INSTALACION).is_file()
    antes.runtime.mkdir(parents=True, exist_ok=True)
    (antes.runtime / 'dato.txt').write_text('x', encoding='utf-8')
    b = a.with_name('ConverterSmartGrid')
    a.rename(b)
    despues = rutas_runtime(b, entorno)
    assert despues.identidad == antes.identidad
    assert despues.runtime == antes.runtime and despues.cache == antes.cache
    assert (despues.runtime / 'dato.txt').read_text(encoding='utf-8') == 'x'


def test_instalacion_existente_conserva_su_raiz_al_fijar_identidad(tmp_path):
    """086:RF-7 — la que ya tiene datos en la raíz por hash se queda con ese hash, sin mover nada."""
    from convertersmartgrid.runtime_paths import (FICHERO_INSTALACION, _identidad_por_ruta, fijar_identidad,
                                                  rutas_runtime)

    entorno = {'LOCALAPPDATA': str(tmp_path / 'local')}
    programa = tmp_path / 'programa'
    programa.mkdir()
    hash_ruta = _identidad_por_ruta(programa.resolve())
    raiz_existente = tmp_path / '.convertersmartgrid-runtime' / hash_ruta
    (raiz_existente / 'data' / 'web').mkdir(parents=True)
    rutas = rutas_runtime(programa, entorno)
    assert rutas.identidad == hash_ruta and rutas.runtime == raiz_existente
    fijar_identidad(rutas)
    otra = rutas_runtime(programa, entorno)
    assert otra.identidad == hash_ruta and otra.runtime == raiz_existente
    # También queda en la raíz de datos, y un segundo arranque no cambia la identidad escrita.
    assert json.loads((raiz_existente / FICHERO_INSTALACION).read_text(encoding='utf-8'))['id'] == hash_ruta
    primero = (programa / FICHERO_INSTALACION).read_bytes()
    fijar_identidad(otra)
    assert (programa / FICHERO_INSTALACION).read_bytes() == primero


def test_el_hash_de_siempre_para_las_rutas_existentes():
    """086:RF-7 — la fórmula no cambia: de ella depende encontrar la raíz de las instalaciones de antes."""
    from convertersmartgrid.runtime_paths import _identidad_por_ruta

    class Ruta:
        @staticmethod
        def as_posix():
            return 'd:/carpeta/programa'

    import hashlib
    esperado = hashlib.sha256(b'd:/carpeta/programa').hexdigest()[:16]
    assert _identidad_por_ruta(Ruta()) == esperado


def test_mover_a_otra_carpeta_madre_sigue_encontrando_los_datos(tmp_path):
    """086:RF-7 — la raíz está junto a la carpeta madre: movida a otra, vale la ruta anotada."""
    from convertersmartgrid.runtime_paths import fijar_identidad, rutas_runtime

    entorno = {'LOCALAPPDATA': str(tmp_path / 'local')}
    programa = tmp_path / 'madre_a' / 'programa'
    programa.mkdir(parents=True)
    antes = rutas_runtime(programa, entorno)
    fijar_identidad(antes)
    (antes.runtime / 'dato.txt').write_text('x', encoding='utf-8')
    destino = tmp_path / 'madre_b' / 'programa'
    destino.parent.mkdir()
    programa.rename(destino)
    despues = rutas_runtime(destino, entorno)
    assert despues.identidad == antes.identidad and despues.runtime == antes.runtime
    assert (despues.runtime / 'dato.txt').is_file()


def test_mover_todo_junto_prefiere_la_raiz_vecina(tmp_path):
    """086:RF-7 — si los datos viajaron con el programa, la ruta anotada ya es vieja y no manda."""
    from convertersmartgrid.runtime_paths import fijar_identidad, rutas_runtime

    entorno = {'LOCALAPPDATA': str(tmp_path / 'local')}
    madre = tmp_path / 'madre_a'
    programa = madre / 'programa'
    programa.mkdir(parents=True)
    antes = rutas_runtime(programa, entorno)
    fijar_identidad(antes)
    madre.rename(tmp_path / 'madre_b')
    despues = rutas_runtime(tmp_path / 'madre_b' / 'programa', entorno)
    assert despues.identidad == antes.identidad
    assert despues.runtime == tmp_path / 'madre_b' / '.convertersmartgrid-runtime' / antes.identidad
    assert despues.runtime.is_dir()


def test_fichero_de_identidad_danado_o_sin_permiso_no_cambia_nada(tmp_path, monkeypatch):
    """086:RF-7 — ilegible: la identidad por ruta, nunca una nueva y vacía que parezca sin datos."""
    from convertersmartgrid.runtime_paths import (FICHERO_INSTALACION, _identidad_por_ruta, fijar_identidad,
                                                  rutas_runtime)

    programa = tmp_path / 'programa'
    programa.mkdir()
    (programa / FICHERO_INSTALACION).write_text('{roto', encoding='utf-8')
    rutas = rutas_runtime(programa, {'LOCALAPPDATA': str(tmp_path / 'l')})
    assert rutas.identidad == _identidad_por_ruta(programa.resolve())
    (programa / FICHERO_INSTALACION).unlink()

    def sin_permiso(*_a, **_k):
        raise PermissionError('solo lectura')

    monkeypatch.setattr(os, 'replace', sin_permiso)
    assert fijar_identidad(rutas)['id'] == rutas.identidad
    assert not list(programa.iterdir())


def test_configurar_entorno_fija_la_identidad_y_no_anota_una_raiz_explicita(tmp_path):
    """086:RF-7 — el arranque la deja escrita; con ``CSG_RUNTIME_HOME`` del operador, esa raíz no es la propia."""
    from convertersmartgrid.runtime_paths import FICHERO_INSTALACION, configurar_entorno

    previo = os.environ.copy()
    try:
        programa = tmp_path / 'programa'
        programa.mkdir()
        os.environ.pop('CSG_RUTAS_AUTOMATICAS', None)
        configurar_entorno(programa)
        datos = json.loads((programa / FICHERO_INSTALACION).read_text(encoding='utf-8'))
        assert datos['id'] and 'runtime' not in datos
    finally:
        os.environ.clear()
        os.environ.update(previo)


# ---------------------------------------------------------------- RF-8
@pytest.mark.parametrize('destino', ['Z:/datos/x.json', r'\\servidor\recurso\informes\x.json'])
def test_otra_unidad_o_ruta_de_red_publica_junto_al_destino(tmp_path, destino):
    """086:RF-8 — antes daba ValueError al final de la corrida, con todo calculado."""
    from convertersmartgrid.runtime_paths import rutas_runtime

    rutas = rutas_runtime(tmp_path / 'codigo', {'CSG_RUNTIME_HOME': str(tmp_path / 'runtime'),
                                                'LOCALAPPDATA': str(tmp_path / 'local')})
    ruta = Path(destino)
    assert rutas.staging_para(ruta) == ruta.resolve().parent


def test_escribir_de_verdad_con_el_destino_en_otro_volumen(tmp_path, monkeypatch):
    """086:RF-8 — el temporal queda junto al destino, se publica y no deja nada detrás."""
    from convertersmartgrid import runtime_paths
    from convertersmartgrid.util import write_json_atomic

    rutas = runtime_paths.rutas_runtime(tmp_path / 'codigo', {'LOCALAPPDATA': str(tmp_path / 'local')})
    # La raíz de ejecución en una unidad distinta de la del destino, sin depender de cuáles tenga la máquina.
    letra = 'Q' if tmp_path.anchor.upper()[:1] != 'Q' else 'R'
    otra = replace(rutas, runtime=Path(f'{letra}:/runtime'), cache=Path(f'{letra}:/cache/c'))
    assert otra.staging_para(tmp_path / 'x.json') == tmp_path.resolve()
    monkeypatch.setattr(runtime_paths, 'rutas_runtime', lambda *a, **k: otra)
    destino = tmp_path / 'red' / 'informe.json'
    write_json_atomic(destino, {'a': 1}, copia=True)
    write_json_atomic(destino, {'a': 2}, copia=True)
    assert json.loads(destino.read_text(encoding='utf-8')) == {'a': 2}
    assert sorted(p.name for p in destino.parent.iterdir()) == ['informe.json', 'informe.json.bak']


def test_mismo_volumen_sigue_fuera_del_destino(tmp_path):
    """086:RF-8 y 065:RF-11 — con raíz en ese volumen no cambia: el temporal va a la raíz, no junto al código."""
    from convertersmartgrid.runtime_paths import rutas_runtime

    rutas = rutas_runtime(tmp_path / 'codigo', {'CSG_RUNTIME_HOME': str(tmp_path / 'runtime'),
                                                'LOCALAPPDATA': str(tmp_path / 'local')})
    assert rutas.staging_para(tmp_path / 'x.json') == rutas.runtime / 'staging'
