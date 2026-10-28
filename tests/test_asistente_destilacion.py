"""Spec 027, T25: destilación del modelo local de Ollama al Transformer de órdenes.

El maestro es falso (sin Ollama en la suite): interpreta cada orden con la tarea de la plantilla
de donde salió, con un voto equivocado al azar, como un modelo con temperatura. Lo que hace el
Ollama de verdad se mide aparte, en esta máquina (Hecho cuando de T25).
"""
from __future__ import annotations

import random

import pytest

from igea_dgs.asistente import almacen
from igea_dgs.asistente import destilacion as dst
from igea_dgs.asistente.sinteticos import generar
from igea_dgs.asistente.tareas import TAREAS

SEMILLA = random.randrange(1 << 30)
VOCAB = {'alimentadores': ['IN111', 'TA225', 'NA203'], 'proyecto': ['CA101 13'], 'sistema': ['Pisco', 'Nasca']}


class MaestroFalso:
    """Acierta la tarea salvo en un voto de cada ``fallo`` (al azar), y marca sus datos."""

    modelo = 'falso:1b'

    def __init__(self, verdad: dict[str, object], fallo: int = 4, semilla: int = 0):
        self.verdad, self.fallo, self.rnd = verdad, fallo, random.Random(semilla)
        self.llamadas: list[tuple[str, float, int]] = []

    def interpretar(self, texto, *, temperatura=0.0, semilla=0):
        self.llamadas.append((texto, temperatura, semilla))
        e = self.verdad[texto]
        tarea = e.tarea if self.rnd.randrange(self.fallo) else self.rnd.choice(sorted(TAREAS))
        datos = {}
        for a, b, tipo in e.datos:
            datos.setdefault(tipo, []).append({'valor': texto[a:b], 'confianza': 0.5})
        return {'tarea': tarea, 'confianza': 0.8, 'datos': datos}


class MaestroMudo:
    modelo = 'mudo'

    def interpretar(self, texto, *, temperatura=0.0, semilla=0):
        return None


def test_votos_con_temperatura_y_filtro_por_acuerdo():
    """027:RF-56 / 027:RF-57 — k votos con temperatura y semillas distintas; la distribución es
    la proporción de votos y se descarta la orden sin acuerdo."""
    ejemplos = generar(VOCAB, por_tarea=4, semilla=SEMILLA % 1000)
    verdad = {e.texto: e for e in ejemplos}
    cfg = dst.Destilacion(k=5, acuerdo_min=0.6)
    maestro = MaestroFalso(verdad, fallo=3, semilla=SEMILLA)
    r = dst.etiquetar(list(verdad), maestro, cfg)
    assert r['respondio'] and r['blandos'], SEMILLA
    assert {s for _t, _temp, s in maestro.llamadas} == set(range(cfg.k))
    assert all(temp == cfg.temperatura_maestro for _t, temp, _s in maestro.llamadas)
    for b in r['blandos']:
        assert sum(b.distribucion.values()) == pytest.approx(1.0)
        assert b.acuerdo >= cfg.acuerdo_min and b.distribucion[b.tarea] == max(b.distribucion.values())
        assert all(b.texto[x:y].strip() for x, y, _t in b.datos)
    assert len(r['blandos']) + len(r['descartados']) == len(verdad)
    estricto = dst.etiquetar(list(verdad), MaestroFalso(verdad, fallo=2, semilla=SEMILLA),
                             dst.Destilacion(k=5, acuerdo_min=1.0))
    assert estricto['descartados'] and all('acuerdo' in d['motivo'] for d in estricto['descartados'])


