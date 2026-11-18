"""Datos de los formatos F-001, F-002 y F-003 desde la red del área (107-T19b).

Pasa la ``RedArea`` (``pit/red_area``) a la entrada de ``plantillas.celdas_de_formato``. Lo que la red no trae
(código operativo, fecha de puesta en servicio, conductor, pesos, cable de guarda, estado…) queda vacío con su motivo:
no se inventa. Las cifras derivadas dicen su cálculo:
- Pcu% = vkr% (las pérdidas en el cobre a potencia nominal, en % de Sn, son la parte resistiva de la tensión de
  cortocircuito);
- Pfe% = P0 / Sn × 100;
- B = 2·π·f·C, solo si el perfil declara la frecuencia del sistema.
En los de tres devanados, P-S, S-T y P-T son las vk/vkr de primario-secundario, secundario-terciario y
primario-terciario (``vk_hv``, ``vk_mv`` y ``vk_lv`` de la red).

Para el F-001, el nivel de cada tensión sale de la regla ``pit.niveles_tension_kv`` del registro (num. 12.1.1 de la
Norma Tarifas). Una tensión que no está en la lista no se clasifica por aproximación: su elemento se nombra como hueco.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.pit import PitError
from ...aplicacion.pit.red_area import RedArea

__all__ = ['datos_f001', 'datos_f002', 'datos_f003']


def _niveles(registro: RegistroNormativo, fecha: str | None) -> dict[str, list[float]]:
    try:
        valor = registro.regla('pit.niveles_tension_kv', fecha).regla.valor
    except RegistroError as exc:
        raise PitError(f'falta la regla pit.niveles_tension_kv: sin ella no se clasifican las tensiones ({exc})') from exc
    return {nivel: [float(v) for v in kvs] for nivel, kvs in valor.items()}


def _nivel(kv: Any, niveles: Mapping[str, list[float]]) -> str | None:
    if not isinstance(kv, (int, float)):
        return None
    return next((n for n, kvs in niveles.items() if any(math.isclose(kv, v, rel_tol=1e-3) for v in kvs)), None)


def _barras(red: RedArea) -> dict[str, dict[str, Any]]:
    return {b['id']: b for b in red.de_tipo('barra')}


def _set(barras: Mapping[str, Mapping[str, Any]], barra: Any) -> str | None:
    return (barras.get(str(barra)) or {}).get('set')


def datos_f001(red: RedArea, registro: RegistroNormativo, fuente: Mapping[str, Any], fecha: str | None = None
               ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Por titular: km de líneas MAT y AT, y número de SET MAT/AT y AT/MT. Devuelve los datos y los elementos sin nivel."""
    niveles = _niveles(registro, fecha)
    barras = _barras(red)
    por_titular: dict[str, dict[str, Any]] = {}
    sin_nivel: list[dict[str, Any]] = []

    def fila(titular: str) -> dict[str, Any]:
        return por_titular.setdefault(titular, {'titular': titular, 'km_mat': 0.0, 'km_at': 0.0,
                                                '_sets_mat_at': set(), '_sets_at_mt': set()})

    for ln in red.de_tipo('linea'):
        kv = (barras.get(ln['desde']) or {}).get('kv')
        nivel = _nivel(kv, niveles)
        if nivel not in ('MAT', 'AT'):
            sin_nivel.append({'id': ln['id'], 'tipo': 'linea', 'kv': kv,
                              'causa': f'{kv} kV no está en los niveles MAT o AT de la regla 12.1.1'})
            continue
        fila(str(ln['titular']))['km_mat' if nivel == 'MAT' else 'km_at'] += float(ln['longitud_km'])
    for tipo, alto, bajo in (('trafo2', 'hv', 'lv'), ('trafo3', 'hv', 'mv')):
        for t in red.de_tipo(tipo):
            hv, lv = _nivel(barras.get(t[alto], {}).get('kv'), niveles), _nivel(barras.get(t[bajo], {}).get('kv'), niveles)
            sede = t.get('set') or _set(barras, t[alto])
            clase = {('MAT', 'AT'): '_sets_mat_at', ('AT', 'MT'): '_sets_at_mt'}.get((hv, lv))
            if clase is None or not sede:
                sin_nivel.append({'id': t['id'], 'tipo': tipo, 'causa': f'transformación {hv or "?"}/{lv or "?"} sin '
                                  'clase MAT/AT ni AT/MT en la regla 12.1.1, o sin SET'})
                continue
            fila(str(t['titular']))[clase].add(sede)
    filas = []
    for titular in sorted(por_titular):
        f = por_titular[titular]
        filas.append({'titular': titular, 'km_mat': round(f['km_mat'], 3), 'km_at': round(f['km_at'], 3),
                      'set_mat_at': len(f['_sets_mat_at']), 'set_at_mt': len(f['_sets_at_mt']),
                      '_motivos': {'_calculo:km_mat': 'suma de longitud_km de sus líneas MAT (regla 12.1.1)',
                                   '_calculo:km_at': 'suma de longitud_km de sus líneas AT (regla 12.1.1)',
                                   '_calculo:set_mat_at': 'SET distintas con transformación MAT/AT del titular',
                                   '_calculo:set_at_mt': 'SET distintas con transformación AT/MT del titular'}})
    return {'fuente': fuente, 'cabecera': {'area': red.area}, 'bloques': {'titulares': filas}}, sin_nivel


_TEXTOS_F002 = ('codigo', 'sistema', 'ternas', 'conductor', 'seccion_mm2', 'peso_kg_m', 'g_mho_per_km',
                'guarda_numero', 'guarda_tipo', 'guarda_seccion_mm2')


