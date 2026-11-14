"""Spec 047, T2: recuperación híbrida, reranker contrastado y citas verificables.

Fase sintética: el reranker es una función inyectada; ninguna prueba carga un modelo ni usa la
GPU. La medición con los modelos reales es de ``tools/asistente_evaluar_rag.py``.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.asistente import evaluacion_rag, indice, reranker
from convertersmartgrid.asistente.indice import Fragmento, Indice
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app

RAIZ = Path(__file__).resolve().parents[1]
CONJUNTO = RAIZ / 'docs' / 'RAG_PREGUNTAS_SINTETICAS_047.json'
N = 12
FRAGS = [Fragmento(0, 'a.md:1', 'calibrar la barra sin medidor repartiendo la potencia instalada'),
         Fragmento(1, 'b.md:1', 'el flujo de carga del gemelo por matriz de admitancias'),
         Fragmento(2, 'c.md:1', 'documento que trata de reparto de energía entre circuitos'),
         Fragmento(3, 'd.md:1', 'la subestación SE50106 se excluye de la barra por su medición')]


class Ollama:
    """Ollama falso: un vector por texto, sin red ni GPU."""
    modelo = 'falso'

    def __init__(self, fallar_en=None):
        self.llamadas, self.fallar_en = [], fallar_en

    def modelos(self):
        return ['nomic-embed-text:latest']

    def embeddings(self, textos, modelo='nomic-embed-text'):
        self.llamadas.append(list(textos))
        if self.fallar_en is not None and len(self.llamadas) >= self.fallar_en:
            return None
        return [[float(len(t)), 1.0] for t in textos]

    def responder(self, pregunta, contexto):
        return None


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'repo'
    (repo / 'specs' / '099-prueba').mkdir(parents=True)
    (repo / 'docs').mkdir()
    (repo / 'src').mkdir()
    (repo / 'tools').mkdir()
    (repo / 'CODIGO_FUENTE.md').write_text('', encoding='utf-8')
    filas = ['- RF-1: EL SISTEMA repartirá la medida de la barra entre los alimentadores por potencia.',
             '- RF-2: EL SISTEMA excluirá la subestación SE50106 de la barra medida.',
             '- RF-3: EL SISTEMA guardará la huella del libro de clientes.',
             '- RF-4: EL SISTEMA dibujará el diagrama unifilar en una hoja a medida.']
    # El umbral de BM25 pide un corpus con más de cuatro trozos, o ninguna palabra pesa lo bastante.
    filas += [f'- RF-{n}: EL SISTEMA tratará el asunto número{n} de relleno.' for n in range(5, N + 1)]
    (repo / 'specs' / '099-prueba' / 'spec.md').write_text('\n'.join(filas) + '\n', encoding='utf-8')
    return repo


@pytest.fixture(autouse=True)
def _datos(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))


# ----------------------------------------------------------------- recuperación híbrida
def test_fusion_trae_lo_que_solo_hallan_los_vectores():
    """047:RF-21 — el fragmento sin palabras en común entra por vectores, fusionado por posición."""
    i = Indice(FRAGS, [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0]])
    hallados = i.buscar('calibrar la barra', 4, [1.0, 0.0])
    assert hallados[0]['fuente'] == 'a.md:1'                     # en las dos listas
    otra = i.buscar('reparto', 4, [0.0, 1.0])
    assert {'b.md:1', 'c.md:1'} <= {h['fuente'] for h in otra}
    assert otra[0]['fuente'] == 'c.md:1'                          # BM25 + vectores gana a solo vectores
    assert i.buscar('xyzzy', 4)[:1] == []                         # sin vectores ni palabras, nada


def test_las_puntuaciones_no_se_mezclan_por_escala():
    """047:RF-21 — un BM25 enorme no aplasta a los vectores: cuentan las posiciones."""
    i = Indice(FRAGS, [[0.0, 1.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]])
    hallados = i.buscar('calibrar barra medidor potencia instalada', 2, [1.0, 0.0])
    assert {h['fuente'] for h in hallados} == {'a.md:1', 'b.md:1'}
    assert hallados[0]['puntos'] == pytest.approx(1 / 61, rel=1e-6)


def test_vectores_parciales_no_apagan_la_recuperacion():
    """047:RF-21, RF-26 — un fragmento cambiado sin vector sigue por BM25 y los demás por vectores."""
    i = Indice(FRAGS, [[1.0, 0.0], None, [1.0, 0.0], None])
    assert i.cobertura == pytest.approx(0.5)
    r = indice.responder(i, 'flujo de carga del gemelo', SimpleNamespace(
        modelo='falso', embeddings=lambda t: [[1.0, 0.0]], responder=lambda p, c: None))
    assert 'b.md:1' in [c['fuente'] for c in r['citas']]
    assert 'vectores' in r['metodos'] and '2 de 4' in r['recuperacion']


def test_la_consulta_y_los_trozos_llevan_su_prefijo(tmp_path):
    """047:RF-21 — ``nomic-embed-text`` distingue consulta y documento por su prefijo de tarea."""
    repo, o = _repo(tmp_path), Ollama()
    indice.calcular_vectores(repo, o)
    assert all(t.startswith('search_document: ') for lote in o.llamadas for t in lote)
    o.llamadas.clear()
    indice.responder(indice.cargar_o_construir(repo), 'la barra medida', o)
    assert o.llamadas == [['search_query: la barra medida']]


def test_vectores_de_otra_dimension_se_ignoran():
    """047:RF-25 — otro modelo da otra dimensión: se responde con BM25, sin romper."""
    i = Indice(FRAGS, [[1.0, 0.0]] * 4)
    r = indice.responder(i, 'calibrar la barra sin medidor repartiendo potencia', SimpleNamespace(
        modelo='falso', embeddings=lambda t: [[1.0, 0.0, 0.0]], responder=lambda p, c: None))
    assert r['sabe'] and r['metodos'] == ['bm25']


# ------------------------------------------------------------ sin Ollama, y dice qué usó
def test_sin_ollama_responde_con_bm25_y_lo_dice(tmp_path):
    """047:RF-25, RF-26 — sin Ollama: BM25, y la respuesta dice que fue solo eso."""
    repo = _repo(tmp_path)
    r = indice.responder(indice.cargar_o_construir(repo), '¿cómo se reparte la medida de la barra?', None, repo=repo)
    assert r['sabe'] and r['metodos'] == ['bm25'] and 'BM25' in r['recuperacion']
    assert 'vectores' in r['recuperacion'].lower()                # dice por qué no los hubo
    sin_modelo = SimpleNamespace(modelo='falso', embeddings=lambda t: None, responder=lambda p, c: None)
    i = Indice(FRAGS, [[1.0, 0.0]] * 4)
    assert indice.responder(i, 'calibrar la barra sin medidor repartiendo potencia', sin_modelo)['metodos'] == ['bm25']


def test_la_web_dice_los_metodos_en_el_texto(tmp_path, monkeypatch):
    """047:RF-26 — lo que ve el operador es ``texto``: ahí van los métodos, con citas."""
    repo = _repo(tmp_path)
    monkeypatch.setattr(services, 'project_root', lambda: repo)
    monkeypatch.setattr('convertersmartgrid.asistente.ollama.cliente_configurado',
                        lambda: SimpleNamespace(modelos=lambda: None))
    # El informe del repositorio adopta un reranker: esta prueba no debe cargarlo en la GPU.
    monkeypatch.setattr(reranker, 'politica', lambda: {'hibrido': True, 'modelo': None, 'revision': None, 'motivo': ''})
    monkeypatch.setattr(reranker, 'abstencion', lambda: indice.Abstencion(calibrada=True, umbral_bm25_solo=2.0))
    r = services.asistente_pregunta('¿cómo se reparte la medida de la barra?')
    assert r['sabe'] and r['citas'] and r['metodos'] == ['bm25'] and 'BM25' in r['texto']
    r = services.asistente_pregunta('receta de la tortilla de patatas')
    assert not r['sabe'] and r['texto'].startswith('No lo sé') and not r['citas'] and 'BM25' in r['texto']


# ------------------------------------------------------------------- vectores en trabajo
def test_la_pregunta_no_calcula_los_vectores_del_corpus(tmp_path):
    """047:RF-23 — responder pide como mucho el vector de la consulta, y con índice sin vectores, ninguno."""
    repo, o = _repo(tmp_path), Ollama()
    i = indice.cargar_o_construir(repo)
    r = indice.responder(i, 'la barra medida', o)
    assert r['sabe'] and o.llamadas == [] and i.cobertura == 0
    assert indice.vectores_pendientes(repo, o) is True
    assert o.llamadas == []                                        # comprobarlo tampoco los calcula


def test_el_trabajo_calcula_y_el_indice_los_usa(tmp_path):
    """047:RF-22 — el trabajo los guarda; el índice recargado los usa y ya no hay pendientes."""
    repo, o = _repo(tmp_path), Ollama()
    r = indice.calcular_vectores(repo, o, lote=2)
    assert r['estado'] == 'completo' and r['con_vector'] == r['total'] == N
    assert indice.cargar_o_construir(repo).cobertura == 1.0
    assert indice.vectores_pendientes(repo, o) is False
    avance = []
    o.llamadas.clear()
    assert indice.calcular_vectores(repo, o, progreso=lambda *a: avance.append(a))['estado'] == 'completo'
    assert o.llamadas == []                                        # no repite lo ya calculado


def test_sin_modelo_de_embeddings_no_hay_trabajo(tmp_path):
    """047:RF-22 — solo si Ollama responde con su modelo; si no, nada que programar."""
    repo = _repo(tmp_path)
    assert indice.vectores_pendientes(repo, SimpleNamespace(modelos=lambda: None)) is False
    assert indice.vectores_pendientes(repo, SimpleNamespace(modelos=lambda: ['qwen3:8b'])) is False


def test_cancelar_guarda_lo_calculado_y_retoma(tmp_path):
    """047:RF-24 — cancelar a medias conserva lo hecho; la siguiente vez sigue donde quedó."""
    repo, o = _repo(tmp_path), Ollama()
    vueltas = []

    def cancelar():
        vueltas.append(1)
        if len(vueltas) == 2:
            raise InterruptedError

    with pytest.raises(InterruptedError):
        indice.calcular_vectores(repo, o, lote=2, cancelar=cancelar)
    assert indice.cargar_o_construir(repo).cobertura == pytest.approx(2 / N)
    o.llamadas.clear()
    assert indice.calcular_vectores(repo, o, lote=2)['estado'] == 'completo'
    assert sum(len(x) for x in o.llamadas) == N - 2


def test_cede_el_carril_y_guarda(tmp_path):
    """047:RF-24 — si otra orden espera, termina guardando lo que lleva."""
    repo, o = _repo(tmp_path), Ollama()
    r = indice.calcular_vectores(repo, o, lote=1, ceder=lambda: len(o.llamadas) >= 1)
    assert r['estado'] == 'cedido' and r['con_vector'] == 1
    assert indice.cargar_o_construir(repo).cobertura == pytest.approx(1 / N)


def test_ollama_que_falla_no_pierde_lo_hecho(tmp_path):
    """047:RF-24, RF-25 — Ollama se cae a mitad: queda lo calculado y el estado lo dice."""
    repo, o = _repo(tmp_path), Ollama(fallar_en=2)
    r = indice.calcular_vectores(repo, o, lote=2)
    assert r['estado'] == 'fallo' and r['con_vector'] == 2


def test_vectores_rotos_no_tumban_el_indice(tmp_path):
    """047:RF-25 — un fichero de vectores truncado equivale a no tenerlos."""
    repo = _repo(tmp_path)
    indice.calcular_vectores(repo, Ollama())
    (tmp_path / 'datos' / 'indice' / 'vectores.npy').write_bytes(b'roto')
    i = indice.cargar_o_construir(repo)
    assert i.cobertura == 0 and indice.responder(i, 'la barra medida')['sabe']


def _cliente_con_orden(tmp_path, monkeypatch, repo):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'twin'))
    monkeypatch.setenv('CSG_ASISTENTE_VECTORES', '1')
    monkeypatch.setattr(services, 'project_root', lambda: repo)
    monkeypatch.setattr(services, 'asistente_orden', lambda ws, texto, trabajos: {'plan': {
        'id': 'p', 'tarea': 'pregunta', 'listo': True, 'modo': 'consulta', 'escribe': False}})
    return create_app(tmp_path / 'web')


def _esperar(client, job_id):
    fin = time.monotonic() + 30
    while time.monotonic() < fin:
        j = client.get(f'/api/jobs/{job_id}').json()
        if j['status'] in ('done', 'failed', 'cancelled'):
            return j
        time.sleep(0.05)
    raise AssertionError('el trabajo no terminó')


def _trabajos(client, wid):
    return client.get(f'/api/workspaces/{wid}').json()['jobs']


def test_la_web_programa_los_vectores_sola(tmp_path, monkeypatch):
    """047:RF-22 — tras una pregunta y sin paso manual, un trabajo del carril del asistente los calcula."""
    repo, o = _repo(tmp_path), Ollama()
    monkeypatch.setattr('convertersmartgrid.asistente.ollama.cliente_configurado', lambda: o)
    with TestClient(_cliente_con_orden(tmp_path, monkeypatch, repo)) as c:
        wid = c.post('/api/workspaces', json={'name': 'rag'}).json()['id']
        orden = c.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': '¿cómo se reparte?'}).json()
        assert _esperar(c, orden['id'])['status'] == 'done'
        trabajo = next(j for j in _trabajos(c, wid) if j['kind'] == 'asistente_indice')
        assert trabajo['lane'] == 'asistente'
        assert _esperar(c, trabajo['id'])['status'] == 'done'
    assert indice.cargar_o_construir(repo).cobertura == 1.0


def test_en_producto_tambien_programa_los_vectores(tmp_path, monkeypatch):
    """047:RF-22; 086:RF-15 — las preguntas sobre el código, con sus vectores, también en el programa instalado.
    Hasta el 2026-11-13 la edición de producto no los calculaba ni dejaba al lanzador pedirlos."""
    repo, o = _repo(tmp_path), Ollama()
    monkeypatch.setenv('CSG_EDICION', 'producto')
    monkeypatch.setattr('convertersmartgrid.asistente.ollama.cliente_configurado', lambda: o)
    with TestClient(_cliente_con_orden(tmp_path, monkeypatch, repo)) as c:
        wid = c.post('/api/workspaces', json={'name': 'rag'}).json()['id']
        orden = c.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': '¿cómo se reparte?'}).json()
        assert _esperar(c, orden['id'])['status'] == 'done'
        trabajo = next((j for j in _trabajos(c, wid) if j['kind'] == 'asistente_indice'), None)
        assert trabajo is not None, 'en producto no se programaron los vectores'
        assert _esperar(c, trabajo['id'])['status'] == 'done'


def test_pruebas_y_app_sin_variable_no_programan(tmp_path, monkeypatch):
    """047:RF-22 — fuera del servidor real no hay trabajo que use Ollama por su cuenta."""
    repo, o = _repo(tmp_path), Ollama()
    monkeypatch.setattr('convertersmartgrid.asistente.ollama.cliente_configurado', lambda: o)
    app = _cliente_con_orden(tmp_path, monkeypatch, repo)
    monkeypatch.delenv('CSG_ASISTENTE_VECTORES')
    with TestClient(app) as c:
        wid = c.post('/api/workspaces', json={'name': 'rag'}).json()['id']
        orden = c.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': '¿cómo se reparte?'}).json()
        _esperar(c, orden['id'])
        assert not [j for j in _trabajos(c, wid) if j['kind'] == 'asistente_indice']


def test_una_orden_no_recibe_409_por_los_vectores_y_estos_ceden(tmp_path, monkeypatch):
    """047:RF-24 — con los vectores en curso la orden entra; el trabajo de vectores le deja el carril."""
    repo = _repo(tmp_path)
    empezo, cedio = threading.Event(), threading.Event()

    def calcular(ctx, ceder):
        if cedio.is_set():
            return {'estado': 'completo'}
        empezo.set()
        fin = time.monotonic() + 20
        while time.monotonic() < fin:
            if ceder():
                cedio.set()
                return {'estado': 'cedido'}
            time.sleep(0.02)
        return {'estado': 'completo'}

    monkeypatch.setattr(services, 'asistente_vectores_pendientes', lambda: True)
    monkeypatch.setattr(services, 'asistente_calcular_vectores', calcular)
    with TestClient(_cliente_con_orden(tmp_path, monkeypatch, repo)) as c:
        wid = c.post('/api/workspaces', json={'name': 'rag'}).json()['id']
        primera = c.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': 'una'}).json()
        _esperar(c, primera['id'])
        assert empezo.wait(10)
        segunda = c.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': 'dos'})
        assert segunda.status_code == 202, segunda.text
        assert cedio.wait(10)
        assert _esperar(c, segunda.json()['id'])['status'] == 'done'


def test_cancelar_el_trabajo_de_vectores_desde_la_web(tmp_path, monkeypatch):
    """047:RF-22, RF-24 — es un trabajo como los demás: se cancela con su ruta y conserva lo hecho."""
    repo, o = _repo(tmp_path), Ollama()
    entro, seguir = threading.Event(), threading.Event()
    original = o.embeddings

    def lento(textos, modelo='nomic-embed-text'):
        entro.set()
        seguir.wait(10)
        return original(textos, modelo)

    o.embeddings = lento
    monkeypatch.setattr('convertersmartgrid.asistente.ollama.cliente_configurado', lambda: o)
    with TestClient(_cliente_con_orden(tmp_path, monkeypatch, repo)) as c:
        wid = c.post('/api/workspaces', json={'name': 'rag'}).json()['id']
        orden = c.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': 'una'}).json()
        _esperar(c, orden['id'])
        assert entro.wait(10)
        trabajo = next(j for j in _trabajos(c, wid) if j['kind'] == 'asistente_indice')
        c.post(f"/api/jobs/{trabajo['id']}/cancel")
        seguir.set()
        assert _esperar(c, trabajo['id'])['status'] == 'cancelled'
    assert indice.cargar_o_construir(repo).cobertura > 0


# -------------------------------------------------------------------- citas verificables
def test_cita_apunta_fragmento_real(tmp_path):
    """047:RF-3 — cada cita lleva fichero:línea y su texto sale de ese fichero."""
    repo = _repo(tmp_path)
    r = indice.responder(indice.cargar_o_construir(repo), '¿qué se excluye de la barra medida?', None, repo=repo)
    assert r['citas']
    for c in r['citas']:
        fichero, linea = c['fuente'].rsplit(':', 1)
        renglon = (repo / fichero).read_text(encoding='utf-8').splitlines()[int(linea) - 1]
        assert c['verificada'] is True and renglon.split(': ', 1)[1] in c['texto']
        assert len(c['sha256']) == 64


def test_cita_que_ya_no_esta_en_el_fichero_se_quita(tmp_path):
    """047:RF-29 — si el fichero cambió bajo el índice, esa cita no se presenta; sin citas, «No lo sé»."""
    repo = _repo(tmp_path)
    i = indice.cargar_o_construir(repo)
    ruta = repo / 'specs' / '099-prueba' / 'spec.md'
    ruta.write_text(ruta.read_text(encoding='utf-8').replace('huella del libro', 'marca del cuaderno'), encoding='utf-8')
    r = indice.responder(i, 'huella del libro de clientes', None, repo=repo)
    assert all('huella del libro' not in c['texto'] for c in r['citas'])
    ruta.unlink()
    r = indice.responder(i, 'huella del libro de clientes', None, repo=repo)
    assert not r['sabe'] and not r['citas'] and r['respuesta'].startswith('No lo sé')


def test_sin_evidencia_abstiene(tmp_path):
    """047:RF-3 — sin fragmentos que respondan no se fabrica una cita."""
    repo = _repo(tmp_path)
    r = indice.responder(indice.cargar_o_construir(repo), 'receta de la tortilla de patatas', None, repo=repo)
    assert not r['sabe'] and r['citas'] == [] and r['respuesta'].startswith('No lo sé')


def test_citas_que_no_apoyan_sigue_en_pie(tmp_path):
    """047:RF-3 — lo ya operativo se conserva con el reranker: 027:RF-41 sigue revisando la redacción."""
    repo = _repo(tmp_path)
    falsa = SimpleNamespace(modelo='falso', embeddings=lambda t: None,
                            responder=lambda p, c: 'Las tortillas llevan huevo y patatas fritas en aceite [1].')
    r = indice.responder(indice.cargar_o_construir(repo), 'la barra medida', falsa, repo=repo)
    assert r['redactada_por'] is None and r['citas_sin_apoyo']


# ------------------------------------------------------------------------------ reranker
def _hostil(_consulta, textos):
    """Prefiere lo contrario de lo que importa: el último candidato es el mejor."""
    return [float(n) for n in range(len(textos))]


def _reordenar_con(puntuar):
    return lambda consulta, candidatos: reranker.reordenar(
        consulta, candidatos, modelo='falso', revision='0', puntuar=puntuar)


def test_reordenar_preserva_fuente_y_fragmento():
    """047:RF-3, RF-4 — reordena sin cambiar identidad, fuente ni texto."""
    candidatos = [{'id': i, 'fuente': f'f{i}', 'texto': f't{i}', 'bm25': 1.0} for i in range(3)]
    salida = reranker.reordenar('q', candidatos, modelo='falso', revision='0', puntuar=_hostil)
    assert [c['id'] for c in salida] == [2, 1, 0]
    assert all(c['fuente'] == f"f{c['id']}" and c['texto'] == f"t{c['id']}" and 'reranker' in c for c in salida)
    assert candidatos[0].keys() == {'id', 'fuente', 'texto', 'bm25'}


def test_reordenar_rechaza_un_puntuador_que_no_cuadra():
    """047:RF-30 — menos puntuaciones que candidatos no es un orden: se aparta el reranker."""
    with pytest.raises(indice.RerankerNoDisponible):
        reranker.reordenar('q', [{'id': 0, 'fuente': 'f', 'texto': 't'}], modelo='m', revision='0',
                           puntuar=lambda c, t: [])


def test_codigo_exacto_se_conserva(tmp_path):
    """047:RF-28 — ni el reranker ni la fusión apartan el fragmento con el código pedido."""
    repo = _repo(tmp_path)
    i = indice.cargar_o_construir(repo)
    r = indice.responder(i, 'barra medida SE50106', None, repo=repo, reordenador=_reordenar_con(_hostil))
    assert 'SE50106' in r['citas'][0]['texto'] and any(m.startswith('reranker') for m in r['metodos'])
    i = Indice(FRAGS, [[0.0, 1.0], [1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    assert i.buscar('SE50106', 4, [1.0, 0.0])[0]['fuente'] == 'd.md:1'
    assert i.buscar('se50106 barra', 4)[0]['fuente'] == 'd.md:1'


def test_sin_cuda_queda_el_orden_hibrido_y_lo_dice(monkeypatch):
    """047:RF-30 — sin CUDA, sin memoria o con la GPU ocupada: error claro, sin CPU, y queda el orden."""
    monkeypatch.setattr('convertersmartgrid.training_coordinator.exigir_memoria_ml', lambda *a, **k: {})
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    monkeypatch.setenv('HF_HUB_OFFLINE', '0')
    with pytest.raises(indice.RerankerNoDisponible, match='CUDA'):
        reranker.cargar_puntuador(reranker.MODELOS[0], reranker.ficha_modelo(reranker.MODELOS[0])['revision'])
    assert os.environ['HF_HUB_OFFLINE'] == '1'                    # sin red: lee solo la caché

    def no_hay_cuda(_consulta, _candidatos):
        raise indice.RerankerNoDisponible('CUDA no disponible')

    i = Indice(FRAGS)
    sin = indice.responder(i, 'calibrar la barra sin medidor repartiendo potencia', None)
    con = indice.responder(i, 'calibrar la barra sin medidor repartiendo potencia', None, reordenador=no_hay_cuda)
    assert [c['fuente'] for c in con['citas']] == [c['fuente'] for c in sin['citas']]
    assert con['metodos'] == ['bm25'] and 'CUDA' in con['recuperacion']


def test_sin_memoria_no_llega_a_cargar(monkeypatch):
    """047:RF-30 — memoria insuficiente es un motivo dicho, no una caída."""
    from convertersmartgrid.training_coordinator import MemoriaMLInsuficiente

    def falta(*_a, **_k):
        raise MemoriaMLInsuficiente('Memoria insuficiente')

    monkeypatch.setattr('convertersmartgrid.training_coordinator.exigir_memoria_ml', falta)
    with pytest.raises(indice.RerankerNoDisponible, match='Memoria'):
        reranker.cargar_puntuador(reranker.MODELOS[0], reranker.ficha_modelo(reranker.MODELOS[0])['revision'])


def test_los_candidatos_estan_fijados_por_revision():
    """047:RF-27 — cada reranker candidato, en el catálogo con revisión y huella de sus pesos."""
    assert len(reranker.MODELOS) == 2
    for modelo in reranker.MODELOS:
        ficha = reranker.ficha_modelo(modelo)
        assert len(ficha['revision']) == 40 and ficha['licencia']
        assert any(f['path'] == 'model.safetensors' and f['sha256'] for f in ficha['files'])
    with pytest.raises(ValueError):
        reranker.ficha_modelo('otro/modelo')
    with pytest.raises(indice.RerankerNoDisponible):
        reranker.cargar_puntuador(reranker.MODELOS[0], '0' * 40)


# ----------------------------------------------------------- evaluación sellada y decisión
def _corpus(n=24):
    frags = [Fragmento(i, f'doc{i}.md:1', f'tema{i} ruido comun documento numero {i} texto compartido')
             for i in range(n)]
    preguntas = [{'pregunta': f'ruido comun tema{i}', 'fichero': f'doc{i}.md', 'ancla': f'tema{i} ', 'tipo': 'spec'}
                 for i in range(n)]
    preguntas.append({'pregunta': 'xyzzy plugh', 'sin_respuesta': True, 'tipo': 'sin_respuesta'})
    return frags, {'procedencia': 'sintetico_maestro_de_sesion', 'preguntas': preguntas, 'sha256': 'sello'}


def _vectores_que_no_ayudan(frags):
    return Indice(frags, [[1.0, 0.0]] * len(frags))


def _hibrido(_pregunta):
    return [1.0, 0.0]


def test_mide_los_tres_metodos_con_el_mismo_conjunto():
    """047:RF-4 — BM25, híbrido y reranker, mismas preguntas, mismo sello, sin datos de texto."""
    frags, conjunto = _corpus()
    informe = evaluacion_rag.evaluar(_vectores_que_no_ayudan(frags), conjunto, _hibrido, {'m': _hostil})
    assert set(informe['metodos']) == {'bm25', 'hibrido', 'reranker:m'}
    assert informe['conjunto_sha256'] == 'sello' and informe['procedencia'] == 'sintetico_maestro_de_sesion'
    assert {m['queries'] for m in informe['metodos'].values()} == {len(conjunto['preguntas'])}
    assert all('latencia_p95_ms' in m for m in informe['metodos'].values())
    assert 'ruido comun' not in json.dumps(informe['metodos'], ensure_ascii=False)


def test_reranker_que_empeora_queda_desactivado():
    """047:RF-4, RF-27 — no mejora: se dice y no entra. Es un resultado válido."""
    frags, conjunto = _corpus()
    informe = evaluacion_rag.evaluar(_vectores_que_no_ayudan(frags), conjunto, _hibrido, {'m': _hostil})
    assert informe['decision']['reranker']['adoptado'] is False
    assert informe['decision']['reranker']['por_modelo']['m']['motivos']


def _corpus_dificil():
    """BM25 no distingue los temas: el fragmento bueno queda abajo y solo el reranker lo sube."""
    n = 24
    frags = [Fragmento(i, f'doc{i}.md:1', f'clave{i} ruido comun ' + 'ruido comun ' * (i % 3 + 4)) for i in range(n)]
    preguntas = [{'pregunta': f'ruido comun clave{i}x', 'fichero': f'doc{i}.md', 'ancla': f'clave{i} ', 'tipo': 'spec'}
                 for i in range(n)]
    return frags, {'procedencia': 'sintetico_maestro_de_sesion', 'preguntas': preguntas, 'sha256': 'sello'}


def _sabio_dificil(consulta, textos):
    return [1.0 if consulta.split()[-1][:-1] + ' ' in t else 0.0 for t in textos]


def test_reranker_que_mejora_a_los_dos_se_adopta():
    """047:RF-4, RF-27 — mejora a BM25 y a híbrido con IC95 % sobre cero: se adopta ese modelo."""
    frags, conjunto = _corpus_dificil()
    informe = evaluacion_rag.evaluar(_vectores_que_no_ayudan(frags), conjunto, _hibrido, {'m': _sabio_dificil})
    mrr = {k: v['mrr@10'] for k, v in informe['metodos'].items()}
    assert mrr['reranker:m'] > mrr['bm25'] and mrr['reranker:m'] > mrr['hibrido'], mrr
    d = informe['decision']['reranker']
    assert d['adoptado'] is True and d['modelo'] == 'm', d
    assert d['por_modelo']['m']['frente_a']['bm25']['ci95_bootstrap'][0] > 0


def test_un_modelo_que_falla_se_anota_y_no_se_adopta():
    """047:RF-4 — el que no cabe en memoria consta con su error; se mide el resto."""
    frags, conjunto = _corpus_dificil()

    def no_cabe(_c, _t):
        raise indice.RerankerNoDisponible('Memoria insuficiente')

    informe = evaluacion_rag.evaluar(_vectores_que_no_ayudan(frags), conjunto, _hibrido,
                                     {'grande': no_cabe, 'm': _sabio_dificil})
    assert 'Memoria' in informe['metodos']['reranker:grande']['error']
    assert informe['decision']['reranker']['modelo'] == 'm'
    assert 'error' in str(informe['decision']['reranker']['por_modelo']['grande']['motivos'])


def test_hibrido_sin_mejora_no_se_promueve_por_empate():
    """047:RF-4 — empate con BM25 no adopta el híbrido."""
    metodos = {'bm25': {'mrr@10': .5, 'recall@10': .5, 'per_query': []},
               'hibrido': {'mrr@10': .5, 'recall@10': .5, 'per_query': []}}
    assert evaluacion_rag.decidir(metodos, set())['hibrido']['adoptado'] is False


def test_una_pregunta_de_codigo_que_pierde_el_primer_lugar_veta():
    """047:RF-28 — mejorar la media no compensa perder un código."""
    def fila(g, x):
        return {'group_id': g, 'answerable': True, 'reciprocal_rank@10': x, 'exact_citation@1': float(x == 1.0)}

    base = [fila(f'g{i}', .5) for i in range(30)] + [fila('cod', 1.0)]
    mejor = [fila(f'g{i}', 1.0) for i in range(30)] + [fila('cod', .5)]
    metodos = {'bm25': {'mrr@10': .5, 'recall@10': 1., 'per_query': base},
               'hibrido': {'mrr@10': .5, 'recall@10': 1., 'per_query': base},
               'reranker:m': {'mrr@10': .9, 'recall@10': 1., 'latencia_p95_ms': 10., 'per_query': mejor}}
    d = evaluacion_rag.decidir(metodos, {'cod'})['reranker']
    assert d['adoptado'] is False and 'código' in str(d['por_modelo']['m']['motivos'])


def test_lento_no_se_adopta():
    """047:RF-27 — el percentil 95 de latencia entra en la política declarada."""
    def fila(g, x):
        return {'group_id': g, 'answerable': True, 'reciprocal_rank@10': x, 'exact_citation@1': float(x == 1.0)}

    base, mejor = [fila(f'g{i}', .5) for i in range(30)], [fila(f'g{i}', 1.0) for i in range(30)]
    metodos = {'bm25': {'mrr@10': .5, 'recall@10': 1., 'per_query': base},
               'hibrido': {'mrr@10': .5, 'recall@10': 1., 'per_query': base},
               'reranker:m': {'mrr@10': 1., 'recall@10': 1., 'latencia_p95_ms': 6000., 'per_query': mejor}}
    assert evaluacion_rag.decidir(metodos, set())['reranker']['adoptado'] is False


def _politica(tmp_path, decision, sello=None):
    conjunto = tmp_path / 'conjunto.json'
    conjunto.write_text('{"preguntas": []}', encoding='utf-8')
    informe = tmp_path / 'informe.json'
    informe.write_text(json.dumps({'conjunto_sha256': sello or evaluacion_rag.sha256_de(conjunto),
                                   'decision': decision}), encoding='utf-8')
    return reranker.politica(informe, conjunto), informe, conjunto


def test_produccion_solo_con_decision_del_conjunto_sellado(tmp_path):
    """047:RF-27 — sin informe, con el conjunto cambiado o sin adoptar: reranker apagado."""
    modelo = reranker.MODELOS[1]
    revision = reranker.ficha_modelo(modelo)['revision']
    sin = reranker.politica(tmp_path / 'no.json', tmp_path / 'no2.json')
    assert sin['modelo'] is None and sin['hibrido'] is True and sin['motivo']
    adoptado = {'hibrido': {'adoptado': True}, 'reranker': {'adoptado': True, 'modelo': modelo, 'revision': revision}}
    p, _, conjunto = _politica(tmp_path, adoptado)
    assert p['modelo'] == modelo and p['revision'] == revision
    assert reranker.reordenador_de(p) is not None
    conjunto.write_text('{"preguntas": [1]}', encoding='utf-8')
    otra = reranker.politica(tmp_path / 'informe.json', conjunto)
    assert otra['modelo'] is None and 'cambió' in otra['motivo']
    p, *_ = _politica(tmp_path, {'hibrido': {'adoptado': False}, 'reranker': {'adoptado': False}})
    assert p['modelo'] is None and p['hibrido'] is False and reranker.reordenador_de(p) is None
    p, *_ = _politica(tmp_path, {'hibrido': {'adoptado': True},
                                 'reranker': {'adoptado': True, 'modelo': 'otro/modelo', 'revision': '0' * 40}})
    assert p['modelo'] is None                                    # no fijado en el catálogo


def test_el_informe_real_del_repositorio_esta_sellado():
    """047:RF-4, RF-27 — el informe guardado, si lo hay, corresponde al conjunto sellado de hoy."""
    informe = RAIZ / 'docs' / 'EVALUACION_RAG_047.json'
    if informe.is_file():
        assert json.loads(informe.read_text(encoding='utf-8'))['conjunto_sha256'] == evaluacion_rag.sha256_de(CONJUNTO)
    assert reranker.politica()['hibrido'] in (True, False)


def test_el_conjunto_es_sintetico_y_ancla_en_el_indice_real():
    """047:RF-4 — declara su procedencia y sus respuestas son fragmentos reales del índice."""
    conjunto = evaluacion_rag.cargar_conjunto(CONJUNTO)
    assert conjunto['procedencia'] == 'sintetico_maestro_de_sesion'
    assert conjunto['sha256'] == evaluacion_rag.sha256_de(CONJUNTO)
    frags = indice.fragmentos(RAIZ)
    pares, sin_ancla, _ = evaluacion_rag.resolver_pares(conjunto, frags)
    con_respuesta = [p for p in pares if p.answerable]
    assert len(con_respuesta) >= 50 and len(pares) - len(con_respuesta) >= 10
    # Un documento puede cambiar sin relación con esto; medir exige el 100 %, esta prueba vigila la deriva.
    assert len(sin_ancla) <= len(pares) // 10, sin_ancla


def test_un_conjunto_de_operadores_fingido_se_rechaza(tmp_path):
    """047:RF-4 — el evaluador no acepta un conjunto sin su procedencia declarada."""
    ruta = tmp_path / 'c.json'
    ruta.write_text(json.dumps({'procedencia': 'operadores', 'preguntas': []}), encoding='utf-8')
    with pytest.raises(ValueError):
        evaluacion_rag.cargar_conjunto(ruta)


def test_medir_exige_que_todo_el_conjunto_ancle():
    """047:RF-4 — medir con anclas perdidas falsearía la comparación: se rechaza."""
    frags, conjunto = _corpus()
    conjunto['preguntas'].append({'pregunta': 'otra', 'fichero': 'no.md', 'ancla': 'nada', 'tipo': 'spec'})
    with pytest.raises(ValueError, match='ancla'):
        evaluacion_rag.evaluar(Indice(frags), conjunto, _hibrido, {})


def test_liberar_recolecta_antes_de_vaciar_la_cache(monkeypatch):
    """047:RF-30 — descargar el modelo devuelve la GPU: primero se recolectan sus ciclos."""
    orden = []
    monkeypatch.setattr(reranker.gc, 'collect', lambda: orden.append('recolectar'))
    torch = SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: orden.append('vaciar')))
    reranker.Puntuador(object(), torch).liberar()
    assert orden == ['recolectar', 'vaciar']


def test_gpu_ocupada_aparta_el_reranker_sin_esperar():
    """047:RF-30 — otro entrenamiento tiene la GPU: no se espera ni se cae a CPU; queda el orden."""
    def ocupada():
        raise RuntimeError('GPU ocupada: otro proceso conserva la guardia')

    modelo = reranker.MODELOS[1]
    pol = {'modelo': modelo, 'revision': reranker.ficha_modelo(modelo)['revision']}
    r = indice.responder(Indice(FRAGS), 'calibrar la barra sin medidor repartiendo potencia', None,
                         reordenador=reranker.reordenador_de(pol, ocupada))
    assert r['sabe'] and r['metodos'] == ['bm25'] and 'GPU' in r['recuperacion']


def test_hibrido_no_adoptado_no_pide_vectores():
    """047:RF-27 — si la evaluación apartó el híbrido, ni se pide el vector y la respuesta lo dice."""
    llamadas = []
    o = SimpleNamespace(modelo='falso', embeddings=lambda t: llamadas.append(t) or [[1.0, 0.0]],
                        responder=lambda p, c: None)
    r = indice.responder(Indice(FRAGS, [[1.0, 0.0]] * 4), 'calibrar la barra sin medidor repartiendo potencia', o,
                         usar_vectores=False)
    assert llamadas == [] and r['metodos'] == ['bm25'] and 'no los adoptó' in r['recuperacion']


def test_el_sello_no_depende_del_final_de_linea(tmp_path):
    """047:RF-4 — Git en Windows saca el conjunto con CRLF: sigue siendo el mismo conjunto sellado."""
    lf, crlf = tmp_path / 'lf.json', tmp_path / 'crlf.json'
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert evaluacion_rag.sha256_de(lf) == evaluacion_rag.sha256_de(crlf)
    crlf.write_bytes(b'{"a": 9}\r\n{"b": 2}\r\n')
    assert evaluacion_rag.sha256_de(lf) != evaluacion_rag.sha256_de(crlf)


# ------------------------------------------------------------------- abstención calibrada
Q_FRAGS = 'calibrar la barra sin medidor repartiendo potencia'
CALIBRADA = indice.Abstencion(calibrada=True, modelo_reranker='m', umbral_reranker=5.0, umbral_coseno=0.9,
                              umbral_bm25=50.0, umbral_bm25_solo=2.0)


def _con_etiqueta(puntos):
    def reordenador(consulta, candidatos):
        return reranker.reordenar(consulta, candidatos, modelo='m', revision='', puntuar=lambda c, t: [puntos] * len(t))
    reordenador.etiqueta = 'reranker:m'
    return reordenador


def test_decide_la_puntuacion_del_reranker_calibrado():
    """047:RF-31 — con el reranker calibrado manda su umbral, aunque BM25 o el coseno digan otra cosa."""
    i = Indice(FRAGS)
    assert indice.responder(i, Q_FRAGS, None, reordenador=_con_etiqueta(9.0), abstencion=CALIBRADA)['sabe'] is True
    r = indice.responder(i, Q_FRAGS, None, reordenador=_con_etiqueta(1.0), abstencion=CALIBRADA)
    assert r['sabe'] is False and r['citas'] == [] and r['respuesta'].startswith('No lo sé')


def test_otro_reranker_no_usa_el_umbral_calibrado():
    """047:RF-31, RF-32 — el umbral es de ese modelo; otro no lo hereda y decide BM25."""
    def otro(consulta, candidatos):
        return reranker.reordenar(consulta, candidatos, modelo='x', revision='', puntuar=lambda c, t: [0.0] * len(t))
    otro.etiqueta = 'reranker:otro'
    assert indice.responder(Indice(FRAGS), Q_FRAGS, None, reordenador=otro, abstencion=CALIBRADA)['sabe'] is True


def test_sin_reranker_deciden_coseno_y_bm25_calibrados():
    """047:RF-32 — con vectores, cualquiera de sus dos umbrales; sin vectores, el de BM25 solo."""
    i = Indice(FRAGS, [[1.0, 0.0]] * 4)
    def cerca(t):
        return SimpleNamespace(modelo='f', embeddings=lambda x: [[1.0, 0.0]], responder=lambda p, c: None)
    def lejos(t):
        return SimpleNamespace(modelo='f', embeddings=lambda x: [[0.0, 1.0]], responder=lambda p, c: None)
    assert indice.responder(i, Q_FRAGS, cerca(0), abstencion=CALIBRADA)['sabe'] is True
    assert indice.responder(i, Q_FRAGS, lejos(0), abstencion=CALIBRADA)['sabe'] is False       # BM25 bajo 50
    assert indice.responder(Indice(FRAGS), Q_FRAGS, None, abstencion=CALIBRADA)['sabe'] is True
    assert indice.responder(Indice(FRAGS), 'barra', None, abstencion=CALIBRADA)['sabe'] is False


def test_reranker_apartado_cae_a_los_umbrales_sin_reranker():
    """047:RF-30, RF-32 — sin CUDA no se usa el umbral del reranker: decide lo que queda."""
    def apartado(_c, _t):
        raise indice.RerankerNoDisponible('CUDA no disponible')
    apartado.etiqueta = 'reranker:m'
    r = indice.responder(Indice(FRAGS), Q_FRAGS, None, reordenador=apartado, abstencion=CALIBRADA)
    assert r['sabe'] is True and r['metodos'] == ['bm25'] and 'CUDA' in r['recuperacion']


def test_sin_calibrar_no_lo_se_y_lo_dice():
    """047:RF-33 — sin calibración, «No lo sé» antes que una cita que no apoya, y dice por qué."""
    r = indice.responder(Indice(FRAGS), Q_FRAGS, None, abstencion=indice.Abstencion())
    assert r['sabe'] is False and r['citas'] == [] and 'sin calibrar' in r['recuperacion']
    solo_vectores = indice.Abstencion(calibrada=True, umbral_coseno=0.5)
    r = indice.responder(Indice(FRAGS), Q_FRAGS, None, abstencion=solo_vectores)      # sin vectores ni su umbral
    assert r['sabe'] is False and 'sin calibrar' in r['recuperacion']


def test_la_web_pasa_la_abstencion_y_sin_calibrar_no_cita(tmp_path, monkeypatch):
    """047:RF-33 — la vía de la web usa la calibración guardada; sin ella, ninguna cita."""
    repo = _repo(tmp_path)
    monkeypatch.setattr(services, 'project_root', lambda: repo)
    monkeypatch.setattr('convertersmartgrid.asistente.ollama.cliente_configurado',
                        lambda: SimpleNamespace(modelos=lambda: None))
    monkeypatch.setattr(reranker, 'politica', lambda: {'hibrido': True, 'modelo': None, 'revision': None, 'motivo': ''})
    monkeypatch.setattr(reranker, 'abstencion', lambda: indice.Abstencion())
    r = services.asistente_pregunta('¿cómo se reparte la medida de la barra?')
    assert r['sabe'] is False and r['citas'] == [] and r['texto'].startswith('No lo sé')


def test_un_codigo_hallado_es_evidencia_y_uno_inventado_no():
    """047:RF-37 — el código que está tal cual cuenta; uno que no está no abre la puerta."""
    i = Indice(FRAGS)
    alto = indice.Abstencion(calibrada=True, umbral_bm25_solo=999.0)
    assert indice.responder(i, 'SE50106', None, abstencion=alto)['sabe'] is True
    assert indice.responder(i, 'SE99871 barra', None, abstencion=alto)['sabe'] is False


def _calibracion(tmp_path, **cambios):
    conjunto = tmp_path / 'calibracion.json'
    conjunto.write_text('{"preguntas": []}', encoding='utf-8')
    modelo = reranker.MODELOS[1]
    datos = {'conjunto_sha256': evaluacion_rag.sha256_de(conjunto), 'modelo_reranker': modelo,
             'revision': reranker.ficha_modelo(modelo)['revision'],
             'umbrales': {'reranker': 1.5, 'coseno': 0.8, 'bm25': None, 'bm25_solo': 9.0}, **cambios}
    ruta = tmp_path / 'umbrales.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return ruta, conjunto


def test_los_umbrales_solo_valen_con_su_conjunto(tmp_path):
    """047:RF-34 — la calibración vale con la huella de su conjunto; sin ella, sin calibrar."""
    ruta, conjunto = _calibracion(tmp_path)
    a = reranker.abstencion(ruta, conjunto)
    assert a.calibrada and a.umbral_reranker == 1.5 and a.umbral_coseno == 0.8 and a.umbral_bm25 is None
    assert a.modelo_reranker == reranker.MODELOS[1]
    assert not reranker.abstencion(tmp_path / 'no.json', conjunto).calibrada
    conjunto.write_text('{"preguntas": [1]}', encoding='utf-8')
    assert not reranker.abstencion(ruta, conjunto).calibrada


def test_revision_ajena_anula_solo_el_umbral_del_reranker(tmp_path):
    """047:RF-34 — otra revisión del modelo no hereda el umbral; coseno y BM25 siguen valiendo."""
    ruta, conjunto = _calibracion(tmp_path, revision='0' * 40)
    a = reranker.abstencion(ruta, conjunto)
    assert a.calibrada and a.umbral_reranker is None and a.umbral_bm25_solo == 9.0


def _fila(responde, bm25=0.0, coseno=0.0, puntos=0.0, codigo=False):
    return {'responde': responde, 'bm25': bm25, 'coseno': coseno, 'reranker': puntos, 'codigo': codigo}


def test_calibrar_elige_el_umbral_mas_bajo_que_cumple():
    """047:RF-34 — con 20 sin respuesta y objetivo 0,95, una puede pasar: el umbral queda sobre la segunda."""
    sin = [_fila(False, puntos=float(n)) for n in range(20)]
    con = [_fila(True, puntos=30.0), _fila(True, puntos=18.5), _fila(True, puntos=5.0)]
    c = evaluacion_rag.calibrar(sin + con)
    assert 18.0 < c['umbrales']['reranker'] < 18.1
    assert c['en_calibracion']['reranker']['abstencion'] >= 0.95
    assert c['en_calibracion']['reranker']['conserva'] == pytest.approx(2 / 3)


def test_calibrar_el_par_conserva_mas_y_puede_prescindir_de_una_senal():
    """047:RF-34 — BM25 no separa nada; el par se queda con el coseno y deja BM25 sin contar."""
    sin = [_fila(False, bm25=9.0, coseno=0.1 + n / 100) for n in range(20)]
    con = [_fila(True, bm25=9.0, coseno=0.9) for _ in range(5)]
    u = evaluacion_rag.calibrar(sin + con)['umbrales']
    # Un umbral de BM25 por encima de todas las preguntas tampoco decide nada.
    assert (u['bm25'] is None or u['bm25'] > 9.0) and 0.2 < u['coseno'] < 0.9


def test_calibrar_aparta_las_de_codigo_y_exige_los_dos_tipos():
    """047:RF-34, RF-37 — el código se decide aparte; sin preguntas de los dos tipos no se calibra."""
    sin = [_fila(False, puntos=1.0) for _ in range(20)]
    u = evaluacion_rag.calibrar(sin + [_fila(True, puntos=2.0), _fila(True, puntos=-9.0, codigo=True)])['umbrales']
    assert u['reranker'] == pytest.approx(1.0, abs=1e-3)
    with pytest.raises(ValueError):
        evaluacion_rag.calibrar(sin)


def _sellado_sintetico():
    frags = [Fragmento(i, f'doc{i}.md:1', f'clave{i} calibrar barra medidor texto propio del documento {i}') for i in range(30)]
    preguntas = [{'pregunta': f'clave{i} calibrar barra', 'fichero': f'doc{i}.md', 'ancla': f'clave{i} ', 'tipo': 'spec'} for i in range(20)]
    preguntas += [{'pregunta': f'calibrar barra pregunta{i}', 'sin_respuesta': True, 'tipo': 'dominio' if i % 2 else 'fuera'} for i in range(10)]
    return Indice(frags, [[1.0, 0.0]] * 30), {'procedencia': 'sintetico_maestro_de_sesion', 'preguntas': preguntas, 'sha256': 'sello'}


def test_el_sellado_mide_cada_metodo_y_aplica_la_puerta():
    """047:RF-36 — reranker que separa bien cumple su puerta; híbrido y BM25 que no abstienen, no."""
    i, conjunto = _sellado_sintetico()

    def puntuar(consulta, textos):
        return [5.0 if 'clave' in consulta and consulta.split()[0] + ' ' in t else -5.0 for t in textos]

    abst = indice.Abstencion(calibrada=True, modelo_reranker='m', umbral_reranker=0.0, umbral_coseno=0.5, umbral_bm25_solo=0.0)
    informe = evaluacion_rag.medir_sellado(i, conjunto, lambda q: [1.0, 0.0], puntuar, 'm', abst)
    assert informe['puerta']['reranker']['cumple'] is True, informe['puerta']['reranker']
    assert informe['metodos']['reranker']['abstention_accuracy'] == 1.0
    assert informe['puerta']['hibrido']['cumple'] is False and informe['cumple_todos'] is False
    assert any('abstención' in m for m in informe['puerta']['hibrido']['motivos'])
    assert informe['metodos']['reranker']['abstencion_por_tipo'] == {'dominio': 1.0, 'fuera': 1.0}
    assert informe['conjunto_sha256'] == 'sello'
    assert 'calibrar barra' not in json.dumps(informe['metodos'], ensure_ascii=False)


def test_perder_recall_veta_aunque_se_abstenga():
    """047:RF-36 — abstenerse de todo daría 1,0 de abstención: la puerta lo rechaza por Recall@10."""
    i, conjunto = _sellado_sintetico()
    todo_no = indice.Abstencion(calibrada=True, modelo_reranker='m', umbral_reranker=99.0, umbral_coseno=99.0, umbral_bm25_solo=99.0)
    informe = evaluacion_rag.medir_sellado(i, conjunto, lambda q: [1.0, 0.0], lambda c, t: [0.0] * len(t), 'm', todo_no)
    assert informe['metodos']['reranker']['abstention_accuracy'] == 1.0
    assert informe['puerta']['reranker']['cumple'] is False
    assert any('Recall@10' in m for m in informe['puerta']['reranker']['motivos'])
    assert any('significativa' in m for m in informe['puerta']['reranker']['motivos'])
    # clave10 a clave19 son códigos que están tal cual: cuentan como evidencia (RF-37).
    assert informe['metodos']['reranker']['con_respuesta_abstenidas'] == 10


def test_un_reranker_que_falla_al_medir_no_cumple():
    """047:RF-36 — si el reranker no corre, su puerta no se da por buena."""
    i, conjunto = _sellado_sintetico()

    def falla(_c, _t):
        raise indice.RerankerNoDisponible('Memoria insuficiente')

    abst = indice.Abstencion(calibrada=True, modelo_reranker='m', umbral_reranker=0.0, umbral_coseno=0.5, umbral_bm25_solo=0.0)
    informe = evaluacion_rag.medir_sellado(i, conjunto, lambda q: [1.0, 0.0], falla, 'm', abst)
    assert informe['puerta']['reranker']['cumple'] is False and 'Memoria' in informe['metodos']['reranker']['error']


def test_el_sellado_no_se_mide_dos_veces(tmp_path, monkeypatch):
    """047:RF-35 — con un informe de la misma huella, la herramienta se niega sin tocar la GPU."""
    import importlib.util

    ruta = RAIZ / 'tools' / 'asistente_evaluar_rag.py'
    spec = importlib.util.spec_from_file_location('asistente_evaluar_rag', ruta)
    herramienta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(herramienta)
    sello = evaluacion_rag.sha256_de(RAIZ / 'docs' / 'RAG_ABSTENCION_SELLADO_047.json')
    salida = tmp_path / 'informe.json'
    salida.write_text(json.dumps({'conjunto_sha256': sello}), encoding='utf-8')
    monkeypatch.setattr(reranker, 'abstencion', lambda: pytest.fail('no debía seguir'))
    assert herramienta.main(['--datos', str(tmp_path / 'd'), '--sellado', '--salida', str(salida)]) == 2


def test_el_sellado_exige_calibracion_antes(tmp_path, monkeypatch):
    """047:RF-34, RF-35 — sin umbrales fijados no se abre el conjunto sellado."""
    import importlib.util

    spec = importlib.util.spec_from_file_location('asistente_evaluar_rag', RAIZ / 'tools' / 'asistente_evaluar_rag.py')
    herramienta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(herramienta)
    monkeypatch.setattr(reranker, 'abstencion', lambda: indice.Abstencion())
    assert herramienta.main(['--datos', str(tmp_path / 'd'), '--sellado', '--salida', str(tmp_path / 'x.json')]) == 2


def test_los_conjuntos_nuevos_estan_separados_y_anclan():
    """047:RF-34 — calibración, sellado y los 76 no comparten preguntas ni respuestas esperadas."""
    nombres = ('RAG_ABSTENCION_CALIBRACION_047', 'RAG_ABSTENCION_SELLADO_047', 'RAG_PREGUNTAS_SINTETICAS_047')
    cal, sel, his = (evaluacion_rag.cargar_conjunto(RAIZ / 'docs' / f'{n}.json') for n in nombres)
    def textos(c):
        return {x['pregunta'] for x in c['preguntas']}
    def anclas(c):
        return {(x['fichero'], x['ancla']) for x in c['preguntas'] if 'ancla' in x}
    for a, b in ((cal, sel), (cal, his), (sel, his)):
        assert not textos(a) & textos(b) and not anclas(a) & anclas(b)
    frags = indice.fragmentos(RAIZ)
    for c in (cal, sel):
        pares, sin_ancla, _ = evaluacion_rag.resolver_pares(c, frags)
        assert len(sin_ancla) <= 4, sin_ancla                         # medir exige el 100 %; esto vigila la deriva
        assert sum(not p.answerable for p in pares) == 40
        assert {x['tipo'] for x in c['preguntas'] if x.get('sin_respuesta')} == {'dominio', 'fuera'}
    assert sel['sha256'] == '2faeb8c3973f308bab55b74116ec1651581178151da6c02e8f90f35953a45231'
    assert cal['sha256'] == 'c5ba77aaca78a92d531475030b9f88cbdb08678614bda758ac794efd0e572437'
    assert his['sha256'] == '88245a0755bac8813968dee64a03a22778168d8a6aec9d21e813f73a0ff5c36a'

