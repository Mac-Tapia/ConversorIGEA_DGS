"""065:RF-10, 065:RF-11, 065:RF-12 — publicación real fuera del checkout."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def politica_externa(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('CSG_TEMP_HOME', str(tmp_path / 'runtime' / 'tmp'))


def _escritor(nombre, ruta, monkeypatch):
    dato = {'valor': 'Señal Ñ'}
    if nombre == 'registro':
        from convertersmartgrid.model_registry import RegistroModelo
        return lambda: RegistroModelo(ruta.parent)._reemplazar_json(ruta, dato)
    if nombre == 'binding':
        from convertersmartgrid.powerfactory_binding import _escribir_registro
        return lambda: _escribir_registro(ruta, dato)
    if nombre == 'coordinador':
        from convertersmartgrid.training_coordinator import TrainingCoordinator
        instancia = TrainingCoordinator.__new__(TrainingCoordinator)
        return lambda: instancia._escribir(ruta, dato)
    if nombre == 'trabajador':
        from convertersmartgrid.trabajadores_ml import escribir_informe
        return lambda: escribir_informe(ruta, dato)
    if nombre == 'almacen':
        from convertersmartgrid.asistente import almacen
        monkeypatch.setattr(almacen, 'raiz', lambda: ruta.parent)
        return lambda: almacen.guardar_json(ruta.stem, dato)
    if nombre == 'checkpoint':
        from convertersmartgrid.asistente.orquestador import PuntoDeControl
        instancia = PuntoDeControl.abrir(ruta)
        return lambda: instancia.marcar('fuente', 'hecha', resultado=dato)
    if nombre == 'pide_json':
        from convertersmartgrid.pide_dataset import _write_json_atomic
        return lambda: _write_json_atomic(ruta, dato)
    if nombre == 'pide_jsonl':
        from convertersmartgrid.pide_dataset import _write_jsonl_atomic
        return lambda: _write_jsonl_atomic(ruta, [dato])
    if nombre == 'custodia_json':
        from convertersmartgrid.web.source_runs import _atomic_json
        return lambda: _atomic_json(ruta, dato)
    if nombre == 'turno':
        from convertersmartgrid.pf_arnes import _escribir_turno
        return lambda: _escribir_turno(ruta, dato)
    if nombre == 'oraculo':
        from convertersmartgrid.digital_twin import oraculo
        monkeypatch.setattr(oraculo, '_raiz_modelos', lambda _b: ruta.parent)
        return lambda: oraculo.promover(None, 'v1', 'prueba')
    if nombre == 'transformer':
        from convertersmartgrid.asistente import transformer
        monkeypatch.setattr(transformer, 'raiz_modelos', lambda _n: ruta.parent)
        return lambda: transformer.promover('v1', 'prueba')
    raise AssertionError(nombre)


ESCRITORES = ('registro', 'binding', 'coordinador', 'trabajador', 'almacen',
              'checkpoint', 'pide_json', 'pide_jsonl', 'custodia_json', 'turno',
              'oraculo', 'transformer')


@pytest.mark.parametrize('nombre', ESCRITORES)
@pytest.mark.parametrize('corte', [False, True])
def test_publicacion_json_externa_conserva_anterior_y_limpia(tmp_path, monkeypatch, nombre, corte):
    """065:RF-10, 065:RF-11, 065:RF-12 — ruta privada, mismo volumen y fallo íntegro."""
    ruta = tmp_path / 'producto' / 'promovido.json'
    ruta.parent.mkdir()
    anterior = b'{"version": "anterior"}'
    ruta.write_bytes(anterior)
    publicar = _escritor(nombre, ruta, monkeypatch)
    reemplazar = os.replace
    observados = []

    def observar(origen, destino, *args, **kwargs):
        origen, destino = Path(origen), Path(destino)
        if destino == ruta:
            assert not origen.is_relative_to(ruta.parent), origen
            assert origen.anchor == destino.anchor
            assert (origen.parent / 'owner.json').is_file()
            assert ruta.read_bytes() == anterior
            observados.append(origen)
            if corte:
                raise OSError('corte antes de publicar')
        return reemplazar(origen, destino, *args, **kwargs)

    monkeypatch.setattr(os, 'replace', observar)
    if corte:
        with pytest.raises(OSError, match='corte antes'):
            publicar()
        assert ruta.read_bytes() == anterior
    else:
        publicar()
        assert json.loads(ruta.read_text(encoding='utf-8')) != json.loads(anterior)
    assert len(observados) == 1
    assert all(not p.exists() for p in observados)
    assert not list((tmp_path / 'runtime').rglob('owner.json'))
    assert not list(ruta.parent.glob('*.tmp'))


def test_custodia_copia_independiente_con_fsync_y_origen_intacto(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — una copia fallida nunca retira el original."""
    from convertersmartgrid.web.source_runs import _sha256_copy
    fuente = tmp_path / 'fuente.bin'
    contenido = b'fuente real de prueba' * 100
    fuente.write_bytes(contenido)
    destino = tmp_path / 'producto' / fuente.name
    destino.parent.mkdir()
    destino.write_bytes(b'anterior')
    sincronizar = os.fsync
    sincronizados = []

    def registrar(fd):
        sincronizados.append(fd)
        sincronizar(fd)

    monkeypatch.setattr(os, 'fsync', registrar)
    size, digest = _sha256_copy(fuente, destino)
    assert (size, digest) == (len(contenido), hashlib.sha256(contenido).hexdigest())
    assert sincronizados
    destino.write_bytes(b'cambio en copia')
    assert fuente.read_bytes() == contenido
    monkeypatch.setattr(os, 'fsync', lambda _fd: (_ for _ in ()).throw(OSError('sin disco')))
    with pytest.raises(OSError, match='sin disco'):
        _sha256_copy(fuente, destino)
    assert destino.read_bytes() == b'cambio en copia'
    assert fuente.read_bytes() == contenido
    assert not list(destino.parent.glob('*.part'))
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_escritores_concurrentes_no_comparten_temporal(tmp_path):
    """065:RF-11, 065:RF-12 — hilos del mismo PID publican sin pisar su staging."""
    from convertersmartgrid.model_registry import RegistroModelo
    registro = RegistroModelo(tmp_path / 'producto')
    ruta = registro.raiz / 'puntero.json'
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: registro._reemplazar_json(ruta, {'n': n}), range(32)))
    assert json.loads(ruta.read_text())['n'] in range(32)
    assert not list((tmp_path / 'runtime').rglob('owner.json'))
    assert sorted(p.name for p in ruta.parent.iterdir()) == ['puntero.json']


