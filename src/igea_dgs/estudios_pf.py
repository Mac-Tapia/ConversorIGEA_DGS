"""Lo que los estudios de la spec 011 deciden sin DIgSILENT.

El guion ``tools/estudios_pf.py`` ejecuta cada estudio en «Sin proyecto» y en «Con
proyecto» y devuelve, por caso, alimentador y estudio, una **medida**: si converge, las
tensiones extremas, el elemento más cargado, la cabecera, las pérdidas y la lista de
barras y elementos con su valor. Aquí está todo lo que se hace con esas medidas y no
necesita PowerFactory, para poder probarlo con datos sorteados:

- qué estudios se ofrecen y cuáles no, con el dato que les falta (RF-23, RF-24);
- los límites de tensión y cargabilidad del perfil de empresa (RF-35);
- las violaciones de cada medida y las que solo aparecen con proyecto (RF-33, RF-34);
- la diferencia entre con proyecto y sin proyecto (RF-32);
- los dos ficheros de resultados, siempre iguales para las mismas medidas (RF-37).

Los límites no tienen valores de una empresa (constitución P13): sin perfil se usan
±5 % y 100 %, y el informe dice que son los de por defecto.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from .studies import ESTUDIOS, Estudio

#: Los estudios de esta iteración (usuario, 2026-10-11), en el orden del catálogo.
ESTUDIOS_011 = tuple(e.clave for e in ESTUDIOS if e.clave in {
    'flujo', 'flujo_desequilibrado', 'contingencias', 'troncal',
    'punto_apertura', 'perfil_tension', 'balance_fases'})

#: La red como se importó: referencia, sin estudios ni obras (RF-58).
CASO_BASE = 'Caso base'
SIN_PROYECTO = 'Sin proyecto'
CON_PROYECTO = 'Con proyecto'
#: Caso de las filas que dan con proyecto menos sin proyecto (RF-32).
DIFERENCIA = 'Diferencia (con − sin)'

#: Valores numéricos de una medida que se restan entre los dos casos.
VALORES = ('vm_min', 'vm_max', 'cargabilidad_max', 'cabecera_kw', 'cabecera_kvar', 'perdidas_kw')

COLUMNAS_RESULTADOS = (
    'caso', 'alimentador', 'estudio', 'converge', 'vm_min', 'vm_min_barra', 'vm_max',
    'vm_max_barra', 'mas_cargado', 'cargabilidad_max', 'cabecera_kw', 'cabecera_kvar',
    'perdidas_kw', 'violaciones')
COLUMNAS_VIOLACIONES = (
    'caso', 'alimentador', 'estudio', 'tipo', 'elemento', 'valor', 'limite', 'nueva')


class EstudiosError(ValueError):
    """Petición de estudios o límites que no se pueden usar; el mensaje es para el operador."""


# --------------------------------------------------------------------------- catálogo
def estudios_ofrecidos() -> tuple[Estudio, ...]:
    """Los de RF-23. Todos son defendibles hoy; si uno dejara de serlo, no se ofrece."""
    return tuple(e for e in ESTUDIOS if e.clave in ESTUDIOS_011 and e.defendible)


def estudios_no_ofrecidos() -> list[dict[str, Any]]:
    """Los demás del catálogo con lo que les falta (RF-24).

    Un estudio defendible que no está en la iteración (el flujo óptimo) no tiene dato
    faltante: se dice que queda fuera, en vez de inventarle uno.
    """
    ofrecidos = {e.clave for e in estudios_ofrecidos()}
    out = []
    for e in ESTUDIOS:
        if e.clave in ofrecidos:
            continue
        falta = [x.nombre for x in e.bloqueantes]
        motivo = ('faltan datos: ' + '; '.join(falta)) if falta else 'fuera de esta iteración'
        out.append({'clave': e.clave, 'nombre': e.nombre, 'falta': falta, 'motivo': motivo})
    return out


def validar_estudios(claves: Iterable[str]) -> tuple[str, ...]:
    """Los pedidos, sin repetir y en el orden del catálogo; error si alguno no se ofrece."""
    pedidos = set(claves)
    if not pedidos:
        raise EstudiosError('Elija al menos un estudio.')
    no = {o['clave']: o for o in estudios_no_ofrecidos()}
    malos = sorted(c for c in pedidos if c not in ESTUDIOS_011)
    if malos:
        partes = [f"{no[c]['nombre']} ({no[c]['motivo']})" if c in no else f'{c} (no existe)'
                  for c in malos]
        raise EstudiosError('No se pueden ejecutar: ' + '; '.join(partes) + '.')
    return tuple(c for c in ESTUDIOS_011 if c in pedidos)


# --------------------------------------------------------------------------- límites
@dataclass(frozen=True)
class Limites:
    """Límites con que se juzga cada medida (RF-35)."""

    tension_min_pu: float
    tension_max_pu: float
    cargabilidad_max_pct: float
    origen: str = 'por defecto'
    """«perfil», «operador» o «por defecto»: el informe dice de dónde salen."""

    def __post_init__(self) -> None:
        for nombre in ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct'):
            v = getattr(self, nombre)
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                raise EstudiosError(f'El límite {nombre} tiene que ser un número positivo: {v!r}.')
        if not self.tension_min_pu < 1.0 < self.tension_max_pu:
            raise EstudiosError(
                f'Los límites de tensión tienen que dejar 1 p.u. dentro: '
                f'{self.tension_min_pu} – {self.tension_max_pu}.')

    def con(self, **cambios: float) -> 'Limites':
        """Los mismos límites con los que cambia el operador antes de ejecutar."""
        cambios = {k: v for k, v in cambios.items() if v is not None}
        return replace(self, **cambios, origen='operador') if cambios else self


#: Sin perfil: ±5 % y 100 %, los habituales de la norma, no los de una empresa.
LIMITES_POR_DEFECTO = Limites(0.95, 1.05, 100.0)

#: Clave del perfil de empresa con los límites de los estudios.
CLAVE_PERFIL = 'estudios'


def limites_de_perfil(ruta: Path | None = None) -> Limites:
    """Límites de la clave ``estudios`` de ``config/perfil_empresa.json``.

    Cada valor que el perfil no da toma el de por defecto. Un perfil con un valor
    imposible es un error, no se ignora: estudiar con un límite que nadie eligió daría
    violaciones que no son.
    """
    if ruta is None:
        from .carpeta_pf import ruta_perfil
        ruta = ruta_perfil()
    ruta = Path(ruta)
    if not ruta.is_file():
        return LIMITES_POR_DEFECTO
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise EstudiosError(f'No se pudo leer el perfil de empresa {ruta.name}: {exc}') from exc
    seccion = datos.get(CLAVE_PERFIL) if isinstance(datos, dict) else None
    if not isinstance(seccion, dict) or not seccion:
        return LIMITES_POR_DEFECTO
    valores = {k: seccion[k] for k in ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct')
               if k in seccion}
    try:
        return replace(LIMITES_POR_DEFECTO, **valores, origen='perfil')
    except EstudiosError as exc:
        raise EstudiosError(f'{exc} (perfil {ruta.name}, clave {CLAVE_PERFIL!r})') from exc


# --------------------------------------------------------------------------- medidas
def violaciones(medida: Mapping[str, Any], limites: Limites) -> list[dict[str, Any]]:
    """Barras fuera de tensión y elementos sobrecargados de una medida (RF-33).

    Sin convergencia no hay valores que juzgar: la medida ya dice que no convergió.
    Orden: tipo y elemento, para que el fichero no dependa del orden de DIgSILENT.
    """
    if not medida.get('converge'):
        return []
    out = []
    for nombre, u in medida.get('barras') or ():
        if u is None:
            continue
        if u < limites.tension_min_pu:
            out.append({'tipo': 'tension_baja', 'elemento': nombre, 'valor': u,
                        'limite': limites.tension_min_pu})
        elif u > limites.tension_max_pu:
            out.append({'tipo': 'tension_alta', 'elemento': nombre, 'valor': u,
                        'limite': limites.tension_max_pu})
    for nombre, _clase, carga in medida.get('elementos') or ():
        if carga is not None and carga > limites.cargabilidad_max_pct:
            out.append({'tipo': 'sobrecarga', 'elemento': nombre, 'valor': carga,
                        'limite': limites.cargabilidad_max_pct})
    return sorted(out, key=lambda v: (v['tipo'], v['elemento']))


def diferencia(con: Mapping[str, Any], sin: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Con proyecto menos sin proyecto, valor a valor (RF-32); sin dato, ``None``."""
    if sin is None:
        return None
    out = {}
    for k in VALORES:
        a, b = con.get(k), sin.get(k)
        out[k] = a - b if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
    return out


