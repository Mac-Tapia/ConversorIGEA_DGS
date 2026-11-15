"""Spec 107 T11 — observaciones del regulador enlazadas con la traza del expediente (107:RF-10)."""
from __future__ import annotations

import pytest

from datos_pit import perfil_b

from convertersmartgrid.pit.ambito import PitError
from convertersmartgrid.pit.observaciones import escribir_observaciones, leer_observaciones, registrar


def _referencias(caso):
    """Lo que un expediente expone para enlazar: elementos, casos y celdas con su traza."""
    elementos = {e['id']: {'tipo': e['tipo'], 'titular': e['titular']} for e in caso['elementos']}
    celda = 'cuadro.nuevas!F3'
    traza = {'fuente': {'sha256': 'c' * 64}, 'calculo': 'valorar_obra', 'motor': 'abierto',
             'regla': {'clave': 'pit.cuadro.nuevas', 'estado': 'modificada'}}
    return {'elemento': elementos, 'caso': {f'{caso["anios"][0]}:base': {}}, 'celda': {celda: traza}}, celda


def test_observacion_sobre_una_celda_y_otra_sobre_un_elemento(tmp_path):
    """107:RF-10 — cada observación con número, fecha, texto, respuesta y su objeto, enlazada con la traza."""
    caso = perfil_b(12)
    refs, celda = _referencias(caso)
    elemento = caso['pistas']['compartida']
    obs = registrar([
        {'numero': '2', 'fecha': '2031-02-01', 'texto': 'Sustente la inversión.', 'afecta': 'celda',
         'referencia': celda, 'respuesta': 'Sale del módulo estándar citado.'},
        {'numero': '1', 'fecha': '2031-01-15', 'texto': 'Asigne el elemento compartido.', 'afecta': 'elemento',
         'referencia': elemento, 'respuesta': 'Asignado en el perfil.'},
    ], refs)
    assert [o.numero for o in obs] == ['1', '2']
    assert obs[1].enlace['regla']['clave'] == 'pit.cuadro.nuevas' and obs[1].enlace['motor'] == 'abierto'
    assert obs[0].enlace['titular'] and obs[0].respuesta
    ruta = escribir_observaciones(tmp_path / 'obs.json', obs)
    assert leer_observaciones(ruta, refs) == obs
    assert escribir_observaciones(tmp_path / 'otra.json', obs).read_bytes() == ruta.read_bytes()


@pytest.mark.parametrize('cambio,error', [
    ({'referencia': 'cuadro.inexistente!A1'}, 'no tiene celda'),
    ({'afecta': 'tarifa'}, 'afecta'),
    ({'fecha': '15/01/2031'}, 'AAAA-MM-DD'),
])
def test_observacion_sin_objeto_conocido_es_un_error(cambio, error):
    """107:RF-10 — una observación que no se puede enlazar con el expediente no se registra."""
    caso = perfil_b(12)
    refs, celda = _referencias(caso)
    base = {'numero': '1', 'fecha': '2031-01-15', 'texto': 'x', 'afecta': 'celda', 'referencia': celda}
    with pytest.raises(PitError, match=error):
        registrar([{**base, **cambio}], refs)


# --- Documento de absolución (aclaración de 107:RF-10, T20) ---------------------------------------------------------

def _observaciones(caso, celda):
    elemento = caso['pistas']['compartida']
    return [
        {'numero': '1', 'fecha': '2031-01-15', 'texto': 'Asigne el elemento compartido.', 'afecta': 'elemento',
         'referencia': elemento, 'respuesta': 'Asignado en el perfil.'},
        {'numero': '2', 'fecha': '2031-02-01', 'texto': 'Sustente la inversión.', 'afecta': 'celda',
         'referencia': celda, 'respuesta': 'Sale del módulo estándar citado.'},
    ]


def test_absolucion_con_objeto_respuesta_y_traza_de_lo_que_cambio(tmp_path):
    """107:RF-10 — la absolución cita cada observación con su objeto y su respuesta, y la traza de lo que cambió:
    la celda observada cambió (huella antes y después) y el elemento no, y se dice."""
    import json

    from convertersmartgrid.pit.observaciones import absolucion, escribir_absolucion

    caso = perfil_b(12)
    antes, celda = _referencias(caso)
    despues = {k: dict(v) for k, v in antes.items()}
    despues['celda'][celda] = {**antes['celda'][celda], 'calculo': 'set_nueva.leer_modulos_pit'}
    doc = absolucion(_observaciones(caso, celda), antes, despues)
    por = {d['numero']: d for d in doc}
    assert [d['numero'] for d in doc] == ['1', '2']
    assert por['2']['cambio']['estado'] == 'cambiado'
    assert por['2']['cambio']['huella_antes'] != por['2']['cambio']['huella_despues']
    assert por['2']['cambio']['despues']['calculo'] == 'set_nueva.leer_modulos_pit'
    assert por['1']['cambio']['estado'] == 'sin_cambios' and 'sin cambios' in por['1']['cambio']['texto']
    assert all(d['respuesta'] and d['afecta'] and d['referencia'] for d in doc)
    ruta = escribir_absolucion(tmp_path / 'absolucion.json', _observaciones(caso, celda), antes, despues)
    assert json.loads(ruta.read_text(encoding='utf-8')) == doc
    otra = escribir_absolucion(tmp_path / 'otra.json', list(reversed(_observaciones(caso, celda))), antes, despues)
    assert otra.read_bytes() == ruta.read_bytes()


def test_absolucion_de_un_objeto_retirado_del_expediente(tmp_path):
    """107:RF-10 — si lo observado ya no está en el expediente, la absolución lo dice: no se calla ni se inventa."""
    from convertersmartgrid.pit.observaciones import absolucion

    caso = perfil_b(12)
    antes, celda = _referencias(caso)
    despues = {**antes, 'celda': {}}
    doc = {d['numero']: d for d in absolucion(_observaciones(caso, celda), antes, despues)}
    assert doc['2']['cambio']['estado'] == 'retirado' and doc['2']['cambio']['despues'] is None


@pytest.mark.parametrize('cambio,error', [
    ({'referencia': 'cuadro.inexistente!A1'}, 'no tiene celda'),
    ({'respuesta': '  '}, 'sin respuesta'),
])
def test_absolucion_sin_objeto_conocido_o_sin_respuesta_es_un_error(cambio, error):
    """107:RF-10 — una absolución con una referencia desconocida, o sin respuesta, no se emite."""
    from convertersmartgrid.pit.observaciones import absolucion

    caso = perfil_b(12)
    antes, celda = _referencias(caso)
    obs = _observaciones(caso, celda)
    obs[1] = {**obs[1], **cambio}
    with pytest.raises(PitError, match=error):
        absolucion(obs, antes, antes)
