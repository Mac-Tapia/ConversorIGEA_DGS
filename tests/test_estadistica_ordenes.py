"""081:RF-71 a RF-74 — estadística de las órdenes de DIgSILENT."""
from __future__ import annotations

import json
import random

from convertersmartgrid import estadistica_ordenes as eo


def _filas(n, media, fallos, guion='obras_pf.py', dia='2026-11-03', causa='ERROR: no converge en la barra 12'):
    rnd = random.Random(n * 7 + fallos)
    return [{'fecha': f'{dia}T10:{i % 60:02d}:00', 'id': f'{i:012x}', 'guion': guion, 'modo': [],
             'codigo': 1 if i < fallos else 0, 'segundos': max(1.0, rnd.gauss(media, media / 5)),
             'causa': eo.causa_corta(causa if i < fallos else '')} for i in range(n)]


def test_registro_de_una_orden_con_su_causa(tmp_path):
    """081:RF-71 — la fila lleva guion, modo, código, duración y causa sin rutas ni números."""
    log = tmp_path / 'a.log'
    log.write_text('leyendo\nERROR: no existe D:/x/y.json en 12 s\n', encoding='utf-8')
    f = eo.registro({'id': 'a', 'guion': 'obras_pf.py', 'argv': ['--evaluar', '--plan', 'p.json']}, 1, 12.34,
                    eo.ultima_causa(log))
    assert f['modo'] == ['--evaluar'] and f['codigo'] == 1 and f['segundos'] == 12.3
    assert f['causa'] == 'ERROR: no existe <ruta> en # s'
    json.dumps(f)


def test_descriptiva_con_intervalo_de_la_mediana():
    """081:RF-72 — n, tasa de fallos, mediana dentro de su IC 95 %, p90 ≤ máximo; reproducible."""
    filas = _filas(40, 100.0, 8) + _filas(10, 5.0, 0, guion='estudios_pf.py')
    t = eo.descriptiva(filas)
    r = next(x for x in t if x['guion'] == 'obras_pf.py')
    lo, hi = r['ic95_mediana_s']
    assert r['n'] == 40 and r['tasa_fallos'] == 0.2 and lo <= r['mediana_s'] <= hi and r['p90_s'] <= r['max_s']
    assert eo.descriptiva(filas) == t
    assert eo.descriptiva(filas, clave='dia')[0]['n'] == 50


def test_contraste_demuestra_la_mejora_y_no_la_inventa():
    """081:RF-73 — B claramente más rápida y con menos fallos: se demuestra; iguales o pocas: no."""
    a, b = _filas(30, 400.0, 12), _filas(30, 100.0, 1)
    c = eo.contrastar(a, b)
    assert c['duracion']['demostrado'] and c['fallos']['demostrado']
    assert not eo.contrastar(a, _filas(30, 400.0, 12))['duracion']['demostrado']
    assert eo.contrastar(a, b[:3])['duracion']['p'] is None


def test_fallos_repetidos_y_historial_del_servidor(tmp_path):
    """081:RF-74 — la misma causa dos veces es una regresión; RF-71: el historial anterior sale de servidor.log."""
    assert eo.repetidos(_filas(10, 50.0, 3)) == [('obras_pf.py', 'ERROR: no converge en la barra #', 3)]
    (tmp_path / 'servidor.log').write_text(
        '2026-11-03 14:14:14 Orden 593a8771de0d: obras_pf.py\n'
        '2026-11-03 14:20:00 Orden 593a8771de0d de un proceso anterior cerrada con código 3.\n'
        '2026-11-03 15:00:00 Orden aaaaaaaaaaaa: casos_pf.py\n'
        '2026-11-03 15:00:05 Orden aaaaaaaaaaaa terminada con código 0 en 5 s.\n', encoding='utf-8')
    filas = eo.leer(tmp_path)
    assert [(f['guion'], f['codigo'], f['segundos']) for f in filas] == [('obras_pf.py', 3, 346.0), ('casos_pf.py', 0, 5.0)]
