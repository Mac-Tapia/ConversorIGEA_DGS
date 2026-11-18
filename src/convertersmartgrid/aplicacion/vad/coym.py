"""COyM de la empresa modelo según el Anexo 7 del TdR del VAD (spec 108, RF-8, RF-9, RF-13).

El Anexo 7 («Metodología de Costos de Operación y Mantenimiento», ``vad.anexo7.*`` en ``config/vad/anexo7_coym.json``)
no trae cifras: da el método y deja los costos unitarios, las frecuencias y las tasas de falla al estudio, con su
sustento (``vad.anexo7.parametros_de_calculo``). Aquí se calcula lo que el método fija, cada resultado con la regla y
la huella que lo respaldan; ningún valor del TdR ni de una empresa está escrito en el código:

- :func:`coym_tecnico`: «las cantidades globales de redes e instalaciones adaptadas agrupadas por las etapas del
  sistema de distribución, por los costos unitarios estándar de mantenimiento». Los componentes y sus unidades son las
  filas del cuadro «Detalle de Costo Unitario Estándar» del registro. Un componente sin costo unitario es un hueco
  nombrado y no suma; un costo unitario sin fuente, o de un componente o una unidad que el cuadro no trae, deja el
  resultado ``no_conforme``. Dos monedas no se suman. :func:`cantidades_de_dimensionamiento` saca las cantidades de la
  red dimensionada de la T6 (km por nivel, SED y kVA), con el componente de red que declara el perfil.
- :func:`depurar_partidas`: la lista CERRADA de costos excluidos (``vad.anexo7.costos_excluidos``) y la regla de que,
  sin contrato u orden de servicio, no se toma el monto informado (``vad.anexo7.costos_eficientes``): la actividad no
  se desconoce, pero su monto no entra.
- :func:`tope_salarial`: el costo anual por empleado de la encuesta no excede el real de la empresa de referencia
  (``vad.anexo7.remuneraciones``); si lo excede, se toma el real y se avisa.
- :func:`capital_de_trabajo`: el CCT de ``vad.anexo7.capital_de_trabajo``, con la tasa diaria EFECTIVA (decisión P-4 de
  28) y la proporcional como contraste; y el aviso de la errata del num. 5.12, que remite al numeral 12 cuando el CCT
  es el 11 (``vad.capital_de_trabajo.remision``).
- :func:`costos_compartidos`: el 75/25 de los órganos de gobierno con el tope del 7,5 % del TdR, que MANDA para el
  VAD 2026-2030 (decisión de 28), con el aviso de que el Manual vigente (RCD 218-2020-OS/CD, modificada por la
  249-2022-OS/CD) aplica el 75/25 con otro ámbito y otra base del tope, el hueco A7-4 (el texto de la RM 197-94-EM/VME
  no se ha hallado) y la base del tope de la empresa modelo (P-5: el aVNR del periodo, sustituible por el perfil).
"""
from __future__ import annotations

import calendar
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...dominio.registro_normativo import RegistroError, RegistroNormativo, ReglaVigente, regla_remitida
from . import VadError

