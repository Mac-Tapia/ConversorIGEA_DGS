"""Estadística de las órdenes de DIgSILENT: descriptiva, contraste entre versiones y fallos que se repiten (081:RF-70 a RF-73).

Pisco (2026-11-02 y 03): dos días y dos noches para un sistema, con solo 6,9 h de DIgSILENT calculando; el resto
fueron 62 órdenes fallidas de 316, dos caídas del motor y 71 arranques. Sin medirlo no se ve dónde se pierde el
tiempo ni se puede demostrar que una versión nueva lo mejora. Cada orden queda en ``ordenes.jsonl`` de la cola
(``pf_servidor.py``) y aquí se resume y se contrasta: la hipótesis «la versión B es más rápida que la A» con
Mann-Whitney de una cola y «B falla menos» con la exacta de Fisher, a un nivel α que se dice.
"""
from __future__ import annotations

import json
import random
import re
import statistics as st
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

#: Fichero de la cola de DIgSILENT con una línea JSON por orden atendida (081:RF-70).
REGISTRO = 'ordenes.jsonl'
#: Nivel de significación por defecto de los contrastes (081:RF-72).
ALFA = 0.05
_LINEA = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (.*)$')


def registro(orden: Mapping[str, Any], codigo: int, segundos: float, causa: str = '',
             ahora: datetime | None = None) -> dict[str, Any]:
    """081:RF-70: la fila de una orden: cuándo, qué guion y modo, cuánto tardó, cómo terminó y por qué falló."""
    argv = [str(a) for a in orden.get('argv') or []]
    return {'fecha': (ahora or datetime.now()).isoformat(timespec='seconds'), 'id': str(orden.get('id') or ''),
            'guion': str(orden.get('guion') or '?'), 'modo': [a for a in argv if a.startswith('--') and a not in
                                                               ('--plan', '--report', '--cancel-file')],
            'codigo': int(codigo or 0), 'segundos': round(float(segundos), 1), 'causa': causa_corta(causa)}


def causa_corta(texto: str) -> str:
    """La causa normalizada de un fallo: sin números, rutas ni identificadores, para contar las que se repiten (RF-73)."""
    t = (texto or '').strip().splitlines()[-1] if (texto or '').strip() else ''
    t = re.sub(r'[A-Za-z]:[\\/][^\s\'"]+', '<ruta>', t)
    t = re.sub(r'\b[0-9a-f]{12,}\b', '<id>', t)
    t = re.sub(r'\d+([.,]\d+)?', '#', t)
    return t[:240]


def ultima_causa(log: Path) -> str:
    """La última línea de error de la salida de una orden (``ERROR:`` o la de la excepción)."""
    try:
        lineas = log.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    errores = [ln for ln in lineas if ln.startswith('ERROR') or re.match(r'^\w+(Error|Exception)\b', ln)]
    return (errores or lineas[-1:] or [''])[-1]


def leer(cola: Path | str) -> list[dict[str, Any]]:
    """Las órdenes de ``ordenes.jsonl`` y, de antes de que existiera, las de ``servidor.log`` (sin causa)."""
    cola = Path(cola)
    filas = []
    if (cola / REGISTRO).is_file():
        for ln in (cola / REGISTRO).read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                filas.append(json.loads(ln))
            except ValueError:
                continue
    desde = min((f['fecha'] for f in filas), default='9999')
    return sorted(de_servidor_log(cola / 'servidor.log', hasta=desde) + filas, key=lambda f: f['fecha'])


def de_servidor_log(ruta: Path, hasta: str = '9999') -> list[dict[str, Any]]:
    """Las órdenes que dice ``servidor.log`` (019:RF-21), para el historial anterior a ``ordenes.jsonl``."""
    if not ruta.is_file():
        return []
    inicio: dict[str, tuple[datetime, str]] = {}
    out = []
    for ln in ruta.read_text(encoding='utf-8', errors='replace').splitlines():
        m = _LINEA.match(ln)
        if not m or m.group(1).replace(' ', 'T') >= hasta:
            continue
        t, texto = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S'), m.group(2)
        if o := re.match(r'Orden ([0-9a-f]+): (\S+)$', texto):
            inicio[o.group(1)] = (t, o.group(2))
        elif o := re.match(r'Orden ([0-9a-f]+) terminada con código (\d+) en (\d+) s', texto):
            out.append({'fecha': t.isoformat(), 'id': o.group(1), 'guion': inicio.get(o.group(1), (t, '?'))[1],
                        'modo': [], 'codigo': int(o.group(2)), 'segundos': float(o.group(3)), 'causa': ''})
        elif o := re.match(r'Orden ([0-9a-f]+) de un proceso anterior cerrada', texto):
            t0, guion = inicio.get(o.group(1), (t, '?'))
            out.append({'fecha': t.isoformat(), 'id': o.group(1), 'guion': guion, 'modo': [], 'codigo': 3,
                        'segundos': (t - t0).total_seconds(), 'causa': 'DIgSILENT murió a mitad de la orden'})
    return out


