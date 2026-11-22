"""Dejar una empresa fuera cada vez con datos en disco: conversión VNR y pronóstico (112:RF-15 a RF-19).

Cada empresa es una subcarpeta de la carpeta que se da. Su nombre no sale nunca en el informe: las empresas se
renombran ``E1…En`` por el orden de su huella (``seudonimos_de_empresa`` de las cohortes), y el informe dice cuántas hay.

- Conversión VNR: la subcarpeta tiene ``red_vnr.json``, los tramos (código de conductor y longitud) y las fichas que
  ``red_de_modelo`` saca del modelo canónico de la copia de SQL Server del paquete público de esa empresa
  (``cargar_copia``, spec 023; ``tools/interempresa_loco.py preparar-vnr``), sin pasar por un export CYMDIST (112:RF-22).
  También vale un trío TXT de CYMDIST: del RED se toman los tramos y del BD_Equipo sus fichas. Una carpeta sin tramos es
  un error, nunca un pliegue que no pasa.
- Pronóstico: la subcarpeta es un benchmark de series de la 112 (``series.csv`` y ``series_objetivos.csv``). Lo que se
  ajusta con las demás es la forma semanal normalizada (cada serie por su media, mediana por día y cuarto de hora), y en la
  retenida se pronostica su nivel de los últimos 28 días por esa forma; se compara con su propia base «semanal» del 089
  en el mismo origen, con el WAPE del 089 (RF-18). Una forma aprendida de otras empresas que no empeora la base de la
  retenida es la que generaliza.

El informe se escribe con ``write_json_atomic`` (001:RF-5) y lleva el veredicto, su motivo, los criterios y cada pliegue.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ...aplicacion.benchmarks.cohortes import seudonimos_de_empresa
from ...dominio.benchmarks.interempresa import (TOLERANCIA_FICHA, UMBRAL_ACIERTO, Ficha, RedEmpresa, ajustar_catalogo,
                                                criterio_catalogo, dejar_una_fuera, medir_catalogo)
from ...dominio.benchmarks.redes import leer_fichero
from ...dominio.dataset import TABLAS_TIPOS_LINEA
from ...dominio.util import write_json_atomic
from ..pronostico_demanda import HORIZONTE_DIAS, escala_estacional, medir, predecir
from .series import arreglos, leer

ESQUEMA = 'csg-interempresa-v1'
#: Cuánto puede empeorar el WAPE de la forma aprendida de las demás frente a la base propia de la retenida.
MARGEN_PRONOSTICO = 0.10
#: Días de la semana por cuartos de hora: la celda de la forma semanal.
CELDAS = 7 * 96
_SECCIONES_TRAMO = ('LINE CONFIGURATION', 'OVERHEADLINE SETTING', 'UNDERGROUNDLINE SETTING')
#: 112:RF-22: lo que la conversión de una empresa necesita, sacado de su modelo canónico, en su subcarpeta.
RED_VNR = 'red_vnr.json'
ESQUEMA_RED = 'csg-red-vnr-v2'
#: El formato de la RF-22, sin el origen de las fichas: todas cuentan como propias.
ESQUEMA_RED_V1 = 'csg-red-vnr-v1'
#: 112:RF-23: de dónde sale la ficha de un conductor.
ORIGEN_PROPIA = 'propia'
ORIGEN_CATALOGO = 'catálogo 053'
#: 112:RF-23: lo que mide cada evaluación, escrito en el informe.
QUE_MIDE = {
    ORIGEN_CATALOGO: ('acierto, por longitud, del modelo (el código igual o el más parecido) al dar a los conductores de '
                      'la retenida las fichas de las demás, frente a la ficha que el catálogo universal (053) da a los de '
                      'la retenida; el catálogo es el mismo para todas las empresas, así que mide si los códigos de cada '
                      'una llevan a la misma ficha, no unas fichas independientes'),
    ORIGEN_PROPIA: ('acierto, por longitud, del modelo al dar a los conductores de la retenida las fichas de las demás, '
                    'frente a la ficha propia que trae la fuente de la retenida'),
}


class SinEmpresas(ValueError):
    """La carpeta no tiene ninguna subcarpeta con datos de una empresa."""


def _huella(nombre: str) -> str:
    return hashlib.sha256(nombre.encode('utf-8')).hexdigest()


def empresas_de(raiz: Path | str) -> dict[str, Path]:
    """``E1…En`` → subcarpeta, por la huella del nombre: el nombre no se escribe ni ordena el resultado."""
    carpetas = sorted(p for p in Path(raiz).iterdir() if p.is_dir() and not p.name.startswith(('.', '_')))
    if not carpetas:
        raise SinEmpresas(f'{Path(raiz).name} no tiene subcarpetas de empresa')
    por_huella = {_huella(p.name): p for p in carpetas}
    return {seudonimo: por_huella[h] for h, seudonimo in seudonimos_de_empresa(por_huella).items()}


# ------------------------------------------------------------------ conversión VNR


def _numero(valor: str) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float('nan')


def _positivo(valor: Any) -> float:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) and v > 0 else 0.0


def _medida(valor: Any) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float('nan')


def _ficha_con_datos(r1: Any, x1: Any, amps: Any) -> Ficha | None:
    """Una ficha solo si trae R1, X1 y corriente admisible: lo que el criterio compara (RF-17). Las normas de una copia de
    VNR-GIS traen la descripción del conductor, no su impedancia; una ficha vacía no es una ficha propia que medir."""
    ficha = Ficha(_medida(r1), _medida(x1), _medida(amps))
    return ficha if all(math.isfinite(v) for v in (ficha.r1, ficha.x1, ficha.amps)) else None


@dataclass
class RedVnr:
    """Los tramos de una empresa y sus fichas por origen (112:RF-23): las que trae su fuente y las que da el catálogo."""

    tramos: list[tuple[str, float]] = field(default_factory=list)
    propias: dict[str, Ficha] = field(default_factory=dict)
    catalogo: dict[str, Ficha] = field(default_factory=dict)

    @property
    def fichas(self) -> dict[str, Ficha]:
        return {**self.catalogo, **self.propias}

    def red(self, origen: str) -> RedEmpresa:
        """La red con las fichas de un solo origen: un tramo con ficha del otro cuenta como «sin ficha propia»."""
        return RedEmpresa(list(self.tramos), dict(self.propias if origen == ORIGEN_PROPIA else self.catalogo))

    def cobertura(self) -> dict[str, Any]:
        """Por tramos y por longitud: con ficha propia, resueltos por el catálogo y sin resolver."""
        cuenta = {ORIGEN_PROPIA: [0, 0.0], ORIGEN_CATALOGO: [0, 0.0], None: [0, 0.0]}
        for codigo, longitud in self.tramos:
            origen = ORIGEN_PROPIA if codigo in self.propias else ORIGEN_CATALOGO if codigo in self.catalogo else None
            cuenta[origen][0] += 1
            cuenta[origen][1] += longitud
        total = sum(v[1] for v in cuenta.values())
        return {'tramos': len(self.tramos), 'con_ficha_propia': cuenta[ORIGEN_PROPIA][0],
                'resueltos_catalogo': cuenta[ORIGEN_CATALOGO][0], 'no_resueltos': cuenta[None][0],
                'longitud_resuelta_catalogo': cuenta[ORIGEN_CATALOGO][1] / total if total else None,
                'origen_catalogo': ORIGEN_CATALOGO}


def red_de_modelo(modelo: Any, *, resolver: Callable[[Any], Any] | None = None) -> RedVnr:
    """112:RF-22 y RF-23: los tramos MT (código de conductor y longitud) del modelo canónico de una copia de VNR-GIS (el
    que devuelve ``cargar_copia``) y sus fichas (R1, X1 y corriente admisible), cada una con su origen.

    Primero las que trae la copia (propias). Después ``resolver`` (en la conversión, ``fichas_del_catalogo`` de
    ``adaptadores/sources/vnr.py`` con el catálogo universal, 053) completa en el modelo las que faltan, y esas son del
    catálogo. Solo cuenta una ficha con R1, X1 y corriente; un conductor sin ninguna queda sin resolver. El resolutor no
    amplía el catálogo: la evaluación solo lo lee."""
    red = RedVnr()
    for tramo in modelo.sections:
        if tramo.conductor_code:
            red.tramos.append((str(tramo.conductor_code), _positivo(tramo.length_m)))

    def fichas() -> dict[str, Ficha]:
        salida: dict[str, Ficha] = {}
        for c in modelo.conductor_types:
            ficha = _ficha_con_datos(c.r1_ohm_km, c.x1_ohm_km, c.ampacity_a) if c.conductor_code else None
            if ficha is not None:
                salida.setdefault(str(c.conductor_code), ficha)
        return salida

    red.propias = fichas()
    if resolver is not None:
        resolver(modelo)
        red.catalogo = {c: f for c, f in fichas().items() if c not in red.propias}
    return red


def guardar_red(red: RedVnr, carpeta: Path | str) -> Path:
    """``red_vnr.json`` en la carpeta de la empresa, con escritura atómica: solo códigos de conductor, longitudes y
    fichas con su origen, ningún nombre ni coordenada."""
    ruta = Path(carpeta) / RED_VNR
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fichas = {c: {'r1': f.r1, 'x1': f.x1, 'amps': f.amps, 'origen': origen}
              for origen, grupo in ((ORIGEN_CATALOGO, red.catalogo), (ORIGEN_PROPIA, red.propias))
              for c, f in sorted(grupo.items())}
    write_json_atomic(ruta, {'esquema': ESQUEMA_RED, 'tramos': [list(t) for t in red.tramos],
                             'fichas': dict(sorted(fichas.items())), 'cobertura': red.cobertura()})
    return ruta


def _leer_red_vnr(ruta: Path) -> RedVnr:
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    esquema = datos.get('esquema')
    if esquema not in (ESQUEMA_RED, ESQUEMA_RED_V1):
        raise ValueError(f'{ruta.name}: esquema {esquema!r}, se esperaba {ESQUEMA_RED!r}')
    red = RedVnr([(str(c), _positivo(longitud)) for c, longitud in datos.get('tramos') or []])
    for codigo, valores in (datos.get('fichas') or {}).items():
        if esquema == ESQUEMA_RED_V1:
            ficha, origen = _ficha_con_datos(*valores), ORIGEN_PROPIA
        else:
            ficha, origen = _ficha_con_datos(valores.get('r1'), valores.get('x1'), valores.get('amps')), valores.get('origen')
        if ficha is not None:
            (red.catalogo if origen == ORIGEN_CATALOGO else red.propias)[str(codigo)] = ficha
    return red


def leer_red_vnr(carpeta: Path | str) -> RedVnr:
    """112:RF-23: los tramos y las fichas por origen de una carpeta; las del trío TXT cuentan como propias."""
    if (Path(carpeta) / RED_VNR).is_file():
        return _leer_red_vnr(Path(carpeta) / RED_VNR)
    red = leer_red_empresa(carpeta)
    return RedVnr(red.tramos, dict(red.fichas))


def leer_red_empresa(carpeta: Path | str) -> RedEmpresa:
    """Tramos y fichas de una carpeta: su ``red_vnr.json`` (112:RF-22) o, si no lo tiene, su trío TXT, donde el RED y
    el BD_Equipo se reconocen por sus secciones."""
    if (Path(carpeta) / RED_VNR).is_file():
        return _leer_red_vnr(Path(carpeta) / RED_VNR).red(ORIGEN_PROPIA)
    red = RedEmpresa()
    for ruta in sorted(Path(carpeta).rglob('*.txt'), key=lambda p: p.as_posix().lower()):
        f = leer_fichero(ruta, ruta.name)
        for e in f.entradas:
            if e[0] != 'fila':
                continue
            seccion, fila = e[1], e[2]
            if seccion in _SECCIONES_TRAMO and fila.get('LineCableID'):
                longitud = _numero(fila.get('Length', ''))
                red.tramos.append((fila['LineCableID'], longitud if np.isfinite(longitud) and longitud > 0 else 0.0))
            elif seccion in TABLAS_TIPOS_LINEA and fila.get('ID'):
                red.fichas.setdefault(fila['ID'], Ficha(_numero(fila.get('R1', '')), _numero(fila.get('X1', '')),
                                                        _numero(fila.get('Amps', ''))))
    return red


def evaluar_vnr(raiz: Path | str, *, umbral: float = UMBRAL_ACIERTO, tolerancia: float = TOLERANCIA_FICHA) -> dict[str, Any]:
    """112:RF-17, RF-22 y RF-23. Si alguna empresa trae fichas resueltas por el catálogo universal, el veredicto mide
    sobre ellas y el informe separa aparte la evaluación con fichas propias; si no, mide sobre las propias, como antes.
    El informe dice qué mide y la cobertura del catálogo de cada empresa."""
    redes = {e: leer_red_vnr(c) for e, c in empresas_de(raiz).items()}
    # 112:RF-22: una empresa sin tramos es una conversión que no se hizo: el veredicto saldría de carpetas vacías.
    vacias = sorted(e for e, red in redes.items() if not red.tramos)
    if vacias:
        raise SinEmpresas(f'{", ".join(vacias)} sin tramos: ni {RED_VNR} ni un trío TXT con tramos')

    def evaluar(origen: str) -> dict[str, Any]:
        datos = {e: r.red(origen) for e, r in redes.items()}
        resultado = dejar_una_fuera(datos, ajustar_catalogo,
                                    lambda cat, red: medir_catalogo(cat, red, tolerancia=tolerancia),
                                    criterio_catalogo(umbral))
        return {**resultado.como_dict(), 'fichas': origen, 'que_mide': QUE_MIDE[origen]}

    con_catalogo = any(r.catalogo for r in redes.values())
    informe = {'esquema': ESQUEMA, 'tarea': 'conversion_vnr',
               **evaluar(ORIGEN_CATALOGO if con_catalogo else ORIGEN_PROPIA),
               'criterio': {'metrica': 'acierto', 'umbral': umbral, 'tolerancia_ficha': tolerancia}}
    if con_catalogo:
        informe['ficha_propia'] = (evaluar(ORIGEN_PROPIA) if any(r.propias for r in redes.values()) else
                                   {'evaluada': False, 'fichas': ORIGEN_PROPIA,
                                    'motivo': 'ninguna fuente trae la impedancia de sus conductores'})
        informe['cobertura_catalogo'] = {e: redes[e].cobertura() for e in sorted(redes)}
    return informe


# ------------------------------------------------------------------ pronóstico


def _celdas(t: np.ndarray) -> np.ndarray:
    minutos = np.asarray(t, dtype='datetime64[m]').astype(np.int64)
    dias = minutos // 1440
    return ((dias + 3) % 7) * 96 + (minutos % 1440) // 15        # el 1970-01-01 fue jueves: lunes = 0


def _series_de(carpeta: Path) -> list[tuple[np.ndarray, np.ndarray]]:
    """Las series de potencia activa con media positiva: la Q cruza el cero con los bancos y no se normaliza."""
    objetivos, _exogenas = leer(carpeta)
    salida = []
    for o in sorted(objetivos, key=lambda o: (o.clase, o.ident, o.magnitud)):
        if o.magnitud.lower() == 'kvar':
            continue
        t, y = arreglos(o)
        orden = np.argsort(t, kind='stable')
        t, y = t[orden], y[orden]
        if len(y) and np.nanmean(y) > 0:
            salida.append((t, y))
    return salida


def ajustar_forma(entrenamiento: Mapping[str, Sequence[tuple[np.ndarray, np.ndarray]]]) -> np.ndarray:
    """La forma semanal de las empresas de entrenamiento: mediana por celda de cada serie dividida por su media."""
    celdas, valores = [], []
    for empresa in sorted(entrenamiento):
        for t, y in entrenamiento[empresa]:
            ok = np.isfinite(y)
            media = float(np.mean(y[ok])) if ok.any() else 0.0
            if media <= 0:
                continue
            celdas.append(_celdas(t[ok]))
            valores.append(y[ok] / media)
    forma = np.ones(CELDAS)
    if not celdas:
        return forma
    c, v = np.concatenate(celdas), np.concatenate(valores)
    for k in np.unique(c):
        forma[k] = float(np.median(v[c == k]))
    return forma


def medir_forma(forma: np.ndarray, series: Sequence[tuple[np.ndarray, np.ndarray]], *,
                horizonte_dias: int = HORIZONTE_DIAS) -> dict[str, Any]:
    """WAPE de la forma de las demás y de la base «semanal» propia, en el mismo origen de cada serie de la retenida."""
    error_forma = error_base = energia = 0.0
    medidas = 0
    for t, y in series:
        if len(t) < 2:
            continue
        origen = t[-1] - np.timedelta64(horizonte_dias, 'D')
        antes, despues = t <= origen, t > origen
        if antes.sum() < 96 * 7 or not despues.any():
            continue                                  # sin una semana de historia no hay base con que comparar
        t_h, y_h, t_f, y_f = t[antes], y[antes], t[despues], y[despues]
        cerca = t_h >= t_h[-1] - np.timedelta64(horizonte_dias, 'D')
        nivel = float(np.nanmean(y_h[cerca]))
        escala = escala_estacional(t_h, y_h)
        m_forma = medir(y_f, nivel * forma[_celdas(t_f)], escala)
        m_base = medir(y_f, predecir('semanal', t_h, y_h, t_f), escala)
        if not m_base.get('energia'):
            continue
        error_forma += m_forma['error_abs']
        error_base += m_base['error_abs']
        energia += m_base['energia']
        medidas += 1
    return {'series': medidas, 'horizonte_dias': horizonte_dias,
            'wape_forma_de_las_demas': error_forma / energia if energia else None,
            'wape_base_propia': error_base / energia if energia else None}


def criterio_forma(margen: float = MARGEN_PRONOSTICO):
    def criterio(m: Mapping[str, Any]) -> tuple[bool, str]:
        forma, base = m.get('wape_forma_de_las_demas'), m.get('wape_base_propia')
        if forma is None or base is None:
            return False, 'sin series con una semana de historia y un horizonte que medir'
        if forma > base * (1 + margen):
            return False, (f'la forma de las demás da un WAPE de {forma:.3f}, peor que su base propia ({base:.3f}) '
                           f'en más del {margen:.0%}')
        return True, f'WAPE {forma:.3f} frente a {base:.3f} de su base propia'
    return criterio


def evaluar_pronostico(raiz: Path | str, *, margen: float = MARGEN_PRONOSTICO,
                       horizonte_dias: int = HORIZONTE_DIAS) -> dict[str, Any]:
    datos = {e: _series_de(c) for e, c in empresas_de(raiz).items()}
    resultado = dejar_una_fuera(datos, ajustar_forma,
                                lambda forma, series: medir_forma(forma, series, horizonte_dias=horizonte_dias),
                                criterio_forma(margen))
    return {'esquema': ESQUEMA, 'tarea': 'pronostico', **resultado.como_dict(),
            'criterio': {'metrica': 'wape', 'margen_sobre_la_base': margen, 'base': 'semanal',
                         'horizonte_dias': horizonte_dias}}


def escribir_informe(informe: Mapping[str, Any], ruta: Path | str) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(ruta, dict(informe))
    return ruta
