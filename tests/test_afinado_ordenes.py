"""079 — afinado real del intérprete de órdenes.

Todo con dobles sobre la CPU, o un XLM-Roberta diminuto sin pesos descargados: ningún texto real del operador (P9), ni el almacén
real, ni GPU, ni DIgSILENT. La medida de verdad la lanza el integrador (T7).
"""
from collections import Counter
import copy
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import types

import pytest

torch = pytest.importorskip('torch')

from test_interprete_codificador import CodificadorFalso, _entrenado, _humanas, _pequeno, falso  # noqa: E402,F401

from convertersmartgrid.asistente import afinado_ordenes as af                         # noqa: E402
from convertersmartgrid.asistente import codificador_ordenes as co                     # noqa: E402
from convertersmartgrid.asistente import curriculo_maestro as cm                       # noqa: E402
from convertersmartgrid.asistente import destilacion_integral as di                    # noqa: E402
from convertersmartgrid.asistente import ordenes_fijas as of                           # noqa: E402
from convertersmartgrid.asistente import prueba_sellada as anterior                    # noqa: E402
from convertersmartgrid.asistente import prueba_sellada_079 as ps                      # noqa: E402
from convertersmartgrid.asistente import transformer as tr                             # noqa: E402
from convertersmartgrid.asistente import validacion_cruzada as vc                      # noqa: E402
from convertersmartgrid.asistente.interprete import PUESTO_CHARLA, charla_cerca, interpretar  # noqa: E402
from convertersmartgrid.asistente.maestro_real import NINGUNA, clave_texto, firma_familia  # noqa: E402
from convertersmartgrid.asistente.sinteticos import expandir                           # noqa: E402
from convertersmartgrid.asistente.tareas import TAREAS                                 # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CPU = torch.device('cpu')
VOCAB = {'alimentadores': ['AB101', 'CD202'], 'proyecto': ['Proyecto X'], 'sistema': ['Valle'], 'set': ['Puerto']}


@pytest.fixture(scope='module')
def corpus():
    return di.preparar_corpus(VOCAB, [], por_familia=4)


# ------------------------------------------------------------------ la prueba sellada

def test_sellada_cubre_el_catalogo_con_frases_nuevas():
    """079:RF-38 — al menos 5 frases por cada tarea del catálogo."""
    assert set(ps.FRASES) == set(TAREAS)
    assert all(len(set(v)) >= 5 for v in ps.FRASES.values())
    por_tarea = {}
    for r in ps.selladas():
        por_tarea.setdefault(r['tarea'], set()).add(r['group_id'])
    assert all(len(g) >= 5 for g in por_tarea.values())


def test_sellada_huella_fija_sin_depender_del_espacio():
    """079:RF-39 — misma huella con cualquier vocabulario del espacio."""
    assert ps.CONJUNTO == 'sellada_079' and ps.huella_de(ps.filas()) == ps.HUELLA
    uno, m1 = di.preparar_corpus({}, [], por_familia=1)
    dos, m2 = di.preparar_corpus({'alimentadores': ['ZZ909'], 'proyecto': ['Otro'], 'sistema': ['Valle']}, [], por_familia=1)
    sellada = lambda filas: sorted(r['record_id'] for r in filas if r.get('conjunto') == ps.CONJUNTO)  # noqa: E731
    assert sellada(uno) == sellada(dos) and m1['prueba_sellada_079']['huella'] == m2['prueba_sellada_079']['huella'] == ps.HUELLA


def test_sellada_cambiar_una_frase_se_rechaza(monkeypatch):
    """079:RF-40 — tocar una frase mueve la huella y se rechaza."""
    monkeypatch.setitem(ps.FRASES, 'estado', (*ps.FRASES['estado'][:-1], 'una frase cambiada'))
    with pytest.raises(ValueError, match='huella'):
        ps.selladas()


def test_sellada_declara_su_metodo():
    """079:RF-41 — quién, cómo y qué no garantiza."""
    for frase in ('un solo autor', 'de una vez', 'sin mirar ningún modelo', 'expandir', 'semilla', 'HUELLA',
                  'Lo que no garantiza', 'Otro redactor no era posible'):
        assert frase in ps.__doc__, frase


def test_sellada_choque_con_seleccion_para(monkeypatch):
    """079:RF-42 — si coincide con selección o calibración se para: cambiarlas movería sus huellas."""
    fila = {**ps.selladas()[0], 'particion': 'seleccion', 'record_id': 'x', 'group_id': 'g'}
    with pytest.raises(ValueError, match='sellada coincide'):
        di._con_la_prueba_sellada([fila])


def test_sellada_ninguna_familia_entrena(corpus):
    """079:RF-43 — ni un texto ni una familia suya entrena, selecciona o calibra."""
    filas, _ = corpus
    sellada = [r for r in filas if r.get('conjunto') == ps.CONJUNTO]
    resto = [r for r in filas if r['particion'] != 'prueba']
    textos = {clave_texto(r['texto']) for r in sellada}
    familias = {firma_familia(r['texto'], r['datos']) for r in sellada}
    assert sellada and resto
    assert not [r for r in resto if clave_texto(r['texto']) in textos or firma_familia(r['texto'], r['datos']) in familias]


def test_sellada_sale_del_entrenamiento_lo_que_coincide():
    """079:RF-43 — una fila de entrenamiento igual a una sellada sale de él, y se cuenta."""
    fila = {**ps.selladas()[0], 'particion': 'entrenamiento', 'record_id': 'x', 'group_id': 'g'}
    filas, _anterior, nueva = di._con_la_prueba_sellada([fila])
    assert all(r['record_id'] != 'x' for r in filas) and nueva['quitadas_de_entrenar'] == 1


def test_sellada_separada_de_la_anterior():
    """079:RF-44 — ningún texto ni familia en común con la sellada anterior; solo se comparan cuentas."""
    vieja = anterior.selladas()
    textos = {clave_texto(r['texto']) for r in vieja}
    familias = {firma_familia(r['texto'], r['datos']) for r in vieja}
    choques = [r for r in ps.selladas() if clave_texto(r['texto']) in textos or firma_familia(r['texto'], r['datos']) in familias]
    assert not choques, len(choques)


def test_sellada_anterior_intacta_y_sin_decidir(corpus):
    """079:RF-46 / 079:RF-36 — su huella sigue y queda marcada sin decidir; la de las fijas, igual."""
    filas, meta = corpus
    assert meta['prueba_sellada']['huella'] == anterior.HUELLA == 'df5e1db88595d378'
    assert meta['prueba_sellada']['decide'] is False and meta['prueba_sellada_079']['decide'] is True
    assert of.huella(of.generar({})) == '41f7ab110ac35c0b'
    assert sum(r.get('conjunto') == anterior.CONJUNTO for r in filas) == meta['prueba_sellada']['filas']
    assert not [r for r in filas if r.get('conjunto') and di.es_historica(r)]


def test_sellada_vedada_a_la_lectura_local():
    """079:RF-60 — el patrón de los sellados de la 077 la cubre, sin tocar la lectura del proyecto."""
    from convertersmartgrid.asistente import lectura_proyecto as lp
    import fnmatch
    assert any(fnmatch.fnmatch(Path(ps.__file__).name, p) for p in lp.SELLADOS)


def test_sellada_filas_sin_datos_de_empresa():
    """079:RF-41 / P13 — vocabulario propio e inventado: ningún prefijo ni nombre de una empresa real."""
    texto = Path(ps.__file__).read_text(encoding='utf-8')
    assert not re.search(r'electro\s*dunas|\bica\b|\bpisco\b|\bchincha\b', texto, re.I)


def test_sellada_informe_sin_textos_en_el_manifiesto(corpus):
    """079:RF-64 — el manifiesto, que acaba en el registro, no lleva frases de las selladas."""
    filas, meta = corpus
    volcado = json.dumps({k: meta[k] for k in ('prueba_sellada', 'prueba_sellada_079')}, ensure_ascii=False)
    assert all(r['texto'] not in volcado for r in filas if r.get('conjunto'))


