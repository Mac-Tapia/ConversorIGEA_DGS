"""Spec 077, RF-78 a RF-80 (T12) — el asistente lee la biblioteca normativa por su API: cada regla es un fragmento del índice
ampliado, una norma añadida cambia la huella y entra en la siguiente indexación, la cita normativa se comprueba contra la
biblioteca, `consultar_norma` es una lectura más, y las preguntas sobre la norma quedan selladas. Con el registro real."""
from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from convertersmartgrid.asistente import indice, lectura_proyecto

RAIZ = Path(__file__).resolve().parents[1]
CONJUNTO = RAIZ / 'docs' / 'CONJUNTO_NORMATIVO_SELLADO_077.json'


def _cn():
    assert importlib.util.find_spec('convertersmartgrid.asistente.corpus_normativo') is not None, \
        'falta asistente/corpus_normativo.py (077 T12)'
    return importlib.import_module('convertersmartgrid.asistente.corpus_normativo')


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Un árbol mínimo con la biblioteca de la entrega y una capa del usuario vacía, aparte de la de esta máquina."""
    for c in ('config/normativa', 'config/vad'):
        shutil.copytree(RAIZ / c, tmp_path / c)
    (tmp_path / 'README.md').write_text('# Prueba\n\nUn árbol mínimo.\n', encoding='utf-8')
    monkeypatch.setenv('CSG_NORMATIVA_USUARIO', str(tmp_path / 'capa_usuario'))
    return tmp_path


def _norma_nueva(repo: Path) -> None:
    (repo / 'config' / 'normativa' / 'zz_prueba.json').write_text(json.dumps({
        'esquema': 'registro_normativo_v1', 'normas': [{
            'acto': 'RCD 999-2099-OS/CD', 'titulo': 'Norma de prueba de la biblioteca', 'estado_juridico': 'vigente_comprobada',
            'sha256': 'b' * 64, 'vigencia_desde': '2020-01-01',
            'reglas': [{'clave': 'prueba.biblioteca.umbral', 'valor': 42, 'cita_literal': '«el umbral es 42»',
                        'pagina': '1', 'articulo_o_anexo': 'art. 7'}]}]}), encoding='utf-8')


def test_077_rf78_cada_regla_es_un_fragmento_del_indice_ampliado(repo):
    """077:RF-78 — el índice ampliado lleva una fuente normativa:<acto>#<clave> por regla, con artículo, valor, estado y
    cita; el de la 047 no la lleva."""
    cn = _cn()
    frags = indice.fragmentos(repo, indice.CORPUS_AMPLIADO)
    normativos = [f for f in frags if str(f.fuente).startswith(cn.PREFIJO)]
    assert [f.id for f in frags] == list(range(len(frags)))
    n1 = next(f for f in normativos if f.fuente == 'normativa:RCD 018-2018-OS/CD#pit.n1_demanda_min_mw')
    assert 'pit.n1_demanda_min_mw = 30 MW' in n1.texto and '12.3.1' in n1.texto and n1.vigencia == 'vigente'
    assert len(normativos) == sum(len(n.reglas) for n in cn.biblioteca(repo).normas.values())
    assert not any(str(f.fuente).startswith(cn.PREFIJO) for f in indice.fragmentos(repo, indice.CORPUS_047))


def test_077_rf78_una_norma_nueva_cambia_la_huella_y_entra_en_el_indice(repo):
    """077:RF-78 — añadida una norma a la biblioteca, la huella del corpus ampliado cambia y su regla entra en el índice,
    sin tocar ningún otro fichero."""
    cn = _cn()
    antes = indice.huella(repo, indice.CORPUS_AMPLIADO)
    _norma_nueva(repo)
    assert indice.huella(repo, indice.CORPUS_AMPLIADO) != antes
    fuentes = {f.fuente: f.texto for f in indice.fragmentos(repo, indice.CORPUS_AMPLIADO)}
    texto = fuentes['normativa:RCD 999-2099-OS/CD#prueba.biblioteca.umbral']
    assert 'prueba.biblioteca.umbral = 42' in texto and 'art. 7' in texto and '«el umbral es 42»' in texto
    assert cn.huella(repo) == cn.huella(repo)


def test_077_rf79_la_cita_normativa_se_comprueba_contra_la_biblioteca(repo):
    """077:RF-79 — una cita normativa vale si la regla sigue en la biblioteca con el mismo texto; alterada o retirada,
    no vale."""
    cn = _cn()
    _norma_nueva(repo)
    frag = next(f for f in indice.fragmentos(repo, indice.CORPUS_AMPLIADO)
                if f.fuente == 'normativa:RCD 999-2099-OS/CD#prueba.biblioteca.umbral')
    buena = {'fuente': frag.fuente, 'texto': frag.texto}
    alterada = {'fuente': frag.fuente, 'texto': frag.texto.replace('42', '43')}
    assert indice.verificables(repo, [buena, alterada], indice.CORPUS_AMPLIADO) == [buena]
    (repo / 'config' / 'normativa' / 'zz_prueba.json').unlink()
    assert indice.verificables(repo, [buena], indice.CORPUS_AMPLIADO) == []
    assert cn.es_normativa(frag.fuente) and not cn.es_normativa('docs/ARQUITECTURA.md:1')


def test_077_rf79_consultar_norma_es_una_lectura_del_catalogo(repo):
    """077:RF-79 — `consultar_norma` está en el catálogo que ven el LLM y el MCP; por clave da la regla vigente con su
    norma y artículo, en una fecha la de entonces, y por palabras las que las contienen; lo que no existe se dice."""
    _cn()
    assert 'consultar_norma' in {h['nombre'] for h in lectura_proyecto.catalogo()}
    r = lectura_proyecto.ejecutar(repo, 'consultar_norma', {'clave': 'pit.n1_demanda_min_mw'})
    assert r['existe'] and r['reglas'][0]['valor'] == 30 and r['reglas'][0]['norma'] == 'RCD 018-2018-OS/CD'
    assert r['fuente'] == 'normativa:RCD 018-2018-OS/CD#pit.n1_demanda_min_mw'
    antes = lectura_proyecto.ejecutar(repo, 'consultar_norma', {'clave': 'pit.n1_demanda_min_mw', 'fecha': '2015-01-01'})
    assert antes['existe'] is False or antes['reglas'][0]['norma'] != 'RCD 018-2018-OS/CD'
    palabras = lectura_proyecto.ejecutar(repo, 'consultar_norma', {'texto': 'factor potencia barras'})
    assert any(x['clave'] == 'pit.factor_potencia_barras_mt' for x in palabras['reglas'])
    falta = lectura_proyecto.ejecutar(repo, 'consultar_norma', {'clave': 'no.existe'})
    assert falta['existe'] is False and falta['motivo']


def test_077_rf80_preguntas_normativas_selladas_y_ancladas():
    """077:RF-80 — el conjunto de la biblioteca es sintético, sellado y está en la auditoría de fugas; cada pregunta con
    respuesta encuentra su regla en la biblioteca real y hay preguntas sin respuesta de control."""
    cn = _cn()
    from convertersmartgrid.asistente import evaluacion_rag, fuga_evaluacion, reranker
    assert reranker.CONJUNTO_NORMATIVO_077 == CONJUNTO
    assert reranker.sha256_de(CONJUNTO) == reranker.SELLO_NORMATIVO_077, 'el conjunto cambió después de sellarse'
    assert 'docs/CONJUNTO_NORMATIVO_SELLADO_077.json' in fuga_evaluacion.CONJUNTOS_RAG['077']
    assert lectura_proyecto.motivo_de_rechazo('docs/CONJUNTO_NORMATIVO_SELLADO_077.json') is not None
    conjunto = evaluacion_rag.cargar_conjunto(CONJUNTO)
    frags = [indice.Fragmento(i, f, t, v) for i, (f, t, v) in enumerate(cn.trozos(cn.biblioteca(RAIZ)))]
    pares, sin_ancla, _ = evaluacion_rag.resolver_pares(conjunto, frags)
    assert sin_ancla == [] and len(pares) == len(conjunto['preguntas'])
    assert sum(not p.answerable for p in pares) >= 6 and sum(p.answerable for p in pares) >= 30
