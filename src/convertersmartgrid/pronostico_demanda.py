"""Pronóstico de demanda de cabecera, clientes fijos y escaladas: un solo módulo (spec 089).

Lleva de los libros que haya en cada carpeta a un pronóstico elegido por backtest. Nada dice qué
meses o libros hay: cada mes llega un libro nuevo y entra solo. Los modelos neuronales y sus puertas
siguen en la 046 (``digital_twin``); un proyecto anterior de la empresa midió a 28 días un WAPE mediano
de 32,7 % con ML recursivo frente a 21,0 % de un perfil anclado y 17,0 % del semanal: por eso aquí
compiten los perfiles y se mide lejos, no a un paso.

Nunca cambia la curva de la calibración ni de las obras (089:RF-28): limpia una copia para entrenar.
"""
from __future__ import annotations

from bisect import bisect_left
import csv
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np

from .cabecera_ancha import libros_de
from .demanda_medida import (
    ALIAS,
    Cabecera,
    DemandaError,
    abrir_libro,
    base_del_medidor,
    buscar_cabecera,
    catalogar_libros_clientes,
    clave_codigo,
    curva_de_demanda,
    curvas_de_clientes,
    descubrir_libro_suministros,
    filas_de_hoja,
    indexar_libro_cabecera,
    leer_suministros,
    maximas,
    normalizar,
    numero,
    partir_medidores,
    texto_de_celda,
)
from .digital_twin.pronostico import Objetivo
from .perfil_empresa import PerfilError, centrales_termicas, datos_perfil

Curva = Sequence[tuple[datetime, float, float | None]]

#: Hasta aquí es media tensión; por encima, una fila del libro no es un alimentador (089:RF-8, RF-9).
MEDIA_TENSION_MAX_KV = 35.0
#: Fracción de kW negativo desde la que el medidor está en sentido contrario, y por encima de la cual
#: la serie va en ambos sentidos (089:RF-18, RF-20). Por debajo, unos pocos negativos en una serie normal.
SENTIDO_INVERTIDO, SENTIDO_AMBOS = .95, .05
DIAS_DEL_SENTIDO = 60
DIAS_BAJA_CLIENTE = 45
#: Días a cada lado del primer dato de un cliente para ver si la cabecera subió con él, y qué parte de su consumo debe subir para
#: darlo por nuevo. Si sube menos, la carga ya estaba y lo que empezó fue su libro (089:RF-82 y RF-83).
DIAS_ESCALON_CLIENTE = 14
FRACCION_ESCALON_CLIENTE = .5
#: Por debajo de esta parte de la cabecera, el escalón de un cliente no se distingue del ruido: un cliente pequeño recién aparecido no
#: puede borrar la historia de su alimentador (089:RF-84).
FRACCION_CLIENTE_PEQUENO = .2
#: 4 horas idénticas son un medidor congelado (089:RF-22), como midió el proyecto anterior.
TRAMO_CONGELADO = 16
#: Mediana móvil de 7 días y 6 desviaciones robustas (089:RF-24). Un atípico sostenido es otro nivel.
VENTANA_ATIPICOS, UMBRAL_ATIPICOS = 672, 6.0
MAX_FRACCION_NO_OPERATIVA = .5
MAX_DIFERENCIA_APOYO = .02
MEJORA_MINIMA_TEMPERATURA = .01
METODOS = ('semanal', 'perfil_calendario', 'perfil_anclado')
CON_TEMPERATURA = 'anclado_temperatura'
HORIZONTE_DIAS, ORIGENES, HISTORIA_MINIMA_DIAS, PASOS_DESFASE = 28, 3, 28, 4


class CurvaCompacta(Sequence):
    """Una curva en arreglos, que se recorre como la lista de tuplas de siempre (089:RF-70).

    Con cientos de series y años de 15 minutos, una tupla con su fecha por registro agotó la memoria al leer los libros de
    clientes de un año más: 16 GB no bastaban. Un NaN de la Q es un registro sin kVAR.
    """

    __slots__ = ('t', 'columnas')

    def __init__(self, t: np.ndarray, *columnas: np.ndarray):
        self.t = np.asarray(t, dtype='datetime64[ns]')
        self.columnas = tuple(np.asarray(x, dtype=float) for x in columnas)

    def __len__(self) -> int:
        return len(self.t)

    def __getitem__(self, i):
        if isinstance(i, slice):
            return CurvaCompacta(self.t[i], *(x[i] for x in self.columnas))
        valores = [float(x[i]) for x in self.columnas]
        return (self.t[i].astype('datetime64[us]').item(), valores[0], *(None if math.isnan(v) else v for v in valores[1:]))

    def __eq__(self, otra) -> bool:
        return len(self) == len(otra) and list(self) == list(otra)

    __hash__ = None

    @property
    def bytes_por_registro(self) -> int:
        return 8 + 8 * len(self.columnas)

    @classmethod
    def desde(cls, filas: Sequence) -> 'CurvaCompacta':
        """Desde tuplas ``(t, kW)`` o ``(t, kW, kVAR)``, con ``None`` como hueco de la Q."""
        if isinstance(filas, cls):
            return filas
        if not len(filas):
            return cls(np.zeros(0, dtype='datetime64[ns]'), np.zeros(0))
        t = np.array([f[0] for f in filas], dtype='datetime64[ns]')
        return cls(t, *(np.array([np.nan if f[k] is None else f[k] for f in filas], dtype=float) for k in range(1, len(filas[0]))))


@dataclass(frozen=True)
class Fuentes:
    """Dónde están los datos: carpetas que crecen cada mes y libros de referencia."""

    cabecera: Path | Sequence[Path]
    equivalencia: Path
    clientes: Path | None = None
    suministros: Path | None = None
    apoyo: Path | None = None
    apoyo_clientes: Path | None = None
    exogenas: Path | None = None
    patron_clientes: str | Sequence[str] | None = None
    #: Solo estos alimentadores (031:RF-13): los libros de una empresa pesan cientos de MB, y proyectar un sistema no
    #: exige leer los clientes de los demás.
    alimentadores: Sequence[str] | None = None


@dataclass(frozen=True)
class Punto:
    """Una fila del libro alimentador–medidor."""

    codigo: str
    medidores: tuple[str, ...]
    kv: float
    set: str
    clase: str


@dataclass
class Exogenas:
    no_laborables: set[date] = field(default_factory=set)
    temperatura: Mapping[datetime, float] = field(default_factory=dict)
    sin_norma: list[date] = field(default_factory=list)

    @cached_property
    def dias_no_laborables(self) -> np.ndarray:
        return np.array(sorted(self.no_laborables), dtype='datetime64[D]')

    @cached_property
    def serie_temperatura(self):
        import pandas as pd

        return pd.Series(dict(self.temperatura), dtype=float).sort_index()


@dataclass
class Dataset:
    objetivos: list[Objetivo]
    apartados: list[dict]
    libros: list[dict]
    ultimo_dato: dict[str, str]
    exogenas: Exogenas | None = None
    huella: str = ''
    avisos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- equivalencia
def equivalencias(ruta: Path | str, alias=ALIAS) -> tuple[list[Punto], list[dict]]:
    """Las filas del libro con su clase (089:RF-6 a RF-10), por el código y la tensión.

    No por la SET: «CL» (cliente en alta tensión) es de una empresa, y a más de 35 kV una fila ya no es
    un alimentador en ninguna.
    """
    libro = abrir_libro(ruta)
    for hoja in libro.sheet_names:
        filas = filas_de_hoja(libro, hoja)
        hallada = buscar_cabecera(filas, ('alimentador', 'medidor', 'nivel', 'siglas'), alias, ('alimentador', 'medidor'))
        if hallada is None:
            continue
        i, cols = hallada
        puntos, apartados = [], []
        for fila in filas[i + 1:]:
            codigo = texto_de_celda(fila, cols['alimentador'])
            medidor = texto_de_celda(fila, cols['medidor'])
            kv = numero(fila[cols['nivel']]) if 'nivel' in cols and cols['nivel'] < len(fila) else None
            if not codigo and not medidor:
                continue
            if not medidor or not codigo:
                apartados.append({'objetivo': f'equivalencia:{codigo or medidor}', 'motivo': 'la fila no dice su medidor o su código'})
            elif kv is None:
                apartados.append({'objetivo': f'equivalencia:{codigo}', 'motivo': 'la fila no dice su tensión'})
            else:
                es_barra = normalizar(codigo).startswith('barra')
                clase = 'barra' if es_barra else 'alimentador' if kv <= MEDIA_TENSION_MAX_KV else 'transmision'
                sigla = texto_de_celda(fila, cols['siglas']) if 'siglas' in cols else ''
                puntos.append(Punto(codigo, tuple(partir_medidores(medidor)), kv, sigla, clase))
        return puntos, apartados
    raise DemandaError(f'{Path(ruta).name}: ninguna hoja tiene columnas de alimentador y medidor.')


# --------------------------------------------------------------------------- lectura de cabecera
def _unir_libros(rutas: Iterable[Path], medidores: Sequence[str], alimentador: str, abiertas: dict[Path, Cabecera]):
    """Las curvas de los medidores de un alimentador en todos los libros (089:RF-1, RF-2, RF-12).

    El mes nuevo llega en otro libro, y ``Cabecera.maxima`` se queda con un solo libro por medidor, que es lo
    que pide la máxima de un periodo. ``maximas`` junta los canales sin hoja (IN111_V19 es otro canal de
    IN111). A igual instante manda el libro modificado más tarde, el que trae la corrección.
    """
    puntos: dict[str, dict[datetime, tuple[float, float | None]]] = {}
    avisos, nombres, errores = [], [], {}
    for ruta in sorted(rutas, key=lambda p: p.stat().st_mtime_ns):
        cabecera = abiertas.setdefault(ruta, Cabecera([ruta]))
        for r in maximas([ruta], [(alimentador, m) for m in medidores], cabecera=cabecera):
            if r.error or not r.curva:
                errores.setdefault(r.medidor, r.error or 'sin curva')
                # Que un libro no lo tenga no dice nada; que tenga la hoja vacía, sí: dice más que los demás.
                if 'no está en ningún libro' not in (r.error or ''):
                    errores[r.medidor] = r.error or 'sin curva'
                continue
            nombres.append(r.libro)
            avisos += r.avisos
            puntos.setdefault(r.canal_de or r.medidor, {}).update((t, (p, q)) for t, p, q in r.curva)
    leidos = {clave_codigo(k) for k in puntos}
    bases = {clave_codigo(base_del_medidor(k) or k) for k in puntos}
    faltan = [m for m in medidores if clave_codigo(m) not in leidos and clave_codigo(base_del_medidor(m) or m) not in bases | leidos]
    curvas = [[(t, *serie[t]) for t in sorted(serie)] for serie in _fundir_canales(puntos).values()]
    # Una hoja vacía o sin kW en un libro, con el medidor bien en otros, no se calla (089:RF-75).
    avisos += [f'{m}: {e}' for m, e in errores.items() if m not in faltan and 'no está en ningún libro' not in e]
    return curvas, nombres, avisos, [(m, errores.get(m, 'sin curva')) for m in faltan]