REGLA_CALCULO = 'vad.anexo7.parametros_de_calculo'
REGLA_EXCLUIDOS = 'vad.anexo7.costos_excluidos'
REGLA_EFICIENTES = 'vad.anexo7.costos_eficientes'
REGLA_REMUNERACIONES = 'vad.anexo7.remuneraciones'
REGLA_CCT = 'vad.anexo7.capital_de_trabajo'
REGLA_REMISION_CCT = 'vad.capital_de_trabajo.remision'
REGLA_TASA = 'vad.tasa_actualizacion'
REGLA_COMPARTIDOS = 'vad.anexo7.costos_compartidos'
_GRUPO_PERIODO = re.compile(r'^vad\.grupo\.\d+\.periodo$')
#: El Manual vigente con que se contrasta el «numeral 5.1» que transcribe el TdR (b3 de 6c).
REGLAS_MANUAL = ('manual_costos.costos_indirectos.imputacion', 'manual_costos.costos_indirectos.organos_de_gobierno')
#: La regla del hueco A7-4 que trae REG-HUECOS (``config/vad/tdr_vad_2026_anexo7_manual.json``), si está registrada.
REGLA_A7_4 = 'vad.anexo7.manual_costos'
#: Quién recibe el exceso sobre el tope del 7,5 %: el TdR no lo dice, y solo lo asignaría una regla citada DE SU ÁMBITO
#: (los órganos de gobierno del Anexo 7). Hoy no hay ninguna: el exceso es un hueco y no se asigna (c3, VAD-A7 v3).
REGLA_EXCESO = 'vad.anexo7.costos_compartidos.exceso'
#: La Nota 2 del Formato 3.2 del Manual vigente («75% o la diferencia») existe, pero es de OTRO ámbito (suministros,
#: servicios de terceros, tributos y cargas de gestión): no se extiende a los órganos de gobierno; solo se avisa (c3).
REGLA_NOTA2_MANUAL = 'manual_costos.formato_3_2.nota_2'
DESTINOS_EXCESO = ('servicio',)
CONVERSIONES = ('efectiva', 'proporcional')
ETAPAS = ('MT', 'SED', 'BT', 'AP')


def _cita(v: ReglaVigente) -> str:
    return (f'{v.norma.acto}, {v.regla.articulo_o_anexo}, pág. {v.regla.pagina}, líneas {v.regla.lineas}: '
            f'«{v.regla.cita_literal}»')


def _regla(registro: RegistroNormativo, clave: str, fecha: str | None, motivos: list[str],
           reglas: dict[str, str]) -> ReglaVigente | None:
    """La regla, su huella en ``reglas`` y, si no obliga o no está, su motivo de ``no_conforme``."""
    try:
        v = registro.regla(clave, fecha)
    except RegistroError as exc:
        motivos.append(f'falta la regla {clave} del registro: {exc}')
        return None
    reglas[clave] = v.huella()
    if not v.obligatoria:
        motivos.append(f'la regla {clave} no obliga (estado «{v.estado}» o sin cita): el resultado no es conforme')
    return v


def _unidad(texto: str) -> str:
    """«S/ /km» y «S/./km» (sic, las dos en el cuadro) → «km»: la unidad física tras la última barra."""
    return texto.rsplit('/', 1)[-1].strip()


# ----------------------------------------------------------------------------------------------- COyM técnico
@dataclass(frozen=True)
class Cantidad:
    """Cantidad adaptada de un componente del cuadro, en su unidad física (km, subestación, equipo, trafo, kVA…)."""
    componente: str
    valor: float
    unidad: str
    etapa: str
    origen: str = ''


@dataclass(frozen=True)
class CostoUnitario:
    """Costo unitario estándar de mantenimiento de un componente: lo aporta el estudio con su sustento."""
    componente: str
    valor: float
    unidad: str
    moneda: str
    fuente: str


@dataclass
class ResultadoCoym:
    por_sistema: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    """sistema → etapa → moneda → monto."""
    totales: dict[str, float] = field(default_factory=dict)
    detalle: list[dict[str, Any]] = field(default_factory=list)
    huecos: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)
    reglas: dict[str, str] = field(default_factory=dict)

    @property
    def conforme(self) -> bool:
        return not self.motivos


def para_el_vad(v: ReglaVigente) -> str:
    """«para el VAD <periodos> (<acto>, vigente desde <fecha>)»: los periodos son los de los grupos que registra el
    mismo acto que la regla (``vad.grupo.N.periodo``) y la vigencia, la del acto en el registro, que sale de su texto
    (RN-VIG). Ningún periodo se escribe en el código (108:RF-13); si el acto no registra grupos, se dice así."""
    periodos = sorted({str(r.valor) for r in v.norma.reglas if _GRUPO_PERIODO.match(r.clave)})
    vigencia = f', vigente desde {v.norma.vigencia_desde}' if v.norma.vigencia_desde else ''
    if not periodos:
        return f'para el VAD de este TdR ({v.norma.acto}{vigencia}; el acto no registra los periodos de sus grupos)'
    return f'para el VAD {" y ".join(periodos)} ({v.norma.acto}{vigencia})'


