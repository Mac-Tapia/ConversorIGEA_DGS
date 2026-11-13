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
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'web/_asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'web/_digital_twin'))
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(tmp_path / 'config/perfil_empresa.json'))
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


def _todos(manifiesto: dict) -> list[dict]:
    """086:RF-79: cada nombre de la copia, también los de un fichero guardado una vez, con su huella."""
    return [fila for f in manifiesto['ficheros']
            for fila in [f, *({**o, 'sha256': f['sha256'], 'bytes': f['bytes']} for o in f.get('otros_nombres') or [])]]


def _estado(raiz: Path) -> dict[str, str]:
    """Cada fichero con su huella: dos estados iguales son iguales byte a byte."""
    return {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob('*')) if p.is_file() and p.name != 'ultima_copia.json'}


def _configurar_raices_externas(tmp_path, monkeypatch):
    from convertersmartgrid.web import copia_datos as copia
    program = tmp_path / 'programa'
    program.mkdir()
    local = tmp_path / 'local'
    monkeypatch.setattr(copia, 'raiz_local', lambda _p: local)
    monkeypatch.setattr(copia, 'es_programa_instalado', lambda _p: True)
    monkeypatch.setattr(copia, 'project_root', lambda: program)
    assistant, twin = tmp_path / 'asistente_externo', tmp_path / 'gemelo_externo'
    profile = tmp_path / 'configuracion_cliente/mi_perfil.json'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(assistant))
    monkeypatch.setenv('CSG_TWIN_DATA', str(twin))
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(profile))
    critical = [tmp_path / 'web/dato.txt', assistant / 'modelo.pt', assistant / 'eventos.jsonl',
                twin / 'pesos.pt', profile, local / 'config/line_type_aliases.json']
    for index, path in enumerate(critical):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('original_' + str(index)).encode())
    return copia, critical


def test_copia_y_restauracion_incluyen_raices_externas_y_perfil_archivo(tmp_path, monkeypatch):
    """086:RF-38, 086:RF-47 — modelos y perfil en sus rutas explícitas sobreviven a la reversión."""
    copia, critical = _configurar_raices_externas(tmp_path, monkeypatch)
    before = {str(p): p.read_bytes() for p in critical}
    roots = copia.raices_de_datos()
    manifest = copia.crear_copia(tmp_path / 'copias', raices=roots)
    assert manifest['version'] == copia.VERSION_MANIFIESTO and manifest['tipos_raiz']['perfil_empresa'] == 'archivo'
    included = {str((Path(manifest['raices'][row['raiz']]) if manifest['tipos_raiz'][row['raiz']] == 'archivo'
                     else Path(manifest['raices'][row['raiz']]) / row['ruta']).resolve()) for row in _todos(manifest)}
    assert set(before) <= included
    for path in critical:
        path.write_bytes(b'posterior a la copia')
    result = copia.restaurar_copia(Path(manifest['ruta']), raices=roots)
    assert {str(p): p.read_bytes() for p in critical} == before
    assert result['apartados']
    assert any(p.read_bytes() == b'posterior a la copia' for p in Path(critical[4].parent).glob('*.antes-restaurar-*'))


def test_fallo_intermedio_de_restauracion_recupera_configuracion_y_datos(tmp_path, monkeypatch):
    """086:RF-38 — un error al publicar la segunda raíz no deja la configuración de otra versión."""
    from convertersmartgrid.web import copia_datos as copia
    data, config = tmp_path / 'web', tmp_path / 'config'
    data.mkdir(); config.mkdir()
    file, profile = data / 'dato.txt', config / 'perfil_empresa.json'
    file.write_bytes(b'antes'); profile.write_bytes(b'antes')
    roots = {'datos': data, 'config': config}
    backup = Path(copia.crear_copia(tmp_path / 'copias', raices=roots)['ruta'])
    file.write_bytes(b'actual'); profile.write_bytes(b'actual')
    replace = Path.replace
    def fallar_publicacion(path, target):
        if '.restaurando-' in path.name and Path(target) == data:
            raise OSError('fallo de publicación inyectado')
        return replace(path, target)
    monkeypatch.setattr(Path, 'replace', fallar_publicacion)
    with pytest.raises(OSError, match='inyectado'):
        copia.restaurar_copia(backup, raices=roots)
    assert file.read_bytes() == profile.read_bytes() == b'actual'


