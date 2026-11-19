"""086:RF-115 (T85): un cursor que quedó por detrás de lo descartado recibe ``historial_truncado`` (auditoría del 18-11,
H15). Un historial completo no lo lleva; la consulta y el WebSocket usan la misma regla.
"""
from __future__ import annotations

from pathlib import Path

from convertersmartgrid.presentacion.web.jobs import EventLog

RAIZ = Path(__file__).resolve().parents[1]


def _registro_con_cuatro(maxlen: int = 2) -> tuple[EventLog, list[dict]]:
    log = EventLog(maxlen=maxlen)
    emitidos = [log.append('log', {'text': f'línea {i}'}) for i in range(4)]
    return log, emitidos


def test_cursor_antiguo_notifica_truncamiento():
    log, emitidos = _registro_con_cuatro()
    recibidos = log.since(0)
    assert recibidos[0]['type'] == 'historial_truncado'
    assert recibidos[0]['data'] == {'perdidos': 2, 'hasta': emitidos[1]['seq']}
    assert [e['seq'] for e in recibidos[1:]] == [e['seq'] for e in emitidos[2:]]
    assert recibidos[0]['seq'] < recibidos[1]['seq'], 'el cursor del cliente sigue avanzando'


def test_cursor_dentro_del_hueco_cuenta_solo_lo_que_le_falta():
    log, emitidos = _registro_con_cuatro()
    recibidos = log.since(emitidos[0]['seq'])
    assert recibidos[0]['type'] == 'historial_truncado'
    assert recibidos[0]['data']['perdidos'] == 1


def test_cursor_al_dia_no_lleva_marcador():
    log, emitidos = _registro_con_cuatro()
    assert [e['type'] for e in log.since(emitidos[1]['seq'])] == ['log', 'log']
    assert log.since(emitidos[3]['seq']) == []


def test_sin_descartes_el_historial_es_completo():
    log, emitidos = _registro_con_cuatro(maxlen=10)
    assert [e['seq'] for e in log.since(0)] == [e['seq'] for e in emitidos]


def test_la_espera_del_websocket_usa_la_misma_regla():
    log, emitidos = _registro_con_cuatro()
    recibidos = log.wait(0, 0.01)
    assert recibidos[0]['type'] == 'historial_truncado'
    assert log.wait(emitidos[1]['seq'], 0.01)[0]['type'] == 'log'


def test_la_pestana_anota_el_truncado_y_relee():
    """La línea sale de ``reconexion.ts`` (probada en node); aquí, que el gancho la use y relea el espacio."""
    gancho = (RAIZ / 'frontend/src/shared/useWorkspace.ts').read_text(encoding='utf-8')
    tipos = (RAIZ / 'frontend/src/api/types.ts').read_text(encoding='utf-8')
    assert "'historial_truncado'" in tipos
    assert "ev.type === 'historial_truncado'" in gancho
    assert 'lineaDeTruncado(' in gancho
    assert 'releer()' in gancho.split("ev.type === 'historial_truncado'")[1].split('} else if')[0] or \
        'truncado = true' in gancho