def _fundir_canales(puntos: dict[str, dict]) -> dict[str, dict]:
    """El mismo punto con otro nombre en otro libro («IN1_V18» e «IN1»): sin apenas instantes comunes se unen (089:RF-77)."""
    salida: dict[str, dict] = {}
    por_base: dict[str, str] = {}
    for clave, serie in puntos.items():
        base = clave_codigo(base_del_medidor(clave) or clave)
        previa = por_base.get(base)
        if previa is not None and len(set(salida[previa]) & set(serie)) < .01 * min(len(salida[previa]), len(serie)) + 1:
            salida[previa].update(serie)
            continue
        por_base.setdefault(base, clave)
        salida[clave] = dict(serie)
    return salida


def _sumar(curvas: Sequence[Curva]) -> list[tuple[datetime, float, float | None]]:
    """Varias curvas de un alimentador en sus instantes comunes (089:RF-12)."""
    if len(curvas) == 1:
        return list(curvas[0])
    por = [{t: (p, q) for t, p, q in c} for c in curvas]
    comunes = sorted(set.intersection(*(set(d) for d in por)))
    salida = []
    for t in comunes:
        qs = [d[t][1] for d in por]
        salida.append((t, sum(d[t][0] for d in por), None if any(q is None for q in qs) else sum(qs)))
    return salida


def curvas_de_cabecera(rutas: Iterable[Path | str], pares=None, *, centrales=None) -> tuple[dict[str, dict], list[dict]]:
    """``{alimentador: {curva, fuente}}``, con la central descontada si se declara (089:RF-13)."""
    libros = libros_de(rutas)
    if pares is None:
        pares = list(dict.fromkeys((h, h) for p in libros for h in indexar_libro_cabecera(p)['hojas']))
    centrales = dict(centrales or {})
    por_alimentador: dict[str, list[str]] = {}
    for alimentador, medidor in pares:
        por_alimentador.setdefault(alimentador, []).append(medidor)
    abiertas: dict[Path, Cabecera] = {}
    salida, apartados = {}, []
    for alimentador, medidores in por_alimentador.items():
        curvas, nombres, avisos, faltan = _unir_libros(libros, medidores, alimentador, abiertas)
        if faltan or not curvas:
            m, motivo = faltan[0] if faltan else (medidores[0], 'sin curva')
            # Sin uno de sus medidores, la suma se quedaría corta y parecería menos demanda.
            apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': f'{m}: {motivo}'})
            continue
        curva = _sumar(curvas)
        if not curva:
            apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': 'sus medidores no tienen instantes comunes'})
            continue
        ultimo = max(c0[-1][0] for c0 in curvas)
        if curva[-1][0] < ultimo:
            avisos.append(f'cabecera:{alimentador}: la suma de sus medidores llega hasta {curva[-1][0]}, uno sigue hasta {ultimo} (089:RF-76)')
        central = centrales.get(alimentador)
        if central:
            otros = [_unir_libros(libros, [central[k]], alimentador, abiertas)[0] for k in ('generacion', 'llegada', 'salida')]
            if not all(otros):
                apartados.append({'objetivo': f'cabecera:{alimentador}',
                                  'motivo': 'falta la curva de un medidor de la central; no se pronostica sin descontarla'})
                continue
            curva, informe = curva_de_demanda(curva, otros[0][0], otros[1][0], otros[2][0])
            # 089:RF-78: con el balance roto, la calibración va sin la central; aquí no se entrena con otra serie sin decirlo.
            if not curva or 'balance' in (informe.error or ''):
                apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': f'sin demanda con la central: {informe.error}'})
                continue
        salida[alimentador] = {'curva': curva, 'fuente': {
            'medidor': ' + '.join(medidores), 'libros': sorted(set(nombres)),
            'central_descontada': bool(central), 'avisos': avisos}}
    for cabecera in abiertas.values():
        apartados += [{'objetivo': f'libro:{ruta.name}', 'motivo': motivo, 'libro_roto': True} for ruta, motivo in cabecera.rotos.items()]
    return salida, apartados


def _objetivos_kw_kvar(clase: str, ident: str, curva: Curva, fuente: dict) -> list[Objetivo]:
    """kW y kVAR de una misma curva ``(t, kW, kVAR)``; el kVAR solo si el libro lo trae."""
    c3 = CurvaCompacta.desde(curva)
    salida = [Objetivo(clase, ident, 'kW', 'kW', CurvaCompacta(c3.t, c3.columnas[0]), fuente)]
    hay_q = np.isfinite(c3.columnas[1]) if len(c3.columnas) > 1 else np.zeros(len(c3), dtype=bool)
    if hay_q.any():
        salida.append(Objetivo(clase, ident, 'kVAR', 'kVAR', CurvaCompacta(c3.t[hay_q], c3.columnas[1][hay_q]), fuente))
    return salida


# --------------------------------------------------------------------------- limpieza
def sentido_de_serie(kw: np.ndarray) -> str:
    """``invertido``, ``ambos`` o ``normal``, por la fracción negativa de lo distinto de cero (089:RF-18, RF-20).

    En los libros reales hay medidores con el kW negativo en más del 98 % de los registros, instalados en
    sentido contrario, y centrales y baterías que van en los dos sentidos. Un corte en cero no dice
    hacia dónde va la potencia.
    """
    valores = np.asarray(kw, dtype=float)
    distintos = valores[np.isfinite(valores) & (valores != 0)]
    if not len(distintos):
        return 'normal'
    negativa = float((distintos < 0).mean())
    return 'invertido' if negativa >= SENTIDO_INVERTIDO else 'ambos' if negativa > SENTIDO_AMBOS else 'normal'


def _orientar(curva: Curva) -> tuple[Curva, str, int]:
    """La curva en el sentido de la carga y los registros contrarios quitados (089:RF-18, RF-20, RF-54).

    Se juzga por lo reciente: un alimentador real iba al revés hasta julio y desde agosto no da un solo negativo, y
    juzgado por todo el año se apartaba como si generase. Lo antiguo contrario no es su demanda de hoy.
    """
    if not len(curva):
        return curva, 'normal', 0
    corte = curva[-1][0] - timedelta(days=DIAS_DEL_SENTIDO)
    sentido = sentido_de_serie(np.array([p for t, p, _q in curva if t >= corte], dtype=float))
    if sentido == 'ambos':
        return curva, sentido, 0
    if sentido == 'invertido':
        curva = [(t, -p, None if q is None else -q) for t, p, q in curva]
    limpia = [fila for fila in curva if fila[1] >= 0]
    return limpia, sentido, len(curva) - len(limpia)


MOTIVO_AMBOS = 'flujo en ambos sentidos: no es una serie de demanda; declare su central si la tiene'


def objetivos_de_cabecera(rutas, pares=None, *, centrales=None) -> tuple[list[Objetivo], list[dict]]:
    """kW y kVAR de cada ``(alimentador, medidor)``, en el sentido de la carga (046:RF-9, RF-10; 089:RF-18 a RF-21)."""
    curvas, apartados = curvas_de_cabecera(rutas, pares, centrales=centrales)
    objetivos = []
    for alimentador, d in curvas.items():
        curva, sentido, contrarios = _orientar(d['curva'])
        if sentido == 'ambos':
            apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': MOTIVO_AMBOS})
            continue
        objetivos += _objetivos_kw_kvar('cabecera', alimentador, curva, {**d['fuente'], 'sentido_invertido': sentido == 'invertido',
                                                                         'registros_contrarios': contrarios})
    return objetivos, apartados