def test_sellada_familia_ancha_no_esta_en_seleccion(corpus):
    """079:RF-42 — con la familia más ancha de la 075 se cuenta lo que se parece a selección, por si crece sin avisar."""
    filas, _ = corpus
    desarrollo = vc.Claves(vc.clave_de_familia(r['texto'], r['datos']) for r in filas if r['particion'] == 'seleccion')
    frases = {r['group_id']: r for r in ps.selladas()}
    parecidas = sum(desarrollo.toca(vc.clave_de_familia(r['texto'], r['datos'])) for r in frases.values())
    assert parecidas <= len(frases) // 2, parecidas


# ------------------------------------------------------------------ dobles del afinado

class BaseFalsa(CodificadorFalso):
    """Un codificador partido: lo congelado sale del hash de cada palabra y el tramo son capas lineales con residuo."""
    def __init__(self, *_a):
        super().__init__()
        self.prefijos, self.pasos_tramo, self._original = [], 0, {}

    def prefijo(self, textos, capas):
        self.prefijos.extend(textos)
        cod = CodificadorFalso.__call__(self, textos)
        estados = torch.nn.utils.rnn.pad_sequence(cod.tokens, batch_first=True)
        atencion = torch.zeros(estados.shape[:2], dtype=torch.long)
        for i, t in enumerate(cod.tokens):
            atencion[i, :len(t)] = 1
        return co.Prefijo(estados, atencion, [list(range(len(t))) for t in cod.tokens], cod.tramos)

    def tramo_original(self, capas):
        if capas not in self._original:
            torch.manual_seed(1234)
            self._original[capas] = torch.nn.ModuleList(torch.nn.Linear(self.dim, self.dim) for _ in range(capas))
        return copy.deepcopy(self._original[capas])

    def aplicar_tramo(self, tramo, estados, atencion):
        self.pasos_tramo += 1
        h = estados
        for capa in tramo:
            h = h + capa(h)
        return h

    def huella_congelada(self, capas):
        return f'congelada-{capas}'


def _seleccion():
    return [{'texto': e.texto, 'tarea': e.tarea, 'datos': [list(d) for d in e.datos]} for e in _pequeno()[:6]]


def _cfg(**kw):
    base = dict(afinar_capas=2, afinar_epocas=2, pasos_por_epoca=6, afinar_lote=8, afinar_piezas=200, oculta_tarea=16, oculta_etiquetas=8,
                lr_tramo=1e-2, lr_cabezas=5e-3)
    return co.Configuracion(**{**base, **kw})


def _afinado(cfg=None, base=None, seleccion=None):
    base = base or BaseFalsa()
    cache = af.CachePrefijo(base, (cfg or _cfg()).afinar_capas, _seleccion() if seleccion is None else seleccion, di.evaluar_alumno)
    return co.entrenar(_pequeno(), cfg or _cfg(), cache=cache, dispositivo=CPU), base, cache


def _tramo(modelo):
    return {k: v.clone() for k, v in modelo.red.tramo.state_dict().items()}


class TokenizadorDiminuto:
    """Una pieza por palabra, con sus posiciones, como el de e5: sin descargar nada."""
    def __call__(self, textos, **_k):
        filas = [[(m.span(), hash(m.group()) % 90 + 5) for m in re.finditer(r'\S+', t)] for t in textos]
        largo = max(len(f) for f in filas) + 2
        ids, atencion, posiciones = [], [], []
        for f in filas:
            ids.append([1, *(i for _s, i in f), 2, *[0] * (largo - len(f) - 2)])
            atencion.append([1] * (len(f) + 2) + [0] * (largo - len(f) - 2))
            posiciones.append([(0, 0), *(s for s, _i in f), *[(0, 0)] * (largo - len(f) - 1)])

        class Lote(dict):
            pass
        return Lote(input_ids=torch.tensor(ids), attention_mask=torch.tensor(atencion), offset_mapping=torch.tensor(posiciones))


@pytest.fixture(scope='module')
def diminuto():
    """El codificador real de la 069 sobre un XLM-Roberta aleatorio, sin descargar nada."""
    from transformers import XLMRobertaConfig, XLMRobertaModel

    torch.manual_seed(5)
    cfg = XLMRobertaConfig(vocab_size=100, hidden_size=24, num_hidden_layers=4, num_attention_heads=2, intermediate_size=32,
                           max_position_embeddings=128, pad_token_id=0)
    cod = object.__new__(co.CodificadorPreentrenado)
    cod.tokenizador, cod.red, cod.dispositivo, cod.dim, cod._huellas = TokenizadorDiminuto(), XLMRobertaModel(cfg).eval(), CPU, 24, {}
    for p in cod.red.parameters():
        p.requires_grad_(False)
    return cod


# ------------------------------------------------------------------ afinado

def test_afinado_aprende_tramo_y_cabezas():
    """079:RF-1 — el tramo cambia y aprende: reconoce lo que entrenó."""
    m, base, _ = _afinado(_cfg(afinar_epocas=40, paciencia=40, lr_cabezas=1e-2))
    original = base.tramo_original(2).state_dict()
    assert any(not torch.equal(v, original[k]) for k, v in m.red.tramo.state_dict().items())
    p = m.predecir('convierte AB101')
    assert p['tarea'] == 'convertir' and [d['valor'] for d in p['datos']['alimentadores']] == ['AB101']


def test_afinado_suma_la_contrastiva_y_las_otras_dos(monkeypatch):
    """079:RF-25 — el bucle la suma con su peso: con peso cero no cambia la pérdida por su culpa, y se llama en cada paso."""
    llamadas = []
    original = af.perdida_contrastiva

    def espia(*a):
        valor = original(*a)
        llamadas.append(valor.detach())
        return valor + 100.
    monkeypatch.setattr(af, 'perdida_contrastiva', espia)
    con = _afinado(_cfg(peso_contrastiva=1., afinar_epocas=1))[0].afinado['epocas'][0]
    sin = _afinado(_cfg(peso_contrastiva=0., afinar_epocas=1))[0].afinado['epocas'][0]
    assert len(llamadas) >= con['pasos'] + sin['pasos'] and con['perdida'] > sin['perdida'] + 50


def test_afinado_sin_opcion_solo_cabezas():
    """079:RF-2 — sin capas, las cabezas de siempre, sin tramo, y las capas no se recorren."""
    cod = BaseFalsa()
    m = co.entrenar(_pequeno(), co.Configuracion(epocas=1, lote_tarea=8, lote_etiquetas=8, oculta_tarea=8, oculta_etiquetas=8),
                    cache=co.CacheCodificada(cod), dispositivo=CPU)
    assert not hasattr(m.red, 'tramo') and cod.pasos_tramo == 0 and m.meta_extra['arquitectura'] == co.ARQUITECTURA
    assert co.Configuracion().afinar_capas == 0


def test_afinado_tasas_diferenciadas():
    """079:RF-3 / 079:RF-4 — las cabezas más rápido que el tramo, y cada capa más despacio que la siguiente."""
    cfg = _cfg(afinar_capas=3, lr_tramo=2e-5, lr_cabezas=1e-3, decaimiento_capa=.8)
    red = co.construir_cabezas(8, 3, 3, cfg)
    red.tramo = torch.nn.ModuleList(torch.nn.Linear(8, 8) for _ in range(3))
    g = af.grupos_de_parametros(red, cfg)
    assert g[0]['lr'] == 1e-3 and g[1]['lr'] < g[2]['lr'] < g[3]['lr'] == 2e-5 < g[0]['lr']
    assert sum(len(x['params']) for x in g) == len(list(red.parameters()))
    cabezas, *tramo = af.plan_de_tasas(100, 3)
    assert len(tramo) == 3 and cabezas(0) == 1. and tramo[0](0) == .1 and tramo[0](9) == .91 and tramo[0](50) == cabezas(50) == .5
    assert cabezas(99) == .1


def test_afinado_por_omision_pocas_capas_y_lotes_ajustados():
    """079:RF-5 / 079:RF-6 / 079:RF-7 — 2 capas al pedirlo, 32 frases, 1 536 piezas y 5 GB."""
    import inspect
    d = co.Configuracion()
    assert (d.afinar_lote, d.afinar_piezas, d.tope_gpu_gb) == (32, 1536, 5.)
    herramienta = (RAIZ / 'tools/asistente_entrenar.py').read_text(encoding='utf-8')
    assert re.search(r"--afinar-capas', type=int, default=2", herramienta)
    assert 'afinar_capas' in inspect.signature(co.Configuracion).parameters


