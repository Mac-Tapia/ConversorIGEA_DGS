"""Dejar una empresa fuera cada vez con datos en disco: conversión VNR y pronóstico (112:RF-15 a RF-19).

Cada empresa es una subcarpeta de la carpeta que se da. Su nombre no sale nunca en el informe: las empresas se
renombran ``E1…En`` por el orden de su huella (``seudonimos_de_empresa`` de las cohortes), y el informe dice cuántas hay.

- Conversión VNR: la subcarpeta tiene el trío TXT de CYMDIST que sacó ``vnr-etl convert --format cymdist`` del paquete
  público de esa empresa. Del RED se toman los tramos (código de conductor y longitud) y del BD_Equipo sus fichas.
- Pronóstico: la subcarpeta es un benchmark de series de la 112 (``series.csv`` y ``series_objetivos.csv``). Lo que se
  ajusta con las demás es la forma semanal normalizada (cada serie por su media, mediana por día y cuarto de hora), y en la
  retenida se pronostica su nivel de los últimos 28 días por esa forma; se compara con su propia base «semanal» del 089
  en el mismo origen, con el WAPE del 089 (RF-18). Una forma aprendida de otras empresas que no empeora la base de la
  retenida es la que generaliza.

El informe se escribe con ``write_json_atomic`` (001:RF-5) y lleva el veredicto, su motivo, los criterios y cada pliegue.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
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


def leer_red_empresa(carpeta: Path | str) -> RedEmpresa:
    """Tramos y fichas del trío TXT de una carpeta; el RED y el BD_Equipo se reconocen por sus secciones."""
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
    datos = {e: leer_red_empresa(c) for e, c in empresas_de(raiz).items()}
    resultado = dejar_una_fuera(datos, ajustar_catalogo, lambda cat, red: medir_catalogo(cat, red, tolerancia=tolerancia),
                                criterio_catalogo(umbral))
    return {'esquema': ESQUEMA, 'tarea': 'conversion_vnr', **resultado.como_dict(),
            'criterio': {'metrica': 'acierto', 'umbral': umbral, 'tolerancia_ficha': tolerancia}}


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