def componentes_del_cuadro(registro: RegistroNormativo, fecha: str | None = None) -> dict[str, tuple[str, ...]]:
    """Componente del cuadro «Detalle de Costo Unitario Estándar» → sus unidades físicas («S/ /trafo y S/./kVA» da dos)."""
    try:
        valor = registro.regla(REGLA_CALCULO, fecha).regla.valor
    except RegistroError as exc:
        raise VadError(f'el COyM técnico necesita el cuadro del Anexo 7 ({REGLA_CALCULO}): {exc}') from exc
    return {f['componente']: tuple(_unidad(u) for u in f['unidad'].split(' y '))
            for f in valor['cuadro_costo_unitario_estandar']}


def coym_tecnico(cantidades: Mapping[str, Sequence[Cantidad]], unitarios: Mapping[str, CostoUnitario],
                 registro: RegistroNormativo, fecha: str | None = None) -> ResultadoCoym:
    """COyM técnico de mantenimiento por sistema y etapa: Σ cantidad adaptada × costo unitario estándar."""
    res = ResultadoCoym()
    _regla(registro, REGLA_CALCULO, fecha, res.motivos, res.reglas)
    cuadro = componentes_del_cuadro(registro, fecha)
    for comp, cu in sorted(unitarios.items()):
        if comp not in cuadro:
            res.motivos.append(f'el costo unitario de «{comp}» no es de un componente del cuadro del Anexo 7')
            continue
        if _unidad(cu.unidad) not in cuadro[comp]:
            res.motivos.append(f'el costo unitario de «{comp}» va en {cu.unidad!r}; el cuadro pide '
                               f'{" o ".join(cuadro[comp])}')
        if not str(cu.fuente or '').strip():
            res.motivos.append(f'el costo unitario de «{comp}» no declara su fuente (el Anexo 7 pide sustentarlo)')
        if not str(cu.moneda or '').strip():
            res.motivos.append(f'el costo unitario de «{comp}» no declara su moneda')
    sin_costo: set[str] = set()
    for sistema in sorted(cantidades):
        etapas: dict[str, dict[str, float]] = {}
        for c in cantidades[sistema]:
            if c.componente not in cuadro:
                res.motivos.append(f'{sistema}: «{c.componente}» no es un componente del cuadro del Anexo 7')
                continue
            if c.etapa not in ETAPAS:
                res.motivos.append(f'{sistema}: «{c.componente}» va en la etapa {c.etapa!r}; las etapas son {ETAPAS}')
                continue
            cu = unitarios.get(c.componente)
            if cu is None:
                sin_costo.add(c.componente)
                continue
            if _unidad(cu.unidad) != _unidad(c.unidad):
                res.motivos.append(f'{sistema}: la cantidad de «{c.componente}» va en {c.unidad} y su costo unitario '
                                   f'en {cu.unidad}: no se multiplican')
                continue
            monto = float(c.valor) * float(cu.valor)
            por_moneda = etapas.setdefault(c.etapa, {})
            por_moneda[cu.moneda] = por_moneda.get(cu.moneda, 0.0) + monto
            res.totales[cu.moneda] = res.totales.get(cu.moneda, 0.0) + monto
            res.detalle.append({'sistema': sistema, 'etapa': c.etapa, 'componente': c.componente,
                                'cantidad': c.valor, 'unidad': c.unidad, 'costo_unitario': cu.valor,
                                'moneda': cu.moneda, 'monto': monto, 'fuente': cu.fuente, 'origen': c.origen,
                                'regla': REGLA_CALCULO})
        res.por_sistema[sistema] = etapas
    for comp in sorted(sin_costo):
        res.huecos.append(f'«{comp}» sin costo unitario estándar: el Anexo 7 no lo da (lo sustenta el estudio con '
                          'estudios propios, regulatorios anteriores y estándares latinoamericanos); no suma')
    return res