def test_restauracion_automatica_recupera_un_perfil_externo_que_ya_no_existe(tmp_path, monkeypatch):
    """086:RF-38 — perder el perfil no elimina su destino de la restauración automática."""
    copia, critical = _configurar_raices_externas(tmp_path, monkeypatch)
    profile = critical[4]
    expected = profile.read_bytes()
    backup = Path(copia.crear_copia(tmp_path / 'copias')['ruta'])
    profile.unlink()
    copia.restaurar_copia(backup)
    assert profile.read_bytes() == expected


def test_perfil_personalizado_en_config_se_restaura_sin_tocar_otros_archivos(tmp_path, monkeypatch):
    """086:RF-38 — la copia incluye un nombre de perfil propio y conserva el resto de configuración."""
    copia, critical = _configurar_raices_externas(tmp_path, monkeypatch)
    config = tmp_path / 'local/config'
    profile = config / 'perfil_personalizado.json'
    critical[4].replace(profile)
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(profile))
    expected = profile.read_bytes()
    untouched = config / 'no_tocar.json'
    untouched.write_bytes(b'no se debe restaurar desde otro archivo')
    backup = Path(copia.crear_copia(tmp_path / 'copias')['ruta'])
    profile.write_bytes(b'posterior')
    copia.restaurar_copia(backup)
    assert profile.read_bytes() == expected
    assert untouched.read_bytes() == b'no se debe restaurar desde otro archivo'


def test_manifiesto_v2_con_tipo_desconocido_se_rechaza_sin_cambiar_datos(tmp_path, monkeypatch):
    """086:RF-38, 086:RF-47 — un formato no soportado no se interpreta como directorio."""
    copia, critical = _configurar_raices_externas(tmp_path, monkeypatch)
    backup = Path(copia.crear_copia(tmp_path / 'copias')['ruta'])
    manifest = backup / copia.MANIFIESTO
    data = json.loads(manifest.read_text(encoding='utf-8'))
    data['tipos_raiz']['perfil_empresa'] = 'desconocido'
    manifest.write_text(json.dumps(data), encoding='utf-8')
    before = {str(p):p.read_bytes() for p in critical}
    with pytest.raises(copia.CopiaNoValida, match='Tipos'):
        copia.restaurar_copia(backup)
    assert {str(p):p.read_bytes() for p in critical} == before


def test_perfil_que_desaparece_no_actualiza_el_registro_de_copia_valida(tmp_path, monkeypatch):
    """086:RF-38, 086:RF-47 — perder un archivo configurado no se declara una copia completa."""
    copia, critical = _configurar_raices_externas(tmp_path, monkeypatch)
    roots = copia.raices_de_datos()
    register = copia._registro_ultima(roots['datos'])
    register.parent.mkdir(parents=True)
    register.write_bytes(b'{"ruta":"copia anterior"}')
    copy = copia._copiar_con_huella
    def desaparecer(source, target):
        if Path(source) == critical[4]:
            Path(source).unlink()
            raise FileNotFoundError(str(source))
        return copy(source, target)
    monkeypatch.setattr(copia, '_copiar_con_huella', desaparecer)
    result = copia.crear_copia(tmp_path / 'copias', raices=roots)
    assert result['errores']
    assert register.read_bytes() == b'{"ruta":"copia anterior"}'


@pytest.mark.parametrize('case', ['fila', 'ruta', 'raiz', 'bytes', 'sha256'])
def test_manifiesto_mal_formado_se_rechaza_con_error_controlado(tmp_path, case):
    """086:RF-47 — tipos JSON inválidos no causan excepciones de implementación ni restauraciones."""
    from convertersmartgrid.web import copia_datos as copia
    source = tmp_path / 'web'; source.mkdir()
    original = source / 'dato.txt'; original.write_bytes(b'original')
    folder = Path(copia.crear_copia(tmp_path / 'copias', raices={'datos':source})['ruta'])
    path = folder / copia.MANIFIESTO
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if case == 'fila':
        manifest['ficheros'] = [42]
    else:
        manifest['ficheros'][0][case] = {'ruta':[], 'raiz':[], 'bytes':'ocho', 'sha256':None}[case]
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(copia.CopiaNoValida):
        copia.verificar_copia(folder)
    assert original.read_bytes() == b'original'


