"""Libros nuevos de demanda: foto de las carpetas, verificación de cada libro y su aviso (spec 104).

El 2026-11-12 llegó el libro de octubre de 2026 de clientes importantes y lo verificó Claude a mano: mes, clientes,
registros por cliente frente a 31 días × 96, clientes nuevos y los que no están en el libro de suministros. El
usuario: «el conversor debe hacerlo de forma automática, reconocerlo». Aquí está esa verificación, sin la web: la
web (``web/libros_nuevos.py``) decide cuándo y la publica. El mismo día se vio que el libro de abril de 2026 repetía
los valores de marzo, día a día y hora a hora: también se detecta (RF-15 a RF-17).

Nada bloquea (memoria «reconstruir, no bloquear»): un libro que no se lee se dice y los demás siguen.
"""

from __future__ import annotations

import calendar
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .demanda_medida import (
    MESES,
    nombre_de_mes,
    ALIAS,
    EXTENSIONES,
    abrir_libro,
    clave_codigo,
    curvas_de_clientes,
    filas_de_hoja,
    leer_suministros,
    mes_generico,
    registros_de_hoja,
)
from .libros_por_anio import arbol_de_libros

#: Un mes «repite» otro si al menos esta fracción de sus registros es igual (RF-15). Abril de 2026 frente a marzo:
#: el 100 %; marzo frente a febrero, del 2 al 4 %; mayo frente a abril, el 0 %.
UMBRAL_REPETIDO = 0.95
#: … en más de esta fracción de las series comparables.
MAYORIA_REPETIDO = 0.5
#: Una serie con menos registros distintos de cero que un día no se compara: dos clientes apagados son «iguales».
MINIMO_COMPARABLE = 96
REGISTROS_DIA = 96
PASO = timedelta(minutes=15)


Foto = tuple[tuple[str, int, int], ...]
Curva = Sequence[tuple[datetime, float, float | None]]


# --------------------------------------------------------------------------- foto
def foto_de_fuente(path: Path | str) -> Foto:
    """Ruta relativa, tamaño y fecha de cada libro de la fuente, sin abrir ninguno (104:RF-1, RF-3; 025:RF-31)."""
    path = Path(path)
    if path.is_file():
        rutas = [(path, path.name)] if path.suffix.lower() in EXTENSIONES else []
    elif path.is_dir():
        rutas = [(x.ruta, x.relativa) for x in arbol_de_libros(path)]
    else:
        return ()
    salida = []
    for p, rel in rutas:
        try:
            s = p.stat()
        except OSError:          # un libro que se está copiando o se borró entre listar y mirar
            continue
        salida.append((rel, s.st_size, s.st_mtime_ns))
    return tuple(salida)


def cambios(conocidos: Mapping[str, tuple[int, int]], foto: Foto) -> dict[str, list[str]]:
    """Libros nuevos, cambiados y retirados frente a lo ya conocido (104:RF-1, RF-5)."""
    actuales = {rel: (size, mtime) for rel, size, mtime in foto}
    return {
        'nuevos': sorted(rel for rel in actuales if rel not in conocidos),
        'cambiados': sorted(rel for rel, v in actuales.items() if rel in conocidos and tuple(conocidos[rel]) != v),
        'retirados': sorted(rel for rel in conocidos if rel not in actuales),
    }


# --------------------------------------------------------------------------- textos
def mes_anterior(mes: str) -> str:
    anio, m = int(mes[:4]), int(mes[5:])
    return f'{anio - (m == 1):04d}-{(m - 2) % 12 + 1:02d}'


def _mes_del_registro(t: datetime) -> str:
    """El registro de las 00:00 del día 1 cierra el mes anterior (089:RF-15): se mira el instante 15 min antes."""
    t = t - PASO
    return f'{t.year:04d}-{t.month:02d}'


def _dias_del_mes(mes: str) -> int:
    return calendar.monthrange(int(mes[:4]), int(mes[5:]))[1]


