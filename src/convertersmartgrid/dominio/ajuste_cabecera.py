"""Ajuste de las demandas de un alimentador a su máxima de cabecera (spec 006).

La demanda medida (spec 004) da la máxima de cabecera y los clientes importantes con su
SED, pero el operador la repartía a mano entre las SED del alimentador modelado en
DIgSILENT, a prueba y error hasta que el flujo de carga diera en la cabecera la máxima
medida. Aquí está el reparto, sin DIgSILENT, para poder probarlo:

- Las SED con clientes importantes llevan la suma de la potencia de sus clientes, en
  lugar de la demanda que tengan en el modelo (RF-5, RF-6).
- Las demás se reparten lo que falta, todas con los mismos kW y kVAR por kVA instalado
  (RF-8): una SED de 630 kVA lleva lo mismo por kVA que una de 50, sea cual sea la
  demanda que tenía.

Las pérdidas no se conocen hasta ejecutar el flujo: el reparto inicial cuadra sin ellas,
y el cuadre las va añadiendo cambiando solo los dos factores (``a`` para kW, ``b`` para
kVAR) de las SED que escalan.
"""

from __future__ import annotations

import calendar
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .compat_pf import zip_estricto
from .numeros_medidos import clave_codigo, numero


class AjusteError(ValueError):
    """No se puede ajustar: falta el objetivo o un dato de una SED (RF-3, RF-24)."""


@dataclass(frozen=True)
class Objetivo:
    """Lo que tiene que entrar por la cabecera: el registro de la máxima (RF-1)."""

    kw: float
    kvar: float
    medidor: str
    alimentador: str = ''
    fecha: str | None = None

    @property
    def tan_phi(self) -> float:
        return self.kvar / self.kw

    @property
    def fp(self) -> float:
        return self.kw / math.hypot(self.kw, self.kvar)


def objetivo_de(maxima: Mapping[str, Any]) -> Objetivo:
    """El objetivo desde una fila de la máxima de cabecera (``MaximaCabecera.to_dict``)."""
    medidor = str(maxima.get('medidor') or '')
    if maxima.get('error'):
        raise AjusteError(f'{medidor}: sin máxima de cabecera ({maxima["error"]}).')
    kw = numero(maxima.get('kw'))
    if kw is None or kw <= 0:
        raise AjusteError(f'{medidor}: la máxima de cabecera no tiene un kW positivo.')
    kvar = numero(maxima.get('kvar'))
    if kvar is None:
        # Hay medidores que exportan el FP y no el kVAR: el del mismo registro sirve.
        fp = numero(maxima.get('fp'))
        if fp is None or not 0 < abs(fp) <= 1:
            raise AjusteError(f'{medidor}: la máxima de cabecera no trae kVAR ni FP.')
        # 088:RF-14 (RF-2, RF-3): el signo de la Q lo da su FP declarado (``lead`` capacitivo, ``lag`` inductivo) o, sin
        # él, el signo de su medida (un FP negativo es capacitivo, como lo deja ``maxima_de_registros``).
        palabras = str((maxima.get('columnas') or {}).get('fp') or '').lower().split()
        capacitivo = 'lead' in palabras or ('lag' not in palabras and fp < 0)
        kvar = math.copysign(kw * math.tan(math.acos(abs(fp))), -1.0 if capacitivo else 1.0)
    return Objetivo(kw=kw, kvar=kvar, medidor=medidor,
                    alimentador=str(maxima.get('alimentador') or ''), fecha=maxima.get('fecha'))


@dataclass
class Fija:
    """SED con clientes importantes: su demanda es la de ellos (RF-5)."""

    sed: str
    kw: float = 0.0
    kvar: float = 0.0
    clientes: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    derivaciones: list[dict[str, Any]] = field(default_factory=list)

    @property
    def fp(self) -> float:
        apparent = math.hypot(self.kw, self.kvar)
        return abs(self.kw) / apparent if apparent else 1.0


def fijas_de(cruzados: Iterable[Mapping[str, Any]], objetivo: Objetivo,
             fp_minimo: float | None = None) -> dict[str, Fija]:
    """Suma por SED de los clientes cruzados (``ClienteImportante.to_dict``).

    El kVAR de cada cliente sale de su energía reactiva y activa del mes (RF-6): es su
    factor de potencia medio, que es lo que se conoce de él. Sin una de las dos, el del
    objetivo (RF-7). El factor de las escaladas del perfil no las toca (015:RF-53).

    Con ``fp_minimo`` (perfil de empresa, 015:RF-62 a RF-64), el cliente cuyo EA/ERI da un
    factor menor se escribe con ese mínimo, como compensado por su banco propio, y queda
    dicho en su derivación y en un aviso. En CA191 (2026-10-15) el EA/ERI daba factores
    de 0,43 a 0,98 y la cabecera 3036 kvar frente a 302 medidos.
    """
    por_clave: dict[str, Fija] = {}
    for c in cruzados:
        sed = str(c.get('sed') or '').strip()
        derivacion = derivacion_cliente(c, objetivo.tan_phi, objetivo.fp, fp_minimo)
        if not sed or derivacion is None:
            continue
        f = por_clave.setdefault(clave_codigo(sed), Fija(sed))
        aviso = derivacion.pop('aviso', None)
        if aviso:
            f.avisos.append(aviso)
        f.kw += derivacion['p_kw']
        f.kvar += derivacion['q_kvar']
        f.clientes.append(derivacion['cliente'])
        f.derivaciones.append(derivacion)
    return {f.sed: f for f in por_clave.values()}


def derivacion_cliente(c: Mapping[str, Any], tan_objetivo: float, fp_objetivo: float,
                       fp_minimo: float | None = None) -> dict[str, Any] | None:
    """La P y la Q que se escriben de un cliente fijo, y de dónde salen (035:RF-2 a RF-4).

    Una sola cuenta para la tabla de la web y para el ajuste: antes la tabla enseñaba la POT
    de cada cliente, cada una de su día, y el ajuste escribía la P del instante de la máxima
    de su alimentador (004:RF-67); el operador no veía lo que iba a DIgSILENT (2026-10-29).
    ``None`` si el cliente no trae potencia. ``aviso``, si lo hay, es para el informe.
    """
    kw = numero(c.get('pot'))
    if kw is None:
        return None
    ea, eri = numero(c.get('ea')), numero(c.get('eri'))
    codigo = str(c.get('codigo') or '')
    q_registro = numero(c.get('q_registro_kvar'))
    p_registro = numero(c.get('p_registro_kw'))
    fecha = str(c.get('fecha_registro') or '').strip() or None
    aviso = None
    q_directa = None
    sin_consumo = False
    if p_registro is not None:
        # 004:RF-67: P y Q del cliente en el instante de su alimentador, coincidentes.
        kw = p_registro
    if q_registro is not None and kw:
        # 004:RF-66: la reactiva del registro de 15 minutos (el del instante o el de su POT).
        tan = q_registro / kw
        metodo = ('REGISTRO_DEL_INSTANTE' if p_registro is not None
                  else f"ERI_DEL_REGISTRO {fecha or ''}".strip())
    elif q_registro is not None and p_registro is not None:
        # 035:RF-32: P = 0 en el registro del instante es su valor, no la falta de un dato: la Q es la del registro y
        # no se etiqueta «ERI/EA». Una distribuidora real tenía un suministro con 60 kWh en el mes.
        tan, q_directa, sin_consumo = 0.0, q_registro, True
        metodo = 'REGISTRO_DEL_INSTANTE'
        mes = f'; su EA del mes es {ea:,.1f} kWh' if ea is not None else ''
        aviso = f'{codigo}: fija sin consumo en el instante ({fecha or "su registro"}){mes}.'
    elif ea is None or eri is None or ea == 0:
        tan = tan_objetivo
        metodo = 'FP_CABECERA_FALLBACK'
        aviso = f'{codigo}: sin EA o ERI; su kVAR con el FP del objetivo ({fp_objetivo:.3f}).'
        if tan < 0:
            # 088:RF-13: una cabecera capacitiva no hace capacitiva a una carga: el FP de las fijas del perfil o, sin
            # él, el de la cabecera como inductivo.
            fp_fija = fp_minimo if fp_minimo is not None else fp_objetivo
            tan = math.tan(math.acos(fp_fija))
            metodo = 'FP_FIJAS_PERFIL' if fp_minimo is not None else 'FP_CABECERA_INDUCTIVO'
            aviso = (f'{codigo}: sin EA o ERI y con la cabecera capacitiva; su kVAR con FP {fp_fija:.3f} inductivo '
                     + ('de las fijas del perfil.' if fp_minimo is not None else 'de la cabecera.'))
    else:
        tan = eri / ea
        metodo = 'ERI/EA'
    q_kvar = kw * tan if q_directa is None else q_directa
    fp_libro = abs(kw) / math.hypot(kw, q_kvar) if (kw or q_kvar) else 1.0
    compensado = None
    # 004:RF-66: con su registro, su FP es el de su EA y ERI en esa fecha y hora, sin
    # llevarlo al mínimo: la compensación de 015:RF-62 era para el cociente del mes
    # (usuario, 2026-10-28).
    if fp_minimo is not None and fp_libro < fp_minimo and kw > 0 and q_registro is None:
        q_libro = q_kvar
        q_kvar = kw * math.tan(math.acos(fp_minimo))
        compensado = {'fp_ea_eri': fp_libro, 'fp_escrito': fp_minimo,
                      'q_ea_eri_kvar': q_libro, 'q_escrita_kvar': q_kvar}
        aviso = (f'{codigo}: FP {fp_libro:.3f} de su EA/ERI llevado a {fp_minimo:.3f} por su '
                 f'banco propio; Q {q_libro:,.1f} → {q_kvar:,.1f} kvar.')
    derivacion: dict[str, Any] = {
        'cliente': codigo,
        'p_kw': kw,
        'q_kvar': q_kvar,
        'fp': abs(kw) / math.hypot(kw, q_kvar) if (kw or q_kvar) else 1.0,
        'metodo': metodo,
        'ea': ea,
        'eri': eri,
    }
    if q_registro is not None and fecha:
        derivacion['fecha'] = fecha                 # 035:RF-2: de qué registro sale
    if sin_consumo:
        derivacion['sin_consumo'] = True            # 035:RF-32
    if compensado:
        derivacion['compensado'] = compensado
    if aviso:
        derivacion['aviso'] = aviso
    return derivacion


