"""Spec 026, T5: intérprete híbrido y plan con los datos contrastados."""
from __future__ import annotations

from igea_dgs.asistente.interprete import interpretar, periodo_de
from igea_dgs.asistente.plan import parecido, resolver

VOCAB = {'alimentadores': ['IN111', 'TA225', 'PA217'], 'proyecto': ['20261015-170359_IGEA_IN111_TA225', 'CA101 13'],
         'sistema': ['Pisco', 'Ica']}


class Transformer:
    def __init__(self, tarea, confianza, datos=None):
        self.r = {'tarea': tarea, 'confianza': confianza, 'datos': datos or {}, 'alternativas': [('estado', 0.1)],
                  'version': 'v1'}

    def predecir(self, _texto):
        return self.r


class Ollama:
    modelo = 'qwen2.5:3b'

    def __init__(self, r):
        self.r, self.llamadas = r, 0

    def interpretar(self, _texto):
        self.llamadas += 1
        return self.r


def _d(*valores):
    return [{'valor': v, 'confianza': 0.9} for v in valores]


def test_primero_el_transformer():
    """026:RF-2 — con confianza suficiente decide el Transformer y no se consulta a Ollama."""
    o = Ollama(None)
    i = interpretar('convierte in111 y ta225', transformer=Transformer('convertir', 0.97,
                                                                       {'alimentadores': _d('in111 y ta225')}), ollama=o)
    assert i.tarea == 'convertir' and i.modelo == 'transformer' and o.llamadas == 0


def test_si_duda_pregunta_a_ollama():
    """026:RF-3 — si el Transformer duda, decide el modelo local de Ollama."""
    o = Ollama({'tarea': 'pide', 'confianza': 0.8, 'datos': {'proyecto': _d('CA101 13')}, 'modelo': 'ollama:qwen2.5:3b',
                'razon': 'plan de inversiones'})
    i = interpretar('el plan de inversiones de CA101 13', transformer=Transformer('estado', 0.4), ollama=o)
    assert i.tarea == 'pide' and i.modelo.startswith('ollama') and o.llamadas == 1


def test_si_nadie_entiende_no_se_ejecuta_nada():
    """026:RF-4 — sin confianza suficiente, el plan no tiene tarea y pide aclararla."""
    i = interpretar('xyzzy', transformer=Transformer('estado', 0.3), ollama=Ollama(None))
    plan = resolver(i, VOCAB)
    assert plan.tarea is None and not plan.listo and 'no entendí' in plan.faltan[0]


def test_contrasta_los_datos_con_lo_que_existe():
    """026:RF-6 — erratas reconocidas por parecido, nombres inexistentes fuera y con aviso, datos
    que el modelo no marcó tomados del texto, rutas inexistentes rechazadas."""
    i = interpretar('convierte in11 y XX999', transformer=Transformer('convertir', 0.99,
                                                                     {'alimentadores': _d('in11 y XX999')}))
    plan = resolver(i, VOCAB)
    assert plan.datos['alimentadores'] == ['IN111'] and any('XX999' in d for d in plan.dudas)
    i = interpretar('haz el pide de 20261015-170359_IGEA_IN111_TA225 para TA225', transformer=Transformer('pide', 0.99))
    plan = resolver(i, VOCAB)
    assert plan.datos['proyecto'] == '20261015-170359_IGEA_IN111_TA225' and plan.datos['alimentadores'] == ['TA225']
    i = interpretar('integra las cargas de "D:/no/existe.xlsx" en CA101 13 PA217',
                    transformer=Transformer('cargas_nuevas', 0.99))
    plan = resolver(i, VOCAB)
    assert 'ruta: Excel de cargas nuevas' in plan.faltan and any('no existe' in d for d in plan.dudas)
    assert parecido('pisko', VOCAB['sistema'], 0.75) == 'Pisco'


def test_periodos_y_razonamiento():
    """026:RF-7 — el plan dice qué entendió, con qué modelo y de dónde sale cada dato; el periodo
    se normaliza a AAAA-MM o AAAA."""
    assert periodo_de('julio de 2026') == '2026-07' and periodo_de('2025') == '2025'
    assert periodo_de('el 2026-7') == '2026-07' and periodo_de('nada') is None
    i = interpretar('calibra el sistema pisko con julio de 2026', transformer=Transformer(
        'sistema_completo', 0.99, {'sistema': _d('pisko')}))
    plan = resolver(i, VOCAB)
    assert plan.listo and plan.datos == {'sistema': 'Pisco', 'periodo': '2026-07'}
    texto = ' '.join(plan.razonamiento)
    assert 'Transformer' in texto and 'Pisco' in texto and '2026-07' in texto and 'confirmación' in texto