# --------------------------------------------------------------------------- meses repetidos
def _arreglos(curva) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Clave (día del mes, hora, minuto), P y Q de una curva de tuplas o compacta (la del pronóstico, sin copiarla)."""
    if hasattr(curva, 't') and hasattr(curva, 'columnas'):
        t = np.asarray(curva.t, dtype='datetime64[m]')
        p = np.asarray(curva.columnas[0], dtype=float)
        q = np.asarray(curva.columnas[1], dtype=float) if len(curva.columnas) > 1 else np.full(len(t), np.nan)
    else:
        filas = list(curva)
        t = np.array([f[0] for f in filas], dtype='datetime64[m]')
        p = np.array([np.nan if f[1] is None else f[1] for f in filas], dtype=float)
        q = np.array([np.nan if len(f) < 3 or f[2] is None else f[2] for f in filas], dtype=float)
    dias = t.astype('datetime64[D]')
    dia_del_mes = (dias - t.astype('datetime64[M]').astype('datetime64[D]')).astype(int) + 1
    return dia_del_mes * 1440 + (t - dias).astype(int), p, q


def _iguales(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ambos_nan = np.isnan(a) & np.isnan(b)
    return ambos_nan | (np.abs(a - b) <= 1e-9 * np.maximum(1.0, np.maximum(np.abs(a), np.abs(b))))


def fraccion_repetida(nueva, otra) -> tuple[float, int] | None:
    """Fracción de registros de ``nueva`` iguales (P y Q) a ``otra`` en el mismo día del mes y hora (RF-15).

    Los registros en cero no cuentan; con menos de un día de registros comparables, ``None``.
    """
    k1, p1, q1 = _arreglos(nueva)
    k2, p2, q2 = _arreglos(otra)
    # Solo los registros en que la P cambia: un medidor congelado repite su valor todos los meses (IN216 de Ica en 2026)
    # y no es un libro copiado; uno apagado, tampoco.
    cambia = np.r_[True, p1[1:] != p1[:-1]] if len(p1) else np.zeros(0, dtype=bool)
    validos = ~np.isnan(p1) & ~((p1 == 0) & (np.isnan(q1) | (q1 == 0))) & cambia
    comparables = int(validos.sum())
    if comparables < MINIMO_COMPARABLE:
        return None
    if not len(k2):
        return 0.0, comparables
    orden = np.argsort(k2, kind='stable')
    k2, p2, q2 = k2[orden], p2[orden], q2[orden]
    i = np.clip(np.searchsorted(k2, k1), 0, len(k2) - 1)
    iguales = validos & (k2[i] == k1) & _iguales(p1, p2[i]) & _iguales(q1, q2[i])
    return float(iguales.sum()) / comparables, comparables


def repite_otro_mes(nuevas: Mapping[str, Curva], otras: Mapping[str, Curva]) -> dict[str, Any]:
    """Si un libro mensual copia otro: ≥ 95 % de registros iguales en más de la mitad de las series (RF-15)."""
    otras_por_clave = {clave_codigo(c): v for c, v in otras.items()}
    comparables = iguales = 0
    for codigo, curva in nuevas.items():
        otra = otras_por_clave.get(clave_codigo(codigo))
        if otra is None:
            continue
        r = fraccion_repetida(curva, otra)
        if r is None:
            continue
        comparables += 1
        iguales += r[0] >= UMBRAL_REPETIDO
    return {'series_comparables': comparables, 'series_iguales': iguales,
            'repite': comparables > 0 and iguales > MAYORIA_REPETIDO * comparables}


def meses_repetidos_de_serie(curva: Curva) -> list[tuple[str, str, float]]:
    """Los meses de una serie de varios meses que repiten el anterior (RF-17): ``(mes, anterior, fracción)``."""
    por_mes: dict[str, list] = {}
    for fila in curva:
        por_mes.setdefault(_mes_del_registro(fila[0]), []).append(fila)
    salida = []
    for mes in sorted(por_mes):
        previo = por_mes.get(mes_anterior(mes))
        if previo is None:
            continue
        r = fraccion_repetida(por_mes[mes], previo)
        if r is not None and r[0] >= UMBRAL_REPETIDO:
            salida.append((mes, mes_anterior(mes), r[0]))
    return salida


# --------------------------------------------------------------------------- clientes
def como_se_reconocio(origen: str | None, anio: int | None) -> str:
    """De dónde sale el mes del libro (RF-7)."""
    return {
        'nombre': 'por su nombre' + (f', con el año {anio} de su carpeta' if anio else ''),
        'contenido': 'por las fechas de sus hojas',
        'manual': 'asignado por el operador',
    }.get(origen or '', 'sin reconocer')


def suministros_del_libro(path: Path | str, alias=ALIAS) -> set[str]:
    """Las claves de los códigos, actuales y anteriores, del libro de suministros (RF-11)."""
    suministros, _avisos = leer_suministros(path, alias)
    return {clave_codigo(c) for s in suministros for c in (s.actual, s.anterior) if c}


def mes_del_libro_de_suministros(nombre: str, anio: int) -> str | None:
    """El mes del libro de suministros por su nombre, con el año del libro de clientes («0926 Clientes_spl»)."""
    return mes_generico(nombre, anio)


def verificar_libro_clientes(path: Path | str, mes: str | None, *, origen: str | None = None, anio: int | None = None,
                             anterior: Mapping[str, Curva] | None = None, codigos_anteriores: Iterable[str] | None = None,
                             mes_previo: str | None = None, suministros: set[str] | None = None,
                             nombre_suministros: str | None = None, meses_de_otros: Mapping[str, str] | None = None,
                             curvas: Mapping[str, Curva] | None = None) -> dict[str, Any]:
    """Lo que la revisión manual del 2026-11-12 decía del libro de octubre, para cualquier libro (RF-7 a RF-15).

    ``anterior`` son las curvas del libro del mes anterior (para los nuevos, los que faltan y el mes repetido);
    ``meses_de_otros``, el mes de cada otro libro activo ({mes: nombre}) para el solape (046:RF-12).
    """
    path = Path(path)
    ficha: dict[str, Any] = {'tipo': 'clientes', 'libro': path.name, 'mes': mes, 'como': como_se_reconocio(origen, anio),
                             'error': None}
    try:
        if curvas is None:
            curvas, notas = curvas_de_clientes(path, None, mes=mes)
        else:
            notas = []
    except Exception as exc:  # noqa: BLE001 - calamine da errores propios; no se calla (RF-18)
        ficha['error'] = str(exc) or exc.__class__.__name__
        return ficha
    registros = [len(c) for c in curvas.values()]
    ficha.update(clientes=len(curvas), codigos=sorted(curvas), avisos_lectura=list(notas))
    instantes = [f[0] for c in curvas.values() for f in (c[0], c[-1]) if len(c)]
    ficha['periodo'] = [min(instantes).isoformat(), max(instantes).isoformat()] if instantes else None
    if mes:
        dias = _dias_del_mes(mes)
        esperados = dias * REGISTROS_DIA
        dentro = {c: [f for f in curva if _mes_del_registro(f[0]) == mes] for c, curva in curvas.items()}
        cortos = {c: len(v) for c, v in dentro.items() if len(v) < esperados}
        cubiertos = {(f[0] - PASO).date() for v in dentro.values() for f in v}
        ficha.update(dias=dias, esperados=esperados, incompletos=len(cortos), completo=bool(curvas) and not cortos,
                     dias_con_registro=len(cubiertos))
        fuera: dict[str, int] = {}
        for curva in curvas.values():
            for f in curva:
                m = _mes_del_registro(f[0])
                if m != mes:
                    fuera[m] = fuera.get(m, 0) + 1
        ficha['solape'] = [{'mes': m, 'registros': n, 'libro': (meses_de_otros or {}).get(m)}
                           for m, n in sorted(fuera.items()) if (meses_de_otros or {}).get(m)]
        ficha['mismo_mes'] = (meses_de_otros or {}).get(mes)
    ficha['registros'] = ({'min': min(registros), 'mediana': int(statistics.median(registros)), 'max': max(registros)}
                          if registros else None)
    ficha['en_cero'] = sorted(c for c, curva in curvas.items()
                              if curva and all(not f[1] and not (f[2] or 0) for f in curva))
    previos = None
    if anterior is not None:
        previos = {clave_codigo(c) for c in anterior}
    elif codigos_anteriores is not None:
        previos = {clave_codigo(c) for c in codigos_anteriores}
    if previos is not None:
        propios = {clave_codigo(c): c for c in curvas}
        ficha['mes_previo'] = mes_previo
        ficha['nuevos'] = sorted(v for k, v in propios.items() if k not in previos)
        ficha['faltan'] = sorted(k for k in previos if k not in propios)
    if suministros is not None:
        ficha['sin_suministro'] = sorted(c for c in curvas if clave_codigo(c) not in suministros)
        ficha['suministros'] = nombre_suministros
        if mes and nombre_suministros:
            propio = mes_del_libro_de_suministros(nombre_suministros, int(mes[:4]))
            ficha['mes_suministros'] = propio
            ficha['falta_suministros_del_mes'] = propio != mes
    if anterior is not None and mes:
        r = repite_otro_mes(curvas, anterior)
        ficha['repite'] = r
        ficha['copia_de'] = mes_previo if r['repite'] else None
    return ficha


def verificar_clientes_de_fuente(raiz: Path | str, rel: str, catalogo: Sequence[Mapping[str, Any]],
                                 suministros: Path | str | None = None, alias=ALIAS) -> dict[str, Any]:
    """La verificación de un libro de una carpeta de clientes indexada, con el libro del mes anterior y el de
    suministros leídos aquí: corre entera en el proceso de fondo, que se termina si el operador lanza algo (104:RF-33).
    """
    import logging

    from .demanda_medida import DemandaError, descubrir_libro_suministros

    log = logging.getLogger(__name__)
    raiz = Path(raiz)
    fila = next((x for x in catalogo if x.get('nombre') == rel), {})
    mes = fila.get('mes')
    path = raiz / rel if raiz.is_dir() else raiz
    otros = {x['mes']: x['nombre'] for x in catalogo if x.get('activo') and x.get('mes') and x.get('nombre') != rel}
    anterior, mes_previo = None, None
    if mes:
        mes_previo = mes_anterior(mes)
        previo = otros.get(mes_previo)
        if previo:
            try:
                anterior, _notas = curvas_de_clientes(raiz / previo, None, mes=mes_previo)
            except Exception as exc:  # noqa: BLE001 - sin el mes anterior se verifica lo demás (RF-18)
                log.warning('mes anterior %s: %s', previo, exc)
    codigos, nombre_sum = None, None
    if suministros is not None:
        try:
            libro = Path(suministros)
            libro = descubrir_libro_suministros(libro, alias) if libro.is_dir() else libro
            codigos, nombre_sum = suministros_del_libro(libro, alias), libro.name
        except (DemandaError, OSError, ValueError) as exc:
            log.warning('suministros: %s', exc)
    return verificar_libro_clientes(path, mes, origen=fila.get('origen_mes'), anio=fila.get('anio'),
                                    anterior=anterior, mes_previo=mes_previo, suministros=codigos,
                                    nombre_suministros=nombre_sum, meses_de_otros=otros)


def _lista(codigos: Sequence[str], tope: int = 10) -> str:
    return ', '.join(codigos[:tope]) + (f' y {len(codigos) - tope} más' if len(codigos) > tope else '')


def mensaje_de_clientes(ficha: Mapping[str, Any]) -> str:
    """El aviso de un libro de clientes, como el de la revisión manual (RF-20)."""
    mes = ficha.get('mes')
    if ficha.get('error'):
        return f"{ficha['libro']} de clientes importantes no se pudo leer: {ficha['error']}; los demás siguen."
    if ficha.get('copia_de'):
        este = nombre_de_mes(mes)
        return (f"{este[:1].upper()}{este[1:]} de clientes importantes repite los valores de "
                f"{nombre_de_mes(ficha['copia_de'])}: pida el libro correcto; mientras, {este.split()[0]} no se usa "
                'para la máxima ni para el pronóstico.')
    partes = [f"{ficha.get('clientes', 0)} clientes"]
    if mes is None:
        partes.append('sin mes reconocido: sus hojas «día, hora» no se pueden fechar')
    elif ficha.get('completo'):
        partes.append(f"completo ({ficha['dias']} días)")
    elif 'dias' in ficha:
        partes.append(f"incompleto: {ficha['incompletos']} de {ficha['clientes']} con menos de "
                      f"{ficha['esperados']} registros ({ficha.get('dias_con_registro', 0)} de {ficha['dias']} días)")
    nuevos = ficha.get('nuevos') or []
    sin_sum = set(ficha.get('sin_suministro') or [])
    if nuevos:
        ambos = [c for c in nuevos if c in sin_sum]
        if ambos and len(ambos) == len(nuevos):
            partes.append(f"{len(nuevos)} nuevos sin suministro: {_lista(nuevos)}")
        else:
            partes.append(f"{len(nuevos)} nuevos: {_lista(nuevos)}")
    otros_sin = sorted(sin_sum - set(nuevos))
    if otros_sin:
        partes.append(f"{len(otros_sin)} sin suministro: {_lista(otros_sin)}")
    if ficha.get('faltan'):
        partes.append(f"{len(ficha['faltan'])} del mes anterior que no vienen: {_lista(ficha['faltan'])}")
    if ficha.get('en_cero'):
        partes.append(f"{len(ficha['en_cero'])} con todo en cero: {_lista(ficha['en_cero'])}")
    for s in ficha.get('solape') or []:
        partes.append(f"{s['registros']} registros de {nombre_de_mes(s['mes'])}, que ya da {s['libro']}")
    if ficha.get('mismo_mes'):
        partes.append(f"{ficha['mismo_mes']} es del mismo mes")
    if ficha.get('avisos_lectura'):
        partes.append(f"{len(ficha['avisos_lectura'])} avisos de lectura")
    if ficha.get('falta_suministros_del_mes'):
        partes.append(f"falta el libro de suministros de {nombre_de_mes(mes).split()[0]}")
    return f"Llegó {nombre_de_mes(mes)} de clientes importantes: " + ', '.join(partes[:2]) + (
        ', ' + '; '.join(partes[2:]) if len(partes) > 2 else '')


# --------------------------------------------------------------------------- cabecera
def curvas_de_cabecera_por_hoja(path: Path | str, alias=ALIAS) -> tuple[dict[str, list], list[str]]:
    """La curva (fecha, kW, kVAR) de cada hoja de medición de un libro de cabecera."""
    libro = abrir_libro(path)
    salida, avisos = {}, []
    for hoja in libro.sheet_names:
        registros, usadas = registros_de_hoja(filas_de_hoja(libro, hoja), alias)
        if 'kw' not in usadas or not registros:
            continue
        curva = [(r.fecha, r.valores.get('kw'), r.valores.get('kvar')) for r in registros
                 if isinstance(r.fecha, datetime) and r.valores.get('kw') is not None]
        if len(curva) < len(registros):
            avisos.append(f'{hoja}: {len(registros) - len(curva)} registro(s) sin fecha y hora o sin kW.')
        salida[hoja] = sorted(curva, key=lambda f: f[0])
    return salida, avisos


def verificar_libro_cabecera(path: Path | str, nombre: str | None = None, alias=ALIAS) -> dict[str, Any]:
    """Hojas, meses, meses incompletos y meses repetidos de un libro de cabecera (RF-8, RF-9, RF-17, RF-18)."""
    path = Path(path)
    ficha: dict[str, Any] = {'tipo': 'cabecera', 'libro': nombre or path.name, 'error': None}
    try:
        curvas, avisos = curvas_de_cabecera_por_hoja(path, alias)
    except Exception as exc:  # noqa: BLE001 - se dice y los demás siguen (RF-18)
        ficha['error'] = str(exc) or exc.__class__.__name__
        return ficha
    meses: set[str] = set()
    incompletos: list[dict] = []
    repetidos: list[dict] = []
    for hoja, curva in curvas.items():
        por_mes: dict[str, int] = {}
        for f in curva:
            por_mes[_mes_del_registro(f[0])] = por_mes.get(_mes_del_registro(f[0]), 0) + 1
        meses.update(por_mes)
        ultimo = max(por_mes) if por_mes else None
        for m, n in sorted(por_mes.items()):
            # El último mes de la hoja puede estar en curso: no es un hueco, se dice como periodo.
            if m != ultimo and n < _dias_del_mes(m) * REGISTROS_DIA:
                incompletos.append({'hoja': hoja, 'mes': m, 'registros': n, 'esperados': _dias_del_mes(m) * REGISTROS_DIA})
        repetidos += [{'hoja': hoja, 'mes': m, 'igual_a': a, 'fraccion': round(fr, 4)}
                      for m, a, fr in meses_repetidos_de_serie(curva)]
    instantes = [c[i][0] for c in curvas.values() if c for i in (0, -1)]
    ficha.update(hojas=sorted(curvas), meses=sorted(meses), incompletos=incompletos, repetidos=repetidos,
                 avisos_lectura=avisos,
                 periodo=[min(instantes).isoformat(), max(instantes).isoformat()] if instantes else None)
    if not curvas:
        ficha['error'] = 'ninguna hoja tiene columnas de fecha y kW: no es una medición de cabecera'
    return ficha


def mensaje_de_cabecera(ficha: Mapping[str, Any]) -> str:
    """El aviso de un libro de cabecera (RF-17, RF-20)."""
    if ficha.get('error'):
        return f"{ficha['libro']} de cabecera: {ficha['error']}; los demás siguen."
    meses = ficha.get('meses') or []
    texto = (f"Llegó {ficha['libro']} de cabecera: {len(ficha.get('hojas') or [])} hojas de medición, "
             + (f"de {nombre_de_mes(meses[0])} a {nombre_de_mes(meses[-1])}" if meses else 'sin meses'))
    if ficha.get('incompletos'):
        hojas = sorted({x['hoja'] for x in ficha['incompletos']})
        texto += f"; {len(hojas)} hojas con algún mes incompleto ({_lista(hojas, 5)})"
    por_hoja: dict[str, list[dict]] = {}
    for r in ficha.get('repetidos') or []:
        por_hoja.setdefault(r['hoja'], []).append(r)
    for hoja, rs in por_hoja.items():
        if len(rs) == 1:
            texto += (f"; {hoja} repite en {nombre_de_mes(rs[0]['mes'])} los valores de {nombre_de_mes(rs[0]['igual_a'])}: "
                      'pida el libro correcto y no calibre con ese mes')
        else:
            texto += (f"; {hoja} repite los valores del mes anterior en {', '.join(nombre_de_mes(r['mes']) for r in rs)}: "
                      'pida el libro correcto y no calibre con esos meses')
    return texto + '.'


# --------------------------------------------------------------------------- estado del reconocimiento
NOMBRE_ESTADO = 'libros_nuevos.json'


def leer_estado(carpeta: Path | str) -> dict[str, Any]:
    """El estado del reconocimiento de un espacio (fotos, avisos, libros repetidos, dataset); vacío si no hay."""
    import json

    path = Path(carpeta) / NOMBRE_ESTADO
    try:
        datos = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def guardar_estado(carpeta: Path | str, estado: Mapping[str, Any]) -> None:
    """Se publica de una vez: un corte a mitad deja el estado anterior entero."""
    import json

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = carpeta / (NOMBRE_ESTADO + '.tmp')
    temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    temporal.replace(carpeta / NOMBRE_ESTADO)


def libros_repetidos(carpeta: Path | str) -> dict[str, str]:
    """{ruta relativa: aviso} de los libros de clientes que repiten otro mes (RF-16)."""
    return {str(k): str(v) for k, v in (leer_estado(carpeta).get('repetidos') or {}).items()}
