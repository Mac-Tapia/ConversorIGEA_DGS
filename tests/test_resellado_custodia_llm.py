"""047:RF-57 y 047:RF-58: volver a sellar un corpus reubicado con el prompt vigente, a través de su custodia.

El corpus del 065 se reubicó con un manifiesto de custodia (``reubicacion_fuentes``) y se selló con un prompt que ya no
es el vigente. El sellado nuevo no puede reutilizar el manifiesto tal cual ni leer las fuentes en su ruta histórica:
las resuelve por la custodia, comprobando cada sha256, y deja el rastro del sellado anterior.
"""
import json
from pathlib import Path

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.aplicacion.asistente import llm_destilacion as llm
from convertersmartgrid.aplicacion.evaluacion_modelos import huella

PROMPT_ANTERIOR = 'prompt de un protocolo anterior'


@pytest.fixture
def custodia(tmp_path, monkeypatch):
    """Un corpus sellado con un prompt anterior y reubicado después: su única vía de lectura es la custodia."""
    from convertersmartgrid.aplicacion.asistente.reubicacion_corpus import reubicar_corpus
    anterior = tmp_path / 'anterior'
    anterior.mkdir()
    fuentes = []
    for nombre, texto in (('red.txt', 'registro sintético de red'), ('cargas.txt', 'registro sintético de cargas')):
        (anterior / nombre).write_text(texto, encoding='utf-8')
        fuentes.append(llm.custodiar(anterior / nombre, localizador='archivo completo'))
    dataset = tmp_path / 'dataset'
    dataset.mkdir()
    filas, contextos = [], []
    for parte in llm.PARTICIONES:
        contextos.append({'source_fingerprint': 'origen-sintetico', 'network_id': parte, 'particion': parte,
                          'alimentador': parte, 'proyectos': [], 'sistema': None, 'seds': [],
                          'ruta': str(anterior / 'red.txt'), 'periodos': [], 'fuentes': {'red': fuentes[0]}})
        registro = {'texto': 'estado de ' + parte, 'tarea': 'estado', 'datos': [], 'particion': parte,
                    'context_id': huella(['origen-sintetico', parte]), 'group_id': parte,
                    'quality': 'silver_teacher_real_source', 'fuentes': list(fuentes)}
        registro['respuesta'] = llm.respuesta_maestro(registro)
        registro['record_id'] = huella(registro)
        filas.append(registro)
    (dataset / 'corpus.json').write_text(json.dumps(filas), encoding='utf-8')
    (dataset / 'contextos.json').write_text(json.dumps(contextos), encoding='utf-8')
    (dataset / 'humanas_reservadas.json').write_text('[{"texto":"humana reservada"}]', encoding='utf-8')
    meta = {'schema_version': 2, 'dataset_hash': huella(filas), 'por_particion': {p: 1 for p in llm.PARTICIONES},
            'fuentes_manifest': {'fuentes': {'red': fuentes[0]}, 'semilla_particion': 23}}
    (dataset / 'dataset_manifest.json').write_text(json.dumps(meta), encoding='utf-8')
    with monkeypatch.context() as m:
        m.setattr(llm, 'sistema_alumno', lambda: PROMPT_ANTERIOR)
        llm.sellar_particiones(dataset, tmp_path / 'sellado')
        nueva = tmp_path / 'nueva'
        anterior.rename(nueva)
        reubicada = tmp_path / 'reubicada'
        reubicar_corpus(tmp_path / 'sellado', reubicada, anterior, nueva, ejecutar=True)
    # Las fuentes solo quedan en la custodia: ni la raíz anterior ni la nueva existen ya.
    nueva.rename(tmp_path / 'retirada')
    return reubicada


def _manifiesto(ruta: Path) -> dict:
    return json.loads((ruta / 'dataset_manifest.json').read_text(encoding='utf-8'))