def test_dos_archivos_no_pueden_restaurarse_sobre_el_mismo_destino(tmp_path, monkeypatch):
    """086:RF-38 — una colisión de destinos no pisa los originales ni sus apartados."""
    copia, critical = _configurar_raices_externas(tmp_path, monkeypatch)
    roots = copia.raices_de_datos()
    folder = Path(copia.crear_copia(tmp_path / 'copias', raices=roots)['ruta'])
    critical[5].write_bytes(b'alias actual')
    roots['perfil_empresa'] = critical[5]
    before = {str(p):p.read_bytes() for p in critical}
    with pytest.raises(copia.CopiaNoValida, match='(?i)destino|solap'):
        copia.restaurar_copia(folder, raices=roots)
    assert {str(p):p.read_bytes() for p in critical} == before


def test_lector_nuevo_conserva_restauracion_de_manifiesto_v1(tmp_path):
    """086:RF-38 — actualizar el formato no invalida las copias previas del operador."""
    from convertersmartgrid.web import copia_datos as copia
    source = tmp_path / 'web'; source.mkdir()
    (source / 'dato.txt').write_bytes(b'original')
    manifest = copia.crear_copia(tmp_path / 'copias', raices={'datos':source})
    folder = Path(manifest['ruta'])
    legacy = json.loads((folder / copia.MANIFIESTO).read_text(encoding='utf-8'))
    legacy['version'] = 1
    legacy.pop('tipos_raiz', None)
    (folder / copia.MANIFIESTO).write_text(json.dumps(legacy), encoding='utf-8')
    target = tmp_path / 'restaurado'
    copia.restaurar_copia(folder, raices={'datos':target})
    assert (target / 'dato.txt').read_bytes() == b'original'


def test_directorios_de_restauracion_solapados_se_rechazan_antes_de_escribir(tmp_path):
    """086:RF-38 — raíces ambiguas no pueden producir movimientos que invaliden otra raíz."""
    from convertersmartgrid.web import copia_datos as copia
    data = tmp_path / 'web'; child = data / 'modelos'; child.mkdir(parents=True)
    (child / 'pesos.pt').write_bytes(b'original')
    output = tmp_path / 'copia'
    with pytest.raises(ValueError, match='solap|superpuest'):
        copia.crear_copia(output, raices={'datos':data,'asistente':child})
    assert not output.exists() and (child / 'pesos.pt').read_bytes() == b'original'


def test_sin_modelos_tambien_filtra_raices_externas_sin_perder_registros(tmp_path, monkeypatch):
    """086:RF-47 — una raíz independiente no esquiva la elección de omitir pesos."""
    copia, _ = _configurar_raices_externas(tmp_path, monkeypatch)
    manifest = copia.crear_copia(tmp_path / 'copias', raices=copia.raices_de_datos(), sin_modelos=True)
    assert any(r['raiz']=='asistente' and r['ruta']=='eventos.jsonl' for r in manifest['ficheros'])
    assert not any(r['ruta'].endswith('.pt') for r in manifest['ficheros'])
    assert any('pesos' in row['motivo'] for row in manifest['omitidos'])


def test_la_copia_lleva_lo_valioso_y_no_lo_que_retiraria_la_limpieza(tmp_path):
    """086:RF-10 — misma regla que la retención; el manifiesto dice qué lleva, qué no y qué queda fuera."""
    from convertersmartgrid.web.copia_datos import crear_copia

    raiz, wid = _crear_datos(tmp_path)
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    rutas = {f['ruta'] for f in _todos(m)}
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
    rutas = {f['ruta'] for f in _todos(m)}
    assert '_asistente/interprete/pesos.pt' not in rutas and '_asistente/decisiones.jsonl' in rutas


def test_restaurar_devuelve_el_mismo_estado(tmp_path):
    """086:RF-10 — se estropea todo, se restaura y cada fichero copiado vuelve igual; lo de antes queda aparte."""
    from convertersmartgrid.web.copia_datos import crear_copia, restaurar_copia, verificar_copia
    from convertersmartgrid.web.workspace import WorkspaceStore

    raiz, wid = _crear_datos(tmp_path)
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    copia = Path(m['ruta'])
    assert verificar_copia(copia)['ok']
    esperado = {f['ruta']: f['sha256'] for f in _todos(m)}
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
    assert set(raices) == {'datos', 'heredada', 'config', 'perfil_empresa'} and raices['datos'] == raiz
    m = modulo.crear_copia(tmp_path / 'copias', raices=raices)
    por_raiz = {f['raiz'] for f in _todos(m)}
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
    assert _estado(raiz) == {f['ruta']: f['sha256'] for f in _todos(manifiesto)}
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


