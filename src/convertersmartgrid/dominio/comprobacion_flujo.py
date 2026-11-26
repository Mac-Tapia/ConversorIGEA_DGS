"""Lo que un flujo o una calibración dijeron frente a lo que pasó (spec 081).

Tres mentiras del mismo día, las tres sin DIgSILENT de por medio una vez leídos los datos:

* un flujo que «converge» con una SED de una fase fuera de su ramal: su barra de baja a 0 p.u. y
  su carga sin consumir (081:RF-11, RF-12);
* «Calibración: done» con alimentadores ``NO_CONVERGE``: el trabajo solo miraba si había excepción
  (081:RF-17 a RF-19);
* un «Caso base» que dejó de converger tras calibrar, cuando el caso no debe cambiar (081:RF-33).

Este módulo solo lee y decide: la lectura de DIgSILENT la hace el guion, sin escribir. No para nada.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from convertersmartgrid.dominio.util import cuenta

#: Por debajo de esto una barra está a cero: un resultado de 0,01 p.u. no alimenta nada.
UMBRAL_PU = 0.01
#: Una carga con menos de 1 W no consume: lo que queda son restos del cálculo.
UMBRAL_MW = 1e-6
#: La baja tensión, en kV entre fases.
KV_BT = 1.0
_MAX_LISTA = 50


def comprobar_tras_flujo(barras: Iterable[Mapping[str, Any]], cargas: Iterable[Mapping[str, Any]],
                         *, umbral_pu: float = UMBRAL_PU, umbral_mw: float = UMBRAL_MW) -> dict[str, Any]:
    """Las barras de BT con carga a 0 p.u. y las cargas que no consumen (081:RF-11, RF-12).

    ``barras``: ``{nombre, uknom_kv, u_pu}``; ``cargas``: ``{nombre, barra, programada_mw,
    consumo_mw, en_servicio}``. Un resultado ausente cuenta como cero: DIgSILENT deja sin
    resultado lo que no alimenta.
    """
    cargas = list(cargas)
    con_carga = {c.get('barra') for c in cargas if c.get('en_servicio', True) and float(c.get('programada_mw') or 0) > umbral_mw}
    barras_cero = [b.get('nombre') for b in barras
                   if float(b.get('uknom_kv') or 0) < KV_BT and b.get('nombre') in con_carga
                   and float(b.get('u_pu') or 0) < umbral_pu]
    sin_consumo = [c.get('nombre') for c in cargas
                   if c.get('en_servicio', True) and float(c.get('programada_mw') or 0) > umbral_mw
                   and abs(float(c.get('consumo_mw') or 0)) < umbral_mw]
    return {'barras_bt_a_cero': len(barras_cero), 'cargas_sin_consumo': len(sin_consumo),
            'limpio': not barras_cero and not sin_consumo,
            'lista_barras': barras_cero[:_MAX_LISTA], 'lista_cargas': sin_consumo[:_MAX_LISTA]}


def texto_tras_flujo(tras: Mapping[str, Any]) -> str:
    return (f"{cuenta(tras.get('barras_bt_a_cero', 0), 'barra', 'barras')} de baja con carga a 0 p.u. y "
            f"{cuenta(tras.get('cargas_sin_consumo', 0), 'carga que no consume', 'cargas que no consumen')} aunque el flujo convergió")


#: Lo que no quedó calibrado aunque el trabajo termine: ``VIOLACION_FISICA`` converge y no cumple.
NO_QUEDO_BIEN = ('NO_CONVERGE', 'VIOLACION_FISICA', 'FALLO_VALIDACION_NATIVA', 'FALLO_VALIDACION_NATIVA_EN_EL_PROYECTO')


#: Los avisos que dicen por qué no quedó calibrado, antes que los informativos.
_ETIQUETAS_DE_FALLO = ('VALIDACION_FISICA', 'SOBRECARGA', 'NO cumple')
#: Avisos que nunca son el motivo de un fallo: dicen lo que se hizo, no lo que falló (081:RF-19, 26-11).
_AVISOS_INFORMATIVOS = ('con los parámetros de su ficha', 'es de su cliente: la fija se reparte')


def motivo_de_informe(informe: Mapping[str, Any]) -> str:
    """Por qué no quedó calibrado un alimentador (081:RF-19), en una línea para el Registro.

    CA191 + CHN192 (2026-11-09) quedó en FALLO_VALIDACION_NATIVA con ``motivo`` vacío: el
    Registro decía «no cumple la tolerancia: None» y el motivo era el primer aviso, el de
    los conductores con ficha, que es informativo. La causa estaba en el aviso
    VALIDACION_FISICA: SED fijas con más demanda que su transformador.
    """
    avisos = [str(a) for a in informe.get('avisos') or [] if a]
    de_fallo = next((a for e in _ETIQUETAS_DE_FALLO for a in avisos if a.startswith(e)), None)
    # 26-11: SM218 volvió a enseñar el aviso de las fichas: sin etiqueta de fallo se tomaba el primer aviso. El motivo
    # sale de los fallos de la validación y, sin ellos, nunca de un aviso informativo.
    utiles = [a for a in avisos if not any(i in a for i in _AVISOS_INFORMATIVOS)]
    estado = informe.get('status')
    return str(informe.get('error') or informe.get('motivo') or de_fallo or _texto_de_fallos(informe)
               or (utiles[0] if utiles else '') or (f'{estado}: vea su informe' if estado else 'vea su informe'))


def _texto_de_fallos(informe: Mapping[str, Any]) -> str:
    """081:RF-19: los fallos de la validación agrupados por tipo y error, con cuántas cargas y unas SED."""
    fallos = list(informe.get('fallos') or [])
    for clave in ('validacion_posterior_nativa', 'validacion_previa_nativa'):
        if not fallos:
            fallos = list((informe.get(clave) or {}).get('fallos') or [])
    grupos: dict[str, list[str]] = {}
    for f in fallos:
        d = f.get('detalle') if isinstance(f.get('detalle'), Mapping) else f
        tipo = str(d.get('tipo') or f.get('error') or 'FALLO')
        errores = '; '.join(str(e) for e in d.get('errores') or [])
        clave = f'{tipo}: {errores}' if errores else tipo
        grupos.setdefault(clave, []).append(str(d.get('sed') or f.get('sed') or ''))
    partes = []
    for clave, seds in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
        con = [s for s in seds if s]
        partes.append(f"{clave} en {len(seds)} {'carga' if len(seds) == 1 else 'cargas'}"
                      + (f" ({', '.join(con[:5])}{'…' if len(con) > 5 else ''})" if con else ''))
    return '; '.join(partes[:3])


_motivo = motivo_de_informe


def veredicto_calibracion(informes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """El estado verdadero de una calibración (081:RF-17 a RF-19), para el resultado del trabajo."""
    pendientes = [{'alimentador': i.get('feeder'), 'estado': i.get('status') or ('ERROR' if i.get('error') else None),
                   'motivo': _motivo(i)}
                  for i in informes if i.get('error') or i.get('status') in NO_QUEDO_BIEN]
    if not pendientes:
        return {'estado_trabajo': 'done', 'pendientes': []}
    alguno_no_converge = any(p['estado'] in ('NO_CONVERGE', 'ERROR') for p in pendientes)
    ninguno = len(pendientes) == len(informes)
    return {'estado_trabajo': 'no_converge' if ninguno and alguno_no_converge else 'parcial',
            'pendientes': pendientes}


def veredicto_importacion(ok: int, fallidos: int, sin_aceptar: int) -> dict[str, Any]:
    """El estado verdadero de una importación (081:RF-22): 078 los cuenta; el trabajo no lo decía."""
    if not fallidos and not sin_aceptar:
        return {'estado_trabajo': 'done'}
    return {'estado_trabajo': 'parcial' if ok else 'no_converge'}


# ---------------------------------------------------------------- huella del «Caso base»

def _carga_de_huella(c: Mapping[str, Any]) -> list[Any]:
    return [round(float(c.get('p_kw') or 0), 3), round(float(c.get('q_kvar') or 0), 3),
            round(float(c.get('escala') if c.get('escala') is not None else 1), 6), bool(c.get('en_servicio', True))]


def huella_de_caso(cargas: Iterable[Mapping[str, Any]], flujo: Mapping[str, Any] | None) -> dict[str, Any]:
    """La huella del «Caso base»: su flujo y sus cargas (081:RF-33). Determinista."""
    filas = {str(c.get('nombre')): _carga_de_huella(c) for c in cargas}
    flujo = dict(flujo or {})
    resumen = {'converge': flujo.get('converge'), 'return_code': flujo.get('return_code'),
               'kw': None if flujo.get('kw') is None else round(float(flujo['kw']), 1)}
    sello = hashlib.sha256(json.dumps({'cargas': filas, 'flujo': resumen}, sort_keys=True).encode()).hexdigest()
    return {'cargas': filas, 'flujo': resumen, 'sha256': sello}


def _mismo_flujo(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Dos flujos de la misma red no dan el mismo kW al decimal: paran dentro de su criterio de
    convergencia, y eso no puede sonar a «FALLO GRAVE» (086:RF-14). El mismo ruido que la validación del guion."""
    if a.get('converge') != b.get('converge') or a.get('return_code') != b.get('return_code'):
        return False
    ka, kb = a.get('kw'), b.get('kw')
    if ka is None or kb is None:
        return ka == kb
    return abs(ka - kb) <= max(1.0, abs(ka) * 1e-4)