def cantidades_de_dimensionamiento(dim: Any, *, componente_red: Mapping[str, str],
                                   registro: RegistroNormativo, fecha: str | None = None) -> dict[str, list[Cantidad]]:
    """Cantidades adaptadas de la red dimensionada de la T6 (``vad.dimensionamiento.Dimensionamiento``), por
    alimentador: km de cada nivel con conductor de la empresa modelo, número de SED y kVA de la empresa modelo.

    ``componente_red`` (nivel → componente del cuadro, p. ej. si la red es aérea o subterránea) lo declara el perfil:
    sin él no se adivina. Las SED van al componente del cuadro que se cuenta por subestación y los kVA al que se cuenta
    por kVA."""
    cuadro = componentes_del_cuadro(registro, fecha)
    por_sub = [c for c, u in cuadro.items() if 'subestación' in u]
    por_kva = [c for c, u in cuadro.items() if 'kVA' in u]
    if len(por_sub) != 1 or len(por_kva) != 1:
        raise VadError('el cuadro del Anexo 7 no tiene un solo componente por subestación y uno por kVA')
    for nivel, comp in componente_red.items():
        if comp not in cuadro or 'km' not in cuadro[comp]:
            raise VadError(f'el componente de red {comp!r} del nivel {nivel} no es un componente por km del cuadro')
    largo = {t.tramo: t.longitud_m for t in dim.modelo.tramos}
    out: dict[str, list[Cantidad]] = {}
    for alim in sorted({t.alimentador for t in dim.tramos} | {s.alimentador for s in dim.sed}):
        filas: list[Cantidad] = []
        for nivel in sorted({t.nivel for t in dim.tramos if t.alimentador == alim}):
            tramos = [t for t in dim.tramos if t.alimentador == alim and t.nivel == nivel
                      and t.conductor_modelo is not None and largo.get(t.tramo) is not None]
            if not tramos:
                continue
            if nivel not in componente_red:
                raise VadError(f'{alim}: el perfil no declara a qué componente del cuadro va la red de {nivel}')
            km = sum(float(largo[t.tramo]) for t in tramos) / 1000.0
            filas.append(Cantidad(componente_red[nivel], km, 'km', nivel if nivel in ETAPAS else 'MT',
                                  f'{len(tramos)} tramos dimensionados'))
        seds = [s for s in dim.sed if s.alimentador == alim and s.kva_modelo is not None]
        if seds:
            filas.append(Cantidad(por_sub[0], float(len(seds)), 'subestación', 'SED', 'SED de la empresa modelo'))
            filas.append(Cantidad(por_kva[0], sum(float(s.kva_modelo) for s in seds), 'kVA', 'SED',
                                  'kVA de la empresa modelo'))
        out[alim] = filas
    return out


# ------------------------------------------------------------------- costos excluidos y sustento contractual
@dataclass(frozen=True)
class Partida:
    """Un costo informado para el COyM: su naturaleza, su monto, su moneda y su fuente."""
    concepto: str
    naturaleza: str
    monto: float
    moneda: str
    fuente: str
    tercerizada: bool = False
    contrato: str = ''
    """Contrato de ejecución u orden de servicio que la sustenta; vacío si no hay."""