@pytest.mark.parametrize('semilla', [1, 2, 3])
def test_afinado_el_lote_no_pasa_del_presupuesto(semilla):
    """079:RF-6 — con el relleno contado y largos sorteados; una frase sola siempre cabe."""
    rnd = random.Random(semilla)
    largos = [rnd.randint(3, 96) for _ in range(400)]
    cfg = co.Configuracion(afinar_capas=2, afinar_lote=32, afinar_piezas=512, pasos_por_epoca=10 ** 6)
    tareas = [rnd.choice(('calibrar', 'estado', 'flujo', NINGUNA)) for _ in largos]
    lotes = af.lotes_de_epoca(tareas, largos, cfg, rnd)
    assert all(len(x) <= 32 and (len(x) * max(largos[i] for i in x) <= 512 or len(x) == 1) for x in lotes)
    assert {i for x in lotes for i in x} == set(range(len(largos)))
    uno = af.lotes_de_epoca(['estado'], [800], cfg, random.Random(0))
    assert uno == [[0]]


def test_afinado_tope_de_pasos_por_epoca():
    """079:RF-11 — una época es un tope de pasos: se mide selección a menudo, también con muchas filas."""
    cfg = co.Configuracion(afinar_capas=2, afinar_lote=4, pasos_por_epoca=3)
    assert len(af.lotes_de_epoca(['estado'] * 400, [5] * 400, cfg, random.Random(0))) == 3


def test_afinado_limita_la_memoria_de_gpu(monkeypatch):
    """079:RF-7 — 5 GB de 8 GB, sin tocar la GPU; en la CPU no se llama."""
    assert af.fraccion_de_gpu(5., 8 * 2 ** 30) == .625 and af.fraccion_de_gpu(16., 8 * 2 ** 30) == 1.
    fracciones = []
    # Sin dispositivo en el doble: el real rechaza `cuda` sin índice, que es lo que da ``oraculo.dispositivo``.
    monkeypatch.setattr(torch.cuda, 'set_per_process_memory_fraction', lambda f: fracciones.append(f))
    monkeypatch.setattr(torch.cuda, 'reset_peak_memory_stats', lambda: None)
    monkeypatch.setattr(torch.cuda, 'current_device', lambda: 0)
    monkeypatch.setattr(torch.cuda, 'get_device_properties', lambda d: types.SimpleNamespace(total_memory=8 * 2 ** 30) if d == 0 else 1 / 0)
    af._limitar_memoria(co.Configuracion(), CPU)
    assert not fracciones
    af._limitar_memoria(co.Configuracion(), torch.device('cuda'))
    assert fracciones == [.625]


def test_afinado_sin_memoria_nombra_la_opcion():
    """079:RF-8 — dice qué bajar."""
    class SinMemoria(BaseFalsa):
        def aplicar_tramo(self, *_a):
            raise torch.cuda.OutOfMemoryError('CUDA out of memory')
    with pytest.raises(RuntimeError, match='--afinar-lote'):
        _afinado(base=SinMemoria())


def test_afinado_precision_mixta_en_cuda(monkeypatch):
    """079:RF-9 — el tramo pasa bajo autocast en float16 y con el escalador; aquí, los dos sobre un doble: la GPU real no se prueba."""
    llamadas, escaladores = [], []

    class Contexto:
        def __init__(self, *a, **k):
            llamadas.append((a, k))
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False

    real = torch.amp.GradScaler

    def escalador(tipo, enabled=True):
        escaladores.append(enabled)
        return real('cpu', enabled=False)
    monkeypatch.setattr(af, 'con_precision_mixta', lambda _d: True)
    monkeypatch.setattr(torch.amp, 'autocast', Contexto)
    monkeypatch.setattr(torch.amp, 'GradScaler', escalador)
    _afinado()
    assert llamadas and all(k['enabled'] is True and k['dtype'] is torch.float16 for _a, k in llamadas) and escaladores == [True]
    monkeypatch.undo()
    assert af.con_precision_mixta(torch.device('cuda')) and not af.con_precision_mixta(CPU)


def test_afinado_sin_gpu_el_error_de_siempre(falso, monkeypatch):
    """079:RF-10 — pedir afinado sin GPU falla como siempre, antes de abrir nada."""
    filas, meta = di.preparar_corpus({}, _humanas(), por_familia=1)
    di.guardar_corpus(falso / 'corpus', filas, meta)

    def sin_gpu():
        raise RuntimeError('No hay GPU con CUDA')
    monkeypatch.setattr(tr, 'dispositivo_de_calculo', sin_gpu)
    monkeypatch.setattr(co, 'FABRICA', lambda *_a: pytest.fail('no debe abrir el codificador'))
    with pytest.raises(RuntimeError, match='CUDA'):
        di.entrenar_destilacion(falso / 'corpus', falso / 'run', cfg=_cfg(), semillas=(11,), log=lambda *_a, **_k: None)


def test_afinado_parada_y_mejor_epoca(monkeypatch):
    """079:RF-11 / 079:RF-12 — para tras 2 sin mejorar y se queda con los pesos de la mejor."""
    medidas = iter([(.5, .5), (.9, .9), (.6, .9), (.7, .9), (.99, .99), (.99, .99)])
    vistos = []

    def medir(modelo, _seleccion):
        vistos.append({k: v.clone() for k, v in modelo.red.state_dict().items()})
        return next(medidas)
    monkeypatch.setattr(af, 'medir_seleccion', medir)
    m, _b, _c = _afinado(_cfg(afinar_epocas=6))
    assert len(vistos) == 4 and m.afinado['mejor_epoca'] == 1 and m.afinado['parada_temprana']
    assert m.afinado['seleccion_mejor'] == [.9, .9]
    assert all(torch.equal(v, vistos[1][k]) for k, v in m.red.state_dict().items())
    assert not m.red.training


def test_afinado_el_desempate_es_el_f1(monkeypatch):
    """079:RF-11 — mismo orden que elige al candidato: tarea y después datos."""
    medidas = iter([(.5, .5), (.5, .6)])
    monkeypatch.setattr(af, 'medir_seleccion', lambda *_a: next(medidas))
    assert _afinado()[0].afinado['mejor_epoca'] == 1


def test_afinado_mide_con_seleccion_nunca_con_otra(monkeypatch):
    """079:RF-11 — las filas son las de selección que trae la caché."""
    medidas = []
    original = af.medir_seleccion
    monkeypatch.setattr(af, 'medir_seleccion', lambda m, c: medidas.append(c.seleccion) or original(m, c))
    sel = _seleccion()
    _afinado(seleccion=sel)
    assert medidas and all(s is sel for s in medidas)


def test_afinado_sin_seleccion_no_afina():
    """079:RF-13 — sin selección no hay con qué parar."""
    with pytest.raises(ValueError, match='selección'):
        _afinado(seleccion=[])


def test_afinado_cada_entrenamiento_parte_del_original():
    """079:RF-14 — lo compartido no se toca: el segundo parte de los mismos pesos, y dos corridas con la misma semilla coinciden."""
    base = BaseFalsa()
    original = {k: v.clone() for k, v in base.tramo_original(2).state_dict().items()}
    uno, _b, _c = _afinado(base=base)
    assert all(torch.equal(v, original[k]) for k, v in base.tramo_original(2).state_dict().items())
    dos, _b, _c = _afinado(base=base)
    assert all(torch.equal(v, _tramo(uno)[k]) for k, v in _tramo(dos).items())
    assert uno.red.tramo is not dos.red.tramo


def test_afinado_el_original_real_no_se_toca(diminuto):
    """079:RF-14 — con el codificador real: copia con gradiente; el compartido sigue congelado e igual."""
    antes = {k: v.clone() for k, v in diminuto.red.state_dict().items()}
    tramo = diminuto.tramo_original(2)
    assert all(p.requires_grad for p in tramo.parameters())
    with torch.no_grad():
        for p in tramo.parameters():
            p.add_(1.)
    assert not any(p.requires_grad for p in diminuto.red.parameters())
    assert all(torch.equal(v, antes[k]) for k, v in diminuto.red.state_dict().items())


