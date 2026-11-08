"""076:RF-4, 076:RF-19: fuentes fijadas y vigencia actual conservan autoridades distintas."""
from pathlib import Path

import pytest

from apoyo import cargar_herramienta

PE = cargar_herramienta('preguntas_entregables.py')


def test_la_api_actual_se_lee_solo_de_su_ruta_canonica(tmp_path, monkeypatch):
    client = tmp_path / 'frontend/src/api/client.ts'
    client.parent.mkdir(parents=True)
    client.write_text('export const api = {\n  vigente: () => null,\n};\n', encoding='utf-8')
    # Una fachada vieja contradictoria no puede sustituir al cliente vigente.
    (tmp_path / 'frontend/src/api.ts').write_text('  obsoleto: () => null,\n', encoding='utf-8')
    monkeypatch.setattr(PE, 'RAIZ', tmp_path)
    assert PE._funciones_de_api() == {'vigente'}


@pytest.mark.parametrize('otra_revision', ['0' * 40, 'HEAD'])
def test_cache_no_reutiliza_un_blob_fuera_del_sha_fijado(monkeypatch, otra_revision):
    filename = 'frontend/src/components/InputsPanel.tsx'
    PE._CACHE.clear()
    assert PE._en_revision(filename)
    monkeypatch.setattr(PE, 'REVISION', otra_revision)
    assert PE._en_revision(filename) is None


def test_ancla_historica_inexistente_se_rechaza_sin_remapearla():
    fact = next(row for row in PE.leer_jsonl(PE.HECHOS)
                if row['fuentes'][0]['fichero'].endswith('/InputsPanel.tsx'))
    source = {**fact['fuentes'][0], 'ancla': 'ANCLA_INEXISTENTE_revision_076'}
    errors = PE.errores_de_fuentes([{**fact, 'fuentes': [source]}])
    assert any('no contiene' in error for error in errors)


def test_contenido_vigente_alterado_se_rechaza_aunque_el_historico_siga_valido(tmp_path, monkeypatch):
    fact = next(row for row in PE.leer_jsonl(PE.HECHOS)
                if row['fuentes'][0]['fichero'].endswith('/InputsPanel.tsx'))
    source = fact['fuentes'][0]
    root = PE.RAIZ
    run = PE.subprocess.run
    seen = []

    def real_git_fixed(*args, **kwargs):
        # Git real sobre el repo original; solo el árbol vigente es el fixture.
        seen.append(args[0])
        return run(*args, **{**kwargs, 'cwd': root})

    canonical = tmp_path / 'frontend/src/features/conversion/InputsPanel.tsx'
    canonical.parent.mkdir(parents=True)
    canonical.write_text(source['ancla'], encoding='utf-8')
    PE._CACHE.clear()
    monkeypatch.setattr(PE.subprocess, 'run', real_git_fixed)
    monkeypatch.setattr(PE, 'RAIZ', tmp_path)
    row = {**fact, 'fuentes': [{**source, 'rf': None}]}
    assert PE.errores_de_fuentes([row]) == []
    canonical.write_text('contenido modificado sin el ancla', encoding='utf-8')
    errors = PE.errores_de_fuentes([row])
    assert any('ya no está en el árbol' in error for error in errors)
    assert all(command[2].startswith(PE.REVISION + ':') for command in seen)


def test_los_hechos_reales_se_validan_con_su_revision_y_cliente_actual():
    assert PE.errores_de_hechos(PE.leer_jsonl(PE.HECHOS)) == []
