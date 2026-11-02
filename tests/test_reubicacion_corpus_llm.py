"""047:RF-20 y 065:RF-12: traslado de custodia sin alterar muestras selladas."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from convertersmartgrid.asistente import llm_destilacion as llm
from convertersmartgrid.evaluacion_modelos import huella


@pytest.fixture
def corpus(tmp_path):
    anterior = tmp_path / 'anterior'
    anterior.mkdir()
    fuente = anterior / 'datos.txt'
    fuente.write_text('registro original de contrato', encoding='utf-8')
    evidencia = llm.custodiar(fuente, localizador='archivo completo')
    dataset = tmp_path / 'dataset'
    dataset.mkdir()
    filas, contextos = [], []
    for parte in llm.PARTICIONES:
        contexto = {'source_fingerprint': 'origen-contrato', 'network_id': parte,
                    'particion': parte, 'alimentador': parte, 'proyectos': [],
                    'sistema': None, 'seds': [], 'ruta': str(fuente), 'periodos': [],
                    'fuentes': {'red': evidencia}}
        contextos.append(contexto)
        registro = {'texto': 'estado de ' + parte, 'tarea': 'estado', 'datos': [],
                    'particion': parte, 'context_id': huella(['origen-contrato', parte]),
                    'group_id': parte, 'quality': 'silver_teacher_real_source',
                    'fuentes': [evidencia]}
        registro['respuesta'] = llm.respuesta_maestro(registro)
        registro['record_id'] = huella(registro)
        filas.append(registro)
    (dataset / 'corpus.json').write_text(json.dumps(filas), encoding='utf-8')
    (dataset / 'contextos.json').write_text(json.dumps(contextos), encoding='utf-8')
    (dataset / 'humanas_reservadas.json').write_text('[{"texto":"humana reservada"}]', encoding='utf-8')
    meta = {'schema_version': 2, 'dataset_hash': huella(filas),
            'por_particion': {p: 1 for p in llm.PARTICIONES},
            'fuentes_manifest': {'fuentes': {'red': evidencia}, 'semilla_particion': 23}}
    (dataset / 'dataset_manifest.json').write_text(json.dumps(meta), encoding='utf-8')
    sellado = tmp_path / 'sellado'
    llm.sellar_particiones(dataset, sellado)
    nueva = tmp_path / 'nueva'
    anterior.rename(nueva)
    return sellado, anterior, nueva


def test_reubicar_preserva_bytes_y_ids_y_usa_custodia_relativa(corpus, tmp_path):
    """047:RF-12 / 047:RF-20 / 065:RF-12: mover datos no reetiqueta ni reparticiona."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    antes = {p.name: p.read_bytes() for p in origen.iterdir()}
    destino = tmp_path / 'nuevo-sellado'
    plan = reubicar_corpus(origen, destino, anterior, nueva)
    assert not destino.exists() and plan['ejecutado'] is False
    salida = reubicar_corpus(origen, destino, anterior, nueva, ejecutar=True)
    assert salida['auditoria']['ok'] and salida['ejecutado']
    for nombre in antes:
        assert (origen / nombre).read_bytes() == antes[nombre]
        if nombre != 'dataset_manifest.json':
            assert (destino / nombre).read_bytes() == antes[nombre]
    meta = json.loads((destino / 'dataset_manifest.json').read_text(encoding='utf-8'))
    assert meta['dataset_hash'] == json.loads(antes['dataset_manifest.json'])['dataset_hash']
    assert all(not Path(r['destino']).is_absolute() for r in meta['reubicacion_fuentes']['resoluciones'])
    nueva.rename(tmp_path / 'datos-ya-no-necesarios')
    origen.rename(tmp_path / 'original-solo-archivo')
    assert llm.auditar_fuentes_corpus(destino)['ok']
    for parte in llm.PARTICIONES:
        assert llm.leer_particion_real(destino, parte)[0]
    portable = tmp_path / 'otra-ubicacion'
    shutil.copytree(destino, portable)
    assert llm.auditar_fuentes_corpus(portable)['ok']
    evidencia = json.loads(antes['corpus_auditoria.json'])[0]['fuentes'][0]
    with pytest.raises(ValueError, match='ausente'):
        llm.verificar_fuente(evidencia)


@pytest.mark.parametrize('modo', ['ausente', 'alterada'])
def test_reubicacion_bloquea_fuente_faltante_o_sha_distinto(corpus, tmp_path, modo):
    """047:RF-20: no buscar por parecido ni aceptar bytes diferentes."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    if modo == 'ausente':
        (nueva / 'datos.txt').unlink()
    else:
        (nueva / 'datos.txt').write_text('otra fuente', encoding='utf-8')
    with pytest.raises(ValueError, match='fuente|huella'):
        reubicar_corpus(origen, tmp_path / 'destino', anterior, nueva, ejecutar=True)
    assert not (tmp_path / 'destino').exists()


@pytest.mark.parametrize('campo', ['record_id', 'particion', 'group_id'])
def test_reubicacion_no_resella_ids_ni_particiones_alteradas(corpus, tmp_path, campo):
    """047:RF-12 / 047:RF-20: un traslado no legitima manipulación del sellado."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    archivo = origen / 'corpus_auditoria.json'
    filas = json.loads(archivo.read_text(encoding='utf-8'))
    filas[0][campo] = 'alterado'
    archivo.write_text(json.dumps(filas), encoding='utf-8')
    with pytest.raises(ValueError, match='integridad|registro|particion'):
        reubicar_corpus(origen, tmp_path / 'destino', anterior, nueva)


