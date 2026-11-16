"""Control de reidentificación: antes de emitir, se busca en cada byte lo que delataría a la empresa (112:RF-4, RF-10).

Un benchmark solo sale si este control no encuentra nada. Se busca, en todos los ficheros de la salida:

- los identificadores originales del mapa (de 3 caracteres o más), como palabra completa o como trozo de una palabra
  separado por ``_``, ``-`` o ``.``; los de los clientes, aparte («cliente»);
- los términos del perfil de la empresa y las rutas, correos e IP de :mod:`convertersmartgrid.privacidad`. Un perfil
  pedido que falta o no se lee detiene el control (``PerfilIlegible``): no se busca «ningún término» en silencio;
- coordenadas dentro del recuadro del origen ampliado 50 km;
- fechas dentro del intervalo del origen, sin desplazar;
- secuencias de 8 valores seguidos de una serie original, iguales a 4 decimales (la escala sorteada las cambia: si
  coinciden, la transformación no se aplicó);
- fragmentos de 6 palabras seguidas de los textos del origen que no son tablas;
- cualquier fichero que no esté en la lista cerrada de la salida (RF-10);
- la semilla secreta de los seudónimos, sola o dentro de una cadena más larga (RF-12): con ella y la lista de
  códigos originales se rehace el mapa. La semilla pública del manifiesto (``semilla.semilla_publica``) sí sale.

Cada hallazgo dice su clase, el fichero y la línea, nunca el valor original: el mensaje se puede guardar y enseñar.
"""
from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from .. import privacidad
from ..evaluacion_modelos import texto_canonico
from ..model import extract_sed_code
from .redes import SECCIONES, SED_, Fichero

#: Lo único que puede haber en la carpeta de un benchmark.
FICHEROS_PERMITIDOS = frozenset({'RED.txt', 'CARGA.txt', 'BD_Equipo.txt', 'series.csv', 'series_objetivos.csv',
                                 'manifiesto.json'})
MARGEN_COORDENADAS_M = 50_000.0
VENTANA_SECUENCIA = 8
PALABRAS_FRAGMENTO = 6
_TOKEN = re.compile(r'[A-Za-z0-9ÑñÁÉÍÓÚáéíóú_.\-]+')
_SEPARADOR = re.compile(r'([_.\-])')
_FECHA = re.compile(r'\b(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?))?')
_PALABRA = re.compile(r'\w+')
_CIFRAS = re.compile(r'\d+')


@dataclass(frozen=True)
class Hallazgo:
    tipo: str
    fichero: str
    linea: int
    motivo: str

    def texto(self) -> str:
        return f'{self.tipo} en {self.fichero}:{self.linea}: {self.motivo}'


class FugaDetectada(ValueError):
    """El benchmark contiene algo del origen: no se emite."""


def exigir_limpio(hallazgos: Sequence[Hallazgo]) -> None:
    """Lanza :class:`FugaDetectada` con lo que delató al benchmark (clase, fichero y línea, sin el valor)."""
    if hallazgos:
        raise FugaDetectada('no se emite el benchmark: ' + '; '.join(h.texto() for h in hallazgos[:20])
                            + (f' (y {len(hallazgos) - 20} más)' if len(hallazgos) > 20 else ''))


def _identificador_util(valor: str) -> bool:
    valor = valor.strip()
    if len(valor) < 3 or valor.upper() == 'DEFAULT':
        return False
    # Un número corto (un 1200, un 42) aparece en cualquier tabla sin delatar nada.
    return not (valor.isdigit() and len(valor) < 6)


def _shingles(texto: str) -> set[tuple[str, ...]]:
    palabras = _PALABRA.findall(texto_canonico(texto))
    return {tuple(palabras[i:i + PALABRAS_FRAGMENTO]) for i in range(len(palabras) - PALABRAS_FRAGMENTO + 1)}


def _hashes(valores: np.ndarray) -> np.ndarray:
    """Huella de cada ventana de 8 valores a 4 decimales; fuera las ventanas casi constantes y las que tienen huecos."""
    v = np.asarray(valores, dtype=float)
    if len(v) < VENTANA_SECUENCIA:
        return np.zeros(0, dtype=np.uint64)
    ventanas = np.lib.stride_tricks.sliding_window_view(v, VENTANA_SECUENCIA)
    validas = np.isfinite(ventanas).all(axis=1)
    enteros = np.round(np.where(np.isfinite(ventanas), ventanas, 0.0) * 1e4).astype(np.int64)
    ordenadas = np.sort(enteros, axis=1)
    distintos = (np.diff(ordenadas, axis=1) != 0).sum(axis=1) + 1
    utiles = validas & (distintos >= 4)
    pesos = np.array([0x9E3779B97F4A7C15 * (k + 1) % (1 << 64) for k in range(VENTANA_SECUENCIA)], dtype=np.uint64)
    with np.errstate(over='ignore'):
        h = (enteros[utiles].astype(np.uint64) * pesos).sum(axis=1, dtype=np.uint64)
    return h