def test_afinado_recorre_el_tramo_en_cada_paso_sin_guardarlo():
    """079:RF-15 — un paso de tramo por lote, y en la caché solo hay lo congelado, igual antes y después."""
    base = BaseFalsa()
    cache = af.CachePrefijo(base, 2, _seleccion(), di.evaluar_alumno)
    cache.asegurar([e.texto for e in _pequeno()])
    antes = {t: f[0].clone() for t, f in cache.filas.items()}
    base.pasos_tramo = 0
    m = co.entrenar(_pequeno(), _cfg(), cache=cache, dispositivo=CPU)
    pasos = sum(x['pasos'] for x in m.afinado['epocas'])
    assert base.pasos_tramo >= pasos > 0
    assert all(torch.equal(f[0].float(), antes[t].float()) for t, f in cache.filas.items())
    # Lo guardado es el prefijo: el tramo afinado da otra cosa, y predecir pasa por él.
    t = 'convierte AB101'
    congelado = base.prefijo([t], 2).estados
    assert not torch.equal(m.codificador([t]).tokens[0], congelado[0])


def test_afinado_lo_congelado_una_vez_por_frase():
    """079:RF-16 — cada frase pasa una vez, aunque haya varios entrenamientos con la misma caché."""
    base = BaseFalsa()
    cache = af.CachePrefijo(base, 2, [{'texto': 'frase solo de seleccion', 'tarea': 'estado', 'datos': []}], di.evaluar_alumno)
    co.entrenar(_pequeno(), _cfg(), cache=cache, dispositivo=CPU)
    co.entrenar(_pequeno(), _cfg(semilla=3), cache=cache, dispositivo=CPU)
    cuenta = Counter(base.prefijos)
    assert all(cuenta[e.texto] == 1 for e in _pequeno())


def test_afinado_el_corte_da_lo_mismo_que_la_red_entera(diminuto):
    """079:RF-16 — prefijo y tramo original, con relleno, igual que ``red`` entera: si cambia ``transformers``, salta aquí."""
    textos = ['calibra AB101 con la maxima', 'hola', 'une AB101 y CD202 en un solo dgs por favor']
    entero = diminuto(textos)
    p = diminuto.prefijo(textos, 2)
    with torch.no_grad():
        h = diminuto.aplicar_tramo(diminuto.tramo_original(2).eval(), p.estados, p.atencion)
    oraciones, tokens = co.piezas_del_tramo(h, p.atencion, p.indices)
    assert torch.allclose(oraciones, entero.oraciones, atol=1e-5)
    assert all(torch.allclose(a, b, atol=1e-5) for a, b in zip(tokens, entero.tokens, strict=True))
    assert p.tramos == entero.tramos


def test_afinado_da_lo_medido_por_epoca():
    """079:RF-17 — pérdida, selección, tiempo y memoria de pico por época."""
    avisos = []
    base = BaseFalsa()
    co.entrenar(_pequeno(), _cfg(), avisos.append, cache=af.CachePrefijo(base, 2, _seleccion(), di.evaluar_alumno), dispositivo=CPU)
    m = _afinado()[0]
    assert {'epoca', 'perdida', 'pasos', 'macro_tarea', 'f1_datos', 'tiempo_s', 'memoria_pico_gb'} <= set(m.afinado['epocas'][0])
    assert any('época 0 de afinado' in a and 'GPU' in a for a in avisos)


# ------------------------------------------------------------------ artefacto

def test_artefacto_lleva_cabezas_y_tramo_con_sus_huellas(falso):
    """079:RF-18 / 079:RF-19 — sin el resto del codificador, y con nombre, revisión, capas y huellas."""
    m, _b, _c = _afinado()
    di._guardar_alumno(m, falso / 'alumno', {'version': 'alumno'})
    pesos = torch.load(falso / 'alumno' / 'pesos.pt', weights_only=True)
    assert any(k.startswith('tramo.') for k in pesos) and any(k.startswith('tarea.') for k in pesos)
    assert not [k for k in pesos if k.startswith(('embeddings', 'encoder'))]
    meta = json.loads((falso / 'alumno' / 'modelo.json').read_text(encoding='utf-8'))
    d = meta['codificador']
    assert meta['arquitectura'] == co.ARQUITECTURA_AFINADA
    assert d['nombre'] == co.NOMBRE_CODIFICADOR and d['revision'] == co.REVISION_CODIFICADOR
    assert d['tramo']['capas'] == 2 and d['tramo']['huella_congelada'] == 'congelada-2' and len(d['tramo']['huella']) == 32
    assert d['tramo']['parametros'] == sum(p.numel() for p in m.red.tramo.parameters())


def test_artefacto_huellas_que_no_coinciden_se_rechazan(falso, monkeypatch):
    """079:RF-20 — pesos del tramo tocados, o lo congelado de otra revisión."""
    monkeypatch.setattr(co, 'FABRICA', BaseFalsa)
    m, _b, _c = _afinado()
    di._guardar_alumno(m, falso / 'alumno', {'version': 'alumno'})
    meta = json.loads((falso / 'alumno' / 'modelo.json').read_text(encoding='utf-8'))
    pesos = torch.load(falso / 'alumno' / 'pesos.pt', weights_only=True)
    otros = {**pesos, 'tramo.0.weight': pesos['tramo.0.weight'] + 1}
    with pytest.raises(ValueError, match='huella del tramo'):
        co.modelo_desde(meta, otros, 'v', CPU)
    malo = {**meta, 'codificador': {**meta['codificador'], 'tramo': {**meta['codificador']['tramo'], 'huella_congelada': 'otra'}}}
    with pytest.raises(ValueError, match='capas congeladas'):
        co.modelo_desde(malo, pesos, 'v', CPU)


def test_artefacto_reabierto_predice_igual_en_el_mismo_proceso(falso, monkeypatch):
    """079:RF-21 / 079:RF-22 — mismas predicciones y mismos campos que 069:RF-2, con la regla si la lleva."""
    monkeypatch.setattr(co, 'FABRICA', BaseFalsa)
    m, _b, _c = _afinado(_cfg(afinar_epocas=4))
    m.puesto_charla, m.piso_charla, m.umbral, m.temperatura = 4, .3, .9, 1.5
    di._guardar_alumno(m, falso / 'alumno', {'version': 'alumno'})
    textos = ['convierte AB101', 'que hay cargado']
    ruta = falso / 'alumno' / 'readback.json'
    ruta.write_text(json.dumps({'textos': textos, 'predicciones': [m.predecir(t) for t in textos]}), encoding='utf-8')
    assert di.verificar_reapertura(falso / 'alumno')['ok']
    abierto = di.cargar_alumno(falso / 'alumno')
    assert isinstance(abierto.codificador, co.CodificadorAfinado)
    assert (abierto.puesto_charla, abierto.piso_charla, abierto.umbral, abierto.temperatura) == (4, .3, .9, 1.5)
    p = abierto.predecir(textos[0])
    assert set(p) == {'tarea', 'confianza', 'alternativas', 'datos', 'modelo', 'version'} and p['modelo'] == 'transformer'


def test_artefacto_heredados_y_sin_afinar_cargan_y_el_puntero_es_el_mismo(falso, monkeypatch):
    """079:RF-23 / 079:RF-24 — letra a letra, cabezas sin afinar y afinado, por el mismo puntero del registro."""
    monkeypatch.setattr(co, 'FABRICA', BaseFalsa)
    from convertersmartgrid.asistente import almacen, modelos_en_uso
    from convertersmartgrid.model_registry import RegistroModelo

    cfg = tr.Configuracion(dim=8, capas=1, cabezas=2, epocas=1)
    red = tr.construir_red(4, {'tarea': len(TAREAS)}, cfg, len(tr.ETIQUETAS))
    heredado = tr.guardar(tr.ModeloOrdenes(red, {'a': 3}, sorted(TAREAS), cfg), {})
    tr.promover(heredado, 'heredado')
    assert isinstance(tr.cargar(), tr.ModeloOrdenes)
    registro = RegistroModelo(almacen.raiz() / 'model_registry')

    def en_uso(modelo, nombre):
        di._guardar_alumno(modelo, falso / nombre, {'version': nombre})
        c = registro.registrar_candidato(
            'transformer', model_manifest={'algorithm': nombre}, dataset_manifest={}, metrics={},
            decision={'status': 'PROMOVIDO', 'gates': {'approved': True}, 'fallos': []}, smoke_reload={'ok': True},
            artifacts=[falso / nombre / 'pesos.pt', falso / nombre / 'modelo.json'])
        assert modelos_en_uso.aplicar_decision('transformer', c)['promovido']
        return tr.cargar()

    sin_afinar = en_uso(_entrenado(epocas=2), 'sin_afinar')
    assert isinstance(sin_afinar, co.ModeloCodificador) and not hasattr(sin_afinar.red, 'tramo') and sin_afinar.puesto_charla is None
    afinado = _afinado(_cfg(afinar_epocas=4))[0]
    abierto = en_uso(afinado, 'afinado')
    assert isinstance(abierto.codificador, co.CodificadorAfinado)
    assert abierto.predecir('convierte AB101')['tarea'] == afinado.predecir('convierte AB101')['tarea']