# ---------------------------------------------------------------- RF-78 a RF-86: cada fichero físico una vez
def _datos_con_enlaces(tmp_path) -> tuple[Path, bytes]:
    """Como el 2026-11-12: el mismo paquete en varias ejecuciones, por enlaces duros, y una copia idéntica aparte."""
    raiz = tmp_path / 'web'
    paquete = raiz / 'original' / 'ELOR25_V2.zip'
    paquete.parent.mkdir(parents=True)
    contenido = os.urandom(256 * 1024)
    paquete.write_bytes(contenido)
    for n in range(4):
        enlace = raiz / f'corrida_{n}' / 'entradas' / 'ELOR25_V2.zip'
        enlace.parent.mkdir(parents=True)
        os.link(paquete, enlace)
    (raiz / 'otra').mkdir()
    (raiz / 'otra' / 'mismo_contenido.zip').write_bytes(contenido)
    (raiz / 'otra' / 'distinto.txt').write_bytes(b'x' * 10)
    return raiz, contenido


_RUTAS_PAQUETE = ['original/ELOR25_V2.zip', 'otra/mismo_contenido.zip',
                  *(f'corrida_{n}/entradas/ELOR25_V2.zip' for n in range(4))]


def test_la_copia_guarda_una_vez_cada_fichero_fisico_con_todos_sus_nombres(tmp_path):
    """086:RF-78, 086:RF-79 — cinco enlaces duros y una copia idéntica ocupan una vez; el manifiesto los nombra a todos."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, contenido = _datos_con_enlaces(tmp_path)
    m = copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    guardados = [p for p in (Path(m['ruta']) / 'archivos').rglob('*') if p.is_file()]
    assert sum(p.stat().st_size for p in guardados) == len(contenido) + 10 and len(guardados) == 2
    assert m['bytes_total'] == len(contenido) + 10 and m['bytes_logicos'] == 6 * len(contenido) + 10
    paquete = next(f for f in m['ficheros'] if f['bytes'] == len(contenido))
    assert paquete['sha256'] == hashlib.sha256(contenido).hexdigest()
    assert {paquete['ruta'], *(o['ruta'] for o in paquete['otros_nombres'])} == set(_RUTAS_PAQUETE)
    assert m['version'] == copia.VERSION_MANIFIESTO == 3 and m['nombres'] == 7 and m['otros_nombres'] == 5
    comprobado = copia.verificar_copia(Path(m['ruta']))
    assert comprobado['ok'] and comprobado['ficheros'] == 2 and comprobado['nombres'] == 7


def test_restaurar_recrea_los_nombres_como_enlaces_duros_en_la_misma_unidad(tmp_path):
    """086:RF-80 — en la misma unidad cada enlace duro vuelve como enlace del primero; el fichero aparte con el mismo
    contenido vuelve como copia suya, no enlazado (antes volvían los seis enlazados)."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, contenido = _datos_con_enlaces(tmp_path)
    m = copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    destino = tmp_path / 'restaurado'
    r = copia.restaurar_copia(Path(m['ruta']), raices={'datos': destino})
    assert r['restaurados'] == 7 and r['ficheros_fisicos'] == 2 and r['enlaces'] == 4 and r['copias_de_nombres'] == 1
    enlazados = [ruta for ruta in _RUTAS_PAQUETE if ruta != 'otra/mismo_contenido.zip']
    assert len({os.stat(destino / ruta).st_ino for ruta in enlazados}) == 1
    assert os.stat(destino / enlazados[0]).st_nlink == 5
    assert os.stat(destino / 'otra/mismo_contenido.zip').st_nlink == 1
    assert all((destino / ruta).read_bytes() == contenido for ruta in _RUTAS_PAQUETE)
    assert (destino / 'otra/distinto.txt').read_bytes() == b'x' * 10


