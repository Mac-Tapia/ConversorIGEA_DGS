"""Alternativas de transmisión mutuamente excluyentes y su comparación (107:RF-5, 107:RF-8).

Cada alternativa es un conjunto de cambios sobre la red del área (altas con su costo, bajas), y todas se evalúan con
la **misma demanda y el mismo motor**, que el resultado fija con su huella. Se valora:

- la inversión con ``costos_fuentes.valorar_obra`` (ámbito ``transmision``), o con un módulo del libro CAPEX de la
  empresa (``set_nueva.leer_modulos_pit``), que es de la empresa y no oficial, y así se rotula;
- el COyM como porcentaje de la inversión (``pit.coym_pct`` del registro: la 217-2013 lo define así, art. 17.2);
- las pérdidas del flujo de cada año y, si el registro da su precio (``pit.precio_perdidas``) y sus horas
  equivalentes (``pit.horas_perdidas``), su valor;
- la confiabilidad según la matriz de motores (con el abierto, la potencia sin servir en el peor N-1);
- el valor presente con ``pide_economia.frc`` y ``van``, con la tasa (``pit.tasa_actualizacion``) y la vida útil
  (``pit.vida_util_anios``) del registro.

Lo que falta deja la alternativa **incompleta y fuera de la comparación**, nunca con un 0 (por eso no se usa
``costo_anual``, que suma como 0 lo que falta). Una regla que no obliga se usa como referencia y se dice (107:RF-8).
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .. import costos_fuentes
from ..pide_economia import frc, van
from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError
from .motores import capacidad, ejecutar
from .red_area import RedArea

__all__ = ['Comparacion', 'ResultadoAlternativa', 'aplicar', 'evaluar']

_REGLAS = ('pit.tasa_actualizacion', 'pit.vida_util_anios', 'pit.coym_pct')
_REGLAS_PERDIDAS = ('pit.precio_perdidas', 'pit.horas_perdidas')


@dataclass
class ResultadoAlternativa:
    nombre: str
    completa: bool
    motivos: list[str] = field(default_factory=list)
    inversion: dict[str, float] = field(default_factory=dict)
    inversion_detalle: dict[str, Any] = field(default_factory=dict)
    coym_anual: dict[str, float] = field(default_factory=dict)
    perdidas_mw: dict[int, float] = field(default_factory=dict)
    perdidas_valor: dict[int, float] = field(default_factory=dict)
    confiabilidad: dict[str, Any] = field(default_factory=dict)
    anualidad: dict[str, float] = field(default_factory=dict)
    valor_presente: dict[str, float] = field(default_factory=dict)
    violaciones: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Comparacion:
    motor: str
    demanda_huella: str
    reglas: dict[str, dict[str, Any]]
    alternativas: list[ResultadoAlternativa]
    orden: list[str]
    fuera_de_comparacion: list[str]
    avisos: list[str] = field(default_factory=list)
    cancelado: bool = False

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


def aplicar(red: RedArea, cambios: Iterable[Mapping[str, Any]]) -> RedArea:
    """La red con las altas y sin las bajas de una alternativa; la red de partida no cambia."""
    nueva = copy.deepcopy(red)
    for c in cambios:
        if c.get('accion') == 'baja':
            eid = str(c['elemento'])
            for tipo, lista in nueva.elementos.items():
                nueva.elementos[tipo] = [e for e in lista if e['id'] != eid]
        elif c.get('accion') == 'alta':
            e = dict(c['elemento'])
            e.setdefault('area', red.area)
            nueva.elementos.setdefault(str(e['tipo']), []).append(e)
        else:
            raise PitError(f'cambio con acción {c.get("accion")!r}: las alternativas dan altas y bajas')
    return nueva


def _regla(registro: RegistroNormativo, clave: str, fecha: str | None) -> dict[str, Any] | None:
    try:
        r = registro.regla(clave, fecha)
    except RegistroError:
        return None
    return {'clave': clave, 'valor': r.regla.valor, 'norma': r.norma.acto, 'estado': r.estado,
            'obligatoria': r.obligatoria, 'articulo_o_anexo': r.regla.articulo_o_anexo, 'pagina': r.regla.pagina}


def _inversion(cambios, tablas) -> tuple[dict[str, float], dict[str, Any], list[str]]:
    oficiales, motivos, empresa = [], [], []
    for c in cambios:
        if c.get('accion') != 'alta':
            continue
        e = c['elemento']
        if c.get('modulo_pit'):
            m = c['modulo_pit']
            if not m.get('moneda'):
                motivos.append(f'{e["id"]}: el módulo del libro CAPEX no dice su moneda')
                continue
            empresa.append({'elemento': e['id'], 'costo': float(m['costo']), 'moneda': m['moneda'],
                            'fuente': 'libro CAPEX de la empresa (no oficial)', 'descripcion': m.get('descripcion'),
                            'huella': str(m.get('huella') or '')})
        elif c.get('costo'):
            oficiales.append({'elemento': e['id'], 'ambito': 'transmision', **c['costo']})
        else:
            motivos.append(f'{e["id"]}: sin costo declarado (ni módulo estándar ni módulo del libro CAPEX)')
    detalle: dict[str, Any] = {'empresa': empresa}
    total: dict[str, float] = {}
    if oficiales:
        if 'transmision' not in tablas:
            motivos.append('sin fuente de costos de transmisión para los módulos estándar')
        else:
            v = costos_fuentes.valorar_obra(oficiales, {'transmision': tablas['transmision']})
            detalle['oficial'] = v
            motivos += [f'{x["elemento"]}: {x["motivo"]}' for x in v['sin_costo']]
            for moneda, monto in v['total_por_moneda'].items():
                total[moneda] = total.get(moneda, 0.0) + monto
    for x in empresa:
        total[x['moneda']] = total.get(x['moneda'], 0.0) + x['costo']
    if len(total) > 1:
        motivos.append(f'la inversión está en {sorted(total)}: sumarlas exigiría un tipo de cambio no declarado')
    return total, detalle, motivos


def _huella(datos: Any) -> str:
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def evaluar(red: RedArea, alternativas: Iterable[Mapping[str, Any]], demanda: Mapping[int, Mapping[str, tuple]],
            anios: Iterable[int], registro: RegistroNormativo, tablas: Mapping[str, Any], *,
            fecha: str | None = None, motor: str = 'abierto', cancel: threading.Event | None = None) -> Comparacion:
    """Evalúa las alternativas con la misma demanda y el mismo motor, y las ordena por valor presente."""
    anios = sorted(int(a) for a in anios)
    reglas = {c: r for c in _REGLAS + _REGLAS_PERDIDAS if (r := _regla(registro, c, fecha)) is not None}
    comp = Comparacion(motor, _huella({a: demanda.get(a) for a in anios}), reglas, [], [], [])
    for clave, r in sorted(reglas.items()):
        if not r['obligatoria']:
            comp.avisos.append(f'{clave} = {r["valor"]} de {r["norma"]} ({r["estado"]}) se usa como referencia, '
                               'no como obligatoria (107:RF-8)')
    valorar_perdidas = all(c in reglas for c in _REGLAS_PERDIDAS)
    if not valorar_perdidas:
        comp.avisos.append('el registro no da el precio ni las horas de las pérdidas: se comparan en MW, sin valorar')
    conf = capacidad(motor, 'confiabilidad')
    nombres = set()
    for alt in alternativas:
        if cancel is not None and cancel.is_set():
            comp.cancelado = True
            comp.avisos.append('evaluación cancelada entre alternativas')
            break
        nombre = str(alt['nombre'])
        if nombre in nombres:
            raise PitError(f'la alternativa {nombre!r} está dos veces')
        nombres.add(nombre)
        cambios = list(alt.get('cambios') or ())
        res = ResultadoAlternativa(nombre, True)
        res.inversion, res.inversion_detalle, motivos = _inversion(cambios, tablas)
        res.motivos += motivos
        res.motivos += [f'falta la regla {c} en el registro normativo' for c in _REGLAS if c not in reglas]
        red_alt = aplicar(red, cambios)
        peor = 0.0
        for anio in anios:
            cargas = demanda.get(anio)
            if not cargas:
                res.motivos.append(f'el año {anio} no tiene demanda: la alternativa no se evalúa en él')
                continue
            base = ejecutar('flujo', red_alt, cargas, motor=motor)['resultado']
            if not base.converge:
                res.motivos.append(f'el flujo del año {anio} no converge: {base.mensaje}')
                continue
            res.perdidas_mw[anio] = base.perdidas_mw
            if valorar_perdidas:
                res.perdidas_valor[anio] = (base.perdidas_mw * float(reglas['pit.horas_perdidas']['valor'])
                                            * float(reglas['pit.precio_perdidas']['valor']))
            for eid in [e['id'] for t in ('linea', 'trafo2', 'trafo3') for e in red_alt.de_tipo(t)]:
                r = ejecutar('n_1', red_alt, cargas, motor=motor, fuera=[eid])['resultado']
                peor = max(peor, r.p_sin_servir_mw if r.converge else float('inf'))
        res.confiabilidad = {'motor': motor, 'alcance': conf.alcance, 'texto': conf.texto,
                             'p_sin_servir_peor_n_1_mw': peor}
        if not res.motivos:
            tasa = float(reglas['pit.tasa_actualizacion']['valor'])
            vida = int(reglas['pit.vida_util_anios']['valor'])
            pct = float(reglas['pit.coym_pct']['valor']) / 100
            for moneda, ci in res.inversion.items():
                res.coym_anual[moneda] = ci * pct
                res.anualidad[moneda] = ci * frc(tasa, vida)
                perdidas = [res.perdidas_valor.get(a, 0.0) if valorar_perdidas else 0.0 for a in anios]
                # Año 0: la inversión y las pérdidas de ese año; desde el 1, COyM y pérdidas (11.3 de la 217-2013).
                flujos = [ci + perdidas[0]] + [res.coym_anual[moneda] + p for p in perdidas[1:]]
                res.valor_presente[moneda] = van(flujos, tasa)
        res.completa = not res.motivos
        comp.alternativas.append(res)
    completas = [a for a in comp.alternativas if a.completa]
    monedas = {m for a in completas for m in a.valor_presente}
    if len(monedas) > 1:
        comp.avisos.append(f'las alternativas completas están en {sorted(monedas)}: no se ordenan sin tipo de cambio')
        comp.orden = []
    else:
        moneda = next(iter(monedas), None)
        comp.orden = [a.nombre for a in sorted(completas, key=lambda a: (a.valor_presente.get(moneda, 0.0), a.nombre))]
    comp.fuera_de_comparacion = [a.nombre for a in comp.alternativas if not a.completa]
    return comp