def test_candidato_canonico_publica_carpeta_externa_y_copia_pesos(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — candidato completo, hash estable y fuente independiente."""
    from convertersmartgrid.model_registry import RegistroModelo
    fuente = tmp_path / 'pesos.bin'
    fuente.write_bytes(b'pesos originales')
    registro = RegistroModelo(tmp_path / 'registro')
    reemplazar = os.replace
    carpetas = []

    def observar(origen, destino, *args, **kwargs):
        origen, destino = Path(origen), Path(destino)
        if origen.is_dir():
            assert not origen.is_relative_to(registro.raiz)
            assert (origen.parent / 'owner.json').is_file()
            carpetas.append(origen)
        return reemplazar(origen, destino, *args, **kwargs)

    monkeypatch.setattr(os, 'replace', observar)
    payload = dict(model_manifest={'cfg': 1}, dataset_manifest={'sha256': 'a' * 64},
                   metrics={'error': .1}, decision={'status': 'RECHAZADO'},
                   smoke_reload={'ok': False}, artifacts=[fuente])
    candidato = registro.registrar_candidato('pinn', **payload)
    assert registro.registrar_candidato('pinn', **payload)['candidate_id'] == candidato['candidate_id']
    copia = Path(candidato['path']) / 'artifacts' / fuente.name
    assert copia.read_bytes() == fuente.read_bytes()
    copia.write_bytes(b'otra copia')
    assert fuente.read_bytes() == b'pesos originales'
    assert len(carpetas) == 1 and not carpetas[0].exists()
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_informe_prepara_docx_y_json_antes_de_publicar(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — no publica JSON si falla guardar el Word."""
    import docx
    from convertersmartgrid.informe_docx import _guardar
    documento = docx.Document()
    documento.add_paragraph('Informe de prueba')
    destino = tmp_path / 'informes' / 'estudio.docx'
    destino.parent.mkdir()
    reemplazar = os.replace
    observados = []

    def observar(origen, target, *args, **kwargs):
        origen, target = Path(origen), Path(target)
        assert not origen.is_relative_to(destino.parent)
        assert (origen.parent / 'owner.json').is_file()
        observados.append(target)
        return reemplazar(origen, target, *args, **kwargs)

    monkeypatch.setattr(os, 'replace', observar)
    _guardar(documento, destino, {'red': 'prueba'})
    assert docx.Document(destino).paragraphs[0].text == 'Informe de prueba'
    assert observados == [destino.with_suffix('.json'), destino]
    antes = destino.read_bytes(), destino.with_suffix('.json').read_bytes()
    with pytest.raises(ValueError):
        circular = {}; circular['yo'] = circular
        _guardar(documento, destino, circular)
    assert (destino.read_bytes(), destino.with_suffix('.json').read_bytes()) == antes
    assert not list((tmp_path / 'runtime').rglob('owner.json'))
    assert sorted(p.name for p in destino.parent.iterdir()) == ['estudio.docx', 'estudio.json']


def test_extraer_paquete_no_toca_part_ajeno_y_publica_fuera(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — copia custodiada y temporales ajenos conservados."""
    import zipfile
    from vnr_etl.pipeline import safe_extract_package
    fuente = tmp_path / 'fuente.zip'
    with zipfile.ZipFile(fuente, 'w') as zip:
        zip.writestr('red/datos.csv', 'id,x\nA,1\n')
    bytes_fuente = fuente.read_bytes()
    destino = tmp_path / 'producto' / 'extraido'
    ajeno = destino.with_name(destino.name + '.part')
    ajeno.mkdir(parents=True)
    (ajeno / 'conservar.txt').write_text('otro trabajo')
    reemplazar = os.replace
    def observar(origen, target, *args, **kwargs):
        origen = Path(origen)
        assert not origen.is_relative_to(destino.parent)
        assert (origen.parent / 'owner.json').is_file()
        return reemplazar(origen, target, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', observar)
    reporte = safe_extract_package(fuente, destino)
    assert reporte.files == [destino / 'red' / 'datos.csv']
    assert reporte.total_bytes == len(b'id,x\nA,1\n')
    assert fuente.read_bytes() == bytes_fuente
    assert (ajeno / 'conservar.txt').read_text() == 'otro trabajo'
    with pytest.raises(FileExistsError):
        safe_extract_package(fuente, destino)
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_descarga_prepara_ruta_privada_y_limpia_tras_error(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — validación previa, hash y destino anterior preservado."""
    from vnr_etl.discovery.download import DownloadError, DownloadManager
    destino = tmp_path / 'producto' / 'red.bin'
    destino.parent.mkdir()
    destino.write_bytes(b'anterior')
    manager = DownloadManager(tmp_path / 'cache', retries=1)
    paths = []
    def stream(_requests, _url, temporal, *, on_progress):
        assert not temporal.is_relative_to(destino.parent)
        assert temporal.anchor == destino.anchor
        assert (temporal.parent / 'owner.json').is_file()
        paths.append(temporal)
        temporal.write_bytes(b'descarga')
        return 'application/octet-stream'
    monkeypatch.setattr(manager, '_stream', stream)
    manifest = manager.download('https://example.test/red.bin', destino, force=True)
    assert manifest.sha256 == hashlib.sha256(b'descarga').hexdigest()
    def interrumpir(_requests, _url, temporal, *, on_progress):
        paths.append(temporal)
        temporal.write_bytes(b'parcial')
        raise OSError('conexion interrumpida')
    monkeypatch.setattr(manager, '_stream', interrumpir)
    with pytest.raises(DownloadError, match='conexion interrumpida'):
        manager.download('https://example.test/red.bin', destino, force=True)
    assert destino.read_bytes() == b'descarga'
    assert all(not p.exists() for p in paths)
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


@pytest.mark.parametrize('tipo', ['valido', 'checkout', 'otro_volumen'])
def test_descarga_temp_dir_explicito_respeta_fronteras(tmp_path, monkeypatch, tipo):
    """065:RF-10, 065:RF-11 — temp_dir conserva contrato sin copiar entre volúmenes."""
    from convertersmartgrid.runtime_paths import rutas_runtime
    from vnr_etl.discovery.download import DownloadManager
    destino = tmp_path / 'producto' / 'red.bin'
    if tipo == 'checkout':
        temporal = rutas_runtime().primario / 'temporal-no-crear'
    elif tipo == 'otro_volumen':
        temporal = Path(os.environ.get('SystemDrive', 'C:') + '/temporal-no-crear')
        assert temporal.anchor.casefold() != destino.anchor.casefold(), 'el caso requiere el volumen del sistema distinto'
    else:
        temporal = tmp_path / 'temporales_explicitos'
    manager = DownloadManager(tmp_path / 'cache', temp_dir=temporal, retries=1)
    observados = []
    def stream(_requests, _url, part, *, on_progress):
        assert part.parent.parent == temporal
        assert (part.parent / 'owner.json').is_file()
        observados.append(part)
        part.write_bytes(b'descarga')
        return 'application/octet-stream'
    monkeypatch.setattr(manager, '_stream', stream)
    if tipo != 'valido':
        with pytest.raises(ValueError):
            manager.download('https://example.test/red.bin', destino)
        assert not observados and not destino.exists() and not temporal.exists()
    else:
        manifest = manager.download('https://example.test/red.bin', destino)
        assert manifest.sha256 == hashlib.sha256(b'descarga').hexdigest()
        assert not list(temporal.iterdir())


def test_exportador_dgs_publica_dgs_ultimo_sin_staging_en_salida(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — motor real, hash verificado y cleanup al fallar renombre."""
    from test_vnr_etl import _production_ready_model
    from vnr_etl.exporters.dgs import DgsExporter
    destino = tmp_path / 'producto'
    reemplazar = os.replace
    publicados = []
    def observar(origen, target, *args, **kwargs):
        origen, target = Path(origen), Path(target)
        if target.parent == destino / 'dgs':
            assert not origen.is_relative_to(destino)
            assert origen.anchor == target.anchor
            publicados.append(target)
        return reemplazar(origen, target, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', observar)
    paths = DgsExporter().export(_production_ready_model(), destino)
    dgs = next(p for p in paths if p.suffix == '.dgs')
    manifest = json.loads(next(p for p in paths if p.name.endswith('.manifest.json')).read_text())
    assert manifest['artifact_sha256'] == hashlib.sha256(dgs.read_bytes()).hexdigest()
    assert publicados[-1] == dgs
    assert not (destino / '.staging').exists()
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_subida_vnr_real_prepara_fuera_y_conserva_anteriores(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — multipart real publica completo y rechaza carga corrupta."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from vnr_etl.web.app import create_router
    app = FastAPI()
    raiz = tmp_path / 'web'
    app.include_router(create_router(raiz, jobs=None))
    reemplazar = os.replace
    observados = []
    def observar(origen, destino, *args, **kwargs):
        origen, destino = Path(origen), Path(destino)
        if destino.parent == raiz / '_vnr_uploads':
            assert not origen.is_relative_to(raiz)
            assert (origen.parent / 'owner.json').is_file()
            observados.append(destino)
        return reemplazar(origen, destino, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', observar)
    with TestClient(app) as client:
        response = client.post('/api/vnr/sources/upload', files={'file': ('red.csv', b'id,x\nA,1\n', 'text/csv')})
        assert response.status_code == 200, response.text
        guardado = raiz / '_vnr_uploads' / response.json()['stored_name']
        assert guardado.read_bytes() == b'id,x\nA,1\n'
        response = client.post('/api/vnr/sources/upload', files={'file': ('corrupto.zip', b'no zip', 'application/zip')})
        assert response.status_code == 400, response.text
    assert len(observados) == 2
    assert list((raiz / '_vnr_uploads').iterdir()) == [guardado]
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_particiones_e_indice_conservan_bytes_y_hashes(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — formatos canónicos reabiertos tras staging externo."""
    from convertersmartgrid.asistente.dataset_entrenamiento import (
        escribir_particiones, normalizar_orden, particionar_dataset, registrar_evento_conversion)
    from convertersmartgrid.asistente.embeddings import guardar_indice_versionado, reabrir_indice_versionado
    from convertersmartgrid.asistente.indice import Fragmento
    producto = tmp_path / 'producto'
    reemplazar = os.replace
    observados = []
    def observar(origen, destino, *args, **kwargs):
        origen, destino = Path(origen), Path(destino)
        if destino.is_relative_to(producto):
            assert not origen.is_relative_to(producto)
            assert (origen.parent / 'owner.json').is_file()
            observados.append(destino)
        return reemplazar(origen, destino, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', observar)
    filas = [normalizar_orden({'texto': f'ordena {i}', 'tarea': 'convertir', 'origen': 'confirmado'}) for i in range(20)]
    manifest = escribir_particiones(particionar_dataset(filas), producto / 'dataset')
    for nombre in ('train', 'validation', 'test'):
        ruta = producto / 'dataset' / f'{nombre}.jsonl'
        assert manifest['partitions'][nombre]['sha256'] == hashlib.sha256(ruta.read_bytes()).hexdigest()
    evento = registrar_evento_conversion(outbox=producto / 'outbox', source_run_id='r1',
        source_mode='txt', source_fingerprint='f' * 64, todos_alimentadores=['A'],
        manifest={'feeders': [{'network_id': 'A', 'status': 'ok'}]})
    assert evento['ok']
    fragmentos = [Fragmento(1, 'prueba', 'Flujo de la red')]
    indice = producto / 'indice'
    guardar_indice_versionado(fragmentos, [[1., 0.]], indice,
        modelo='encoder-prueba@sha256:abc', segmentacion={'max_chars': 1500})
    assert reabrir_indice_versionado(indice).buscar('flujo', 1, [1., 0.])
    assert len(observados) == 8
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


@pytest.mark.parametrize('tipo', ['catalogo', 'pide', 'transferencia'])
def test_libros_publican_fuera_y_conservan_libro_anterior(tmp_path, monkeypatch, tipo):
    """065:RF-11, 065:RF-12 — XLSX válido y anterior intacto ante fallo de publicación."""
    from openpyxl import load_workbook
    destino = tmp_path / 'producto' / 'informe.xlsx'
    destino.parent.mkdir()
    if tipo == 'catalogo':
        from test_catalogo_crece import _catalogo
        from convertersmartgrid.catalog import ampliar_catalogo
        destino = _catalogo(destino.parent)
        publicar = lambda: ampliar_catalogo(destino, ['AS05003G'])
    elif tipo == 'pide':
        from convertersmartgrid.pide import escribir_formatos
        publicar = lambda: escribir_formatos(destino, {})
    else:
        from convertersmartgrid.transferencia_pf import escribir_fichero
        publicar = lambda: escribir_fichero([], destino)
    reemplazar = os.replace
    cortes = []
    def observar(origen, target, *args, **kwargs):
        origen, target = Path(origen), Path(target)
        if target == destino:
            assert not origen.is_relative_to(destino.parent)
            assert origen.suffix == '.xlsx'
            assert (origen.parent / 'owner.json').is_file()
            cortes.append(origen)
        return reemplazar(origen, target, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', observar)
    publicar()
    libro = load_workbook(destino)
    assert libro.sheetnames
    libro.close()
    anterior = destino.read_bytes()
    def fallar(origen, target, *args, **kwargs):
        if Path(target) == destino:
            raise OSError('corte de publicación')
        return reemplazar(origen, target, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', fallar)
    if tipo == 'catalogo':
        publicar = lambda: ampliar_catalogo(destino, ['AS07003G'])
    with pytest.raises(OSError, match='corte de publicación'):
        publicar()
    assert destino.read_bytes() == anterior
    assert cortes and all(not p.exists() for p in cortes)
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_bufer_preserva_canonico_fsync_e_idempotencia(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — objeto inmutable e índice reabierto con episodio real del contrato."""
    from test_digital_twin_episode import _payload
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    from convertersmartgrid.digital_twin.episode import leer_episodio, contenido_canonico, episodio_a_dict
    bufer = BuferEpisodios(tmp_path / 'producto')
    episodio = leer_episodio(_payload())
    reemplazar = os.replace
    observados = []
    def observar(origen, target, *args, **kwargs):
        origen, target = Path(origen), Path(target)
        assert not origen.is_relative_to(bufer.raiz)
        assert (origen.parent / 'owner.json').is_file()
        observados.append(target)
        return reemplazar(origen, target, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', observar)
    ruta = bufer.guardar(episodio)
    assert ruta.read_text(encoding='utf-8') == contenido_canonico(episodio_a_dict(episodio)) + '\n'
    assert bufer.guardar(episodio) == ruta and len(observados) == 1
    assert BuferEpisodios(bufer.raiz).leer(episodio.episode_id) == episodio
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


@pytest.mark.parametrize('licencia_valida', [True, False])
def test_clon_git_real_usa_staging_externo_y_limpia_readonly(tmp_path, monkeypatch, licencia_valida):
    """065:RF-11, 065:RF-12 — Git real fija commit/licencia sin temporal hermano."""
    from test_upstream_ia import catalogo as crear_catalogo
    from convertersmartgrid import upstream_ia
    catalogo = crear_catalogo.__wrapped__(tmp_path, monkeypatch)
    if not licencia_valida:
        catalogo['repositorios'][0]['license_sha256'] = '0' * 64
    destino = tmp_path / 'producto'
    ejecutar_git = upstream_ia._git
    observados = []
    def observar(argumentos, *, cwd=None):
        if argumentos[0] == 'init':
            candidato = Path(argumentos[1])
            assert not candidato.is_relative_to(destino)
            assert (candidato.parent / 'owner.json').is_file()
            observados.append(candidato)
        return ejecutar_git(argumentos, cwd=cwd)
    monkeypatch.setattr(upstream_ia, '_git', observar)
    resultado = upstream_ia.preparar_catalogo(catalogo, destino)
    assert resultado['ok'] == licencia_valida
    assert (destino / 'ejemplo').exists() == licencia_valida
    assert len(observados) == 1 and not observados[0].exists()
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_shard_fusionado_usa_safetensors_real_y_publicacion_externa(tmp_path, monkeypatch):
    """065:RF-11, 065:RF-12 — exportación sintética FP16; no acredita modelo operativo."""
    from types import SimpleNamespace
    import torch
    from safetensors.torch import load_file
    from convertersmartgrid.asistente import llm_destilacion
    modelo = torch.nn.Sequential(torch.nn.Linear(2, 2, bias=False))
    modelo.config = SimpleNamespace(to_dict=lambda: {'arquitectura': 'prueba'})
    ficha = {'id': 'modelo-sintetico', 'revision': 'a' * 40}
    tokenizer = SimpleNamespace(save_pretrained=lambda destino: (destino / 'tokenizer.json').write_text('{}'))
    monkeypatch.setattr(llm_destilacion, 'ficha_base', lambda: ficha)
    monkeypatch.setattr(llm_destilacion, '_base_local', lambda _base: (modelo, tokenizer, ficha))
    destino = tmp_path / 'producto'
    reemplazar = os.replace
    observados = []
    def observar(origen, target, *args, **kwargs):
        origen, target = Path(origen), Path(target)
        if target.suffix == '.safetensors':
            assert not origen.is_relative_to(destino)
            assert (origen.parent / 'owner.json').is_file()
            observados.append(target)
        return reemplazar(origen, target, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', observar)
    resultado = llm_destilacion.exportar_fusionado(destino, log=lambda *args, **kwargs: None)
    assert resultado['ok'] and len(observados) == 1
    tensor = load_file(str(observados[0]))['0.weight']
    assert tensor.dtype == torch.float16
    assert torch.equal(tensor, modelo[0].weight.detach().to(dtype=torch.float16))
    assert resultado['artefactos'][0]['sha256'] == hashlib.sha256(observados[0].read_bytes()).hexdigest()
    assert not list((tmp_path / 'runtime').rglob('owner.json'))
