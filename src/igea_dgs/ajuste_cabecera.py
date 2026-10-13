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

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .demanda_medida import clave_codigo, numero


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
        kvar = kw * math.tan(math.acos(abs(fp)))
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


def fijas_de(cruzados: Iterable[Mapping[str, Any]], objetivo: Objetivo) -> dict[str, Fija]:
    """Suma por SED de los clientes cruzados (``ClienteImportante.to_dict``).

    El kVAR de cada cliente sale de su energía reactiva y activa del mes (RF-6): es su
    factor de potencia medio, que es lo que se conoce de él. Sin una de las dos, el del
    objetivo (RF-7).
    """
    por_clave: dict[str, Fija] = {}
    for c in cruzados:
        sed = str(c.get('sed') or '').strip()
        kw = numero(c.get('pot'))
        if not sed or kw is None:
            continue
        f = por_clave.setdefault(clave_codigo(sed), Fija(sed))
        ea, eri = numero(c.get('ea')), numero(c.get('eri'))
        codigo = str(c.get('codigo') or '')
        if ea is None or eri is None or ea == 0:
            tan = objetivo.tan_phi
            metodo = 'FP_CABECERA_FALLBACK'
            f.avisos.append(f'{codigo}: sin EA o ERI; su kVAR con el FP del objetivo '
                            f'({objetivo.fp:.3f}).')
        else:
            tan = eri / ea
            metodo = 'ERI/EA'
        q_kvar = kw * tan
        f.kw += kw
        f.kvar += q_kvar
        f.clientes.append(codigo)
        f.derivaciones.append({
            'cliente': codigo,
            'p_kw': kw,
            'q_kvar': q_kvar,
            'fp': abs(kw) / math.hypot(kw, q_kvar) if (kw or q_kvar) else 1.0,
            'metodo': metodo,
            'ea': ea,
            'eri': eri,
        })
    return {f.sed: f for f in por_clave.values()}


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
    todo_escala: bool = False
    solo_kw: bool = False
    omitidas: list[dict[str, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def con_factores(self, a: float, b: float | None = None) -> 'Reparto':
        """El mismo reparto con otros factores; en «solo kW» el kVAR sigue al kW (RF-14)."""
        b = a if self.solo_kw else (self.b if b is None else b)
        return Reparto(**{**self.__dict__, 'a': a, 'b': b})

    def a_solo_kw(self, objetivo: 'Objetivo') -> 'Reparto':
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


def reparto_inicial(objetivo: Objetivo, fijas: Mapping[str, Fija],
                    kva: Mapping[str, Any]) -> Reparto:
    """El reparto que da el objetivo sin pérdidas.

    ``kva`` tiene una entrada por cada carga de SED del alimentador en DIgSILENT, con el
    nombre que tiene allí: es la lista de SED. Las fijas se buscan en ella por su código.
    """
    por_clave = {clave_codigo(s): s for s in kva}
    kvas = {s: _kva_valido(v) for s, v in kva.items()}
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
    repartir = [s for s in kva if s not in fijas_pf]
    sin_kva = [s for s in repartir if kvas[s] is None]
    if sin_kva:
        raise AjusteError(
            f'{len(sin_kva)} SED sin potencia instalada ni en DIgSILENT ni en la entrada '
            f'original: {", ".join(sin_kva[:50])}. Corríjalas antes de ajustar.')
    origen = {s: ('cliente' if s in fijas_pf else 'kva') for s in kva}
    kva_r = {s: kvas[s] or 0.0 for s in repartir}       # ya comprobado: ninguno es None
    kva_rep = sum(kva_r.values())
    p_fijas = sum(p for p, _ in fijas_pf.values())
    q_fijas = sum(q for _, q in fijas_pf.values())
    p_falta, q_falta = objetivo.kw - p_fijas, objetivo.kvar - q_fijas

    if p_falta > 0 and kva_rep > 0:
        solo_kw = q_falta < 0
        if solo_kw:
            avisos.append(f'El kVAR que falta por repartir es negativo ({q_falta:,.1f}): se '
                          'cuadra solo el kW y las SED repartidas llevan el FP del objetivo '
                          f'({objetivo.fp:.3f}).')
        base = {s: (k, k * objetivo.tan_phi if solo_kw else k) for s, k in kva_r.items()}
        a = p_falta / kva_rep
        return Reparto(fijas=fijas_pf, base=base, origen=origen, kva=kvas, a=a,
                       b=a if solo_kw else q_falta / kva_rep, solo_kw=solo_kw,
                       omitidas=omitidas, avisos=avisos)

    # Los clientes ya llenan la cabecera, o no queda SED que repartir: escala todo (RF-13).
    # Las repartidas parten de la utilización media de las fijas, para que «junto con
    # las demás» no las deje en cero.
    kva_fij = sum(kvas[s] or 0.0 for s in fijas_pf)
    uso = p_fijas / kva_fij if kva_fij else 0.0
    base = dict(fijas_pf)
    for s, k in kva_r.items():
        p = uso * k
        base[s] = (p, p * objetivo.tan_phi)
    bp = sum(p for p, _ in base.values())
    bq = sum(q for _, q in base.values())
    if bp <= 0:
        raise AjusteError('No hay demanda que escalar: ninguna SED con clientes importantes '
                          'tiene potencia ni hay SED que repartir.')
    solo_kw = objetivo.kvar < 0 or bq <= 0
    avisos.append(
        f'Los clientes importantes suman {p_fijas:,.1f} kW frente a un objetivo de '
        f'{objetivo.kw:,.1f} kW: se escalan todas las SED, también las suyas.'
        if repartir else
        'Todas las SED del alimentador tienen clientes importantes: se escalan sus demandas.')
    a = objetivo.kw / bp
    return Reparto(fijas={}, base=base, origen=origen, kva=kvas, a=a,
                   b=a if solo_kw else objetivo.kvar / bq, todo_escala=True, solo_kw=solo_kw,
                   omitidas=omitidas, avisos=avisos)


# =========================================================================== cuadre
@dataclass(frozen=True)
class Medida:
    """Lo que entra por la cabecera en un flujo de carga; sin valores si no converge."""

    converge: bool
    kw: float | None = None
    kvar: float | None = None
    motivo: str = ''


#: Remedios de RF-16, por orden. El primero no toca el flujo de carga: se acerca al
#: objetivo desde el último reparto que convergió. Los demás son ajustes del ``ComLdf``;
#: ``('x', n)`` multiplica el valor que tenga. Son datos para que el informe diga qué
#: cambió (RF-17) y el guion los deshaga al final.
ESCALERA: tuple[tuple[str, dict[str, Any]], ...] = (
    ('acercarse en pasos', {}),
    ('más iteraciones', {'itrlx': ('x', 3)}),
    ('paso automático', {'iStepAdapt': 1}),
    ('adaptación automática del modelo y cargas dependientes de la tensión',
     {'iopt_lev': 1, 'iopt_pq': 1}),
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

    def errores(self) -> tuple[float | None, float | None]:
        """Error relativo de kW y kVAR en la cabecera, con signo (medido − objetivo)."""
        m = self.medida
        if m is None or not m.converge or m.kw is None or m.kvar is None:
            return None, None
        return (_rel(m.kw, self.objetivo.kw),
                _rel(m.kvar, self.objetivo.kvar, self.objetivo.kw))

    def perdidas(self) -> tuple[float | None, float | None]:
        """Lo que entra por la cabecera menos lo que consumen las SED."""
        m = self.medida
        if self.reparto is None or m is None or m.kw is None or m.kvar is None:
            return None, None
        p, q = self.reparto.totales()
        return m.kw - p, m.kvar - q


def _rel(medido: float, objetivo: float, respaldo: float | None = None) -> float:
    # Un objetivo de kVAR casi nulo haría enorme cualquier error: se mide contra el kW.
    den = abs(objetivo) if abs(objetivo) > 1e-9 else abs(respaldo or 1.0)
    return (medido - objetivo) / den


def cuadrado(medida: Medida, objetivo: Objetivo, tolerancia: float, solo_kw: bool) -> bool:
    """RF-11: converge y kW (y kVAR, salvo en «solo kW») dentro de la tolerancia."""
    if not medida.converge or medida.kw is None or medida.kvar is None:
        return False
    if abs(_rel(medida.kw, objetivo.kw)) > tolerancia:
        return False
    return solo_kw or abs(_rel(medida.kvar, objetivo.kvar, objetivo.kw)) <= tolerancia


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
) -> Cuadre:
    """Ajusta los factores del reparto hasta que la cabecera dé el objetivo (RF-11, RF-12).

    ``flujo(reparto)`` escribe las demandas y ejecuta el flujo de carga. ``remedio(nombre,
    ajustes)`` aplica un remedio de :data:`ESCALERA` y dice qué cambió. Si no cuadra, el
    resultado lleva el último reparto que convergió, y el flujo queda ejecutado con él
    (RF-18, RF-22).
    """
    res = Cuadre(cuadrado=False, reparto=None, medida=None, objetivo=objetivo,
                 tolerancia=tolerancia, avisos=list(reparto.avisos))
    puntos_p: list[tuple[float, float]] = []
    puntos_q: list[tuple[float, float]] = []
    actual = meta = reparto      # meta: adonde se quería llegar cuando dejó de converger
    escalon = mitades = 0
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
                              'motivo': m.motivo})
        progreso(res.flujos, max_flujos, f'flujo {res.flujos}: ' + (
            f'{m.kw:,.1f} kW / {m.kvar:,.1f} kVAR en la cabecera'
            if m.converge and m.kw is not None and m.kvar is not None else 'no converge'))
        if m.converge and m.kw is not None and m.kvar is not None:
            # ``mitades`` no vuelve a cero aquí: tras un medio camino que converge, la
            # secante vuelve a saltar al objetivo, y si allí no converge se repetía sin
            # llegar nunca a los remedios del flujo de carga.
            res.reparto, res.medida = actual, m
            if cuadrado(m, objetivo, tolerancia, actual.solo_kw):
                res.cuadrado = True
                return res
            puntos_p.append((actual.a, m.kw))
            a = _siguiente(actual.a, m.kw, objetivo.kw, puntos_p,
                           sum(p for p, _ in actual.base.values()))
            if a <= 0:
                # Las pérdidas y las fijas ya pasan del objetivo: no se cruza el cero de un salto.
                a = actual.a / 2
            b = None
            if not actual.solo_kw:
                puntos_q.append((actual.b, m.kvar))
                b = _siguiente(actual.b, m.kvar, objetivo.kvar, puntos_q,
                               sum(q for _, q in actual.base.values()))
                if b < 0:
                    # Los cables dan más reactiva de la que pide la cabecera (RF-14).
                    actual = actual.a_solo_kw(objetivo)
                    res.avisos.append(
                        'Con las pérdidas, el kVAR que falta por repartir sale negativo: se '
                        'cuadra solo el kW y las SED repartidas llevan el FP del objetivo.')
                    puntos_q.clear()
            actual = meta = actual.con_factores(a, b)
            continue

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
        actual = meta              # con el flujo más tolerante, otra vez a por el objetivo

    if not res.cuadrado and not res.motivo:
        res.motivo = (f'sin cuadrar al {tolerancia:.1%} tras {res.flujos} flujos'
                      if res.reparto is not None else
                      'el flujo de carga no converge con ningún reparto, ni con los remedios')
    if res.reparto is not None and ultimo_flujo is not res.reparto:
        # La red queda con el último reparto que convergió y con sus resultados (RF-18).
        res.medida = flujo(res.reparto)
    return res
