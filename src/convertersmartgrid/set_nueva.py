"""SET nueva para las cargas que la red existente ya no puede atender (spec 042).

Por qué. En NA203 + NA205 (2026-10-31) las 37 cargas nuevas del libro suman unos 30 MW sobre 11 MW
calibrados: juntas dejan la red a 0,63 pu y ninguna variante de la escalera de la 025 cumple. Las
que no caben pasan, con los tramos de NA203 y NA205 donde se conectan, a una SET nueva (la Copara
que Electro Dunas ya planifica en Nasca). Aquí, sin DIgSILENT: su potencia de diseño a la vida
útil, el módulo del Plan de Inversiones en Transmisión que la cubre y el punto donde menos
potencia por distancia hay que llevar.
"""
from __future__ import annotations

import math
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RADIO_TIERRA_M = 6_371_000.0
M_POR_GRADO = 111_320.0
#: Trozos en que se reparte el crecimiento de un sorteo entre las zonas (RF-9).
TROZOS_POR_SORTEO = 20


class SetNuevaError(ValueError):
    """Falta un dato para diseñar la SET nueva; el mensaje dice cuál (042:RF-8, P13)."""


@dataclass(frozen=True)
class Parametros:
    anios: int
    factor_seguridad: float
    modulos_pit: Mapping[str, Any]
    max_unidades: int = 1
    """Transformadores iguales en paralelo que admite la empresa (042:RF-14); sin dato, uno."""
    factor_seguridad_sin_tasa: float | None = None
    """El de diseñar sin contar el crecimiento (086:RF-51); sin dato, ``factor_seguridad``."""

    def factor_para(self, tasa_ponderada: float) -> float:
        """086:RF-51: el margen es por el crecimiento que no se cuenta. Con la tasa, no se cobra dos veces.

        Usuario (2026-11-04): «debe ser 1.25 si no se considera la tasa de crecimiento». La SET de
        NA203 + NA205 se diseña con la tasa medida y el 1,0 del perfil; sin tasa, ese 1,0 no dejaba margen.
        """
        if self.anios > 0 and tasa_ponderada > 0:
            return self.factor_seguridad
        return self.factor_seguridad if self.factor_seguridad_sin_tasa is None else self.factor_seguridad_sin_tasa


def parametros(perfil: Mapping[str, Any]) -> Parametros:
    """Vida útil, factor de seguridad y configuración de los módulos PIT del perfil (042:RF-8)."""
    plan = perfil.get('planificacion') or {}
    faltan = [k for k in ('vida_util_anios', 'factor_seguridad_set', 'modulos_pit') if not plan.get(k)]
    if faltan:
        raise SetNuevaError('el perfil de empresa no trae ' + ', '.join(f'planificacion.{k}' for k in faltan)
                            + ': no se supone ningún valor para diseñar la SET nueva (042:RF-8).')
    # Sin el dato, un solo transformador: el paralelo es una decisión de la empresa (P13).
    unidades = int((plan.get('transformador_set') or {}).get('unidades_en_paralelo_max') or 1)
    # El horizonte de diseño de la SET, aparte de la vida útil del costeo: con 30 años y la tasa
    # medida, la SET de NA203 + NA205 salía de 372 MVA (usuario, 2026-11-01: horizonte del PIDE).
    horizonte = plan.get('horizonte_set_anios') or plan['vida_util_anios']
    sin_tasa = plan.get('factor_seguridad_set_sin_tasa')
    return Parametros(int(horizonte), float(plan['factor_seguridad_set']),
                      plan['modulos_pit'], max(1, unidades), None if sin_tasa is None else float(sin_tasa))


def distancia_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia sobre la esfera entre dos puntos (lat, lon) en grados."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(min(1.0, math.sqrt(h)))