def test_resella_con_custodia_y_prompt_vigente(custodia, tmp_path):
    """047:RF-57: cada fuente se resuelve por la custodia, se recalculan record_id y dataset_hash y queda el rastro."""
    with pytest.raises(ValueError, match='prompt'):
        llm.leer_particion_real(custodia, 'entrenamiento')
    original = _manifiesto(custodia)
    filas_antes = json.loads((custodia / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    destino = tmp_path / 'v6'
    meta = llm.resellar_con_custodia(custodia / 'dataset_manifest.json', destino)
    assert meta['prompt_hash'] == huella(llm.sistema_alumno()) != original['prompt_hash']
    assert 'reubicacion_fuentes' not in meta
    filas = json.loads((destino / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    assert meta['dataset_hash'] == huella(filas) != original['dataset_hash']
    raiz = custodia.resolve()
    for antes, ahora in zip(filas_antes, filas, strict=True):
        assert {k: v for k, v in ahora.items() if k not in ('fuentes', 'record_id')} == \
               {k: v for k, v in antes.items() if k not in ('fuentes', 'record_id')}
        assert ahora['record_id'] == huella({k: v for k, v in ahora.items() if k != 'record_id'}) != antes['record_id']
        for f_antes, f_ahora in zip(antes['fuentes'], ahora['fuentes'], strict=True):
            assert Path(f_ahora['ruta']).is_relative_to(raiz)
            assert (f_ahora['sha256'], f_ahora['bytes']) == (f_antes['sha256'], f_antes['bytes'])
    rastro = meta['resellado']
    assert rastro['dataset_hash_anterior'] == original['dataset_hash']
    assert rastro['prompt_hash_anterior'] == original['prompt_hash']
    assert rastro['huella_reubicacion'] == original['reubicacion_fuentes']['huella']
    assert rastro['dataset_hash_preservado'] == original['reubicacion_fuentes']['dataset_hash_preservado']
    assert rastro['manifiesto_custodia']['sha256'] == llm.custodiar(custodia / 'dataset_manifest.json',
                                                                      localizador='x')['sha256']
    assert len(rastro['fuentes_resueltas']) == 2
    llm.verificar_fuente(rastro['record_ids'])
    pares = json.loads(Path(rastro['record_ids']['ruta']).read_text(encoding='utf-8'))
    assert pares == [[a['record_id'], b['record_id']] for a, b in zip(filas_antes, filas)]
    for parte in llm.PARTICIONES:
        assert llm.leer_particion_real(destino, parte)[0]
    assert llm.auditar_fuentes_corpus(destino)['ok']


def test_resellado_determinista(custodia, tmp_path):
    """047:RF-57: dos resellados de la misma custodia dan las mismas particiones y el mismo manifiesto."""
    a = llm.resellar_con_custodia(custodia / 'dataset_manifest.json', tmp_path / 'a')
    b = llm.resellar_con_custodia(custodia / 'dataset_manifest.json', tmp_path / 'b')
    assert a['prompt_hash'] == b['prompt_hash'] == huella(llm.sistema_alumno())
    assert a['dataset_hash'] == b['dataset_hash'] and a['huellas_particion'] == b['huellas_particion']
    for parte in llm.PARTICIONES:
        assert (tmp_path / 'a' / (parte + '.jsonl')).read_bytes() == (tmp_path / 'b' / (parte + '.jsonl')).read_bytes()


def test_copia_custodiada_con_otro_sha_se_rechaza_con_su_causa(custodia, tmp_path):
    """047:RF-58: una copia de la custodia que no casa por sha256 se rechaza nombrando la fuente y la causa."""
    resolucion = next(r for r in _manifiesto(custodia)['reubicacion_fuentes']['resoluciones']
                      if r['origen'].endswith('cargas.txt'))
    (custodia / resolucion['destino']).write_bytes(b'otros bytes')
    with pytest.raises(ValueError, match=r'cargas\.txt.*sha256'):
        llm.resellar_con_custodia(custodia / 'dataset_manifest.json', tmp_path / 'v6')
    assert not (tmp_path / 'v6').exists()


def test_fuente_sin_resolucion_en_la_custodia_se_rechaza(custodia, tmp_path):
    """047:RF-58: una fuente sin resolución en la custodia no se busca por parecido: se rechaza con su causa."""
    archivo = custodia / 'dataset_manifest.json'
    meta = _manifiesto(custodia)
    traslado = meta['reubicacion_fuentes']
    traslado['resoluciones'] = [r for r in traslado['resoluciones'] if not r['origen'].endswith('red.txt')]
    traslado['huella'] = huella({k: v for k, v in traslado.items() if k != 'huella'})
    archivo.write_text(json.dumps(meta), encoding='utf-8')
    with pytest.raises(ValueError, match=r'red\.txt.*sin resolución'):
        llm.resellar_con_custodia(archivo, tmp_path / 'v6')
    assert not (tmp_path / 'v6').exists()


def test_manifiesto_sin_custodia_o_alterado_se_rechaza(custodia, tmp_path):
    """047:RF-58: sin manifiesto de reubicación, o con su huella rota, no hay resellado."""
    meta = _manifiesto(custodia)
    sin = tmp_path / 'sin_custodia'
    sin.mkdir()
    (sin / 'dataset_manifest.json').write_text(json.dumps({k: v for k, v in meta.items()
                                                           if k != 'reubicacion_fuentes'}), encoding='utf-8')
    with pytest.raises(ValueError, match='reubicación'):
        llm.resellar_con_custodia(sin / 'dataset_manifest.json', tmp_path / 'v6')
    meta['reubicacion_fuentes']['raiz_nueva'] = 'otra'
    (custodia / 'dataset_manifest.json').write_text(json.dumps(meta), encoding='utf-8')
    with pytest.raises(ValueError, match='huella'):
        llm.resellar_con_custodia(custodia / 'dataset_manifest.json', tmp_path / 'v6')
    assert not (tmp_path / 'v6').exists()


def test_orden_sellar_con_custodia(custodia, tmp_path, capsys):
    """047:RF-57 / 047:RF-58: ``tools/llm_destilar.py sellar --custodia`` resella o dice por qué no."""
    herramienta = cargar_herramienta('llm_destilar.py')
    destino = tmp_path / 'v6'
    assert herramienta.main(['sellar', '--custodia', str(custodia / 'dataset_manifest.json'),
                             '--destino', str(destino)]) == 0
    salida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert salida['ok'] and salida['prompt_hash'] == huella(llm.sistema_alumno())
    assert salida['dataset_hash_anterior'] == _manifiesto(custodia)['dataset_hash']
    assert herramienta.main(['sellar', '--custodia', str(custodia / 'dataset_manifest.json'),
                             '--dataset', str(tmp_path), '--destino', str(tmp_path / 'otro')]) == 2
    assert 'custodia' in json.loads(capsys.readouterr().out.strip().splitlines()[-1])['error']
    assert herramienta.main(['sellar', '--destino', str(tmp_path / 'otro')]) == 2
    capsys.readouterr()