# ------------------------------------------------------------------ contrastiva

def test_contrastiva_separa_lo_que_se_confunde():
    """079:RF-25 — más pérdida con tareas parecidas juntas; sus gradientes llegan; y sin pares no aporta, sin NaN."""
    tareas = ['calibrar', 'recalibrar', 'estado', NINGUNA]
    parecidas = af.tareas_parecidas(tareas)
    y = torch.tensor([0, 0, 1, 1])
    juntas = torch.nn.functional.normalize(torch.tensor([[1., 0.], [1., .01], [1., .02], [1., .03]]), dim=-1).requires_grad_()
    separadas = torch.nn.functional.normalize(torch.tensor([[1., 0.], [1., .01], [0., 1.], [.01, 1.]]), dim=-1)
    alta = af.perdida_contrastiva(juntas, y, parecidas, .1)
    assert alta > af.perdida_contrastiva(separadas, y, parecidas, .1)
    alta.backward()
    assert juntas.grad.abs().sum() > 0
    sola = af.perdida_contrastiva(juntas, torch.tensor([0, 1, 2, 3]), parecidas, .1)
    assert float(sola.detach()) == 0. and torch.isfinite(sola)


def test_contrastiva_no_mira_tareas_que_no_se_parecen():
    """079:RF-25 — `flujo` y `pide` no se contrastan: no están en el mismo grupo."""
    tareas = ['flujo', 'pide']
    y = torch.tensor([0, 0, 1, 1])
    o = torch.nn.functional.normalize(torch.randn(4, 3), dim=-1)
    assert float(af.perdida_contrastiva(o, y, af.tareas_parecidas(tareas), .1)) == 0.


def test_contrastiva_grupos_del_catalogo():
    """079:RF-26 — los cuatro grupos declarados, con tareas que existen y sin repetir ninguna."""
    planos = [t for g in af.GRUPOS_PARECIDOS for t in g]
    assert set(planos) <= set(TAREAS) and len(planos) == len(set(planos))
    assert {'calibrar', 'recalibrar', 'simular_calibracion', 'sistema_completo'} == set(af.GRUPOS_PARECIDOS[0])
    assert {'escanear', 'verificar_caso_base', 'verificar_convergencia'} == set(af.GRUPOS_PARECIDOS[1])
    assert {'convertir', 'unir', 'convertir_sistema', 'convertir_set'} == set(af.GRUPOS_PARECIDOS[2])
    assert {'no_disponible', 'estudios'} == set(af.GRUPOS_PARECIDOS[3])


def test_contrastiva_ninguna_se_parece_a_todas():
    """079:RF-27 — con toda tarea, sin incluirse a sí misma."""
    tareas = co.tareas_del_modelo()
    m = af.tareas_parecidas(tareas)
    i = tareas.index(NINGUNA)
    assert m[i, [j for j in range(len(tareas)) if j != i]].all() and not m[i, i]
    a, b = tareas.index('calibrar'), tareas.index('recalibrar')
    assert m[a, b] and m[b, a] and not m[a, tareas.index('flujo')]


def test_contrastiva_cada_lote_lleva_su_grupo():
    """079:RF-28 — filas del grupo que toca y de `ninguna`, con dos de cada tarea para tener pares."""
    tareas = (['calibrar'] * 50 + ['recalibrar'] * 50 + ['simular_calibracion'] * 50 + ['sistema_completo'] * 50 + ['escanear'] * 50
              + ['verificar_caso_base'] * 50 + ['verificar_convergencia'] * 50 + [NINGUNA] * 50 + ['flujo'] * 1000)
    cfg = co.Configuracion(afinar_capas=2, afinar_lote=32, afinar_piezas=10 ** 6, pasos_por_epoca=8)
    lotes = af.lotes_de_epoca(tareas, [10] * len(tareas), cfg, random.Random(4))
    primero = Counter(tareas[i] for i in lotes[0])
    assert all(primero[t] >= 2 for t in af.GRUPOS_PARECIDOS[0]) and primero[NINGUNA] >= 2
    segundo = Counter(tareas[i] for i in lotes[1])
    assert all(segundo[t] >= 2 for t in af.GRUPOS_PARECIDOS[1]) and segundo[NINGUNA] >= 2


def test_contrastiva_confusiones_solo_cuentas():
    """079:RF-29 — pares de tareas ordenados, sin ningún texto."""
    class Doble:
        def predecir(self, texto):
            return {'tarea': 'recalibrar' if 'x' in texto else 'calibrar'}
    filas = [{'texto': 'x uno', 'tarea': 'calibrar'}, {'texto': 'x dos', 'tarea': 'calibrar'}, {'texto': 'y', 'tarea': 'calibrar'}]
    salida = af.confusiones(Doble(), filas)
    assert salida == [{'esperada': 'calibrar', 'predicha': 'recalibrar', 'filas': 2}]


def test_contrastiva_no_depende_de_ninguna_prueba():
    """079:RF-30 / 079:RF-37 — el afinado y el currículo no leen selladas, filas humanas ni el almacén."""
    for fichero in (af.__file__, cm.__file__):
        texto = Path(fichero).read_text(encoding='utf-8')
        assert not re.search(r'^\s*(from|import) .*(prueba_sellada|maestro_real import leer|almacen)', texto, re.M), fichero
        assert 'ejemplos.jsonl' not in texto.replace('`ejemplos.jsonl`', '')


# ------------------------------------------------------------------ currículo

def test_curriculo_solo_entrena_y_marca_su_origen(corpus):
    """079:RF-31 / 079:RF-32 — solo a entrenamiento, con su origen, y el manifiesto da sus cuentas."""
    filas, meta = corpus
    nuevas = [r for r in filas if r.get('origen_curriculo') == 'parafrasis_079']
    assert nuevas and {r['particion'] for r in nuevas} == {'entrenamiento'}
    assert {r['tarea'] for r in nuevas} == set(cm.PARAFRASIS_079)
    assert meta['parafrasis_079']['filas'] == len(nuevas) and meta['parafrasis_079']['maestro'] == cm.MAESTRO_079
    assert all(r['maestro'] == 'claude' and r['del_maestro'] for r in nuevas)


def test_curriculo_al_menos_diez_por_tarea_floja():
    """079:RF-33 — las seis tareas flojas declaradas, con 10 o más frases distintas."""
    flojas = {'calibrar', 'no_disponible', 'escanear', 'descargar_resultados', 'verificar_caso_base', 'simular_calibracion'}
    assert set(cm.PARAFRASIS_079) == flojas
    assert all(len(set(v)) >= 10 for v in cm.PARAFRASIS_079.values())


def _expandidas():
    salida = {}
    for tarea, frases in cm.PARAFRASIS_079.items():
        for p in frases:
            salida[p] = expandir(p, tarea, random.Random(1), VOCAB)
    return salida


def test_curriculo_no_toca_lo_que_mide(corpus):
    """079:RF-34 — ni por texto ni por familia exacta con selección, calibración o una prueba: ninguna frase se pierde por fuga."""
    filas, meta = corpus
    assert meta['parafrasis_079']['excluidas_por_fuga'] == 0
    apartadas = [r for r in filas if r['particion'] != 'entrenamiento']
    textos = {clave_texto(r['texto']) for r in apartadas}
    familias = {firma_familia(r['texto'], r['datos']) for r in apartadas}
    for r in (r for r in filas if r.get('origen_curriculo') == 'parafrasis_079'):
        assert clave_texto(r['texto']) not in textos and firma_familia(r['texto'], r['datos']) not in familias