def test_destino_existente_interno_y_cuota_no_se_publican(corpus, tmp_path):
    """065:RF-12 / 065:RF-19: no sobrescribir fuente, checkout ni destinos existentes."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    for destino in (origen, origen / 'dentro', nueva / 'dentro', Path(__file__).parents[1] / 'corpus-nuevo'):
        with pytest.raises(ValueError, match='destino|externo|cruce'):
            reubicar_corpus(origen, destino, anterior, nueva)
    with pytest.raises(ValueError, match='cuota'):
        reubicar_corpus(origen, tmp_path / 'destino', anterior, nueva, max_bytes=1)


def test_copia_alterada_y_escape_del_mapeo_fallan(corpus, tmp_path):
    """047:RF-20: el resolvedor local no elude SHA ni permite escapar del corpus."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    destino = tmp_path / 'destino'
    reubicar_corpus(origen, destino, anterior, nueva, ejecutar=True)
    archivo = destino / 'dataset_manifest.json'
    meta = json.loads(archivo.read_text(encoding='utf-8'))
    resolucion = next(r for r in meta['reubicacion_fuentes']['resoluciones'] if r['origen'].endswith('datos.txt'))
    copia = destino / resolucion['destino']
    original = copia.read_bytes()
    copia.write_bytes(b'alterado')
    with pytest.raises(ValueError, match='huella'):
        llm.auditar_fuentes_corpus(destino)
    copia.write_bytes(original)
    resolucion['destino'] = '../fuera.txt'
    traslado = meta['reubicacion_fuentes']
    traslado['huella'] = huella({k: v for k, v in traslado.items() if k != 'huella'})
    archivo.write_text(json.dumps(meta), encoding='utf-8')
    with pytest.raises(ValueError, match='relativa|escape'):
        llm.auditar_fuentes_corpus(destino)


def test_dos_raices_con_fuente_identica_son_ambiguas(corpus, tmp_path):
    """047:RF-20: dos candidatos no se resuelven escogiendo arbitrariamente uno."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    shutil.copytree(nueva, anterior)
    with pytest.raises(ValueError, match='ambigua'):
        reubicar_corpus(origen, tmp_path / 'destino', anterior, nueva)


def test_enlace_nativo_en_fuente_o_destino_se_rechaza(corpus, tmp_path):
    """065:RF-12: una junction o symlink no permite cruzar las raíces protegidas."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    enlace = tmp_path / 'enlace'
    if os.name == 'nt':
        creacion = subprocess.run(['cmd', '/c', 'mklink', '/J', str(enlace), str(nueva)], capture_output=True)
        assert creacion.returncode == 0, creacion.stderr.decode(errors='replace')
        assert enlace.is_junction()
    else:
        enlace.symlink_to(nueva, target_is_directory=True)
    for destino, raiz in ((enlace / 'destino', nueva), (tmp_path / 'destino', enlace)):
        with pytest.raises(ValueError, match='enlace'):
            reubicar_corpus(origen, destino, anterior, raiz)


def test_metadatos_cambiados_y_mapa_duplicado_no_validan(corpus, tmp_path):
    """047:RF-12 / 047:RF-20: conservar la semilla y una resolución inequívoca."""
    from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
    origen, anterior, nueva = corpus
    destino = tmp_path / 'destino'
    reubicar_corpus(origen, destino, anterior, nueva, ejecutar=True)
    archivo = destino / 'dataset_manifest.json'
    original = archivo.read_bytes()
    meta = json.loads(original)
    meta['fuentes_manifest']['semilla_particion'] += 1
    archivo.write_text(json.dumps(meta), encoding='utf-8')
    with pytest.raises(ValueError, match='manifiesto distinto'):
        llm.auditar_fuentes_corpus(destino)
    from convertersmartgrid.asistente.custodia_corpus import CustodiaCorpus
    with pytest.raises(ValueError, match='manifiesto distinto'):
        llm.auditar_fuentes_corpus(destino, custodia=CustodiaCorpus(destino, {}))
    meta = json.loads(original)
    traslado = meta['reubicacion_fuentes']
    traslado['resoluciones'].append(traslado['resoluciones'][0])
    traslado['huella'] = huella({k: v for k, v in traslado.items() if k != 'huella'})
    archivo.write_text(json.dumps(meta), encoding='utf-8')
    with pytest.raises(ValueError, match='ambigua'):
        llm.auditar_fuentes_corpus(destino)


def test_cli_ayuda_no_carga_pesos_y_dryrun_no_escribe(tmp_path):
    """065:RF-12 / 047:RF-20: CLI examinable sin importar Torch ni comenzar QLoRA."""
    import sys
    herramienta = Path(__file__).parents[1] / 'tools/reubicar_corpus_llm.py'
    ayuda = subprocess.run([sys.executable, '-B', str(herramienta), '--help'], capture_output=True, text=True)
    assert ayuda.returncode == 0 and '--ejecutar' in ayuda.stdout
    intento = subprocess.run([sys.executable, '-B', str(herramienta), '--origen', str(tmp_path / 'ausente'),
        '--destino', str(tmp_path / 'nuevo'), '--raiz-anterior', str(tmp_path / 'anterior'),
        '--raiz-nueva', str(tmp_path / 'nueva')], capture_output=True, text=True)
    assert intento.returncode == 2 and not (tmp_path / 'nuevo').exists()
    assert not json.loads(intento.stdout)['ejecutado']
