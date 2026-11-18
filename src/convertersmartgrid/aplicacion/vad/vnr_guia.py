"""VNR según la «Guía de Elaboración del VNR de las Instalaciones de Distribución Eléctrica» (RCD 232-2017-OS/CD;
spec 108, RF-21 a RF-25).

El VNR adaptado es la entrada de la anualidad del VAD: VNR = MIE × CEIE + MINE × CINE (art. 17.2). Este módulo arma
sus piezas en el orden de la Guía, y cada número sale del registro normativo (``config/normativa/rcd_232_2017.json``):

- **Zonificación** (art. 22, :func:`zonificar`): cuadrículas UTM de 1000, 500 y 250 m alineadas a múltiplos de mil; la
  densidad de cada una es la suma de la máxima demanda de sus SED (de la empresa y de terceros, del año previo a la
  fijación) entre su área. Las de «Muy Alta» quedan fijas en cada nivel; el resto se subdivide. En las de 250 m se
  asignan las cinco zonas de la Tabla N° 1; la cuadrícula cuya zona difiere de TODAS las que la rodean adopta la
  predominante (si hay empate, no hay predominante y conserva la suya); las de densidad cero se eliminan. Mapa de MT
  con todas las SED y de BT con las de uso no industrial (art. 22.8).
- El alumbrado público se asigna a su SED con el factor de carga y el de coincidencia del art. 22.3
  (:func:`demanda_de_alumbrado`).
- Un punto fuera de toda cuadrícula está en Zona de Baja Densidad (art. 23.2, :meth:`Zonificacion.zona_en`).
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Literal

from ...dominio.registro_normativo import RegistroNormativo

REGLA_ZONAS = 'vnr.zonas.densidad'
REGLA_LADOS = 'vnr.cuadricula.lados_m'
REGLA_FC_AP = 'vnr.ap.factor_carga'
REGLA_FCOINC_AP = 'vnr.ap.factor_coincidencia'
ZONA_FUERA = 'Baja'  # art. 23.2: las porciones de red fuera de toda cuadrícula, en Zona de Baja Densidad
HORAS_ANIO = 8760.0

Mapa = Literal['MT', 'BT']


class VnrGuiaError(ValueError):
    """Un dato que la Guía no permite usar tal como llega: se dice cuál y por qué."""


@dataclass(frozen=True)
class SedZonificable:
    """Una SED para la zonificación: sus coordenadas UTM (m), su máxima demanda (kW, del año previo a la fijación) y su
    uso. ``alumbrado_kw`` es la demanda del AP ya asignada a la SED (:func:`demanda_de_alumbrado`)."""

    codigo: str
    x: float
    y: float
    md_kw: float
    industrial: bool = False
    tercero: bool = False
    alumbrado_kw: float = 0.0

    @property
    def demanda_kw(self) -> float:
        return self.md_kw + self.alumbrado_kw


@dataclass(frozen=True)
class Cuadricula:
    x0: float
    y0: float
    lado_m: int
    demanda_kw: float
    zona: str
    seds: tuple[str, ...]
    zona_calculada: str = ''  # la de su densidad, si la predominante la cambió

    @property
    def densidad_mw_km2(self) -> float:
        return (self.demanda_kw / 1000.0) / ((self.lado_m / 1000.0) ** 2)

    def contiene(self, x: float, y: float) -> bool:
        return self.x0 <= x < self.x0 + self.lado_m and self.y0 <= y < self.y0 + self.lado_m


@dataclass
class Zonificacion:
    mapa: Mapa
    cuadriculas: list[Cuadricula]
    citas: dict[str, str] = field(default_factory=dict)  # clave de la regla → «acto, artículo»

    def zona_en(self, x: float, y: float) -> str:
        for c in self.cuadriculas:
            if c.contiene(x, y):
                return c.zona
        return ZONA_FUERA

    def resumen(self) -> dict[str, int]:
        return dict(Counter(c.zona for c in self.cuadriculas))


def _valor(registro: RegistroNormativo, clave: str, fecha: str | None, citas: dict[str, str]):
    v = registro.regla(clave, fecha)
    citas[clave] = f'{v.norma.acto}, {v.regla.articulo_o_anexo}'
    return v.regla.valor


def zona_de_densidad(densidad_mw_km2: float, zonas: Iterable[Mapping]) -> str:
    """La zona de la Tabla N° 1 (art. 22.1): «desde» incluido, «hasta» excluido."""
    for z in zonas:
        desde, hasta = z['desde_mw_km2'], z['hasta_mw_km2']
        if (desde is None or densidad_mw_km2 >= desde) and (hasta is None or densidad_mw_km2 < hasta):
            return z['zona']
    raise VnrGuiaError(f'densidad {densidad_mw_km2} MW/km2 fuera de la Tabla N° 1 registrada')


def demanda_de_alumbrado(energia_kwh_anual: float, registro: RegistroNormativo, fecha: str | None = None) -> float:
    """kW del AP asignado a una SED: energía anual / (8760 × FC) × factor de coincidencia (art. 22.3)."""
    citas: dict[str, str] = {}
    fc = float(_valor(registro, REGLA_FC_AP, fecha, citas))
    fco = float(_valor(registro, REGLA_FCOINC_AP, fecha, citas))
    if energia_kwh_anual < 0:
        raise VnrGuiaError(f'energía de alumbrado negativa: {energia_kwh_anual} kWh')
    return energia_kwh_anual / (HORAS_ANIO * fc) * fco


def _origen(v: float, lado: int) -> float:
    return math.floor(v / lado) * lado


def zonificar(seds: Iterable[SedZonificable], registro: RegistroNormativo, *, mapa: Mapa = 'MT',
              fecha: str | None = None) -> Zonificacion:
    """Mapa de densidad de carga del art. 22 (ver el docstring del módulo)."""
    citas: dict[str, str] = {}
    zonas = _valor(registro, REGLA_ZONAS, fecha, citas)
    lados = [int(x) for x in _valor(registro, REGLA_LADOS, fecha, citas)]
    if lados != sorted(lados, reverse=True) or any(lados[i] % lados[i + 1] for i in range(len(lados) - 1)):
        raise VnrGuiaError(f'lados de cuadrícula {lados}: cada uno debe dividir al anterior')
    muy_alta = next(z['zona'] for z in zonas if z['hasta_mw_km2'] is None)
    lista = [s for s in seds if mapa == 'MT' or not s.industrial]
    for s in lista:
        if s.md_kw < 0 or s.alumbrado_kw < 0:
            raise VnrGuiaError(f'SED {s.codigo}: demanda negativa')

    fijas: list[Cuadricula] = []
    pendientes = {(_origen(s.x, lados[0]), _origen(s.y, lados[0])): None for s in lista}
    for nivel, lado in enumerate(lados):
        ultimo = nivel == len(lados) - 1
        grupos: dict[tuple[float, float], list[SedZonificable]] = {}
        for s in lista:
            clave = (_origen(s.x, lado), _origen(s.y, lado))
            padre = (_origen(s.x, lados[nivel - 1]), _origen(s.y, lados[nivel - 1])) if nivel else clave
            if padre in pendientes:
                grupos.setdefault(clave, []).append(s)
        siguientes = {}
        for (x0, y0), del_grupo in sorted(grupos.items()):
            demanda = sum(s.demanda_kw for s in del_grupo)
            if demanda <= 0:
                continue  # art. 22.6.4: densidad cero, eliminada
            densidad = (demanda / 1000.0) / ((lado / 1000.0) ** 2)
            zona = zona_de_densidad(densidad, zonas)
            if zona == muy_alta or ultimo:
                fijas.append(Cuadricula(x0, y0, lado, demanda, zona, tuple(sorted(s.codigo for s in del_grupo))))
            else:
                siguientes[(x0, y0)] = None
        pendientes = siguientes
    return Zonificacion(mapa, _predominante(fijas, lados[-1]), citas)


def _predominante(cuadriculas: list[Cuadricula], lado: int) -> list[Cuadricula]:
    """Art. 22.6.3: la cuadrícula del último nivel cuya zona difiere de todas las que la rodean adopta la predominante de
    ellas. Las vecinas son las de cualquier tamaño que tocan sus ocho lados y esquinas; con empate, conserva la suya."""
    salida = []
    for c in cuadriculas:
        if c.lado_m != lado:
            salida.append(c)
            continue
        vecinas = [o for o in cuadriculas if o is not c and _tocan(c, o)]
        zonas = Counter(o.zona for o in vecinas)
        if not zonas or c.zona in zonas:
            salida.append(c)
            continue
        (primera, n1), *resto = zonas.most_common()
        if resto and resto[0][1] == n1:
            salida.append(c)  # sin predominante
            continue
        salida.append(Cuadricula(c.x0, c.y0, c.lado_m, c.demanda_kw, primera, c.seds, zona_calculada=c.zona))
    return salida


def _tocan(a: Cuadricula, b: Cuadricula) -> bool:
    return (a.x0 <= b.x0 + b.lado_m and b.x0 <= a.x0 + a.lado_m and a.y0 <= b.y0 + b.lado_m
            and b.y0 <= a.y0 + a.lado_m)


# ============================================================== adaptación (arts. 23 a 44 y Anexo 6) — 108:RF-22

SECTORES = ('urbano_alta', 'urbano_media_baja', 'urbano_rural', 'rural_ser')
ANEXO6_DEFECTO = Path(__file__).resolve().parents[4] / 'config' / 'vnr' / 'anexo6_equivalencias.json'


def cargar_anexo6(ruta: Path | str | None = None) -> dict:
    return json.loads(Path(ruta or ANEXO6_DEFECTO).read_text(encoding='utf-8'))


def _n(material: str) -> str:
    return ' '.join(material.split()).casefold()


@dataclass(frozen=True)
class Equivalencia:
    material: str
    seccion_mm2: float
    tabla: int


def equivalencia(anexo6: Mapping, origen: str, seccion_mm2: float, destino: str, nivel: str = 'MT') -> Equivalencia:
    """Cambio de tecnología (Anexo 6, tablas de tipo «tecnologia»): ``origen`` de ``seccion_mm2`` a ``destino``. Si la
    celda trae otro material, la equivalencia lo conserva (p. ej. «CU Desnudo 185»)."""
    if _n(origen) == _n(destino):
        return Equivalencia(destino, seccion_mm2, 0)
    for t in anexo6['tablas']:
        if t.get('tipo') != 'tecnologia' or t.get('nivel') != nivel:  # MT (tablas 4-6) y BT (7-9) no se mezclan
            continue
        cols = [_n(c) for c in t['columnas']]
        if _n(destino) not in cols:
            continue
        for f in t['filas']:
            if _n(f['origen']) == _n(origen) and f['seccion_mm2'] == seccion_mm2:
                v = f['valores'][cols.index(_n(destino))]
                if v is None:
                    break
                if isinstance(v, dict):
                    return Equivalencia(v['material'], v['seccion_mm2'], t['tabla'])
                return Equivalencia(t['columnas'][cols.index(_n(destino))], v, t['tabla'])
    raise VnrGuiaError(f'Anexo 6 ({nivel}) sin equivalencia de {origen} {seccion_mm2:g} mm2 en {destino}')


def equivalencia_de_tension(anexo6: Mapping, origen: str, seccion_mm2: float, kv: float) -> Equivalencia:
    """Adaptación de 2,3 kV y 5,8 kV a 10 kV (Anexo 6, tablas 1 a 3, potencia constante)."""
    col = {2.3: 0, 5.8: 1}.get(round(kv, 1))
    if col is None:
        return Equivalencia(origen, seccion_mm2, 0)
    for t in anexo6['tablas']:
        if t.get('tipo') == 'tension':
            for f in t['filas']:
                if _n(f['origen']) == _n(origen) and f['seccion_mm2'] == seccion_mm2:
                    return Equivalencia(origen, f['valores'][col], t['tabla'])
    raise VnrGuiaError(f'Anexo 6 sin equivalencia de tensión de {origen} {seccion_mm2:g} mm2 a {kv:g} kV')


def es_corrosivo(distancia_costa_km: float | None, registro: RegistroNormativo, anexo6: Mapping, *,
                 departamento: str = '', provincia: str = '', fecha: str | None = None) -> bool:
    """Ambiente corrosivo (art. 22.1 y Anexo 6, numeral 4): franja de 7 km de la costa, salvo las provincias de la
    Tabla N° 14, que tienen sus propios tramos (o ninguno)."""
    if distancia_costa_km is None:
        return False
    for t in anexo6['tablas']:
        if t.get('tipo') == 'corrosivo_excepciones':
            for f in t['filas']:
                if _n(f['departamento']) == _n(departamento) and _n(f['provincia']) == _n(provincia):
                    return any(a <= distancia_costa_km <= b for a, b in f['tramos_corrosivos_km'])
    ancho = float(registro.regla('vnr.corrosivo.ancho_km', fecha).regla.valor)
    return 0 <= distancia_costa_km <= ancho


def porciones_por_zona(puntos: list[tuple[float, float]], zonas: Zonificacion, paso_m: float = 5.0) -> dict[str, float]:
    """Longitud (m) de una polilínea en cada zona (arts. 23.2 y 26.1): cada segmento se parte en pasos de ``paso_m`` y
    cada paso cuenta en la zona de su punto medio; fuera de toda cuadrícula, Baja."""
    salida: dict[str, float] = {}
    for (x1, y1), (x2, y2) in pairwise(puntos):
        largo = math.hypot(x2 - x1, y2 - y1)
        n = max(1, math.ceil(largo / paso_m))
        for k in range(n):
            f = (k + 0.5) / n
            z = zonas.zona_en(x1 + (x2 - x1) * f, y1 + (y2 - y1) * f)
            salida[z] = salida.get(z, 0.0) + largo / n
    return salida


@dataclass(frozen=True)
class Tramo:
    """Una porción de tramo ya situada en su zona y su ambiente."""

    codigo: str
    material: str
    seccion_mm2: float
    longitud_m: float
    subterranea: bool
    zona: str
    corrosivo: bool
    kv: float | None = None
    fases: int = 3
    sed: str = ''           # BT: la SED a la que pertenece (art. 26.3, reparto por SED)
    sed_adaptada: str = ''  # BT: el tipo de su SED ya adaptada (art. 26.1.3)
    especial: str = ''      # 'historica' (art. 43) o 'calle_angosta' (art. 44)


@dataclass(frozen=True)
class TramoAdaptado:
    existente: Tramo
    material: str
    seccion_mm2: float
    subterranea: bool
    regla: str
    subcomponente: str = ''

    @property
    def longitud_m(self) -> float:
        return self.existente.longitud_m


def _criterio(registro: RegistroNormativo, sector: str, rubro: str, fecha: str | None) -> tuple[dict, str]:
    if sector not in SECTORES:
        raise VnrGuiaError(f'sector típico «{sector}» desconocido; válidos: {", ".join(SECTORES)}')
    v = registro.regla(f'vnr.adaptacion.{sector}.{rubro}', fecha)
    return v.regla.valor, f'{v.norma.acto}, {v.regla.articulo_o_anexo}'


def _a(anexo6, t: Tramo, destino: str, cita: str, subterranea: bool, subcomponente: str = '', nivel: str = 'MT'
       ) -> TramoAdaptado:
    seccion = equivalencia_de_tension(anexo6, t.material, t.seccion_mm2, t.kv).seccion_mm2 if t.kv else t.seccion_mm2
    e = equivalencia(anexo6, t.material, seccion, destino, nivel)
    return TramoAdaptado(t, e.material, e.seccion_mm2, subterranea, cita, subcomponente)


def _aBT(anexo6, t: Tramo, destino: str, cita: str, subterranea: bool, subcomponente: str = '') -> TramoAdaptado:
    return _a(anexo6, t, destino, cita, subterranea, subcomponente, nivel='BT')


def _especial(registro: RegistroNormativo, especial: str, fecha: str | None) -> str:
    e = registro.regla('vnr.adaptacion.zonas_historicas' if especial == 'historica'
                       else 'vnr.adaptacion.calles_angostas', fecha)
    return f'{e.norma.acto}, {e.regla.articulo_o_anexo}'


def adaptar_tramo_mt(t: Tramo, sector: str, registro: RegistroNormativo, anexo6: Mapping, *,
                     fecha: str | None = None) -> TramoAdaptado:
    """Un tramo de MT con los criterios de su sector (arts. 23, 28, 33 y 38) y de las zonas especiales (arts. 43 y 44).
    El tope del 14 % del art. 28.7 es del sistema eléctrico: lo aplica :func:`adaptar_red_mt`."""
    c, cita = _criterio(registro, sector, 'mt', fecha)
    desnudo = (c.get('aerea', {}).get('otras') or c.get('aerea', {}).get('todas') or
               c.get('aerea_y_subterranea') or {}).get('desnudo_por_ambiente', {})
    por_ambiente = desnudo.get('corrosivo' if t.corrosivo else 'no_corrosivo')
    if t.especial in ('historica', 'calle_angosta') and t.subterranea:
        return _a(anexo6, t, 'NA2XSY', _especial(registro, t.especial, fecha), True)
    if 'aerea_y_subterranea' in c:
        return _a(anexo6, t, por_ambiente, cita, False)
    autoportante = 'autoportante' in _n(t.material)
    de_cobre = _n(t.material).startswith('cu')
    if sector == 'urbano_alta':
        if t.subterranea:
            na = _a(anexo6, t, 'NA2XSY', cita, True)
            if t.zona in c['subterranea']['NA2XSY_en'] or \
                    na.seccion_mm2 >= c['subterranea']['media_baja']['NA2XSY_desde_mm2']:
                return na
            return _a(anexo6, t, por_ambiente, cita, False)
        if t.zona == 'Muy Alta':
            return _a(anexo6, t, 'NA2XSY', cita, False)
        if autoportante:
            auto = c['aerea']['otras']['autoportante']
            if t.zona in auto['zonas'] and de_cobre:
                try:
                    return _a(anexo6, t, auto['CU Autoportante'], cita, False)
                except VnrGuiaError:  # «siempre y cuando exista la equivalencia respectiva» (art. 23.6)
                    pass
            return TramoAdaptado(t, t.material, t.seccion_mm2, False, cita)
        return _a(anexo6, t, por_ambiente, cita, False)
    # urbano_media_baja (art. 28)
    if t.subterranea:
        return _a(anexo6, t, c['subterranea']['tipo'], cita, True)
    if autoportante:
        if de_cobre:
            return _a(anexo6, t, c['aerea']['todas']['autoportante']['CU Autoportante'], cita, False)
        return TramoAdaptado(t, t.material, t.seccion_mm2, False, cita)
    return _a(anexo6, t, por_ambiente, cita, False)


def _tope(lista: list[Tramo], salida: list[TramoAdaptado], tope_pct: float, orden, destino, cita: str) -> None:
    total = sum(t.longitud_m for t in lista)
    subt = sum(a.longitud_m for a in salida if a.subterranea)
    for i in sorted((i for i, a in enumerate(salida) if a.subterranea and not lista[i].especial), key=orden):
        if total <= 0 or subt / total <= tope_pct / 100.0:
            break
        salida[i] = destino(lista[i], cita)
        subt -= lista[i].longitud_m


def adaptar_red_mt(tramos: Iterable[Tramo], sector: str, registro: RegistroNormativo, anexo6: Mapping, *,
                   fecha: str | None = None) -> list[TramoAdaptado]:
    """Los tramos de MT de un sistema eléctrico; en el urbano de media y baja densidad, si la red subterránea supera el
    14 % de la longitud total, los cables pasan a desnudo empezando por las secciones más delgadas (art. 28.7)."""
    lista = list(tramos)
    salida = [adaptar_tramo_mt(t, sector, registro, anexo6, fecha=fecha) for t in lista]
    if sector == 'urbano_media_baja':
        c, cita = _criterio(registro, sector, 'mt', fecha)
        desn = c['aerea']['todas']['desnudo_por_ambiente']
        _tope(lista, salida, c['subterranea']['tope_porcentaje_sistema'],
              lambda i: (lista[i].seccion_mm2, lista[i].codigo),
              lambda t, ci: _a(anexo6, t, desn['corrosivo' if t.corrosivo else 'no_corrosivo'], ci, False),
              cita + ' (28.7)')
    return salida


def adaptar_red_bt(tramos: Iterable[Tramo], sector: str, registro: RegistroNormativo, anexo6: Mapping, *,
                   fecha: str | None = None) -> list[TramoAdaptado]:
    """La red de BT de un sistema eléctrico (arts. 26, 31, 36, 41 y 43)."""
    lista = list(tramos)
    c, cita = _criterio(registro, sector, 'bt', fecha)
    salida: list[TramoAdaptado] = []
    for t in lista:
        if t.especial == 'historica' and t.subterranea:
            salida.append(_aBT(anexo6, t, 'NA2XY', _especial(registro, 'historica', fecha), True))
        elif 'aerea_y_subterranea' in c:
            salida.append(_aBT(anexo6, t, c['aerea_y_subterranea'], cita, False))
        elif sector == 'urbano_alta':
            if t.zona == 'Muy Alta':
                salida.append(_aBT(anexo6, t, c['Muy Alta'], cita, t.subterranea))
            elif not t.subterranea:
                salida.append(_aBT(anexo6, t, c['aerea_otras'], cita, False))
            elif t.sed_adaptada.split()[:1] in (['Monoposte'], ['Biposte']):
                salida.append(_aBT(anexo6, t, c['subterranea_otras']['sed_aerea'], cita, False))
            else:
                salida.append(_aBT(anexo6, t, c['subterranea_otras']['sed_no_aerea'], cita, True))
        else:  # urbano_media_baja (art. 31)
            salida.append(_aBT(anexo6, t, c['subterranea']['tipo'] if t.subterranea else c['aerea'], cita,
                             t.subterranea))
    orden = lambda i: (lista[i].fases != 2, lista[i].seccion_mm2, lista[i].codigo)  # bifásicas primero
    if sector == 'urbano_media_baja':
        _tope(lista, salida, c['subterranea']['tope_porcentaje_sistema'], orden,
              lambda t, ci: _aBT(anexo6, t, c['subterranea']['exceso'], ci, False), cita + ' (31.3)')
    if sector == 'urbano_alta':
        reparto = c['subterranea_otras']['reparto_aereo']
        pasadas = [i for i, a in enumerate(salida) if lista[i].subterranea and not a.subterranea]
        por_sed: dict[str, list[int]] = {}
        for i in pasadas:
            por_sed.setdefault(lista[i].sed, []).append(i)
        for indices in por_sed.values():  # art. 26.3: 71 % a A.1.1 y 29 % a A.1.3, por SED
            meta, acum = sum(lista[i].longitud_m for i in indices) * reparto['A.1.3'] / 100.0, 0.0
            for i in sorted(indices, key=orden):
                sub = 'A.1.3' if acum < meta else 'A.1.1'
                if sub == 'A.1.3':
                    acum += lista[i].longitud_m
                a = salida[i]
                salida[i] = TramoAdaptado(a.existente, a.material, a.seccion_mm2, False, a.regla + ' (26.3)', sub)
    return salida


def kva_adaptado(md_kw: float, sector: str, registro: RegistroNormativo, *, fecha: str | None = None) -> float:
    """kVA adaptado = máxima demanda (kW) / (f.p. × f.u.) (arts. 25.1, 30.1, 35.1 y 40.1)."""
    c, _ = _criterio(registro, sector, 'sed', fecha)
    return md_kw / (c['fp'] * c['fu'])


def adaptar_sed(tipo_existente: str, kva: float, fases: int, zona: str, sector: str, registro: RegistroNormativo, *,
                instalada_subterranea: bool = False, especial: str = '', fecha: str | None = None) -> tuple[str, str]:
    """(tipo de SED adaptada, cita) por la tabla de su sector y su zona (arts. 25, 30, 35, 40, 43 y 44)."""
    c, cita = _criterio(registro, sector, 'sed', fecha)
    if especial and instalada_subterranea:
        e = registro.regla('vnr.adaptacion.zonas_historicas' if especial == 'historica'
                           else 'vnr.adaptacion.calles_angostas', fecha)
        if any(_n(s) in _n(tipo_existente) for s in e.regla.valor['sed_subterraneas']):
            return f'{tipo_existente} {fases}ø', f'{e.norma.acto}, {e.regla.articulo_o_anexo}'
    tabla = c['tabla'].get(zona) or c['tabla'].get('otras') or c['tabla'].get('todas')
    for f in tabla:
        if f['fases'] != fases:
            continue
        if 'mayor_que' in f and not kva > f['mayor_que']:
            continue
        if 'hasta' in f and not kva <= f['hasta']:
            continue
        if 'existentes' in f and not any(_n(e) in _n(tipo_existente) for e in f['existentes']):
            continue
        return f['adaptada'], cita
    raise VnrGuiaError(f'SED {tipo_existente} {fases}ø de {kva:.1f} kVA sin fila en la tabla de {sector}/{zona}')


def adaptar_equipo(equipo: str, red_subterranea: bool, sector: str, registro: RegistroNormativo, *,
                   fecha: str | None = None) -> tuple[str, str]:
    """(equipo adaptado, cita) de protección y seccionamiento (arts. 24, 29, 34 y 39)."""
    c, cita = _criterio(registro, sector, 'proteccion', fecha)
    if any(_n(e) == _n(equipo) for e in c.get('se_mantienen', [])):
        return equipo, cita
    for existente, adaptado in (c.get('subterranea' if red_subterranea else 'aerea') or {}).items():
        if _n(existente) == _n(equipo):
            return (adaptado or equipo), cita
    raise VnrGuiaError(f'{equipo}: la Guía no lo reconoce en la red {"subterránea" if red_subterranea else "aérea"} '
                       f'del sector {sector} ({cita})')


def adaptar_luminaria(tecnologia: str, potencia_w: float, sector: str, registro: RegistroNormativo, anexo6: Mapping, *,
                      fecha: str | None = None) -> tuple[str, float, str]:
    """(tecnología adaptada, potencia en W, cita) del alumbrado (arts. 27, 32, 37, 42 y Anexo 6, tablas 10 a 13); en
    los sectores urbano-rural y rural, con su potencia máxima de sodio y de LED."""
    c, cita = _criterio(registro, sector, 'ap', fecha)
    tabla = next(t for t in anexo6['tablas'] if t['tabla'] == c['tabla_anexo6'])
    fila = next((f for f in tabla['filas'] if _n(f['origen']) == _n(tecnologia)), None)
    if fila is None:
        raise VnrGuiaError(f'luminaria {tecnologia}: sin fila en la tabla {c["tabla_anexo6"]} del Anexo 6')
    adaptada = fila['valores'][0]
    tope = c.get('sodio_max_w') if adaptada == 'Sodio' else c.get('led_max_w')
    return adaptada, (min(potencia_w, tope) if tope else potencia_w), cita


# ============================================================== códigos VNR y cálculo (art. 17.2, Anexos 2 y 3) — 108:RF-23

SIN_CODIGO = 'SIN CÓDIGO: '
ANEXO2_DEFECTO = Path(__file__).resolve().parents[4] / 'config' / 'vnr' / 'anexo2_codigos.json'

#: Cómo nombra el Anexo 2 cada material, por nivel y por tipo de red: (subcomponente, raíz de la descripción).
_RAICES = {
    ('MT', False): ('A1 ', {'aa desnudo': 'CONDUCTOR DE AA O SIMIL.', 'cu desnudo': 'CONDUCTOR DE COBRE',
                            'cu protegido': 'CONDUCTOR DE COBRE PROTEGIDO', 'aa protegido': 'CONDUCTOR DE AA PROTEGIDO',
                            'al autoportante': 'AUTOPORTANTE DE AL', 'cu autoportante': 'AUTOPORTANTE DE CU'}),
    ('MT', True): ('B1 ', {'na2xsy': 'CABLE NA2XSY', 'n2xsy': 'CABLE N2XSY', 'nky': 'CABLE NKY',
                           'n2ysey': 'CABLE N2YSEY', 'nysy': 'CABLE NYSY', 'n2ysy': 'CABLE N2YSY'}),
    ('BT', False): ('A1.1', {'al autoportante': 'SP AUTOPORTANTE DE AL', 'cu autoportante': 'SP AUTOPORTANTE DE CU',
                             'al desnudo': 'SP COND. DESNUDO DE AL', 'cu desnudo': 'SP COND. DESNUDO DE CU',
                             'al protegido': 'SP COND. CUBIERTO DE AL', 'cu protegido': 'SP COND. DE CU CUBIERTO'}),
    ('BT', True): ('B1.1', {'na2xy': 'SP CABLE NA2XY', 'nyy - unipolar o tripolar': 'SP CABLE NYY',
                            'nky': 'SP CABLE NKY', 'n2xy': 'SP CABLE N2XY'}),
}
_CALIFICATIVOS = ('PROTEGIDO', 'CUBIERTO', 'DOBLE TERNA', 'SP+AP', 'NEUTRO')
_SED_PREFIJO = {'monoposte': ('A1 ', 'MONOPOSTE'), 'biposte': ('A2 ', 'BIPOSTE'),
                'convencional': ('A3 ', 'S.E. CONVENCIONAL '), 'compacta pedestal': ('A4 ', 'COMPACTA PEDESTAL'),
                'compacta bóveda': ('A5 ', 'COMPACTA BOVEDA')}


def cargar_anexo2(ruta: Path | str | None = None) -> dict:
    return json.loads(Path(ruta or ANEXO2_DEFECTO).read_text(encoding='utf-8'))


def _sec(seccion_mm2: float) -> str:
    return f'{seccion_mm2:g}'.replace('.', ',')


def codigo_de_red(anexo2: Mapping, nivel: str, subterranea: bool, material: str, seccion_mm2: float,
                  conductores: int = 3, subcomponente: str = '') -> str:
    """El código VNR (Anexo 2) de un tramo: subcomponente, raíz de su material y «Nx<sección> mm2» (o «N-1x»)."""
    sub, raices = _RAICES[(nivel, subterranea)]
    raiz = raices.get(_n(material))
    if raiz is None:
        raise VnrGuiaError(f'{material} ({nivel}, {"subterránea" if subterranea else "aérea"}): sin raíz en el Anexo 2')
    sub = subcomponente or sub
    forma = re.compile(rf'(?<![\d,])(?:{conductores}x|{conductores}-1x){re.escape(_sec(seccion_mm2))} mm2')
    cand = [c for c in anexo2['codigos'] if c['subcomponente'].startswith(sub) and raiz in c['descripcion']
            and forma.search(c['descripcion'])
            and not any(q in c['descripcion'] and q not in raiz for q in _CALIFICATIVOS)]
    codigos = sorted({c['codigo'] for c in cand})
    if len(codigos) != 1:
        raise VnrGuiaError(f'{material} {conductores}x{_sec(seccion_mm2)} mm2 en {sub}: '
                           + ('sin código en el Anexo 2' if not codigos else f'varios códigos {codigos}'))
    return codigos[0]


def codigo_de_sed(anexo2: Mapping, tipo_adaptado: str, kva: float) -> tuple[str, float]:
    """(código VNR, kVA de catálogo) de una SED adaptada: un solo transformador, «N kVA (3F)» si es 3ø o «1xN kVA» si es
    1ø (los bancos de monofásicos no se permiten, art. 25.6), con la menor capacidad del Anexo 2 que cubre el kVA
    adaptado (decisión de 4d, 16-11: la Guía da el kVA adaptado; la capacidad sale del catálogo de códigos)."""
    fases = 1 if tipo_adaptado.rstrip().endswith('1ø') else 3
    tipo = _n(tipo_adaptado.replace('3ø', '').replace('1ø', ''))
    sub, raiz = _SED_PREFIJO.get(tipo, (None, None))
    if sub is None:
        raise VnrGuiaError(f'SED «{tipo_adaptado}» sin subcomponente en el Anexo 2')
    forma = re.compile(r'(?<![\dx,])(\d+(?:,\d+)?) kVA \(3F\)$' if fases == 3 else r'\b1x(\d+(?:,\d+)?) kVA$')
    opciones = []
    for c in anexo2['codigos']:
        if c['grupo'].startswith('2') and c['subcomponente'].startswith(sub) and raiz in c['descripcion'] \
                and 'SUBTERRANEA' not in c['descripcion']:
            m = forma.search(c['descripcion'])
            if m:
                opciones.append((float(m.group(1).replace(',', '.')), c['codigo']))
    validas = sorted(o for o in opciones if o[0] >= kva - 1e-9)
    if not validas:
        tope = max((o[0] for o in opciones), default=0)
        raise VnrGuiaError(f'SED {tipo_adaptado} de {kva:.1f} kVA: el Anexo 2 llega a {tope:g} kVA')
    return validas[0][1], validas[0][0]


#: El tipo de un equipo de la MT en VNR-GIS es el prefijo de su código VNR del Anexo 2 (componente C); los que la Guía
#: adapta (arts. 24, 29, 34 y 39) con el nombre con que los nombra su criterio de protección.
EQUIPO_POR_PREFIJO = {'IN': 'Interruptor', 'SC': 'Seccionador bajo carga', 'SE': 'Seccionador Unipolar (x1, x2, x3)',
                      'SF': 'Seccionador fusible (cut-out)', 'RE': 'Reconectador', 'SL': 'Seccionalizador'}
#: La palabra de la descripción del Anexo 2 que distingue al equipo adaptado («Reconectador SF6» → «SF6»).
_DISTINTIVO = {'sf6': 'SF6', 'electronico': 'ELECTRONICO', 'vacio': 'VACIO'}


def codigo_de_equipo(anexo2: Mapping, prefijo: str, kv: float | None, adaptado: str = '') -> tuple[str, str]:
    """(código VNR, nota) de un equipo de protección y seccionamiento de la MT o de su componente C4 (bancos,
    reguladores, pararrayos): el del ``prefijo`` a la tensión ``kv``, con la palabra que distingue al ``adaptado`` si el
    catálogo la tiene. VNR-GIS no da la corriente nominal: se toma la menor del catálogo y la nota lo dice."""
    candidatos = [c for c in anexo2['codigos'] if c['grupo'].startswith('1') and c['componente'].startswith('C ')
                  and c['codigo'].startswith(prefijo)]
    if not candidatos:
        raise VnrGuiaError(f'equipo {prefijo}: sin código en el componente C de la MT del Anexo 2')
    if kv is not None:
        texto_kv = f'{kv:g}'.replace('.', ',') + ' kV'
        a_su_tension = [c for c in candidatos if texto_kv.lower() in c['descripcion'].lower()]
        candidatos = a_su_tension or candidatos
    palabra = next((v for k, v in _DISTINTIVO.items() if k in _n(adaptado)), '')
    con_palabra = [c for c in candidatos if palabra and palabra in _n(c['descripcion']).upper()]
    candidatos = con_palabra or candidatos

    def corriente(c):
        m = re.search(r'In\s*=\s*(\d+)', c['descripcion'])
        return (int(m.group(1)) if m else 0, c['codigo'])
    elegido = min(candidatos, key=corriente)
    return elegido['codigo'], 'corriente nominal no declarada en VNR-GIS: la menor del catálogo a su tensión'


@dataclass(frozen=True)
class ItemMetrado:
    """Una partida del metrado adaptado: código VNR, cantidad (km para las redes, unidades para el resto) y las claves
    del SICODI (tensión de la Tabla 9 y secundario de la Tabla 11 o tensión BT del Anexo 3)."""

    codigo: str
    cantidad: float
    tension: str
    secundario: str
    origen: str = ''      # qué instalación existente lo produjo
    subfamilia: str = ''  # la del subcomponente del Anexo 2: desambigua el SICODI (A1.1 y A1.3 comparten código)


@dataclass(frozen=True)
class LineaVnr:
    item: ItemMetrado
    costo_unitario: float | None
    subtotal: float | None
    motivo: str = ''  # por qué no hay costo: hueco nombrado, nunca cero


@dataclass(frozen=True)
class ResultadoVnr:
    sector_sicodi: str
    lineas: tuple[LineaVnr, ...]
    ine: tuple[tuple[str, float, float], ...]
    huella_costos: str
    formula: str

    @property
    def vnr_ie(self) -> float:
        return sum(x.subtotal for x in self.lineas if x.subtotal is not None)

    @property
    def vnr_ine(self) -> float:
        return sum(c * u for _, c, u in self.ine)

    @property
    def huecos(self) -> tuple[LineaVnr, ...]:
        return tuple(x for x in self.lineas if x.subtotal is None)

    @property
    def completo(self) -> bool:
        return not self.huecos

    @property
    def total(self) -> float | None:
        """VNR = MIE × CEIE + MINE × CINE; sin total mientras quede un hueco."""
        return self.vnr_ie + self.vnr_ine if self.completo else None


def calcular_vnr(items_ie: Iterable[ItemMetrado], tabla_costos, sector_sicodi: str, registro: RegistroNormativo, *,
                 ine: Iterable[tuple[str, float, float]] = (), fecha: str | None = None) -> ResultadoVnr:
    """Art. 17.2: cada partida con el costo estándar de la última fijación (art. 12.1) que la tabla del SICODI da para su
    código, tensión, secundario y sector típico; INE como (descripción, cantidad, costo de la empresa) (art. 16.5)."""
    formula = registro.regla('vnr.formula', fecha)
    sectores = {k[3] for k in getattr(tabla_costos, 'filas', {})}
    if sectores and sector_sicodi not in sectores:
        raise VnrGuiaError(f'sector típico {sector_sicodi} no está en la tabla de costos ({", ".join(sorted(sectores))})')
    lineas = []
    for it in items_ie:
        if it.cantidad < 0:
            raise VnrGuiaError(f'{it.codigo}: cantidad negativa {it.cantidad}')
        if it.codigo.startswith(SIN_CODIGO):
            lineas.append(LineaVnr(it, None, None, it.origen))
            continue
        costo, motivo = tabla_costos.resolver(it.codigo, it.tension, it.secundario, sector_sicodi, it.subfamilia)
        total = None if costo is None else costo.componentes.get('total')
        if total is None:
            lineas.append(LineaVnr(it, None, None, motivo or f'sin costo estándar para {it.codigo}/{it.tension}/'
                                                             f'{it.secundario}/{sector_sicodi}'))
        else:
            lineas.append(LineaVnr(it, total, total * it.cantidad))
    for desc, cant, costo in ine:
        if cant < 0 or costo < 0:
            raise VnrGuiaError(f'INE {desc}: cantidad o costo negativo')
    huella = getattr(getattr(tabla_costos, 'fuente', None), 'huella', '')
    return ResultadoVnr(sector_sicodi, tuple(lineas), tuple(ine), huella,
                        f'{formula.regla.valor} ({formula.norma.acto}, {formula.regla.articulo_o_anexo})')


def items_de_red(adaptados: Iterable[TramoAdaptado], anexo2: Mapping, nivel: str, tension: str, *,
                 postes: str = 'C', conductores: int = 3) -> list[ItemMetrado]:
    """Partidas de una red adaptada: km por código. ``postes`` es el código de estructura de la Tabla 11 del sector
    (C concreto, A madera) y la red subterránea va con X. La subfamilia de cada partida es la del subcomponente del
    Anexo 2 donde está su código: en el SICODI, la BT sobre estructura del SP (A.1.3) se distingue por ella."""
    salida: dict[tuple[str, str], float] = {}
    for a in adaptados:
        sub = a.subcomponente.replace('A.1.', 'A1.') if a.subcomponente else ''
        sec = 'X' if a.subterranea else postes
        subfam = ''
        try:
            n = a.existente.fases if nivel == 'BT' else conductores
            cod, origen = codigo_de_red(anexo2, nivel, a.subterranea, a.material, a.seccion_mm2, n, sub),                 f'{nivel} adaptada'
            sub_real = sub or _RAICES[(nivel, a.subterranea)][0]
            subfam = next(c['subcomponente'] for c in anexo2['codigos']
                          if c['codigo'] == cod and c['subcomponente'].startswith(sub_real)).split(' ', 1)[1]
        except VnrGuiaError as exc:  # el Anexo 2 no tiene ese código: la partida queda como hueco nombrado
            cod, origen = f'{SIN_CODIGO}{a.material} {_sec(a.seccion_mm2)} mm2', str(exc)
        clave = (cod, sec, origen, subfam)
        salida[clave] = salida.get(clave, 0.0) + a.longitud_m / 1000.0
    return [ItemMetrado(c, km, tension, s, o, f) for (c, s, o, f), km in sorted(salida.items())]


# ============================================================== formatos del Anexo 5 (A1, B1, C1 y D1) — 108:RF-24

ANEXO5_DEFECTO = Path(__file__).resolve().parents[4] / 'config' / 'vnr' / 'anexo5_formatos.json'


def cargar_anexo5(ruta: Path | str | None = None) -> dict:
    return json.loads(Path(ruta or ANEXO5_DEFECTO).read_text(encoding='utf-8'))


@dataclass(frozen=True)
class FilaFormato:
    grupo: str
    item: str
    descripcion: str
    unidad: str
    cantidad: float
    costo_unitario: float | None   # subtotal / cantidad (nota 2 del formato)
    subtotal_miles: float | None   # en miles de la moneda de los costos
    huecos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Formato:
    codigo: str          # A1, B1, C1 o D1
    titulo: str
    ambito: str          # empresa, sector típico, sistema eléctrico o unidad de gestión
    moneda: str
    filas: tuple[FilaFormato, ...]
    sin_fila: tuple[str, ...]  # códigos VNR que el formato no tiene dónde poner

    @property
    def total_miles(self) -> float | None:
        if any(f.huecos for f in self.filas):
            return None
        return sum(f.subtotal_miles or 0.0 for f in self.filas)


def _fila_de(codigo: str, anexo2: Mapping, subfamilia: str = '') -> tuple[str, str] | None:
    """(grupo, ítem del formato) del subcomponente del código en el Anexo 2 (el de su subfamilia si el código está en
    varios, como A1.1 y A1.3); la red subterránea de MT es «B»."""
    entradas = [c for c in anexo2['codigos'] if c['codigo'] == codigo]
    if subfamilia:
        entradas = [c for c in entradas if _n(c['subcomponente'].split(' ', 1)[-1]) == _n(subfamilia)] or entradas
    if not entradas:
        return None
    grupo, sub = entradas[0]['grupo'].split()[0], entradas[0]['subcomponente'].split()[0]
    return grupo, ('B' if grupo == '1' and sub == 'B1' else sub)


def formato_resumen(resultado: ResultadoVnr, anexo2: Mapping, anexo5: Mapping, *, codigo: str = 'A1',
                    ambito: str = '', moneda: str = '') -> Formato:
    """El formato ``codigo`` (A1 empresa, B1 sector típico, C1 sistema eléctrico, D1 INE por unidad de gestión) con las
    filas del Formato N° 1 del Anexo 5: cantidad, costo (subtotal / cantidad) y subtotal en miles. Una fila con alguna
    partida sin costo lleva sus huecos y no tiene subtotal."""
    if codigo not in anexo5['formatos']:
        raise VnrGuiaError(f'formato {codigo} no está en el Anexo 5 ({", ".join(anexo5["formatos"])})')
    acum: dict[tuple[str, str], list] = {}
    sin_fila = []
    if codigo != 'D1':
        for linea in resultado.lineas:
            clave = None if linea.item.codigo.startswith(SIN_CODIGO) else _fila_de(linea.item.codigo, anexo2,
                                                                                    linea.item.subfamilia)
            if clave is None:
                sin_fila.append(linea.item.codigo)
                continue
            a = acum.setdefault(clave, [0.0, 0.0, []])
            a[0] += linea.item.cantidad
            if linea.subtotal is None:
                a[2].append(f'{linea.item.codigo}: {linea.motivo}')
            else:
                a[1] += linea.subtotal
    filas = []
    for f in anexo5['filas']:
        if (codigo == 'D1') != (f['grupo'] == '4'):
            continue
        cant, sub, huecos = acum.get((f['grupo'], f['item']), (0.0, 0.0, []))
        filas.append(FilaFormato(f['grupo'], f['item'], f['descripcion'], f['unidad'], cant,
                                 None if huecos or not cant else sub / cant,
                                 None if huecos else sub / 1000.0, tuple(huecos)))
    return Formato(codigo, anexo5['formatos'][codigo], ambito, moneda, tuple(filas), tuple(sin_fila))


def formato_ine(ine_por_rubro: Mapping[str, tuple[float, float]], anexo5: Mapping, *, ambito: str = '',
                moneda: str = '') -> Formato:
    """Formato D1 (INE a nivel de unidad de gestión): ``ine_por_rubro`` = {ítem A-H del grupo 4: (cantidad, costo
    total)} con los costos de la empresa (art. 16.5)."""
    filas = []
    items = {f['item'] for f in anexo5['filas'] if f['grupo'] == '4'}
    ajenos = sorted(set(ine_por_rubro) - items)
    if ajenos:
        raise VnrGuiaError(f'rubros de INE {ajenos} no están en el Formato N° 4 ({", ".join(sorted(items))})')
    for f in anexo5['filas']:
        if f['grupo'] != '4':
            continue
        cant, total = ine_por_rubro.get(f['item'], (0.0, 0.0))
        filas.append(FilaFormato('4', f['item'], f['descripcion'], f['unidad'], cant,
                                 total / cant if cant else None, total / 1000.0))
    return Formato('D1', anexo5['formatos']['D1'], ambito, moneda, tuple(filas), ())


# ============================================================== altas y bajas (art. 18) — 108:RF-25

@dataclass(frozen=True)
class AltasBajas:
    altas: tuple[str, ...]
    bajas: tuple[str, ...]
    modificadas: tuple[str, ...]
    vnr_altas: ResultadoVnr
    vnr_bajas: ResultadoVnr
    vnr_modificadas_antes: ResultadoVnr
    vnr_modificadas_despues: ResultadoVnr

    @property
    def efecto(self) -> float | None:
        """Cambio del VNR del año: altas − bajas + (modificadas después − antes); sin total si queda un hueco."""
        partes = (self.vnr_altas.total, self.vnr_bajas.total, self.vnr_modificadas_antes.total,
                  self.vnr_modificadas_despues.total)
        if any(p is None for p in partes):
            return None
        a, b, m0, m1 = partes
        return a - b + (m1 - m0)


def altas_y_bajas(anterior: Mapping[str, ItemMetrado], actual: Mapping[str, ItemMetrado], tabla_costos,
                  sector_sicodi: str, registro: RegistroNormativo, *, fecha: str | None = None) -> AltasBajas:
    """Altas y bajas del año (art. 18) entre dos inventarios VNR de una empresa, cada uno {id de la instalación:
    partida}. Alta: id solo en el actual; baja: solo en el anterior; modificada: mismo id con otro código, cantidad o
    claves del SICODI. Todas se valoran con la misma tabla de costos para que el efecto sea comparable."""
    altas = tuple(sorted(set(actual) - set(anterior)))
    bajas = tuple(sorted(set(anterior) - set(actual)))
    modificadas = tuple(sorted(k for k in set(anterior) & set(actual) if anterior[k] != actual[k]))

    def vnr(items):
        return calcular_vnr(items, tabla_costos, sector_sicodi, registro, fecha=fecha)
    return AltasBajas(altas, bajas, modificadas, vnr([actual[k] for k in altas]), vnr([anterior[k] for k in bajas]),
                      vnr([anterior[k] for k in modificadas]), vnr([actual[k] for k in modificadas]))


#: Públicos para otros módulos (el estudio desde el inventario VNR-GIS lee los códigos al revés).
RAICES_ANEXO2 = _RAICES