def datos_f002(red: RedArea, fuente: Mapping[str, Any], frecuencia_hz: float | None = None) -> dict[str, Any]:
    barras = _barras(red)
    filas = []
    for ln in red.de_tipo('linea'):
        desde, hasta = _set(barras, ln['desde']), _set(barras, ln['hasta'])
        f: dict[str, Any] = {k: ln.get(k) for k in _TEXTOS_F002}
        f.update(nombre=f'{desde}-{hasta}' if desde and hasta else ln['id'],
                 tension_kv=(barras.get(ln['desde']) or {}).get('kv'), longitud_km=ln['longitud_km'],
                 max_i_ka=ln['max_i_ka'], r_ohm_per_km=ln['r_ohm_per_km'], x_ohm_per_km=ln['x_ohm_per_km'])
        servicio = str(ln.get('fecha_servicio') or '')
        partes = servicio.split('-') if len(servicio) == 10 else []
        f.update(servicio_anio=partes[0] if partes else None, servicio_mes=partes[1] if partes else None,
                 servicio_dia=partes[2] if partes else None)
        motivos: dict[str, str] = {'_calculo:nombre': ('SET de envío - SET de recepción' if desde and hasta
                                                       else 'identificador de la línea: sus barras no dicen su SET'),
                                   '_calculo:tension_kv': 'tensión de la barra de envío'}
        if frecuencia_hz:
            f['b_mho_per_km'] = 2 * math.pi * float(frecuencia_hz) * float(ln['c_nf_per_km']) * 1e-9
            motivos['_calculo:b_mho_per_km'] = f'B = 2·π·{frecuencia_hz:g} Hz·C (C en nF/km de la red)'
        else:
            f['b_mho_per_km'] = None
            motivos['b_mho_per_km'] = 'el perfil no declara la frecuencia del sistema: B no se calcula'
        if not partes:
            for k in ('servicio_dia', 'servicio_mes', 'servicio_anio'):
                motivos[k] = 'la red del área no trae la fecha de puesta en servicio (AAAA-MM-DD)'
        f['_motivos'] = motivos
        filas.append(f)
    return {'fuente': fuente, 'cabecera': {'area': red.area}, 'bloques': {'lineas': filas}}


_TEXTOS_F003 = ('codigo', 'anio_fabricacion', 'utm', 'grupo_conexion', 'taps', 'tipo_regulacion', 'peso_total_kg',
                'peso_cobre_kg', 'asociado_compensador', 'estado')


def datos_f003(red: RedArea, fuente: Mapping[str, Any]) -> dict[str, Any]:
    barras = _barras(red)
    dos, tres, comp = [], [], []
    for t in red.de_tipo('trafo2'):
        f = {k: t.get(k) for k in _TEXTOS_F003}
        f.update(nombre=t['id'], set=t.get('set') or _set(barras, t['hv']), sn_mva=t['sn_mva'],
                 vn_hv_kv=t['vn_hv_kv'], vn_lv_kv=t['vn_lv_kv'], vk_percent=t['vk_percent'],
                 pcu_percent=t['vkr_percent'], pfe_percent=round(t['pfe_kw'] / (t['sn_mva'] * 1000) * 100, 6),
                 _motivos={'_calculo:pcu_percent': 'Pcu% = vkr% (parte resistiva de la tensión de cortocircuito)',
                           '_calculo:pfe_percent': 'Pfe% = P0 / Sn × 100'})
        dos.append(f)
    for t in red.de_tipo('trafo3'):
        f = {k: t.get(k) for k in _TEXTOS_F003}
        f.update(nombre=t['id'], set=t.get('set') or _set(barras, t['hv']), sn_hv_mva=t['sn_hv_mva'],
                 sn_mv_mva=t['sn_mv_mva'], sn_lv_mva=t['sn_lv_mva'], vn_hv_kv=t['vn_hv_kv'],
                 vn_mv_kv=t['vn_mv_kv'], vn_lv_kv=t['vn_lv_kv'], vk_ps_percent=t['vk_hv_percent'],
                 vk_st_percent=t['vk_mv_percent'], vk_pt_percent=t['vk_lv_percent'],
                 pcu_ps_percent=t['vkr_hv_percent'], pcu_st_percent=t['vkr_mv_percent'],
                 pcu_pt_percent=t['vkr_lv_percent'],
                 pfe_percent=round(t['pfe_kw'] / (t['sn_hv_mva'] * 1000) * 100, 6),
                 _motivos={'_calculo:vk_ps_percent': 'vk primario-secundario de la red (vk_hv)',
                           '_calculo:vk_st_percent': 'vk secundario-terciario de la red (vk_mv)',
                           '_calculo:vk_pt_percent': 'vk primario-terciario de la red (vk_lv)',
                           '_calculo:pfe_percent': 'Pfe% = P0 / Sn del primario × 100'})
        tres.append(f)
    for c in red.de_tipo('compensacion'):
        es_capacitor = str(c.get('tipo_compensacion') or '').strip().lower() == 'capacitor'
        f = {'tipo_compensacion': c.get('tipo_compensacion'), 'codigo': c.get('codigo'),
             'anio_fabricacion': c.get('anio_fabricacion'), 'utm': c.get('utm'),
             'set': c.get('set') or _set(barras, c['barra']), 'tension_kv': (barras.get(c['barra']) or {}).get('kv'),
             'q_capacitor_mvar': abs(c['q_mvar']) if es_capacitor else None,
             '_motivos': {} if es_capacitor else {
                 'q_capacitor_mvar': 'la red no dice que el equipo sea un capacitor: su potencia no se pone en esa '
                                     'columna'}}
        comp.append(f)
    return {'fuente': fuente, 'cabecera': {'area': red.area},
            'bloques': {'trafo2': dos, 'trafo3': tres, 'compensacion': comp}}