def test_sin_etiqueta_son_las_no_confirmadas_y_no_las_de_prueba(tmp_path, monkeypatch):
    """027:RF-59 — del registro de órdenes, las que el operador no confirmó ni corrigió, sin
    las de la prueba fija y sin repetir."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    for t in ('convierte IN111', 'calibra Pisco', 'convierte IN111', 'informe de CA101', 'de prueba'):
        almacen.anotar('ordenes', {'texto': t})
    almacen.anotar('ejemplos', {'texto': 'calibra Pisco', 'tarea': 'convertir', 'datos': []})
    assert dst.sin_etiqueta(excluir=['de prueba']) == ['convierte IN111', 'informe de CA101']


def test_maestro_mudo_y_registro():
    """027:RF-61 / 027:RF-62 — si el maestro no responde, se dice; el registro guarda maestro,
    k, temperaturas, α y cuántas etiquetó y descartó."""
    r = dst.etiquetar(['convierte IN111'], MaestroMudo())
    assert not r['respondio'] and not r['blandos']
    reg = dst.registro(dst.Destilacion(), MaestroMudo(), r)
    assert reg['maestro'] == 'mudo' and reg['k'] == 5 and reg['alfa'] == 0.5 and reg['T'] == 2.0
    assert reg['etiquetadas'] == 0 and reg['descartadas'] == 1 and not reg['respondio']


@pytest.fixture()
def con_ordenes(tmp_path, monkeypatch):
    """Un almacén con órdenes del operador sin confirmar, de las mismas plantillas."""
    pytest.importorskip('torch')
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    sin = generar(VOCAB, por_tarea=6, semilla=SEMILLA % 997 + 1)
    for e in sin:
        almacen.anotar('ordenes', {'texto': e.texto})
    return {e.texto: e for e in sin}


def test_el_alumno_se_entrena_con_el_maestro_y_solo_se_usa_si_no_empeora(con_ordenes, monkeypatch):
    """027:RF-58 / 027:RF-60 / 027:RF-62 — el alumno aprende con α·CE + (1 − α)·T²·KL; se
    entrena también sin destilar con la misma semilla, se guardan las dos métricas y se usa
    el destilado solo si acierta al menos lo mismo."""
    from igea_dgs.asistente import transformer as tr

    llamadas = []
    original = tr.entrenar

    def espia(datos, cfg=None, log=lambda _m: None, **kw):
        llamadas.append(kw)
        return original(datos, cfg, log, **kw)

    monkeypatch.setattr(tr, 'entrenar', espia)
    r = tr.entrenar_y_promover(VOCAB, cfg=tr.Configuracion(epocas=3, por_tarea=10),
                               puertas=tr.Puertas(acierto_tarea=0.0, f1_datos=0.0),
                               destilar=dst.Destilacion(k=3, acuerdo_min=0.6, alfa=0.3, T=2.0),
                               maestro=MaestroFalso(con_ordenes, fallo=5, semilla=SEMILLA))
    d = r['destilacion']
    assert d['maestro'] == 'falso:1b' and d['etiquetadas'] > 0, d
    assert len(llamadas) == 2 and not llamadas[0] and llamadas[1]['alfa'] == 0.3 and llamadas[1]['T'] == 2.0
    assert len(llamadas[1]['blandos']) == d['etiquetadas']
    m0, m1 = d['metricas_sin_destilar'], d['metricas_destilado']
    assert d['usado'] == (m1['acierto_tarea'] >= m0['acierto_tarea'])
    assert r['acierto_tarea'] == (m1 if d['usado'] else m0)['acierto_tarea']


def test_sin_maestro_se_entrena_sin_destilar(con_ordenes):
    """027:RF-61 — con el maestro mudo, un solo entrenamiento y el registro lo dice."""
    from igea_dgs.asistente import transformer as tr

    r = tr.entrenar_y_promover(VOCAB, cfg=tr.Configuracion(epocas=1, por_tarea=5),
                               puertas=tr.Puertas(acierto_tarea=0.0, f1_datos=0.0),
                               destilar=dst.Destilacion(k=2), maestro=MaestroMudo())
    assert r['destilacion']['usado'] is False and not r['destilacion']['respondio']
