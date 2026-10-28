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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

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


def fijas_de(cruzados: Iterable[Mapping[str, Any]], objetivo: Objetivo,
             fp_minimo: float | None = None) -> dict[str, Fija]:
    """Suma por SED de los clientes cruzados (``ClienteImportante.to_dict``).

    El kVAR de cada cliente sale de su energía reactiva y activa del mes (RF-6): es su
    factor de potencia medio, que es lo que se conoce de él. Sin una de las dos, el del
    objetivo (RF-7). El factor de las escaladas del perfil no las toca (015:RF-53).

    Con ``fp_minimo`` (perfil de empresa, 015:RF-62 a RF-64), el cliente cuyo EA/ERI da un
    factor menor se escribe con ese mínimo, como compensado por su banco propio, y queda
    dicho en su derivación y en un aviso. En CA101 (2026-10-15) el EA/ERI daba factores
    de 0,43 a 0,98 y la cabecera 3036 kvar frente a 302 medidos.
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
        q_registro = numero(c.get('q_registro_kvar'))
        if numero(c.get('p_registro_kw')) is not None:
            # 004:RF-67: P y Q del cliente en el instante de su alimentador, coincidentes.
            kw = numero(c.get('p_registro_kw'))
        if q_registro is not None and kw:
            # 004:RF-66: la reactiva del registro de 15 minutos en que se dio su POT.
            tan = q_registro / kw
            metodo = f"ERI_DEL_REGISTRO {c.get('fecha_registro') or ''}".strip()
        elif ea is None or eri is None or ea == 0:
            tan = objetivo.tan_phi
            metodo = 'FP_CABECERA_FALLBACK'
            f.avisos.append(f'{codigo}: sin EA o ERI; su kVAR con el FP del objetivo '
                            f'({objetivo.fp:.3f}).')
        else:
            tan = eri / ea
            metodo = 'ERI/EA'
        q_kvar = kw * tan
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
            f.avisos.append(
                f'{codigo}: FP {fp_libro:.3f} de su EA/ERI llevado a {fp_minimo:.3f} por su '
                f'banco propio; Q {q_libro:,.1f} → {q_kvar:,.1f} kvar (015:RF-62).')
        f.kw += kw
        f.kvar += q_kvar
        f.clientes.append(codigo)
        derivacion = {
            'cliente': codigo,
            'p_kw': kw,
            'q_kvar': q_kvar,
            'fp': abs(kw) / math.hypot(kw, q_kvar) if (kw or q_kvar) else 1.0,
            'metodo': metodo,
            'ea': ea,
            'eri': eri,
        }
        if compensado:
            derivacion['compensado'] = compensado
        f.derivaciones.append(derivacion)
    return {f.sed: f for f in por_clave.values()}


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
    todo_escala: bool = False
    solo_kw: bool = False
    omitidas: list[dict[str, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def con_factores(self, a: float, b: float | None = None) -> Reparto:
        """El mismo reparto con otros factores; en «solo kW» el kVAR sigue al kW (RF-14)."""
        b = a if self.solo_kw else (self.b if b is None else b)
        return Reparto(**{**self.__dict__, 'a': a, 'b': b})

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


def reparto_inicial(objetivo: Objetivo, fijas: Mapping[str, Fija],
                    cargas: Mapping[str, tuple[float, float]],
                    kva: Mapping[str, Any] | None = None,
                    fp: float | None = None) -> Reparto:
    """El reparto que da el objetivo sin pérdidas, con el factor de escala de DIgSILENT.

    ``cargas`` tiene una entrada por cada carga de SED del alimentador en DIgSILENT, con el
    nombre que tiene allí y su P y Q (kW, kVAR): es la lista de SED. Las fijas (clientes
    importantes) se buscan en ella por su código y llevan su P y Q (015:RF-43).

    Las demás escalan según su potencia instalada (015:RF-44): P base = kVA × FP, Q base con
    ese mismo FP, y un solo factor de escala, el ``scale0`` de DIgSILENT, que es así la
    fracción de carga de sus transformadores. El usuario, el 2026-10-15: «el escalado se
    debe hacer a sus potencias instaladas de cada SED escalada». Con la P del archivo, en
    CA101 98 de 160 escaladas (11 057 kVA) tenían demanda cero y los 6 MW caían en 62 SED.
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
                       solo_kw=True, omitidas=omitidas, avisos=avisos)

    # Los clientes ya llenan la cabecera, o no queda demanda que escalar: escala todo
    # (RF-13), las fijas con su P y Q como punto de partida.
    todo = {**base, **fijas_pf}
    bp = sum(p for p, _ in todo.values())
    if bp <= 0:
        raise AjusteError('No hay demanda que escalar: ninguna SED tiene demanda en el archivo '
                          'original ni clientes importantes con potencia.')
    avisos.append(
        f'Los clientes importantes suman {p_fijas:,.1f} kW frente a un objetivo de '
        f'{objetivo.kw:,.1f} kW: se escalan todas las SED, también las suyas.'
        if base else
        'Todas las SED del alimentador tienen clientes importantes: se escalan sus demandas.')
    a = objetivo.kw / bp
    return Reparto(fijas={}, base=todo, origen=origen, kva=kvas, a=a, b=a, todo_escala=True,
                   solo_kw=True, omitidas=omitidas, avisos=avisos)


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