def _marcar_atipicos(p: np.ndarray) -> np.ndarray:
    """Aislados frente a lo anterior a cada registro: lo posterior no cambia qué se marca (089:RF-24)."""
    import pandas as pd

    s = pd.Series(p)
    previa = s.shift(1)
    minimo = max(24, VENTANA_ATIPICOS // 7)
    mediana = previa.rolling(VENTANA_ATIPICOS, min_periods=minimo).median()
    escala = 1.4826 * (previa - mediana).abs().rolling(VENTANA_ATIPICOS, min_periods=minimo).median().replace(0, np.nan)
    candidato = ((s - mediana).abs() > UMBRAL_ATIPICOS * escala).fillna(False)
    # Más de 2 en 8 registros no son atípicos: es un cambio de nivel, y la mediana lo alcanzará.
    previos = candidato.shift(1, fill_value=False).astype(float).rolling(8, min_periods=1).sum()
    return (candidato & previos.lt(2)).to_numpy(dtype=bool)


def limpiar_curva(curva: Curva, clase: str) -> tuple[list, dict[str, int]]:
    """Una copia sin los registros que no son demanda, sin rellenarlos (089:RF-22 a RF-24, RF-26, RF-27).

    Un cliente parado sí consume cero; un alimentador en cero está cortado.
    """
    curva = list(curva)
    p = np.array([v for _t, v, _q in curva], dtype=float)
    informe = {'cero': 0, 'congelado': 0, 'atipico': 0}
    if not len(p):
        return curva, informe
    ceros = (p == 0) if clase == 'cabecera' else np.zeros(len(p), dtype=bool)
    cambios = np.flatnonzero(np.diff(p) != 0)
    inicios, fines = np.r_[0, cambios + 1], np.r_[cambios + 1, len(p)]
    congelado = np.zeros(len(p), dtype=bool)
    for a, b in zip(inicios, fines, strict=True):
        if b - a >= TRAMO_CONGELADO and p[a] != 0:
            congelado[a:b] = True
    valores = p.copy()
    valores[ceros | congelado] = np.nan
    atipico = _marcar_atipicos(valores) & ~(ceros | congelado)
    if clase != 'cabecera':
        # Un cliente arranca a tiros y sus puntas son reales: solo sale lo imposible frente a su máximo de los 28 días anteriores.
        import pandas as pd

        maximo = pd.Series(np.abs(valores)).shift(1).rolling(2688, min_periods=96).max().to_numpy()
        atipico &= np.abs(valores) > 3 * np.nan_to_num(maximo, nan=np.inf)
    informe.update(cero=int(ceros.sum()), congelado=int(congelado.sum()), atipico=int(atipico.sum()))
    quitar = ceros | congelado | atipico
    return [fila for fila, q in zip(curva, quitar, strict=True) if not q], informe


# --------------------------------------------------------------------------- clases
def _cliente_ya_estaba(cabecera: Curva, tiempos: Sequence[datetime], cliente: dict, inicio: datetime) -> bool:
    """La cabecera no subió con el primer dato del cliente: su carga ya estaba y lo nuevo es el libro (089:RF-82, RF-83)."""
    ancho = timedelta(days=DIAS_ESCALON_CLIENTE)
    a, b, c = bisect_left(tiempos, inicio - ancho), bisect_left(tiempos, inicio), bisect_left(tiempos, inicio + ancho)
    if a == b or b == c:
        return False                                     # sin cabecera a los dos lados no hay escalón que medir
    antes = sum(cabecera[i][1] for i in range(a, b)) / (b - a)
    despues = sum(cabecera[i][1] for i in range(b, c)) / (c - b)
    suyo = [v[0] for x, v in cliente.items() if inicio <= x < inicio + ancho]
    if not suyo:
        return False
    consumo = sum(suyo) / len(suyo)
    return consumo >= FRACCION_CLIENTE_PEQUENO * despues and despues - antes < FRACCION_ESCALON_CLIENTE * consumo


def escaladas_de(cabecera: Curva, clientes: Sequence[Curva], ultimo_clientes: datetime | None = None, primero_clientes: datetime | None = None) -> list:
    """Cabecera menos fijas, instante a instante (089:RF-30 a RF-32).

    Un instante sin dato de un cliente no se resta como cero: daría una punta falsa. Después de su último dato, su libro va atrasado
    y el instante queda sin dato, salvo que los demás clientes sigan más de 45 días: se dio de baja (089:RF-72). Antes del primero,
    medido en PA217 (cabecera desde 2023, libros desde 2025) y PE102 (cabecera plana y un cliente que aparece en 2026): lo que falta
    casi siempre es el libro, no el cliente, y dar toda la cabecera como escaladas enseña un nivel falso (089:RF-81, RF-82). Un resto
    negativo es ruido de medida de un alimentador casi dedicado, no una escalada que genere. La Q no se recorta: los bancos pueden
    dejarla negativa.
    """
    por = [{t: (p, q) for t, p, q in c} for c in clientes if c]
    rangos = [(min(d), max(d)) for d in por]
    if not por:
        return [(t, max(p, 0.0), q) for t, p, q in cabecera]
    desde = primero_clientes or min(a for a, _b in rangos)
    tiempos = [f[0] for f in cabecera]
    for d, (a, _b) in zip(por, rangos, strict=True):
        if a > desde and _cliente_ya_estaba(cabecera, tiempos, d, a):
            desde = a
    salida = []
    for t, p, q in cabecera[bisect_left(tiempos, desde):]:
        resto_p, resto_q, falta = p, q, False
        for d, (a, b) in zip(por, rangos, strict=True):
            if t in d:
                resto_p -= d[t][0]
                resto_q = None if resto_q is None or d[t][1] is None else resto_q - d[t][1]
            elif t >= a and (t <= b or ultimo_clientes is None or (ultimo_clientes - b) <= timedelta(days=DIAS_BAJA_CLIENTE)):
                falta = True
                break
        if not falta:
            salida.append((t, max(resto_p, 0.0), resto_q))
    return salida


def desfase_de_relojes(cabecera: Curva, fijas: Curva) -> int:
    """Pasos que las fijas van detrás de la cabecera, si se ve claro; si no, 0 (089:RF-34).

    Medido con el cambio de cada serie, no con su nivel: la forma diaria correlaciona con cualquier desfase.
    Se dice y no se corrige: no se sabe qué reloj está mal.
    """
    import pandas as pd

    if not len(cabecera) or not len(fijas):
        return 0
    h = pd.Series({t: p for t, p, _q in cabecera}).diff()
    f = pd.Series({t: p for t, p, _q in fijas}).diff()
    paso = timedelta(minutes=15)
    correlaciones = {}
    for k in range(-PASOS_DESFASE, PASOS_DESFASE + 1):
        par = pd.concat([h, f.shift(freq=-paso * k)], axis=1, join='inner').dropna()
        correlaciones[k] = float(par.iloc[:, 0].corr(par.iloc[:, 1])) if len(par) > 8 else float('nan')
    validas = {k: v for k, v in correlaciones.items() if math.isfinite(v)}
    if not validas:
        return 0
    mejor = max(validas, key=validas.get)
    if mejor and validas[mejor] >= .5 and validas[mejor] >= validas.get(0, -1.0) + .2:
        return mejor
    return 0


def apoyar(base: Curva, apoyo: Curva) -> tuple[list, dict]:
    """La base con el apoyo antes de su primer dato, si coinciden en lo común (089:RF-35, RF-36).

    2026 no llega a un año entero, y otro libro con el mismo nombre de medidor puede ser otro punto.
    """
    base = list(base)
    info: dict[str, Any] = {'usado': False, 'inicio_base': base[0][0] if base else None}
    if not base or not apoyo:
        return base, {**info, 'motivo': 'sin datos de apoyo'}
    propios = {t: p for t, p, _q in base}
    comunes = [(propios[t], p) for t, p, _q in apoyo if t in propios]
    if comunes:
        a = np.array(comunes, dtype=float)
        referencia = float(np.median(np.abs(a[:, 0]))) or 1.0
        diferencia = float(np.median(np.abs(a[:, 0] - a[:, 1]))) / referencia
        info['diferencia_mediana'] = diferencia
        if diferencia > MAX_DIFERENCIA_APOYO:
            return base, {**info, 'motivo': f'el apoyo difiere un {diferencia:.1%} de la base en lo común'}
    else:
        info['aviso'] = 'sin instantes comunes: no se pudo comprobar que sea el mismo medidor'
    anteriores = [fila for fila in apoyo if fila[0] < base[0][0]]
    return [*sorted(anteriores, key=lambda f: f[0]), *base], {**info, 'usado': bool(anteriores)}


def _curvas_por_cliente(libros: Iterable[tuple[Path, str | None]], codigos=None, canonico: Callable[[str], str] = lambda c: c):
    """Las curvas de cada cliente en todos los libros. Dos valores de un instante no se eligen (046:RF-12)."""
    trozos: dict[str, list[CurvaCompacta]] = {}
    de_libro: dict[str, list[str]] = {}
    contradictorios: dict[str, str] = {}
    avisos: dict[str, list[str]] = {}
    apartados: list[dict] = []
    for libro, mes in libros:
        curvas, notas = curvas_de_clientes(libro, codigos, mes=mes)
        if not curvas and not codigos:
            # Un mes que no se puede leer no se calla: el objetivo tendría un hueco sin explicar.
            apartados.append({'objetivo': f'libro:{libro.name}', 'motivo': '; '.join(notas) or 'sin curvas de clientes'})
        for codigo, curva in curvas.items():
            actual = canonico(codigo)
            de_libro.setdefault(actual, []).append(libro.name)
            trozos.setdefault(actual, []).append(CurvaCompacta.desde(curva))
        for nota in notas:
            avisos.setdefault(nota.split(':', 1)[0], []).append(nota)
    por = {}
    for actual, partes in trozos.items():
        por[actual], choque = _unir_trozos(partes)
        if choque is not None:
            contradictorios[actual] = f'{de_libro[actual][-1]} da otro valor en el mismo instante ({str(choque)[:19]})'
    return por, de_libro, contradictorios, avisos, apartados


def _unir_trozos(partes: Sequence[CurvaCompacta]) -> tuple[CurvaCompacta, np.datetime64 | None]:
    """Los meses de un cliente en orden; lo repetido igual se une, y dos valores de un instante se dicen (046:RF-12)."""
    t = np.concatenate([x.t for x in partes])
    p = np.concatenate([x.columnas[0] for x in partes])
    q = np.concatenate([x.columnas[1] if len(x.columnas) > 1 else np.full(len(x), np.nan) for x in partes])
    orden = np.argsort(t, kind='stable')
    t, p, q = t[orden], p[orden], q[orden]
    repetido = np.r_[False, t[1:] == t[:-1]]
    distinto = repetido & ~((p == np.r_[np.nan, p[:-1]]) & ((q == np.r_[np.nan, q[:-1]]) | (np.isnan(q) & np.isnan(np.r_[np.nan, q[:-1]]))))
    return CurvaCompacta(t[~repetido], p[~repetido], q[~repetido]), (t[distinto][0] if distinto.any() else None)


def objetivos_de_clientes(rutas, codigos=None) -> tuple[list[Objetivo], list[dict]]:
    """kW y kVAR de cada cliente libre desde sus hojas de 15 minutos (046:RF-11, RF-12)."""
    por, de_libro, contradictorios, avisos, apartados = _curvas_por_cliente([(p, None) for p in libros_de(rutas)], codigos)
    objetivos = []
    for codigo, serie in por.items():
        if codigo in contradictorios:
            apartados.append({'objetivo': f'cliente:{codigo}', 'motivo': contradictorios[codigo]})
            continue
        objetivos += _objetivos_kw_kvar('cliente', codigo, serie, {'libros': de_libro[codigo], 'avisos': avisos.get(codigo, [])})
    for codigo in codigos or ():
        if codigo not in por:
            apartados.append({'objetivo': f'cliente:{codigo}', 'motivo': 'no está en el maestro de ningún libro'})
    return objetivos, apartados


# --------------------------------------------------------------------------- dataset
def _ficha_de_libro(p: Path) -> dict:
    s = p.stat()
    return {'libro': p.name, 'bytes': s.st_size, 'modificado': datetime.fromtimestamp(s.st_mtime).isoformat(timespec='seconds')}


def _libros_con_mes(carpeta: Path, patron) -> tuple[list[tuple[Path, str | None]], list[str]]:
    """Los libros de clientes y su mes, sin lista fija; de los duplicados de un mes, el más reciente (013:RF-5).

    Lo que no se usa se dice (089:RF-75)."""
    salida, sin_uso = [], []
    for x in catalogar_libros_clientes(carpeta, patron):
        # Un libro sin mes en el nombre sigue valiendo si sus hojas traen la fecha (disposición moderna).
        descartado = any('no se usa' in a for a in x.avisos) or any('duplicados' in a for a in x.avisos) and not x.activo
        if descartado:
            sin_uso.append(f'{Path(x.path).name}: ' + '; '.join(x.avisos))
        else:
            salida.append((Path(x.path), x.mes))
    return salida, sin_uso


def _renumeracion(ruta: Path | None) -> tuple[Callable[[str], str], dict[str, str]]:
    """El código actual de cada cliente y su alimentador (089:RF-16, RF-17)."""
    if ruta is None:
        return (lambda c: c), {}
    libro = descubrir_libro_suministros(ruta) if Path(ruta).is_dir() else Path(ruta)
    suministros, _avisos = leer_suministros(libro)
    actuales, radiales = {}, {}
    for s in suministros:
        actual = s.actual or s.anterior
        for codigo in (s.actual, s.anterior):
            if codigo:
                actuales.setdefault(clave_codigo(codigo), actual)
        radiales.setdefault(clave_codigo(actual), s.radial)
    return (lambda c: actuales.get(clave_codigo(c), c)), radiales


def _codigos_de(ruta: Path | None, pedidos: set[str]) -> list[str]:
    """Los códigos, actuales y anteriores, de los suministros de los alimentadores pedidos (031:RF-13)."""
    if ruta is None:
        return []
    libro = descubrir_libro_suministros(ruta) if Path(ruta).is_dir() else Path(ruta)
    return [c for s in leer_suministros(libro)[0] if clave_codigo(s.radial) in pedidos for c in (s.actual, s.anterior) if c]


def _fracciones_no_operativas(curva: Curva) -> float:
    p = np.array([v for _t, v, _q in curva], dtype=float)
    return float((p == 0).mean()) if len(p) else 1.0


def _centrales_del_perfil() -> dict:
    try:
        return centrales_termicas(datos_perfil())
    except PerfilError:
        return {}


def armar_dataset(fuentes: Fuentes) -> Dataset:
    """De las carpetas a los objetivos limpios de las tres clases (089:RF-1 a RF-37)."""
    puntos, apartados = equivalencias(fuentes.equivalencia)
    pedidos = None if fuentes.alimentadores is None else {clave_codigo(a) for a in fuentes.alimentadores}
    pares = [(p.codigo, m) for p in puntos if p.clase == 'alimentador' and (pedidos is None or clave_codigo(p.codigo) in pedidos)
             for m in p.medidores]
    libros_cabecera = libros_de([fuentes.cabecera] if isinstance(fuentes.cabecera, (str, Path)) else fuentes.cabecera)
    fichas = [_ficha_de_libro(p) for p in libros_cabecera]
    leidas, ap = curvas_de_cabecera(libros_cabecera, pares, centrales=_centrales_del_perfil())
    avisos = [f"{a['objetivo']}: {a['motivo']}" for a in ap if a.get('libro_roto')]
    avisos += [a for d0 in leidas.values() for a in d0['fuente']['avisos'] if '089:RF-7' in a or 'hasta' in a]
    apartados += ap
    de_apoyo: dict[str, dict] = {}
    if fuentes.apoyo:
        libros_apoyo = libros_de([fuentes.apoyo])
        fichas += [_ficha_de_libro(p) for p in libros_apoyo]
        de_apoyo = curvas_de_cabecera(libros_apoyo, pares)[0]

    objetivos: list[Objetivo] = []
    limpias: dict[str, tuple[list, dict]] = {}
    for alimentador, d in leidas.items():
        if _fracciones_no_operativas(d['curva']) > MAX_FRACCION_NO_OPERATIVA:
            apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': 'no operativo: más de la mitad de sus registros están en cero'})
            continue
        curva, sentido, contrarios = _orientar(d['curva'])
        if sentido == 'ambos':
            apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': MOTIVO_AMBOS})
            continue
        if not curva:
            apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': 'no operativo: ningún registro en su sentido'})
            continue
        fuente = {**d['fuente'], 'sentido_invertido': sentido == 'invertido', 'registros_contrarios': contrarios,
                  'inicio_base': curva[0][0].isoformat()}
        if alimentador in de_apoyo and not d['fuente']['central_descontada']:
            orientada, _s, _c = _orientar(de_apoyo[alimentador]['curva'])
            curva, info = apoyar(curva, orientada)
            fuente['apoyo'] = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in info.items()}
        limpia, informe = limpiar_curva(curva, 'cabecera')
        limpia = CurvaCompacta.desde(limpia)
        fuente['limpieza'] = informe
        objetivos += _objetivos_kw_kvar('cabecera', alimentador, limpia, fuente)
        limpias[alimentador] = (limpia, fuente)

    por_alimentador: dict[str, list[list]] = {}
    if fuentes.clientes:
        libros, sin_uso = _libros_con_mes(fuentes.clientes, fuentes.patron_clientes)
        avisos += sin_uso
        fichas += [_ficha_de_libro(p) for p, _m in libros]
        canonico, radiales = _renumeracion(fuentes.suministros)
        codigos = None if pedidos is None else _codigos_de(fuentes.suministros, pedidos)
        por, de_libro, contradictorios, avisos_cli, ap = _curvas_por_cliente(libros, codigos, canonico=canonico)
        apartados += ap
        por_apoyo: dict[str, dict] = {}
        if fuentes.apoyo_clientes:
            libros_apoyo, sin_uso = _libros_con_mes(fuentes.apoyo_clientes, fuentes.patron_clientes)
            avisos += sin_uso
            fichas += [_ficha_de_libro(p) for p, _m in libros_apoyo]
            por_apoyo = _curvas_por_cliente(libros_apoyo, codigos, canonico=canonico)[0]
        for codigo, serie in por.items():
            if codigo in contradictorios:
                # 089:RF-74: fuera como objetivo, pero su carga sigue en el alimentador.
                apartados.append({'objetivo': f'cliente:{codigo}', 'motivo': contradictorios[codigo]})
                por_alimentador.setdefault(clave_codigo(radiales.get(clave_codigo(codigo), '')), []).append(serie)
                continue
            base = list(serie)
            inicio_base = base[0][0].isoformat() if base else None
            if codigo in por_apoyo:
                base, _info = apoyar(base, list(por_apoyo.pop(codigo)))
            limpia, informe = limpiar_curva(base, 'cliente')
            limpia = CurvaCompacta.desde(limpia)
            del base
            radial = radiales.get(clave_codigo(codigo), '')
            por[codigo] = None                       # lo ya limpio libera su copia
            por_alimentador.setdefault(clave_codigo(radial), []).append(limpia)
            objetivos += _objetivos_kw_kvar('cliente', codigo, limpia, {
                'libros': de_libro[codigo], 'avisos': avisos_cli.get(codigo, []), 'alimentador': radial, 'limpieza': informe,
                'inicio_base': inicio_base})
    # 089:RF-73: sin clientes o sin el libro que los asigna no se puede restar: unas escaladas iguales a la cabecera serían falsas.
    con_escaladas = bool(fuentes.clientes and fuentes.suministros)
    if fuentes.clientes and not fuentes.suministros:
        avisos.append('sin libro de suministros no se sabe de qué alimentador es cada cliente: no se dan escaladas')
    sin_alimentador = len(por_alimentador.get('', []))
    if sin_alimentador:
        avisos.append(f'{sin_alimentador} cliente(s) sin alimentador en el libro de suministros: sus escaladas quedan sin restarlos')
    ultimos = [c0.t[-1] for lista in por_alimentador.values() for c0 in lista if len(c0)]
    ultimo_clientes = max(ultimos).astype('datetime64[us]').item() if ultimos else None
    primeros = [c0.t[0] for lista in por_alimentador.values() for c0 in lista if len(c0)]
    primero_clientes = min(primeros).astype('datetime64[us]').item() if primeros else None
    for alimentador, (limpia, fuente) in (limpias.items() if con_escaladas else ()):
        limpia = list(limpia)
        if not fuentes.apoyo_clientes and fuente.get('inicio_base'):
            inicio = datetime.fromisoformat(fuente['inicio_base'])
            limpia = [f for f in limpia if f[0] >= inicio]    # sin clientes en el apoyo, ahí no se puede restar
        fijas = por_alimentador.get(clave_codigo(alimentador), [])
        extra = {'incluye_bancos': True, 'clientes_fijos': len(fijas)}
        if fijas:
            extra['desfase_de_relojes_pasos'] = desfase_de_relojes(limpia, _sumar_presentes(fijas))
        objetivos += _objetivos_kw_kvar('escaladas', alimentador, escaladas_de(limpia, fijas, ultimo_clientes, primero_clientes), {**fuente, **extra})
    ultimo: dict[str, str] = {}
    for o in objetivos:
        if o.curva:
            ultimo[o.clase] = max(ultimo.get(o.clase, ''), max(t for t, _v in o.curva).isoformat())
    exogenas = leer_exogenas(fuentes.exogenas) if fuentes.exogenas else None
    return Dataset(objetivos, apartados, fichas, ultimo, exogenas, avisos=avisos)


