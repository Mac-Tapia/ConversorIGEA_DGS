"""Spec 086, RF-10 y RF-47: copia y restauración con manifiesto, y aviso si la copia es vieja."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
RUN = '20261101T101010-abcdefabcdef'
RUN_LIBRE = '20200101T101010-abcabcabcabc'
RUN_INFORME = '20200102T101010-abcabcabcabd'


@pytest.fixture(autouse=True)
def _entorno(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('CSG_WEB_DATA', str(tmp_path / 'web'))
    monkeypatch.delenv('CSG_COPIA_MAX_DIAS', raising=False)
    yield


def _crear_datos(tmp_path) -> tuple[Path, str]:
    """Un espacio con de todo: lo que hay que conservar y lo que la limpieza retiraría."""
    from convertersmartgrid.web.workspace import WorkspaceStore

    raiz = tmp_path / 'web'
    ws = WorkspaceStore(raiz).create()
    subido = ws.upload_target('red', 'RED.txt')
    subido.write_text('red', encoding='utf-8')
    fuera = tmp_path / 'fuera' / 'CARGA.txt'
    fuera.parent.mkdir()
    fuera.write_text('carga', encoding='utf-8')
    ws.set_input('red', subido, origin='upload')
    ws.set_input('loads', fuera, origin='server')
    ws.groups['G'] = {'dgs': str(ws.root / 'runs' / RUN / 'salida' / 'G.dgs')}
    ws.save()
    for run, fichero in ((RUN, 'salida/G.dgs'), (RUN_LIBRE, 'salida/F.dgs'), (RUN_INFORME, 'salida/informe.docx')):
        ruta = ws.root / 'runs' / run / fichero
        ruta.parent.mkdir(parents=True)
        ruta.write_bytes(run.encode())
    viejo = time.time() - 30 * 86400
    for fichero in (ws.root / 'runs' / RUN_LIBRE).rglob('*'):
        os.utime(fichero, (viejo, viejo))
    os.utime(ws.root / 'runs' / RUN_LIBRE / 'salida', (viejo, viejo))
    (ws.root / 'tmp').mkdir()
    (ws.root / 'tmp' / 'basura.txt').write_text('x', encoding='utf-8')
    (raiz / 'vinculos_pf.json').write_text('{"schema": "x"}', encoding='utf-8')
    modelo = raiz / '_asistente' / 'interprete'
    modelo.mkdir(parents=True)
    (modelo / 'pesos.pt').write_bytes(b'pesos')
    (raiz / '_asistente' / 'decisiones.jsonl').write_text('{}\n', encoding='utf-8')
    return raiz, ws.id


def _estado(raiz: Path) -> dict[str, str]:
    """Cada fichero con su huella: dos estados iguales son iguales byte a byte."""
    return {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob('*')) if p.is_file() and p.name != 'ultima_copia.json'}


def test_la_copia_lleva_lo_valioso_y_no_lo_que_retiraria_la_limpieza(tmp_path):
    """086:RF-10 — misma regla que la retención; el manifiesto dice qué lleva, qué no y qué queda fuera."""
    from convertersmartgrid.web.copia_datos import crear_copia

    raiz, wid = _crear_datos(tmp_path)
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    rutas = {f['ruta'] for f in m['ficheros']}
    assert f'{wid}/workspace.json' in rutas and f'{wid}/conversiones.json' in rutas
    assert f'{wid}/entradas/red/RED.txt' in rutas and 'vinculos_pf.json' in rutas
    assert f'{wid}/runs/{RUN}/salida/G.dgs' in rutas  # con referencia
    assert f'{wid}/runs/{RUN_INFORME}/salida/informe.docx' in rutas  # informe sin referencia
    assert '_asistente/interprete/pesos.pt' in rutas and '_asistente/decisiones.jsonl' in rutas
    assert not any(RUN_LIBRE in r or '/tmp/' in r for r in rutas)
    assert {o['motivo'] for o in m['omitidos']} >= {'temporales del espacio', 'ejecución que retiraría la limpieza'}
    assert [Path(r).name for r in m['rutas_externas_sin_copiar']] == ['CARGA.txt']
    assert m['bytes_total'] == sum(f['bytes'] for f in m['ficheros']) and not m['errores']
    copia = Path(m['ruta'])
    assert copia.name.startswith('csg-copia-') and (copia / 'manifiesto.json').is_file()
    assert not list((tmp_path / 'copias').glob('.parcial-*'))
    for fichero in m['ficheros']:
        contenido = (copia / 'archivos' / 'datos' / fichero['ruta']).read_bytes()
        assert hashlib.sha256(contenido).hexdigest() == fichero['sha256']


def test_sin_modelos_y_enlaces(tmp_path):
    """086:RF-10 — los pesos se pueden dejar fuera, y un enlace no saca la copia de los datos."""
    from convertersmartgrid.web.copia_datos import crear_copia

    raiz, _ = _crear_datos(tmp_path)
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz}, sin_modelos=True)
    rutas = {f['ruta'] for f in m['ficheros']}
    assert '_asistente/interprete/pesos.pt' not in rutas and '_asistente/decisiones.jsonl' in rutas


def test_restaurar_devuelve_el_mismo_estado(tmp_path):
    """086:RF-10 — se estropea todo, se restaura y cada fichero copiado vuelve igual; lo de antes queda aparte."""
    from convertersmartgrid.web.copia_datos import crear_copia, restaurar_copia, verificar_copia
    from convertersmartgrid.web.workspace import WorkspaceStore

    raiz, wid = _crear_datos(tmp_path)
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    copia = Path(m['ruta'])
    assert verificar_copia(copia)['ok']
    esperado = {f['ruta']: f['sha256'] for f in m['ficheros']}
    # El desastre: el espacio dañado y un fichero borrado.
    (raiz / wid / 'workspace.json').write_text('{roto', encoding='utf-8')
    (raiz / 'vinculos_pf.json').unlink()
    (raiz / 'nuevo.txt').write_text('de después', encoding='utf-8')
    r = restaurar_copia(copia, raices={'datos': raiz})
    assert _estado(raiz) == esperado
    assert r['restaurados'] == len(esperado)
    apartado = next(a for a in r['apartados'] if '.antes-restaurar-' in a)
    assert (Path(apartado) / 'nuevo.txt').read_text(encoding='utf-8') == 'de después'
    assert (Path(apartado) / wid / 'workspace.json').read_text(encoding='utf-8') == '{roto'
    # El espacio abre y su entrada subida sigue apuntando a su sitio.
    ws = WorkspaceStore(raiz).get(wid)
    assert ws is not None and Path(ws.input_path('red')).read_text(encoding='utf-8') == 'red'


def test_restaurar_en_otra_carpeta_resuelve_las_rutas_alli(tmp_path):
    """086:RF-10, 086:RF-6 — restaurar en otro disco funciona, gracias a las rutas relativas."""
    from convertersmartgrid.web.copia_datos import crear_copia, restaurar_copia
    from convertersmartgrid.web.workspace import WorkspaceStore

    raiz, wid = _crear_datos(tmp_path)
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    otra = tmp_path / 'otro_disco' / 'web'
    otra.parent.mkdir()
    r = restaurar_copia(Path(m['ruta']), raices={'datos': otra})
    assert r['apartados'] == []
    ws = WorkspaceStore(otra).get(wid)
    assert Path(ws.input_path('red')).is_relative_to(otra)


@pytest.mark.parametrize('dano', ['borrado', 'alterado', 'ruta_que_sale', 'manifiesto'])
def test_una_copia_danada_no_se_restaura_y_no_toca_nada(tmp_path, dano):
    """086:RF-10 — se comprueba cada huella antes de empezar; una copia mala no arruina lo que hay."""
    from convertersmartgrid.web.copia_datos import CopiaNoValida, crear_copia, restaurar_copia, verificar_copia

    raiz, wid = _crear_datos(tmp_path)
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    copia = Path(m['ruta'])
    objetivo = copia / 'archivos' / 'datos' / wid / 'workspace.json'
    if dano == 'borrado':
        objetivo.unlink()
    elif dano == 'alterado':
        objetivo.write_text('{"cambiado": true}', encoding='utf-8')
    elif dano == 'ruta_que_sale':
        datos = json.loads((copia / 'manifiesto.json').read_text(encoding='utf-8'))
        datos['ficheros'][0]['ruta'] = '../../fuera.txt'
        (copia / 'manifiesto.json').write_text(json.dumps(datos), encoding='utf-8')
    else:
        (copia / 'manifiesto.json').write_text('{roto', encoding='utf-8')
    antes = _estado(raiz)
    if dano != 'manifiesto':
        assert not verificar_copia(copia)['ok']
    with pytest.raises(CopiaNoValida):
        restaurar_copia(copia, raices={'datos': raiz})
    assert _estado(raiz) == antes


def test_manifiesto_de_version_futura_no_se_restaura(tmp_path):
    """086:RF-10 — igual que un espacio: una copia de un programa más nuevo no se interpreta a ciegas."""
    from convertersmartgrid.web.copia_datos import CopiaNoValida, crear_copia, restaurar_copia

    raiz, _ = _crear_datos(tmp_path)
    copia = Path(crear_copia(tmp_path / 'copias', raices={'datos': raiz})['ruta'])
    datos = json.loads((copia / 'manifiesto.json').read_text(encoding='utf-8'))
    datos['version'] = 99
    (copia / 'manifiesto.json').write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(CopiaNoValida, match='Actualice'):
        restaurar_copia(copia, raices={'datos': raiz})


def test_el_destino_no_puede_estar_dentro_de_los_datos(tmp_path):
    """086:RF-10 — la copia se copiaría a sí misma, y un disco que falla se lleva ambas."""
    from convertersmartgrid.web.copia_datos import crear_copia

    raiz, _ = _crear_datos(tmp_path)
    with pytest.raises(ValueError, match='dentro de los datos'):
        crear_copia(raiz / 'copias', raices={'datos': raiz})


def test_un_fallo_de_lectura_queda_en_la_copia_y_no_cuenta_como_buena(tmp_path, monkeypatch):
    """086:RF-10, 086:RF-47 — con errores no se restaura ni calla el aviso de que falta copia."""
    from convertersmartgrid.web import copia_datos as modulo

    raiz, wid = _crear_datos(tmp_path)
    original = modulo._copiar_con_huella

    def falla(origen, destino):
        if origen.name == 'vinculos_pf.json':
            raise PermissionError('en uso')
        return original(origen, destino)

    monkeypatch.setattr(modulo, '_copiar_con_huella', falla)
    m = modulo.crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    assert [Path(e['ruta']).name for e in m['errores']] == ['vinculos_pf.json']
    monkeypatch.setattr(modulo, '_copiar_con_huella', original)
    assert modulo.estado_copia(raiz)['ultima'] is None
    with pytest.raises(modulo.CopiaNoValida, match='errores'):
        modulo.restaurar_copia(Path(m['ruta']), raices={'datos': raiz})


def test_copia_tambien_la_raiz_heredada_y_la_configuracion_local(tmp_path):
    """086:RF-10 — los espacios de ``output/web`` y el perfil local no están en git: si se pierden, no vuelven."""
    from convertersmartgrid.web import copia_datos as modulo

    programa = tmp_path / 'programa'
    heredada = programa / 'output' / 'web'
    heredada.mkdir(parents=True)
    (heredada / 'vinculos_pf.json').write_text('{}', encoding='utf-8')
    config = programa / 'config'
    config.mkdir()
    (config / 'perfil_empresa.json').write_text('{"perfil": "x"}', encoding='utf-8')
    (config / 'de_git.json').write_text('{}', encoding='utf-8')
    raiz, _ = _crear_datos(tmp_path)
    raices = modulo.raices_de_datos(programa)
    assert set(raices) == {'datos', 'heredada', 'config'} and raices['datos'] == raiz
    m = modulo.crear_copia(tmp_path / 'copias', raices=raices)
    por_raiz = {f['raiz'] for f in m['ficheros']}
    assert por_raiz == {'datos', 'heredada', 'config'}
    assert [f['ruta'] for f in m['ficheros'] if f['raiz'] == 'config'] == ['perfil_empresa.json']
    (config / 'perfil_empresa.json').write_text('{"perfil": "otro"}', encoding='utf-8')
    r = modulo.restaurar_copia(Path(m['ruta']), raices=raices)
    assert json.loads((config / 'perfil_empresa.json').read_text(encoding='utf-8')) == {'perfil': 'x'}
    assert (config / 'de_git.json').is_file()
    assert any('perfil_empresa.json.antes-restaurar-' in a for a in r['apartados'])


def test_un_espacio_danado_entra_entero(tmp_path):
    """086:RF-10 — sin poder leer sus referencias, ninguna ejecución se da por prescindible."""
    from convertersmartgrid.web.copia_datos import crear_copia

    raiz, wid = _crear_datos(tmp_path)
    (raiz / wid / 'workspace.json').write_text('{roto', encoding='utf-8')
    rutas = {f['ruta'] for f in crear_copia(tmp_path / 'copias', raices={'datos': raiz})['ficheros']}
    assert f'{wid}/runs/{RUN_LIBRE}/salida/F.dgs' in rutas and f'{wid}/workspace.json' in rutas


def _herramienta(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RAIZ / 'tools/copia_datos.py'), *args], capture_output=True,
                          encoding='utf-8', timeout=120,
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8', **(env or {})})


def test_la_orden_de_copia_y_la_de_restauracion(tmp_path):
    """086:RF-10 — las órdenes de verdad: crear, verificar, estado y restaurar, con sus códigos de salida."""
    raiz, wid = _crear_datos(tmp_path)
    salida = _herramienta('crear', '--destino', str(tmp_path / 'copias'), '--raiz-datos', str(raiz))
    assert salida.returncode == 0, salida.stderr
    creada = json.loads(salida.stdout)
    assert creada['ficheros'] > 3 and creada['errores'] == []
    assert _herramienta('verificar', '--copia', creada['ruta']).returncode == 0
    estado = json.loads(_herramienta('estado', env={'CSG_WEB_DATA': str(raiz)}).stdout)
    assert estado['vencida'] is False and estado['ruta'] == creada['ruta']
    manifiesto = json.loads((Path(creada['ruta']) / 'manifiesto.json').read_text(encoding='utf-8'))
    (raiz / wid / 'workspace.json').write_text('{roto', encoding='utf-8')
    salida = _herramienta('restaurar', '--copia', creada['ruta'], '--raiz-datos', str(raiz))
    assert salida.returncode == 0, salida.stderr
    assert _estado(raiz) == {f['ruta']: f['sha256'] for f in manifiesto['ficheros']}
    (Path(creada['ruta']) / 'manifiesto.json').write_text('{roto', encoding='utf-8')
    fallo = _herramienta('verificar', '--copia', creada['ruta'])
    assert fallo.returncode == 1 and 'manifiesto' in fallo.stderr


def test_la_orden_no_copia_con_trabajos_a_medias_salvo_que_se_fuerce(tmp_path):
    """086:RF-10 — copiar en medio de una calibración guardaría una mezcla de antes y de después."""
    raiz, _ = _crear_datos(tmp_path)
    (raiz / '_trabajos').mkdir()
    (raiz / '_trabajos' / 'j.json').write_text(json.dumps({'title': 'Calibrar', 'status': 'running'}), encoding='utf-8')
    salida = _herramienta('crear', '--destino', str(tmp_path / 'copias'), '--raiz-datos', str(raiz))
    assert salida.returncode == 1 and 'Calibrar' in salida.stderr
    assert not (tmp_path / 'copias').exists()
    assert _herramienta('crear', '--destino', str(tmp_path / 'copias'), '--raiz-datos', str(raiz),
                        '--forzar').returncode == 0


def test_restaurar_se_niega_con_la_web_en_marcha(tmp_path):
    """086:RF-10 — la web tiene los espacios en memoria y, al guardar, pisaría lo restaurado."""
    import socket

    raiz, _ = _crear_datos(tmp_path)
    creada = json.loads(_herramienta('crear', '--destino', str(tmp_path / 'copias'), '--raiz-datos', str(raiz)).stdout)
    with socket.socket() as servidor:
        servidor.bind(('127.0.0.1', 0))
        servidor.listen()
        puerto = str(servidor.getsockname()[1])
        salida = _herramienta('restaurar', '--copia', creada['ruta'], '--puerto', puerto)
    assert salida.returncode == 1 and 'en marcha' in salida.stderr


def test_la_orden_de_identidad_la_fija_antes_de_renombrar(tmp_path):
    """086:RF-7 — para renombrar sin depender de que la web haya arrancado con este código."""
    salida = _herramienta('identidad')
    datos = json.loads(salida.stdout)
    assert salida.returncode == 0 and len(datos['id']) >= 16 and 'fijada' in datos


# ---------------------------------------------------------------- RF-47
def test_aviso_sin_copia_y_con_copia_vieja(tmp_path, monkeypatch):
    """086:RF-47 — sin ninguna, avisa; reciente, calla; pasada la antigüedad configurada, avisa."""
    from convertersmartgrid.web.copia_datos import crear_copia, estado_copia

    raiz, _ = _crear_datos(tmp_path)
    nunca = estado_copia(raiz)
    assert nunca['vencida'] is True and nunca['ultima'] is None and 'No hay ninguna' in nunca['aviso']
    momento = time.time()
    crear_copia(tmp_path / 'copias', raices={'datos': raiz}, ahora=momento)
    reciente = estado_copia(raiz, ahora=momento + 86400)
    assert reciente['vencida'] is False and reciente['aviso'] is None and reciente['edad_dias'] == 1
    vieja = estado_copia(raiz, ahora=momento + 8 * 86400)
    assert vieja['vencida'] is True and '8 días' in vieja['aviso'] and vieja['maxima_dias'] == 7
    monkeypatch.setenv('CSG_COPIA_MAX_DIAS', '30')
    assert estado_copia(raiz, ahora=momento + 8 * 86400)['vencida'] is False
    monkeypatch.setenv('CSG_COPIA_MAX_DIAS', 'nada')
    assert estado_copia(raiz, ahora=momento)['maxima_dias'] == 7


def test_la_web_avisa_de_la_copia(tmp_path):
    """086:RF-47 — el aviso llega por la API; tras copiar deja de avisar."""
    from convertersmartgrid.web.app import create_app
    from convertersmartgrid.web.copia_datos import crear_copia

    raiz, _ = _crear_datos(tmp_path)
    with TestClient(create_app(raiz, host='127.0.0.1')) as cliente:
        estado = cliente.get('/api/health').json()['copia_datos']
        assert estado['vencida'] is True and 'tools/copia_datos.py' in estado['aviso']
        crear_copia(tmp_path / 'copias', raices={'datos': raiz})
        assert cliente.get('/api/health').json()['copia_datos']['vencida'] is False