def cuadrado(medida: Medida, objetivo: Objetivo, tolerancia: float,
             solo_kw: bool = True) -> bool:
    """Compatibilidad del API histórico; ``solo_kw`` ya no cambia la aceptación."""
    del solo_kw
    return cuadrado_kw(medida, objetivo, tolerancia)


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
                              'carga_kw': m.carga_kw, 'carga_kvar': m.carga_kvar,
                              'motivo': m.motivo})
        progreso(res.flujos, max_flujos, f'flujo {res.flujos}: ' + (
            f'{m.kw:,.1f} kW / {m.kvar:,.1f} kVAR en la cabecera'
            if m.converge and m.kw is not None and m.kvar is not None else 'no converge'))
        if m.converge and m.kw is not None:
            # ``mitades`` no vuelve a cero aquí: tras un medio camino que converge, la
            # secante vuelve a saltar al objetivo, y si allí no converge se repetía sin
            # llegar nunca a los remedios del flujo de carga.
            res.reparto, res.medida = actual, m
            if cuadrado_kw(m, objetivo, tolerancia):
                p_nominal, _q_nominal = actual.totales()
                p_cargas = p_nominal if m.carga_kw is None else m.carga_kw
                perdida_p = m.kw - p_cargas
                # Una red pasiva no puede entregar en su cabecera menos potencia activa
                # que el consumo efectivo de sus cargas (o el nominal, si el motor no da
                # resultados). CA101 llegó a aparentar -6.684 MW porque el ElmFeeder
                # medía solo una de sus dos troncales.
                # Se admite únicamente ruido numérico pequeño (0,01 % del objetivo).
                tolerancia_perdida = max(0.1, abs(objetivo.kw) * 1e-4)
                if perdida_p < -tolerancia_perdida:
                    res.motivo = (
                        f'pérdidas activas negativas ({perdida_p:,.1f} kW): la frontera '
                        'de medición puede estar omitiendo una troncal o parte de las cargas')
                    return res
                res.cuadrado = True
                return res
            puntos_p.append((actual.a, m.kw))
            a = _siguiente(actual.a, m.kw, objetivo.kw, puntos_p,
                           sum(p for p, _ in actual.base.values()))
            if a <= 0:
                # Las pérdidas y las fijas ya pasan del objetivo: no se cruza el cero de un salto.
                a = actual.a / 2
            # La asignación inicial de Q se conserva. Sólo P se itera para compensar las
            # pérdidas; el Q final será el que produzca la red nativa con sus bancos.
            actual = meta = actual.con_factores(a)
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


# =========================================================================== dos zonas
@dataclass(frozen=True)
class ObjetivoZonas:
    """El objetivo de un alimentador con una central en su troncal (spec 021, RF-33).

    En NA205 la cabecera solo ve lo que entra desde la SET: con la central generando, 1 123
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

    def desvio(self, clave: str) -> float | None:
        """Error relativo de kW de una clave en el último flujo común que convergió."""
        m = self.medida
        if m is None or not m.converge or m.kw.get(clave) is None:
            return None
        return _rel(m.kw[clave], self.objetivos[clave].kw)  # type: ignore[arg-type]


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
) -> CuadreConjunto:
    """Ajusta a la vez un factor por clave hasta que todas den su objetivo (021:RF-54 a RF-58).

    Las claves son los alimentadores de un proyecto, o las zonas de uno con central: en el
    proyecto de NA203 y NA205 (2026-10-17) se iba a calibrar uno y después el otro, y el
    usuario pidió calibrar por proyecto, todos en el mismo flujo. ``flujo(repartos)``
    escribe todas las demandas, ejecuta **un** flujo de carga y mide cada clave. Cada
    factor sigue su secante con la medida de su clave; solo cuadra cuando todas cumplen en
    el mismo flujo (RF-55). Si no converge, los pasos de :func:`cuadrar` para todas: medio
    camino desde el último flujo común que convergió y luego los remedios de
    :data:`ESCALERA`, una vez para el proyecto (RF-56). Una clave en ``quietas`` (una zona
    solo con clientes fijos, 021:RF-45) se escribe pero no se ajusta ni decide.
    """
    quietas = set(quietas)
    claves = tuple(repartos)
    pendiente = {k: (0.0 if k in quietas else sum(p for p, _ in r.base.values()))
                 for k, r in repartos.items()}
    ajustables = tuple(k for k in claves if pendiente[k] > 0)
    res = CuadreConjunto(cuadrado=False, repartos=None, medida=None, objetivos=objetivos,
                         tolerancia=tolerancia, ajustables=ajustables)
    if not ajustables:
        raise AjusteError('Ninguno de los alimentadores tiene cargas que escalar.')
    puntos: dict[str, list[tuple[float, float]]] = {k: [] for k in claves}
    actual = meta = dict(repartos)
    escalon = mitades = 0
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
            if all(abs(_rel(m.kw[k], objetivos[k].kw)) <= tolerancia  # type: ignore[arg-type]
                   for k in ajustables):
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
                res.cuadrado = True
                return res
            nuevo = dict(actual)
            for k in ajustables:
                r, y = actual[k], m.kw[k]
                puntos[k].append((r.a, y))  # type: ignore[arg-type]
                a = _siguiente(r.a, y, objetivos[k].kw, puntos[k], pendiente[k])  # type: ignore[arg-type]
                nuevo[k] = r.con_factores(a if a > 0 else r.a / 2)
            actual = meta = nuevo
            continue
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


# =========================================================================== bancos que faltan
def bancos_que_faltan(q_red_kvar: float | None, q_medido_kvar: float | None,
                      tamano_kvar: float | None) -> int:
    """Cuántos bancos de ``tamano_kvar`` cubren el déficit reactivo (021:RF-64, RF-65).

    El déficit es lo que da la red en la cabecera menos lo medido: en NA203 (2026-10-17)
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