def _sumar_presentes(curvas: Sequence[list]) -> list:
    """La suma de fijas en cada instante con alguna medida, solo para comparar relojes."""
    total: dict[datetime, float] = {}
    for c in curvas:
        for t, p, _q in c:
            total[t] = total.get(t, 0.0) + p
    return [(t, total[t], None) for t in sorted(total)]


# --------------------------------------------------------------------------- exógenas
def _verdadero(texto: Any) -> bool:
    return str(texto).strip().casefold() in ('true', '1', 'si', 'sí', 'x', 'verdadero')


def leer_exogenas(carpeta: Path | str) -> Exogenas:
    """Calendario y temperatura de la carpeta, reconocidos por sus columnas: el fichero crece sin cambiar de nombre.

    Un fin de semana no se cuenta como no laborable: ya tiene su forma, y un sábado no es un domingo.
    """
    no_laborables: set[date] = set()
    temperatura: dict[datetime, float] = {}
    sin_norma: list[date] = []
    for ruta in sorted(Path(carpeta).rglob('*.csv')):
        with ruta.open(encoding='utf-8-sig', newline='') as f:
            lector = csv.DictReader(f)
            columnas = set(lector.fieldnames or ())
            if {'fecha', 'no_laborable'} <= columnas:
                for fila in lector:
                    if _verdadero(fila['no_laborable']) and not _verdadero(fila.get('fin_semana', '')):
                        dia = date.fromisoformat(fila['fecha'][:10])
                        no_laborables.add(dia)
                        if not (fila.get('norma') or '').strip():
                            sin_norma.append(dia)
            elif {'fecha_hora', 'temperatura_c'} <= columnas:
                for fila in lector:
                    valor = numero(fila['temperatura_c'])
                    if valor is not None:
                        temperatura[datetime.fromisoformat(fila['fecha_hora'])] = valor
    return Exogenas(no_laborables, temperatura, sorted(set(sin_norma)))