@dataclass
class Origen:
    """Lo que el control sabe del origen. Vive solo en memoria, como el mapa: nunca se escribe."""

    identificadores: dict[str, str] = field(default_factory=dict)      # valor → clase («identificador», «cliente»)
    terminos: frozenset[str] = frozenset()
    recuadro: tuple[float, float, float, float] | None = None           # x mín, y mín, x máx, y máx
    intervalo: tuple[datetime, datetime] | None = None
    secuencias: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.uint64))
    fragmentos: frozenset[tuple[str, ...]] = frozenset()
    permitidos: frozenset[str] = FICHEROS_PERMITIDOS
    semilla: int | None = None                                          # la secreta (RF-12): nunca en __repr__

    def __repr__(self) -> str:
        return f'Origen(identificadores={len(self.identificadores)}, terminos={len(self.terminos)})'

    @classmethod
    def desde(cls, *, red: Iterable[Fichero] = (), series=None, perfil: Path | str | None = None,
              textos: Iterable[str] = (), permitidos: Iterable[str] = FICHEROS_PERMITIDOS,
              semilla: int | None = None) -> 'Origen':
        """Reúne del trío leído (``redes.leer_fichero``), del dataset del 089 y del perfil lo que no puede salir."""
        ids: dict[str, str] = {}
        xs: list[float] = []
        ys: list[float] = []
        libres: list[str] = list(textos)
        for f in red:
            secciones = SECCIONES.get(f.nombre, {})
            for e in f.entradas:
                if e[0] != 'fila':
                    continue
                clases = secciones.get(e[1]) or {}
                for col, valor in e[2].items():
                    if not valor:
                        continue
                    clase = clases.get(col)
                    if isinstance(clase, tuple):
                        if _identificador_util(valor):
                            ids.setdefault(valor, 'cliente' if clase[1] == 'cliente' else 'identificador')
                        if clase[0] == SED_ and (codigo := extract_sed_code(valor)) and _identificador_util(codigo):
                            ids.setdefault(codigo, 'identificador')
                    elif clase in ('x', 'y') and (numero := _numero(valor)) is not None:
                        (xs if clase == 'x' else ys).append(numero)
                    elif clase is None and len(_PALABRA.findall(valor)) >= PALABRAS_FRAGMENTO:
                        libres.append(valor)        # texto libre de una columna que no sale: no puede aparecer
            for e in f.entradas:
                if e[0] == 'feeder':
                    for valor in e[2][:2]:
                        if _identificador_util(valor):
                            ids.setdefault(valor, 'identificador')
        recuadro = (min(xs), min(ys), max(xs), max(ys)) if xs and ys else None
        intervalo = None
        secuencias = [np.zeros(0, dtype=np.uint64)]
        if series is not None:
            from .series import arreglos
            extremos = []
            for o in series.objetivos:
                if _identificador_util(o.ident):
                    ids.setdefault(o.ident, 'cliente' if o.clase == 'cliente' else 'identificador')
                t, v = arreglos(o)
                if len(t):
                    extremos.append((t[0], t[-1]))
                secuencias.append(_hashes(v))
            if extremos:
                desde = min(a for a, _ in extremos).astype('datetime64[s]').astype(datetime)
                hasta = max(b for _, b in extremos).astype('datetime64[s]').astype(datetime)
                intervalo = (desde, hasta)
        # Un perfil pedido que falta o no se lee lanza PerfilIlegible: sin sus términos, el control no sabría qué
        # buscar y el benchmark saldría con el nombre de la empresa. Mejor no emitir (112:RF-4).
        terminos = (frozenset(privacidad.terminos_del_perfil(Path(perfil), obligatorio=True)) if perfil
                    else frozenset())
        fragmentos = frozenset().union(*(_shingles(t) for t in libres)) if libres else frozenset()
        return cls(ids, terminos, recuadro, intervalo, np.unique(np.concatenate(secuencias)), fragmentos,
                   frozenset(permitidos), semilla)


def _trozos(token: str) -> Iterable[str]:
    """La palabra y cada tramo seguido de sus partes: «BT-13_SE1000» da también «SE1000» y «13_SE1000»."""
    partes = _SEPARADOR.split(token)
    piezas = partes[0::2]
    seps = partes[1::2]
    for i in range(len(piezas)):
        texto = piezas[i]
        if texto:
            yield texto
        for j in range(i + 1, len(piezas)):
            texto += seps[j - 1] + piezas[j]
            yield texto


def _numero(texto: str) -> float | None:
    try:
        return float(texto)
    except ValueError:
        return None


