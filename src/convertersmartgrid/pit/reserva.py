"""Transformadores de reserva compartida del área (107:RF-16, T24), con el procedimiento vigente del registro.

La regla de decisión sale del registro normativo (en el registro real, la RCD 094-2022-OS/CD):
- el horizonte de la potencia no servida (``pit.reserva.horizonte_pns_anios``);
- el costo de la energía no servida por falla, como costo de racionamiento × factor (``pit.reserva.costo_ens_falla``);
- el umbral de beneficio/costo, que se tiene que SUPERAR (``pit.reserva.beneficio_costo_minimo``);
- la exclusión de los trifásicos de más tensión que el límite cuyo traslado no es factible
  (``pit.reserva.excluye_trifasicos_mayor_kv``).

La ENS evitada por año de cada ubicación posible es el resultado del modelo de confiabilidad (Markov-Montecarlo,
num. 5.5 y 5.7 de la norma) y entra con su fuente y su huella: aquí no se simula. Si el registro no trae el modelo
oficial, se avisa. Sin una regla no se supone ninguna cifra: no se elige ninguna reserva y el aviso la nombra. Entre
las ubicaciones que superan el umbral se elige la de mayor beneficio neto (beneficio presente − inversión), que es el
óptimo económico que pide la norma; el empate se resuelve por B/C y por nombre, sin depender del orden de entrada.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError

__all__ = ['REGLAS', 'evaluar_reserva']

REGLAS = ('pit.reserva.horizonte_pns_anios', 'pit.reserva.costo_ens_falla', 'pit.reserva.beneficio_costo_minimo',
          'pit.reserva.excluye_trifasicos_mayor_kv')
_MODELO = 'pit.reserva.modelo_oficial'


def _numero(valor: Any, que: str, *, positivo: bool = False) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < 0 or (positivo and valor <= 0):
        cota = 'positivo' if positivo else 'no negativo'
        raise PitError(f'reserva: {que}={valor!r} tiene que ser un número {cota}')
    return float(valor)


def _reglas(registro: RegistroNormativo, fecha: str | None) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    valores, citas, avisos = {}, [], []
    for clave in REGLAS:
        try:
            rv = registro.regla(clave, fecha)
        except RegistroError:
            avisos.append(f'falta la regla {clave} en el registro normativo: no se elige ninguna reserva')
            continue
        valores[clave] = rv.regla.valor
        citas.append({'clave': clave, 'norma': rv.norma.acto, 'estado': rv.estado, 'obligatoria': rv.obligatoria,
                      'articulo_o_anexo': rv.regla.articulo_o_anexo, 'pagina': rv.regla.pagina,
                      'huella': rv.huella()})
    try:
        modelo = registro.regla(_MODELO, fecha).regla.valor
    except RegistroError:
        modelo = None  # justificado: sin la regla del modelo oficial se avisa abajo, igual que si no está transcrito
    if not (isinstance(modelo, Mapping) and modelo.get('transcrito')):
        avisos.append('el modelo oficial de confiabilidad de la norma no está en el registro: la ENS evitada sale de '
                      'la fuente declarada del área')
    return valores, citas, avisos


def _coherencia(area: Mapping[str, Any], fuente: Mapping[str, Any]) -> list[str]:
    """El resultado de confiabilidad tiene que ser de la misma área, los mismos años y la misma red que el estudio
    (condición del auditor ca, 2026-11-14): si no coincide o falta, no hay decisión y se dice la causa."""
    red = area.get('red') or {}
    if not str(red.get('huella') or '').strip():
        return ['el área no trae la huella de su red vigente: no se puede comprobar de qué red sale la ENS evitada']
    faltan = [c for c in ('area', 'anios', 'huella_red') if not fuente.get(c)]
    if faltan:
        return [(f'la fuente {fuente.get("nombre")} no declara {", ".join(faltan)}: no se sabe de qué área, años o '
                 'red sale la ENS evitada')]
    causas = []
    if str(fuente['area']) != str(red.get('area') or area.get('nombre')):
        causas.append(f'la ENS evitada es de otra área ({fuente["area"]}, el estudio es {red.get("area")})')
    if [int(a) for a in fuente['anios']] != [int(a) for a in red.get('anios') or ()]:
        causas.append(f'la ENS evitada es de otros años ({fuente["anios"]}, el estudio usa {red.get("anios")})')
    if str(fuente['huella_red']) != str(red['huella']):
        causas.append('la ENS evitada se calculó sobre otra red (su huella no es la de la red vigente)')
    return causas


def evaluar_reserva(registro: RegistroNormativo, area: Mapping[str, Any], fecha: str | None = None
                    ) -> dict[str, Any]:
    """Cada ubicación posible con su beneficio, su B/C y su motivo, y la reserva elegida (o ninguna, con el aviso).

    ``area``: ``nombre``, ``red`` (``area``, ``anios`` y ``huella`` de la red vigente del estudio), ``fuente``
    (``nombre`` y ``huella`` del resultado del modelo de confiabilidad, y el ``area``, los ``anios`` y la
    ``huella_red`` sobre los que se calculó),
    ``costo_racionamiento_usd_mwh`` (el de la fijación de tarifas en barra vigente), ``tasa`` de actualización y
    ``candidatos``: ``subestacion``, ``titular``, ``capacidad_mva``, ``tension_max_kv``, ``trifasico``,
    ``transportable``, ``inversion_usd`` (de la base de módulos estándar vigente) y ``ens_evitada_mwh`` por año.
    """
    fuente = area.get('fuente') or {}
    if not str(fuente.get('nombre') or '').strip() or not str(fuente.get('huella') or '').strip():
        raise PitError(f'reserva: el área necesita la fuente del modelo de confiabilidad con su huella ({fuente!r})')
    candidatos = list(area.get('candidatos') or ())
    if not candidatos:
        raise PitError('reserva: el área no trae candidatos (ubicaciones posibles de la reserva)')
    valores, citas, avisos = _reglas(registro, fecha)
    incoherencias = _coherencia(area, fuente)
    avisos += [f'sin decisión: {c}' for c in incoherencias]
    completo = all(c in valores for c in REGLAS) and not incoherencias
    tasa = _numero(area.get('tasa', 0.0), 'tasa')
    if completo:
        horizonte = int(valores['pit.reserva.horizonte_pns_anios'])
        factor = valores['pit.reserva.costo_ens_falla']
        costo_ens = (_numero(area.get('costo_racionamiento_usd_mwh'), 'costo_racionamiento_usd_mwh', positivo=True)
                     * float(factor['factor_numerador_usd_mwh']) / float(factor['factor_denominador_usd_mwh']))
        umbral = float(valores['pit.reserva.beneficio_costo_minimo'])
        limite_kv = float(valores['pit.reserva.excluye_trifasicos_mayor_kv'])
    salida = []
    for c in candidatos:
        nombre = str(c.get('subestacion') or '').strip()
        if not nombre:
            raise PitError(f'reserva: candidato sin subestación ({c!r})')
        inversion = _numero(c.get('inversion_usd'), f'{nombre}.inversion_usd', positivo=True)
        ens = [_numero(x, f'{nombre}.ens_evitada_mwh') for x in (c.get('ens_evitada_mwh') or ())]
        fila: dict[str, Any] = {'subestacion': nombre, 'titular': c.get('titular'), 'capacidad_mva': c.get('capacidad_mva'),
                'inversion_usd': inversion, 'excluida': False, 'viable': False, 'bc': None,
                'beneficio_vp_usd': None, 'motivo': ''}
        salida.append(fila)
        if not completo:
            fila['motivo'] = ('sin decisión: ' + '; '.join(incoherencias) if incoherencias
                              else 'sin las reglas del registro no se evalúa')
            continue
        if len(ens) != horizonte:
            raise PitError(f'reserva: {nombre} trae {len(ens)} años de ENS evitada y el horizonte del registro es '
                           f'de {horizonte}')
        tension = _numero(c.get('tension_max_kv'), f'{nombre}.tension_max_kv', positivo=True)
        if c.get('trifasico') and tension > limite_kv and not c.get('transportable'):
            fila.update(excluida=True, motivo=f'trifásico de {tension:g} kV (más de {limite_kv:g} kV) sin traslado '
                                              'factible: se analiza por criterios de demanda')
            continue
        beneficio = sum(e * costo_ens / (1 + tasa) ** i for i, e in enumerate(ens, start=1))
        bc = beneficio / inversion
        viable = bc > umbral
        fila.update(beneficio_vp_usd=beneficio, bc=bc, viable=viable,
                    motivo=(f'B/C {bc:.3f} > {umbral:g}' if viable else f'B/C {bc:.3f} no supera {umbral:g}'))
    viables = [f for f in salida if f['viable']]
    elegida = max(viables, key=lambda f: (f['beneficio_vp_usd'] - f['inversion_usd'], f['bc'], f['subestacion']),
                  default=None)
    return {'area': area.get('nombre'), 'fuente': {'nombre': fuente['nombre'], 'huella': fuente['huella']},
            'candidatos': salida, 'elegida': elegida, 'avisos': avisos, 'reglas': citas}