@dataclass
class Depuradas:
    admitidas: list[Partida] = field(default_factory=list)
    excluidas: list[tuple[Partida, str]] = field(default_factory=list)
    sin_monto: list[tuple[Partida, str]] = field(default_factory=list)
    """Actividades sin contrato u orden de servicio: no se desconocen, pero su monto informado no se toma."""
    motivos: list[str] = field(default_factory=list)
    reglas: dict[str, str] = field(default_factory=dict)

    def total(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for p in self.admitidas:
            out[p.moneda] = out.get(p.moneda, 0.0) + p.monto
        return out


def _clave_texto(texto: str) -> str:
    return ' '.join(str(texto).casefold().split())


def depurar_partidas(partidas: Sequence[Partida], registro: RegistroNormativo,
                     fecha: str | None = None) -> Depuradas:
    res = Depuradas()
    excl = _regla(registro, REGLA_EXCLUIDOS, fecha, res.motivos, res.reglas)
    efic = _regla(registro, REGLA_EFICIENTES, fecha, res.motivos, res.reglas)
    if excl is None or efic is None:
        raise VadError('; '.join(res.motivos))
    lista = {_clave_texto(x): x for x in excl.regla.valor}
    for p in partidas:
        if not str(p.fuente or '').strip():
            res.motivos.append(f'la partida «{p.concepto}» no declara su fuente')
        excluida = lista.get(_clave_texto(p.naturaleza))
        if excluida is not None:
            res.excluidas.append((p, f'«{excluida}» está en la lista cerrada de costos excluidos ({_cita(excl)})'))
        elif p.tercerizada and not str(p.contrato or '').strip():
            res.sin_monto.append((p, f'sin contrato ni orden de servicio no se toma el monto informado; la '
                                     f'actividad no se desconoce ({_cita(efic)})'))
        else:
            res.admitidas.append(p)
    return res


# ---------------------------------------------------------------------------------------------- tope salarial
@dataclass
class TopeSalarial:
    costo: dict[str, float] = field(default_factory=dict)
    recortadas: dict[str, tuple[float, float]] = field(default_factory=dict)
    """categoría → (encuesta, real): la encuesta excedía el real y se tomó el real."""
    avisos: list[str] = field(default_factory=list)
    reglas: dict[str, str] = field(default_factory=dict)


def tope_salarial(categorias: Mapping[str, tuple[float, float]], registro: RegistroNormativo,
                  fecha: str | None = None) -> TopeSalarial:
    """``categorias``: categoría → (costo anual por empleado de la encuesta, costo real de la empresa de referencia),
    los dos con las mismas componentes (remuneraciones + beneficios + cargas patronales, sin reparto de utilidades)."""
    res = TopeSalarial()
    motivos: list[str] = []
    v = _regla(registro, REGLA_REMUNERACIONES, fecha, motivos, res.reglas)
    if v is None:
        raise VadError('; '.join(motivos))
    for cat, (encuesta, real) in sorted(categorias.items()):
        if encuesta > real:
            res.costo[cat] = float(real)
            res.recortadas[cat] = (float(encuesta), float(real))
            res.avisos.append(f'{cat}: la encuesta ({encuesta}) excede el costo real de la empresa de referencia '
                              f'({real}); se toma el real ({_cita(v)})')
        else:
            res.costo[cat] = float(encuesta)
    res.avisos.extend(motivos)
    return res


# ---------------------------------------------------------------------------------------- capital de trabajo
@dataclass
class CapitalDeTrabajo:
    cct: float
    contraste: float
    """El CCT con la otra conversión diaria (la proporcional si se usó la efectiva, y al revés)."""
    tasa_anual: float
    tasa_diaria: float
    conversion: str
    dias: int
    avisos: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)
    reglas: dict[str, str] = field(default_factory=dict)

    @property
    def conforme(self) -> bool:
        return not self.motivos


def tasa_diaria(tasa_anual: float, dias_del_anio: int, conversion: str) -> float:
    if conversion == 'efectiva':
        return (1.0 + tasa_anual) ** (1.0 / dias_del_anio) - 1.0
    if conversion == 'proporcional':
        return tasa_anual / dias_del_anio
    raise VadError(f'conversión diaria {conversion!r}; las admitidas son {CONVERSIONES}')


def _cct(saldos: Sequence[float], i_d: float) -> float:
    n = len(saldos)
    return sum(max(0.0, -float(s)) * i_d * (1.0 + i_d) ** (n - 1 - k) for k, s in enumerate(saldos))


