#!/usr/bin/env python
"""Aceptación nativa de las T4 de las specs 044, 045, 048 y 049: lo aplicado sigue tras reabrir.

Las pruebas no se conectan al DIgSILENT real (084:RF-21, ``pf_arnes.exigir_fuera_de_pruebas``). La
evidencia nativa se produce aquí, fuera de pytest, como el operador: la obra la define y la aplica la web
(``/obras``, ``/pf/obras/aplicar``) y las protecciones las comprueba la web (``/pf/protecciones/capacidades``);
cada relectura es un proceso nuevo de ``digital_twin_snapshot_pf.py`` (una sesión nueva de DIgSILENT por
el arnés, que desactiva y vuelve a activar el proyecto) y la obra se retira con ``obras_pf.py
--retirar-obras``. Este guion no abre DIgSILENT: no hay una segunda vía de acceso (044 T4, plan).

Lo que deja en ``--evidencia``: cada lectura e informe tal como salió, y ``aceptacion_nativa.json`` con la
huella SHA-256 de cada uno, la versión de DIgSILENT, el commit y los veredictos. Las pruebas
``tests/test_*_nativa*.py`` y ``tests/test_gemelo_fisico_nativo.py`` releen esos ficheros con la variable
``CSG_EVIDENCIA_NATIVA``, comprueban las huellas y vuelven a calcular los veredictos con las funciones de
aquí: no se fían del veredicto guardado.

    python tools/aceptacion_nativa.py --espacio ID --proyecto P --alimentador CA101 \\
        --planes CARPETA_DE_PLANES_DEL_ESPACIO --evidencia CARPETA obras --barra 14932 --q-kvar 300
    python tools/aceptacion_nativa.py ... protecciones

Códigos de salida: 0 evidencia escrita (los veredictos dicen qué cierra), 2 no se pudo, 3 sin la web.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
RAIZ = HERE.parents[1]
LECTURA = HERE.with_name('digital_twin_snapshot_pf.py')
OBRAS = HERE.with_name('obras_pf.py')
MANIFIESTO = 'aceptacion_nativa.json'
ESQUEMA = 'convertersmartgrid-aceptacion-nativa-v1'
#: Los cuatro papeles de caso de la spec 011; el contraste del gemelo los pide todos (045 T4).
ROLES = ('caso_base', 'sin_proyecto', 'con_proyecto', 'cargas_nuevas')
#: Dos lecturas de la misma red en sesiones distintas: el flujo de DIgSILENT converge a su error de nodo
#: (1 kVA por defecto), no al bit. Declarados antes de medir; más que esto es otra red, no ruido.
TOL_V_PU = 1e-4
TOL_KW = 1.0
TOL_Q_MVAR = 1e-4


# =========================================================================== huellas y lecturas
def sha256_de(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def nombre_de_barra(lectura: dict, ident: str | None) -> str | None:
    return (((lectura.get('topologia') or {}).get('barras') or {}).get(ident) or {}).get('nombre')


def inventario(lectura: dict) -> dict[str, Any]:
    """Bancos, centrales y demanda de una lectura: lo que no puede cambiar salvo la obra declarada (045:RF-11)."""
    grafo = (lectura.get('topologia') or {}).get('grafo') or {}
    bancos = {b['id']: {'barra': nombre_de_barra(lectura, b.get('nodo')), 'q_mvar': _num(b.get('q_mvar')),
                        'en_servicio': b.get('en_servicio'), 'escalones': _num(b.get('escalones'))}
              for b in grafo.get('bancos') or [] if b.get('id')}
    centrales = {g['id']: {'p_mw': _num(g.get('p_mw')), 'en_servicio': g.get('en_servicio')}
                 for g in grafo.get('generadores') or [] if g.get('id')}
    nodos = (grafo.get('nodos') or {}).values()
    return {'bancos': bancos, 'centrales': centrales,
            'demanda_mw': sum(_num(n.get('carga_p_mw')) or 0.0 for n in nodos),
            'demanda_efectiva_mw': sum(_num(n.get('carga_p_efectiva_mw')) or 0.0 for n in nodos),
            'sin_tension': len(((lectura.get('flujo') or {}).get('tensiones') or {}).get('sin_tension') or [])}


def releida(lectura: dict | None, rol: str, esperadas: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """La lectura es de DIgSILENT real, tras reabrir, del caso pedido y con lo esperado activo (RF-9)."""
    lectura = lectura or {}
    activas = set((lectura.get('topologia') or {}).get('variaciones_activas') or ())
    motivos = []
    if lectura.get('error'):
        motivos.append(str(lectura['error']))
    if not lectura.get('pf_version'):
        motivos.append('sin versión de DIgSILENT: no es una lectura nativa')
    if lectura.get('reopen_verified') is not True:
        motivos.append('no se verificó la reapertura')
    if (lectura.get('caso_nativo') or {}).get('rol') != rol:
        motivos.append(f'el caso leído no es «{rol}»')
    if not isinstance(lectura.get('flujo'), dict):
        motivos.append('sin flujo convergido tras reabrir')
    faltan = sorted(set(esperadas) - activas)
    if faltan:
        motivos.append(f'tras reabrir no están activas: {faltan}')
    return {'ok': not motivos, 'motivos': motivos}


def comparar_lecturas(a: dict, b: dict) -> dict[str, Any]:
    """Dos lecturas del mismo caso en sesiones distintas: la misma red, controles, tensiones y cabeceras."""
    from convertersmartgrid.digital_twin.contratos_fisicos import contexto_fisico

    fa, fb = contexto_fisico(a), contexto_fisico(b)
    ta = ((a.get('flujo') or {}).get('tensiones') or {}).get('valores') or {}
    tb = ((b.get('flujo') or {}).get('tensiones') or {}).get('valores') or {}
    comunes = set(ta) & set(tb)
    dv = max((abs(ta[k] - tb[k]) for k in comunes), default=None)
    ca = ((a.get('flujo') or {}).get('balance') or {}).get('valores', {}).get('cabeceras') or {}
    cb = ((b.get('flujo') or {}).get('balance') or {}).get('valores', {}).get('cabeceras') or {}
    dkw = max((abs((_num(ca.get(f)) or 0.0) - (_num(cb.get(f)) or 0.0)) for f in set(ca) | set(cb)), default=None)
    motivos = []
    for clave in ('topology_hash', 'controls_hash', 'scenario_hash'):
        if fa.get(clave) is None or fa.get(clave) != fb.get(clave):
            motivos.append(f'{clave} distinto o ausente')
    if set(ta) != set(tb):
        motivos.append(f'barras con tensión distintas: {len(set(ta) ^ set(tb))}')
    if dv is None or dv > TOL_V_PU:
        motivos.append(f'tensión: diferencia máxima {dv} p.u. (tolerancia {TOL_V_PU})')
    if dkw is None or dkw > TOL_KW:
        motivos.append(f'cabecera: diferencia máxima {dkw} kW (tolerancia {TOL_KW})')
    if inventario(a)['bancos'] != inventario(b)['bancos'] or inventario(a)['centrales'] != inventario(b)['centrales']:
        motivos.append('bancos o centrales distintos')
    return {'ok': not motivos, 'max_dv_pu': dv, 'max_dkw': dkw, 'barras': len(comunes), 'motivos': motivos}


def bancos_nuevos(antes: dict, despues: dict) -> dict[str, dict]:
    """Los bancos que tiene ``despues`` y no ``antes``: lo que añadió la obra."""
    a, d = inventario(antes)['bancos'], inventario(despues)['bancos']
    return {k: v for k, v in d.items() if k not in a}


def obra_presente(sin: dict, con: dict, barra: str, q_kvar: float) -> dict[str, Any]:
    """El banco de la obra está en «Con proyecto» reabierto, en su barra y con su potencia (044/048:RF-9)."""
    nuevos = bancos_nuevos(sin, con)
    hallados = [k for k, v in nuevos.items() if v['barra'] == barra and v['en_servicio'] is not False
                and v['q_mvar'] is not None and abs(v['q_mvar'] - q_kvar / 1000.0) <= TOL_Q_MVAR]
    viejos = {k: v for k, v in inventario(con)['bancos'].items() if k not in nuevos}
    cambiados = sorted(k for k, v in viejos.items() if inventario(sin)['bancos'].get(k) != v)
    motivos = ([] if len(hallados) == 1 else [f'bancos nuevos en {barra} con {q_kvar} kvar: {len(hallados)}'])
    if len(nuevos) != len(hallados):
        motivos.append(f'otros bancos nuevos no declarados: {sorted(set(nuevos) - set(hallados))}')
    if cambiados:
        motivos.append(f'bancos existentes cambiados: {cambiados}')
    return {'ok': not motivos, 'banco': hallados[0] if len(hallados) == 1 else None, 'motivos': motivos}


# =========================================================================== veredictos
def veredicto_048(informe: dict, antes: dict[str, dict], despues: dict[str, dict], con: dict, *,
                  barra: str, q_kvar: float, variacion: str, juicio: dict | None) -> dict[str, Any]:
    """048:RF-9: la obra persiste en su variación, la referencia no cambia y la demanda no cae."""
    pers = informe.get('persistencia') or {}
    sin_d = despues.get('sin_proyecto') or {}
    inv_con, inv_sin = inventario(con), inventario(sin_d)
    checks = {
        'persistencia_del_guion': {'ok': pers.get('ok') is True and pers.get('reabierto') is True,
                                   'motivos': [] if pers.get('ok') else [str(pers.get('error') or pers)]},
        'con_proyecto_releido': releida(con, 'con_proyecto', [variacion]),
        'obra_presente': obra_presente(sin_d, con, barra, q_kvar),
        'demanda_atendida': {
            'ok': abs(inv_con['demanda_mw'] - inv_sin['demanda_mw']) * 1000.0 <= TOL_KW
            and inv_con['sin_tension'] <= inv_sin['sin_tension'],
            'con_mw': inv_con['demanda_mw'], 'sin_mw': inv_sin['demanda_mw'],
            'sin_tension_con': inv_con['sin_tension'], 'sin_tension_sin': inv_sin['sin_tension']},
    }
    for rol in ('caso_base', 'sin_proyecto'):
        checks[f'{rol}_intacto'] = comparar_lecturas(antes.get(rol) or {}, despues.get(rol) or {})
    persiste = all(c['ok'] for c in checks.values())
    # Convergencia sin tensión o cargabilidad admisibles no cierra la tarea (048 T4, plan).
    admisible = bool(juicio) and juicio.get('clase') == 'accepted'
    return {'checks': checks, 'persiste': persiste, 'admisible': admisible, 'juicio': juicio,
            'cerrable': persiste and admisible}


def prediccion_fisica(lectura: dict, kv_min: float) -> dict[str, Any]:
    """Lo que predice el gemelo físico (flujo mallado, en la CPU) para la red leída, en las barras de media."""
    from convertersmartgrid.digital_twin.oraculo import ModeloMallado, muestra

    grafo = (lectura.get('topologia') or {}).get('grafo') or {}
    tensiones = ((lectura.get('flujo') or {}).get('tensiones') or {}).get('valores') or {}
    if not grafo.get('nodos') or not tensiones:
        # Sin flujo convergido tras reabrir no hay con qué contrastar («Con proyecto» de CA101 + PE104,
        # 2026-11-07: 687 barras sin tensión); se dice, no se inventa una predicción.
        return {'v_min': None, 'perdidas_kw': None, 'fuera_de_dominio': True, 'convergio': False,
                'motivos': ['la lectura no trae grafo o tensiones de DIgSILENT'], 'barras_contrastadas': 0,
                'mae_v_pu': None, 'max_error_v_pu': None}
    m = muestra(grafo, tensiones)
    p = ModeloMallado().predecir_muestra(m)
    barras = (lectura.get('topologia') or {}).get('barras') or {}
    media = [i for i, n in enumerate(m.ids)
             if m.alimentado[i] and float((barras.get(n) or {}).get('kv') or 0.0) >= kv_min]
    vmin = min((float(p['v'][i]) for i in media), default=None) if p.get('convergio') else None
    errores = [abs(float(p['v'][i]) - float(m.v[i])) for i in range(len(m.ids)) if m.mascara[i]] if p.get('convergio') else []
    return {'v_min': vmin, 'perdidas_kw': p['perdidas_mw'] * 1000.0 if p.get('convergio') else None,
            'fuera_de_dominio': bool(p.get('fuera_de_dominio')), 'motivos': list(p.get('motivos') or []),
            'convergio': bool(p.get('convergio')), 'barras_contrastadas': len(errores),
            'mae_v_pu': sum(errores) / len(errores) if errores else None,
            'max_error_v_pu': max(errores) if errores else None}


def veredicto_044(con: dict, sin: dict, base: dict, *, variacion: str, barra: str, q_kvar: float,
                  limites: Any, tolerancias: dict) -> dict[str, Any]:
    """044:RF-9: el diseño confirmado se relee tras una sesión nueva y la decisión sale de esa relectura.

    Un caso que converge con violaciones se rechaza por la evaluación eléctrica, no por converger.
    """
    from convertersmartgrid.digital_twin.episode import Caso
    from convertersmartgrid.digital_twin.evaluacion import evaluar
    from convertersmartgrid.digital_twin.evolutivo import verificar_top_k
    from convertersmartgrid.digital_twin.integration import (
        contexto_de_lectura,
        medicion_de_lecturas,
    )
    from convertersmartgrid.optimizacion_oraculo import KV_MEDIA_MIN

    reabierto = releida(con, 'con_proyecto', [variacion])
    presente = obra_presente(sin, con, barra, q_kvar)
    medicion = medicion_de_lecturas(con, sin, base, aplicadas=[variacion], kv_min=KV_MEDIA_MIN)
    pred = prediccion_fisica(con, KV_MEDIA_MIN)
    alternativa = {'codigo': f'banco {q_kvar:g} kvar en {barra}', 'v_min': pred['v_min'],
                   'perdidas_kw': pred['perdidas_kw'], 'fuera_de_dominio': pred['fuera_de_dominio']}
    esperado = contexto_de_lectura(con, base, esperado=True)
    r = verificar_top_k([alternativa], lambda _alt: medicion, contexto=esperado, limites=limites, **tolerancias)
    juicio = None
    if medicion.get('flujo') is not None:
        j = evaluar(Caso.CON_PROYECTO, medicion['flujo'], convergio=True, revertido=medicion['revertido'],
                    reabierto=medicion['reabierto'], limites=limites, calibracion_cuadra=None,
                    referencia=(medicion.get('referencia') or {}).get('flujo'))
        juicio = {'clase': j.clase.value, 'violaciones': list(j.violaciones), 'bloqueos': list(j.bloqueos)}
    perdidas = _num(medicion.get('perdidas_kw'))
    resultados = {'ok': medicion.get('converge') is True and _num(medicion.get('v_min')) is not None
                  and perdidas is not None and perdidas >= 0,
                  'v_min_pu': medicion.get('v_min'), 'perdidas_kw': perdidas}
    descartada = next(iter(r.get('descartadas') or []), {})
    rechazo_electrico = (not r.get('verificada') and juicio is not None and juicio['clase'] != 'accepted'
                         and bool(juicio['violaciones']))
    aceptada = bool(r.get('verificada')) and juicio is not None and juicio['clase'] == 'accepted'
    return {'reabierto': reabierto, 'obra_presente': presente, 'resultados': resultados, 'prediccion': pred,
            'top_k': {'verificada': bool(r.get('verificada')), 'motivo': descartada.get('motivo')},
            'juicio': juicio, 'rechazo_electrico': rechazo_electrico, 'aceptada': aceptada,
            # Se relee tras una sesión nueva y la decisión es coherente con lo releído: aceptada solo si
            # la evaluación eléctrica la acepta, y rechazada por ella cuando converge con violaciones.
            'cerrable': reabierto['ok'] and presente['ok'] and resultados['ok'] and (aceptada or rechazo_electrico)}


def veredicto_045(despues: dict[str, dict], antes: dict[str, dict], *, pedidos: list[str],
                  bancos_declarados: list[str], tolerancia_v_pu: float, variacion: str) -> dict[str, Any]:
    """045:RF-11: contraste del gemelo físico con DIgSILENT en cada papel pedido, del mismo alcance."""
    from convertersmartgrid.optimizacion_oraculo import KV_MEDIA_MIN

    roles = {}
    for rol in pedidos:
        lectura = despues.get(rol) or {}
        rel = releida(lectura, rol, [variacion] if rol == 'con_proyecto' else [])
        contraste = prediccion_fisica(lectura, KV_MEDIA_MIN) if rel['ok'] else None
        roles[rol] = {'releido': rel, 'contraste': contraste,
                      'dentro_de_tolerancia': bool(contraste and contraste['mae_v_pu'] is not None
                                                   and contraste['max_error_v_pu'] <= tolerancia_v_pu)}
    inv = {}
    for rol in ('caso_base', 'sin_proyecto'):
        if antes.get(rol) and despues.get(rol):
            a, d = inventario(antes[rol]), inventario(despues[rol])
            inv[rol] = {'ok': a['bancos'] == d['bancos'] and a['centrales'] == d['centrales'],
                        'bancos': len(d['bancos']), 'centrales': len(d['centrales'])}
    if antes.get('sin_proyecto') and despues.get('con_proyecto'):
        nuevos = bancos_nuevos(antes['sin_proyecto'], despues['con_proyecto'])
        a, d = inventario(antes['sin_proyecto']), inventario(despues['con_proyecto'])
        viejos = {k: v for k, v in d['bancos'].items() if k not in nuevos}
        inv['con_proyecto'] = {'ok': viejos == a['bancos'] and sorted(nuevos) == sorted(bancos_declarados)
                               and d['centrales'] == a['centrales'],
                               'bancos': len(d['bancos']), 'nuevos': sorted(nuevos), 'centrales': len(d['centrales'])}
    releidos = all(r['releido']['ok'] for r in roles.values())
    inventario_ok = bool(inv) and all(v['ok'] for v in inv.values())
    return {'roles': roles, 'inventario': inv, 'releidos': releidos, 'inventario_ok': inventario_ok,
            'cerrable': releidos and inventario_ok and all(r['contraste'] for r in roles.values())}


def veredicto_049(capacidades: dict, estado: dict) -> dict[str, Any]:
    """049:RF-9: sin dispositivos con fichas no hay ajustes que aplicar ni releer; se guarda la lista de bloqueo."""
    informe = capacidades.get('informe') or capacidades
    disp = estado.get('disponibilidad') or {}
    nativo = bool(informe.get('version') or informe.get('pf_version'))
    bloqueo = list(disp.get('faltan') or []) + list(disp.get('bloqueos') or [])
    dispositivos = {c: (d or {}).get('cuantos') for c, d in (informe.get('clases') or {}).items()}
    comandos = {c: {'existe': (d or {}).get('existe'), 'ejecuta': (d or {}).get('ejecuta'),
                    'atributos': (d or {}).get('atributos')} for c, d in (informe.get('comandos') or {}).items()}
    return {'nativo': nativo, 'version': informe.get('version'), 'disponible': bool(disp.get('disponible')),
            'bloqueo': bloqueo, 'dispositivos': dispositivos, 'comandos': comandos,
            # Ni dobles, ni gráficos inventados, ni un ComShc ejecutado cierran la T4 (049, plan).
            'cerrable': False}


# =========================================================================== ejecución
def _correr(args: list[str], log: Path) -> tuple[int, int]:
    env = {**os.environ, 'PYTHONPATH': str(RAIZ / 'src')}
    with log.open('w', encoding='utf-8') as salida:
        proc = subprocess.Popen([sys.executable, *args], stdout=salida, stderr=subprocess.STDOUT, env=env,
                                cwd=str(RAIZ))
        return proc.wait(timeout=3600), proc.pid


def plan_firmado(planes: Path, proyecto: str, feeders: list[str], prefijo: str) -> dict:
    """El plan más reciente que la web firmó para este proyecto y alimentadores: su contexto nativo."""
    for ruta in sorted(planes.glob(f'{prefijo}_*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        plan = json.loads(ruta.read_text(encoding='utf-8'))
        ctx = plan.get('native_action_context') or {}
        if plan.get('project') == proyecto and list(ctx.get('feeders') or []) == sorted(feeders):
            return plan
    raise SystemExit(f'ERROR: no hay un plan «{prefijo}» firmado por la web para {proyecto} {feeders} en {planes}')


def leer(base: dict, rol: str, esperadas: list[str], carpeta: Path, etiqueta: str) -> dict:
    """Una lectura de ``rol`` en un proceso nuevo (una sesión nueva de DIgSILENT por el arnés)."""
    plan = {k: base[k] for k in ('project', 'folder', 'feeders', 'native_action_context', 'periodo',
                                 'criterio_fijas', 'anio_casos') if base.get(k) is not None}
    plan.update(case=rol, variaciones_esperadas=list(esperadas), huellas_gps_de=[])
    if isinstance(plan.get('periodo'), dict):
        # La lectura tras la calibración guarda el cruce de periodos de la 013 ({"maxima": "2026-07", …});
        # el contexto del experimento es un mes, el de la máxima (043, ``ContextoExperimento.period``).
        plan['periodo'] = plan['periodo'].get('maxima')
    ruta_plan = carpeta / f'plan_{etiqueta}_{rol}.json'
    ruta_plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    salida = carpeta / f'lectura_{etiqueta}_{rol}.json'
    print(f'Lectura «{rol}» ({etiqueta}) en un proceso nuevo…', flush=True)
    rc = pid = None
    try:
        rc, pid = _correr([str(LECTURA), '--plan', str(ruta_plan), '--output-json', str(salida)],
                          carpeta / f'lectura_{etiqueta}_{rol}.log')
        lectura = (json.loads(salida.read_text(encoding='utf-8')) if salida.is_file()
                   else {'error': f'sin lectura (código {rc})'})
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # El fichero original, incluso incompleto, queda para revisar; no se fabrica una lectura nativa.
        lectura = {'error': f'lectura no disponible: {type(exc).__name__}: {exc}'}
    print(f'  código {rc}, proceso {pid}', flush=True)
    return {'ruta': salida.name, 'rc': rc, 'pid': pid, 'lectura': lectura}


def referencia_valida(resultado: dict, rol: str, base: dict) -> dict:
    """044/048:RF-9: reapertura, identidad pedida y referencia física completa antes de escribir."""
    from convertersmartgrid.estudios_pf import CASO_BASE, SIN_PROYECTO

    motivos = []
    if resultado.get('rc') != 0:
        motivos.append(f"lectura terminó con código {resultado.get('rc')}")
    pid = resultado.get('pid')
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        motivos.append('sin identidad del proceso de relectura')
    datos = resultado.get('lectura')
    if not isinstance(datos, dict):
        motivos.append('el informe de lectura no es un objeto')
    else:
        try:
            motivos += releida(datos, rol)['motivos']
            for clave in ('project', 'folder'):
                if datos.get(clave) != base.get(clave):
                    motivos.append(f'{clave} no corresponde al plan')
            if sorted(datos.get('feeders') or []) != sorted(base.get('feeders') or []):
                motivos.append('alimentadores no corresponden al plan')
            caso = datos.get('caso_nativo') or {}
            nombre = {'caso_base': CASO_BASE, 'sin_proyecto': SIN_PROYECTO}[rol]
            nombre += f" {base['anio_casos']}" if base.get('anio_casos') is not None else ''
            if caso.get('nombre') != nombre or not str(caso.get('id') or '').startswith('IntCase:'):
                motivos.append('identidad del caso nativo ausente o distinta de la pedida')
            propia = comparar_lecturas(datos, datos)
            motivos += propia['motivos']
            flujo = datos.get('flujo') or {}
            tensiones = (flujo.get('tensiones') or {}).get('valores') or {}
            cabeceras = ((flujo.get('balance') or {}).get('valores') or {}).get('cabeceras') or {}
            if any(_num(v) is None for v in (*tensiones.values(), *cabeceras.values())):
                motivos.append('la referencia contiene tensiones o cabeceras no finitas')
            if _num(propia.get('max_dv_pu')) is None:
                motivos.append('la referencia no tiene tensiones finitas comparables')
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            motivos.append(f'informe de lectura inválido: {type(exc).__name__}: {exc}')
    return {'ok': not motivos, 'motivos': motivos,
            **{k: resultado.get(k) for k in ('ruta', 'rc', 'pid')}}


def referencias_conservadas(antes: dict, despues: dict, base: dict) -> dict:
    """048:RF-9: misma comprobación al retirar y al recalcular los veredictos de los archivos."""
    checks = {}
    for rol in ('caso_base', 'sin_proyecto'):
        previa, posterior = antes.get(rol) or {}, despues.get(rol) or {}
        check = referencia_valida(posterior, rol, base)
        previa_valida = referencia_valida(previa, rol, base)
        if not previa_valida['ok']:
            check['ok'] = False
            check['motivos'] += ['referencia anterior: ' + m for m in previa_valida['motivos']]
        if check['ok']:
            comparacion = comparar_lecturas(previa['lectura'], posterior['lectura'])
            check['ok'] = comparacion['ok']
            check['motivos'] += comparacion['motivos']
            check['comparacion'] = comparacion
        checks[rol] = check
    return checks


def _web(url: str, espacio: str):
    sys.path.insert(0, str(HERE.parent))
    from sistema_web import Web

    return Web(url, espacio)


def _commit() -> str | None:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=RAIZ, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - sin git la evidencia sigue valiendo por sus huellas
        return None


def etapa_obras(args, carpeta: Path) -> dict:
    web = _web(args.url, args.espacio)
    feeders = [args.alimentador]
    base_lectura = plan_firmado(args.planes, args.proyecto, feeders, 'gemelo_lectura')
    lecturas: dict[str, dict] = {}
    for rol in ('caso_base', 'sin_proyecto'):
        lecturas[f'antes/{rol}'] = leer(base_lectura, rol, [], carpeta, 'antes')
    datos = {'clase': 'condensador', 'alimentador': args.alimentador, 'casos': ['Con proyecto'],
             'barra': args.barra, 'q_kvar': args.q_kvar, 'escalones': 1}
    referencias = {rol: referencia_valida(lecturas[f'antes/{rol}'], rol, base_lectura)
                   for rol in ('caso_base', 'sin_proyecto')}
    motivos = [f'{rol}: {m}' for rol, ref in referencias.items() for m in ref['motivos']]
    preflight = {'ok': not motivos, 'motivos': motivos, 'referencias': referencias}
    if not preflight['ok']:
        return {'obra': datos, 'trabajo': 'abortado_preflight', 'preflight': preflight, 'retiro': None,
                'lecturas': {k: {kk: vv for kk, vv in v.items() if kk != 'lectura'}
                             for k, v in lecturas.items()}}
    if args.guion_local:
        # La web ejecuta los guiones de su propia copia; un arreglo de ``tools/`` sin integrar se prueba con el
        # mismo guion y el plan que firmó la web (2026-11-07: la fecha de «Con proyecto», 081:RF-78).
        plan_obras = plan_firmado(args.planes, args.proyecto, feeders, 'obras_aplicacion')
        plan = {**{k: v for k, v in plan_obras.items() if k != 'obras'}, 'obras': [datos]}
        (carpeta / 'plan_aplicar.json').write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n',
                                                   encoding='utf-8')
        print('Aplicar la obra con tools/obras_pf.py en un proceso nuevo…', flush=True)
        rc, pid = _correr([str(OBRAS), '--plan', str(carpeta / 'plan_aplicar.json'), '--output-json',
                           str(carpeta / 'obras_aplicar_informe.json')], carpeta / 'obras_aplicar.log')
        informe = cargar(carpeta, 'obras_aplicar_informe.json') if (carpeta / 'obras_aplicar_informe.json').is_file() else {}
        obra = {'id': 'guion_local', **datos}
        trabajo = {'status': 'done' if rc == 0 else f'codigo {rc}', 'pid': pid, 'result': {'informe': informe}}
    else:
        obra = web._pedir('POST', f'/api/workspaces/{args.espacio}/obras', json=datos)
        print(f"Obra {obra['id']}: aplicar por la web…", flush=True)
        trabajo = web.esperar(web.post('/pf/obras/aplicar', json={'project': args.proyecto, 'feeders': feeders,
                                                                  'ids': [obra['id']]}), limite_s=3 * 3600)
    (carpeta / 'obras_aplicar.json').write_text(json.dumps(trabajo, indent=2, ensure_ascii=False, default=str) + '\n',
                                                 encoding='utf-8')
    informe = (trabajo.get('result') or {}).get('informe') or {}
    variacion = next((f.get('variacion') for f in informe.get('obras') or [] if f.get('variacion')), None)
    print(f"  {trabajo.get('status')}; variación {variacion}", flush=True)
    for rol in ROLES:
        lecturas[f'despues/{rol}'] = leer(base_lectura, rol, [variacion] if rol == 'con_proyecto' and variacion else [],
                                          carpeta, 'despues')
    retiro = None
    if variacion:
        plan_obras = plan_firmado(args.planes, args.proyecto, feeders, 'obras_aplicacion')
        plan_ret = {k: plan_obras[k] for k in ('project', 'folder', 'feeders', 'native_action_context', 'anio_casos')
                    if plan_obras.get(k) is not None}
        plan_ret['variaciones'] = [variacion]
        (carpeta / 'plan_retirar.json').write_text(json.dumps(plan_ret, indent=2, ensure_ascii=False) + '\n',
                                                   encoding='utf-8')
        print('Retirar la obra en un proceso nuevo…', flush=True)
        rc, pid = _correr([str(OBRAS), '--retirar-obras', '--plan', str(carpeta / 'plan_retirar.json'),
                           '--output-json', str(carpeta / 'obras_retirar.json')], carpeta / 'obras_retirar.log')
        informe_retiro = cargar(carpeta, 'obras_retirar.json') if (carpeta / 'obras_retirar.json').is_file() else {}
        retiro = {'rc': rc, 'pid': pid, 'ruta': 'obras_retirar.json', 'pedidas': [variacion],
                  'ok': rc == 0 and informe_retiro.get('retiradas') == [variacion]}
        lecturas['retirada/con_proyecto'] = leer(base_lectura, 'con_proyecto', [], carpeta, 'retirada')
        for rol in ('caso_base', 'sin_proyecto'):
            lecturas[f'retirada/{rol}'] = leer(base_lectura, rol, [], carpeta, 'retirada')
        referencias_retiro = referencias_conservadas(
            {r: lecturas[f'antes/{r}'] for r in ('caso_base', 'sin_proyecto')},
            {r: lecturas[f'retirada/{r}'] for r in ('caso_base', 'sin_proyecto')}, base_lectura)
        retiro['referencias'] = referencias_retiro
        retiro['ok'] = retiro['ok'] and all(c['ok'] for c in referencias_retiro.values())
    return {'obra': {**obra, 'variacion': variacion}, 'trabajo': trabajo.get('status'), 'preflight': preflight, 'lecturas': {
        k: {kk: vv for kk, vv in v.items() if kk != 'lectura'} for k, v in lecturas.items()}, 'retiro': retiro,
        'base': {k: v for k, v in cargar(carpeta, 'plan_despues_con_proyecto.json').items()
                 if k in ('periodo', 'criterio_fijas', 'anio_casos')}}


def etapa_protecciones(args, carpeta: Path) -> dict:
    web = _web(args.url, args.espacio)
    trabajo = web.esperar(web.post('/pf/protecciones/capacidades', json={
        'project': args.proyecto, 'feeders': [args.alimentador], 'ejecutar_ordenes': True}), limite_s=3600)
    (carpeta / 'protecciones_capacidades.json').write_text(
        json.dumps(trabajo.get('result') or trabajo, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    estado = web.get('/pf/protecciones', params={'project': args.proyecto})
    (carpeta / 'protecciones_estado.json').write_text(json.dumps(estado, indent=2, ensure_ascii=False) + '\n',
                                                      encoding='utf-8')
    return {'trabajo': trabajo.get('status'), 'ficheros': ['protecciones_capacidades.json', 'protecciones_estado.json']}


def cargar(carpeta: Path, nombre: str) -> dict:
    return json.loads((carpeta / nombre).read_text(encoding='utf-8'))


def contexto_de_aceptacion(carpeta: Path, manifiesto: dict, perfil_ruta: Path | None) -> dict:
    """Lo que necesitan los veredictos de obras: lecturas, límites del perfil y la base del contexto firmado."""
    from convertersmartgrid.digital_twin.integration import (
        TOLERANCIAS_ACEPTACION,
        limites_combinados,
        normas_de,
    )
    from convertersmartgrid.evaluacion_modelos import huella
    from convertersmartgrid.perfil_empresa import datos_perfil, estructura_empresa

    obras = manifiesto['obras']
    lect = {k: cargar(carpeta, v['ruta']) for k, v in obras['lecturas'].items() if (carpeta / v['ruta']).is_file()}
    perfil = datos_perfil(perfil_ruta) if perfil_ruta else datos_perfil()
    try:
        estructura = estructura_empresa(perfil_ruta) if perfil_ruta else estructura_empresa()
    except Exception:  # noqa: BLE001 - sin estructura no hay norma por sistema: lo dice la evaluación
        estructura = None
    limites = limites_combinados(perfil, normas_de(estructura, [manifiesto['alimentador']]))
    con = lect.get('despues/con_proyecto') or {}
    base = {'native_action_context': (cargar(carpeta, 'plan_despues_con_proyecto.json').get('native_action_context')),
            'year': obras['base'].get('anio_casos'), 'period': obras['base'].get('periodo'),
            'criterio_fijas': obras['base'].get('criterio_fijas'), 'profile_hash': huella(perfil),
            'case_role': 'con_proyecto'}
    tol = {**TOLERANCIAS_ACEPTACION, **((perfil.get('gemelo') or {}).get('aceptacion') or {})}
    return {'lecturas': lect, 'con': con, 'base': base, 'limites': limites, 'tolerancias': tol}


def veredictos(carpeta: Path, manifiesto: dict, perfil_ruta: Path | None = None) -> dict:
    """Los veredictos de las cuatro T4 a partir de los ficheros de la evidencia, nunca del resumen guardado."""
    out: dict[str, Any] = {}
    if manifiesto.get('obras') and (manifiesto['obras'].get('preflight') or {}).get('ok') is False:
        out['preflight'] = {'cerrable': False, **manifiesto['obras']['preflight']}
    elif manifiesto.get('obras'):
        obras = manifiesto['obras']
        c = contexto_de_aceptacion(carpeta, manifiesto, perfil_ruta)
        obra = manifiesto['obras']['obra']
        var, barra, q = obra.get('variacion'), obra.get('barra'), float(obra.get('q_kvar') or 0.0)
        lect = c['lecturas']
        sin_d = lect.get('despues/sin_proyecto') or {}
        v44 = veredicto_044(c['con'], sin_d, c['base'], variacion=var, barra=barra, q_kvar=q,
                            limites=c['limites'], tolerancias={
                                'tolerancia_v_pu': c['tolerancias']['tolerancia_v_pu'],
                                'tolerancia_perdidas': c['tolerancias']['tolerancia_perdidas'],
                                'tolerancia_perdidas_kw': c['tolerancias'].get('tolerancia_perdidas_kw')})
        informe = ((cargar(carpeta, 'obras_aplicar.json').get('result') or {}).get('informe') or {})
        antes = {r: lect[f'antes/{r}'] for r in ('caso_base', 'sin_proyecto') if f'antes/{r}' in lect}
        despues = {r: lect[f'despues/{r}'] for r in ROLES if f'despues/{r}' in lect}
        out['044'] = v44
        out['048'] = veredicto_048(informe, antes, despues, c['con'], barra=barra, q_kvar=q, variacion=var,
                                   juicio=v44['juicio'])
        nuevo = obra_presente(sin_d, c['con'], barra, q).get('banco')
        out['045'] = veredicto_045(despues, antes, pedidos=list(ROLES), bancos_declarados=[nuevo] if nuevo else [],
                                   tolerancia_v_pu=c['tolerancias']['tolerancia_v_pu'], variacion=var)
        retirada = lect.get('retirada/con_proyecto')
        # Recalcular desde las lecturas: el resumen del manifiesto no sustituye a los datos.
        refs = referencias_conservadas(
            {r: {**obras['lecturas'].get(f'antes/{r}', {}), 'lectura': lect.get(f'antes/{r}')}
             for r in ('caso_base', 'sin_proyecto')},
            {r: {**obras['lecturas'].get(f'retirada/{r}', {}), 'lectura': lect.get(f'retirada/{r}')}
             for r in ('caso_base', 'sin_proyecto')}, cargar(carpeta, 'plan_antes_caso_base.json'))
        informe_retiro = cargar(carpeta, 'obras_retirar.json') if (carpeta / 'obras_retirar.json').is_file() else {}
        out['retiro'] = {'ok': (obras.get('retiro') or {}).get('rc') == 0
                         and informe_retiro.get('retiradas') == [var] and all(r['ok'] for r in refs.values())
                         and releida(retirada, 'con_proyecto')['ok'] and not bancos_nuevos(sin_d, retirada)
                         and var not in set((retirada.get('topologia') or {}).get('variaciones_activas') or ()),
                         'referencias': refs, 'informe': informe_retiro}
        for rol, check in refs.items():
            original = out['048']['checks'][f'{rol}_intacto']
            original['post_retiro'] = check
            original['ok'] = original['ok'] and check['ok']
        out['048']['persiste'] = out['048']['persiste'] and all(r['ok'] for r in refs.values())
        out['048']['cerrable'] = out['048']['cerrable'] and out['retiro']['ok']
    if manifiesto.get('protecciones'):
        out['049'] = veredicto_049(cargar(carpeta, 'protecciones_capacidades.json'),
                                   cargar(carpeta, 'protecciones_estado.json'))
    return out


def huellas(carpeta: Path) -> dict[str, str]:
    return {p.name: sha256_de(p) for p in sorted(carpeta.iterdir()) if p.is_file() and p.name != MANIFIESTO}


def comprobar_huellas(carpeta: Path, manifiesto: dict, *, permitir_nuevos: bool = False) -> list[str]:
    """Custodia completa; un inventario ausente no acredita una captura vacía."""
    if not isinstance(manifiesto, dict) or manifiesto.get('schema') != ESQUEMA:
        return ['manifiesto: esquema no válido']
    hashes = manifiesto.get('sha256')
    if not isinstance(hashes, dict) or not hashes:
        return ['manifiesto: faltan huellas de captura']
    errores = []
    for nombre, digest in hashes.items():
        if (not isinstance(nombre, str) or not nombre or nombre in ('.', '..', MANIFIESTO)
                or any(c in nombre for c in '/\\:')):
            errores.append(f'ruta no válida: {nombre}')
            continue
        ruta = carpeta / nombre
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            errores.append(f'huella no válida: {nombre}')
        elif ruta.is_symlink() or not ruta.is_file() or sha256_de(ruta) != digest:
            errores.append(nombre)
    if not permitir_nuevos:
        presentes = {p.name for p in carpeta.iterdir() if p.is_file() and p.name != MANIFIESTO}
        errores.extend(f'sin custodia: {n}' for n in sorted(presentes - set(hashes)))
    return errores


def _guardar_manifiesto(ruta: Path, manifiesto: dict) -> None:
    """Un error de escritura no trunca el manifiesto de captura anterior."""
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=ruta.parent,
                                         prefix='.custodia-', suffix='.tmp', delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(json.dumps(manifiesto, indent=2, ensure_ascii=False) + '\n')
            salida.flush()
            os.fsync(salida.fileno())
        os.replace(temporal, ruta)
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Evidencia nativa de las T4 de las specs 044, 045, 048 y 049 '
                                            '(reapertura y relectura en DIgSILENT, por la web)')
    p.add_argument('--url', default='http://127.0.0.1:8765')
    p.add_argument('--espacio', required=True)
    p.add_argument('--proyecto', required=True)
    p.add_argument('--alimentador', required=True)
    p.add_argument('--planes', type=Path, required=True, help='Carpeta de planes del espacio de la web')
    p.add_argument('--evidencia', type=Path, required=True)
    p.add_argument('--perfil', type=Path, help='Perfil de empresa (por defecto, el activo)')
    sub = p.add_subparsers(dest='etapa', required=True)
    o = sub.add_parser('obras', help='banco en «Con proyecto», relecturas, retiro (044, 045, 048)')
    o.add_argument('--barra', required=True)
    o.add_argument('--q-kvar', type=float, required=True)
    o.add_argument('--guion-local', action='store_true',
                   help='aplicar con tools/obras_pf.py de esta copia y el plan firmado por la web, no por la web')
    sub.add_parser('protecciones', help='capacidades y disponibilidad de protecciones (049)')
    sub.add_parser('veredictos', help='solo recalcula los veredictos de una evidencia ya escrita')
    args = p.parse_args(argv)
    carpeta = args.evidencia
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / MANIFIESTO
    anterior = None
    original = None
    try:
        if ruta.exists():
            original = ruta.read_bytes()
            anterior = json.loads(original)
            fallos = comprobar_huellas(carpeta, anterior)
            if fallos:
                raise ValueError('; '.join(fallos))
            for clave in ('proyecto', 'alimentador', 'espacio'):
                if clave in anterior and anterior[clave] != getattr(args, clave):
                    raise ValueError(f'{clave} distinto de la captura')
            if args.etapa != 'veredictos' and args.etapa in anterior:
                raise ValueError('etapa ya capturada: utilice otra carpeta para una nueva captura')
        elif args.etapa == 'veredictos':
            raise ValueError('falta el manifiesto de captura')
        elif any(carpeta.iterdir()):
            raise ValueError('hay ficheros previos sin manifiesto: use una carpeta vacía para la primera captura')
    except (OSError, ValueError, TypeError) as exc:
        print(f'ERROR de custodia: {exc}', flush=True)
        return 2
    manifiesto = json.loads(original) if original is not None else {
        'schema': ESQUEMA, 'proyecto': args.proyecto, 'alimentador': args.alimentador, 'espacio': args.espacio}
    revision = {'commit': _commit(), 'escrito': datetime.now(UTC).isoformat(timespec='seconds')}
    try:
        if args.etapa == 'obras':
            manifiesto['obras'] = {**etapa_obras(args, carpeta), 'inicio': datetime.now(UTC).isoformat(timespec='seconds')}
            manifiesto['obras']['obra'].update(barra=args.barra, q_kvar=args.q_kvar)
            preflight = manifiesto['obras'].get('preflight') or {}
            if preflight.get('ok') is False:
                manifiesto.setdefault('errores', []).append('obras: preflight rechazado; no se llamó al escritor: '
                                                          + '; '.join(preflight['motivos']))
            if manifiesto['obras'].get('retiro') and not manifiesto['obras']['retiro'].get('ok'):
                manifiesto.setdefault('errores', []).append(
                    'obras: retiro de la variación o conservación de referencias tras retirar no confirmados')
        elif args.etapa == 'protecciones':
            manifiesto['protecciones'] = etapa_protecciones(args, carpeta)
    except Exception as exc:  # noqa: BLE001 - la evidencia parcial se guarda con el motivo
        manifiesto.setdefault('errores', []).append(f'{args.etapa}: {type(exc).__name__}: {exc}')
        print(f'ERROR: {exc}', flush=True)
    if args.etapa != 'veredictos':
        if args.perfil:
            manifiesto['perfil'] = str(args.perfil)
        if anterior is None:
            manifiesto.update(revision)
        manifiesto.setdefault('capturas', {})[args.etapa] = dict(revision)
        manifiesto['sha256'] = huellas(carpeta)
    try:
        manifiesto['veredictos'] = json.loads(json.dumps(veredictos(carpeta, manifiesto, args.perfil), default=str))
    except Exception as exc:  # noqa: BLE001 - el 2026-11-07 un fallo aquí perdió el registro de las lecturas
        manifiesto['veredictos'] = {}
        manifiesto.setdefault('errores', []).append(f'veredictos: {type(exc).__name__}: {exc}')
    try:
        # También comprobar después del cálculo: no publicar si un lector o escritor
        # cambió los bytes que acabamos de evaluar, ni pisar otro manifiesto.
        if anterior is not None:
            fallos = comprobar_huellas(carpeta, anterior, permitir_nuevos=args.etapa != 'veredictos')
            if fallos or ruta.read_bytes() != original:
                raise ValueError('; '.join(fallos) or 'el manifiesto cambió durante la revisión')
        if args.etapa == 'veredictos':
            manifiesto['revision_veredictos'] = {
                **revision, 'manifiesto_origen_sha256': hashlib.sha256(original).hexdigest()}
        _guardar_manifiesto(ruta, manifiesto)
    except (OSError, ValueError) as exc:
        print(f'ERROR de custodia: {exc}', flush=True)
        return 2
    for spec, v in manifiesto['veredictos'].items():
        print(f"{spec}: cerrable={v.get('cerrable')}", flush=True)
    return 2 if manifiesto.get('errores') else 0


if __name__ == '__main__':
    raise SystemExit(main())
