"""Entrenamiento en Colab como opción del local: paquete, vuelta del candidato y aviso de datos nuevos.

Spec 113: 113:RF-4, 113:RF-5, 113:RF-6, 113:RF-9, 113:RF-10, 113:RF-11, 113:RF-13, 113:RF-16.
Con nombres sintéticos: ningún dato de la distribuidora entra en el repositorio.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion import entrenamiento_remoto as er

REV = 'a' * 40
OTRA_REV = 'b' * 40
REPO = 'dueno/proyecto'


def _ahora():
    return datetime(2026, 11, 26, 23, 0, 0)


def _dataset(raiz: Path) -> Path:
    d = raiz / 'corpus'
    d.mkdir()
    (d / 'entrenamiento.jsonl').write_text(
        json.dumps({'texto': 'La SET Valle Verde alimenta a Hidro Andina S.A.A.', 'n': 3}, ensure_ascii=False) + '\n',
        encoding='utf-8')
    (d / 'seleccion.jsonl').write_text(json.dumps({'texto': 'sección de bancos'}) + '\n', encoding='utf-8')
    (d / 'dataset_manifest.json').write_text('{"schema": "x"}', encoding='utf-8')
    return d


@pytest.fixture
def familia_texto(monkeypatch):
    """Una familia de prueba que anonimiza al empaquetar (las reales se comprueban una a una, 113 T8)."""
    monkeypatch.setitem(er.FAMILIAS, 'prueba_texto', {'anonimizacion': 'texto', 'entrenar': 'tools/x.py {datos}',
                                                     'puerta': 'tools/x.py evaluar'})
    return 'prueba_texto'


def test_el_paquete_lleva_su_manifiesto_con_huellas_y_se_verifica(tmp_path):
    """113:RF-4, RF-9: cada fichero con su huella; el paquete releído cuadra."""
    m = er.preparar_paquete(_dataset(tmp_path), familia='asistente_redaccion', revision=REV, repositorio=REPO,
                            destino=tmp_path / 'drive', ahora=_ahora)
    carpeta = tmp_path / 'drive' / f'asistente_redaccion_{REV[:8]}_{m["huella"][:8]}'
    assert carpeta.is_dir() and not list((tmp_path / 'drive').glob('.preparando_*'))
    assert m['revision'] == REV and m['familia'] == 'asistente_redaccion'
    assert {f['ruta'] for f in m['ficheros']} == {'entrenamiento.jsonl', 'seleccion.jsonl', 'dataset_manifest.json'}
    assert er.verificar_paquete(carpeta)['huella'] == m['huella']
    (carpeta / 'datos' / 'seleccion.jsonl').write_text('alterado', encoding='utf-8')
    with pytest.raises(ValueError, match='no coincide'):
        er.verificar_paquete(carpeta)


def test_anonimizado_en_origen_se_copia_byte_a_byte(tmp_path):
    """113:RF-5: el corpus de redacción ya viene anonimizado; sus huellas propias deben seguir valiendo."""
    origen = _dataset(tmp_path)
    m = er.preparar_paquete(origen, familia='asistente_redaccion', revision=REV, repositorio=REPO, destino=tmp_path / 'd', ahora=_ahora)
    assert m['anonimizacion']['modo'] == 'en_origen'
    assert all(f['sha256'] == f['sha256_origen'] for f in m['ficheros'])


def test_la_familia_de_texto_oculta_los_nombres(tmp_path, familia_texto):
    """113:RF-5: en los JSONL de texto se ocultan instalación y razón social; las cifras siguen."""
    m = er.preparar_paquete(_dataset(tmp_path), familia=familia_texto, revision=REV, repositorio=REPO, destino=tmp_path / 'd',
                            ahora=_ahora)
    carpeta = next((tmp_path / 'd').iterdir())
    fila = json.loads((carpeta / 'datos' / 'entrenamiento.jsonl').read_text(encoding='utf-8'))
    assert 'Valle Verde' not in fila['texto'] and 'Hidro Andina' not in fila['texto']
    assert fila['n'] == 3 and m['anonimizacion']['modo'] == 'texto'


@pytest.mark.parametrize('nombre', ['red_sintetica.txt', 'base.mdb', 'paquete.bak', 'medidores.xlsx', 'red.dgs'])
def test_los_datos_crudos_nunca_salen(tmp_path, nombre):
    """113:RF-6: TXT, MDB, .bak, libros y DGS de la distribuidora se rechazan y no se escribe nada."""
    d = _dataset(tmp_path)
    (d / nombre).write_bytes(b'x')
    with pytest.raises(er.PaqueteProhibido, match='dato crudo'):
        er.preparar_paquete(d, familia='asistente_redaccion', revision=REV, repositorio=REPO, destino=tmp_path / 'd', ahora=_ahora)
    assert not (tmp_path / 'd').exists()


@pytest.mark.parametrize('ruta', ['prueba.jsonl', 'sellado/x.jsonl', 'test_holdout.jsonl'])
def test_los_conjuntos_sellados_nunca_salen(tmp_path, ruta):
    """113:RF-6: la partición de prueba y lo sellado se quedan en el equipo."""
    d = _dataset(tmp_path)
    (d / ruta).parent.mkdir(parents=True, exist_ok=True)
    (d / ruta).write_text('{}', encoding='utf-8')
    with pytest.raises(er.PaqueteProhibido, match='sellado'):
        er.preparar_paquete(d, familia='asistente_redaccion', revision=REV, repositorio=REPO, destino=tmp_path / 'd', ahora=_ahora)


def test_cambios_sin_commit_se_avisan():
    """113:RF-4: Colab clona la revisión; lo que no está en un commit no lo vería."""
    assert er.cambios_sin_commit(' M src/a.py\n?? tools/b.py\n') == ['src/a.py', 'tools/b.py']
    assert er.cambios_sin_commit('') == []


def _candidato(raiz: Path, paquete: dict, *, revision=REV, nombre='c1') -> Path:
    c = raiz / 'candidatos' / nombre
    c.mkdir(parents=True)
    (c / 'adaptador.safetensors').write_bytes(b'pesos')
    m = er.manifiesto_candidato(familia=paquete['familia'], revision=revision, paquete=paquete['huella'], semilla=11,
                                entorno={'gpu': 'A100', 'torch': '2.5'}, hiperparametros={'lr': 2e-4},
                                metricas={'perdida': 0.9}, carpeta=c, pruebas=[{'lr': 1e-4, 'perdida': 1.1}],
                                ahora=_ahora)
    (c / 'candidato.json').write_text(json.dumps(m), encoding='utf-8')
    return c


def _paquete(tmp_path):
    m = er.preparar_paquete(_dataset(tmp_path), familia='asistente_redaccion', revision=REV, repositorio=REPO,
                            destino=tmp_path / 'drive', ahora=_ahora)
    return m, er.paquetes_de(tmp_path / 'drive')


def test_el_candidato_trae_entorno_hiperparametros_y_todas_las_pruebas(tmp_path):
    """113:RF-8, RF-9: el manifiesto del candidato registra todas las pruebas de la búsqueda, no solo la ganadora."""
    m, paquetes = _paquete(tmp_path)
    c = _candidato(tmp_path, m)
    dato = er.verificar_candidato(c, revision=REV, paquetes=paquetes)
    assert dato['pruebas'] == [{'lr': 1e-4, 'perdida': 1.1}] and dato['entorno']['gpu'] == 'A100'
    assert dato['semilla'] == 11 and dato['hiperparametros'] == {'lr': 2e-4}


def test_se_rechaza_el_candidato_de_otra_revision(tmp_path):
    """113:RF-10: entrenado con otro código: se rechaza con su motivo."""
    m, paquetes = _paquete(tmp_path)
    c = _candidato(tmp_path, m, revision=OTRA_REV)
    with pytest.raises(er.CandidatoRechazado, match='revisión'):
        er.verificar_candidato(c, revision=REV, paquetes=paquetes)


def test_se_rechaza_el_candidato_de_un_paquete_ajeno_o_alterado(tmp_path):
    """113:RF-10: un paquete que no salió de aquí, o un artefacto cambiado, no entran."""
    m, paquetes = _paquete(tmp_path)
    ajeno = dict(m, huella='f' * 64)
    with pytest.raises(er.CandidatoRechazado, match='no salió de este equipo'):
        er.verificar_candidato(_candidato(tmp_path, ajeno, nombre='c2'), revision=REV, paquetes=paquetes)
    c = _candidato(tmp_path, m, nombre='c3')
    (c / 'adaptador.safetensors').write_bytes(b'otros pesos')
    with pytest.raises(er.CandidatoRechazado, match='huella'):
        er.verificar_candidato(c, revision=REV, paquetes=paquetes)


def test_traer_copia_los_validos_sin_activarlos_y_dice_por_que_rechaza(tmp_path):
    """113:RF-10, RF-11: los válidos quedan en local con la orden de su puerta; nada se activa."""
    m, paquetes = _paquete(tmp_path)
    _candidato(tmp_path, m, nombre='bueno')
    _candidato(tmp_path, m, revision=OTRA_REV, nombre='viejo')
    r = {x['candidato']: x for x in er.traer_candidatos(tmp_path / 'candidatos', tmp_path / 'local', revision=REV,
                                                         paquetes=paquetes)}
    assert r['bueno']['aceptado'] and r['bueno']['activado'] is False
    assert r['bueno']['puerta'] == 'tools/asistente_qlora.py evaluar'
    assert (tmp_path / 'local' / 'asistente_redaccion' / 'bueno' / 'candidato.json').is_file()
    assert not r['viejo']['aceptado'] and 'revisión' in r['viejo']['motivo']
    assert not (tmp_path / 'local' / 'asistente_redaccion' / 'viejo').exists()


def test_datos_nuevos_proponen_reentrenar():
    """113:RF-13: crecer lo bastante propone reentrenar; poco no."""
    assert er.hay_datos_nuevos(1300, 1000)
    assert not er.hay_datos_nuevos(1030, 1000)
    assert er.hay_datos_nuevos(60, 0)


def test_el_registro_avisa_cuando_el_dataset_crecio(tmp_path):
    """113:RF-13: se anota con cuántos ejemplos se preparó; al crecer lo bastante, se propone reentrenar."""
    d = _dataset(tmp_path)
    sellada = d / 'prueba_sellada'
    sellada.mkdir()
    (sellada / 'prueba.jsonl').write_text('{"a": 1}\n' * 500, encoding='utf-8')
    assert er.ejemplos_de(d) == 2, 'lo sellado no cuenta'
    registro = tmp_path / 'asistente' / 'colab' / er.REGISTRO_PREPARADOS
    assert er.avisos_de_reentreno(registro) == [], 'sin registro, sin avisos ni errores'
    er.registrar_preparado(registro, familia='asistente_redaccion', origen=d, ejemplos=er.ejemplos_de(d), huella='h',
                           ahora=_ahora)
    assert er.avisos_de_reentreno(registro) == []
    with (d / 'entrenamiento.jsonl').open('a', encoding='utf-8') as f:
        f.write('{"texto": "nuevo"}\n' * 60)
    aviso, = er.avisos_de_reentreno(registro)
    assert (aviso['familia'], aviso['ejemplos_al_preparar'], aviso['ejemplos'], aviso['nuevos']) == (
        'asistente_redaccion', 2, 62, 60)
    registro.write_text('{roto', encoding='utf-8')
    assert er.avisos_de_reentreno(registro) == [], 'un registro ilegible nunca bloquea'


def test_lo_local_no_depende_de_colab(tmp_path):
    """113:RF-16: sin Drive, entrenar en este equipo sigue disponible y la orden es la misma que en Colab."""
    sin_drive = er.opciones_de_entrenamiento(None)
    assert sin_drive[0] == {'donde': 'local', 'disponible': True, 'texto': 'En este equipo'}
    assert sin_drive[1]['disponible'] is False
    assert er.opciones_de_entrenamiento(tmp_path)[1]['disponible'] is True
    assert er.carpeta_drive({er.VARIABLE_DRIVE: str(tmp_path)}) == tmp_path
    local = er.orden_de_entrenamiento('asistente_redaccion', datos='D:/corpus', salida='D:/sal')
    assert local == ('tools/asistente_qlora.py entrenar --dataset D:/corpus --salida D:/sal --epocas 1 --semilla 11')


def test_la_url_de_colab_fija_la_revision():
    """113:RF-2: el cuaderno se abre en el commit exacto de GitHub."""
    assert er.url_colab(REV, repositorio=REPO) == (f'https://colab.research.google.com/github/{REPO}/blob/{REV}/'
                                                   'notebooks/ConverterSmartGrid.ipynb')
    with pytest.raises(ValueError):
        er.url_colab('main', repositorio=REPO)
    with pytest.raises(ValueError):
        er.url_colab(REV, repositorio='sin barra')


@pytest.mark.parametrize('remoto', ('https://github.com/dueno/proyecto.git\n', 'https://github.com/dueno/proyecto',
                                    'git@github.com:dueno/proyecto.git', 'https://x-access-token:t@github.com/dueno/proyecto.git'))
def test_el_repositorio_sale_del_remoto_del_clon(remoto):
    """113:RF-2: el nombre del repositorio no se fija en el código: sale del remoto ``origin``."""
    assert er.repositorio_de(remoto) == REPO


def test_un_remoto_que_no_es_de_github_se_rechaza():
    """113:RF-2: sin un remoto de GitHub, Colab no podría clonar; se dice en vez de abrir otro repositorio."""
    for remoto in ('', 'D:/repos/proyecto', 'https://gitlab.com/dueno/proyecto.git'):
        with pytest.raises(ValueError, match='GitHub'):
            er.repositorio_de(remoto)


CUADERNO = Path(__file__).resolve().parents[1] / 'notebooks' / 'ConverterSmartGrid.ipynb'


def test_el_cuaderno_no_lleva_salidas_datos_ni_credenciales():
    """113:RF-1: el cuaderno del repositorio público va sin ejecutar y sin secretos."""
    nb = json.loads(CUADERNO.read_text(encoding='utf-8'))
    codigo = [c for c in nb['cells'] if c['cell_type'] == 'code']
    assert codigo and all(c['outputs'] == [] and c['execution_count'] is None for c in codigo)
    texto = CUADERNO.read_text(encoding='utf-8')
    for prohibido in ('ghp_', 'github_pat_', 'AIza', 'ya29.', 'BEGIN PRIVATE KEY', 'password', 'D:/', 'D:\\'):
        assert prohibido not in texto, prohibido


def test_el_cuaderno_clona_la_revision_del_paquete_y_usa_las_ordenes_locales():
    """113:RF-2, RF-3, RF-7, RF-14, RF-16: la revisión sale del manifiesto y se comprueba; entrena con la orden de
    tools/ que da el módulo (la misma que en el equipo) y retoma desde su punto de control."""
    fuente = '\n'.join(''.join(c['source']) for c in json.loads(CUADERNO.read_text(encoding='utf-8'))['cells'])
    assert "REVISION, FAMILIA = MANIFIESTO['revision'], MANIFIESTO['familia']" in fuente
    assert "MANIFIESTO['repositorio']" in fuente, 'el repositorio sale del paquete, no del cuaderno'
    assert "'checkout', '--quiet', '--detach', REVISION" in fuente and 'assert cabeza == REVISION' in fuente
    assert "userdata.get('GITHUB_TOKEN')" in fuente
    assert 'requirements.txt' in fuente and 'er.verificar_paquete(CARPETA)' in fuente
    assert 'er.orden_de_entrenamiento(' in fuente and "rglob('progreso_*')" in fuente
    assert 'er.manifiesto_candidato(' in fuente and 'er.perfil_colab(' in fuente


def test_la_previa_dice_que_sube_y_que_lo_impide(tmp_path):
    """113:RF-4: antes de confirmar, el operador ve cuántos ficheros, cuánto pesan y lo que no puede salir."""
    d = _dataset(tmp_path)
    p = er.previa_paquete(d, familia='asistente_redaccion')
    assert p['ficheros'] == 3 and p['bytes'] > 0 and p['prohibidos'] == []
    (d / 'base.mdb').write_bytes(b'x')
    assert er.previa_paquete(d, familia='asistente_redaccion')['prohibidos'] == ['base.mdb: dato crudo de la '
                                                                               'distribuidora (.mdb)']


def test_colab_pro_entrena_mas_que_el_equipo_segun_su_gpu():
    """113:RF-8, RF-16: A100 y L4 entrenan más épocas y semillas que el equipo; sin GPU no se entrena en Colab."""
    a100 = er.perfil_colab('NVIDIA A100-SXM4-40GB', 39.6)
    assert a100['epocas'] == 3 and a100['semillas'] == [11, 12, 13]
    assert er.perfil_colab('NVIDIA L4', 22.5)['semillas'] == [11, 12]
    t4 = er.perfil_colab('Tesla T4', 15.0)
    assert t4['epocas'] == 1 and 'A100' in t4['nota']
    with pytest.raises(er.SinGpu):
        er.perfil_colab(None, None)


def _web(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.delenv(er.VARIABLE_DRIVE, raising=False)
    monkeypatch.setattr(er, 'DRIVE_ESCRITORIO', tmp_path / 'sin_unidad' / 'ConverterSmartGrid' / 'colab')
    return TestClient(create_app(tmp_path / 'web'))


def test_la_web_sin_drive_solo_ofrece_este_equipo(tmp_path, monkeypatch):
    """113:RF-16: sin Drive, la web ofrece entrenar en este equipo y no da ningún error."""
    with _web(tmp_path, monkeypatch) as c:
        r = c.get('/api/entrenamiento/colab')
        assert r.status_code == 200, r.text
        opciones = {o['donde']: o for o in r.json()['opciones']}
        assert opciones['local']['disponible'] is True and opciones['colab']['disponible'] is False
        assert r.json()['drive'] is None


def test_la_web_prepara_solo_con_la_confirmacion_del_operador(tmp_path, monkeypatch):
    """113:RF-4, RF-6: previa con confirmación de un solo uso; un programa no saca datos; lo crudo no tiene confirmación."""
    d = _dataset(tmp_path)
    with _web(tmp_path, monkeypatch) as c:
        monkeypatch.setenv(er.VARIABLE_DRIVE, str(tmp_path / 'drive'))
        cuerpo = {'familia': 'asistente_redaccion', 'dataset': str(d)}
        programa = c.post('/api/entrenamiento/colab/preparar', json=cuerpo, headers={'Authorization': 'Bearer x'})
        assert programa.status_code == 403
        previa = c.post('/api/entrenamiento/colab/preparar', json=cuerpo).json()
        assert previa['ficheros'] == 3 and previa['confirmacion'] and len(previa['revision']) == 40
        assert not (tmp_path / 'drive' / 'paquetes').exists(), 'la previa no sube nada'
        hecho = c.post('/api/entrenamiento/colab/preparar', json={**cuerpo, 'confirmacion': previa['confirmacion']})
        assert hecho.status_code == 200, hecho.text
        assert hecho.json()['colab'].startswith('https://colab.research.google.com/github/')
        assert (tmp_path / 'drive' / 'paquetes' / hecho.json()['paquete'] / 'manifiesto.json').is_file()
        otra = c.post('/api/entrenamiento/colab/preparar', json={**cuerpo, 'confirmacion': previa['confirmacion']})
        assert otra.status_code == 409, 'la confirmación vale una sola vez'
        assert c.get('/api/entrenamiento/colab').json()['reentrenar'] == []
        with (d / 'entrenamiento.jsonl').open('a', encoding='utf-8') as f:
            f.write('{"texto": "nuevo"}\n' * 60)
        aviso, = c.get('/api/entrenamiento/colab').json()['reentrenar']
        assert aviso['familia'] == 'asistente_redaccion' and aviso['nuevos'] == 60, 'RF-13: la web lo avisa'
        (d / 'base.mdb').write_bytes(b'x')
        cruda = c.post('/api/entrenamiento/colab/preparar', json=cuerpo).json()
        assert cruda['confirmacion'] is None and cruda['prohibidos']