def test_sin_enlaces_duros_en_el_destino_cada_nombre_vuelve_como_copia(tmp_path, monkeypatch):
    """086:RF-80 — otra unidad (o Drive, sin enlaces duros): cada nombre se copia y se comprueba su huella."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, contenido = _datos_con_enlaces(tmp_path)
    m = copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz})

    def sin_enlaces(*_a, **_k):
        raise OSError(17, 'No es la misma unidad')
    monkeypatch.setattr(copia.os, 'link', sin_enlaces)
    destino = tmp_path / 'otra_unidad'
    r = copia.restaurar_copia(Path(m['ruta']), raices={'datos': destino})
    assert r['enlaces'] == 0 and r['copias_de_nombres'] == 5
    assert (destino / 'corrida_3/entradas/ELOR25_V2.zip').read_bytes() == contenido
    assert os.stat(destino / 'corrida_3/entradas/ELOR25_V2.zip').st_nlink == 1


def test_la_verificacion_detecta_un_fichero_alterado_y_no_restaura(tmp_path):
    """086:RF-79, 086:RF-10 — la huella del fichero guardado una vez sigue mandando: alterado, no se restaura."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, contenido = _datos_con_enlaces(tmp_path)
    m = copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    paquete = next(f for f in m['ficheros'] if f['bytes'] == len(contenido))
    guardado = Path(m['ruta']) / 'archivos' / 'datos' / paquete['ruta']
    guardado.write_bytes(b'Z' + contenido[1:])
    resultado = copia.verificar_copia(Path(m['ruta']))
    assert not resultado['ok'] and resultado['distintos'] == [paquete['ruta']]
    with pytest.raises(copia.CopiaNoValida):
        copia.restaurar_copia(Path(m['ruta']), raices={'datos': tmp_path / 'restaurado'})
    assert not (tmp_path / 'restaurado').exists()


def test_un_nombre_que_sale_de_la_copia_no_se_sigue(tmp_path):
    """086:RF-79 — los otros nombres del manifiesto también son una entrada: uno con «..» invalida la copia."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, _ = _datos_con_enlaces(tmp_path)
    folder = Path(copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz})['ruta'])
    datos = json.loads((folder / copia.MANIFIESTO).read_text(encoding='utf-8'))
    con_otros = next(f for f in datos['ficheros'] if f.get('otros_nombres'))
    con_otros['otros_nombres'].append({'raiz': 'datos', 'ruta': '../fuera.zip'})
    (folder / copia.MANIFIESTO).write_text(json.dumps(datos), encoding='utf-8')
    assert not copia.verificar_copia(folder)['ok']
    with pytest.raises(copia.CopiaNoValida):
        copia.restaurar_copia(folder, raices={'datos': tmp_path / 'restaurado'})
    assert not (tmp_path / 'fuera.zip').exists()


def test_un_manifiesto_de_version_2_se_sigue_restaurando(tmp_path):
    """086:RF-79 — una copia hecha antes de la versión 3, con un fichero por nombre, se verifica y restaura igual."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, contenido = _datos_con_enlaces(tmp_path)
    folder = Path(copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz})['ruta'])
    # Lo que escribía la versión 2: cada nombre con sus bytes, sin «otros_nombres».
    viejo = json.loads((folder / copia.MANIFIESTO).read_text(encoding='utf-8'))
    filas = []
    for fila in _todos(viejo):
        filas.append({k: fila[k] for k in ('raiz', 'ruta', 'bytes', 'sha256')})
        guardado = folder / 'archivos' / fila['raiz'] / fila['ruta']
        if not guardado.exists():
            guardado.parent.mkdir(parents=True, exist_ok=True)
            guardado.write_bytes(contenido)
    viejo.update(version=2, ficheros=filas)
    (folder / copia.MANIFIESTO).write_text(json.dumps(viejo), encoding='utf-8')
    assert copia.verificar_copia(folder)['ok']
    destino = tmp_path / 'restaurado'
    r = copia.restaurar_copia(folder, raices={'datos': destino})
    assert r['restaurados'] == 7 and r['enlaces'] == 0
    assert (destino / 'corrida_2/entradas/ELOR25_V2.zip').read_bytes() == contenido