def test_curriculo_no_se_parece_ni_con_la_familia_ancha(corpus):
    """079:RF-34 — con la familia más ancha de la 075, frente a selección, calibración y las dos selladas; solo se comparan cuentas."""
    filas, _ = corpus
    medido = vc.Claves(vc.clave_de_familia(r['texto'], r['datos']) for r in filas
                       if r['particion'] in ('seleccion', 'calibracion') or r.get('conjunto'))
    parecidas = [p for p, e in _expandidas().items() if medido.toca(vc.clave_de_familia(e.texto, e.datos))]
    assert not parecidas, parecidas


def test_curriculo_una_frase_que_choca_no_entrena(monkeypatch):
    """079:RF-34 — si una frase coincide con lo apartado, no entra y se cuenta."""
    monkeypatch.setitem(di.PARAFRASIS_079, 'estado', (cm.FAMILIAS['estado'][1],))    # la plantilla de selección
    _, despues = di.preparar_corpus(VOCAB, [], por_familia=12)
    assert despues['parafrasis_079']['excluidas_por_fuga'] >= 1


def test_curriculo_deja_identicas_las_huellas(monkeypatch, corpus):
    """079:RF-35 / 079:RF-36 — fijas, histórica, selección y calibración, iguales con y sin el currículo nuevo."""
    filas, meta = corpus
    assert of.huella(of.generar({})) == '41f7ab110ac35c0b'
    monkeypatch.setattr(di, 'PARAFRASIS_079', {})
    sin, meta_sin = di.preparar_corpus(VOCAB, [], por_familia=4)
    assert meta['prueba_historica'] == meta_sin['prueba_historica']
    for parte in ('seleccion', 'calibracion'):
        a = sorted(r['record_id'] for r in filas if r['particion'] == parte)
        assert a and a == sorted(r['record_id'] for r in sin if r['particion'] == parte)
    assert meta['dataset_hash'] != meta_sin['dataset_hash'] and meta['curriculo_hash'] != meta_sin['curriculo_hash']


# ------------------------------------------------------------------ regla de Ollama

class DudaFija:
    """Un modelo que da, por texto, su confianza y el puesto de `ninguna`."""
    umbral = .9
    puesto_charla = None
    piso_charla = 0.

    def __init__(self, casos):
        self.casos = casos

    def predecir(self, texto):
        conf, _puesto = self.casos[texto]
        return {'tarea': 'estado', 'confianza': conf, 'alternativas': [], 'datos': {}, 'modelo': 'transformer', 'version': 'v'}

    def puesto_ninguna(self, texto):
        return self.casos[texto][1]


def _rejilla_con(charla, ordenes):
    casos = {**{f'c{i}': c for i, c in enumerate(charla)}, **{f'o{i}': o for i, o in enumerate(ordenes)}}
    return DudaFija(casos), [f'c{i}' for i in range(len(charla))], [{'texto': f'o{i}'} for i in range(len(ordenes))]


def test_regla_rejilla_declarada():
    """079:RF-50 — los puestos y pisos de la spec, y el primero es el de la 075."""
    assert di.PUESTOS_CHARLA == (2, 3, 4, 5) and di.PISOS_CHARLA == (0., .3, .5) and PUESTO_CHARLA == 2


def test_regla_elige_la_que_cumple_y_menos_frena():
    """079:RF-51 / 079:RF-52 / 079:RF-54 — sube a 3 solo porque hace falta, y se guarda en el modelo."""
    charla = [(.5, 3)] * 9 + [(.99, 9)] * 191
    ordenes = [(.99, 9)] * 900 + [(.5, 3)] * 40 + [(.5, 9)] * 60
    m, reservados, seleccion = _rejilla_con(charla, ordenes)
    r = di.elegir_regla_charla(m, seleccion, reservados)
    assert r['elegida']['puesto'] == 3 and r['elegida']['piso'] == 0. and r['cumple'] is True
    assert (m.puesto_charla, m.piso_charla) == (3, 0.)
    assert r['ollama_consultado'] is False and len(r['rejilla']) == 12


def test_regla_el_piso_tambien_cuenta():
    """079:RF-50 / 079:RF-52 — si el puesto no basta y el piso sí, se elige por el piso."""
    charla = [(.2, 9)] * 9 + [(.99, 9)] * 191
    ordenes = [(.99, 9)] * 980 + [(.6, 9)] * 20
    m, reservados, seleccion = _rejilla_con(charla, ordenes)
    r = di.elegir_regla_charla(m, seleccion, reservados)
    assert r['elegida']['piso'] == .3 and r['elegida']['puesto'] == 2 and r['cumple'] is True


def test_regla_sin_ninguna_que_cumpla_lo_dice():
    """079:RF-53 — sin pasar de 0,05 de frenadas, la que menos deja llegar; y dice que no cumple."""
    charla = [(.8, 9)] * 9 + [(.5, 3)] * 9 + [(.99, 9)] * 182
    ordenes = [(.99, 9)] * 960 + [(.5, 3)] * 40
    m, reservados, seleccion = _rejilla_con(charla, ordenes)
    r = di.elegir_regla_charla(m, seleccion, reservados)
    assert r['cumple'] is False and r['elegida']['ordenes_frenadas'] <= .05 and r['elegida']['reservados_a_ollama'] == 9 / 200


def test_regla_sin_admisible_queda_la_de_la_075():
    """079:RF-53 — si todas frenan de más, no se empeora: la primera de la rejilla, que es la de la 075, y no cumple."""
    m, reservados, seleccion = _rejilla_con([(.5, 1)] * 10, [(.5, 1)] * 10)
    r = di.elegir_regla_charla(m, seleccion, reservados)
    assert r['cumple'] is False and (r['elegida']['puesto'], r['elegida']['piso']) == (2, 0.)


def test_regla_sin_mensajes_no_elige():
    """079:RF-51 — sin mensajes reservados no hay medida y no se elige nada."""
    m = DudaFija({})
    assert di.elegir_regla_charla(m, [], None) is None and m.puesto_charla is None


class OllamaEspia:
    modelo = 'doble'
    revisar_transformer = False

    def __init__(self):
        self.llamadas = 0

    def interpretar(self, _texto, **_k):
        self.llamadas += 1
        return {'tarea': 'estado', 'confianza': 1., 'datos': {}, 'modelo': 'ollama'}


@pytest.mark.parametrize('puesto, confianza, regla, consulta', [
    (3, .5, (3, 0.), False),     # 079:RF-55: la regla del modelo frena donde la fija no
    (4, .5, (3, 0.), True),      # fuera de la regla, se consulta
    (9, .2, (2, .3), False),     # bajo el piso, tampoco
    (9, .4, (2, .3), True),
])
def test_regla_el_interprete_usa_la_del_modelo(puesto, confianza, regla, consulta):
    """079:RF-55 — frena por el puesto o por el piso que trae el modelo, sin consultar a Ollama."""
    m = DudaFija({'muchas gracias': (confianza, puesto)})
    m.puesto_charla, m.piso_charla = regla
    o = OllamaEspia()
    i = interpretar('muchas gracias', transformer=m, ollama=o)
    assert (o.llamadas == 1) is consulta
    if not consulta:
        assert i.tarea is None and any('sin Ollama' in c for c in i.consultados)


def test_regla_sin_regla_la_de_la_075():
    """079:RF-56 — sin regla en el modelo, `ninguna` en tercer lugar se consulta y en segundo no."""
    tercero, segundo = DudaFija({'a': (.5, 3)}), DudaFija({'a': (.5, 2)})
    o = OllamaEspia()
    interpretar('a', transformer=tercero, ollama=o)
    assert o.llamadas == 1
    interpretar('a', transformer=segundo, ollama=o)
    assert o.llamadas == 1
    assert charla_cerca(DudaFija({'a': (.5, 2)}), 'a') and not charla_cerca(DudaFija({'a': (.5, 3)}), 'a')


# ------------------------------------------------------------------ una corrida entera con dobles

CONFIRMADAS = [('cuentame lo que tienes cargado', 'estado'), ('muestrame el resumen del espacio', 'estado'),
               ('exporta la red zeta', 'convertir'), ('genera el fichero para pasarlo', 'convertir'),
               ('lanza potencia sobre todo', 'flujo'), ('calcula el reparto de cargas', 'flujo'),
               ('dime tus proyectos importados', 'proyectos'), ('a ver que tienes abierto', 'estado')]


