"""070:RF-92 — el modelo de órdenes guardado con una parte de las tareas del contrato se abre y predice con las suyas.

El 2026-11-24 (070 T22) el modelo en uso prov-8fd8a405 conocía 49 tareas y el contrato tenía 68, sin quitar ninguna:
``modelo_desde`` exigía la lista idéntica, el asistente se quedaba sin modelo de órdenes («contrato de tareas o
entidades incompatible») y la no regresión del candidato no se podía medir. Aquí el modelo se entrena de verdad (en CPU,
con el codificador falso de las pruebas) y su cabeza de tareas se recorta a una parte del contrato, como queda un modelo
entrenado antes de que el contrato creciera.
"""
from __future__ import annotations

import json

import pytest

torch = pytest.importorskip('torch')

from test_interprete_codificador import _entrenado, falso  # noqa: E402,F401

from convertersmartgrid.aplicacion.asistente import codificador_ordenes as co   # noqa: E402
from convertersmartgrid.aplicacion.asistente import destilacion_integral as di  # noqa: E402
from convertersmartgrid.aplicacion.asistente import transformer as tr           # noqa: E402
from convertersmartgrid.aplicacion.asistente.maestro_real import NINGUNA       # noqa: E402

CPU = torch.device('cpu')
TEXTOS = ['convierte AB101', 'que hay cargado', 'calibra el alimentador AB101', 'hola que tal']


def _recortado(carpeta, quitar: int = 3):
    """Guarda un modelo entrenado y lo deja con las tareas del contrato menos ``quitar`` (nunca «ninguna»)."""
    m = _entrenado(epocas=40)
    di._guardar_alumno(m, carpeta, {'version': 'alumno'})
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    pesos = torch.load(carpeta / 'pesos.pt', weights_only=True)
    completas = list(meta['tareas'])
    predichas = {m.predecir(t)['tarea'] for t in TEXTOS}
    fuera = [t for t in completas if t != NINGUNA and t not in predichas][:quitar]
    quedan = [i for i, t in enumerate(completas) if t not in fuera]
    ultima = max(int(k.split('.')[1]) for k in pesos if k.startswith('tarea.') and k.endswith('.weight'))
    for parte in ('weight', 'bias'):
        clave = f'tarea.{ultima}.{parte}'
        pesos[clave] = pesos[clave][quedan].clone()
    meta['tareas'] = [completas[i] for i in quedan]
    torch.save(pesos, carpeta / 'pesos.pt')
    (carpeta / 'modelo.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    return m, meta, pesos, fuera


def test_070_rf92_una_parte_del_contrato_se_abre_y_predice_con_sus_tareas(falso):
    completo, meta, pesos, fuera = _recortado(falso / 'alumno')
    assert len(fuera) == 3 and len(meta['tareas']) == len(co.tareas_del_modelo()) - 3
    abierto = co.modelo_desde(meta, pesos, 'v', CPU)
    assert abierto.tareas == meta['tareas']
    for texto in TEXTOS:
        p, q = abierto.predecir(texto), completo.predecir(texto)
        assert p['tarea'] in meta['tareas'] and p['tarea'] not in fuera
        # Las tareas que conserva puntúan como en el modelo completo: la que ganaba sigue ganando.
        assert p['tarea'] == q['tarea']
    # Por el mismo camino que el registro (cargar_alumno) también se abre.
    assert di.cargar_alumno(falso / 'alumno').tareas == meta['tareas']


def test_070_rf92_el_modelo_en_uso_recortado_lo_abre_la_web_y_lo_mide_la_no_regresion(falso, monkeypatch):
    _recortado(falso / 'alumno')
    carpeta = tr.raiz_modelos() / 'v1'
    carpeta.mkdir(parents=True)
    for n in ('pesos.pt', 'modelo.json'):
        (carpeta / n).write_bytes((falso / 'alumno' / n).read_bytes())
    tr.promover('v1', 'prueba')
    monkeypatch.setattr(tr, 'dispositivo_de_calculo', lambda: CPU)
    monkeypatch.setattr(tr, '_cache', {})
    assert tr.motivo_no_disponible() is None
    assert tr.cargar() is not None
    humanas = [{'texto': t, 'tarea': 'estado', 'datos': []} for t in TEXTOS]
    en_uso = di._medir_en_uso(humanas, humanas, None)
    assert 'error' not in en_uso and en_uso['version']


def test_070_rf92_una_tarea_que_el_contrato_ya_no_tiene_sigue_incompatible(falso):
    _completo, meta, pesos, _fuera = _recortado(falso / 'alumno')
    otra = {**meta, 'tareas': [*meta['tareas'][:-2], 'tarea_que_ya_no_existe', meta['tareas'][-1]]}
    with pytest.raises(ValueError, match='contrato de tareas o entidades incompatible'):
        co.modelo_desde(otra, pesos, 'v', CPU)
    repetida = {**meta, 'tareas': [meta['tareas'][0], *meta['tareas'][:-1]]}
    with pytest.raises(ValueError, match='contrato de tareas o entidades incompatible'):
        co.modelo_desde(repetida, pesos, 'v', CPU)
    sin_entidad = {**meta, 'etiquetas': list(meta['etiquetas'])[:-1]}
    with pytest.raises(ValueError, match='contrato de tareas o entidades incompatible'):
        co.modelo_desde(sin_entidad, pesos, 'v', CPU)