def _mediana_ic(datos: Sequence[float], nivel: float = 0.95, remuestras: int = 2000,
                semilla: int = 20261103) -> tuple[float, float]:
    """Intervalo de confianza de la mediana por remuestreo (bootstrap percentil), con semilla fija: reproducible."""
    if len(datos) < 2:
        return (datos[0], datos[0]) if datos else (float('nan'), float('nan'))
    rnd = random.Random(semilla)
    medianas = sorted(st.median(rnd.choices(datos, k=len(datos))) for _ in range(remuestras))
    a = (1 - nivel) / 2
    return medianas[int(a * remuestras)], medianas[min(remuestras - 1, int((1 - a) * remuestras))]


def descriptiva(filas: Iterable[Mapping[str, Any]], clave: str = 'guion') -> list[dict[str, Any]]:
    """081:RF-71: por guion (o ``clave``): n, fallos y su tasa, horas, media, mediana con su IC 95 %, p90 y máximo."""
    grupos: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for f in filas:
        grupos[str(f.get(clave) if clave != 'dia' else str(f['fecha'])[:10])].append(f)
    out = []
    for g, fs in grupos.items():
        d = sorted(float(f['segundos']) for f in fs)
        fallos = sum(1 for f in fs if int(f.get('codigo') or 0))
        lo, hi = _mediana_ic(d)
        out.append({clave: g, 'n': len(d), 'fallos': fallos, 'tasa_fallos': fallos / len(d), 'horas': sum(d) / 3600,
                    'media_s': st.mean(d), 'mediana_s': st.median(d), 'ic95_mediana_s': (lo, hi),
                    'p90_s': d[int(0.9 * (len(d) - 1))], 'max_s': d[-1]})
    return sorted(out, key=lambda r: -r['horas'])


def contrastar(a: Sequence[Mapping[str, Any]], b: Sequence[Mapping[str, Any]], alfa: float = ALFA) -> dict[str, Any]:
    """081:RF-72: H1 «B tarda menos que A» (Mann-Whitney U, una cola) y «B falla menos que A» (Fisher, una cola).

    Con menos de 5 órdenes en un grupo no hay contraste de duración: se dice, en vez de dar un p sin potencia.
    """
    from scipy.stats import fisher_exact, mannwhitneyu

    da, db = [float(f['segundos']) for f in a], [float(f['segundos']) for f in b]
    fa, fb = sum(1 for f in a if int(f.get('codigo') or 0)), sum(1 for f in b if int(f.get('codigo') or 0))
    out: dict[str, Any] = {'alfa': alfa, 'n_a': len(da), 'n_b': len(db),
                           'mediana_a_s': st.median(da) if da else None, 'mediana_b_s': st.median(db) if db else None,
                           'tasa_fallos_a': fa / len(da) if da else None, 'tasa_fallos_b': fb / len(db) if db else None}
    if min(len(da), len(db)) >= 5:
        u, p = mannwhitneyu(db, da, alternative='less')
        out['duracion'] = {'U': float(u), 'p': float(p), 'demostrado': bool(p < alfa)}
    else:
        out['duracion'] = {'p': None, 'demostrado': False, 'motivo': 'menos de 5 órdenes en un grupo'}
    if da and db:
        _r, p = fisher_exact([[fb, len(db) - fb], [fa, len(da) - fa]], alternative='less')
        out['fallos'] = {'p': float(p), 'demostrado': bool(p < alfa)}
    return out


def repetidos(filas: Iterable[Mapping[str, Any]]) -> list[tuple[str, str, int]]:
    """081:RF-73: los fallos con la misma causa en el mismo guion más de una vez: ``(guion, causa, veces)``.

    Un fallo real se arregla una vez y pasa a comprobación permanente (RF-46); si vuelve, es una regresión.
    """
    c = Counter((str(f['guion']), str(f['causa'])) for f in filas if int(f.get('codigo') or 0) and f.get('causa'))
    return sorted(((g, k, n) for (g, k), n in c.items() if n > 1), key=lambda x: -x[2])