@pytest.fixture(scope='module')
def corrida(tmp_path_factory):
    """El protocolo entero, con afinado y validación cruzada; una sola vez porque tarda."""
    import convertersmartgrid.model_registry as mr
    raiz = tmp_path_factory.mktemp('afinado')
    parche = pytest.MonkeyPatch()
    parche.setenv('CSG_ASISTENTE_DATA', str(raiz / 'almacen'))
    parche.setattr(co, 'FABRICA', BaseFalsa)
    parche.setattr(co, '_abiertos', {})
    parche.setattr(tr, 'dispositivo_de_calculo', lambda: CPU)
    parche.setattr(tr, 'liberar_gpu', lambda: None)
    parche.setattr(tr, '_cache', {})
    parche.setattr(mr, 'reabrir_en_subproceso', lambda *_a, **_k: {'ok': True})
    aperturas = []
    original = BaseFalsa.tramo_original
    parche.setattr(BaseFalsa, 'tramo_original', lambda self, capas: aperturas.append(capas) or original(self, capas))
    humanas = [{'texto': t, 'tarea': tarea, 'datos': [], 'origen': 'confirmado'} for t, tarea in CONFIRMADAS]
    reservados = [f'secreto reservado {i}' for i in range(120)]
    filas, meta = di.preparar_corpus({}, humanas, por_familia=1, ninguna=['charla uno de mas', 'charla dos de mas'], ninguna_reservada=reservados)
    di.guardar_corpus(raiz / 'corpus', filas, meta, reservados)
    cfg = _cfg(afinar_epocas=1, pasos_por_epoca=3, afinar_lote=8, afinar_piezas=400, epocas=1)
    try:
        r = di.entrenar_destilacion(raiz / 'corpus', raiz / 'run', cfg=cfg, semillas=(11,), registro=raiz / 'reg', log=lambda *_a, **_k: None,
                                    validacion_cruzada=True)
        meta_final = json.loads((raiz / 'run' / 'alumno' / 'modelo.json').read_text(encoding='utf-8'))
        protocolo = json.loads((raiz / 'run' / 'protocolo.json').read_text(encoding='utf-8'))
        registrados = ''.join(p.read_text(encoding='utf-8') for p in (raiz / 'reg').rglob('*.json'))
        yield {'r': r, 'filas': filas, 'meta': meta, 'final': meta_final, 'protocolo': protocolo, 'aperturas': aperturas, 'registrados': registrados,
               'humanas': humanas}
    finally:
        parche.undo()


def test_cruzada_cada_vuelta_afina_desde_el_original(corrida):
    """079:RF-49 / 079:RF-14 — dos candidatos, cinco vueltas y el final, cada uno con su tramo original; y el final se reabre."""
    assert corrida['r']['validacion_cruzada']['medida'] is True
    assert len(corrida['r']['validacion_cruzada']['vueltas']) == 5
    # 2 candidatos, 5 vueltas y 1 final; más las reaperturas de cada modelo guardado.
    assert len(corrida['aperturas']) >= 8
    assert corrida['final']['arquitectura'] == co.ARQUITECTURA_AFINADA


def test_cruzada_decide_la_nueva_con_las_puertas_de_siempre(corrida):
    """079:RF-45 / 079:RF-46 / 079:RF-47 / 079:RF-48 — decide `sellada_079`; la anterior se mide sin decidir, y las dos se informan."""
    r, filas = corrida['r'], corrida['filas']
    decisora = sum(x.get('conjunto') == ps.CONJUNTO for x in filas)
    assert r['sinteticas']['ejemplos'] == decisora
    assert r['prueba_sellada_079']['huella'] == ps.HUELLA and r['prueba_sellada_079']['decide'] is True
    assert r['prueba_sellada']['huella'] == anterior.HUELLA and r['prueba_sellada']['decide'] is False
    assert r['prueba_sellada']['medida']['ejemplos'] == sum(x.get('conjunto') == anterior.CONJUNTO for x in filas)
    assert '"prueba_sellada_079"' in corrida['registrados'] and anterior.HUELLA in corrida['registrados']
    politica = dict(di.PoliticaEvaluacion(modo='agente').puertas_por_familia)
    assert politica == {'acierto_tarea': .95, 'f1_datos': .85}
    assert (di.RECHAZO_MINIMO, di.SE_CUELA_MAXIMO) == (.90, .02)
    assert r['humanas']['ejemplos'] == len(corrida['humanas'])


def test_cruzada_humanas_bajo_puerta_rechaza():
    """079:RF-48 — 0,98 y 0,95 humanas, sin excepción."""
    familias = {t: {'acierto_tarea': 1., 'f1_datos': 1., 'ejemplos': 5} for t in TAREAS}
    perfecto = {'ejemplos': 200, 'acierto_tarea': 1., 'f1_datos': 1.}
    for malo in ({'acierto_tarea': .979}, {'f1_datos': .949}):
        d = di.decidir_promocion(perfecto, {**perfecto, **malo}, familias, familias, {'ejemplos': 200, 'rechazada': .95, 'se_cuela': .01})
        assert d['status'] == 'RECHAZADO' and any('humana' in f for f in d['fallos'])


def test_cruzada_regla_en_el_informe_sin_decidir(corrida):
    """079:RF-54 / 079:RF-57 — la rejilla medida se informa con `decide` falso, y la elegida va en el modelo."""
    r = corrida['r']
    assert r['regla_elegida']['decide'] is False and len(r['regla_elegida']['rejilla']) == 12
    elegida = r['regla_elegida']['elegida']
    assert corrida['final']['regla_charla'] == {'puesto': elegida['puesto'], 'piso': elegida['piso']}
    assert r['regla_ollama']['decide'] is False and str(elegida['puesto']) in r['regla_ollama']['regla']
    assert not any('regla' in f or 'Ollama' in f for f in r['decision']['fallos'])


def test_cruzada_confusiones_solo_de_desarrollo(corrida):
    """079:RF-29 / 079:RF-30 — en selección y calibración; ninguna medida de confusión sobre una prueba."""
    assert set(corrida['r']['confusiones']) == {'seleccion', 'calibracion'}


def test_cruzada_sin_textos_en_el_informe_ni_el_registro(corrida):
    """079:RF-64 — ni una orden confirmada, ni un mensaje reservado, ni una frase de una prueba."""
    salida = json.dumps(corrida['r'], ensure_ascii=False, default=str)
    for texto in (corrida['registrados'], salida):
        assert 'secreto reservado' not in texto
        assert not [t for t, _ in CONFIRMADAS if t in texto]
        assert not [r['texto'] for r in corrida['filas'] if r.get('conjunto') and r['texto'] in texto]


def test_herramienta_protocolo_antes_de_entrenar(corrida):
    """079:RF-63 — capas, tasas, lotes, grupos y rejilla en el protocolo."""
    p = corrida['protocolo']
    assert p['afinado']['afinar_capas'] == 2 and p['afinado']['lr_tramo'] == 1e-2 and p['afinado']['afinar_lote'] == 8
    assert p['afinado']['grupos_parecidos'][0][0] == 'calibrar'
    assert p['regla_charla'] == {'puestos': [2, 3, 4, 5], 'pisos': [0., .3, .5]}
    assert {'afinado_ordenes.py', 'prueba_sellada_079.py'} <= set(p['codigo_hashes'])


def _herramienta():
    especificacion = importlib.util.spec_from_file_location('asistente_entrenar_079', RAIZ / 'tools/asistente_entrenar.py')
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def test_herramienta_opcion_lleva_las_capas(monkeypatch, tmp_path):
    """079:RF-61 — con su opción y la cruzada, llega a la configuración; sin ella, cero capas (079:RF-2)."""
    llamadas = []

    def entrenar(*_a, cfg, validacion_cruzada, **_k):
        llamadas.append((cfg, validacion_cruzada))
        raise RuntimeError('parada aquí: no se entrena en las pruebas')
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))                  # no el turno real, por si otro entrena
    monkeypatch.setattr(di, 'entrenar_destilacion', entrenar)
    herramienta = _herramienta()
    salida = tmp_path / 'a.json'
    assert herramienta.main(['--output-json', str(salida), '--integral', '--afinar', '--afinar-capas', '3', '--afinar-lote', '16', '--validacion-cruzada']) == 2
    salida2 = tmp_path / 'b.json'
    assert herramienta.main(['--output-json', str(salida2), '--integral']) == 2
    (con, cruzada), (sin, _) = llamadas
    assert con.afinar_capas == 3 and con.afinar_lote == 16 and cruzada is True and sin.afinar_capas == 0
    assert 'no se entrena' in json.loads(salida.read_text(encoding='utf-8'))['error']