def _revisar_linea(nombre: str, n: int, linea: str, origen: Origen, terminos_min: list[str]) -> list[Hallazgo]:
    salida: list[Hallazgo] = []
    if origen.semilla is not None and str(origen.semilla) in _CIFRAS.findall(linea):
        salida.append(Hallazgo('semilla', nombre, n, 'la semilla secreta de los seudónimos (o una cadena que la '
                               'contiene y rehace el mapa)'))
    vistos: set[str] = set()
    for token in _TOKEN.findall(linea):
        for trozo in _trozos(token):
            clase = origen.identificadores.get(trozo)
            if clase and clase not in vistos:
                vistos.add(clase)
                salida.append(Hallazgo(clase, nombre, n, f'un {clase} del origen'))
    minuscula = linea.casefold()
    if any(t in minuscula for t in terminos_min):
        salida.append(Hallazgo('termino', nombre, n, 'un término del perfil de la empresa'))
    for tipo, patron in (('ruta', privacidad.RUTA_WINDOWS), ('ruta', privacidad.RUTA_POSIX),
                         ('correo', privacidad.CORREO), ('ip', privacidad.IP)):
        if patron.search(linea):
            salida.append(Hallazgo(tipo, nombre, n, f'una {tipo}' if tipo == 'ruta' else f'un {tipo}'))
    if origen.recuadro is not None:
        x0, y0, x1, y1 = origen.recuadro
        m = MARGEN_COORDENADAS_M
        numeros = [_numero(c) for c in linea.split(',')]
        for a, b in zip(numeros, numeros[1:]):
            if a is not None and b is not None and x0 - m <= a <= x1 + m and y0 - m <= b <= y1 + m:
                salida.append(Hallazgo('coordenada', nombre, n, 'una coordenada dentro de la zona del origen'))
                break
    if origen.intervalo is not None:
        desde, hasta = origen.intervalo
        for dia, hora in _FECHA.findall(linea):
            try:
                t = datetime.fromisoformat(f'{dia}T{hora}' if hora else dia)
            except ValueError:
                continue
            if desde.replace(hour=0, minute=0, second=0) <= t <= hasta:
                salida.append(Hallazgo('fecha', nombre, n, 'una fecha del intervalo del origen sin desplazar'))
                break
    if origen.fragmentos:
        palabras = _PALABRA.findall(texto_canonico(linea))
        for i in range(len(palabras) - PALABRAS_FRAGMENTO + 1):
            if tuple(palabras[i:i + PALABRAS_FRAGMENTO]) in origen.fragmentos:
                salida.append(Hallazgo('texto', nombre, n, 'un fragmento de un texto del origen'))
                break
    return salida


def _revisar_secuencias(ruta: Path, origen: Origen) -> list[Hallazgo]:
    if not len(origen.secuencias):
        return []
    por_objetivo: dict[str, tuple[list[int], list[float]]] = {}
    with ruta.open(encoding='utf-8', newline='') as f:
        lector = csv.DictReader(f)
        if not {'objetivo', 'v'} <= set(lector.fieldnames or ()):
            return []
        for n, fila in enumerate(lector, start=2):
            lineas, valores = por_objetivo.setdefault(fila['objetivo'], ([], []))
            lineas.append(n)
            valores.append(_numero(fila['v']) if fila['v'] else float('nan'))
    salida = []
    for lineas, valores in por_objetivo.values():
        v = np.array([x if x is not None else float('nan') for x in valores])
        if len(v) < VENTANA_SECUENCIA:
            continue
        ventanas = np.lib.stride_tricks.sliding_window_view(v, VENTANA_SECUENCIA)
        enteros = np.round(np.where(np.isfinite(ventanas), ventanas, 0.0) * 1e4).astype(np.int64)
        distintos = (np.diff(np.sort(enteros, axis=1), axis=1) != 0).sum(axis=1) + 1
        utiles = np.flatnonzero(np.isfinite(ventanas).all(axis=1) & (distintos >= 4))
        h = _hashes(v)                      # mismas ventanas útiles, en el mismo orden
        coinciden = np.isin(h, origen.secuencias)
        if coinciden.any():
            salida.append(Hallazgo('secuencia', ruta.name, lineas[int(utiles[np.flatnonzero(coinciden)[0]])],
                                   'una secuencia de valores de una serie original'))
    return salida


def revisar(carpeta: Path | str, origen: Origen) -> list[Hallazgo]:
    """Todos los hallazgos de la carpeta de un benchmark; una lista vacía es el único resultado que deja emitir."""
    carpeta = Path(carpeta)
    hallazgos: list[Hallazgo] = []
    terminos_min = sorted({t.casefold() for t in origen.terminos}, key=len, reverse=True)
    for ruta in sorted(p for p in carpeta.rglob('*') if p.is_file()):
        nombre = ruta.relative_to(carpeta).as_posix()
        if nombre not in origen.permitidos:
            hallazgos.append(Hallazgo('fichero', nombre, 0, f'un fichero fuera de la lista cerrada: {nombre}'))
            continue
        with ruta.open(encoding='utf-8', errors='replace', newline='') as f:
            for n, linea in enumerate(f, start=1):
                hallazgos.extend(_revisar_linea(nombre, n, linea.rstrip('\r\n'), origen, terminos_min))
        if ruta.suffix == '.csv':
            hallazgos.extend(_revisar_secuencias(ruta, origen))
    return hallazgos