def sed_desconectadas(desconectados: Iterable[Mapping[str, Any]],
                      conectados: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """SED cuyos clientes importantes desmarcó todos el operador (RF-26): SED → sus Nis.

    Una SED con un cliente desmarcado y otro conectado sigue en servicio con la potencia
    del conectado: la carga de DIgSILENT es la de la SED entera, no la de cada cliente.
    """
    siguen = {clave_codigo(str(c.get('sed') or '')) for c in conectados}
    por_clave: dict[str, tuple[str, list[str]]] = {}
    for c in desconectados:
        sed = str(c.get('sed') or '').strip()
        if not sed or clave_codigo(sed) in siguen:
            continue
        por_clave.setdefault(clave_codigo(sed), (sed, []))[1].append(str(c.get('codigo') or ''))
    return dict(por_clave.values())


@dataclass(frozen=True)
class DemandaSed:
    sed: str
    kw: float
    kvar: float
    origen: str                 # 'cliente' | 'kva'
    kva: float | None


@dataclass
class Reparto:
    """Demandas por SED. Las que escalan valen ``a × base_kw`` y ``b × base_kvar``."""

    fijas: dict[str, tuple[float, float]]           # SED → (kW, kVAR) que no escalan
    base: dict[str, tuple[float, float]]            # SED → base (kW, kVAR) de las que escalan
    origen: dict[str, str]
    kva: dict[str, float | None]
    a: float
    b: float
    todo_escala: bool = False           # 006:RF-46: ya no se escalan las fijas; queda para leer informes de antes
    solo_kw: bool = False
    omitidas: list[dict[str, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    #: 006:RF-46: por qué no se puede cuadrar antes de ningún flujo (``estado`` CALIBRACION_IMPOSIBLE o NO_CALIBRABLE).
    causa: dict[str, Any] | None = None
    #: 015:RF-74: la SED del cliente → sus hermanas «<sed>-n», que llevan su parte de la fija y no se escalan.
    grupos: dict[str, list[str]] = field(default_factory=dict)

    def con_factores(self, a: float, b: float | None = None) -> Reparto:
        """El mismo reparto con otros factores; en «solo kW» el kVAR sigue al kW (RF-14)."""
        b = a if self.solo_kw else (self.b if b is None else b)
        return Reparto(**{**self.__dict__, 'a': a, 'b': b})

    def con_q(self) -> Reparto:
        """El mismo reparto con la Q de las escaladas libre de su P (035:RF-6)."""
        return replace(self, solo_kw=False)

    def al_perfil(self) -> Reparto:
        """Las escaladas otra vez con el FP de su base, la Q siguiendo a la P (035:RF-29).

        Es como quedan en la calibración: con una medida de cabecera que no es coherente, su
        Q es la que dé DIgSILENT con ese FP, no una forzada a la medida.
        """
        return replace(self, solo_kw=True, b=self.a)

    def factor_q_maximo(self, fp_minimo: float | None) -> float:
        """El factor de Q de las escaladas con su FP en ``fp_minimo`` (035:RF-28).

        Sin mínimo, el FP de su base: el factor de Q no pasa del de P.
        """
        bp = sum(p for p, _ in self.base.values())
        bq = sum(q for _, q in self.base.values())
        if fp_minimo is None or bp <= 0 or bq <= 0:
            return self.a
        return max(self.a, self.a * math.tan(math.acos(fp_minimo)) / (bq / bp))

    def fp_escaladas(self) -> float | None:
        """FP de las escaladas con los factores actuales: el de su base si ``b == a`` (035:RF-12)."""
        bp = sum(p for p, _ in self.base.values())
        bq = sum(q for _, q in self.base.values())
        if bp <= 0 or self.a <= 0:
            return None
        tan = bq / bp * self.b / self.a
        return 1.0 / math.hypot(1.0, tan)

    def a_solo_kw(self, objetivo: Objetivo) -> Reparto:
        """Pasa a «solo kW» (RF-14): el kVAR de las que escalan, con el FP del objetivo."""
        if self.solo_kw:
            return self
        base = {s: (p, p * objetivo.tan_phi) for s, (p, _) in self.base.items()}
        return Reparto(**{**self.__dict__, 'base': base, 'b': self.a, 'solo_kw': True})

    @property
    def demandas(self) -> dict[str, DemandaSed]:
        out = {}
        for sed in self.origen:
            if sed in self.base:
                bp, bq = self.base[sed]
                kw, kvar = self.a * bp, self.b * bq
            else:
                kw, kvar = self.fijas[sed]
            out[sed] = DemandaSed(sed, kw, kvar, self.origen[sed], self.kva.get(sed))
        return out

    def totales(self) -> tuple[float, float]:
        ds = self.demandas.values()
        return sum(d.kw for d in ds), sum(d.kvar for d in ds)


def _kva_valido(v: Any) -> float | None:
    x = numero(v)
    return x if x is not None and x > 0 else None


def hermanas_de(sed: str, nombres: Iterable[str]) -> list[str]:
    """Las SED «<sed>-n» de ``nombres`` (015:RF-74): la instalación de un cliente con varios transformadores.

    Se comparan los nombres tal cual, en mayúsculas: ``clave_codigo`` quita el guion y confundiría «SE1-2» con «SE12».
    """
    patron = re.compile(re.escape(str(sed).strip().upper()) + r'-\d+')
    return sorted(n for n in nombres if patron.fullmatch(str(n).strip().upper()))


def kva_de_grupo(sed: str, kva: Mapping[str, Any], nombres: Iterable[str]) -> float | None:
    """Los kVA de la SED y de sus hermanas «<sed>-n» (015:RF-75); ``None`` si ninguna tiene."""
    valores = [v for v in (_kva_valido(kva.get(s)) for s in [sed, *hermanas_de(sed, nombres)]) if v]
    return sum(valores) if valores else None


def _grupos_de_fijas(fijas_pf: Mapping[str, tuple[float, float]], nombres: Iterable[str],
                     kwh: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """015:RF-74: las hermanas de cada fija que no son fijas y, si se conoce, sin energía en la fuente."""
    libres = [n for n in nombres if n not in fijas_pf]
    grupos: dict[str, list[str]] = {}
    for sed in fijas_pf:
        suyas = [h for h in hermanas_de(sed, libres)
                 if kwh is None or (numero(kwh.get(h)) or 0.0) <= 0.0]
        if suyas:
            grupos[sed] = suyas
    return grupos


def reparto_inicial(objetivo: Objetivo, fijas: Mapping[str, Fija],
                    cargas: Mapping[str, tuple[float, float]],
                    kva: Mapping[str, Any] | None = None,
                    fp: float | None = None,
                    kwh: Mapping[str, Any] | None = None) -> Reparto:
    """El reparto que da el objetivo sin pérdidas, con el factor de escala de DIgSILENT.

    ``cargas`` tiene una entrada por cada carga de SED del alimentador en DIgSILENT, con el
    nombre que tiene allí y su P y Q (kW, kVAR): es la lista de SED. Las fijas (clientes
    importantes) se buscan en ella por su código y llevan su P y Q (015:RF-43).

    Las demás escalan según su potencia instalada (015:RF-44): P base = kVA × FP, Q base con
    ese mismo FP, y un solo factor de escala, el ``scale0`` de DIgSILENT, que es así la
    fracción de carga de sus transformadores. El usuario, el 2026-10-15: «el escalado se
    debe hacer a sus potencias instaladas de cada SED escalada». Con la P del archivo, en
    CA191 98 de 160 escaladas (11 057 kVA) tenían demanda cero y los 6 MW caían en 62 SED.
    El FP es el del perfil de empresa (``fp``, 015:RF-54) o, sin él, el de la máxima de
    cabecera (RF-55). Una SED sin kVA conocido queda en cero, con aviso (RF-45). Las fijas
    conservan la Q de su EA/ERI y las cambiadas a mano la que tienen (RF-53, RF-58).
    """
    por_clave = {clave_codigo(s): s for s in cargas}
    kvas = {s: _kva_valido((kva or {}).get(s)) for s in cargas}
    fijas_pf: dict[str, tuple[float, float]] = {}
    omitidas, avisos = [], []
    for f in fijas.values():
        sed = por_clave.get(clave_codigo(f.sed))
        if sed is None:
            omitidas.append({'sed': f.sed, 'motivo': 'no está en el alimentador del proyecto',
                             'clientes': ', '.join(f.clientes)})
            continue
        fijas_pf[sed] = (f.kw, f.kvar)
        avisos += [f'{sed}: {a}' for a in f.avisos]
    # 015:RF-74: las hermanas «<sed>-n» de una fija son de su cliente: su P y Q se reparten en el grupo por kVA y salen
    # de las escaladas. Antes cada hermana se escalaba aparte y el grupo cargaba de más (en una red real, 255,8 kW).
    grupos = _grupos_de_fijas(fijas_pf, cargas, kwh)
    for sed, suyas in grupos.items():
        p, q = fijas_pf[sed]
        miembros = [sed, *suyas]
        total = sum(kvas[m] or 0.0 for m in miembros)
        for m in miembros:
            parte = (kvas[m] or 0.0) / total if total > 0 else (1.0 if m == sed else 0.0)
            fijas_pf[m] = (p * parte, q * parte)
        avisos.append(f"{sed}: su grupo ({', '.join(suyas)}) es de su cliente: la fija se reparte por kVA y no se "
                      'escala.')
    fp_escaladas = objetivo.fp if fp is None else fp
    tan = math.tan(math.acos(fp_escaladas))
    base = {s: ((kvas[s] or 0.0) * fp_escaladas, (kvas[s] or 0.0) * fp_escaladas * tan)
            for s in cargas if s not in fijas_pf}
    ceros = sorted(s for s in base if not kvas[s])
    if ceros:
        # 015:RF-45: sin potencia instalada conocida, el factor de escala la deja en cero.
        avisos.append(f'{len(ceros)} SED escaladas sin potencia instalada conocida: quedan '
                      'en cero: ' + ', '.join(ceros[:50]))
    origen = {s: ('cliente' if s in fijas_pf else 'escala') for s in cargas}
    p_fijas = sum(p for p, _ in fijas_pf.values())
    p_base = sum(p for p, _ in base.values())
    p_falta = objetivo.kw - p_fijas
    if p_falta > 0 and p_base > 0:
        a = p_falta / p_base
        return Reparto(fijas=fijas_pf, base=base, origen=origen, kva=kvas, a=a, b=a,
                       solo_kw=True, omitidas=omitidas, avisos=avisos, grupos=grupos)

    # 006:RF-46 (cambia RF-13, orden del usuario del 19-11): las fijas van siempre a escala 1, con su P y Q. Si ya
    # llenan la cabecera, las escaladas quedan al mínimo y no se puede cuadrar (086:RF-124); si no hay escaladas con
    # kVA, no hay qué repartir. Antes se escalaban también las fijas: 5 010 kW frente a 5 000 kW de cabecera y 10 000
    # kVA de escaladas dejaban las fijas en 1 691 kW, cuando con 4 990 kW quedaban en 4 990 kW.
    if not fijas_pf and p_base <= 0:
        raise AjusteError('No hay demanda que escalar: ninguna SED tiene demanda en el archivo '
                          'original ni clientes importantes con potencia.')
    clave = objetivo.alimentador or objetivo.medidor or 'El alimentador'
    if p_base > 0:
        texto = (f'{clave}: sus fijas suman {p_fijas:,.1f} kW frente a {objetivo.kw:,.1f} kW de cabecera; las fijas '
                 'siguen con su P y Q, las escaladas quedan al mínimo y no puede cuadrar sin cambiar sus fijas.')
        causa = {'estado': CALIBRACION_IMPOSIBLE, 'codigo': 'FIJAS_LLENAN_LA_CABECERA', 'fijas_kw': p_fijas,
                 'objetivo_kw': objetivo.kw, 'texto': texto}
        a = 0.0
    else:
        texto = (f'{clave}: no se puede repartir: '
                 + ('ninguna SED escalada tiene potencia instalada conocida' if base else
                    'todas sus SED tienen clientes importantes')
                 + f'; sus fijas suman {p_fijas:,.1f} kW frente a {objetivo.kw:,.1f} kW de cabecera y no se escalan.')
        causa = {'estado': NO_CALIBRABLE, 'codigo': 'SIN_ESCALADAS_CON_KVA' if base else 'SIN_ESCALADAS',
                 'fijas_kw': p_fijas, 'objetivo_kw': objetivo.kw, 'texto': texto}
        a = 1.0
    avisos.append(texto)
    return Reparto(fijas=fijas_pf, base=base, origen=origen, kva=kvas, a=a, b=a, solo_kw=True,
                   omitidas=omitidas, avisos=avisos, causa=causa, grupos=grupos)


#: 006:RF-46: estados de un reparto que no se puede cuadrar antes de ningún flujo.
CALIBRACION_IMPOSIBLE, NO_CALIBRABLE = 'IMPOSIBLE', 'NO_CALIBRABLE'
#: 015:RF-71: una escalada que consume menos de esto está casi en cero (usuario, 2026-11-06: un alimentador real tenía 39 bajo 1 kW).
ESCALADA_CASI_CERO_KW = 1.0
#: 015:RF-71: un factor común de las escaladas (fracción de su potencia instalada) por debajo de esto es anormal.
FACTOR_ESCALADAS_ANORMAL = 0.05


def escaladas_casi_cero(clave: str, escaladas: Mapping[str, float], factor: float | None, fijas_kw: float | None,
                        cabecera_kw: float | None, *, umbral_kw: float = ESCALADA_CASI_CERO_KW,
                        factor_anormal: float = FACTOR_ESCALADAS_ANORMAL) -> dict[str, Any] | None:
    """Las escaladas casi en cero de un alimentador y su causa (015:RF-71), o ``None`` si no hay ninguna.

    ``escaladas``: el kW de cada escalada con potencia instalada (escrito o consumido en el flujo). Un factor común por
    debajo de ``factor_anormal`` no da la calibración por válida; una escalada bajo ``umbral_kw`` con el factor normal
    (una SED muy pequeña) se avisa sin invalidar.
    """
    bajo = sorted((s for s, kw in escaladas.items() if kw < umbral_kw), key=lambda s: (escaladas[s], s))
    anormal = factor is not None and 0 <= factor < factor_anormal
    if not bajo and not anormal:
        return None
    fraccion = fijas_kw / cabecera_kw if fijas_kw is not None and cabecera_kw else None
    # El factor que tendrían las escaladas sin ninguna fija: factor = (cabecera − fijas) / P base, así que la cabecera
    # sola da factor · cabecera / (cabecera − fijas). Si también es anormal, el factor bajo no es de las fijas (AL299,
    # que se comían la cabecera) sino de un alimentador poco cargado en ese instante: el 24-11 dos de un sistema entero,
    # con 18,8 y 55,2 kW frente a varios MVA y sin fijas, dejaron sin validar a los 17. Se avisa sin invalidar.
    libre = (cabecera_kw or 0.0) - (fijas_kw or 0.0)
    sin_fijas = factor * cabecera_kw / libre if anormal and cabecera_kw and libre > 0 else None
    poco_cargado = sin_fijas is not None and sin_fijas < factor_anormal
    n = len(bajo)
    partes = [f'{clave}: {n} de {len(escaladas)} SED escaladas '
              f"{'queda' if n == 1 else 'quedan'} por debajo de {umbral_kw:g} kW"]
    if factor is not None:
        partes.append(f"con un factor de escala de {factor:.4f}{', anormalmente bajo' if anormal else ''}")
    texto = ' '.join(partes)
    if bajo:
        texto += ': ' + ', '.join(bajo[:50]) + (f' y {n - 50} más' if n > 50 else '')
    if fijas_kw is not None and cabecera_kw:
        texto += f'. Las fijas suman {fijas_kw:,.1f} kW frente a {cabecera_kw:,.1f} kW de cabecera ({fraccion:.0%})'
        if poco_cargado:
            texto += (': el alimentador está poco cargado en este instante frente a su potencia instalada; la '
                      'calibración vale, pero conviene revisar la medida de su cabecera y sus potencias instaladas.')
        elif anormal:
            texto += ' y dejan casi nada para repartir; revise las fijas y el instante de sus registros.'
    if not texto.endswith('.'):
        texto += '.' if anormal and not poco_cargado else '; la calibración vale, pero conviene revisar sus potencias instaladas.'
    return {'clave': clave, 'umbral_kw': umbral_kw, 'cantidad': n, 'escaladas': len(escaladas), 'sed': bajo,
            'factor': factor, 'factor_anormal': anormal, 'invalida': anormal and not poco_cargado,
            'poco_cargado': poco_cargado, 'fijas_kw': fijas_kw,
            'cabecera_kw': cabecera_kw, 'fraccion_fijas': fraccion, 'aviso': texto}


def escaladas_casi_cero_del_reparto(reparto: Reparto, objetivo: Objetivo) -> dict[str, Any] | None:
    """:func:`escaladas_casi_cero` con lo que deja el reparto (015:RF-71): las escaladas con potencia instalada."""
    d = reparto.demandas
    escaladas = {s: d[s].kw for s, (p, _q) in reparto.base.items() if p > 0}
    return escaladas_casi_cero(objetivo.alimentador or objetivo.medidor or 'El alimentador', escaladas, reparto.a,
                               sum(p for p, _q in reparto.fijas.values()), objetivo.kw)


# =========================================================================== plausibilidad de las fijas
#: 015:RF-73 (enmienda RF-69), 006:RF-47: una fija a revisar para la calibración antes del primer flujo.
FIJA_A_REVISAR = 'FIJA_A_REVISAR'
#: 015:RF-73 (c): las fijas suman más que esta fracción de la cabecera y dejan a las escaladas con un factor anormal.
FRACCION_FIJAS_DUDOSA = 0.9
#: 015:RF-73 (b): una fija que pide más de estas veces los kVA de su grupo en la fuente, cuando la media de su mes sí
#: cabe en ellos, no es la carga de ese instante: ningún transformador lleva cuatro veces su potencia.
VECES_KVA_GRUPO_DUDOSA = 4.0
#: 015:RF-73 (b), 020:RF-64: la media del mes del cliente por encima de los kVA de su grupo: el dudoso es el kVA.
KVA_FUENTE_INCOHERENTE = 'KVA_FUENTE_INCOHERENTE'
#: 039:RF-25: los motivos de una fija físicamente imposible, que se libera en vez de parar el alimentador.
MOTIVOS_QUE_LIBERAN = frozenset({'SUPERA_LA_CABECERA', 'SUPERA_SU_GRUPO'})


def se_queda_fija(motivo: Mapping[str, Any]) -> bool:
    """039:RF-28: un cliente que pasa su cabecera solo en pocos registros (la cabecera no midió toda la carga en ellos)
    no se libera, con cualquier parte de la energía: su SED es carga del alimentador.

    LL203 (27-11): SE80083 (481000151) pasaba su cabecera en 15 registros de 2 976 y era el 68 % de su energía; liberado,
    sus 2 180 kW se repartieron entre las demás SED y la carga quedó lejos de donde está.
    """
    d = motivo.get('diagnostico') or {}
    # PA217 (27-11): SE30940 (700064806) pasaba su cabecera en 1 registro con el 38 % de su energía y se liberó a
    # 1,2 MW cuando medía 3,3 MW: con pocos registros cuenta la hipótesis de la cabecera, no la parte de la energía.
    return (motivo.get('codigo') == 'SUPERA_LA_CABECERA' and d.get('causa') == CAUSA_HIPOTESIS
            and bool(d.get('pocos_registros')))


def horas_del_mes(fecha: Any) -> float | None:
    """Las horas del mes de una fecha ``AAAA-MM…`` (015:RF-73: la potencia media del mes), o ``None``."""
    m = re.match(r'(\d{4})-(\d{2})', str(fecha or ''))
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return 24.0 * calendar.monthrange(int(m.group(1)), int(m.group(2)))[1]


def plausibilidad_fijas(objetivo: Objetivo, fijas: Mapping[str, Fija], *, p_base_escaladas: float,
                        kva_grupo: Mapping[str, float | None] | None = None,
                        evidencia: Mapping[str, Mapping[str, Any]] | None = None,
                        horas_mes: float | None = None, otras_fijas_kw: float = 0.0,
                        del_operador: Iterable[str] = ()) -> dict[str, Any]:
    """Si el dato de cada fija es plausible, antes del primer flujo (015:RF-73, 006:RF-47).

    ``fijas``: SED → :class:`Fija`; ``p_base_escaladas``: la P base de las escaladas (kVA × FP), con la que sale el
    factor inicial; ``kva_grupo``: los kVA de la SED y sus hermanas en la fuente, sin variaciones (015:RF-75);
    ``evidencia``: cliente → ``{'supera_cabecera': {'registros', 'exceso_max_kw', 'fecha'}}`` de su curva del mes frente
    a la de su cabecera. Una fija queda a revisar si (a) su cliente mide más que su cabecera en algún registro, (b) pide
    más de :data:`VECES_KVA_GRUPO_DUDOSA` veces los kVA de su grupo cuando su media del mes sí cabe, o (c) las fijas
    pasan de :data:`FRACCION_FIJAS_DUDOSA` de la cabecera y dejan el factor inicial bajo :data:`FACTOR_ESCALADAS_ANORMAL`
    (la que más pesa). Si la media del mes no cabe en los kVA del grupo, el dudoso es el kVA: se anota y no para.
    ``otras_fijas_kw``: las fijas del operador (cambios manuales, demandas medidas), que cuentan en (c) y no se dudan.
    """
    evid = {clave_codigo(k): v for k, v in (evidencia or {}).items()}
    # 039:RF-29: los clientes que el operador marcó «a su máxima» en la tabla cruzada son su decisión: no se liberan.
    marcados = {clave_codigo(c) for c in del_operador}
    filas: list[dict[str, Any]] = []
    for sed, f in sorted(fijas.items()):
        motivos: list[dict[str, Any]] = []
        for c in f.clientes:
            sup = (evid.get(clave_codigo(c)) or {}).get('supera_cabecera') or {}
            n = int(numero(sup.get('registros')) or 0)
            if n > 0:
                exceso = numero(sup.get('exceso_max_kw'))
                diag = (evid.get(clave_codigo(c)) or {}).get('diagnostico') or {}
                motivos.append({'codigo': 'SUPERA_LA_CABECERA', 'cliente': c, 'registros': n, 'exceso_max_kw': exceso,
                                'fecha': sup.get('fecha'), 'diagnostico': diag or None,
                                'texto': f'{c} mide más que su cabecera en {n} registro' + ('s' if n > 1 else '')
                                         + (f', hasta {exceso:,.0f} kW' if exceso is not None else '')
                                         + (f" (hipótesis: {diag['hipotesis']})" if diag.get('hipotesis') else
                                            f" (se propone reasignarlo a {diag['alimentador']})"
                                            if diag.get('alimentador') else '')})
        kg = (kva_grupo or {}).get(sed)
        energias = [e for e in (numero(d.get('ea')) for d in f.derivaciones) if e is not None]
        pmed = sum(energias) / horas_mes if energias and horas_mes else None
        s = math.hypot(f.kw, f.kvar)
        fila: dict[str, Any] = {'sed': sed, 'clientes': list(f.clientes), 'p_kw': f.kw, 'kva_carga': s,
                                'kva_grupo': kg, 'p_media_kw': pmed}
        if kg and pmed is not None and pmed > kg:
            fila['kva_fuente_incoherente'] = {'codigo': KVA_FUENTE_INCOHERENTE, 'p_media_kw': pmed, 'kva_grupo': kg}
        elif kg and s > VECES_KVA_GRUPO_DUDOSA * kg:
            motivos.append({'codigo': 'SUPERA_SU_GRUPO', 'kva_carga': s, 'kva_grupo': kg,
                            'texto': f'pide {s:,.0f} kVA con {kg:,.0f} kVA en su grupo'})
        fila['motivos'] = motivos
        filas.append(fila)
    p_fijas = sum(f.kw for f in fijas.values()) + otras_fijas_kw
    fraccion = p_fijas / objetivo.kw if objetivo.kw else None
    factor = (objetivo.kw - p_fijas) / p_base_escaladas if p_base_escaladas > 0 else None
    if (filas and fraccion is not None and fraccion > FRACCION_FIJAS_DUDOSA and factor is not None
            and 0 < factor < FACTOR_ESCALADAS_ANORMAL):
        mayor = max(filas, key=lambda x: (x['p_kw'], x['sed']))
    else:
        mayor = None
    if mayor is not None and mayor['p_kw'] > otras_fijas_kw:
        mayor['motivos'].append({'codigo': 'FIJAS_DEJAN_SIN_ESCALADAS', 'fraccion_fijas': fraccion, 'factor': factor,
                                 'texto': f'las fijas son el {fraccion:.0%} de la cabecera y dejan a las escaladas '
                                          f'con {factor:.3f} de su potencia'})
    for x in filas:
        x['a_revisar'] = bool(x['motivos'])
        # 039:RF-25 (enmienda 015:RF-73): una fija físicamente imposible (mide más que su cabecera, o pide más de cuatro
        # veces su grupo con la media del mes que sí cabe) se libera: su SED va con las escaladas y el alimentador se
        # calibra con el resto. Solo dudosa por el reparto (FIJAS_DEJAN_SIN_ESCALADAS), queda con su medida y se avisa.
        del_op = any(clave_codigo(c) in marcados for c in x['clientes'])                    # 039:RF-29
        x['liberar'] = not del_op and any(m['codigo'] in MOTIVOS_QUE_LIBERAN and not se_queda_fija(m)
                                          for m in x['motivos'])
        if not x['liberar'] and (del_op or any(se_queda_fija(m) for m in x['motivos'])):
            x['queda_fija'] = True                                                     # 039:RF-28, RF-29
            x['marcada_por_el_operador'] = del_op
    revisar = [x for x in filas if x['a_revisar']]
    liberadas = [x['sed'] for x in revisar if x['liberar']]
    clave = objetivo.alimentador or objetivo.medidor or 'El alimentador'
    texto = None
    if revisar:
        texto = (f'{clave}: ' + ('una fija a revisar' if len(revisar) == 1 else f'{len(revisar)} fijas a revisar')
                 + ': ' + '; '.join(f"{x['sed']} ({', '.join(m['texto'] for m in x['motivos'])})" for x in revisar)
                 + '. ' + (f"{', '.join(liberadas)} se {'reparte' if len(liberadas) == 1 else 'reparten'} con las "
                           'escaladas por su potencia instalada' if liberadas else
                           'Queda con su medida: el operador la marcó a su máxima' if any(
                               x.get('marcada_por_el_operador') for x in revisar) else
                           'Queda con su medida: pasa su cabecera solo en pocos registros' if any(
                               x.get('queda_fija') for x in revisar) else
                           'Queda con su medida')
                 + ' y el alimentador se calibra con el resto.')
    return {'estado': FIJA_A_REVISAR if revisar else None, 'clave': clave, 'fijas': filas,
            'a_revisar': [x['sed'] for x in revisar], 'liberadas': liberadas,
            'kva_fuente_incoherente': [x['sed'] for x in filas if x.get('kva_fuente_incoherente')],
            'fijas_kw': p_fijas, 'objetivo_kw': objetivo.kw, 'fraccion_fijas': fraccion, 'factor_inicial': factor,
            'texto': texto}


def cliente_supera_cabecera(cliente: Iterable[tuple[Any, float, Any]],
                            cabecera: Iterable[tuple[Any, float, Any]]) -> dict[str, Any] | None:
    """Los registros en que un cliente mide más que la cabecera de su alimentador, con ella > 0 (015:RF-73 a).

    Las curvas son ``(fecha, kW, kVAR)`` de 15 minutos. Es físicamente imposible: el cliente cuelga de ese alimentador.
    ``None`` si no hay ninguno o no coincide ningún registro.
    """
    cab = {t: kw for t, kw, *_resto in cabecera if kw is not None and kw > 0}
    excesos = [(kw - cab[t], t) for t, kw, *_resto in cliente if t in cab and kw is not None and kw > cab[t]]
    if not excesos:
        return None
    mayor, cuando = max(excesos, key=lambda x: x[0])
    return {'registros': len(excesos), 'exceso_max_kw': mayor,
            'fecha': cuando.isoformat(sep=' ') if hasattr(cuando, 'isoformat') else str(cuando)}


# =========================================================================== diagnóstico de una fija imposible
#: 039:RF-24: las causas que se buscan, en este orden, antes de dar una fija por imposible.
CAUSA_FM = 'FM_CAMBIADO'
CAUSA_REGISTROS = 'REGISTROS_AISLADOS'
CAUSA_OTRO_ALIMENTADOR = 'OTRO_ALIMENTADOR'
CAUSA_HIPOTESIS = 'HIPOTESIS'
#: 039:RF-24 (b): el filtro de Hampel (Hampel, 1974; Pearson, 2002): mediana de ``HAMPEL_VENTANA`` registros a cada lado
#: y atípico si se aparta más de ``HAMPEL_UMBRAL`` veces 1,4826 × la desviación absoluta mediana. Es la versión local del
#: residuo normalizado mayor de la estimación de estado: un registro aislado, no una tendencia.
HAMPEL_VENTANA = 4
HAMPEL_UMBRAL = 3.5
#: 039:RF-24 (b): como mucho esta fracción de los registros del mes, o este número, para que sean datos malos.
FRACCION_REGISTROS_AISLADOS = 0.01
REGISTROS_AISLADOS_MIN = 4
#: 039:RF-24 (a): la cabecera es estable si su energía del mismo par de días cambia menos que esto (± 20 %).
TOLERANCIA_CABECERA_ESTABLE = 0.2


def _mediana(valores: list[float]) -> float:
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def registros_atipicos(curva: Iterable[tuple[Any, float, Any]], *, ventana: int = HAMPEL_VENTANA,
                       umbral: float = HAMPEL_UMBRAL) -> dict[Any, float]:
    """039:RF-24 (b): fecha → la mediana local que reemplaza a cada registro atípico de una curva de 15 minutos.

    Filtro de Hampel: ventana de ``2·ventana + 1`` registros; la escala es 1,4826 × MAD, con un suelo del 2 % de la
    mediana para que una curva plana no dé por atípico cualquier decimal.
    """
    serie = sorted((t, kw) for t, kw, *_resto in curva if kw is not None)
    valores = [kw for _t, kw in serie]
    out: dict[Any, float] = {}
    for i, (t, kw) in enumerate(serie):
        trozo = valores[max(0, i - ventana):i + ventana + 1]
        if len(trozo) < 3:
            continue
        med = _mediana(trozo)
        escala = max(1.4826 * _mediana([abs(v - med) for v in trozo]), 0.02 * abs(med), 1e-9)
        if abs(kw - med) > umbral * escala:
            out[t] = med
    return out


def _dia_de(t: Any) -> str:
    return (t.date().isoformat() if hasattr(t, 'date') else str(t))[:10]


def _energia_del_dia(curva: Iterable[tuple[Any, float, Any]], dia: str) -> float | None:
    """La energía (kWh) de un día ``AAAA-MM-DD`` completo de una curva de 15 minutos (con al menos el 90 % de los
    registros de su día más lleno), o ``None``."""
    por_dia: dict[str, list[float]] = {}
    for t, kw, *_r in curva:
        if kw is not None:
            por_dia.setdefault(_dia_de(t), []).append(kw)
    lleno = max((len(v) for v in por_dia.values()), default=0)
    kws = por_dia.get(dia) or []
    return sum(kws) / 4.0 if kws and len(kws) >= 0.9 * lleno else None


def cabecera_estable(cabecera: Iterable[tuple[Any, float, Any]], cambio_fm: Mapping[str, Any], *,
                     tolerancia: float = TOLERANCIA_CABECERA_ESTABLE) -> dict[str, Any]:
    """039:RF-24 (a): si la cabecera no salta con el cambio de FM del cliente, en los mismos dos días.

    ``estable``: ``True`` si su energía cambia menos de ``tolerancia`` y menos de la mitad del salto del FM (en
    logaritmos); ``False`` si salta; ``None`` si la curva de cabecera no tiene los dos días completos.
    """
    curva = list(cabecera)
    antes = _energia_del_dia(curva, str(cambio_fm.get('dia_anterior') or ''))
    ahora = _energia_del_dia(curva, str(cambio_fm.get('dia') or ''))
    if not antes or ahora is None or antes <= 0 or ahora <= 0:
        return {'estable': None, 'kwh_anterior': antes, 'kwh': ahora}
    razon = ahora / antes
    razon_fm = numero(cambio_fm.get('razon_fm')) or 1.0
    estable = (abs(math.log(razon)) <= math.log1p(tolerancia)
               and abs(math.log(razon)) < 0.5 * abs(math.log(razon_fm)))
    return {'estable': estable, 'kwh_anterior': antes, 'kwh': ahora, 'razon': razon}


def _fecha_texto(t: Any) -> str:
    return t.isoformat(sep=' ') if hasattr(t, 'isoformat') else str(t)


def diagnostico_fija_imposible(codigo: str, cliente: Iterable[tuple[Any, float, Any]],
                               cabecera: Iterable[tuple[Any, float, Any]], *,
                               cambio_fm: Mapping[str, Any] | None = None,
                               vecinas: Mapping[str, Iterable[tuple[Any, float, Any]]] | None = None) -> dict | None:
    """039:RF-24: por qué un cliente mide más que su cabecera y qué se hace, antes de parar; ``None`` si cabe.

    Orden: (a) el FM cambió entre libros con un salto de energía igual a su razón (004:RF-111), la cabecera no saltó y
    con el FM anterior el cliente cabe → ``corregir_factor``; (b) los registros que pasan son pocos y atípicos en el
    cliente o en la cabecera (Hampel) → ``excluir_registros``; (c) cabe en la cabecera de otro alimentador del mismo
    trabajo (la misma SET o sistema) → ``proponer_reasignacion``; (d) nada lo explica → ``liberar_fija`` con la
    hipótesis más probable y sus cifras. Nunca «no puede cuadrar» a secas: usuario, 21-11-2026; un cliente real pasó de
    FM 545,4545 a 1818,1818 sin cambio en la cabecera y su alimentador paraba antes del primer flujo.
    """
    cliente, cabecera = list(cliente), list(cabecera)
    exceso = cliente_supera_cabecera(cliente, cabecera)
    if exceso is None:
        return None
    cab = {t: kw for t, kw, *_r in cabecera if kw is not None and kw > 0}
    pasan = sorted((t, kw, cab[t]) for t, kw, *_r in cliente if t in cab and kw is not None and kw > cab[t])
    n, hasta = exceso['registros'], exceso['exceso_max_kw']
    base = {'cliente': codigo, 'registros': n, 'exceso_max_kw': hasta, 'fecha': exceso['fecha']}
    regs = f"{n} registro{'s' if n > 1 else ''} (hasta {hasta:,.0f} kW)"
    # (a) cambio del factor del medidor (FM)
    factor = numero((cambio_fm or {}).get('factor_propuesto'))
    if cambio_fm and factor and factor > 0:
        estable = cabecera_estable(cabecera, cambio_fm)
        corregida = [(t, kw * factor, None if not r or r[0] is None else r[0] * factor) for t, kw, *r in cliente
                     if kw is not None]
        if estable['estable'] is not False and cliente_supera_cabecera(corregida, cabecera) is None:
            salto = numero(cambio_fm.get('salto_energia')) or 0.0
            return {**base, 'causa': CAUSA_FM, 'accion': 'corregir_factor', 'factor': factor,
                    'cabecera': estable, 'cambio_fm': dict(cambio_fm),
                    'texto': (f"{codigo}: mide más que su cabecera en {regs} porque su FM pasó de "
                              f"{numero(cambio_fm.get('fm_anterior')) or 0:g} a {numero(cambio_fm.get('fm_actual')) or 0:g}"
                              f" con su energía ×{salto:.2f}"
                              + (f" y la cabecera ×{estable['razon']:.2f}" if estable.get('razon') else '')
                              + f"; con el FM anterior (×{factor:.4f}) cabe: corrección automática.")}
    # (b) registros aislados: datos malos del cliente o de la cabecera
    at_cli, at_cab = registros_atipicos(cliente), registros_atipicos(cabecera)
    limite = max(REGISTROS_AISLADOS_MIN, int(FRACCION_REGISTROS_AISLADOS * len(cliente)))
    if len(pasan) <= limite and all(t in at_cli or t in at_cab for t, _kw, _c in pasan):
        excluidos = [{'fecha': _fecha_texto(t), 'kw': kw, 'cabecera_kw': c,
                      'de': 'cliente' if t in at_cli else 'cabecera',
                      'reemplazo_kw': at_cli[t] if t in at_cli else at_cab[t]} for t, kw, c in pasan]
        return {**base, 'causa': CAUSA_REGISTROS, 'accion': 'excluir_registros', 'excluidos': excluidos,
                'texto': (f"{codigo}: mide más que su cabecera en {regs} aislados (filtro de Hampel): son datos "
                          'malos y se excluyen; el resto de su curva cabe.')}
    # (c) otro alimentador de la misma SET o del mismo sistema
    mejor = None
    for nombre, curva in sorted((vecinas or {}).items()):
        otra = {t: kw for t, kw, *_r in curva if kw is not None and kw > 0}
        comunes = [(kw, otra[t]) for t, kw, *_r in cliente if t in otra and kw is not None]
        if not comunes or len(comunes) < 0.5 * len(cliente) or any(kw > c for kw, c in comunes):
            continue
        margen = min(c - kw for kw, c in comunes)
        if mejor is None or margen > mejor[1]:
            mejor = (nombre, margen)
    if mejor is not None:
        return {**base, 'causa': CAUSA_OTRO_ALIMENTADOR, 'accion': 'proponer_reasignacion', 'alimentador': mejor[0],
                'margen_min_kw': mejor[1],
                'texto': (f"{codigo}: mide más que su cabecera en {regs} y cabe siempre en la de {mejor[0]} (margen "
                          f"mínimo {mejor[1]:,.0f} kW): se propone reasignarlo a {mejor[0]}; mientras, su SED se "
                          'reparte con las escaladas.')}
    # (d) la hipótesis más probable, con sus números
    cabria = min(c / kw for _t, kw, c in pasan)
    e_cli = sum(kw for t, kw, *_r in cliente if t in cab and kw is not None)
    e_cab = sum(cab[t] for t, kw, *_r in cliente if t in cab and kw is not None)
    fraccion = e_cli / e_cab if e_cab else None
    if len(pasan) > limite:
        hipotesis = (f'el factor del medidor del cliente o la relación de su TC no es la del libro: con ×{cabria:.3f} '
                     'cabría siempre')
    else:
        hipotesis = ('la cabecera no midió toda la carga en esos registros (transferencia o corte de su medidor) o el '
                     f'cliente tuvo un pico real: con ×{cabria:.3f} cabría')
    return {**base, 'causa': CAUSA_HIPOTESIS, 'accion': 'liberar_fija', 'factor_que_cabria': cabria,
            'fraccion_energia': fraccion, 'hipotesis': hipotesis, 'pocos_registros': len(pasan) <= limite,   # 039:RF-28
            'texto': (f"{codigo}: mide más que su cabecera en {regs}"
                      + (f"; su energía es el {fraccion:.0%} de la de su cabecera" if fraccion is not None else '')
                      + f"; hipótesis más probable: {hipotesis}. Su SED se reparte con las escaladas y el resto del "
                        'alimentador se calibra.')}


# =========================================================================== cuadre
@dataclass(frozen=True)
class Medida:
    """Lo que entra por la cabecera en un flujo de carga; sin valores si no converge."""

    converge: bool
    kw: float | None = None
    kvar: float | None = None
    motivo: str = ''
    carga_kw: float | None = None       # consumo efectivo nativo de las cargas
    carga_kvar: float | None = None


#: Remedios de RF-16, por orden. El primero no toca el flujo de carga: se acerca al
#: objetivo desde el último reparto que convergió. Los demás son ajustes del ``ComLdf``;
#: ``('x', n)`` multiplica el valor que tenga. Son datos para que el informe diga qué
#: cambió (RF-17) y el guion los deshaga al final.
ESCALERA: tuple[tuple[str, dict[str, Any]], ...] = (
    ('acercarse en pasos', {}),
    ('más iteraciones', {'itrlx': ('x', 3)}),
    ('paso automático', {'iStepAdapt': 1}),
    # 015:RF-42: las cargas son PQ; no se activa su dependencia de la tensión (iopt_pq).
    ('adaptación automática del modelo', {'iopt_lev': 1}),
)
#: Flujos que no convergen con cada remedio antes de pasar al siguiente; con cada uno se
#: parte el paso a la mitad.
MITADES = 4
#: Flujos de carga como mucho: 3 a 5 bastan si converge; los remedios piden más.
MAX_FLUJOS = 30


@dataclass
class Cuadre:
    """Resultado del cuadre: el último reparto que convergió y cómo se llegó a él."""

    cuadrado: bool
    reparto: Reparto | None              # el último que convergió (RF-18)
    medida: Medida | None                # su cabecera
    objetivo: Objetivo
    tolerancia: float
    flujos: int = 0
    remedios: list[dict[str, Any]] = field(default_factory=list)
    historial: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    motivo: str = ''
    cancelado: bool = False
    con_q: bool = False                  # 035:RF-5: también la Q de cabecera
    q_estado: str | None = None          # Q_CUADRADA, Q_INCOHERENTE_* o Q_SIN_BASE
    q_extremo: dict[str, Any] | None = None   # 035:RF-30: el flujo que lo demostró
    imposible: dict[str, Any] | None = None   # 086:RF-124: por qué no puede cuadrar (fijas, pérdidas, SED que más pesa)
    no_calibrable: dict[str, Any] | None = None   # 006:RF-46: sin escaladas con kVA, no se puede repartir
    metodos: dict[str, int] = field(default_factory=dict)       # 083:RF-13
    fijas_sospechosas: bool = False                              # 083:RF-7

    def errores(self) -> tuple[float | None, float | None]:
        """Error relativo de kW y kVAR en la cabecera, con signo (medido − objetivo)."""
        m = self.medida
        if m is None or not m.converge or m.kw is None:
            return None, None
        q_error = (None if m.kvar is None else
                   _rel(m.kvar, self.objetivo.kvar, self.objetivo.kw))
        return _rel(m.kw, self.objetivo.kw), q_error

    def perdidas(self) -> tuple[float | None, float | None]:
        """Lo que entra por la cabecera menos lo que consumen las SED."""
        m = self.medida
        if self.reparto is None or m is None or m.kw is None or m.kvar is None:
            return None, None
        nominal_p, nominal_q = self.reparto.totales()
        p = nominal_p if m.carga_kw is None else m.carga_kw
        q = nominal_q if m.carga_kvar is None else m.carga_kvar
        return m.kw - p, m.kvar - q


def _rel(medido: float, objetivo: float, respaldo: float | None = None) -> float:
    # Un objetivo de kVAR casi nulo haría enorme cualquier error: se mide contra el kW.
    den = abs(objetivo) if abs(objetivo) > 1e-9 else abs(respaldo or 1.0)
    return (medido - objetivo) / den


def cuadrado_kw(medida: Medida, objetivo: Objetivo, tolerancia: float) -> bool:
    """Aceptación universal: flujo convergente y kW dentro de tolerancia.

    El kVAR es un resultado físico de la red nativa —incluidos sus bancos— y se informa
    por separado; nunca decide si el ajuste puede continuar.
    """
    return bool(
        medida.converge and medida.kw is not None
        and abs(_rel(medida.kw, objetivo.kw)) <= tolerancia
    )


def kvar_difference(medida: Medida, objetivo: Objetivo, tolerancia: float) -> dict[str, Any]:
    """Diferencia reactiva informativa, completa y explícitamente no bloqueante."""
    native = medida.kvar if medida.converge else None
    if native is None:
        return {
            'status': 'AVISO_KVAR', 'objetivo_kvar': objetivo.kvar,
            'red_nativa_kvar': None, 'diferencia_kvar': None,
            'diferencia_relativa': None, 'tolerancia': tolerancia,
            'supera_tolerancia': True, 'bloquea': False,
        }
    difference = native - objetivo.kvar
    relative = _rel(native, objetivo.kvar, objetivo.kw)
    exceeded = abs(relative) > tolerancia
    return {
        'status': 'AVISO_KVAR' if exceeded else 'OK',
        'objetivo_kvar': objetivo.kvar,
        'red_nativa_kvar': native,
        'diferencia_kvar': difference,
        'diferencia_relativa': relative,
        'tolerancia': tolerancia,
        'supera_tolerancia': exceeded,
        'bloquea': False,
    }


#: Cómo quedó la Q de cabecera cuando se cuadra (035:RF-5, RF-9, RF-28 a RF-30). Una medida
#: es incoherente si ni con las escaladas en un extremo de su FP la cabecera la alcanza: por
#: encima con FP 1 (le haría falta reactiva negativa) o por debajo con su FP mínimo.
Q_CUADRADA, Q_SIN_BASE = 'CUADRADA', 'SIN_BASE'
Q_INCOHERENTE_ALTA, Q_INCOHERENTE_BAJA = 'MEDIDA_INCOHERENTE_ALTA', 'MEDIDA_INCOHERENTE_BAJA'
Q_INCOHERENTES = (Q_INCOHERENTE_ALTA, Q_INCOHERENTE_BAJA)
#: Precisión de la Q de cabecera al recalibrar (035:RF-25). El usuario, el 2026-10-29, primero
#: «± 2 %» y después «la precisión debe ser 1 %».
TOLERANCIA_Q = 0.01


def cuadrado_kvar(kvar: float | None, objetivo: Objetivo, tolerancia: float = TOLERANCIA_Q) -> bool:
    """La Q de cabecera dentro de la tolerancia, medida como el aviso de kVAR (RF-14)."""
    return kvar is not None and abs(_rel(kvar, objetivo.kvar, objetivo.kw)) <= tolerancia


def _paso_q(rep: Reparto, kvar: float, objetivo: Objetivo, puntos: list[tuple[float, float]],
            b_maximo: float, tolerancia: float = TOLERANCIA_Q) -> tuple[float | None, str | None]:
    """El siguiente factor de Q de las escaladas o por qué la medida no es coherente (035:RF-6).

    La Q de las fijas es la de su registro y los bancos son la red: lo único libre es la Q de
    las escaladas, con su FP entre 1 (factor 0) y su mínimo (``b_maximo``). Solo un flujo en
    el extremo decide que la medida no se alcanza (035:RF-28). El usuario, el 2026-10-31:
    «las mediciones en cabecera que no sean coherentes como de NA293» quedan con la Q real de
    DIgSILENT, y «en las que sí tienen coherencia se debe hacer cuadre». NA293 daba 3 447 kvar
    con las escaladas a FP 1 frente a 1 711 medidos: le hacía falta reactiva negativa, y una
    escalada con reactiva negativa no es una carga.
    """
    bq = sum(q for _, q in rep.base.values())
    if bq <= 0:
        return None, Q_SIN_BASE                                         # RF-9
    fuera = not cuadrado_kvar(kvar, objetivo, tolerancia)
    if fuera and kvar > objetivo.kvar and rep.b <= 1e-12:
        return None, Q_INCOHERENTE_ALTA                                 # RF-28
    if fuera and kvar < objetivo.kvar and rep.b >= b_maximo * (1 - 1e-9):
        return None, Q_INCOHERENTE_BAJA                                 # RF-28
    puntos.append((rep.b, kvar))
    return min(b_maximo, max(0.0, _siguiente(rep.b, kvar, objetivo.kvar, puntos, bq))), None


def _extremo_q(rep: Reparto, kvar: float, estado: str) -> dict[str, Any]:
    """El flujo que demostró que la medida no es coherente, para el informe (035:RF-30)."""
    return {'estado': estado, 'fp_escaladas': rep.fp_escaladas() if rep.b > 0 else 1.0,
            'factor_q': rep.b, 'cabecera_kvar': kvar}


def cuadrado(medida: Medida, objetivo: Objetivo, tolerancia: float,
             solo_kw: bool = True) -> bool:
    """Compatibilidad del API histórico; ``solo_kw`` ya no cambia la aceptación."""
    del solo_kw
    return cuadrado_kw(medida, objetivo, tolerancia)


#: Cuánto queda de las escaladas al probar «casi en cero» (083:RF-7).
FACTOR_CASI_CERO = 1e-3
#: Por debajo de esta fracción de su factor inicial, las escaladas ya no pueden bajar más; y lo que se
#: corrige de las fijas como mucho: más que eso no es incoherencia de medida, es un dato mal (083:RF-30).
ESCALADAS_AL_MINIMO = 0.05
TOPE_CORRECCION_FIJAS = 0.10
#: El error conjunto que no baja de esta fracción del de dos flujos antes es oscilación (083:RF-12).
SIN_MEJORA = 0.9


def _acotar(a: float, puntos: list[tuple[float, float]], objetivo: float) -> tuple[float, bool]:
    """El factor dentro del intervalo donde ya se sabe que está la solución (083:RF-11); ``True`` si hubo que corregirlo."""
    debajo = [x for x, y in puntos if y < objetivo]
    encima = [x for x, y in puntos if y > objetivo]
    if debajo and encima:
        lo, hi = max(debajo), min(encima)
        if lo < hi and not lo < a < hi:
            return (lo + hi) / 2, True
    return a, False


class _Broyden:
    """Paso conjunto que aprende cómo un alimentador afecta a otro (083:RF-12); sin dependencias, con pocas claves."""

    def __init__(self, claves: tuple[str, ...], pendiente: Mapping[str, float]) -> None:
        self.claves = claves
        self.b = [[float(pendiente[k]) if i == j else 0.0 for j in range(len(claves))] for i, k in enumerate(claves)]
        self.x: list[float] | None = None
        self.y: list[float] | None = None

    def actualizar(self, x: list[float], y: list[float]) -> None:
        if self.x is not None and self.y is not None:
            dx = [p - q for p, q in zip_estricto(x, self.x)]
            dy = [p - q for p, q in zip_estricto(y, self.y)]
            nn = sum(v * v for v in dx)
            if nn > 1e-24:
                prod = [sum(f * v for f, v in zip_estricto(fila, dx)) for fila in self.b]
                for i, fila in enumerate(self.b):
                    for j in range(len(fila)):
                        fila[j] += (dy[i] - prod[i]) * dx[j] / nn
        self.x, self.y = x, y

    def paso(self, residuo: list[float]) -> list[float] | None:
        """El incremento de los factores, por eliminación con pivote; ``None`` si la matriz no sirve."""
        n = len(residuo)
        m = [list(f) + [r] for f, r in zip_estricto(self.b, residuo)]
        for c in range(n):
            p = max(range(c, n), key=lambda i: abs(m[i][c]))
            if abs(m[p][c]) < 1e-12:
                return None
            m[c], m[p] = m[p], m[c]
            for i in range(n):
                if i != c:
                    f = m[i][c] / m[c][c]
                    for j in range(c, n + 1):
                        m[i][j] -= f * m[c][j]
        return [m[i][n] / m[i][i] for i in range(n)]


def _siguiente(x: float, y: float, objetivo: float, puntos: list[tuple[float, float]],
               pendiente: float) -> float:
    """Secante con los dos últimos puntos que convergieron; sin dos, la pendiente sin
    pérdidas (lo que suben las SED que escalan por unidad de factor)."""
    if len(puntos) >= 2:
        (x0, y0), (x1, y1) = puntos[-2], puntos[-1]
        if abs(y1 - y0) > 1e-12 and abs(x1 - x0) > 1e-15:
            pendiente = (y1 - y0) / (x1 - x0)
    return x + (objetivo - y) / pendiente if pendiente else x


def cuadrar(
    reparto: Reparto,
    objetivo: Objetivo,
    flujo: Callable[[Reparto], Medida],
    *,
    tolerancia: float = 0.01,
    max_flujos: int = MAX_FLUJOS,
    remedio: Callable[[str, dict[str, Any]], list[str]] = lambda nombre, ajustes: [],
    cancelado: Callable[[], bool] = lambda: False,
    progreso: Callable[[int, int, str], None] = lambda n, maximo, texto: None,
    con_q: bool = False,
    tolerancia_q: float = TOLERANCIA_Q,
    fp_minimo_escaladas: float | None = None,
    factor_inicial: float | None = None,
) -> Cuadre:
    """Ajusta los factores del reparto hasta que la cabecera dé el objetivo (RF-11, RF-12).

    086:RF-124: como en :func:`cuadrar_conjunto`, con las escaladas al mínimo (contra ``factor_inicial``, el de antes del
    oráculo) un exceso pequeño se corrige en las fijas (083:RF-30) y uno mayor para el ajuste con su causa.

    ``flujo(reparto)`` escribe las demandas y ejecuta el flujo de carga. ``remedio(nombre,
    ajustes)`` aplica un remedio de :data:`ESCALERA` y dice qué cambió. Si no cuadra, el
    resultado lleva el último reparto que convergió, y el flujo queda ejecutado con él
    (RF-18, RF-22). Con ``con_q`` (bancos en servicio, 035:RF-5) también la Q de cabecera,
    moviendo solo la Q de las escaladas.
    """
    res = Cuadre(cuadrado=False, reparto=None, medida=None, objetivo=objetivo,
                 tolerancia=tolerancia, avisos=list(reparto.avisos), con_q=con_q)
    causa = reparto.causa or {}
    if causa.get('estado') == NO_CALIBRABLE:
        # 006:RF-46: sin escaladas con kVA no hay qué repartir; no se ejecuta ningún flujo ni se tocan las fijas.
        res.no_calibrable, res.motivo = causa, causa['texto']
        return res
    if causa.get('estado') == CALIBRACION_IMPOSIBLE:
        # 006:RF-46, 086:RF-124: las fijas ya llenan la cabecera. Un flujo con las fijas a escala 1 y las escaladas al
        # mínimo mide sus pérdidas para la causa; no se busca ningún factor.
        actual = reparto.con_factores(0.0, 0.0)
        m = flujo(actual)
        res.flujos = 1
        res.historial.append({'flujo': 1, 'a': 0.0, 'b': 0.0, 'converge': m.converge, 'kw': m.kw, 'kvar': m.kvar,
                              'carga_kw': m.carga_kw, 'carga_kvar': m.carga_kvar, 'motivo': m.motivo})
        medido = m.converge and m.kw is not None
        if medido:
            res.reparto, res.medida = actual, m
        res.imposible = causa_imposible(objetivo.alimentador or objetivo.medidor or 'el alimentador', actual,
                                        float(m.kw) if medido else actual.totales()[0],
                                        m.carga_kw if medido else None, objetivo.kw)
        res.fijas_sospechosas = True
        res.motivo = res.imposible['texto']
        return res
    #: 083:RF-34: el tope de 083:RF-30 se mide contra las fijas con que entró el cuadre, no contra las del momento.
    fijas_originales = sum(p for p, _q in reparto.fijas.values())
    puntos_p: list[tuple[float, float]] = []
    puntos_q: list[tuple[float, float]] = []
    if con_q:
        reparto = reparto.con_q()
    actual = meta = reparto      # meta: adonde se quería llegar cuando dejó de converger
    escalon = mitades = 0
    casi_cero = False
    ultimo_flujo: Reparto | None = None

    while res.flujos < max_flujos:
        if cancelado():
            res.cancelado, res.motivo = True, 'cancelado por el operador'
            break
        m = flujo(actual)
        res.flujos += 1
        ultimo_flujo = actual
        res.historial.append({'flujo': res.flujos, 'a': actual.a, 'b': actual.b,
                              'converge': m.converge, 'kw': m.kw, 'kvar': m.kvar,
                              'carga_kw': m.carga_kw, 'carga_kvar': m.carga_kvar,
                              'motivo': m.motivo})
        progreso(res.flujos, max_flujos, f'flujo {res.flujos}: ' + (
            f'{m.kw:,.1f} kW / {m.kvar:,.1f} kVAR en la cabecera'
            if m.converge and m.kw is not None and m.kvar is not None else 'no converge'))
        medido = m.converge and m.kw is not None
        if medido:
            res.reparto, res.medida = actual, m
        # 006:RF-22: la solicitud puede llegar durante el flujo que ya cumple.
        # Primero se conserva lo medido; no se acepta ni se inicia otro ajuste.
        if cancelado():
            res.cancelado, res.motivo = True, 'cancelado por el operador'
            break
        if medido:
            # ``mitades`` no vuelve a cero aquí: tras un medio camino que converge, la
            # secante vuelve a saltar al objetivo, y si allí no converge se repetía sin
            # llegar nunca a los remedios del flujo de carga.
            q_lista = (not con_q or res.q_estado is not None
                       or cuadrado_kvar(m.kvar, objetivo, tolerancia_q))
            if cuadrado_kw(m, objetivo, tolerancia) and q_lista:
                p_nominal, _q_nominal = actual.totales()
                p_cargas = p_nominal if m.carga_kw is None else m.carga_kw
                perdida_p = m.kw - p_cargas
                # Una red pasiva no puede entregar en su cabecera menos potencia activa
                # que el consumo efectivo de sus cargas (o el nominal, si el motor no da
                # resultados). CA191 llegó a aparentar -6.684 MW porque el ElmFeeder
                # medía solo una de sus dos troncales.
                # Se admite únicamente ruido numérico pequeño (0,01 % del objetivo).
                tolerancia_perdida = max(0.1, abs(objetivo.kw) * 1e-4)
                if perdida_p < -tolerancia_perdida:
                    res.motivo = (
                        f'pérdidas activas negativas ({perdida_p:,.1f} kW): la frontera '
                        'de medición puede estar omitiendo una troncal o parte de las cargas')
                    return res
                if con_q and res.q_estado is None:
                    res.q_estado = Q_CUADRADA
                res.cuadrado = True
                return res
            exceso = m.kw - objetivo.kw
            if (exceso > tolerancia * objetivo.kw
                    and actual.a <= ESCALADAS_AL_MINIMO * (factor_inicial if factor_inicial is not None else reparto.a)):
                suma_fijas = sum(p for p, _q in actual.fijas.values())
                if suma_fijas > 0 and exceso + (fijas_originales - suma_fijas) <= TOPE_CORRECCION_FIJAS * fijas_originales:
                    # 083:RF-30, también con un solo alimentador (086:RF-124).
                    factor = 1 - exceso / suma_fijas
                    actual = meta = replace(actual, fijas={s: (p * factor, q * factor) for s, (p, q) in actual.fijas.items()})
                    res.metodos['fijas_corregidas'] = res.metodos.get('fijas_corregidas', 0) + 1
                    puntos_p.clear()
                    continue
                # 086:RF-124: ni las escaladas ni las fijas lo bajan: se para con su causa.
                res.imposible = causa_imposible(objetivo.alimentador or objetivo.medidor or 'el alimentador', actual, float(m.kw), m.carga_kw, objetivo.kw)
                res.fijas_sospechosas = True
                res.motivo = res.imposible['texto']
                break
            puntos_p.append((actual.a, m.kw))
            a = _siguiente(actual.a, m.kw, objetivo.kw, puntos_p,
                           sum(p for p, _ in actual.base.values()))
            if a <= 0:
                # Las pérdidas y las fijas ya pasan del objetivo: no se cruza el cero de un salto.
                a = actual.a / 2
            a, acotado = _acotar(a, puntos_p, objetivo.kw)          # 083:RF-11
            res.metodos['acotados'] = res.metodos.get('acotados', 0) + int(acotado)
            # Sin bancos, la asignación inicial de Q se conserva y solo P se itera (RF-12); con
            # ellos, también la Q de las escaladas hasta la medida (035:RF-5, RF-6).
            b = None
            if con_q and res.q_estado is None and m.kvar is not None and not q_lista:
                b, res.q_estado = _paso_q(actual, m.kvar, objetivo, puntos_q,
                                          actual.factor_q_maximo(fp_minimo_escaladas), tolerancia_q)
                if res.q_estado in Q_INCOHERENTES:
                    # 035:RF-29: la Q, la que dé la red con las escaladas a su FP de perfil.
                    res.q_extremo = _extremo_q(actual, m.kvar, res.q_estado)
                    actual = actual.al_perfil()
            actual = meta = actual.con_factores(a, b)
            continue

        # 083:RF-7: sin ningún flujo bueno, primero las escaladas casi en cero. Si ni así, no son ellas.
        if res.reparto is None:
            if not casi_cero:
                if not res.remedios:
                    res.remedios.append({'remedio': ESCALERA[0][0], 'cambios': []})
                casi_cero = True
                actual = actual.con_factores(actual.a * FACTOR_CASI_CERO, actual.b * FACTOR_CASI_CERO)
                continue
            res.fijas_sospechosas = True
            mitades = MITADES
        # No converge: acercarse a medio camino desde el último reparto que convergió
        # (o desde cero, si ninguno ha convergido todavía), con el ajuste que haya.
        if mitades < MITADES:
            if not res.remedios:
                res.remedios.append({'remedio': ESCALERA[0][0], 'cambios': []})
            mitades += 1
            a0 = res.reparto.a if res.reparto is not None else 0.0
            b0 = res.reparto.b if res.reparto is not None else 0.0
            actual = actual.con_factores((a0 + actual.a) / 2, (b0 + actual.b) / 2)
            continue
        escalon += 1
        if escalon >= len(ESCALERA):
            break
        nombre, ajustes = ESCALERA[escalon]
        res.remedios.append({'remedio': nombre, 'cambios': list(remedio(nombre, ajustes))})
        mitades = 0
        casi_cero = False
        puntos_p.clear()           # 083:RF-11: otra red, otro intervalo
        actual = meta              # con el flujo más tolerante, otra vez a por el objetivo

    if not res.cuadrado and not res.motivo:
        res.motivo = (f'sin cuadrar al {tolerancia:.1%} tras {res.flujos} flujos'
                      if res.reparto is not None else
                      'el flujo de carga no converge con ningún reparto, ni con los remedios')
    if res.reparto is not None and ultimo_flujo is not res.reparto:
        # La red queda con el último reparto que convergió y con sus resultados (RF-18).
        res.medida = flujo(res.reparto)
    return res


# =========================================================================== dos zonas
@dataclass(frozen=True)
class ObjetivoZonas:
    """El objetivo de un alimentador con una central en su troncal (spec 021, RF-33).

    En NA295 la cabecera solo ve lo que entra desde la SET: con la central generando, 1 123
    kW de una demanda de 10 753 kW. Se calibra por zonas: aguas arriba de la central
    (cabecera + llegada) y aguas abajo (la salida), cada una con su factor de escala, y
    la central con la P y Q que medía en el mismo registro (RF-35).
    """

    arriba: Objetivo
    abajo: Objetivo
    generacion_kw: float
    generacion_kvar: float
    cabecera_kw: float | None = None
    cabecera_kvar: float | None = None
    alimentador: str = ''
    fecha: str | None = None


def objetivo_zonas_de(maxima: Mapping[str, Any]) -> ObjetivoZonas:
    """El objetivo desde la máxima con central de la web (``MaximaConCentral.to_dict``)."""
    alimentador = str(maxima.get('alimentador') or '')
    if maxima.get('error'):
        raise AjusteError(f'{alimentador}: sin máxima con central ({maxima["error"]}).')
    valores = {k: numero(maxima.get(k)) for k in (
        'arriba_kw', 'arriba_kvar', 'abajo_kw', 'abajo_kvar', 'generacion_kw', 'generacion_kvar',
        'cabecera_kw', 'cabecera_kvar')}
    for k in ('arriba_kw', 'abajo_kw', 'generacion_kw'):
        if valores[k] is None:
            raise AjusteError(f'{alimentador}: la máxima con central no trae {k}.')
    for k, nombre in (('arriba_kw', 'aguas arriba'), ('abajo_kw', 'aguas abajo')):
        if valores[k] <= 0:   # type: ignore[operator]
            raise AjusteError(f'{alimentador}: la zona {nombre} no tiene demanda en la máxima '
                              f'({valores[k]:,.1f} kW).')
    fecha = maxima.get('fecha')

    def zona(kw: str, kvar: str, nombre: str) -> Objetivo:
        return Objetivo(kw=valores[kw], kvar=valores[kvar] or 0.0,  # type: ignore[arg-type]
                        medidor=nombre, alimentador=alimentador, fecha=fecha)

    return ObjetivoZonas(
        arriba=zona('arriba_kw', 'arriba_kvar', 'aguas arriba de la central'),
        abajo=zona('abajo_kw', 'abajo_kvar', 'aguas abajo de la central'),
        generacion_kw=valores['generacion_kw'],  # type: ignore[arg-type]
        generacion_kvar=valores['generacion_kvar'] or 0.0,
        cabecera_kw=valores['cabecera_kw'], cabecera_kvar=valores['cabecera_kvar'],
        alimentador=alimentador, fecha=fecha)


@dataclass(frozen=True)
class MedidaZonas:
    """Lo que da el flujo en cada zona: aguas arriba, cabecera + llegada; aguas abajo, la
    salida de la central. La cabecera se informa frente a la medida (RF-44)."""

    converge: bool
    arriba_kw: float | None = None
    arriba_kvar: float | None = None
    abajo_kw: float | None = None
    abajo_kvar: float | None = None
    cabecera_kw: float | None = None
    cabecera_kvar: float | None = None
    motivo: str = ''


ZONAS = ('arriba', 'abajo')
NOMBRE_ZONA = {'arriba': 'aguas arriba', 'abajo': 'aguas abajo'}


@dataclass
class CuadreZonas:
    """Resultado del cuadre por zonas: los dos repartos que convergieron y su medida."""

    cuadrado: bool
    arriba: Reparto | None
    abajo: Reparto | None
    medida: MedidaZonas | None
    objetivo: ObjetivoZonas
    tolerancia: float
    flujos: int = 0
    remedios: list[dict[str, Any]] = field(default_factory=list)
    historial: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    motivo: str = ''
    cancelado: bool = False
    ajustables: tuple[str, ...] = ZONAS

    def resumen(self) -> dict[str, Any]:
        """Lo que va al informe de la calibración (021:RF-44)."""
        m, o = self.medida, self.objetivo
        return {
            'factor_arriba': self.arriba.a if self.arriba else None,
            'factor_abajo': self.abajo.a if self.abajo else None,
            'arriba_kw': m.arriba_kw if m else None, 'arriba_objetivo_kw': o.arriba.kw,
            'abajo_kw': m.abajo_kw if m else None, 'abajo_objetivo_kw': o.abajo.kw,
            'cabecera_calculada_kw': m.cabecera_kw if m else None,
            'cabecera_medida_kw': o.cabecera_kw,
            'generacion_kw': o.generacion_kw, 'generacion_kvar': o.generacion_kvar,
            'zonas_ajustadas': list(self.ajustables),
        }


def cuadrar_zonas(
    arriba: Reparto,
    abajo: Reparto,
    objetivo: ObjetivoZonas,
    flujo: Callable[[Reparto, Reparto], MedidaZonas],
    *,
    tolerancia: float = 0.01,
    max_flujos: int = MAX_FLUJOS,
    remedio: Callable[[str, dict[str, Any]], list[str]] = lambda nombre, ajustes: [],
    cancelado: Callable[[], bool] = lambda: False,
    progreso: Callable[[int, int, str], None] = lambda n, maximo, texto: None,
) -> CuadreZonas:
    """Ajusta el factor de cada zona hasta que dé su medida (021:RF-40, RF-41, RF-43).

    Es :func:`cuadrar_conjunto` con las dos zonas por claves. Una zona sin cargas escaladas
    no se puede ajustar: sus fijas quedan como están, se avisa y no decide el cuadre (RF-45).
    """
    repartos, quietas = preparar_zonas(arriba, abajo)
    medidas: list[MedidaZonas] = []

    def f(reps: Mapping[str, Reparto]) -> MedidaConjunta:
        m = flujo(reps['arriba'], reps['abajo'])
        medidas.append(m)
        return medida_de_zonas(m)

    def fila(reps: Mapping[str, Reparto], _m: MedidaConjunta) -> dict[str, Any]:
        mz = medidas[-1]
        return {'a_arriba': reps['arriba'].a, 'a_abajo': reps['abajo'].a,
                'arriba_kw': mz.arriba_kw, 'abajo_kw': mz.abajo_kw,
                'cabecera_kw': mz.cabecera_kw}

    res = cuadrar_conjunto(repartos, {'arriba': objetivo.arriba, 'abajo': objetivo.abajo}, f,
                           quietas=quietas, tolerancia=tolerancia, max_flujos=max_flujos,
                           remedio=remedio, cancelado=cancelado, progreso=progreso, fila=fila)
    reps = res.repartos or {}
    return CuadreZonas(
        cuadrado=res.cuadrado, arriba=reps.get('arriba'), abajo=reps.get('abajo'),
        medida=res.medida.extra if res.medida is not None else None, objetivo=objetivo,
        tolerancia=tolerancia, flujos=res.flujos, remedios=res.remedios,
        historial=res.historial,
        avisos=list(arriba.avisos) + list(abajo.avisos) + avisos_de_zonas(quietas),
        motivo=res.motivo.replace('sin cuadrar todos', 'sin cuadrar las dos zonas'),
        cancelado=res.cancelado, ajustables=res.ajustables)


def preparar_zonas(arriba: Reparto, abajo: Reparto) -> tuple[dict[str, Reparto], set[str]]:
    """Los repartos de las dos zonas y las que no se ajustan (021:RF-45).

    Una zona con solo clientes fijos: ``reparto_inicial`` la pasa a «escalar todo»
    (006:RF-13), pero en una zona eso movería las fijas. Factor 1: su P y Q.
    """
    repartos = {'arriba': arriba, 'abajo': abajo}
    quietas = set()
    for z, r in repartos.items():
        if r.origen and all(o == 'cliente' for o in r.origen.values()):
            repartos[z] = r.con_factores(1.0, 1.0)
            quietas.add(z)
    if len(quietas) == len(ZONAS):
        raise AjusteError('Ninguna de las dos zonas de la central tiene cargas que escalar.')
    return repartos, quietas


def avisos_de_zonas(quietas: Iterable[str]) -> list[str]:
    quietas = set(quietas)
    return [f'La zona {NOMBRE_ZONA[z]} de la central no tiene cargas escaladas: sus fijas '
            'quedan como están y no se puede ajustar.' for z in ZONAS if z in quietas]


def medida_de_zonas(m: MedidaZonas) -> MedidaConjunta:
    return MedidaConjunta(m.converge, kw={'arriba': m.arriba_kw, 'abajo': m.abajo_kw},
                          kvar={'arriba': m.arriba_kvar, 'abajo': m.abajo_kvar},
                          motivo=m.motivo, extra=m)


# =========================================================================== conjunto
@dataclass(frozen=True)
class MedidaConjunta:
    """Lo que da un flujo en cada clave: un alimentador o una zona de su central.

    ``carga_kw`` es el consumo efectivo de sus cargas, si el guion lo lee: con él se
    comprueba que las pérdidas no salgan negativas (como en :func:`cuadrar`). ``extra``
    guarda lo que el guion quiera del flujo (las medidas de cada alimentador).
    """

    converge: bool
    kw: Mapping[str, float | None] = field(default_factory=dict)
    kvar: Mapping[str, float | None] = field(default_factory=dict)
    motivo: str = ''
    carga_kw: Mapping[str, float | None] = field(default_factory=dict)
    extra: Any = None


@dataclass
class CuadreConjunto:
    """Resultado del cuadre conjunto: los repartos del último flujo común que convergió."""

    cuadrado: bool
    repartos: dict[str, Reparto] | None
    medida: MedidaConjunta | None
    objetivos: Mapping[str, Objetivo]
    tolerancia: float
    flujos: int = 0
    remedios: list[dict[str, Any]] = field(default_factory=list)
    historial: list[dict[str, Any]] = field(default_factory=list)
    motivo: str = ''
    cancelado: bool = False
    ajustables: tuple[str, ...] = ()
    q_estado: dict[str, str] = field(default_factory=dict)     # 035:RF-5, por clave con Q
    q_extremo: dict[str, dict[str, Any]] = field(default_factory=dict)   # 035:RF-30
    metodos: dict[str, int] = field(default_factory=dict)       # 083:RF-13
    fijas_sospechosas: bool = False                              # 083:RF-7
    #: 086:RF-124: las claves que no pueden cuadrar (escaladas al mínimo y fijas más pérdidas por encima de su medida),
    #: con su causa; las demás del proyecto siguen y se informan cada una con su estado.
    imposibles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def desvio(self, clave: str) -> float | None:
        """Error relativo de kW de una clave en el último flujo común que convergió."""
        m = self.medida
        if m is None or not m.converge or m.kw.get(clave) is None:
            return None
        return _rel(m.kw[clave], self.objetivos[clave].kw)  # type: ignore[arg-type]

    def cumple(self, clave: str) -> bool:
        """086:RF-124: si esa clave está en tolerancia en el último flujo común, aunque el proyecto no cuadre entero."""
        d = self.desvio(clave)
        return d is not None and abs(d) <= self.tolerancia


def cuadrar_conjunto(
    repartos: Mapping[str, Reparto],
    objetivos: Mapping[str, Objetivo],
    flujo: Callable[[Mapping[str, Reparto]], MedidaConjunta],
    *,
    quietas: Iterable[str] = (),
    tolerancia: float = 0.01,
    max_flujos: int = MAX_FLUJOS,
    remedio: Callable[[str, dict[str, Any]], list[str]] = lambda nombre, ajustes: [],
    cancelado: Callable[[], bool] = lambda: False,
    progreso: Callable[[int, int, str], None] = lambda n, maximo, texto: None,
    fila: Callable[[Mapping[str, Reparto], MedidaConjunta], dict[str, Any]] | None = None,
    con_q: Iterable[str] = (),
    tolerancia_q: float = TOLERANCIA_Q,
    fp_minimo_escaladas: float | None = None,
    factores_iniciales: Mapping[str, float] | None = None,
) -> CuadreConjunto:
    """Ajusta a la vez un factor por clave hasta que todas den su objetivo (021:RF-54 a RF-58).

    ``factores_iniciales`` son los de antes del arranque del oráculo (086:RF-124): «escaladas al mínimo» (083:RF-30) se
    mide contra ellos; contra el del oráculo, que ya puede ser casi cero, no se alcanzaba nunca. Una clave con las
    escaladas al mínimo y un exceso que no se corrige en sus fijas no puede cuadrar: se deja quieta con su causa y, si
    las demás ya cumplen, se para en vez de gastar los flujos.

    Las claves son los alimentadores de un proyecto, o las zonas de uno con central: en el
    proyecto de NA293 y NA295 (2026-10-17) se iba a calibrar uno y después el otro, y el
    usuario pidió calibrar por proyecto, todos en el mismo flujo. ``flujo(repartos)``
    escribe todas las demandas, ejecuta **un** flujo de carga y mide cada clave. Cada
    factor sigue su secante con la medida de su clave; solo cuadra cuando todas cumplen en
    el mismo flujo (RF-55). Si no converge, los pasos de :func:`cuadrar` para todas: medio
    camino desde el último flujo común que convergió y luego los remedios de
    :data:`ESCALERA`, una vez para el proyecto (RF-56). Una clave en ``quietas`` (una zona
    solo con clientes fijos, 021:RF-45) se escribe pero no se ajusta ni decide. Las de
    ``con_q`` (alimentadores con bancos en servicio, 035:RF-5) cuadran también su Q.
    """
    quietas = set(quietas)
    claves = tuple(repartos)
    # 006:RF-46, 086:RF-124: la clave cuyas fijas ya llenan su cabecera entra con las escaladas al mínimo y no se mueve.
    llenas = {k for k, r in repartos.items() if k not in quietas
              and (r.causa or {}).get('estado') == CALIBRACION_IMPOSIBLE}
    repartos = {k: (r.con_factores(0.0, 0.0) if k in llenas else r) for k, r in repartos.items()}
    pendiente = {k: (0.0 if k in quietas or k in llenas else sum(p for p, _ in r.base.values()))
                 for k, r in repartos.items()}
    ajustables = tuple(k for k in claves if pendiente[k] > 0)
    res = CuadreConjunto(cuadrado=False, repartos=None, medida=None, objetivos=objetivos,
                         tolerancia=tolerancia, ajustables=ajustables)
    if not ajustables and not llenas:
        raise AjusteError('Ninguno de los alimentadores tiene cargas que escalar.')
    originales = {k: sum(p for p, _q in r.fijas.values()) for k, r in repartos.items()}    # 083:RF-34
    puntos: dict[str, list[tuple[float, float]]] = {k: [] for k in claves}
    con_q = tuple(k for k in con_q if k in ajustables)
    puntos_q: dict[str, list[tuple[float, float]]] = {k: [] for k in con_q}
    actual = meta = {k: (r.con_q() if k in con_q else r) for k, r in repartos.items()}
    escalon = mitades = 0
    casi_cero = False
    errores: list[float] = []                      # 083:RF-12: el error conjunto de cada flujo bueno
    broyden = _Broyden(ajustables, pendiente)
    ultimo: dict[str, Reparto] | None = None
    while res.flujos < max_flujos:
        if cancelado():
            res.cancelado, res.motivo = True, 'cancelado por el operador'
            break
        m = flujo(actual)
        res.flujos += 1
        ultimo = actual
        res.historial.append({'flujo': res.flujos, 'converge': m.converge, 'motivo': m.motivo,
                              **(fila(actual, m) if fila else {
                                  'a': {k: r.a for k, r in actual.items()},
                                  'kw': dict(m.kw), 'kvar': dict(m.kvar)})})
        medido = m.converge and all(m.kw.get(k) is not None for k in ajustables)
        progreso(res.flujos, max_flujos, f'flujo {res.flujos}: ' + (
            ', '.join(f'{k} {m.kw[k]:,.1f} kW' for k in ajustables) if medido
            else 'no converge'))
        if medido:
            res.repartos, res.medida = dict(actual), m
            for k in sorted(llenas - set(res.imposibles)):
                # 006:RF-46: su causa con lo que da el flujo, sus fijas a escala 1 y sus pérdidas.
                kw_k = m.kw.get(k)
                res.imposibles[k] = causa_imposible(k, actual[k], float(kw_k) if kw_k is not None
                                                    else actual[k].totales()[0],
                                                    m.carga_kw.get(k) if kw_k is not None else None,
                                                    objetivos[k].kw)
                res.fijas_sospechosas = True
        # 021:RF-58: un flujo final común válido también puede recibirse cancelado.
        if cancelado():
            res.cancelado, res.motivo = True, 'cancelado por el operador'
            break
        if medido and not ajustables:
            res.motivo = 'sin cuadrar todos: ' + '; '.join(c['texto'] for c in res.imposibles.values())
            break
        if medido:
            q_listas = {k: k in res.q_estado or cuadrado_kvar(m.kvar.get(k), objetivos[k], tolerancia_q)
                        for k in con_q}
            if not llenas and all(abs(_rel(m.kw[k], objetivos[k].kw)) <= tolerancia  # type: ignore[arg-type]
                                  for k in ajustables) and all(q_listas.values()):
                negativas = [
                    f'{k} ({m.kw[k] - m.carga_kw[k]:,.1f} kW)'  # type: ignore[operator]
                    for k in ajustables if m.carga_kw.get(k) is not None
                    and m.kw[k] - m.carga_kw[k] < -max(0.1, abs(objetivos[k].kw) * 1e-4)]  # type: ignore[operator]
                if negativas:
                    # Como en :func:`cuadrar`: una red pasiva no entrega menos de lo que
                    # consumen sus cargas; la frontera de medición omite una troncal.
                    res.motivo = ('pérdidas activas negativas en ' + ', '.join(negativas)
                                  + ': la frontera de medición puede estar omitiendo una '
                                  'troncal o parte de las cargas')
                    return res
                for k in con_q:
                    res.q_estado.setdefault(k, Q_CUADRADA)
                res.cuadrado = True
                return res
            nuevo = dict(actual)
            errores.append(max(abs(_rel(m.kw[k], objetivos[k].kw)) for k in ajustables))  # type: ignore[arg-type]
            broyden.actualizar([actual[k].a for k in ajustables], [float(m.kw[k]) for k in ajustables])  # type: ignore[arg-type]
            oscila = len(ajustables) > 1 and len(errores) >= 3 and errores[-1] >= SIN_MEJORA * errores[-3]
            paso = broyden.paso([objetivos[k].kw - float(m.kw[k]) for k in ajustables]) if oscila else None  # type: ignore[arg-type]
            if paso is not None:
                res.metodos['broyden'] = res.metodos.get('broyden', 0) + 1
            for n_k, k in enumerate(ajustables):
                r, y = actual[k], m.kw[k]
                puntos[k].append((r.a, y))  # type: ignore[arg-type]
                if abs(_rel(y, objetivos[k].kw)) <= tolerancia and (k not in con_q or q_listas[k]):  # type: ignore[arg-type]
                    # 083:RF-10: el que ya cumple no se mueve: volver a calcularlo lo sacaba de tolerancia.
                    res.metodos['quietos'] = res.metodos.get('quietos', 0) + 1
                    continue
                # 083:RF-30: con las escaladas al mínimo, lo que sobra solo puede salir de las fijas.
                suma_fijas = sum(p for p, _q in r.fijas.values())
                exceso = float(y) - objetivos[k].kw
                inicial = float((factores_iniciales or {}).get(k, repartos[k].a))          # 086:RF-124
                al_minimo = r.a <= ESCALADAS_AL_MINIMO * inicial
                if (exceso > tolerancia * objetivos[k].kw and al_minimo and suma_fijas > 0     # 083:RF-34: contra las originales
                        and exceso + (originales[k] - suma_fijas) <= TOPE_CORRECCION_FIJAS * originales[k]):
                    factor = 1 - exceso / suma_fijas
                    nuevo[k] = replace(r, fijas={s: (p * factor, q * factor) for s, (p, q) in r.fijas.items()})
                    res.metodos['fijas_corregidas'] = res.metodos.get('fijas_corregidas', 0) + 1
                    puntos[k].clear()
                    continue
                if exceso > tolerancia * objetivos[k].kw and al_minimo:
                    # 086:RF-124: ni las escaladas ni la corrección de fijas lo bajan: no puede cuadrar. Se queda
                    # quieto con su causa y no mueve a los demás.
                    res.imposibles[k] = causa_imposible(k, r, float(y), m.carga_kw.get(k), objetivos[k].kw)
                    res.fijas_sospechosas = True
                    continue
                a = (r.a + paso[n_k]) if paso is not None else _siguiente(  # 083:RF-12
                    r.a, y, objetivos[k].kw, puntos[k], pendiente[k])  # type: ignore[arg-type]
                if a > 0:
                    a, acotado = _acotar(a, puntos[k], objetivos[k].kw)   # 083:RF-11
                    res.metodos['acotados'] = res.metodos.get('acotados', 0) + int(acotado)
                b = None
                if k in con_q and not q_listas[k] and m.kvar.get(k) is not None:
                    b, estado = _paso_q(r, m.kvar[k], objetivos[k], puntos_q[k],  # type: ignore[arg-type]
                                        r.factor_q_maximo(fp_minimo_escaladas), tolerancia_q)
                    if estado:
                        res.q_estado[k] = estado
                    if estado in Q_INCOHERENTES:
                        res.q_extremo[k] = _extremo_q(r, m.kvar[k], estado)  # type: ignore[arg-type]
                        r = r.al_perfil()                                    # 035:RF-29
                nuevo[k] = r.con_factores(a if a > 0 else r.a / 2, b)
            pendientes = [k for k in ajustables if k not in res.imposibles
                          and not (abs(_rel(m.kw[k], objetivos[k].kw)) <= tolerancia  # type: ignore[arg-type]
                                   and (k not in con_q or q_listas[k]))]
            if res.imposibles and not pendientes:
                # 086:RF-124: las demás ya cumplen y las imposibles no cambian con más flujos.
                res.motivo = 'sin cuadrar todos: ' + '; '.join(c['texto'] for c in res.imposibles.values())
                break
            actual = meta = nuevo
            continue
        # 083:RF-7: sin ningún flujo bueno, primero las escaladas casi en cero. Si ni así, no son ellas.
        if res.repartos is None:
            if not casi_cero:
                if not res.remedios:
                    res.remedios.append({'remedio': ESCALERA[0][0], 'cambios': []})
                casi_cero = True
                actual = {k: (actual[k].con_factores(actual[k].a * FACTOR_CASI_CERO, actual[k].b * FACTOR_CASI_CERO)
                              if k in ajustables else actual[k]) for k in claves}
                continue
            res.fijas_sospechosas = True
            mitades = MITADES
        if mitades < MITADES:
            if not res.remedios:
                res.remedios.append({'remedio': ESCALERA[0][0], 'cambios': []})
            mitades += 1
            nuevo = dict(actual)
            for k in ajustables:
                bueno = (res.repartos or {}).get(k)
                a0 = bueno.a if bueno is not None else 0.0
                b0 = bueno.b if bueno is not None else 0.0
                nuevo[k] = actual[k].con_factores((a0 + actual[k].a) / 2, (b0 + actual[k].b) / 2)
            actual = nuevo
            continue
        escalon += 1
        if escalon >= len(ESCALERA):
            break
        nombre, ajustes = ESCALERA[escalon]
        res.remedios.append({'remedio': nombre, 'cambios': list(remedio(nombre, ajustes))})
        mitades = 0
        casi_cero = False
        errores.clear()
        broyden = _Broyden(ajustables, pendiente)
        for k in puntos:
            puntos[k].clear()      # 083:RF-11: otra red, otro intervalo
        actual = meta

    if not res.cuadrado and not res.motivo:
        res.motivo = (f'sin cuadrar todos al {tolerancia:.1%} tras {res.flujos} flujos'
                      if res.repartos is not None else
                      'el flujo de carga no converge con ningún reparto, ni con los remedios')
    if (res.repartos is not None and ultimo is not None
            and any(ultimo[k] is not res.repartos[k] for k in claves)):
        # La red queda con los últimos repartos que convergieron (006:RF-18, RF-56).
        res.medida = flujo(res.repartos)
    return res


def causa_imposible(clave: str, r: Reparto, kw: float, carga_kw: float | None, objetivo_kw: float) -> dict[str, Any]:
    """086:RF-124: por qué una clave no puede cuadrar: sus fijas, sus pérdidas y la SED fija que más pesa.

    Las pérdidas son lo que entra por la cabecera menos lo que consumen sus cargas en el flujo; sin ese dato, ``None``.
    """
    fijas = {s: float(p) for s, (p, _q) in r.fijas.items()}
    suma = sum(fijas.values())
    perdidas = kw - carga_kw if carga_kw is not None else None
    exceso = kw - objetivo_kw
    sed, p_sed = max(fijas.items(), key=lambda x: x[1]) if fijas else ('', 0.0)
    partes = [f'{clave}: con las escaladas al mínimo da {kw:,.1f} kW frente a {objetivo_kw:,.1f} kW medidos '
              f'({exceso / objetivo_kw:+.1%}); sus fijas suman {suma:,.1f} kW']
    if perdidas is not None:
        partes.append(f'y sus pérdidas {perdidas:,.1f} kW')
    texto = ' '.join(partes) + '; no puede cuadrar sin cambiar sus fijas'
    if sed:
        texto += (f'. La SED fija que más pesa es {sed}, con {p_sed:,.1f} kW ({p_sed / suma:.0%} de sus fijas): '
                  'revise su registro y dónde se conecta')
    return {'clave': clave, 'kw': kw, 'objetivo_kw': objetivo_kw, 'exceso_kw': exceso, 'fijas_kw': suma,
            'perdidas_kw': perdidas, 'escaladas_factor': r.a,
            'dominante': {'sed': sed, 'kw': p_sed, 'parte': (p_sed / suma) if suma else None} if sed else None,
            'texto': texto + '.'}


def fijas_corregidas(antes: Reparto, despues: Reparto) -> list[dict[str, Any]]:
    """Las fijas que el cuadre bajó, con lo que tenían y lo que quedan (083:RF-30)."""
    return [{'sed': s, 'antes_kw': round(p, 1), 'despues_kw': round(despues.fijas[s][0], 1)}
            for s, (p, _q) in sorted(antes.fijas.items())
            if s in despues.fijas and abs(despues.fijas[s][0] - p) > max(1e-6, 1e-6 * abs(p))]


# =========================================================================== bancos que faltan
def bancos_que_faltan(q_red_kvar: float | None, q_medido_kvar: float | None,
                      tamano_kvar: float | None) -> int:
    """Cuántos bancos de ``tamano_kvar`` cubren el déficit reactivo (021:RF-64, RF-65).

    El déficit es lo que da la red en la cabecera menos lo medido: en NA293 (2026-10-17)
    2 645 kVAR frente a 1 560, sin ningún banco en el modelo; el usuario: «coloca los
    bancos necesarios en cada alimentador». Sin déficit, sin tamaño o sin medida, ninguno.
    """
    if q_red_kvar is None or q_medido_kvar is None or not tamano_kvar or tamano_kvar <= 0:
        return 0
    return max(0, round((q_red_kvar - q_medido_kvar) / tamano_kvar))


def distancias_de_bancos(largo_m: float, n: int) -> list[float]:
    """Dónde poner ``n`` bancos en una troncal de ``largo_m`` (021:RF-66).

    La regla de los 2k/(2n+1): con la carga repartida a lo largo de la troncal, las
    pérdidas son mínimas con el banco k a 2k/(2n+1) del largo (2/3 con uno solo).
    """
    return [largo_m * 2 * k / (2 * n + 1) for k in range(1, n + 1)]


def tamano_de_banco(por_tension: Mapping[float, float] | None, kv: float | None) -> float | None:
    """El tamaño de banco del perfil para la tensión ``kv``: la entrada más cercana, si está
    a menos del 10 % (22,9 kV no es 23); si no, ``None`` (021:RF-65, P13)."""
    if not por_tension or not kv:
        return None
    tension, kvar = min(por_tension.items(), key=lambda par: abs(par[0] - kv))
    return kvar if abs(tension - kv) <= 0.1 * kv else None


# =========================================================================== spec 041
#: Repartos por defecto (041) y mínimo de fijas para estimar de ellas la dispersión (RF-3).
N_PROBABILISTICO = 200
MINIMO_FIJAS_PROBABILISTICO = 5


@dataclass(frozen=True)
class Probabilistico:
    """Cómo varía la utilización de cada SED escalada (041:RF-1 a RF-3, RF-7).

    La utilización de una escalada es ``factor común × (kVA / kVA medio)^pendiente × ruido``,
    con el ruido lognormal de media 1 y desviación ``dispersion`` en su logaritmo: siempre
    positiva y, con la pendiente, mayor cuanto mayor la potencia (el usuario, 2026-10-31: «la
    probabilidad debe ser de acuerdo de la mayor potencia a menos de las escaladas»).
    """

    dispersion: float
    pendiente: float
    n: int = N_PROBABILISTICO
    semilla: int = 0
    fuente: str = ''

    def a_dict(self) -> dict[str, Any]:
        return {'dispersion': self.dispersion, 'pendiente': self.pendiente, 'n': self.n,
                'semilla': self.semilla, 'fuente': self.fuente}


def probabilistico_de_fijas(rep: Reparto, *, n: int = N_PROBABILISTICO, semilla: int = 0,
                            minimo: int = MINIMO_FIJAS_PROBABILISTICO) -> Probabilistico | None:
    """La dispersión y la pendiente con la potencia, de las fijas del mismo reparto (041:RF-3).

    Las fijas son las únicas SED con su potencia medida en el instante: su utilización
    (kW / kVA) frente a su kVA, en logaritmos, da por mínimos cuadrados la pendiente y, de lo
    que queda, la dispersión. La pendiente no baja de cero (RF-2). Con menos de ``minimo``
    fijas con kVA y potencia, ``None``.
    """
    pares = []
    for s, (p, _q) in rep.fijas.items():
        k = _kva_valido(rep.kva.get(s))
        if k and p > 0:
            pares.append((math.log(k), math.log(p / k)))
    if len(pares) < max(3, minimo):
        return None
    # 095:RF-1, RF-2: de las fijas solo la dispersión de su utilización alrededor de su media, sin pendiente con
    # la potencia. AL299 (2026-11-06): con la pendiente de 0,306 las SED de 5 kVA quedaban al 2 % de su kVA frente
    # al 10 % de media; el usuario pidió escaladas proporcionales a su potencia instalada.
    my = sum(y for _, y in pares) / len(pares)
    dispersion = math.sqrt(sum((y - my) ** 2 for _, y in pares) / (len(pares) - 1))
    return Probabilistico(dispersion=dispersion, pendiente=0.0, n=n,
                          semilla=semilla, fuente=f'fijas ({len(pares)})')


def probabilistico_del_perfil(datos: Mapping[str, Any] | None, *, n: int | None = None,
                              semilla: int = 0) -> Probabilistico | None:
    """``calibracion.reparto_probabilistico`` del perfil: ``dispersion`` y ``pendiente``, y
    opcionalmente ``n`` (041:RF-3). Sin la sección, ``None``: no se supone nada (P13)."""
    sec = ((datos or {}).get('calibracion') or {}).get('reparto_probabilistico')
    if not isinstance(sec, Mapping):
        return None
    disp, pend = numero(sec.get('dispersion')), numero(sec.get('pendiente'))
    if disp is None or disp < 0 or pend is None:
        raise AjusteError('calibracion.reparto_probabilistico necesita «dispersion» (≥ 0) y '
                          '«pendiente» numéricas.')
    # 095:RF-3: del perfil solo la dispersión; su pendiente se ignora y se dice.
    return Probabilistico(dispersion=disp, pendiente=0.0,
                          n=int(n or numero(sec.get('n')) or N_PROBABILISTICO), semilla=semilla,
                          fuente='perfil de empresa' + (f' (pendiente {pend:g} ignorada)' if pend else ''))


def muestra_de_reparto(rep: Reparto, prob: Probabilistico, azar) -> Reparto:
    """Un reparto posible: cada escalada con su multiplicador y la misma P base total (041:RF-1, RF-2).

    ``azar`` es un ``random.Random`` con la semilla del informe (RF-7). Se conserva la P base
    total de las escaladas, así que el factor común ``a`` sigue casi igual y el cuadre de cada
    muestra parte de cerca; la Q de cada SED sigue a su P con su mismo FP.
    """
    kvas = [k for s in rep.base if (k := _kva_valido(rep.kva.get(s)))]
    k_medio = math.exp(sum(math.log(k) for k in kvas) / len(kvas)) if kvas else 1.0
    s2 = prob.dispersion ** 2
    mult = {}
    for s in sorted(rep.base):                       # orden fijo: misma semilla, misma muestra
        k = _kva_valido(rep.kva.get(s))
        ruido = math.exp(prob.dispersion * azar.gauss(0.0, 1.0) - s2 / 2)
        mult[s] = ((k / k_medio) ** prob.pendiente if k else 1.0) * ruido
    total = sum(p for p, _ in rep.base.values())
    nuevo = sum(rep.base[s][0] * m for s, m in mult.items())
    norma = total / nuevo if nuevo > 0 else 1.0
    base = {s: (p * mult[s] * norma, q * mult[s] * norma) for s, (p, q) in rep.base.items()}
    return replace(rep, base=base)


def percentil(valores: Iterable[float], q: float) -> float | None:
    """Percentil ``q`` (0 a 1) con interpolación lineal; ``None`` sin valores."""
    xs = sorted(valores)
    if not xs:
        return None
    pos = q * (len(xs) - 1)
    i = int(math.floor(pos))
    return xs[i] if i + 1 >= len(xs) else xs[i] + (xs[i + 1] - xs[i]) * (pos - i)


def reparto_p50(rep: Reparto, kw_por_sed: Mapping[str, list[float]]) -> Reparto:
    """El reparto de las medianas (041:RF-5): por escalada, la mediana de su P en las muestras,
    con su Q a su mismo FP; se cuadra después a la cabecera como cualquiera.

    La P base total es la del determinista, como en cada muestra (:func:`muestra_de_reparto`), y
    los factores llevan la diferencia: las demandas siguen siendo las medianas, y el factor con que
    DIgSILENT cuadra el P50 mide la utilización igual que el determinista. Sin esto, el 26-11 en
    SM115 desde VNR-GIS las muestras cuadradas con el oráculo dejaron medianas 1,354 veces el
    reparto, la base pasó de 4 440 a 6 013 kW y el P50 se cuadró con 0,0397: la 015:RF-71 lo
    invalidó frente a 0,05 con una utilización real de 0,0537.
    """
    base = {}
    for s, (p, q) in rep.base.items():
        med = percentil(kw_por_sed.get(s) or [], 0.5)
        actual = rep.a * p
        if med is None or actual <= 0:
            base[s] = (p, q)
            continue
        base[s] = (p * med / actual, q * med / actual)
    antes, ahora = sum(p for p, _ in rep.base.values()), sum(p for p, _ in base.values())
    if antes <= 0 or ahora <= 0:
        return replace(rep, base=base)
    k = antes / ahora
    return replace(rep, base={s: (p * k, q * k) for s, (p, q) in base.items()}, a=rep.a / k, b=rep.b / k)


def resumen_probabilistico(rep: Reparto, muestras: list[dict[str, Any]],
                           prob: Probabilistico) -> dict[str, Any]:
    """Por escalada, de mayor a menor potencia, sus percentiles de kW y de cargabilidad y la
    probabilidad de pasar del 100 %; y la de una barra fuera de banda (041:RF-6).

    Cada muestra es ``{'kw': {sed: kW}, 'carga': {sed: % o None}, 'fuera_de_banda': bool o
    None}``; solo cuentan las que cuadraron.
    """
    validas = [m for m in muestras if m.get('kw')]
    sed = []
    for s in sorted(rep.base, key=lambda x: (-(_kva_valido(rep.kva.get(x)) or 0.0), x)):
        kw = [m['kw'][s] for m in validas if s in m['kw']]
        carga = [c for m in validas if (c := (m.get('carga') or {}).get(s)) is not None]
        sed.append({
            'sed': s, 'kva': _kva_valido(rep.kva.get(s)),
            'kw_p05': percentil(kw, 0.05), 'kw_p50': percentil(kw, 0.5), 'kw_p95': percentil(kw, 0.95),
            'carga_p05': percentil(carga, 0.05), 'carga_p50': percentil(carga, 0.5),
            'carga_p95': percentil(carga, 0.95),
            'prob_sobrecarga': (sum(c > 100.0 for c in carga) / len(carga)) if carga else None,
        })
    bandas = [m['fuera_de_banda'] for m in validas if m.get('fuera_de_banda') is not None]
    return {**prob.a_dict(), 'muestras': len(muestras), 'validas': len(validas), 'sed': sed,
            'prob_tension_fuera': (sum(bandas) / len(bandas)) if bandas else None}


#: Muestras mínimas antes de cortar por tiempo, y tope por alimentador sin perfil (083:RF-25).
MUESTRAS_MINIMAS = 20
TOPE_MUESTRAS_S = 180.0


def montecarlo(rep: Reparto, prob: Probabilistico,
               cuadrar_muestra: Callable[[Reparto], tuple[Reparto | None, dict[str, Any]]],
               *, cancelado: Callable[[], bool] = lambda: False,
               progreso: Callable[[int, int, str], None] = lambda n, maximo, texto: None,
               tope_s: float | None = None, reloj: Callable[[], float] | None = None,
               ) -> tuple[dict[str, Any], Reparto]:
    """Los N repartos posibles cuadrados a la cabecera, su resumen y el reparto P50 (041:RF-1 a RF-7).

    ``cuadrar_muestra(muestra)`` la cuadra en DIgSILENT y devuelve el reparto cuadrado (o
    ``None``) con lo que se leyó del flujo (``carga`` por SED, ``fuera_de_banda``).
    """
    import random
    import time

    reloj = reloj or time.perf_counter
    azar = random.Random(prob.semilla)
    muestras: list[dict[str, Any]] = []
    inicio = reloj()
    cortado = None
    for i in range(prob.n):
        if cancelado():
            break
        if tope_s is not None and i >= MUESTRAS_MINIMAS and reloj() - inicio >= tope_s:
            cortado = (i, reloj() - inicio)                                   # 083:RF-25
            break
        cuadrada, leido = cuadrar_muestra(muestra_de_reparto(rep, prob, azar))
        progreso(i + 1, prob.n, f'reparto probabilístico {i + 1}/{prob.n}')
        kw = ({s: d.kw for s, d in cuadrada.demandas.items() if s in cuadrada.base}
              if cuadrada is not None else {})
        muestras.append({'kw': kw, **(leido or {})})
    kw_por_sed: dict[str, list[float]] = {}
    for m in muestras:
        for s, v in m['kw'].items():
            kw_por_sed.setdefault(s, []).append(v)
    resumen = resumen_probabilistico(rep, muestras, prob)
    if cortado is not None:
        resumen['muestras_hechas'] = cortado[0]
        resumen['aviso_tope'] = (f'{cortado[0]} de {prob.n} repartos: el tope de {tope_s:.0f} s de las muestras en DIgSILENT se '
                                 f'alcanzó en {cortado[1]:.0f} s; el P50 es de las hechas (083:RF-25).')
    return resumen, reparto_p50(rep, kw_por_sed)