# =========================================================================== RF-7
def potencia_de_diseno(trasladado: Mapping[str, tuple[float, float]], nuevas: tuple[float, float],
                       tasas: Mapping[str, float], *, anios: int, factor_seguridad: float) -> dict[str, Any]:
    """(demanda trasladada × (1 + g)^n + cargas nuevas) × FS, con cada término (042:RF-7).

    ``trasladado``: kW y kvar calibrados que cada alimentador pasa a la SET nueva; ``nuevas``: los
    de las cargas nuevas que van a ella; ``tasas``: la de la spec 029 de cada alimentador. La tasa
    se pondera por los kVA que traslada cada uno: el que más carga aporta es el que más pesa en
    cómo crecerá la SET. Las cargas nuevas no crecen: son fijas con su potencia declarada; la
    tasa es de la demanda registrada (usuario, 2026-10-31: «la tasa es para mediciones
    registradas, fijas y medición de cabecera; las nuevas son fijas, no tienen tasa»).
    """
    faltan = sorted(f for f in trasladado if tasas.get(f) is None)
    if faltan:
        raise SetNuevaError(f"sin tasa de crecimiento de la spec 029 para {', '.join(faltan)}: no se "
                            'supone ninguna (042:RF-8).')
    kva = {f: math.hypot(*pq) for f, pq in trasladado.items()}
    total = sum(kva.values())
    g = (sum(tasas[f] * s for f, s in kva.items()) / total if total
         else sum(tasas[f] for f in trasladado) / len(trasladado) if trasladado else 0.0)
    p = sum(pq[0] for pq in trasladado.values())
    q = sum(pq[1] for pq in trasladado.values())
    base = math.hypot(p, q) + math.hypot(*nuevas)
    crecimiento = (1.0 + g) ** anios
    return {'kva_trasladado': math.hypot(p, q), 'kva_nuevas': math.hypot(*nuevas), 'kva_base': base,
            'tasa_ponderada': g, 'tasas': dict(tasas), 'anios': anios, 'factor_crecimiento': crecimiento,
            'factor_seguridad': factor_seguridad,
            'kva_diseno': (math.hypot(p, q) * crecimiento + math.hypot(*nuevas)) * factor_seguridad}


# =========================================================================== módulos PIT
_TENSIONES_MVA = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)(?:\s*/\s*(\d+(?:[.,]\d+)?))?\s*(?:kV)?\s*(?:de)?\s*'
    r'(\d+(?:[.,]\d+)?)(?:\s*/\s*\d+(?:[.,]\d+)?)*\s*MVA', re.I)


def _num(texto: str) -> float:
    return float(texto.replace(',', '.'))


def _limpio(x: Any) -> str:
    return re.sub(r'\s+', ' ', str(x or '')).strip().upper()