def _clave(r: Mapping[str, Any]) -> tuple[str, str]:
    return r['alimentador'], r['estudio']


def _orden_estudio(clave: str) -> int:
    return ESTUDIOS_011.index(clave) if clave in ESTUDIOS_011 else len(ESTUDIOS_011)


def _ordenadas(filas: list[dict[str, Any]], *extra: str) -> list[dict[str, Any]]:
    return sorted(filas, key=lambda f: (f['caso'], f['alimentador'], _orden_estudio(f['estudio']),
                                        *(str(f[k]) for k in extra)))


def filas_resultados(resultados: Iterable[Mapping[str, Any]], limites: Limites) -> list[dict[str, Any]]:
    """Una fila por caso, alimentador y estudio, y la de la diferencia (RF-37)."""
    resultados = list(resultados)
    sin = {_clave(r): r for r in resultados if r['caso'] == SIN_PROYECTO}
    filas = []
    for r in resultados:
        fila = {c: r.get(c) for c in COLUMNAS_RESULTADOS}
        fila['violaciones'] = len(violaciones(r, limites))
        filas.append(fila)
        if r['caso'] == CON_PROYECTO:
            d = diferencia(r, sin.get(_clave(r)))
            if d is not None:
                base = sin[_clave(r)]
                filas.append({c: None for c in COLUMNAS_RESULTADOS} | d | {
                    'caso': DIFERENCIA, 'alimentador': r['alimentador'], 'estudio': r['estudio'],
                    'converge': bool(r.get('converge') and base.get('converge')),
                    'violaciones': fila['violaciones'] - len(violaciones(base, limites))})
    return _ordenadas(filas)