def capital_de_trabajo(saldos: Sequence[float], registro: RegistroNormativo, *, inicio: date,
                       conversion: str = 'efectiva', sustento: str = '', fecha: str | None = None) -> CapitalDeTrabajo:
    """CCT = Σ_d max(0, −S_d)·i_d·(1 + i_d)^(n_d), desde ``inicio`` (primer día del periodo tarifario) hasta el 31 de
    diciembre de ese año: ``saldos`` trae un saldo de caja por día, ni uno más ni uno menos.

    La tasa diaria es la efectiva (P-4); la proporcional solo con el ``sustento`` del perfil. Los días del año son los
    del calendario (365, o 366 en un año bisiesto)."""
    if conversion not in CONVERSIONES:
        raise VadError(f'conversión diaria {conversion!r}; las admitidas son {CONVERSIONES}')
    if conversion != 'efectiva' and not sustento.strip():
        raise VadError('la tasa diaria proporcional se aparta de la decisión P-4 (efectiva): el perfil tiene que dar '
                       'su sustento')
    dias = (date(inicio.year, 12, 31) - inicio).days + 1
    if len(saldos) != dias:
        raise VadError(f'el flujo va del {inicio.isoformat()} al 31-12-{inicio.year}: son {dias} saldos diarios y '
                       f'llegan {len(saldos)}')
    motivos: list[str] = []
    reglas: dict[str, str] = {}
    v = _regla(registro, REGLA_CCT, fecha, motivos, reglas)
    if v is None:
        raise VadError('; '.join(motivos))
    tasa = float(v.regla.valor['tasa_interes'])
    del_anio = 366 if calendar.isleap(inicio.year) else 365
    i_d = tasa_diaria(tasa, del_anio, conversion)
    otra = 'proporcional' if conversion == 'efectiva' else 'efectiva'
    res = CapitalDeTrabajo(cct=_cct(saldos, i_d), contraste=_cct(saldos, tasa_diaria(tasa, del_anio, otra)),
                           tasa_anual=tasa, tasa_diaria=i_d, conversion=conversion, dias=dias, motivos=motivos,
                           reglas=reglas)
    res.avisos.append(f'tasa diaria {conversion} ({i_d:.10f}) de la tasa del {tasa:.0%} ({_cita(v)}); con la '
                      f'{otra} el CCT sería {res.contraste:.2f}' + (f'; sustento: {sustento}' if sustento else ''))
    try:
        lce = regla_remitida(registro, REGLA_TASA, fecha)     # UNA-TASA: remite a la del art. 79 de la LCE
        reglas[REGLA_TASA] = lce.huella()
        if abs(float(lce.valor) - tasa) > 1e-12:
            res.avisos.append(f'la tasa del CCT ({tasa}) no es la de {REGLA_TASA} ({lce.valor}), a la que remite '
                              'el TdR (art. 79 de la LCE)')
    except (RegistroError, TypeError, ValueError) as exc:
        res.avisos.append(f'no se pudo contrastar la tasa del CCT con {REGLA_TASA}: {exc}')
    try:
        rem = registro.regla(REGLA_REMISION_CCT, fecha)
        reglas[REGLA_REMISION_CCT] = rem.huella()
        res.avisos.append(f'errata del TdR: el {rem.regla.valor["numeral"]} remite al {rem.regla.valor["remite_a"]}; '
                          f'se aplica el {rem.regla.valor["se_aplica"]} ({_cita(rem)})')
    except RegistroError as exc:
        motivos.append(f'falta la regla {REGLA_REMISION_CCT} (la errata del num. 5.12): {exc}')
    return res


def dias_del_periodo(inicio: date) -> list[date]:
    """Los días del flujo del CCT: del primer día del periodo tarifario al 31 de diciembre."""
    return [inicio + timedelta(days=k) for k in range((date(inicio.year, 12, 31) - inicio).days + 1)]


