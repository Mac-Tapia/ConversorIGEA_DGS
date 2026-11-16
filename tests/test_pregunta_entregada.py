"""«Pregunta» en el programa instalado: abstención calibrada sobre los manuales que se entregan (086:RF-15, RF-44;
097:RF-19). Decisión del usuario del 2026-11-13: responde con la abstención calibrada al construir el candidato."""
import json
import shutil
from pathlib import Path

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.asistente import indice, pregunta_entregada as PE, reranker

CC = cargar_herramienta('construir_candidato.py')
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def programa(tmp_path, monkeypatch):
    """La carpeta ``_programa`` de un paquete, con sus documentos, como la deja el constructor."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    raiz = tmp_path / '_programa'
    CC.documentos_de_pregunta(REPO, raiz, CC.version_del_paquete(REPO), calibrar=False)
    return raiz


def test_la_calibracion_cumple_su_objetivo_con_muestra_suficiente(programa):
    """097:RF-19 — al menos 100 sin respuesta y 30 con ella; el umbral sale del cuantil ⌈(n+1)(1−α)⌉/n."""
    datos = PE.calibrar(programa)
    n = datos['muestra']['sin_respuesta']
    assert n >= 100 and datos['muestra']['con_respuesta'] >= 30
    assert datos['objetivo'] == pytest.approx(PE.objetivo(n)) and datos['objetivo'] > 0.95
    assert datos['en_calibracion']['abstencion'] >= datos['objetivo']
    assert datos['en_calibracion']['conserva'] > 0.5, 'una abstención que calla todo no responde'
    assert all(f.startswith('documentos/') for f in datos['ficheros'])
    assert not any(x in f for f in datos['ficheros'] for x in ('MANUAL_COMANDOS', 'GUIA_PRUEBA')), 'solo lo del operador'
    assert (programa / PE.CARPETA / PE.CALIBRACION).is_file()


def test_pregunta_lee_los_manuales_como_llegan_al_cliente(programa):
    """086:RF-91, 097:RF-19 — el corpus de «pregunta» no lleva las secciones de desarrollo que la entrega quita del
    manual: el cliente no las tiene, y en la calibración un título casi vacío casaba con preguntas ajenas."""
    secciones = json.loads((REPO / 'config' / 'entrega.json').read_text(encoding='utf-8'))['documentos'][
        'secciones_de_desarrollo']
    assert secciones, 'la lista de secciones de desarrollo existe'
    for rel, titulos in secciones.items():
        texto = (programa / PE.CARPETA / Path(rel).name).read_text(encoding='utf-8')
        for titulo in titulos:
            assert titulo not in texto, (rel, titulo)
        assert texto.strip(), rel


def test_sin_muestra_minima_no_se_calibra(programa):
    """097:RF-19 — con menos de 100 preguntas sin respuesta no se calibra, y dice cuántas faltan."""
    ruta = programa / PE.CARPETA / PE.CONJUNTO
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    datos['preguntas'] = [p for p in datos['preguntas'] if not p.get('sin_respuesta')][:30] + \
        [p for p in datos['preguntas'] if p.get('sin_respuesta')][:20]
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError, match='faltan 80 sin respuesta'):
        PE.calibrar(programa)


def test_una_pregunta_copiada_en_el_corpus_no_se_calibra(programa):
    """097:RF-19 — ninguna pregunta del conjunto puede estar literal en los documentos que la juzgan."""
    datos = json.loads((programa / PE.CARPETA / PE.CONJUNTO).read_text(encoding='utf-8'))
    copiada = next(p['pregunta'] for p in datos['preguntas'] if p.get('sin_respuesta'))
    manual = programa / PE.CARPETA / 'MANUAL_OPERADOR.md'
    manual.write_text(manual.read_text(encoding='utf-8') + f'\n\n{copiada}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='literales en el corpus'):
        PE.calibrar(programa)


def test_el_constructor_no_arma_sin_poder_calibrar(programa, tmp_path):
    """086:RF-44 — el candidato exige la calibración; un ancla perdida se dice y no se arma."""
    ruta = programa / PE.CARPETA / PE.CONJUNTO
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    datos['preguntas'][0]['fuentes'][0]['ancla'] = 'Un apartado que no existe en ningún manual'
    copia = tmp_path / 'repo'
    (copia / 'config' / 'pregunta_entregada').mkdir(parents=True)
    (copia / CC.CONJUNTO_PREGUNTA).write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    for rel in CC.documentos_del_candidato(CC.version_del_paquete(REPO)):
        if (REPO / rel).is_file():
            (copia / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / rel, copia / rel)
    with pytest.raises(CC.CE.EntregaError, match='ancla'):
        CC.documentos_de_pregunta(copia, tmp_path / 'otro' / '_programa', CC.version_del_paquete(REPO), calibrar=True)


def test_el_instalado_responde_lo_que_esta_y_se_abstiene_de_lo_que_no(programa, monkeypatch):
    """086:RF-15 — en el instalado, «pregunta» usa el corpus entregado con su calibración: responde una pregunta de los
    manuales y dice «No lo sé» a una ajena, sin GPU, vectores ni reranker."""
    PE.calibrar(programa)
    servir = reranker.servicio_entregado(programa / PE.CARPETA / PE.CALIBRACION, programa / PE.CARPETA / PE.CONJUNTO)
    assert servir['corpus'] == indice.CORPUS_ENTREGA and servir['abstencion'].calibrada
    assert servir['politica']['hibrido'] is False and servir['politica']['modelo'] is None
    buscador = indice.cargar_o_construir(programa, servir['corpus'])
    si = indice.responder(buscador, '¿Cómo vuelvo a la versión anterior del programa después de actualizar?', None,
                          repo=programa, usar_vectores=False, abstencion=servir['abstencion'])
    assert si['sabe'] is True and any('MANUAL_INSTALACION' in c['fuente'] for c in si['citas'])
    no = indice.responder(buscador, '¿Cuántos goles marcó Pelé en su carrera?', None, repo=programa,
                          usar_vectores=False, abstencion=servir['abstencion'])
    assert no['sabe'] is False


def test_sin_calibracion_el_instalado_no_inventa(programa):
    """086:RF-15 — sin la calibración del constructor, la abstención queda sin calibrar y no se responde con citas."""
    servir = reranker.servicio_entregado(programa / PE.CARPETA / PE.CALIBRACION, programa / PE.CARPETA / PE.CONJUNTO)
    assert servir['abstencion'].calibrada is False


def test_el_programa_instalado_elige_el_corpus_entregado(monkeypatch):
    """086:RF-15 — instalado, sin specs ni CODIGO_FUENTE, la web sirve el corpus entregado y no el de la 047."""
    monkeypatch.setattr(reranker, 'es_programa_instalado', lambda raiz: True)
    assert reranker.servicio()['corpus'] == indice.CORPUS_ENTREGA
    monkeypatch.setattr(reranker, 'es_programa_instalado', lambda raiz: False)
    assert reranker.servicio()['corpus'] != indice.CORPUS_ENTREGA


def _calibracion_alterada(programa, cambio):
    ruta = programa / PE.CARPETA / PE.CALIBRACION
    PE.calibrar(programa)
    ruta.write_text(cambio(ruta.read_text(encoding='utf-8')), encoding='utf-8')
    return reranker.servicio_entregado(ruta, programa / PE.CARPETA / PE.CONJUNTO)


def test_sin_calibracion_el_instalado_lo_avisa_y_dice_por_que(programa, caplog):
    """086:RF-15 — sin la calibración, el «No lo sé» no es silencioso: queda un aviso en el registro y en la política, con
    el fichero que falta, para que el operador sepa por qué el asistente no responde."""
    ruta = programa / PE.CARPETA / PE.CALIBRACION
    with caplog.at_level('WARNING', logger=reranker.__name__):
        servir = reranker.servicio_entregado(ruta, programa / PE.CARPETA / PE.CONJUNTO)
    assert servir['abstencion'].calibrada is False
    motivo = servir['politica']['abstencion_sin_calibrar']
    assert 'no existe' in motivo and ruta.name in motivo
    avisos = [r for r in caplog.records if r.levelname == 'WARNING' and r.name == reranker.__name__]
    assert len(avisos) == 1 and motivo in avisos[0].getMessage()


@pytest.mark.parametrize('cambio, esperado', [
    (lambda t: t[: len(t) // 2], 'ilegible'),
    (lambda t: json.dumps({k: v for k, v in json.loads(t).items() if k != 'umbrales'}), "falta 'umbrales'"),
    (lambda t: json.dumps({**json.loads(t), 'umbrales': {'bm25_solo': 'alto'}}), 'umbral'),
    (lambda t: json.dumps({**json.loads(t), 'corpus': 'otro'}), 'otro corpus'),
    (lambda t: json.dumps({**json.loads(t), 'conjunto_sha256': '0' * 64}), 'otro conjunto'),
])
def test_una_calibracion_que_no_vale_se_avisa_con_su_causa(programa, caplog, cambio, esperado):
    """086:RF-15 — una calibración ilegible, incompleta, de otro corpus o de otro conjunto deja la abstención sin calibrar
    (no responde con citas) y lo avisa con la causa concreta, en vez de callarlo."""
    with caplog.at_level('WARNING', logger=reranker.__name__):
        servir = _calibracion_alterada(programa, cambio)
    assert servir['abstencion'].calibrada is False
    motivo = servir['politica']['abstencion_sin_calibrar']
    assert esperado in motivo, motivo
    assert any(motivo in r.getMessage() for r in caplog.records if r.levelname == 'WARNING')


def test_con_su_calibracion_no_hay_aviso(programa, caplog):
    """086:RF-15 — con la calibración del constructor, ni aviso ni motivo: la abstención está calibrada."""
    PE.calibrar(programa)
    with caplog.at_level('WARNING', logger=reranker.__name__):
        servir = reranker.servicio_entregado(programa / PE.CARPETA / PE.CALIBRACION, programa / PE.CARPETA / PE.CONJUNTO)
    assert servir['abstencion'].calibrada is True
    assert 'abstencion_sin_calibrar' not in servir['politica']
    assert not [r for r in caplog.records if r.levelname == 'WARNING' and r.name == reranker.__name__]
