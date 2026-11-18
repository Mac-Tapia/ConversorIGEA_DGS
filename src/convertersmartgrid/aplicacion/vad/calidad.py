"""Verificación de la calidad de servicio de la empresa modelo con el criterio del num. 6.11 del TdR (108:RF-18).

El 6.11 pide, para la red adaptada: (1) los SAIFI y SAIDI esperables por sistema; (2) con ellos, las curvas de
distribución de frecuencia y duración; y (3) con las curvas, el **% de clientes que no excede N y D por semestre**
de la NTCSE o la NTCSER, que se presenta en el Cuadro 21 por zona y por cliente MT y BT. Las inversiones y los
costos de calidad van en los Cuadros 22 y 23. Tarjeta VAD-CAL (2026-11-15, f4).

El criterio anterior de este módulo comparaba un valor medio por sistema con un límite: eso no es el 6.11 (un
sistema puede tener la media dentro de N' y D' y clientes que los exceden) y no da el Cuadro 21. Ninguna otra spec
lo usaba (grep de ``verificar_calidad`` y ``vad.calidad``): se sustituye; sus pruebas cambian citando la tarjeta.

Todo sale del registro normativo, nunca del código (108:RF-13):

* SAIFI y SAIDI con la definición **vigente**, la RCD 074-2004-OS/CD consolidada con la RCD 177-2012-OS/CD, de los
  mismos registros del Anexo 1: la **mensual** por sistema (Anexo 2, ``vad.calidad.saifi_saidi.mensual``), base y
  traza; y la **anual en MT** (num. 9.4 y Anexo 3, ``vad.calidad.saifi_saidi.anual_mt``), que es la que toma el 6.11.
* N y D por cliente (NTCSE 6.1.2 y 6.1.3) y sus tolerancias N' y D' (6.1.4 y 6.1.5), con el +30 % del Sector Típico 2
  (DS 009-99-EM, art. 4, en el texto del DS 040-2001-EM); NIC y DIC (NTCSER 5.1.2 y 5.1.3).
* Caída de tensión (calidad de producto) contra las tolerancias ya registradas por la tarjeta PIT-TEN
  (``calidad.tension.tolerancia_ntcse`` y ``_ntcser``): la misma cita no se repite en otra regla.

Huecos nombrados, nunca un «cumple»: la RM 163-2011-MEM/DM sin copia oficial (se cita su 9.4) y las «curvas de
distribución», que no regula ninguna norma: el conversor recibe el N y el D de cada cliente que da el método de la
empresa y no inventa ninguno. Un límite sin registrar o que no obliga deja la celda sin verificar.

Punto de extensión (tarjeta CAL-DS, después): ``Interrupcion.inaplicada`` marca una interrupción a la que un decreto
inaplica la transgresión (DS 013-2026-EM, DS 020-2026-EM); hoy cualquier marca se rechaza con su motivo.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from . import VadError

NIVELES = ('MT', 'BT')
NORMAS = ('NTCSE', 'NTCSER')
SERVICIOS = ('urbano', 'urbano_rural', 'rural')
TIPOS = ('expansion', 'mantenimiento', 'otras')
ESTADOS = ('cumple', 'no_cumple', 'sin_verificar', 'sin_clientes')

R_MENSUAL = 'vad.calidad.saifi_saidi.mensual'
R_ANUAL_MT = 'vad.calidad.saifi_saidi.anual_mt'
R_CRITERIO = 'vad.calidad.criterio_6_11'
R_CUADRO_21 = 'vad.calidad.cuadro_21'
R_ND = {'NTCSE': 'vad.calidad.ntcse.indicadores_n_d', 'NTCSER': 'vad.calidad.ntcser.indicadores_nic_dic'}
R_LIM_N = {'NTCSE': 'vad.calidad.limite.interrupciones', 'NTCSER': 'vad.calidad.limite.interrupciones_ser'}
R_LIM_D = {'NTCSE': 'vad.calidad.limite.duracion', 'NTCSER': 'vad.calidad.limite.duracion_ser'}
R_ST2 = 'vad.calidad.limite.incremento_sector_tipico_2'
R_TENSION = {'NTCSE': 'calidad.tension.tolerancia_ntcse', 'NTCSER': 'calidad.tension.tolerancia_ntcser'}


@dataclass(frozen=True)
class Hueco:
    """Lo que la norma no da o no está comprobado: se nombra con su regla, nunca se supone."""

    clave: str
    motivo: str
    regla: str = ''


def _regla(registro: RegistroNormativo, clave: str, fecha: str | None):
    try:
        return registro.regla(clave, fecha)
    except RegistroError as exc:
        raise VadError(f'el registro no trae {clave}: {exc}') from exc


def _huecos_de(rv) -> tuple[Hueco, ...]:
    return tuple(Hueco(p.get('id') or rv.regla.clave, p['descripcion'], rv.regla.clave) for p in rv.regla.pendientes)


def _numero(x: Any) -> bool:
    return not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)


# --------------------------------------------------------------------------- SAIFI y SAIDI (RCD 074-2004 vigente)
@dataclass(frozen=True)
class RegistroAnexo1:
    """Una interrupción tal como se reporta en el Anexo 1 de la RCD 074-2004-OS/CD (campos E, G, L, N, O, P y T)."""

    id: Any
    sistema: str
    mes: int
    E: int
    G: int
    L: float
    N: float
    O: str
    P: str
    T: str = 'N'
    resultado_T: str | None = None


@dataclass(frozen=True)
class SaifiSaidi:
    sistema: str
    periodo: str
    saifi: float
    saidi: float
    regla: str
    registros: tuple[Any, ...] = ()
    fuera_por_filtro: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    huecos: tuple[Hueco, ...] = ()


def _comprobar_registros(registros: Sequence[RegistroAnexo1]) -> None:
    if not registros:
        raise VadError('no hay ningún registro del Anexo 1 para calcular SAIFI y SAIDI')
    for r in registros:
        if not (isinstance(r.mes, int) and 1 <= r.mes <= 12):
            raise VadError(f'el registro {r.id} tiene el mes {r.mes!r}; va de 1 a 12')
        if not (_numero(r.L) and r.L >= 0 and _numero(r.N) and r.N >= 0):
            raise VadError(f'el registro {r.id} trae L o N que no son números no negativos')


def _usuarios(usuarios: Mapping[tuple[str, int], float], sistema: str, mes: int) -> float:
    t = usuarios.get((sistema, mes))
    if not _numero(t) or t <= 0:
        raise VadError(f'falta T_USUARIOS (campo C del Anexo 2) del sistema {sistema} en el mes {mes}')
    return float(t)


def saifi_saidi_mensual(registro: RegistroNormativo, registros: Sequence[RegistroAnexo1],
                        usuarios: Mapping[tuple[str, int], float],
                        fecha: str | None = None) -> dict[tuple[str, int], SaifiSaidi]:
    """Por sistema y mes: SAIFI = ΣL / T_USUARIOS y SAIDI = ΣN / T_USUARIOS, con todos los registros (Anexo 2)."""
    rv = _regla(registro, R_MENSUAL, fecha)
    _comprobar_registros(registros)
    grupos: dict[tuple[str, int], list[RegistroAnexo1]] = defaultdict(list)
    for r in registros:
        grupos[(r.sistema, r.mes)].append(r)
    out = {}
    for (sistema, mes), rs in sorted(grupos.items()):
        t = _usuarios(usuarios, sistema, mes)
        out[(sistema, mes)] = SaifiSaidi(sistema, f'mes {mes}', sum(r.L for r in rs) / t, sum(r.N for r in rs) / t,
                                         rv.regla.clave, tuple(r.id for r in rs), huecos=_huecos_de(rv))
    return out


def _fallos_mt(r: RegistroAnexo1, filtros: Mapping[str, Any]) -> list[str]:
    fallos = [c for c in ('E', 'G', 'O', 'P') if getattr(r, c) not in filtros[c]]
    t = filtros['T']
    if not (r.T == t['sin_solicitud']
            or (r.T == t['con_solicitud'] and r.resultado_T in t['resultados_que_entran'])):
        fallos.append('T')
    return fallos


def filtrar_mt(registro: RegistroNormativo, registros: Sequence[RegistroAnexo1],
               fecha: str | None = None) -> tuple[list[RegistroAnexo1], dict[str, list[Any]]]:
    """Los registros que entran en el SAIFI MT y el SAIDI MT (Anexo 3) y, por filtro, los que deja fuera (un registro
    que falla dos filtros sale en los dos)."""
    filtros = _regla(registro, R_ANUAL_MT, fecha).regla.valor['filtros']
    dentro, fuera = [], {c: [] for c in filtros}
    for r in registros:
        fallos = _fallos_mt(r, filtros)
        for c in fallos:
            fuera[c].append(r.id)
        if not fallos:
            dentro.append(r)
    return dentro, fuera


def saifi_saidi_anual_mt(registro: RegistroNormativo, registros: Sequence[RegistroAnexo1],
                         usuarios: Mapping[tuple[str, int], float],
                         fecha: str | None = None) -> dict[str, SaifiSaidi]:
    """Por sistema: la suma de los 12 meses de ΣL_MT / T_USUARIOS y de ΣN_MT / T_USUARIOS con los registros que pasan
    los filtros del Anexo 3. Es la que toma el 6.11; lleva el hueco de la RM 163-2011-MEM/DM."""
    rv = _regla(registro, R_ANUAL_MT, fecha)
    _comprobar_registros(registros)
    dentro, fuera = filtrar_mt(registro, registros, fecha)
    out = {}
    for sistema in sorted({r.sistema for r in registros}):
        propios = [r for r in dentro if r.sistema == sistema]
        saifi = saidi = 0.0
        for mes in range(1, rv.regla.valor['meses'] + 1):
            rs = [r for r in propios if r.mes == mes]
            if rs:
                t = _usuarios(usuarios, sistema, mes)
                saifi += sum(r.L for r in rs) / t
                saidi += sum(r.N for r in rs) / t
        ids = {r.id for r in registros if r.sistema == sistema}
        out[sistema] = SaifiSaidi(sistema, 'anual MT', saifi, saidi, rv.regla.clave, tuple(r.id for r in propios),
                                  {c: tuple(i for i in v if i in ids) for c, v in fuera.items()}, _huecos_de(rv))
    return out


# --------------------------------------------------------------------------- N y D por cliente (NTCSE y NTCSER)
@dataclass(frozen=True)
class Interrupcion:
    """Una interrupción del semestre de la red adaptada, con los clientes que afecta."""

    clientes: tuple[str, ...]
    duracion_h: float
    tipo: str = 'otras'
    duracion_programada_h: float | None = None
    fuerza_mayor: bool = False
    rechazo_carga: bool = False
    #: Punto de extensión de la tarjeta CAL-DS (decreto que inaplica la transgresión); hoy se rechaza.
    inaplicada: str = ''


def _comprobar_interrupcion(i: Interrupcion) -> None:
    if i.tipo not in TIPOS:
        raise VadError(f'tipo de interrupción {i.tipo!r}; los válidos son {TIPOS}')
    if not _numero(i.duracion_h) or i.duracion_h < 0:
        raise VadError(f'duración de interrupción no válida: {i.duracion_h!r}')
    if i.duracion_programada_h is not None and (not _numero(i.duracion_programada_h) or i.duracion_programada_h < 0):
        raise VadError(f'duración programada no válida: {i.duracion_programada_h!r}')
    if i.inaplicada:
        raise VadError(f'la inaplicación por decreto ({i.inaplicada}) es de la tarjeta CAL-DS y aún no se aplica')


def n_d_por_cliente(registro: RegistroNormativo, interrupciones: Iterable[Interrupcion], clientes: Iterable[str],
                    norma: str = 'NTCSE', fecha: str | None = None) -> dict[str, tuple[float, float]]:
    """(N, D) de cada cliente en el semestre: N cuenta sus interrupciones (las programadas por expansión con el factor
    registrado) y D = Σ Ki·di, con Ki por tipo y la diferencia con lo programado a 0 o a 1 (NTCSE 6.1.3; en la
    NTCSER son los sumandos de NIC y DIC). No entran las de menos del mínimo, las de fuerza mayor ni, en la NTCSE,
    los rechazos de carga."""
    if norma not in NORMAS:
        raise VadError(f'norma de calidad {norma!r}; las válidas son {NORMAS}')
    p = _regla(registro, R_ND[norma], fecha).regla.valor
    out = {c: [0.0, 0.0] for c in clientes}
    for i in interrupciones:
        _comprobar_interrupcion(i)
        if (i.duracion_h * 60 < p['duracion_minima_min'] or (i.fuerza_mayor and 'fuerza_mayor' in p['excluye'])
                or (i.rechazo_carga and 'rechazo_carga' in p['excluye'])):
            continue
        k = p['k'][i.tipo]
        if i.tipo != 'otras' and i.duracion_programada_h is not None:
            prog = i.duracion_programada_h
            dif = p['k_diferencia_programada']['real_mayor' if i.duracion_h > prog else 'real_menor']
            d = k * min(i.duracion_h, prog) + dif * abs(i.duracion_h - prog)
        else:
            d = k * i.duracion_h
        n = p['factor_n_programadas_expansion'] if i.tipo == 'expansion' else 1.0
        for c in i.clientes:
            if c not in out:
                raise VadError(f'la interrupción afecta al cliente {c}, que no está entre los clientes')
            out[c][0] += n
            out[c][1] += d
    return {c: (v[0], v[1]) for c, v in out.items()}


# --------------------------------------------------------------------------- límites N' y D'
@dataclass(frozen=True)
class Cliente:
    id: str
    fila: str
    nivel: str
    norma: str = 'NTCSE'
    sector_tipico: str = ''
    #: NTCSE 6.1.5: servicio calificado como urbano, urbano-rural o rural.
    servicio: str = 'urbano'
    #: NTCSER: el SER del cliente (NIC y DIC son promedios del SER y el nivel).
    sistema: str = ''


@dataclass(frozen=True)
class Limite:
    n: float | None
    d: float | None
    reglas: tuple[str, ...]
    hueco: Hueco | None = None


def _entero_superior(x: float) -> float:
    return float(math.ceil(round(x, 9)))


def limite_de(registro: RegistroNormativo, cliente: Cliente, fecha: str | None = None) -> Limite:
    """N' y D' del cliente según su norma, nivel, servicio y sector típico, solo de reglas que obligan."""
    if cliente.nivel not in NIVELES or cliente.norma not in NORMAS or cliente.servicio not in SERVICIOS:
        raise VadError(f'cliente {cliente.id}: nivel, norma o servicio no válidos '
                       f'({cliente.nivel!r}, {cliente.norma!r}, {cliente.servicio!r})')
    rn, rd = _regla(registro, R_LIM_N[cliente.norma], fecha), _regla(registro, R_LIM_D[cliente.norma], fecha)
    usadas = [rn.regla.clave, rd.regla.clave]
    for rv in (rn, rd):
        if not rv.obligatoria:
            return Limite(None, None, tuple(usadas), Hueco('limite_no_obliga', f'{rv.regla.clave} es de '
                                                           f'{rv.norma.acto}, «{rv.estado}», y no obliga',
                                                           rv.regla.clave))
    if cliente.norma == 'NTCSER':
        ambito = rn.regla.valor['ambito'].get(cliente.sector_tipico.lower())
        if ambito is None:
            return Limite(None, None, tuple(usadas), Hueco('ambito_ntcser', f'el sector típico '
                                                           f'{cliente.sector_tipico!r} no es rural concentrado ni '
                                                           'disperso (NTCSER 5.1.3)', rn.regla.clave))
        return Limite(float(rn.regla.valor[ambito][cliente.nivel]), float(rd.regla.valor[ambito][cliente.nivel]),
                      tuple(usadas))
    n, d = float(rn.regla.valor[cliente.nivel]), float(rd.regla.valor[cliente.nivel])
    if cliente.nivel == 'BT' and cliente.servicio != 'urbano':
        n *= 1 + rn.regla.valor['incremento_bt'][cliente.servicio]
        d *= 1 + rd.regla.valor['incremento_bt'][cliente.servicio]
    rst2 = _regla(registro, R_ST2, fecha)
    if cliente.sector_tipico == rst2.regla.valor['sector_tipico']:
        usadas.append(rst2.regla.clave)
        if not rst2.obligatoria:
            return Limite(None, None, tuple(usadas), Hueco('limite_no_obliga', f'{R_ST2} no obliga', R_ST2))
        if cliente.servicio != 'urbano' and cliente.nivel == 'BT':
            return Limite(None, None, tuple(usadas), Hueco(
                'st2_y_6_1_5', 'la norma no dice cómo se combina el +30 % del Sector Típico 2 con el incremento del '
                'num. 6.1.5 (BT urbano-rural o rural)', R_ST2))
        f = rst2.regla.valor['factor']
        n, d = n + _entero_superior(n * f), d + _entero_superior(d * f)
    return Limite(n, d, tuple(usadas))


# --------------------------------------------------------------------------- Cuadro 21
@dataclass(frozen=True)
class CeldaCuadro21:
    fila: str
    nivel: str
    clientes: int
    frecuencia: float | None
    duracion: float | None
    pct_excedido: float | None
    estado: str
    excede_n: tuple[str, ...] = ()
    excede_d: tuple[str, ...] = ()
    motivo: str = ''


@dataclass(frozen=True)
class Cuadro21:
    titulo: str
    filas: tuple[str, ...]
    celdas: tuple[CeldaCuadro21, ...]
    regla: str
    huecos: tuple[Hueco, ...] = ()

    def celda(self, fila: str, nivel: str) -> CeldaCuadro21:
        return next(c for c in self.celdas if c.fila == fila and c.nivel == nivel)

    @property
    def estado(self) -> str:
        estados = {c.estado for c in self.celdas}
        if 'no_cumple' in estados:
            return 'no_cumple'
        return 'sin_verificar' if 'sin_verificar' in estados else 'cumple'


def _celda(fila: str, nivel: str, propios: list[Cliente], nd: Mapping[str, tuple[float, float]],
           lim: Mapping[str, Limite]) -> CeldaCuadro21:
    if not propios:
        return CeldaCuadro21(fila, nivel, 0, None, None, None, 'sin_clientes')
    k = len(propios)
    frec, dur = sum(nd[c.id][0] for c in propios) / k, sum(nd[c.id][1] for c in propios) / k
    huecos = sorted({lim[c.id].hueco.motivo for c in propios if lim[c.id].hueco})
    if huecos:
        return CeldaCuadro21(fila, nivel, k, frec, dur, None, 'sin_verificar', motivo='; '.join(huecos))
    en = tuple(c.id for c in propios if nd[c.id][0] > lim[c.id].n)
    ed = tuple(c.id for c in propios if nd[c.id][1] > lim[c.id].d)
    pct = 100.0 * len(set(en) | set(ed)) / k
    return CeldaCuadro21(fila, nivel, k, frec, dur, pct, 'no_cumple' if pct > 0 else 'cumple', en, ed)


def cuadro_21(registro: RegistroNormativo, clientes: Sequence[Cliente], interrupciones: Sequence[Interrupcion],
              fecha: str | None = None) -> Cuadro21:
    """El Cuadro 21 de un semestre: por fila y por cliente MT y BT, la media del N y del D y el % de clientes que
    exceden N' o D'. En la NTCSER cada cliente lleva el NIC y el DIC de su SER y nivel (5.1.2: son promedios)."""
    rv = _regla(registro, R_CUADRO_21, fecha)
    v = rv.regla.valor
    if not clientes:
        raise VadError('no hay ningún cliente para el Cuadro 21')
    ids = [c.id for c in clientes]
    if len(set(ids)) != len(ids):
        raise VadError('clientes repetidos en el Cuadro 21')
    for c in clientes:
        if c.fila not in v['filas']:
            raise VadError(f'el cliente {c.id} está en la fila {c.fila!r}, que el Cuadro 21 no tiene')
    desconocidos = sorted({x for i in interrupciones for x in i.clientes} - set(ids))
    if desconocidos:
        raise VadError(f'interrupciones de clientes que no están: {desconocidos}')
    nd: dict[str, tuple[float, float]] = {}
    for norma in NORMAS:
        propios = [c.id for c in clientes if c.norma == norma]
        if propios:
            ints = [Interrupcion(tuple(x for x in i.clientes if x in propios), i.duracion_h, i.tipo,
                                 i.duracion_programada_h, i.fuerza_mayor, i.rechazo_carga, i.inaplicada)
                    for i in interrupciones]
            nd.update(n_d_por_cliente(registro, ints, propios, norma, fecha))
    ser: dict[tuple[str, str], list[str]] = defaultdict(list)
    for c in clientes:
        if c.norma == 'NTCSER':
            if not c.sistema:
                raise VadError(f'el cliente {c.id} es de la NTCSER y no dice su SER')
            ser[(c.sistema, c.nivel)].append(c.id)
    for grupo in ser.values():
        media = (sum(nd[x][0] for x in grupo) / len(grupo), sum(nd[x][1] for x in grupo) / len(grupo))
        nd.update(dict.fromkeys(grupo, media))
    lim = {c.id: limite_de(registro, c, fecha) for c in clientes}
    celdas = [_celda(f, nivel, [c for c in clientes if c.fila == f and c.nivel == nivel], nd, lim)
              for f in v['filas'] for nivel in v['niveles']]
    celdas += [_celda(v['total'], nivel, [c for c in clientes if c.nivel == nivel], nd, lim) for nivel in v['niveles']]
    huecos = _huecos_de(_regla(registro, R_CRITERIO, fecha))
    return Cuadro21(v['titulo'], tuple(v['filas']) + (v['total'],), tuple(celdas), rv.regla.clave, huecos)


# --------------------------------------------------------------------------- Cuadros 22 y 23
@dataclass(frozen=True)
class FilaCosto:
    concepto: str
    usd: float | None
    especificacion: str = ''


@dataclass(frozen=True)
class CuadroCostos:
    numero: int
    titulo: str
    columnas: tuple[str, ...]
    filas: tuple[FilaCosto, ...]
    total: float
    sin_dimensionar: tuple[str, ...]
    regla: str


def cuadro_costos(registro: RegistroNormativo, numero: int, partidas: Mapping[str, float],
                  otros: Mapping[str, float] | None = None, fecha: str | None = None) -> CuadroCostos:
    """El Cuadro 22 (inversión) o el 23 (OyM anual) con las filas del registro, en US$. Una fila sin dimensionar se
    nombra y queda fuera del total; «Otros (especificar)» exige su especificación."""
    if numero not in (22, 23):
        raise VadError(f'el 6.11 solo tiene los Cuadros 22 y 23 de costos, no el {numero}')
    rv = _regla(registro, f'vad.calidad.cuadro_{numero}', fecha)
    v = rv.regla.valor
    extra = sorted(set(partidas) - set(v['filas']))
    if extra:
        raise VadError(f'el Cuadro {numero} no tiene las filas {extra}')
    otros = dict(otros or {})
    for nombre, x in [*partidas.items(), *otros.items()]:
        if not _numero(x) or x < 0:
            raise VadError(f'Cuadro {numero}, {nombre}: {x!r} no es un importe en US$ no negativo')
    if any(not str(k).strip() for k in otros):
        raise VadError(f'Cuadro {numero}: «{v["otros"]}» sin especificar')
    filas = [FilaCosto(f, float(partidas[f]) if f in partidas else None) for f in v['filas']]
    filas += [FilaCosto(v['otros'], float(x), k) for k, x in otros.items()]
    return CuadroCostos(numero, v['titulo'], tuple(v['columnas']), tuple(filas),
                        sum(f.usd for f in filas if f.usd is not None),
                        tuple(f.concepto for f in filas if f.usd is None), rv.regla.clave)


# --------------------------------------------------------------------------- verificación (RF-18)
@dataclass(frozen=True)
class CaidaTension:
    sistema: str
    nivel: str
    caida_pct: float
    norma: str = 'NTCSE'
    servicio: str = 'urbano'


@dataclass(frozen=True)
class Verificacion:
    sistema: str
    indicador: str
    estado: str
    valor: float | None = None
    limite: float | None = None
    regla_limite: str = ''
    motivo: str = ''


@dataclass(frozen=True)
class ResultadoCalidad:
    verificaciones: tuple[Verificacion, ...]
    cuadro_21: Cuadro21 | None = None
    huecos: tuple[Hueco, ...] = ()

    @property
    def no_cumplen(self) -> list[Verificacion]:
        return [v for v in self.verificaciones if v.estado == 'no_cumple']

    @property
    def sin_verificar(self) -> list[Verificacion]:
        return [v for v in self.verificaciones if v.estado == 'sin_verificar']

    @property
    def estado(self) -> str:
        """``no_cumple`` si alguno no cumple; ``sin_verificar`` si alguno no se pudo verificar; si no, ``cumple``."""
        if self.no_cumplen:
            return 'no_cumple'
        return 'sin_verificar' if self.sin_verificar else 'cumple'


def verificar_tension(registro: RegistroNormativo, t: CaidaTension, fecha: str | None = None) -> Verificacion:
    """La caída de tensión de un sistema contra la tolerancia de su norma (NTCSE 5.1.2 o NTCSER 4.1.2)."""
    if t.nivel not in NIVELES or t.norma not in NORMAS or t.servicio not in SERVICIOS:
        raise VadError(f'caída de tensión de {t.sistema}: nivel, norma o servicio no válidos')
    if not _numero(t.caida_pct):
        raise VadError(f'la caída de tensión de {t.sistema} no es un número: {t.caida_pct!r}')
    indicador = f'caida_tension_{t.nivel.lower()}'
    rv = _regla(registro, R_TENSION[t.norma], fecha)
    if t.norma == 'NTCSER':
        tol = rv.regla.valor[t.nivel]
    else:
        secundaria = t.nivel == 'BT' and t.servicio != 'urbano'
        tol = rv.regla.valor['redes_secundarias_urbano_rurales_o_rurales' if secundaria else 'general']
    limite = 100.0 * tol
    if not rv.obligatoria:
        return Verificacion(t.sistema, indicador, 'sin_verificar', t.caida_pct, limite, rv.regla.clave,
                            f'{rv.regla.clave} no obliga')
    if t.caida_pct > limite:
        return Verificacion(t.sistema, indicador, 'no_cumple', t.caida_pct, limite, rv.regla.clave,
                            f'caída de tensión en {t.nivel} = {t.caida_pct} % supera la tolerancia {limite:g} % '
                            f'({rv.norma.acto})')
    return Verificacion(t.sistema, indicador, 'cumple', t.caida_pct, limite, rv.regla.clave)


def verificar_calidad(registro: RegistroNormativo, clientes: Sequence[Cliente],
                      interrupciones: Sequence[Interrupcion], caidas_tension: Sequence[CaidaTension] = (),
                      fecha: str | None = None) -> ResultadoCalidad:
    """La verificación del 6.11: por cada celda del Cuadro 21, el % de clientes que exceden N' (``interrupciones``) y
    D' (``duracion``), y la caída de tensión de cada sistema. Nombra lo que no cumple y no da nunca por cumplido un
    hueco; el Cuadro 21 y los huecos del criterio van en el resultado."""
    c21 = cuadro_21(registro, clientes, interrupciones, fecha)
    out: list[Verificacion] = []
    for c in c21.celdas:
        if c.estado == 'sin_clientes':
            continue
        donde = f'{c.fila} / cliente {c.nivel}'
        for indicador, exceden, regla in (('interrupciones', c.excede_n, 'N'), ('duracion', c.excede_d, 'D')):
            if c.estado == 'sin_verificar':
                out.append(Verificacion(donde, indicador, 'sin_verificar', motivo=c.motivo))
                continue
            pct = 100.0 * len(exceden) / c.clientes
            if exceden:
                out.append(Verificacion(donde, indicador, 'no_cumple', pct, 0.0, motivo=(
                    f'{pct:g} % de los clientes de {donde} exceden {regla}\' en el semestre: {", ".join(exceden)}')))
            else:
                out.append(Verificacion(donde, indicador, 'cumple', 0.0, 0.0))
    out += [verificar_tension(registro, t, fecha) for t in caidas_tension]
    return ResultadoCalidad(tuple(out), c21, c21.huecos)