def comparar_huellas(antes: Mapping[str, Any], despues: Mapping[str, Any]) -> dict[str, Any]:
    """Qué cambió en el «Caso base» (081:RF-34), y el plan para volver a su huella (081:RF-35)."""
    if antes.get('sha256') == despues.get('sha256'):
        return {'cambio': False, 'cambios': [], 'volver': []}
    cambios: list[str] = []
    volver: list[dict[str, Any]] = []
    a, d = antes.get('cargas') or {}, despues.get('cargas') or {}
    for nombre in sorted(set(a) | set(d)):
        if a.get(nombre) != d.get(nombre):
            cambios.append(f'carga {nombre}: {a.get(nombre)} → {d.get(nombre)}')
            if nombre in a:
                p, q, escala, servicio = a[nombre]
                volver.append({'carga': nombre, 'p_kw': p, 'q_kvar': q, 'escala': escala, 'en_servicio': servicio})
    if not cambios and _mismo_flujo(antes.get('flujo') or {}, despues.get('flujo') or {}):
        return {'cambio': False, 'cambios': [], 'volver': []}
    if antes.get('flujo') != despues.get('flujo'):
        cambios.insert(0, f"flujo: {antes.get('flujo')} → {despues.get('flujo')}")
    return {'cambio': True, 'cambios': cambios[:_MAX_LISTA], 'total': len(cambios), 'volver': volver}


def revisar_huellas(informes: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """El informe de una calibración trae ``caso_base_huella: {antes, despues}``; el fallo grave si cambió."""
    for informe in informes:
        huella = informe.get('caso_base_huella') or {}
        if huella.get('antes') and huella.get('despues'):
            comparacion = comparar_huellas(huella['antes'], huella['despues'])
            if comparacion['cambio']:
                return {'nivel': 'grave', **comparacion,
                        'texto': 'FALLO GRAVE: la calibración cambió el «Caso base», que no debe cambiar. '
                                 + '; '.join(comparacion['cambios'][:5])
                                 + '. Hay un plan para volver a su huella.'}
    return None