def test_antes_de_copiar_se_dice_cuanto_ocupa_y_si_no_cabe_no_se_empieza(tmp_path, monkeypatch):
    """086:RF-82, 086:RF-83 — bytes físicos únicos frente al libre del destino; sin sitio, ni la «.parcial»."""
    import shutil as _shutil

    from convertersmartgrid.web import copia_datos as copia

    raiz, contenido = _datos_con_enlaces(tmp_path)
    destino = tmp_path / 'drive' / 'copias_de_datos'
    plan = copia.planificar_copia(destino, raices={'datos': raiz})
    # Por inodo: el paquete (una vez por sus cinco enlaces), su copia idéntica y el texto; la huella une luego los dos.
    assert plan['ficheros_fisicos'] == 3 and plan['nombres'] == 7 and plan['cabe'] is True
    assert plan['bytes_fisicos'] == 2 * len(contenido) + 10 and plan['bytes_logicos'] == 6 * len(contenido) + 10
    assert 'ficheros físicos' in copia.texto_plan(plan) and 'Libres en' in copia.texto_plan(plan)
    real = _shutil.disk_usage
    monkeypatch.setattr(copia.shutil, 'disk_usage', lambda p: real(p)._replace(free=plan['bytes_fisicos']))
    avisos = []
    with pytest.raises(copia.SinEspacio, match='No cabe'):
        copia.crear_copia(destino, raices={'datos': raiz}, avisar=avisos.append)
    assert avisos and avisos[0]['cabe'] is False
    assert not destino.exists()


def test_la_orden_calcular_y_crear_dicen_lo_que_ocupara(tmp_path):
    """086:RF-82, 086:RF-83 — la orden lo dice antes de copiar; ``calcular`` no escribe nada."""
    raiz, _ = _datos_con_enlaces(tmp_path)
    destino = tmp_path / 'copias'
    salida = _herramienta('calcular', '--destino', str(destino), '--raiz-datos', str(raiz))
    assert salida.returncode == 0, salida.stderr
    assert json.loads(salida.stdout)['nombres'] == 7 and 'La copia ocupará' in salida.stderr
    assert not destino.exists()
    creada = _herramienta('crear', '--destino', str(destino), '--raiz-datos', str(raiz), '--puerto', '9')
    assert creada.returncode == 0 and 'La copia ocupará' in creada.stderr
    assert json.loads(creada.stdout)['nombres'] == 7


def test_un_destino_que_bloquea_se_reintenta_y_la_copia_sale_buena(tmp_path, monkeypatch):
    """086:RF-81 — Drive bloquea un fichero al sincronizar: se repite con espera y la copia queda entera."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, _ = _datos_con_enlaces(tmp_path)
    original = copia._copiar_con_huella
    fallos = {'n': 0}

    def bloqueado(origen, destino):
        if fallos['n'] < 2:
            fallos['n'] += 1
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(b'medio')          # lo escrito a medias se retira antes de repetir
            raise PermissionError(13, 'El proceso no tiene acceso al archivo porque está siendo utilizado')
        return original(origen, destino)
    monkeypatch.setattr(copia, '_copiar_con_huella', bloqueado)
    m = copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz}, espera=0)
    assert fallos['n'] == 2 and not m['errores'] and copia.verificar_copia(Path(m['ruta']))['ok']

    def siempre(_o, _d):
        raise PermissionError(13, 'bloqueado')
    monkeypatch.setattr(copia, '_copiar_con_huella', siempre)
    m = copia.crear_copia(tmp_path / 'copias2', raices={'datos': raiz}, espera=0, reintentos=2)
    assert m['errores'] and all('bloqueado' in e['motivo'] for e in m['errores'])
    assert not copia.verificar_copia(Path(m['ruta']))['ok']


def test_una_copia_cancelada_no_deja_nada_con_aspecto_de_buena(tmp_path):
    """086:RF-84 — cancelada a media copia, se retira la «.parcial» y no aparece ninguna «csg-copia-…»."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, _ = _datos_con_enlaces(tmp_path)
    destino = tmp_path / 'copias'
    vueltas = {'n': 0}

    class Cancelada(Exception):
        pass

    def cancelar():
        vueltas['n'] += 1
        if vueltas['n'] == 2:
            raise Cancelada()
    with pytest.raises(Cancelada):
        copia.crear_copia(destino, raices={'datos': raiz}, comprobar_cancelacion=cancelar)
    assert list(destino.iterdir()) == []
    assert copia.estado_copia(raiz)['ultima'] is None