def filas_violaciones(resultados: Iterable[Mapping[str, Any]], limites: Limites) -> list[dict[str, Any]]:
    """Una fila por violación; las de con proyecto que no están sin proyecto, marcadas (RF-34)."""
    resultados = list(resultados)
    previas = {(*_clave(r), v['tipo'], v['elemento'])
               for r in resultados if r['caso'] == SIN_PROYECTO for v in violaciones(r, limites)}
    filas = []
    for r in resultados:
        for v in violaciones(r, limites):
            nueva = r['caso'] == CON_PROYECTO and (*_clave(r), v['tipo'], v['elemento']) not in previas
            filas.append({'caso': r['caso'], 'alimentador': r['alimentador'], 'estudio': r['estudio'],
                          **v, 'nueva': 'sí' if nueva else ''})
    return _ordenadas(filas, 'tipo', 'elemento')


def _texto(v: Any) -> str:
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'sí' if v else 'no'
    if isinstance(v, float):
        return f'{v:.4f}'
    return str(v)


def escribir_csv(filas: Iterable[Mapping[str, Any]], columnas: tuple[str, ...], destino: Path) -> Path:
    """CSV con «;» y BOM, como las plantillas de cargas: Excel en español lo abre bien.

    Los decimales van con cuatro cifras fijas: así dos ejecuciones con las mismas medidas
    dan el mismo fichero byte a byte.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(columnas)
        for f in filas:
            w.writerow([_texto(f.get(c)) for c in columnas])
    return destino