def leer_modulos_pit(ruta: Path | str, cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Módulos de SET y de transformador del libro CAPEX de la empresa (042:RF-5, RF-7).

    Cada fila cuya descripción dice tensiones y MVA («60/22,9/10 kV de 25/25/25 MVA»): un
    transformador si lo dice, una SET si nombra la SET. Las líneas y las celdas no son módulos de
    SET. La hoja, la fila de cabecera y las columnas vienen del perfil (P13); el costo, por la
    escala del perfil.
    """
    import openpyxl

    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    if cfg['hoja'] not in wb.sheetnames:
        raise SetNuevaError(f"el libro CAPEX no tiene la hoja {cfg['hoja']!r} de los módulos PIT.")
    filas = list(wb[cfg['hoja']].iter_rows(values_only=True))
    marca = _limpio(cfg['fila_cabecera_contiene'])
    i_cab = next((i for i, f in enumerate(filas) if any(marca in _limpio(v) for v in f)), None)
    if i_cab is None:
        raise SetNuevaError(f"la hoja {cfg['hoja']!r} no tiene la cabecera «{cfg['fila_cabecera_contiene']}».")
    cab = [_limpio(v) for v in filas[i_cab]]
    col = {}
    for clave, nombre in cfg['columnas'].items():
        j = next((j for j, c in enumerate(cab) if _limpio(nombre) in c), None)
        if j is None:
            raise SetNuevaError(f"la hoja {cfg['hoja']!r} no tiene la columna «{nombre}».")
        col[clave] = j
    escala = float(cfg.get('escala') or 1.0)
    out = []
    for f in filas[i_cab + 1:]:
        desc = str(f[col['descripcion']] or '').strip() if col['descripcion'] < len(f) else ''
        m = _TENSIONES_MVA.search(desc)
        costo = f[col['costo']] if col['costo'] < len(f) else None
        if not m or not isinstance(costo, (int, float)):
            continue
        if re.search(r'transformador', desc, re.I):
            tipo = 'transformador'
        elif re.search(r'\bSET\b', desc):
            tipo = 'set'
        else:
            continue
        kv = sorted((_num(x) for x in m.groups()[:3] if x), reverse=True)
        out.append({'descripcion': desc, 'tipo': tipo, 'kv_at': kv[0], 'kv_mt': kv[1],
                    'kv': kv, 'mva': _num(m.group(4)), 'costo': float(costo) * escala,
                    'moneda': str(f[col['moneda']] or '').strip() if 'moneda' in col else ''})
    return out


def elegir_modulo(modulos: Sequence[Mapping[str, Any]], kva_diseno: float, kv_mt: float,
                  kv_at: float | None = None, *, max_unidades: int = 1) -> dict[str, Any]:
    """El menor módulo que cubre la potencia de diseño a la tensión de media (042:RF-7).

    Primero un módulo de SET nueva (es lo que se construye); si ninguno cubre, el menor
    transformador, cuyo costo no incluye la SET. Si ninguno cubre solo y el perfil admite
    transformadores en paralelo (``max_unidades`` > 1), el de menor costo con n unidades
    iguales: la SET una vez y n − 1 transformadores de su potencia (042:RF-14; NA203 + NA205,
    2026-10-31: 45,5 MVA de diseño y el mayor módulo de 22,9 kV era de 40 MVA). Sin ninguno,
    ``modulo`` es ``None`` y ``motivo`` dice por qué. ``modulo['unidades']`` dice cuántos.
    """
    def a_tension(m):
        return (any(abs(v - kv_mt) < 0.05 for v in m['kv'][1:])
                and (kv_at is None or abs(m['kv_at'] - kv_at) < 0.5))

    for tipo in ('set', 'transformador'):
        cand = sorted((m for m in modulos if m['tipo'] == tipo and a_tension(m) and m['mva'] * 1000.0 >= kva_diseno),
                      key=lambda m: (m['mva'], m['costo']))
        if cand:
            motivo = ('módulo de SET nueva' if tipo == 'set' else
                      'ningún módulo de SET nueva cubre la potencia: el transformador, sin la SET')
            return {'modulo': {**cand[0], 'unidades': 1, 'mva_total': cand[0]['mva'], 'costo_total': cand[0]['costo']},
                    'motivo': motivo}
    for tipo in ('set', 'transformador') if max_unidades > 1 else ():
        opciones = []
        for m in (m for m in modulos if m['tipo'] == tipo and a_tension(m) and m['mva'] > 0):
            n = math.ceil(kva_diseno / (m['mva'] * 1000.0))
            if n > max_unidades:
                continue
            # La SET se construye una vez; cada unidad más es un transformador de su potencia, o
            # el propio módulo si el libro no trae ese transformador suelto.
            extra = min((t['costo'] for t in modulos if t['tipo'] == 'transformador' and a_tension(t)
                         and abs(t['mva'] - m['mva']) < 1e-6 and abs(t['kv_at'] - m['kv_at']) < 0.5),
                        default=m['costo']) if tipo == 'set' else m['costo']
            opciones.append((m['costo'] + (n - 1) * extra, n, m['mva'], m))
        if opciones:
            costo, n, _, m = min(opciones, key=lambda o: o[:3])
            motivo = (f'ningún módulo cubre solo la potencia: {n} transformadores de {m["mva"]:g} MVA en paralelo'
                      + ('' if tipo == 'set' else ', sin la SET'))
            return {'modulo': {**m, 'unidades': n, 'mva_total': n * m['mva'], 'costo_total': costo}, 'motivo': motivo}
    # El mayor de esa tensión: con todos, la SET El Ángel de 22 kV y 120 MVA salía como «el mayor».
    mayor = max((m['mva'] for m in modulos if any(abs(v - kv_mt) < 0.05 for v in m['kv'][1:])), default=0)
    paralelo = f'; ni con {max_unidades} en paralelo' if max_unidades > 1 else ''
    return {'modulo': None,
            'motivo': f'ningún módulo PIT de {kv_mt:g} kV cubre {kva_diseno / 1000.0:.1f} MVA '
                      f'(el mayor de {kv_mt:g} kV es de {mayor:g} MVA{paralelo})'}


#: Potencias normalizadas de transformador de potencia (MVA), para dimensionar sin módulo en el libro (042:RF-33).
MVA_NORMALIZADOS = (5.0, 7.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 120.0)
#: Tensión de alta si ni el libro ni el perfil la dicen: la de subtransmisión de la distribución (se anota).
KV_ALTA_SUPUESTA = 60.0


def tasas_completas(tasas: Mapping[str, float | None], referencia: float) -> tuple[dict[str, float], list[str]]:
    """042:RF-41: la tasa de cada alimentador; al que no la tiene, la media de los demás o, sin ninguna, la de referencia."""
    con_dato = [float(t) for t in tasas.values() if t is not None]
    relleno = sum(con_dato) / len(con_dato) if con_dato else float(referencia)
    faltan = sorted(f for f, t in tasas.items() if t is None)
    avisos = ([f"Sin tasa de crecimiento medida en {', '.join(faltan)}: se usa {100 * relleno:.2f} %/año (042:RF-41)."] if faltan else [])
    return {f: (float(t) if t is not None else relleno) for f, t in tasas.items()}, avisos


def modulos_del_libro(capex: str | None, cfg: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """042:RF-33: los módulos del libro; sin libro o si no se puede leer, ninguno y se dice: la SET se dimensiona igual."""
    if not capex or not capex.strip():
        return [], ['Sin libro CAPEX: la SET se dimensiona con transformadores normalizados y su costo queda por confirmar (042:RF-33).']
    try:
        return leer_modulos_pit(Path(capex.strip().strip('"')), cfg), []
    except (SetNuevaError, OSError, KeyError, ValueError) as exc:
        return [], [f'No se pudo leer el libro CAPEX ({exc}): la SET se dimensiona con transformadores normalizados y su costo '
                    'queda por confirmar (042:RF-33).']


def modulo_deducido(modulos: Sequence[Mapping[str, Any]], kva_diseno: float, kv_mt: float,
                    kv_at: float | None = None, *, max_unidades: int = 1) -> dict[str, Any]:
    """042:RF-33: sin módulo en el libro, el menor transformador normalizado que cubre la potencia de diseño.

    Si no hay ninguno tan grande, en paralelo hasta ``max_unidades``, y si aun así no llega, más unidades: siempre hay
    solución, por confirmar. El costo sale del costo por MVA del módulo de potencia más parecida; sin ninguno, ``None``.
    """
    kva = max(float(kva_diseno), 1.0)
    mayor = MVA_NORMALIZADOS[-1]
    mva = next((m for m in MVA_NORMALIZADOS if m * 1000.0 >= kva), None)
    unidades = 1
    if mva is None:
        unidades = math.ceil(kva / (mayor * 1000.0))
        mva = mayor
    altas = sorted({float(m['kv_at']) for m in modulos if m.get('kv_at')})
    alta = kv_at or (altas[-1] if altas else KV_ALTA_SUPUESTA)
    con_costo = [m for m in modulos if m.get('costo') and m.get('mva')]
    parecido = min(con_costo, key=lambda m: (m['tipo'] != 'set', abs(float(m['mva']) - mva)), default=None)
    costo = float(parecido['costo']) / float(parecido['mva']) * mva * unidades if parecido else None
    motivo = (f'ningún módulo del libro cubre {kva / 1000.0:.1f} MVA a {kv_mt:g} kV: {unidades} × {mva:g} MVA normalizado'
              + (f', con el costo por MVA de «{parecido["descripcion"]}»' if parecido else ', sin costo')
              + ', por confirmar (042:RF-33)')
    return {'modulo': {'descripcion': f'SET nueva {alta:g}/{kv_mt:g} kV de {mva:g} MVA (deducida)', 'tipo': 'set', 'kv_at': alta,
                       'kv_mt': float(kv_mt), 'kv': [alta, float(kv_mt)], 'mva': mva, 'costo': costo, 'moneda': (parecido or {}).get('moneda', ''),
                       'unidades': unidades, 'mva_total': unidades * mva, 'costo_total': costo, 'por_confirmar': True},
            'motivo': motivo}


# =========================================================================== RF-1 a RF-3
def orden_de_cargas(cargas: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """De mayor a menor potencia (usuario, 2026-10-31); a igual kW, por nombre (042:RF-1)."""
    return sorted(cargas, key=lambda c: (-float(c.get('kw') or 0.0), str(c.get('sed') or '')))


def cuantas_caben(n: int, cabe) -> tuple[int, list[dict[str, Any]]]:
    """El mayor k ≤ n tal que las k primeras cargas caben en la red existente (042:RF-2, RF-3).

    Con más carga nunca es más fácil cumplir, así que basta buscar el límite. Se galopa desde
    abajo (1, 2, 4…) y se afina por bisección entre el último que cabe y el primero que no:
    una prueba que no cabe recorre todas las variantes en DIgSILENT (en NA203 + NA205, 22 min
    por alimentador) y una que cabe para en la primera que cumple. En NA203 + NA205
    (2026-11-01) cabían 3 de 35 y la bisección desde arriba hacía 4 pruebas que no cabían antes
    de llegar a ellas; galopando, una. Sin ninguna carga, k = 0 cabe sin probarlo.
    """
    pruebas: list[dict[str, Any]] = []

    def probar(k: int) -> bool:
        ok = bool(cabe(k))
        pruebas.append({'cargas': k, 'cabe': ok})
        return ok

    if n <= 0:
        return 0, pruebas
    bajo, k = 0, 1                          # cabe(bajo) siempre
    while True:
        k = min(k, n)
        if not probar(k):
            alto = k
            break
        bajo = k
        if k == n:
            return n, pruebas
        k *= 2
    while alto - bajo > 1:
        medio = (bajo + alto) // 2
        if probar(medio):
            bajo = medio
        else:
            alto = medio
    return bajo, pruebas


# =========================================================================== RF-6
def ramas_a_trasladar(red, cabecera: str, destino: set[str], kw_por_barra: Mapping[str, float], *,
                      max_ramas: int, existentes: set[str] | None = None) -> list[dict[str, Any]]:
    """Las ramas del alimentador que pasan a la SET nueva y el tramo donde se abren (042:RF-6).

    ``destino``: barras donde se conectan las cargas que ya no caben en la red existente. Se
    empieza por el menor número de ramas: el ancestro común más bajo de las cargas de cada salida
    de la cabecera. Con alimentadores nuevos de sobra (``max_ramas``), se parte la rama que más
    carga existente arrastra en sus subramas con cargas nuevas: el ancestro común de cargas
    repartidas por NA205 podía estar junto a la cabecera y llevarse el alimentador entero.

    ``existentes``: las barras de la red sin las cargas nuevas. La obra se lee y se graba con
    ellas apartadas, así que cada rama empieza en una de esas barras: la más cercana aguas
    arriba. NODE_T_SU_Predio_Lote_B-6A__CIMAS_MINERA lo crea la variación de su carga al partir
    SEC_1091_1046727, y la SET COPARA no se creaba (NA203 + NA205, 2026-11-01).
    """
    from .troncal import arbol

    a = arbol(red, cabecera)
    if cabecera in destino:
        raise SetNuevaError(f'la cabecera {cabecera} no puede pasar a otra SET (042:RF-6).')
    fuera = sorted(b for b in destino if b not in a.padre)
    if fuera:
        raise SetNuevaError(f"{', '.join(fuera)} no tiene camino cerrado desde la cabecera {cabecera}.")
    hijos: dict[str, list[str]] = {}
    for b in a.orden:
        if a.padre[b] is not None:
            hijos.setdefault(a.padre[b][0], []).append(b)

    def camino(b: str) -> list[str]:
        out = [b]
        while a.padre[out[-1]] is not None:
            out.append(a.padre[out[-1]][0])
        return out[::-1]                                     # de la cabecera a b

    def comun(barras: Sequence[str]) -> str:
        caminos = [camino(b) for b in barras]
        nodo = cabecera
        for nivel in zip(*caminos):
            if len(set(nivel)) > 1:
                break
            nodo = nivel[0]
        return nodo

    def subarbol(nodo: str) -> list[str]:
        out, pila = [], [nodo]
        while pila:
            u = pila.pop()
            out.append(u)
            pila.extend(hijos.get(u, ()))
        return sorted(out)

    def rama(nodo: str) -> dict[str, Any]:
        barras = subarbol(nodo)
        dentro = set(barras)
        return {'nodo': nodo, 'entrada': a.padre[nodo][1].nombre, 'barras': barras,
                'existente': existentes is None or nodo in existentes,
                'tramos': sorted(a.padre[b][1].nombre for b in barras if b != nodo),
                'destino': sorted(destino & dentro),
                'kw_existente': sum(float(kw_por_barra.get(b, 0.0)) for b in barras)}

    def partes(nodo: str, objetivos: set[str]) -> list[str]:
        """Las raíces en que se parte ``nodo``: el ancestro común de los objetivos de cada hijo."""
        grupos: dict[str, list[str]] = {}
        for b in sorted(objetivos):
            c = camino(b)
            grupos.setdefault(c[c.index(nodo) + 1], []).append(b)
        return [comun(g) for _h, g in sorted(grupos.items())]

    def existente(nodo: str) -> str:
        while existentes is not None and nodo not in existentes and a.padre[nodo] is not None:
            nodo = a.padre[nodo][0]
        if nodo == cabecera:
            raise SetNuevaError(f'la rama de las cargas nuevas solo se puede abrir en la cabecera {cabecera} '
                                '(042:RF-6).')
        return nodo

    def raices(nodos: Sequence[str]) -> list[str]:
        # Al subir, una raíz puede quedar aguas arriba de otra: queda solo la de arriba.
        subidas = list(dict.fromkeys(existente(n) for n in nodos))
        return [n for n in subidas if not any(o != n and o in camino(n) for o in subidas)]

    ramas = [rama(r) for r in raices(partes(cabecera, destino))]
    while len(ramas) < max_ramas:
        mejor = None
        for i, r in enumerate(ramas):
            if r['nodo'] in destino:
                continue                                     # su propia carga no se puede dejar
            nuevas = [rama(n) for n in raices(partes(r['nodo'], set(r['destino'])))]
            if any(n['nodo'] == r['nodo'] for n in nuevas) and len(nuevas) > 1:
                continue                                     # se partiría en sí misma y otra
            if len(nuevas) < 2 and nuevas and nuevas[0]['nodo'] == r['nodo']:
                continue
            if len(ramas) - 1 + len(nuevas) > max_ramas:
                continue
            ganancia = r['kw_existente'] - sum(n['kw_existente'] for n in nuevas)
            if ganancia > 0 and (mejor is None or (ganancia, -i) > (mejor[0], -mejor[1])):
                mejor = (ganancia, i, nuevas)
        if mejor is None:
            break
        _g, i, nuevas = mejor
        ramas = ramas[:i] + nuevas + ramas[i + 1:]
    return sorted(ramas, key=lambda r: r['nodo'])


# =========================================================================== RF-9
def _plano(puntos, origen):
    lat0, lon0 = origen
    k = math.cos(math.radians(lat0)) * M_POR_GRADO
    return [((lo - lon0) * k, (la - lat0) * M_POR_GRADO, w) for la, lo, w in puntos], k


def _weber(puntos_xy: Sequence[tuple[float, float, float]]) -> tuple[float, float]:
    """Mínimo de Σ w·d por Weiszfeld, desde el centro de gravedad."""
    total = sum(w for _x, _y, w in puntos_xy)
    if total <= 0:
        return 0.0, 0.0
    x = sum(px * w for px, _y, w in puntos_xy) / total
    y = sum(py * w for _x, py, w in puntos_xy) / total
    for _ in range(1000):
        nx = ny = den = 0.0
        for px, py, w in puntos_xy:
            d = math.hypot(px - x, py - y)
            if d < 1e-9 or w <= 0:
                continue
            nx, ny, den = nx + w * px / d, ny + w * py / d, den + w / d
        if den == 0:
            break
        nx, ny = nx / den, ny / den
        paso = math.hypot(nx - x, ny - y)
        x, y = nx, ny
        if paso < 1e-4:
            break
    return x, y


def _zonas(nuevas, zona_m, origen):
    """Celdas de ``zona_m`` con cargas nuevas: centro ponderado y probabilidad de crecer (∝ kW)."""
    xy, _k = _plano(nuevas, origen)
    celdas: dict[tuple[int, int], list] = {}
    for (x, y, _w), (la, lo, w) in zip(xy, nuevas):
        celdas.setdefault((math.floor(x / zona_m), math.floor(y / zona_m)), []).append((la, lo, w))
    total = sum(w for _la, _lo, w in nuevas)
    out = []
    for clave in sorted(celdas):
        c = celdas[clave]
        s = sum(w for _a, _b, w in c)
        if s <= 0 or total <= 0:
            continue
        out.append(((sum(a * w for a, _b, w in c) / s, sum(b * w for _a, b, w in c) / s), s / total))
    return out


def zonas_de_carga(cargas: Sequence[Mapping[str, Any]], radio_km: float | None) -> list[list[Mapping[str, Any]]]:
    """Las cargas agrupadas por zona: ninguna a más de ``radio_km`` del centro de carga de su zona (042:RF-21).

    Aglomerativo de mayor a menor potencia: cada carga va a la zona más cercana que la admite sin que ninguna
    de sus cargas quede fuera del radio; si ninguna, abre otra. Sin radio, una sola zona (P13). Sin GPS, la
    carga va sola, porque no se sabe dónde está.
    """
    if not radio_km:
        return [list(cargas)] if cargas else []
    limite = float(radio_km) * 1000.0

    def centro(grupo):
        w = sum(float(c.get('kw') or 0) or 1.0 for c in grupo)
        return (sum(float(c['lat']) * (float(c.get('kw') or 0) or 1.0) for c in grupo) / w,
                sum(float(c['lon']) * (float(c.get('kw') or 0) or 1.0) for c in grupo) / w)

    zonas: list[list[Mapping[str, Any]]] = []
    for c in sorted(cargas, key=lambda c: (-float(c.get('kw') or 0), str(c.get('sed')))):
        if c.get('lat') is None or c.get('lon') is None:
            zonas.append([c])
            continue
        mejor = None
        for z in zonas:
            if any(x.get('lat') is None for x in z):
                continue
            nueva = z + [c]
            cen = centro(nueva)
            if all(distancia_m(cen, (float(x['lat']), float(x['lon']))) <= limite for x in nueva):
                d = distancia_m(centro(z), (float(c['lat']), float(c['lon'])))
                if mejor is None or d < mejor[0]:
                    mejor = (d, z)
        if mejor is None:
            zonas.append([c])
        else:
            mejor[1].append(c)
    return zonas


def ubicacion_optima(existentes: Sequence[tuple[float, float, float]],
                     nuevas: Sequence[tuple[float, float, float]], *, incremento_kw: float,
                     zona_m: float, sorteos: int, semilla: int) -> dict[str, Any]:
    """El punto que minimiza el valor esperado de Σ P·d (042:RF-9).

    ``existentes``: (lat, lon, kW) de las SED de los tramos trasladados; ``nuevas``: las cargas
    nuevas del bloque; ``incremento_kw``: lo que crecerá la demanda en la vida útil, repartido por
    zonas de ``zona_m`` con probabilidad proporcional a la potencia nueva de cada una (usuario,
    2026-10-31: «hacer probabilidades a zona [donde] está la tendencia de crecimiento»).

    Como Σ P·d es lineal en P, su valor esperado es el de las potencias esperadas: el punto es el
    de Weber con ellas. Los sorteos dan además dónde caería en cada futuro posible, y su
    dispersión, que es la incertidumbre del punto.
    """
    todos = list(existentes) + list(nuevas)
    if not todos:
        raise SetNuevaError('sin cargas que atender no hay centro de carga para la SET nueva.')
    total = sum(w for _a, _b, w in todos) or 1.0
    origen = (sum(a * w for a, _b, w in todos) / total, sum(b * w for _a, b, w in todos) / total)
    zonas = _zonas(nuevas, zona_m, origen) if nuevas else []
    if not zonas:
        incremento_kw = 0.0
    esperados = todos + [(c[0], c[1], incremento_kw * p) for c, p in zonas]

    def a_grados(xy, k):
        return origen[0] + xy[1] / M_POR_GRADO, origen[1] + xy[0] / k

    xy, k = _plano(esperados, origen)
    lat, lon = a_grados(_weber(xy), k)
    rng = random.Random(semilla)
    puntos = []
    for _ in range(sorteos if incremento_kw > 0 else 0):
        reparto = [0.0] * len(zonas)
        for _t in range(TROZOS_POR_SORTEO):
            r, acum = rng.random(), 0.0
            for i, (_c, p) in enumerate(zonas):
                acum += p
                if r <= acum or i == len(zonas) - 1:
                    reparto[i] += incremento_kw / TROZOS_POR_SORTEO
                    break
        sorteo = todos + [(c[0], c[1], w) for (c, _p), w in zip(zonas, reparto) if w > 0]
        sxy, sk = _plano(sorteo, origen)
        puntos.append(a_grados(_weber(sxy), sk))
    dispersion = (math.sqrt(sum(distancia_m((lat, lon), p) ** 2 for p in puntos) / len(puntos))
                  if puntos else 0.0)
    return {'lat': lat, 'lon': lon, 'pesos': esperados, 'zonas': [
                {'lat': c[0], 'lon': c[1], 'probabilidad': p} for c, p in zonas],
            'incremento_kw': incremento_kw, 'sorteos': len(puntos), 'dispersion_m': dispersion,
            'puntos_sorteados': puntos}