# --------------------------------------------------------------------------- métodos
def _claves(t: np.ndarray, exogenas: Exogenas | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mes, día de la semana y bloque del día; un no laborable es un domingo (089:RF-44)."""
    import pandas as pd

    indice = pd.DatetimeIndex(t)
    dia = np.asarray(indice.dayofweek)
    if exogenas is not None and len(exogenas.dias_no_laborables):
        dia = np.where(np.isin(np.asarray(t, dtype='datetime64[D]'), exogenas.dias_no_laborables), 6, dia)
    return np.asarray(indice.month), dia, np.asarray(indice.hour * 4 + indice.minute // 15)


def _perfil(t_h: np.ndarray, y_h: np.ndarray, t_f: np.ndarray, exogenas: Exogenas | None, *, con_mes: bool) -> np.ndarray:
    """Mediana por mes, día y bloque, con reserva por día y bloque, y por la mediana de todo."""
    import pandas as pd

    mes_h, dia_h, bloque_h = _claves(t_h, exogenas)
    mes_f, dia_f, bloque_f = _claves(t_f, exogenas)
    h = pd.DataFrame({'mes': mes_h, 'dia': dia_h, 'bloque': bloque_h, 'y': y_h})
    reserva = h.groupby(['dia', 'bloque'])['y'].median()
    f = pd.DataFrame({'mes': mes_f, 'dia': dia_f, 'bloque': bloque_f})
    salida = f.join(reserva.rename('r'), on=['dia', 'bloque'])['r']
    if con_mes:
        fina = h.groupby(['mes', 'dia', 'bloque'])['y'].median()
        salida = f.join(fina.rename('m'), on=['mes', 'dia', 'bloque'])['m'].fillna(salida)
    return salida.fillna(float(np.median(y_h)) if len(y_h) else 0.0).to_numpy(dtype=float)


def _recientes(t: np.ndarray, dias: int) -> np.ndarray:
    return t >= t[-1] - np.timedelta64(dias, 'D')


def _anclado(t_h, y_h, t_f, exogenas) -> np.ndarray:
    """La forma del año por el nivel de los últimos 28 días: los árboles y la recursión pierden el nivel."""
    cerca = _recientes(t_h, HORIZONTE_DIAS)
    antes = _recientes(t_h, 730) & ~cerca
    if antes.sum() < 96:
        return _perfil(t_h[cerca], y_h[cerca], t_f, exogenas, con_mes=False)
    # 089:RF-71: la forma sin los últimos 28 días. Con ellos, sus celdas contienen casi solo esos mismos registros, el factor sale
    # cerca de 1 y un escalón de +40 % no se ve: lo halló la revisión del 2026-11-05. El mes solo cuenta con más de un año de
    # historia: si no, la referencia y el futuro caerían en celdas de distinto nivel.
    con_mes = t_h[-1] - t_h[0] >= np.timedelta64(365 + HORIZONTE_DIAS, 'D')
    forma = _perfil(t_h[antes], y_h[antes], t_f, exogenas, con_mes=con_mes)
    referencia = _perfil(t_h[antes], y_h[antes], t_h[cerca], exogenas, con_mes=con_mes)
    media_ref, media_real = float(np.mean(referencia)), float(np.mean(y_h[cerca]))
    factor = media_real / media_ref if media_ref else float('inf')
    if media_ref > 0 and .2 <= factor <= 5:
        return forma * factor
    return forma + (media_real - media_ref)            # la Q cruza el cero con los bancos: un cociente da cualquier cosa


def _clima_futura(t_f: np.ndarray, anterior) -> np.ndarray:
    """La temperatura del futuro no se conoce al emitir: su climatología por mes y hora (046:RF-2, 089:RF-47)."""
    import pandas as pd

    por_mes_hora = anterior.groupby([anterior.index.month, anterior.index.hour]).median()
    por_hora = anterior.groupby(anterior.index.hour).median()
    indice = pd.DatetimeIndex(t_f)
    salida = pd.Series(pd.MultiIndex.from_arrays([indice.month, indice.hour]).map(por_mes_hora), dtype=float)
    salida = salida.fillna(pd.Series(indice.hour.map(por_hora), dtype=float))
    return salida.fillna(float(anterior.median())).to_numpy(dtype=float)


def _anclado_temperatura(t_h, y_h, t_f, exogenas) -> np.ndarray:
    """El perfil anclado más el residuo que explica la temperatura, ajustado antes del origen (089:RF-46, RF-47)."""
    import pandas as pd

    base = _anclado(t_h, y_h, t_f, exogenas)
    serie = exogenas.serie_temperatura if exogenas is not None else None
    if serie is None or not len(serie):
        return base
    anterior = serie[serie.index <= pd.Timestamp(t_h[-1])]
    if len(anterior) < 30 * 24:
        return base
    anio = _recientes(t_h, 365)
    temperatura = pd.Series(pd.DatetimeIndex(t_h[anio])).map(anterior).to_numpy(dtype=float)
    ajuste = _anclado(t_h, y_h, t_h[anio], exogenas)
    ok = np.isfinite(temperatura)
    if ok.sum() < 30 * 96:
        return base
    x = np.c_[np.ones(ok.sum()), temperatura[ok], temperatura[ok] ** 2]
    coef, *_ = np.linalg.lstsq(x, y_h[anio][ok] - ajuste[ok], rcond=None)
    futura = _clima_futura(t_f, anterior)
    return base + np.c_[np.ones(len(futura)), futura, futura ** 2] @ coef


def predecir(metodo: str, t_h: np.ndarray, y_h: np.ndarray, t_f: np.ndarray, exogenas: Exogenas | None = None) -> np.ndarray:
    """La trayectoria de un método con lo observado antes del origen (089:RF-38, RF-39)."""
    t_h, y_h, t_f = np.asarray(t_h, dtype='datetime64[ns]'), np.asarray(y_h, dtype=float), np.asarray(t_f, dtype='datetime64[ns]')
    if metodo == 'semanal':
        cerca = _recientes(t_h, HORIZONTE_DIAS)
        return _perfil(t_h[cerca], y_h[cerca], t_f, exogenas, con_mes=False)
    if metodo == 'perfil_calendario':
        anio = _recientes(t_h, 365)
        return _perfil(t_h[anio], y_h[anio], t_f, exogenas, con_mes=True)
    if metodo == 'perfil_anclado':
        return _anclado(t_h, y_h, t_f, exogenas)
    if metodo == CON_TEMPERATURA:
        return _anclado_temperatura(t_h, y_h, t_f, exogenas)
    raise ValueError(f'método desconocido: {metodo}')


def escala_estacional(t: np.ndarray, y: np.ndarray, dias: int = 7) -> float | None:
    """Error medio de repetir lo de hace una semana, instante con instante; ``None`` si no hay con qué medirlo o da cero (089:RF-85, RF-86).

    Es el denominador del MASE. El WAPE divide por la energía, y una Q que cruza por cero con los bancos tiene una suma pequeña: sus
    cifras no se comparan entre alimentadores. Empareja por fecha, no por posición: un hueco no se compara con otro instante.
    """
    previo = t - np.timedelta64(dias, 'D')
    i = np.minimum(np.searchsorted(t, previo), len(t) - 1) if len(t) else np.zeros(0, dtype=int)
    ok = len(t) > 0 and t[i] == previo
    if not np.any(ok):
        return None
    d = np.abs(y[ok] - y[i[ok]])
    d = d[np.isfinite(d)]
    escala = float(d.mean()) if len(d) else 0.0
    return escala if escala > 1e-9 else None


def medir(y: np.ndarray, p: np.ndarray, escala: float | None = None) -> dict[str, float]:
    """WAPE, RMSE relativo al desvío real, sesgo y MASE, sobre lo observado (089:RF-40, RF-85)."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    ok = np.isfinite(y)
    if not ok.any():
        return {'wape': float('inf'), 'rmse_relativo': float('inf'), 'sesgo': float('nan'), 'n': 0, 'mase': None, 'escala_mase': escala}
    e = p[ok] - y[ok]
    suma, desvio = float(np.abs(y[ok]).sum()), float(y[ok].std())
    rmse = float(np.sqrt(np.mean(e ** 2)))
    return {'wape': float(np.abs(e).sum()) / suma if suma else float('inf'),
            'rmse_relativo': rmse / desvio if desvio else float('inf'), 'sesgo': float(e.mean()), 'n': int(ok.sum()),
            'error_abs': float(np.abs(e).sum()), 'energia': suma, 'mase': float(np.abs(e).mean()) / escala if escala else None, 'escala_mase': escala}


def _arreglos(o: Objetivo) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(o.curva, CurvaCompacta):
        return o.curva.t, o.curva.columnas[0]
    orden = sorted(o.curva, key=lambda f: f[0])
    return np.array([t for t, _v in orden], dtype='datetime64[ns]'), np.array([v for _t, v in orden], dtype=float)


def _malla(desde: np.datetime64, hasta: np.datetime64) -> np.ndarray:
    return np.arange(desde + np.timedelta64(15, 'm'), hasta + np.timedelta64(1, 'm'), np.timedelta64(15, 'm'))


def backtest_objetivo(o: Objetivo, *, horizonte_dias: int = HORIZONTE_DIAS, origenes: int = ORIGENES,
                      exogenas: Exogenas | None = None) -> dict:
    """Compite los métodos en orígenes sucesivos, elige sin el último y mide en él (089:RF-38 a RF-43, RF-48, RF-49)."""
    t, y = _arreglos(o)
    base = {'objetivo': o.nombre, 'clase': o.clase, 'magnitud': o.magnitud, 'horizonte_dias': horizonte_dias}
    if len(t) < 2:
        return {**base, 'status': 'HISTORIA_INSUFICIENTE', 'motivo': 'sin registros'}
    inicio = np.datetime64(o.fuente.get('inicio_base')) if o.fuente.get('inicio_base') else t[0]
    h = np.timedelta64(horizonte_dias, 'D')
    candidatos = [t[-1] - h * k for k in range(1, origenes + 1)]
    fechas = sorted(c for c in candidatos if c >= inicio and c - t[0] >= np.timedelta64(HISTORIA_MINIMA_DIAS, 'D'))
    if len(fechas) < 2:
        return {**base, 'status': 'HISTORIA_INSUFICIENTE',
                'motivo': f'no llega a dos orígenes de {horizonte_dias} días con {HISTORIA_MINIMA_DIAS} días anteriores'}
    metodos = list(METODOS)
    hay_temperatura = exogenas is not None and bool(len(exogenas.temperatura))
    if hay_temperatura:
        metodos.append(CON_TEMPERATURA)
    por_origen: dict[str, list[dict]] = {m: [] for m in metodos}
    residuos: dict[str, list[np.ndarray]] = {m: [] for m in metodos}
    for origen in fechas:
        antes = t <= origen
        futuro = _malla(origen, origen + h)
        posicion = np.searchsorted(futuro, t[(t > origen) & (t <= origen + h)])
        real = np.full(len(futuro), np.nan)
        real[posicion] = y[(t > origen) & (t <= origen + h)]
        escala = escala_estacional(t[antes], y[antes])       # 089:RF-87: solo con lo anterior al origen
        for m in metodos:
            p = predecir(m, t[antes], y[antes], futuro, exogenas)
            por_origen[m].append(medir(real, p, escala))
            residuos[m].append((real - p)[np.isfinite(real)])
    # 089:RF-80: un origen sin dato no vuelve infinito a todos los métodos, que entonces se elegirían por su orden.
    utiles = [i for i in range(len(fechas) - 1) if all(math.isfinite(por_origen[m][i]['wape']) for m in metodos)]
    if not utiles:
        return {**base, 'status': 'HISTORIA_INSUFICIENTE', 'motivo': 'ningún origen de elección tiene datos con que medir'}
    seleccion = {m: float(np.mean([por_origen[m][i]['wape'] for i in utiles])) for m in metodos}
    temperatura: dict[str, Any] = {'usada': False}
    if hay_temperatura:
        anclado = seleccion['perfil_anclado']
        mejora = 1 - seleccion[CON_TEMPERATURA] / anclado if anclado and math.isfinite(anclado) else 0.0
        temperatura = {'usada': mejora >= MEJORA_MINIMA_TEMPERATURA, 'mejora_wape': mejora}
        if not temperatura['usada']:
            seleccion.pop(CON_TEMPERATURA)
    elegido = min(seleccion, key=seleccion.get)
    errores = np.concatenate(residuos[elegido][:-1])
    prueba = {m: por_origen[m][-1] for m in seleccion}
    return {**base, 'status': 'EVALUADO', 'metodo': elegido, 'seleccion': seleccion, 'prueba': prueba, 'error_prueba': prueba[elegido],
            'origenes_seleccion': [str(x)[:19] for x in fechas[:-1]], 'origen_prueba': str(fechas[-1])[:19],
            'temperatura': temperatura,
            'residuos': {'q05': float(np.quantile(errores, .05)), 'q95': float(np.quantile(errores, .95))} if len(errores) else None}


def _sin_infinitos(valor: Any) -> Any:
    """Un error sin definir queda en ``None`` en el informe: un origen sin energía da WAPE infinito, y JSON no lo admite."""
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, dict):
        return {k: _sin_infinitos(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sin_infinitos(v) for v in valor]
    return valor


def backtest(dataset: Dataset, *, horizonte_dias: int = HORIZONTE_DIAS, origenes: int = ORIGENES,
             progreso: Callable[[int, int, str], None] = lambda *_a: None) -> dict:
    """El backtest de todos los objetivos, con el resumen por clase y método."""
    resultados = []
    for i, o in enumerate(dataset.objetivos, start=1):
        progreso(i, len(dataset.objetivos), o.nombre)
        resultados.append(backtest_objetivo(o, horizonte_dias=horizonte_dias, origenes=origenes, exogenas=dataset.exogenas))
    resumen: dict[str, dict] = {}
    for r in resultados:
        c = resumen.setdefault(f"{r['clase']}|{r['magnitud']}", {'objetivos': 0, 'insuficientes': 0, 'elegidos': {}, 'wape_prueba': {}, 'mase_prueba': {}, '_suma': {}})
        c['objetivos'] += 1
        if r['status'] != 'EVALUADO':
            c['insuficientes'] += 1
            continue
        c['elegidos'][r['metodo']] = c['elegidos'].get(r['metodo'], 0) + 1
        for m, x in (*r['prueba'].items(), ('elegido', r['error_prueba'])):
            if x['n'] and math.isfinite(x['wape']):
                c['wape_prueba'].setdefault(m, []).append(x['wape'])
                suma = c['_suma'].setdefault(m, [0.0, 0.0])
                suma[0] += x['error_abs']
                suma[1] += x['energia']
                if x.get('mase') is not None:
                    c['mase_prueba'].setdefault(m, []).append(x['mase'])
    for c in resumen.values():
        # La mediana da el mismo peso a un alimentador casi dedicado, con un resto de escaladas casi nulo y WAPE
        # cerca de 1, que a uno grande; el ponderado dice cuánta energía se yerra (089:RF-53).
        c['wape_prueba'] = {m: float(np.median(v)) for m, v in c['wape_prueba'].items()}
        c['wape_ponderado'] = {m: e / s for m, (e, s) in c.pop('_suma').items() if s}
        c['mase_prueba'] = {m: float(np.median(v)) for m, v in c['mase_prueba'].items()}
    apoyos = [o.fuente['apoyo'] for o in dataset.objetivos if o.clase == 'cabecera' and o.magnitud == 'kW' and 'apoyo' in o.fuente]
    return {'status': 'EVALUADO', 'horizonte_dias': horizonte_dias, 'resumen': resumen, 'resultados': _sin_infinitos(resultados),
            'apoyo': {'usado': sum(bool(a.get('usado')) for a in apoyos), 'rechazado': sum(not a.get('usado') for a in apoyos),
                      'motivos': sorted({str(a.get('motivo')) for a in apoyos if a.get('motivo')})[:10]},
            'apartados': dataset.apartados, 'avisos': dataset.avisos, 'libros': dataset.libros, 'ultimo_dato': dataset.ultimo_dato,
            'exogenas_sin_norma': [d.isoformat() for d in dataset.exogenas.sin_norma] if dataset.exogenas else []}


def pronosticar(o: Objetivo, evaluado: Mapping, *, dias: int = HORIZONTE_DIAS, exogenas: Exogenas | None = None) -> list[dict]:
    """Las filas del pronóstico con el método elegido, con su marca (089:RF-50, RF-51; 046:RF-20)."""
    if evaluado.get('status') != 'EVALUADO':
        return []
    t, y = _arreglos(o)
    futuro = _malla(t[-1], t[-1] + np.timedelta64(dias, 'D'))
    p = predecir(evaluado['metodo'], t, y, futuro, exogenas)
    r = evaluado.get('residuos') or {'q05': 0.0, 'q95': 0.0}
    emision = str(t[-1])[:19]
    return [{'target': o.nombre, 'clase': o.clase, 'magnitud': o.magnitud, 'unit': o.unidad, 'emission_time': emision,
             'forecast_time': str(f)[:19], 'horizon_steps': i, 'horizon_min': i * 15, 'q05': float(v + r['q05']), 'q50': float(v),
             'q95': float(v + r['q95']), 'method': evaluado['metodo'], 'marca': 'pronostico'}
            for i, (f, v) in enumerate(zip(futuro, p, strict=True), start=1)]


# --------------------------------------------------------------------------- modelos (F2 y F3)
REDES = ('nhits', 'nbeatsx', 'patchtst', 'tft', 'itransformer', 'timesnet', 'tide', 'tsmixerx', 'bitcn', 'gru')
CANDIDATOS = (*REDES, 'lightgbm')
COVARIABLES_ML = ('hora_sin', 'hora_cos', 'dia_sin', 'dia_cos', 'no_laborable', 'temperatura_clima')
#: Fijadas el 2026-11-05, antes de la primera medición (089:RF-63 a RF-65). Cambiarlas exige otra versión.
PUERTA = {'version': 1, 'mejora_wape': .02, 'cobertura': (.85, .95), 'maxima_no_peor': True}
ORIGENES_MODELOS = 6
#: Registros entre dos ventanas de entrenamiento de las redes: una por día (089:RF-91).
PASO_VENTANAS = 96
#: Tope del lote por red (089:RF-92): la atención de TFT sobre 28 + 28 días no cabe en 8 GB con más de una serie por lote.
LOTE_MAXIMO = {'tft': 1}
#: Redes que entrenan sin el escalado de la librería (089:RF-93): el resto ya va en la escala de su objetivo.
SIN_ESCALADO = ('itransformer',)


def _covariables(t: np.ndarray, exogenas: Exogenas | None, hasta: np.datetime64) -> np.ndarray:
    """Lo que se conoce al emitir: el reloj, el calendario y la climatología anterior a ``hasta`` (089:RF-58)."""
    import pandas as pd

    indice = pd.DatetimeIndex(t)
    _mes, dia, bloque = _claves(t, None)
    laborable = np.zeros(len(t))
    clima = np.zeros(len(t))
    if exogenas is not None:
        if len(exogenas.dias_no_laborables):
            laborable = np.isin(np.asarray(t, dtype='datetime64[D]'), exogenas.dias_no_laborables).astype(float)
        serie = exogenas.serie_temperatura
        anterior = serie[serie.index <= pd.Timestamp(hasta)] if len(serie) else serie
        if len(anterior):
            clima = (_clima_futura(np.asarray(indice, dtype='datetime64[ns]'), anterior) - 20.0) / 10.0
    angulo_h, angulo_d = 2 * np.pi * bloque / 96, 2 * np.pi * dia / 7
    return np.c_[np.sin(angulo_h), np.cos(angulo_h), np.sin(angulo_d), np.cos(angulo_d), laborable, clima]


def _resto_normalizado(o: Objetivo, hasta: np.datetime64, exogenas: Exogenas | None):
    """Malla regular hasta ``hasta``: el resto sobre el perfil anclado, en su escala; lo que falta, enmascarado (089:RF-57).

    Sobre el perfil, porque predecir la demanda directa pierde el nivel; como resta y no como cociente, porque la Q cruza el
    cero con los bancos.
    """
    t, y = _arreglos(o)
    antes = t <= hasta
    t, y = t[antes], y[antes]
    if len(t) < 96:
        return None
    malla = np.arange(t[0], hasta + np.timedelta64(1, 'm'), np.timedelta64(15, 'm'))
    posicion = np.searchsorted(malla, t)
    valido = (posicion < len(malla)) & (malla[np.minimum(posicion, len(malla) - 1)] == t)
    perfil = _anclado(t, y, malla, exogenas)
    escala = float(np.median(np.abs(y))) or float(np.abs(y).max()) or 1.0
    resto = np.full(len(malla), np.nan)
    resto[posicion[valido]] = (y[valido] - perfil[posicion[valido]]) / escala
    return malla, resto, escala, t, y


def tabla_de_entrenamiento(objetivos: Sequence[Objetivo], hasta: np.datetime64, exogenas: Exogenas | None):
    """La tabla de las redes: un registro cada 15 minutos por objetivo, sin rellenar lo que falta (089:RF-57, RF-58)."""
    import pandas as pd

    partes = []
    for o in objetivos:
        datos = _resto_normalizado(o, hasta, exogenas)
        if datos is None:
            continue
        malla, resto, _escala, _t, _y = datos
        d = pd.DataFrame(_covariables(malla, exogenas, hasta), columns=list(COVARIABLES_ML))
        ok = np.isfinite(resto)
        d.insert(0, 'available_mask', ok.astype(float))
        d.insert(0, 'y', np.where(ok, resto, 0.0))
        d.insert(0, 'ds', malla)
        d.insert(0, 'unique_id', o.nombre)
        partes.append(d)
    if not partes:
        raise ValueError('ningún objetivo con historia antes del origen')
    return pd.concat(partes, ignore_index=True)


class ModeloRed:
    """Una red de neuralforecast, global para los objetivos de una clase y magnitud, solo en CUDA (089:RF-56, RF-62)."""

    requiere_gpu = True
    MULTIVARIANTES = ('itransformer', 'tsmixerx')

    def __init__(self, nombre: str, *, pasos: int = 1500, lote: int = 64, semilla: int = 0, contexto_dias: int = 28, **ajustes):
        from .digital_twin.oraculo import dispositivo

        dispositivo()                                   # sin CUDA, SinGPU antes de cargar nada (046:RF-15)
        self.nombre, self.pasos, self.lote, self.semilla = nombre, pasos, min(lote, LOTE_MAXIMO.get(nombre, lote)), semilla
        self.contexto_dias, self.ajustes = contexto_dias, ajustes
        self.nf = None

    def ajustar(self, objetivos, hasta, horizonte, exogenas, semilla):
        from neuralforecast import NeuralForecast, models
        from neuralforecast.losses.pytorch import MAE

        from .digital_twin.adaptador_neuralforecast import CLASE, CON_CALENDARIO, argumentos_modelo

        tabla = tabla_de_entrenamiento(objetivos, hasta, exogenas)
        kw = argumentos_modelo(self.nombre, horizonte=horizonte, contexto_pasos=self.contexto_dias * 96, semilla=semilla, pasos=self.pasos,
                               lote=self.lote, covariables=COVARIABLES_ML)
        if self.nombre in self.MULTIVARIANTES:
            kw['n_series'] = int(tabla['unique_id'].nunique())
        # 089:RF-91: la librería copia en la GPU todas las ventanas de cada serie del lote. Con una por registro, 28 días de
        # contexto y 28 de horizonte, N-HiTS pidió 285 GiB en la cabecera (2026-11-12); con una por día caben en 8 GB.
        kw['step_size'] = PASO_VENTANAS
        if self.nombre in SIN_ESCALADO:
            # 089:RF-93: iTransformer ve las 87 series a la vez y el escalado robusto de las que aún no empiezan, sin datos en la
            # ventana, dio «Loss is NaN» en la cabecera (2026-11-12). El resto ya está dividido por la escala de su objetivo.
            kw['scaler_type'] = 'identity'
        kw.update(self.ajustes)
        self.con_calendario = self.nombre in CON_CALENDARIO
        if not self.con_calendario:
            tabla = tabla[['unique_id', 'ds', 'y', 'available_mask']]
        self.nf = NeuralForecast(models=[getattr(models, CLASE[self.nombre])(loss=MAE(), **kw)], freq='15min', local_scaler_type=None)
        self.columna = CLASE[self.nombre]
        self.nf.fit(df=tabla)

    def predecir_todos(self, objetivos, hasta, horizonte, exogenas):
        import pandas as pd

        tabla = tabla_de_entrenamiento(objetivos, hasta, exogenas)
        futuro = _malla(hasta, hasta + np.timedelta64(horizonte * 15, 'm'))
        cov = _covariables(futuro, exogenas, hasta)
        partes = []
        for nombre in tabla['unique_id'].unique():
            d = pd.DataFrame(cov, columns=list(COVARIABLES_ML))
            d.insert(0, 'ds', futuro)
            d.insert(0, 'unique_id', nombre)
            partes.append(d)
        kw = {'futr_df': pd.concat(partes, ignore_index=True)} if self.con_calendario else {}
        if not self.con_calendario:
            tabla = tabla[['unique_id', 'ds', 'y', 'available_mask']]
        salida = self.nf.predict(df=tabla, **kw)
        if 'unique_id' not in salida.columns:
            salida = salida.reset_index()
        return _deshacer_resto(objetivos, {n: g.sort_values('ds')[self.columna].to_numpy(dtype=float) for n, g in salida.groupby('unique_id')},
                               hasta, futuro, exogenas)


def _deshacer_resto(objetivos, restos: Mapping[str, np.ndarray], hasta, futuro, exogenas) -> dict[str, np.ndarray]:
    salida = {}
    for o in objetivos:
        if o.nombre not in restos:
            continue
        _malla_o, _r, escala, t, y = _resto_normalizado(o, hasta, exogenas)
        salida[o.nombre] = _anclado(t, y, futuro, exogenas) + restos[o.nombre] * escala
    return salida


class ModeloGRU:
    """La GRU como referencia neuronal: un resto por paso del horizonte, en CUDA (089:RF-56, RF-62)."""

    requiere_gpu = True

    def __init__(self, nombre: str = 'gru', *, pasos: int = 1500, lote: int = 64, semilla: int = 0, contexto_dias: int = 7, **_a):
        import torch

        from .digital_twin.oraculo import dispositivo

        self.torch, self.disp = torch, dispositivo()
        self.pasos, self.lote, self.semilla, self.contexto = pasos, lote, semilla, contexto_dias * 96

    def _red(self, horizonte):
        torch = self.torch

        class Red(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.gru = torch.nn.GRU(1 + len(COVARIABLES_ML), 128, num_layers=2, batch_first=True)
                self.salida = torch.nn.Linear(128, horizonte)

            def forward(self, x):
                return self.salida(self.gru(x)[0][:, -1, :])

        return Red().to(self.disp)

    def ajustar(self, objetivos, hasta, horizonte, exogenas, semilla):
        torch = self.torch
        torch.manual_seed(semilla)
        rng = np.random.default_rng(semilla)
        datos = [(np.nan_to_num(d[1]), _covariables(d[0], exogenas, hasta)) for o in objetivos
                 if (d := _resto_normalizado(o, hasta, exogenas)) is not None and len(d[0]) > self.contexto + horizonte]
        if not datos:
            raise ValueError('ninguna serie llega al contexto más el horizonte')
        self.red = self._red(horizonte)
        optim = torch.optim.Adam(self.red.parameters(), lr=1e-3)
        for _ in range(self.pasos):
            x, y = [], []
            for _i in range(self.lote):
                r, c = datos[int(rng.integers(len(datos)))]
                e = int(rng.integers(self.contexto, len(r) - horizonte))
                x.append(np.c_[r[e - self.contexto:e], c[e - self.contexto:e]])
                y.append(r[e:e + horizonte])
            optim.zero_grad()
            error = self.red(torch.tensor(np.array(x), dtype=torch.float32, device=self.disp)) - torch.tensor(np.array(y), dtype=torch.float32, device=self.disp)
            error.abs().mean().backward()
            optim.step()

    def predecir_todos(self, objetivos, hasta, horizonte, exogenas):
        torch = self.torch
        futuro = _malla(hasta, hasta + np.timedelta64(horizonte * 15, 'm'))
        restos = {}
        self.red.eval()
        with torch.no_grad():
            for o in objetivos:
                d = _resto_normalizado(o, hasta, exogenas)
                if d is None or len(d[0]) < self.contexto:
                    continue
                x = np.c_[np.nan_to_num(d[1][-self.contexto:]), _covariables(d[0][-self.contexto:], exogenas, hasta)]
                restos[o.nombre] = self.red(torch.tensor(x[None], dtype=torch.float32, device=self.disp)).cpu().numpy()[0]
        return _deshacer_resto(objetivos, restos, hasta, futuro, exogenas)


class ModeloLGBM:
    """LightGBM directo: el resto de cada instante futuro con lo conocido al emitir, en CPU (089:RF-56, RF-57).

    Directo y no recursivo: un proyecto anterior midió que la recursión a 15 minutos pierde el nivel en pocos días.
    """

    requiere_gpu = False
    MAX_FILAS = 3_000_000

    def __init__(self, nombre: str = 'lightgbm', *, pasos: int = 1500, semilla: int = 0, hojas: int = 127, aprendizaje: float = .03, **_a):
        self.pasos, self.semilla, self.hojas, self.aprendizaje = pasos, semilla, hojas, aprendizaje

    @staticmethod
    def _filas(resto, cov, e, pasos, escala):
        """Una fila por horizonte: nivel reciente, el mismo instante de la última semana observada y lo conocido del futuro."""
        reciente = resto[e - 96:e]
        semana = resto[e - 672:e]
        media_dia = np.nanmean(reciente) if np.isfinite(reciente).any() else 0.0
        media_semana = np.nanmean(semana) if np.isfinite(semana).any() else 0.0
        anterior = e + pasos - 1 - 672 * np.ceil(pasos / 672).astype(int)
        vista = np.where(anterior >= 0, resto[np.maximum(anterior, 0)], np.nan)
        return np.c_[np.full(len(pasos), media_dia), np.full(len(pasos), media_semana), vista, np.log1p(pasos),
                     np.full(len(pasos), math.log1p(escala)), cov[e + pasos - 1]]

    def ajustar(self, objetivos, hasta, horizonte, exogenas, semilla):
        import lightgbm as lgb

        rng = np.random.default_rng(semilla)
        x, y = [], []
        filas = 0
        for o in objetivos:
            d = _resto_normalizado(o, hasta, exogenas)
            if d is None or len(d[0]) < 672 + 96 + 1:
                continue
            malla, resto, escala, _t, _y = d
            cov = _covariables(malla, exogenas, hasta)
            for e in range(672, len(malla) - 1, 96):
                maximo = min(horizonte, len(malla) - e)
                pasos = np.sort(rng.integers(1, maximo + 1, size=min(48, maximo)))
                objetivo = resto[e + pasos - 1]
                ok = np.isfinite(objetivo)
                if ok.any():
                    x.append(self._filas(resto, cov, e, pasos[ok], escala))
                    y.append(objetivo[ok])
                    filas += int(ok.sum())
        if not filas:
            raise ValueError('ninguna serie con historia para LightGBM')
        xa, ya = np.vstack(x), np.concatenate(y)
        if filas > self.MAX_FILAS:
            elegidas = rng.choice(filas, self.MAX_FILAS, replace=False)
            xa, ya = xa[elegidas], ya[elegidas]
        self.modelo = lgb.train({'objective': 'l1', 'learning_rate': self.aprendizaje, 'num_leaves': self.hojas, 'seed': semilla,
                                 'feature_fraction': .9, 'bagging_fraction': .8, 'bagging_freq': 1, 'verbosity': -1, 'deterministic': True,
                                 'force_col_wise': True}, lgb.Dataset(xa, ya), num_boost_round=self.pasos)

    def predecir_todos(self, objetivos, hasta, horizonte, exogenas):
        futuro = _malla(hasta, hasta + np.timedelta64(horizonte * 15, 'm'))
        restos = {}
        for o in objetivos:
            d = _resto_normalizado(o, hasta, exogenas)
            if d is None or len(d[0]) < 672:
                continue
            malla, resto, escala, _t, _y = d
            todo = np.r_[malla, futuro]
            r = np.r_[resto, np.full(len(futuro), np.nan)]
            restos[o.nombre] = self.modelo.predict(self._filas(r, _covariables(todo, exogenas, hasta), len(malla), np.arange(1, horizonte + 1), escala))
        return _deshacer_resto(objetivos, restos, hasta, futuro, exogenas)


def fabrica_modelo(nombre: str, **ajustes):
    """El candidato por su nombre; PyTorch y LightGBM se cargan aquí, al pedirlo."""
    if nombre == 'lightgbm':
        return ModeloLGBM(nombre, **ajustes)
    if nombre == 'gru':
        return ModeloGRU(nombre, **ajustes)
    if nombre in REDES:
        return ModeloRed(nombre, **ajustes)
    raise ValueError(f'candidato desconocido: {nombre}')


def _error_de_maxima(real: np.ndarray, p: np.ndarray) -> float:
    ok = np.isfinite(real)
    if not ok.any() or not np.abs(real[ok]).max():
        return float('nan')
    return abs(float(p[ok].max()) - float(real[ok].max())) / float(np.abs(real[ok]).max())


def _resumir(medidas: Sequence[dict], etiqueta: str = 'wape') -> float:
    error, energia = sum(m['error_abs'] for m in medidas if m['n']), sum(m['energia'] for m in medidas if m['n'])
    return error / energia if energia else float('inf')


def backtest_modelos(objetivos: Sequence[Objetivo], nombres: Sequence[str], *, horizonte_dias: int = HORIZONTE_DIAS, origenes: int = ORIGENES_MODELOS,
                     exogenas: Exogenas | None = None, semilla: int = 0, fabrica: Callable = fabrica_modelo, ajustes: Mapping | None = None,
                     log: Callable[[str], None] = lambda _m: None) -> dict:
    """Compite los candidatos con los perfiles en los mismos orígenes y decide con la puerta fijada (089:RF-56 a RF-67, RF-69)."""
    h = np.timedelta64(horizonte_dias, 'D')
    pasos = horizonte_dias * 96
    ultimo = max(_arreglos(o)[0][-1] for o in objetivos if len(o.curva))
    fechas = sorted(ultimo - h * k for k in range(1, origenes + 1))
    def evaluables(fecha):
        salida = []
        for o in objetivos:
            t, _y = _arreglos(o)
            inicio = np.datetime64(o.fuente['inicio_base']) if o.fuente.get('inicio_base') else (t[0] if len(t) else fecha)
            if len(t) and fecha >= inicio and fecha - t[0] >= np.timedelta64(HISTORIA_MINIMA_DIAS, 'D') and t[-1] > fecha:
                salida.append(o)
        return salida
    fechas = [f for f in fechas if evaluables(f)]
    if len(fechas) < 2:
        return {'status': 'HISTORIA_INSUFICIENTE', 'ganador': None, 'motivo': 'no hay dos orígenes con objetivos evaluables; queda el perfil',
                'modelos': {}, 'perfiles': {}, 'origenes': []}
    predicciones: dict[str, dict] = {}
    estados: dict[str, dict] = {n: {'status': 'EVALUADO'} for n in nombres}
    reales = {}
    for f in fechas:
        for o in evaluables(f):
            t, y = _arreglos(o)
            futuro = _malla(f, f + h)
            ventana = (t > f) & (t <= f + h)
            r = np.full(len(futuro), np.nan)
            r[np.searchsorted(futuro, t[ventana])] = y[ventana]
            reales[(o.nombre, f)] = r
            antes = t <= f
            for m in METODOS:
                predicciones.setdefault(m, {})[(o.nombre, f)] = predecir(m, t[antes], y[antes], futuro, exogenas)
    for nombre in nombres:
        try:
            for f in fechas:
                objs = evaluables(f)
                modelo = fabrica(nombre, semilla=semilla, **dict(ajustes or {}))
                modelo.ajustar(objs, f, pasos, exogenas, semilla)
                for k, v in modelo.predecir_todos(objs, f, pasos, exogenas).items():
                    predicciones.setdefault(nombre, {})[(k, f)] = v
                log(f'{nombre}: origen {str(f)[:10]} listo')
                del modelo
        except Exception as exc:  # noqa: BLE001 - la librería lanza Exception a secas, y un modelo roto no se lleva a los demás (089:RF-61)
            estados[nombre] = {'status': 'ERROR_ENTORNO', 'motivo': f'{type(exc).__name__}: {exc}'[:500]}
            predicciones.pop(nombre, None)
            log(f'{nombre}: {exc}')
        _liberar_gpu()
    eleccion, prueba = fechas[:-1], fechas[-1]
    def medidas(metodo, grupo):
        return [medir(reales[k], p) for k, p in predicciones[metodo].items() if k[1] in grupo and k in reales]
    def wape_seleccion(metodo):
        return _resumir(medidas(metodo, eleccion))
    disponibles = [n for n in nombres if n in predicciones]
    # 089:RF-69: el conjunto se arma con lo elegido en los orígenes de elección, y prueba como los demás.
    if len(disponibles) >= 2:
        mejores = sorted(disponibles, key=wape_seleccion)[:3]
        claves = set.intersection(*(set(predicciones[n]) for n in mejores))
        predicciones['conjunto'] = {k: np.mean([predicciones[n][k] for n in mejores], axis=0) for k in claves}
        estados['conjunto'] = {'status': 'EVALUADO', 'miembros': mejores}
    perfil = min(METODOS, key=wape_seleccion)
    wape_perfil = _resumir(medidas(perfil, [prueba]))
    def error_maximas(metodo):
        v = [_error_de_maxima(reales[k], p) for k, p in predicciones[metodo].items() if k[1] == prueba and k in reales]
        v = [x for x in v if math.isfinite(x)]
        return float(np.median(v)) if v else float('inf')
    maxima_perfil = error_maximas(perfil)
    def por_horizonte(metodo):
        salida = {}
        for dias in sorted({1, min(7, horizonte_dias), horizonte_dias}):
            corte = dias * 96
            salida[f'{dias}d'] = _resumir([medir(reales[k][:corte], p[:corte]) for k, p in predicciones[metodo].items() if k[1] == prueba and k in reales])
        return salida
    for nombre, estado in estados.items():
        if estado['status'] != 'EVALUADO':
            continue
        errores = np.concatenate([reales[k][np.isfinite(reales[k])] - p[np.isfinite(reales[k])] for k, p in predicciones[nombre].items()
                                  if k[1] in eleccion and k in reales] or [np.zeros(1)])
        q05, q95 = (float(np.quantile(errores, q)) for q in (.05, .95))
        dentro, total = 0, 0
        for k, p in predicciones[nombre].items():
            if k[1] == prueba and k in reales:
                ok = np.isfinite(reales[k])
                dentro += int(((reales[k][ok] >= p[ok] + q05) & (reales[k][ok] <= p[ok] + q95)).sum())
                total += int(ok.sum())
        wape = _resumir(medidas(nombre, [prueba]))
        cobertura = dentro / total if total else 0.0
        puerta = {'wape': wape <= wape_perfil * (1 - PUERTA['mejora_wape']), 'maxima': error_maximas(nombre) <= maxima_perfil,
                  'cobertura': PUERTA['cobertura'][0] <= cobertura <= PUERTA['cobertura'][1]}
        estado.update(wape_prueba=wape, wape_eleccion=wape_seleccion(nombre), error_maxima=error_maximas(nombre), cobertura=cobertura, puerta=puerta,
                      supera_puerta=all(puerta.values()), wape_por_horizonte=por_horizonte(nombre))
    pasan = [n for n, e in estados.items() if e.get('supera_puerta')]
    ganador = min(pasan, key=lambda n: estados[n]['wape_eleccion']) if pasan else None
    return _sin_infinitos({
        'status': 'EVALUADO', 'ganador': ganador, 'puerta_version': PUERTA['version'], 'horizonte_dias': horizonte_dias,
        'motivo': f'{ganador} supera al perfil {perfil}' if ganador else f'ningún modelo supera la puerta: queda el perfil {perfil}',
        'modelos': estados, 'origenes': [str(f)[:19] for f in fechas], 'objetivos': len(objetivos),
        'perfiles': {m: {'wape_prueba': _resumir(medidas(m, [prueba])), 'wape_eleccion': wape_seleccion(m), 'error_maxima': error_maximas(m),
                         'wape_por_horizonte': por_horizonte(m)} for m in METODOS},
        'mejor_perfil': perfil})


#: 031:RF-3: la capa anual mide con las mismas funciones; se publican en vez de copiarlas (la guarda de capas veda lo privado).
arreglos, error_de_maxima, malla, sin_infinitos = _arreglos, _error_de_maxima, _malla, _sin_infinitos


def _liberar_gpu() -> None:
    import gc
    import sys

    gc.collect()
    torch = sys.modules.get('torch')
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


# --------------------------------------------------------------------------- dataset guardado
def huella_de_objetivos(objetivos: Iterable[Objetivo]) -> str:
    """La huella de lo medido: la misma al guardar, al abrir y en la evaluación de la proyección anual (089:RF-68, 031:RF-9)."""
    import hashlib

    huella = hashlib.sha256()
    for o in sorted(objetivos, key=lambda x: x.nombre):
        t, v = _arreglos(o)
        huella.update(o.nombre.encode())
        huella.update(t.astype('int64').tobytes())
        huella.update(v.tobytes())
    return huella.hexdigest()


def guardar_dataset(dataset: Dataset, carpeta: Path | str) -> str:
    """Los objetivos limpios en Parquet con su huella: entrenar no vuelve a leer los libros (089:RF-68)."""
    import json

    import pandas as pd

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    tablas, indice = [], []
    for o in sorted(dataset.objetivos, key=lambda x: x.nombre):
        t, v = _arreglos(o)
        tablas.append(pd.DataFrame({'objetivo': o.nombre, 't': t, 'v': v}))
        indice.append({'clase': o.clase, 'ident': o.ident, 'magnitud': o.magnitud, 'unidad': o.unidad, 'fuente': o.fuente})
    texto = huella_de_objetivos(dataset.objetivos)
    if tablas:
        pd.concat(tablas, ignore_index=True).to_parquet(carpeta / 'objetivos.parquet')
    (carpeta / 'dataset.json.tmp').write_text(json.dumps({'huella': texto, 'objetivos': indice, 'apartados': dataset.apartados, 'libros': dataset.libros,
                                                       'ultimo_dato': dataset.ultimo_dato, 'avisos': dataset.avisos}, ensure_ascii=False, default=str), encoding='utf-8')
    (carpeta / 'dataset.json.tmp').replace(carpeta / 'dataset.json')     # lo último: sin este fichero, el dataset no existe
    return texto


def abrir_dataset(carpeta: Path | str, exogenas: Exogenas | None = None) -> Dataset:
    """El dataset guardado, comprobando su huella (089:RF-68)."""
    import json

    import pandas as pd

    carpeta = Path(carpeta)
    meta = json.loads((carpeta / 'dataset.json').read_text(encoding='utf-8'))
    por = {n: g for n, g in pd.read_parquet(carpeta / 'objetivos.parquet').groupby('objetivo')} if (carpeta / 'objetivos.parquet').exists() else {}
    objetivos = []
    for x in meta['objetivos']:
        o = Objetivo(x['clase'], x['ident'], x['magnitud'], x['unidad'], [], x['fuente'])
        g = por.get(o.nombre)
        curva = CurvaCompacta(np.zeros(0, dtype='datetime64[ns]'), np.zeros(0)) if g is None else CurvaCompacta(g['t'].to_numpy(dtype='datetime64[ns]'), g['v'].to_numpy(dtype=float))
        objetivos.append(Objetivo(x['clase'], x['ident'], x['magnitud'], x['unidad'], curva, x['fuente']))
    if huella_de_objetivos(objetivos) != meta['huella']:
        raise ValueError(f'{carpeta}: la huella del dataset no coincide; vuelva a armarlo')
    return Dataset(objetivos, meta['apartados'], meta['libros'], meta['ultimo_dato'], exogenas, meta['huella'], avisos=meta.get('avisos', []))
