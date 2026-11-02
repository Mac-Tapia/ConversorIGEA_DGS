"""Spec 047, T2: recuperación híbrida, reranker contrastado y citas verificables.

Fase sintética: el reranker es una función inyectada; ninguna prueba carga un modelo ni usa la
GPU. La medición con los modelos reales es de ``tools/asistente_evaluar_rag.py``.
"""
from __future__ import annotations

import json
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
    with pytest.raises(indice.RerankerNoDisponible, match='CUDA'):
        reranker.cargar_puntuador(reranker.MODELOS[0], reranker.ficha_modelo(reranker.MODELOS[0])['revision'])

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