@pytest.mark.parametrize('resto', [['--dataset-v2', 'x', '--solo', 'ordenes'], ['--evaluar'], ['--solo', 'informes']])
def test_herramienta_fuera_de_la_via_integral_se_rechaza(tmp_path, resto, capsys):
    """079:RF-62 — --afinar solo con la vía integral."""
    with pytest.raises(SystemExit):
        _herramienta().main(['--output-json', str(tmp_path / 'a.json'), '--afinar', *resto])
    assert '--afinar solo vale con --integral' in capsys.readouterr().err


# ------------------------------------------------------------------ caché local y proceso nuevo

GUION_ENTRENA = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import torch
from convertersmartgrid.asistente import afinado_ordenes as af, codificador_ordenes as co, destilacion_integral as di
from convertersmartgrid.asistente.sinteticos import Ejemplo
CPU = torch.device('cpu')
filas = [Ejemplo(f'convierte {c}', 'convertir', [(10, 15, 'alimentadores')]) for c in ('AB101', 'CD202', 'EF303')]
filas += [Ejemplo(f'flujo de {c}', 'flujo', [(9, 14, 'alimentadores')]) for c in ('AB101', 'CD202', 'EF303')]
base = co.obtener_codificador(co.NOMBRE_CODIFICADOR, co.REVISION_CODIFICADOR, CPU)
cfg = co.Configuracion(afinar_capas=1, afinar_epocas=1, pasos_por_epoca=3, afinar_lote=4, oculta_tarea=8, oculta_etiquetas=8)
sel = [{'texto': e.texto, 'tarea': e.tarea, 'datos': [list(d) for d in e.datos]} for e in filas[:2]]
m = co.entrenar(filas, cfg, cache=af.CachePrefijo(base, 1, sel, di.evaluar_alumno), dispositivo=CPU)
m.temperatura, m.umbral = 1.5, .9
di._guardar_alumno(m, __import__('pathlib').Path(sys.argv[2]), {'version': 'alumno'})
print(json.dumps([m.predecir(t) for t in ('convierte ZZ909', 'flujo de ZZ909')]))
'''
GUION_REABRE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import torch
from pathlib import Path
from convertersmartgrid.asistente import codificador_ordenes as co
c = Path(sys.argv[2])
m = co.modelo_desde(json.loads((c / 'modelo.json').read_text(encoding='utf-8')),
                    torch.load(c / 'pesos.pt', weights_only=True, map_location='cpu'), 'alumno', torch.device('cpu'))
print(json.dumps([m.predecir(t) for t in ('convierte ZZ909', 'flujo de ZZ909')]))
'''


def _instantanea(hf_home: Path) -> None:
    """Una revisión diminuta con el nombre y la revisión del codificador, en la forma de la caché de Hugging Face."""
    from tokenizers import Tokenizer, models, pre_tokenizers
    from transformers import PreTrainedTokenizerFast, XLMRobertaConfig, XLMRobertaModel

    carpeta = hf_home / 'hub' / f"models--{co.NOMBRE_CODIFICADOR.replace('/', '--')}"
    instantanea = carpeta / 'snapshots' / co.REVISION_CODIFICADOR
    instantanea.mkdir(parents=True)
    (carpeta / 'refs').mkdir()
    (carpeta / 'refs' / 'main').write_text(co.REVISION_CODIFICADOR, encoding='utf-8')
    torch.manual_seed(5)
    cfg = XLMRobertaConfig(vocab_size=64, hidden_size=16, num_hidden_layers=3, num_attention_heads=2, intermediate_size=16,
                           max_position_embeddings=128, pad_token_id=0)
    XLMRobertaModel(cfg).save_pretrained(instantanea)
    vocabulario = {'<pad>': 0, '<unk>': 1, **{p: i + 2 for i, p in enumerate('query : convierte flujo de AB101 CD202 EF303 ZZ909'.split())}}
    t = Tokenizer(models.WordLevel(vocabulario, unk_token='<unk>'))
    t.pre_tokenizer = pre_tokenizers.Whitespace()
    PreTrainedTokenizerFast(tokenizer_object=t, pad_token='<pad>', unk_token='<unk>').save_pretrained(instantanea)


def _proceso(guion: str, hf_home: Path, *argumentos: str) -> subprocess.CompletedProcess:
    entorno = {**os.environ, 'HF_HOME': str(hf_home), 'CUDA_VISIBLE_DEVICES': '', 'HF_HUB_OFFLINE': '1', 'PYTHONIOENCODING': 'utf-8'}
    entorno.pop('HF_HUB_CACHE', None)
    entorno.pop('TRANSFORMERS_CACHE', None)
    return subprocess.run([sys.executable, '-c', guion, str(RAIZ / 'src'), *argumentos], capture_output=True, text=True, encoding='utf-8',
                          env=entorno, timeout=300, check=False)


def test_cache_reabierto_en_proceso_nuevo_predice_igual(tmp_path):
    """079:RF-21 / 079:RF-58 — entrena en un proceso y reabre en otro, leyendo solo del `HF_HOME` que señala el entorno, sin red."""
    hf = tmp_path / 'hf_administrada'
    _instantanea(hf)
    entrena = _proceso(GUION_ENTRENA, hf, str(tmp_path / 'alumno'))
    assert entrena.returncode == 0, entrena.stderr[-1500:]
    reabre = _proceso(GUION_REABRE, hf, str(tmp_path / 'alumno'))
    assert reabre.returncode == 0, reabre.stderr[-1500:]
    primero = json.loads(entrena.stdout.strip().splitlines()[-1])
    segundo = json.loads(reabre.stdout.strip().splitlines()[-1])
    assert [p['tarea'] for p in primero] == [p['tarea'] for p in segundo]
    assert [p['datos'] for p in primero] == [p['datos'] for p in segundo]
    assert all(abs(a['confianza'] - b['confianza']) < 1e-6 for a, b in zip(primero, segundo, strict=True))
    # El artefacto lleva el tramo y no el resto del codificador: el modelo entero en esta escala pesa más.
    pesos = torch.load(tmp_path / 'alumno' / 'pesos.pt', weights_only=True)
    assert any(k.startswith('tramo.0.') for k in pesos) and not any('embeddings' in k for k in pesos)


def test_cache_sin_la_revision_nombra_la_orden(tmp_path):
    """079:RF-58 / 079:RF-59 — con otro `HF_HOME` vacío no usa la red: dice qué falta y cómo se prepara."""
    r = _proceso(GUION_REABRE.replace("m = co.modelo_desde", "m = co.CodificadorPreentrenado(co.NOMBRE_CODIFICADOR, co.REVISION_CODIFICADOR, torch.device('cpu'))\nm = co.modelo_desde"),
                 tmp_path / 'hf_vacia', str(tmp_path))
    assert r.returncode != 0
    for texto in (co.NOMBRE_CODIFICADOR, co.REVISION_CODIFICADOR, 'preparar_modelos_ia.py', '--id'):
        assert texto in r.stderr, texto


def test_cache_se_pide_sin_red_y_sin_carpeta_propia(monkeypatch):
    """079:RF-58 — `local_files_only` y ningún `cache_dir`: manda el entorno del proceso, administrado o del usuario."""
    pedidos = []

    def fallar(nombre, **kw):
        pedidos.append(kw)
        raise OSError('no está')
    falsa = types.SimpleNamespace(AutoModel=types.SimpleNamespace(from_pretrained=fallar), AutoTokenizer=types.SimpleNamespace(from_pretrained=fallar))
    monkeypatch.setitem(sys.modules, 'transformers', falsa)
    with pytest.raises(RuntimeError, match='preparar_modelos_ia'):
        co.CodificadorPreentrenado(co.NOMBRE_CODIFICADOR, co.REVISION_CODIFICADOR, CPU)
    assert pedidos == [{'revision': co.REVISION_CODIFICADOR, 'local_files_only': True}]