# ---------------------------------------------------------------------------------------- costos compartidos
@dataclass
class CostosCompartidos:
    al_servicio: float | None
    a_inversiones: float | None
    tope: float | None
    base: float | None
    base_origen: str
    sin_asignar: float | None = None
    """El exceso de la parte de inversión sobre el tope que ninguna regla citada asigna (hueco nombrado)."""
    avisos: list[str] = field(default_factory=list)
    huecos: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)
    reglas: dict[str, str] = field(default_factory=dict)

    @property
    def conforme(self) -> bool:
        return not self.motivos


def costos_compartidos(gastos_organos_gobierno: float, registro: RegistroNormativo, *,
                       avnr_periodo: float | None = None, base_tope: float | None = None, sustento_base: str = '',
                       vnr: float | None = None, vida_util: float | None = None,
                       fecha: str | None = None) -> CostosCompartidos:
    """Reparto de los gastos de los órganos de gobierno según el TdR (Anexo 7, num. 13, «numeral 5.1 del Manual»):
    inversión = mín(25 % de los gastos; 7,5 % de la base) y el 75 % al servicio. El exceso de la parte de inversión
    sobre el tope solo se asigna con una regla citada de este ámbito (:data:`REGLA_EXCESO`); sin ella queda en
    ``sin_asignar`` como hueco nombrado. La Nota 2 del Formato 3.2 del Manual se cita como aviso: es de otro ámbito y
    no se extiende (c3, VAD-A7 v3).

    La base es la «inversión analizada» del TdR. La empresa modelo no tiene ejercicio contable: por defecto se toma el
    aVNR del periodo (``avnr_periodo``, interpretación P-5); el perfil la sustituye con ``base_tope`` y su
    ``sustento_base``. Con ``vnr`` y ``vida_util`` se da como contraste el tope sobre VNR/vida útil. Sin base, el
    reparto queda como hueco nombrado."""
    motivos: list[str] = []
    reglas: dict[str, str] = {}
    v = _regla(registro, REGLA_COMPARTIDOS, fecha, motivos, reglas)
    if v is None:
        raise VadError('; '.join(motivos))
    if base_tope is not None and not sustento_base.strip():
        raise VadError('la base del tope del 7,5 % que declara el perfil necesita su sustento')
    valor = v.regla.valor
    al_servicio_pct = float(valor['organos_de_gobierno_al_servicio'])
    a_inversion_pct = float(valor['organos_de_gobierno_a_inversiones'])
    tope_pct = float(valor['tope_sobre_inversion'])
    if abs(al_servicio_pct + a_inversion_pct - 1.0) > 1e-12:
        motivos.append(f'{REGLA_COMPARTIDOS}: {al_servicio_pct} + {a_inversion_pct} no suman 1')
    if base_tope is not None:
        base, origen = float(base_tope), f'base declarada por el perfil: {sustento_base}'
    elif avnr_periodo is not None:
        base, origen = float(avnr_periodo), ('aVNR del periodo de la empresa modelo (interpretación P-5 de 28: el '
                                             'TdR dice «inversión analizada» y la empresa modelo no tiene ejercicio)')
    else:
        base, origen = None, ''
    res = CostosCompartidos(None, None, None, base, origen, motivos=motivos, reglas=reglas)
    g = float(gastos_organos_gobierno)
    if base is None:
        res.huecos.append('sin la base del tope del 7,5 % (el aVNR del periodo o la que declare el perfil) no se '
                          f'reparte: hueco nombrado ({_cita(v)})')
    else:
        res.tope = tope_pct * base
        res.a_inversiones = min(a_inversion_pct * g, res.tope)
        exceso = a_inversion_pct * g - res.a_inversiones
        res.al_servicio = al_servicio_pct * g
        res.sin_asignar = 0.0
        res.avisos.append(f'TdR: {al_servicio_pct:.0%} al servicio y {a_inversion_pct:.0%} a inversiones con tope del '
                          f'{tope_pct:.1%} de la base ({origen}) ({_cita(v)})')
        if exceso > 0:
            try:
                regla_exceso = registro.regla(REGLA_EXCESO, fecha)
            except RegistroError:
                regla_exceso = None
            if regla_exceso is not None:
                reglas[REGLA_EXCESO] = regla_exceso.huella()
                destino = (regla_exceso.regla.valor or {}).get('destino') \
                    if isinstance(regla_exceso.regla.valor, Mapping) else None
                if destino not in DESTINOS_EXCESO:
                    raise VadError(f'{REGLA_EXCESO}: destino {destino!r}; los admitidos son {DESTINOS_EXCESO}')
                res.al_servicio += exceso
                res.avisos.append(f'el exceso sobre el tope ({exceso:.2f}) va al {destino} ({_cita(regla_exceso)})')
            else:
                res.sin_asignar = exceso
                res.huecos.append(f'el exceso sobre el tope ({exceso:.2f}) no lo asigna el TdR ni ninguna regla citada '
                                  f'de su ámbito ({REGLA_EXCESO}): hueco nombrado, sin asignar')
                try:
                    nota = registro.regla(REGLA_NOTA2_MANUAL, fecha)
                except RegistroError:
                    nota = None
                if nota is not None:
                    reglas[REGLA_NOTA2_MANUAL] = nota.huella()
                    ambito = ''
                    try:
                        gastos = registro.regla(REGLAS_MANUAL[0], fecha).regla.valor.get('gastos') or ()
                        ambito = ', '.join(gastos)
                    except (RegistroError, AttributeError):
                        pass
                    res.avisos.append(f'la Nota 2 del Formato 3.2 del Manual ({nota.norma.acto}) existe («75 % o la '
                                      f'diferencia», {_cita(nota)}), pero es de otro ámbito'
                                      + (f' ({ambito})' if ambito else '') + ', no de los órganos de gobierno del '
                                      'TdR: no se extiende')
        if vnr is not None and vida_util:
            alterno = tope_pct * float(vnr) / float(vida_util)
            res.avisos.append(f'contraste (P-5): con la base VNR/vida útil = {float(vnr) / float(vida_util):.2f}, el '
                              f'tope sería {alterno:.2f} y a inversiones irían {min(a_inversion_pct * g, alterno):.2f}')
    manual = []
    for clave in REGLAS_MANUAL:
        try:
            m = registro.regla(clave, fecha)
        except RegistroError:
            continue
        reglas[clave] = m.huella()
        manual.append(m)
    if manual:
        acto = manual[0].norma.acto
        modif = ', '.join(manual[0].norma.modificada_por)
        res.avisos.append(
            f'el TdR (Anexo 7, num. 13) transcribe como «numeral 5.1 del Manual» un reparto que no está en el Manual '
            f'vigente ({acto}' + (f', modificada por {modif}' if modif else '') + '), que aplica el 75/25 con otro '
            f'ámbito y otra base del tope: {para_el_vad(v)} manda el TdR. TdR: {_cita(v)}. '
            'Manual: '
            + ' | '.join(_cita(m) for m in manual))
    else:
        res.huecos.append('el Manual de Costos vigente (RCD 218-2020-OS/CD y modificatorias) no está en el registro: '
                          'no se puede citar la discrepancia con el TdR')
    try:
        a74 = registro.regla(REGLA_A7_4, fecha)
        reglas[REGLA_A7_4] = a74.huella()
        manda = a74.regla.valor.get('manda') if isinstance(a74.regla.valor, Mapping) else None
        res.huecos.append('A7-4: el texto de la RM 197-94-EM/VME no se ha hallado' + (f'; manda {manda}' if manda else '')
                          + f' ({_cita(a74)})')
    except RegistroError:
        res.huecos.append('A7-4: el TdR cita también el Manual de Costos de la RM 197-94-EM/VME, cuyo texto no se ha '
                          'hallado (búsqueda web, MINEM y gob.pe; falta el SPIJ): hueco nombrado')
    return res
