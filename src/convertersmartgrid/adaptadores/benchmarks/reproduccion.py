"""Reproducción del estudio: el benchmark tiene que dar el mismo resultado que el original (112:RF-3).

Un benchmark que no reproduce el estudio no sirve para comparar métodos: los resultados no dirían nada de la red real.
Se corre el mismo estudio en los dos —la única vía de conversión, ``reglas`` (P5), y el oráculo abierto de pandapower—
y se compara alimentador a alimentador: tensión mínima y máxima, carga máxima de líneas y de transformadores,
recuento por clase y veredicto. Si algo se sale de la tolerancia, el informe dice qué magnitud y qué alimentador, con
su seudónimo: el informe se puede guardar junto al benchmark sin revelar el original.

La tolerancia es la del estudio si la declara; si no, 0,005 p.u. y un 1 % (decisión de la spec 112, 2026-11-14).
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...dominio.perfil_empresa import PerfilEmpresa
from ...dominio.benchmarks.seudonimos import Mapa


@dataclass(frozen=True)
class Tolerancia:
    """Lo que puede separarse el benchmark del original sin dejar de reproducirlo."""

    v_pu: float = 0.005
    #: Diferencia relativa de la carga máxima de líneas y transformadores (la corriente).
    corriente_rel: float = 0.01
    #: Diferencia relativa de WAPE y MASE de cada método de base del 089 (RF-11).
    metrica_rel: float = 0.01
    fuente: str = 'por defecto'


def tolerancia_para(declarada: Mapping[str, Any] | None) -> Tolerancia:
    """La tolerancia que declara el estudio (con su ``fuente``, p. ej. «spec 011») o la de por defecto."""
    if not declarada:
        return Tolerancia()
    base = Tolerancia()
    valores = {k: float(declarada.get(k, getattr(base, k))) for k in ('v_pu', 'corriente_rel', 'metrica_rel')}
    for k, v in valores.items():
        if not math.isfinite(v) or v < 0:
            raise ValueError(f'tolerancia {k} imposible: {v}')
    return Tolerancia(**valores, fuente=str(declarada.get('fuente') or 'declarada por el estudio'))


@dataclass(frozen=True)
class Motivo:
    """Una magnitud fuera de la tolerancia, en un elemento nombrado por su seudónimo."""

    magnitud: str
    elemento: str
    original: Any
    benchmark: Any
    limite: float | None = None

    def texto(self) -> str:
        limite = f' (tolerancia {self.limite:g})' if self.limite is not None else ''
        return f'{self.elemento}: {self.magnitud} {self.original!r} en el original y {self.benchmark!r} en el benchmark{limite}'


@dataclass
class InformeReproduccion:
    tolerancia: Tolerancia
    metricas_original: dict[str, dict[str, Any]] = field(default_factory=dict)
    metricas_benchmark: dict[str, dict[str, Any]] = field(default_factory=dict)
    motivos: list[Motivo] = field(default_factory=list)

    @property
    def reproduce(self) -> bool:
        return not self.motivos


class ReproduccionFallida(ValueError):
    """El benchmark no reproduce el estudio del original: no se emite."""


def exigir(informe: InformeReproduccion) -> InformeReproduccion:
    """Lanza :class:`ReproduccionFallida` con cada magnitud y elemento fuera de la tolerancia."""
    if not informe.reproduce:
        raise ReproduccionFallida('el benchmark no reproduce el estudio del original: '
                                  + '; '.join(m.texto() for m in informe.motivos[:20]))
    return informe


def estudiar_red(dataset, perfil: PerfilEmpresa | None = None) -> dict[str, dict[str, Any]]:
    """El estudio de cada alimentador por la vía única (``reglas``) y el oráculo: sus magnitudes, sin nombres."""
    from .. import oraculo
    from ...dominio.model import ModelBuildError, build_feeder_model
    from ...aplicacion.reglas import REGLAS_PROYECTO, aplicar_reglas, preparar_dataset, reglas_de_perfil

    preparar_dataset(dataset)
    reglas = reglas_de_perfil(perfil) if perfil is not None else REGLAS_PROYECTO
    salida: dict[str, dict[str, Any]] = {}
    for red in dataset.feeder_ids():
        try:
            modelo = build_feeder_model(dataset, red, strict=True)
        except ModelBuildError as exc:
            # Un alimentador que no se construye tiene que fallar igual en el benchmark: se compara la clase de error.
            salida[red] = {'error': type(exc).__name__}
            continue
        aplicar_reglas(modelo, reglas)
        inf = oraculo.validar(modelo)
        salida[red] = {'convergio': inf.convergio, 'v_min_pu': inf.v_min_pu, 'v_max_pu': inf.v_max_pu,
                       'carga_linea_max_pct': inf.carga_linea_max_pct,
                       'carga_trafo_max_pct': inf.carga_trafo_max_pct,
                       'recuento': inf.recuento, 'veredicto': inf.veredicto}
    return salida


def _fuera(magnitud: str, a: Any, b: Any, tol: Tolerancia) -> float | None | bool:
    """``False`` si está dentro; si no, el límite que se pasó (o ``None`` para las que deben ser iguales)."""
    if a is None or b is None:
        return False if a is None and b is None else None
    if magnitud in ('v_min_pu', 'v_max_pu'):
        return False if abs(a - b) <= tol.v_pu + 1e-12 else tol.v_pu
    if magnitud in ('carga_linea_max_pct', 'carga_trafo_max_pct'):
        escala = max(abs(a), 1e-9)
        return False if abs(a - b) / escala <= tol.corriente_rel + 1e-12 else tol.corriente_rel
    return False if a == b else None


MAGNITUDES_RED = ('error', 'convergio', 'v_min_pu', 'v_max_pu', 'carga_linea_max_pct', 'carga_trafo_max_pct',
                  'recuento', 'veredicto')


def comparar(original: Mapping[str, Mapping[str, Any]], benchmark: Mapping[str, Mapping[str, Any]],
             tol: Tolerancia, magnitudes: tuple[str, ...] = MAGNITUDES_RED) -> list[Motivo]:
    """Los motivos por los que ``benchmark`` no reproduce ``original``; ambos por seudónimo."""
    motivos = []
    for elemento in sorted(set(original) | set(benchmark)):
        if elemento not in original or elemento not in benchmark:
            motivos.append(Motivo('presencia', elemento, elemento in original, elemento in benchmark))
            continue
        o, b = original[elemento], benchmark[elemento]
        for m in magnitudes:
            if m not in o and m not in b:
                continue
            limite = _fuera(m, o.get(m), b.get(m), tol)
            if limite is not False:
                motivos.append(Motivo(m, elemento, o.get(m), b.get(m), limite))
    return motivos


def reproducir_red(trio: tuple[Path | str, Path | str, Path | str], carpeta: Path | str, *, mapa: Mapa,
                   perfil: PerfilEmpresa | None = None, perfil_neutro: PerfilEmpresa | None = None,
                   tolerancia: Mapping[str, Any] | None = None) -> InformeReproduccion:
    """Corre el estudio en el origen y en el benchmark de ``carpeta`` y los compara con la tolerancia."""
    from ..dataset import CymdistDataset

    tol = tolerancia_para(tolerancia)
    carpeta = Path(carpeta)
    original = estudiar_red(CymdistDataset.from_files(*trio), perfil)
    bench = estudiar_red(CymdistDataset.from_files(carpeta / 'RED.txt', carpeta / 'CARGA.txt',
                                                   carpeta / 'BD_Equipo.txt'), perfil_neutro)
    por_seudonimo = {str(mapa('alimentador', red)): m for red, m in original.items()}
    return InformeReproduccion(tol, por_seudonimo, bench, comparar(por_seudonimo, bench, tol))


def _metricas_de_base(objetivo, exogenas) -> dict[str, Any]:
    """WAPE y MASE de cada método de base del 089 en su origen de prueba (``backtest_objetivo``, CPU, sin GPU)."""
    from ..pronostico_demanda import backtest_objetivo

    r = backtest_objetivo(objetivo, exogenas=exogenas)
    if r.get('status') != 'EVALUADO':
        return {'status': r.get('status'), 'prueba': {}}
    return {'status': 'EVALUADO',
            'prueba': {m: {'wape': v.get('wape'), 'mase': v.get('mase')} for m, v in sorted(r['prueba'].items())}}


def _comparar_series(original: Mapping[str, Mapping[str, Any]], benchmark: Mapping[str, Mapping[str, Any]],
                     tol: Tolerancia) -> list[Motivo]:
    motivos = []
    for nombre in sorted(set(original) | set(benchmark)):
        o, b = original.get(nombre), benchmark.get(nombre)
        if o is None or b is None:
            motivos.append(Motivo('presencia', nombre, o is not None, b is not None))
            continue
        if o['status'] != b['status']:
            motivos.append(Motivo('status', nombre, o['status'], b['status']))
            continue
        for metodo in sorted(set(o['prueba']) | set(b['prueba'])):
            for metrica in ('wape', 'mase'):
                a = (o['prueba'].get(metodo) or {}).get(metrica)
                c = (b['prueba'].get(metodo) or {}).get(metrica)
                if a is None and c is None:
                    continue
                if a is None or c is None or not math.isfinite(a) or not math.isfinite(c):
                    if a != c:
                        motivos.append(Motivo(f'{metodo}.{metrica}', nombre, a, c))
                    continue
                if abs(a - c) / max(abs(a), 1e-12) > tol.metrica_rel + 1e-12:
                    motivos.append(Motivo(f'{metodo}.{metrica}', nombre, a, c, tol.metrica_rel))
    return motivos


def reproducir_series(dataset, carpeta: Path | str, *, mapa: Mapa,
                      tolerancia: Mapping[str, Any] | None = None) -> InformeReproduccion:
    """WAPE y MASE de los métodos de base en el original y en el benchmark, por seudónimo, dentro del 1 % (RF-11)."""
    from .series import leer, nombre_publicado

    tol = tolerancia_para(tolerancia)
    original = {nombre_publicado(o, mapa): _metricas_de_base(o, dataset.exogenas) for o in dataset.objetivos}
    objetivos, exogenas = leer(carpeta)
    bench = {o.nombre: _metricas_de_base(o, exogenas) for o in objetivos}
    return InformeReproduccion(tol, original, bench, _comparar_series(original, bench, tol))
