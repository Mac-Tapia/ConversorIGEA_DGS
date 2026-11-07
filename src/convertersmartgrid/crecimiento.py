"""Crecimiento anual de la demanda de cada alimentador desde la medición de cabecera (spec 029).

El PIDE de Chincha (2026-10-28) no tenía tasa: el perfil la dejaba vacía y solo se diagnosticaba
el año 00. La cabecera trae 2025 entero y 2026 hasta el mes del último libro: comparar la máxima
de un año entero con la de medio año daba un crecimiento falso, así que se comparan las máximas
de los meses que tienen los dos años (RF-2). Es la tasa de la demanda medida y nada más: la
proyección con variables exógenas es otra spec (la 031).
"""
from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

Curva = Sequence[tuple[Any, float | None, Any]]


def _fecha(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


def maximas_mensuales(curva: Curva) -> dict[int, float]:
    """La máxima de cada mes de una curva ``[(fecha, kW, kVAR)]``."""
    out: dict[int, float] = {}
    for fecha, kw, *_ in curva:
        f = _fecha(fecha)
        if f is None or kw is None:
            continue
        out[f.month] = max(out.get(f.month, float('-inf')), float(kw))
    return out


def sumar(curvas: Sequence[Curva]) -> list[tuple[Any, float, None]]:
    """Las curvas de los medidores de un alimentador sumadas en sus registros comunes."""
    if len(curvas) == 1:
        return [(f, kw, None) for f, kw, *_ in curvas[0] if kw is not None]
    por_fecha: dict[Any, list[float]] = {}
    for c in curvas:
        for f, kw, *_ in c:
            if kw is not None:
                por_fecha.setdefault(f, []).append(float(kw))
    return [(f, sum(v), None) for f, v in sorted(por_fecha.items(), key=lambda x: str(x[0]))
            if len(v) == len(curvas)]


def tasa_entre(anterior: Curva, ultima: Curva, anios: int) -> dict[str, Any] | None:
    """La tasa compuesta entre las máximas de los meses comunes de dos años (RF-2)."""
    a, b = maximas_mensuales(anterior), maximas_mensuales(ultima)
    meses = sorted(set(a) & set(b))
    if not meses or anios <= 0:
        return None
    ma, mb = max(a[m] for m in meses), max(b[m] for m in meses)
    if ma <= 0 or mb <= 0:
        return None
    return {'tasa': (mb / ma) ** (1 / anios) - 1, 'meses': meses, 'max_anterior_kw': ma,
            'max_ultimo_kw': mb}


def tasas_por_alimentador(curvas: Mapping[int, Mapping[str, Curva]],
                          alimentadores: Sequence[str]) -> dict[str, dict[str, Any]]:
    """La tasa de cada alimentador entre su primer y su último año con datos; los demás, la
    mediana de las medidas (RF-1 a RF-3, RF-5)."""
    out: dict[str, dict[str, Any]] = {}
    for a in alimentadores:
        anios = sorted(y for y, cs in curvas.items() if cs.get(a))
        if len(anios) >= 2:
            r = tasa_entre(curvas[anios[0]][a], curvas[anios[-1]][a], anios[-1] - anios[0])
            if r is not None:
                out[a] = {**r, 'anios': [anios[0], anios[-1]], 'origen': 'medida'}
    medidas = [x['tasa'] for x in out.values()]
    mediana = statistics.median(medidas) if medidas else None
    for a in alimentadores:
        if a not in out:
            out[a] = {'tasa': mediana, 'origen': 'mediana del sistema' if mediana is not None else 'sin datos'}
    return out


def curvas_por_anio(libros_por_anio: Mapping[int, Sequence[Path | str]], pares: Sequence[tuple[str, str]],
                    alias: Any, *, progreso: Callable = lambda *_a: None, log: Callable = lambda _t: None,
                    cancelado: Callable[[], bool] = lambda: False) -> dict[int, dict[str, list]]:
    """Las curvas de cada alimentador (sus medidores sumados) por año, leídas con ``maximas``;
    corre en el proceso del trabajo (RF-7)."""
    from .demanda_medida import maximas

    out: dict[int, dict[str, list]] = {}
    for anio, libros in sorted(libros_por_anio.items()):
        if cancelado():
            break
        log(f'Crecimiento: leyendo la cabecera de {anio} ({len(libros)} libro(s))…')
        res = maximas(list(libros), list(pares), alias=alias, periodo=str(anio), cancelado=cancelado,
                      progreso=progreso)
        por_alim: dict[str, list] = {}
        for r in res:
            if r.curva and r.alimentador:
                por_alim.setdefault(r.alimentador, []).append(r.curva)
        out[anio] = {a: sumar(cs) for a, cs in por_alim.items()}
    return out


def tasa_de_las_fijas(pot_por_mes: Mapping[str, Mapping[str, float]],
                      fijas: Mapping[str, Sequence[Sequence[str]]]) -> dict[str, dict[str, Any] | None]:
    """La tasa de cada alimentador desde la POT registrada de sus fijas (042:RF-7).

    Cuando la cabecera no tiene dos años (NA203 y NA205 solo tienen 2026, 2026-10-31), la demanda
    registrada que sí los tiene es la de las fijas, en los libros de clientes de cada mes.
    ``pot_por_mes``: ``'AAAA-MM'`` → clave de cliente → POT (kW); ``fijas``: alimentador → cada
    fija con sus claves (la actual y la anterior: el código cambió entre años). Se suman, mes a
    mes, las fijas con registro en los dos años (una que entró después inflaría el crecimiento) y
    se comparan con :func:`tasa_entre`, como la cabecera.
    """
    anios = sorted({int(m[:4]) for m in pot_por_mes})
    out: dict[str, dict[str, Any] | None] = {}
    if len(anios) < 2:
        return {f: None for f in fijas}
    ant, ult = anios[-2], anios[-1]

    def pot(mes: str, claves: Sequence[str]) -> float | None:
        datos = pot_por_mes.get(mes) or {}
        return next((datos[k] for k in claves if datos.get(k) is not None), None)

    for f, clientes in fijas.items():
        def con_registro(claves, anio):
            return any(pot(m, claves) for m in pot_por_mes if m.startswith(str(anio)))

        comunes = [c for c in clientes if con_registro(c, ant) and con_registro(c, ult)]
        curvas = {a: [(datetime(a, int(m[5:7]), 1), sum(pot(m, c) or 0.0 for c in comunes), None)
                      for m in sorted(pot_por_mes) if m.startswith(str(a))] for a in (ant, ult)}
        r = tasa_entre(curvas[ant], curvas[ult], ult - ant) if comunes else None
        out[f] = None if r is None else {**r, 'origen': 'fijas', 'clientes': len(comunes),
                                         'de': len(clientes), 'anios': [ant, ult]}
    return out


def _huella_del_libro(ruta: str, alias: Any) -> str | None:
    """042:RF-96: la del libro (ruta, tamaño y fecha), la de los alias y la del lector; ``None`` si no se puede leer."""
    import hashlib
    import json

    try:
        st = Path(ruta).stat()
        lector = (Path(__file__).with_name('demanda_medida.py')).read_bytes()
    except OSError:
        return None
    datos = json.dumps({'ruta': str(Path(ruta).resolve()), 'tam': st.st_size, 'mtime': st.st_mtime_ns,
                        'alias': alias}, sort_keys=True, default=str)
    return hashlib.sha256(datos.encode('utf-8') + hashlib.sha256(lector).digest()).hexdigest()[:32]


def pot_de_los_libros(libros: Sequence[tuple[str, str]], alias: Any, *, progreso: Callable = lambda *_a: None,
                      log: Callable = lambda _t: None,
                      cancelado: Callable[[], bool] = lambda: False,
                      cache: str | Path | None = None) -> dict[str, dict[str, float]]:
    """``'AAAA-MM'`` → clave de cliente → POT (kW) de cada libro de clientes del catálogo (042:RF-7).

    De nivel superior: corre en el proceso del trabajo (029:RF-7). Un libro que no se lee no
    cuenta: su mes queda fuera de los meses comunes. Con ``cache``, la POT de cada libro se guarda
    con su huella y un libro sin cambios no se vuelve a leer (042:RF-96): en PE102 (2026-11-06) cada
    «Con proyecto» releía los 21 libros de clientes importantes, de 50 a 150 MB cada uno.
    """
    import json

    from .demanda_medida import DemandaError, clave_codigo, leer_clientes

    carpeta = Path(cache) if cache else None
    out: dict[str, dict[str, float]] = {}
    for i, (mes, ruta) in enumerate(libros, 1):
        if cancelado():
            break
        progreso(i, len(libros))
        huella = _huella_del_libro(ruta, alias) if carpeta is not None else None
        guardado = carpeta / f'pot_{huella}.json' if huella else None
        if guardado is not None and guardado.is_file():
            try:
                out.setdefault(mes, {}).update(json.loads(guardado.read_text(encoding='utf-8')))
                log(f'Crecimiento: libro de clientes de {mes} ({i}/{len(libros)}), ya leído (042:RF-96).')
                continue
            except (OSError, ValueError):
                pass                                    # un guardado roto se vuelve a leer
        log(f'Crecimiento: libro de clientes de {mes} ({i}/{len(libros)})…')
        try:
            clientes, _avisos = leer_clientes(ruta, alias)
        except (DemandaError, OSError):
            continue
        pot = {clave_codigo(c.codigo): float(c.pot) for c in clientes if c.pot}
        out.setdefault(mes, {}).update(pot)
        if guardado is not None:
            try:
                carpeta.mkdir(parents=True, exist_ok=True)
                temporal = guardado.with_suffix('.tmp')
                temporal.write_text(json.dumps(pot, sort_keys=True), encoding='utf-8')
                temporal.replace(guardado)
            except OSError:
                pass                                    # sin guardar se lee otra vez la próxima: no se bloquea
    return out