def _esperar(cliente, job_id: str, *, segundos: float = 60) -> dict:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        datos = cliente.get(f'/api/jobs/{job_id}').json()
        if datos['status'] not in ('queued', 'running'):
            return datos
        time.sleep(0.05)
    raise AssertionError(f'el trabajo {job_id} no terminó')


def test_la_web_recuerda_la_carpeta_y_copia_como_trabajo(tmp_path, monkeypatch):
    """086:RF-85, 086:RF-86 — «Hacer una copia ahora»: carpeta recordada, trabajo con progreso, y el aviso calla."""
    from convertersmartgrid.web import copia_datos as copia
    from convertersmartgrid.web.app import create_app

    monkeypatch.setattr(copia, 'raiz_local', lambda _p=None: tmp_path / 'local')
    raiz, wid = _crear_datos(tmp_path)
    destino = tmp_path / 'drive'
    destino.mkdir()
    with TestClient(create_app(raiz, host='127.0.0.1')) as cliente:
        assert cliente.get('/api/copia-datos/carpeta').json() == {'carpeta': None}
        mala = cliente.post(f'/api/workspaces/{wid}/copia-datos', json={'carpeta': str(tmp_path / 'no_existe')})
        assert mala.status_code == 400
        job = cliente.post(f'/api/workspaces/{wid}/copia-datos', json={'carpeta': str(destino)})
        assert job.status_code == 202 and job.json()['kind'] == 'copia_datos'
        fin = _esperar(cliente, job.json()['id'])
        assert fin['status'] == 'done', fin
        assert Path(fin['result']['ruta']).parent == destino
        assert fin['progress']['index'] == fin['progress']['total'] > 0
        assert cliente.get('/api/copia-datos/carpeta').json() == {'carpeta': destino.as_posix()}
        assert (tmp_path / 'local/config/copia_datos.json').is_file()
        assert cliente.get('/api/health').json()['copia_datos']['vencida'] is False
        assert copia.verificar_copia(Path(fin['result']['ruta']))['ok']


def test_la_copia_de_la_web_se_cancela_y_bloquea_otros_trabajos(tmp_path, monkeypatch):
    """086:RF-86, 086:RF-84 — con otro trabajo no empieza; mientras copia no entra otro; cancelada, no queda copia."""
    import threading

    from convertersmartgrid.web import copia_datos as copia
    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app

    monkeypatch.setattr(copia, 'raiz_local', lambda _p=None: tmp_path / 'local')
    monkeypatch.setattr(services, 'check_ready', lambda _ws: None)
    raiz, wid = _crear_datos(tmp_path)
    destino = tmp_path / 'drive'
    destino.mkdir()
    dentro, soltar = threading.Event(), threading.Event()
    original = copia._copiar_con_huella

    def lento(origen, salida):
        dentro.set()
        soltar.wait(20)
        return original(origen, salida)
    monkeypatch.setattr(copia, '_copiar_con_huella', lento)
    with TestClient(create_app(raiz, host='127.0.0.1')) as cliente:
        job = cliente.post(f'/api/workspaces/{wid}/copia-datos', json={'carpeta': str(destino)}).json()
        assert dentro.wait(20)
        otro = cliente.post(f'/api/workspaces/{wid}/load')
        assert otro.status_code == 409 and 'copia de los datos' in otro.json()['detail']
        segunda = cliente.post(f'/api/workspaces/{wid}/copia-datos', json={'carpeta': str(destino)})
        assert segunda.status_code == 409 and 'en curso' in segunda.json()['detail']
        assert cliente.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
        soltar.set()
        fin = _esperar(cliente, job['id'])
        assert fin['status'] == 'cancelled', fin
        assert list(destino.iterdir()) == []
        assert cliente.get('/api/health').json()['copia_datos']['vencida'] is True


def test_los_ficheros_de_igual_contenido_vuelven_independientes(tmp_path):
    """086:RF-80 — solo vuelven enlazados los nombres que eran enlaces duros; dos ficheros distintos con el mismo
    contenido vuelven separados. Dos registros vacíos (``historial.jsonl``) se guardan una vez por su huella, y
    restaurados como enlaces, lo que se añadiera a uno salía también en el otro."""
    from convertersmartgrid.web import copia_datos as copia

    raiz = tmp_path / 'web'
    for carpeta in ('a', 'b'):
        (raiz / carpeta).mkdir(parents=True)
        (raiz / carpeta / 'historial.jsonl').write_bytes(b'')
    os.link(raiz / 'b' / 'historial.jsonl', raiz / 'b' / 'enlace.jsonl')
    m = copia.crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    assert len(m['ficheros']) == 1 and m['nombres'] == 3
    destino = tmp_path / 'restaurado'
    r = copia.restaurar_copia(Path(m['ruta']), raices={'datos': destino})
    assert r['restaurados'] == 3 and r['enlaces'] == 1 and r['copias_de_nombres'] == 1
    with (destino / 'a' / 'historial.jsonl').open('ab') as registro:
        registro.write(b'{"evento": 1}\n')
    assert (destino / 'b' / 'historial.jsonl').read_bytes() == b''
    assert os.stat(destino / 'b' / 'historial.jsonl').st_ino == os.stat(destino / 'b' / 'enlace.jsonl').st_ino
    assert os.stat(destino / 'a' / 'historial.jsonl').st_ino != os.stat(destino / 'b' / 'historial.jsonl').st_ino


def test_una_parcial_que_bloquea_la_sincronizacion_se_retira_igual(tmp_path, monkeypatch):
    """086:RF-84, 086:RF-81 — cancelada, la «.parcial» se retira aunque Drive la tenga bloqueada un momento:
    ``shutil.rmtree`` para en el primer fallo, y callarlo dejaba la carpeta ocupando el destino."""
    from convertersmartgrid.web import copia_datos as copia

    raiz, _ = _datos_con_enlaces(tmp_path)
    destino = tmp_path / 'copias'
    real = copia.shutil.rmtree
    fallos = {'n': 0}

    def bloqueado(ruta, *a, **k):
        if fallos['n'] < 2:
            fallos['n'] += 1
            raise PermissionError(13, 'El proceso no tiene acceso al archivo porque está siendo utilizado')
        return real(ruta, *a, **k)
    monkeypatch.setattr(copia.shutil, 'rmtree', bloqueado)

    class Cancelada(Exception):
        pass

    def cancelar():
        raise Cancelada()
    with pytest.raises(Cancelada):
        copia.crear_copia(destino, raices={'datos': raiz}, comprobar_cancelacion=cancelar, espera=0)
    assert fallos['n'] == 2 and list(destino.iterdir()) == []


def test_mientras_se_copia_no_entra_ningun_trabajo_tampoco_los_del_servidor():
    """086:RF-86 — la cola misma lo impide: los trabajos de VNR-GIS y los reintentos de la vigilancia no pasan por la
    comprobación de la ruta de la web, y la copia guardaba una mezcla de antes y de después."""
    import threading

    from convertersmartgrid.web.jobs import JobManager, TrabajoRechazado

    jobs = JobManager(lambda *_a: None)
    dentro, soltar = threading.Event(), threading.Event()
    try:
        otro = jobs.submit('espacio', 'load', 'Cargar', lambda _ctx: soltar.wait(20))
        # Con otro trabajo en curso la copia no se admite, aunque se encole directamente.
        with pytest.raises(TrabajoRechazado, match='en curso'):
            jobs.submit('espacio', 'copia_datos', 'Copia de los datos', lambda _ctx: None)
        soltar.set()
        limite = time.monotonic() + 20
        while jobs.en_curso() and time.monotonic() < limite:
            time.sleep(0.02)
        soltar.clear()

        def copiar(_ctx):
            dentro.set()
            soltar.wait(20)
        copia = jobs.submit('espacio', 'copia_datos', 'Copia de los datos', copiar)
        assert dentro.wait(20)
        for espacio, kind, carril in (('_vnr', 'vnr_export_dgs', 'engine'), ('otro', 'pf_verificar', 'powerfactory')):
            with pytest.raises(TrabajoRechazado, match='copia de los datos'):
                jobs.submit(espacio, kind, 'Otro', lambda _ctx: None, lane=carril)
        assert [j.id for j in jobs.list() if j.status not in ('done', 'failed', 'cancelled')] == [copia.id]
        assert otro.status == 'done'
    finally:
        soltar.set()
        jobs.shutdown(5)
