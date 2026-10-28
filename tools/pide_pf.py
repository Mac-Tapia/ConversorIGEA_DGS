#!/usr/bin/env python
"""Verifica en DIgSILENT cada año del horizonte del PIDE (spec 024, T13, RF-51 a RF-53).

Para cada año pedido escala la demanda con el factor de escala de cargas del ``ComLdf``
((1 + tasa)^año), ejecuta el flujo en el caso pedido y diagnostica con la norma del perfil
(``igea_dgs.pide``). Al terminar devuelve el factor a su valor: no crea ni guarda nada en
el proyecto.

    python tools/pide_pf.py --plan plan.json --output-json informe.json

El plan: ``{"project", "folder", "feeders", "case", "tasa", "anios": [0, 4, 8, ...],
"limites": {...}, "native_action_context"}``.

Códigos de salida: 0 leído (con o sin problemas), 2 sin proyecto, sin caso o sin tasa,
1 error inesperado, 3 sin API.
"""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, clave_pf, flujo_de_carga
from casos_pf import (
    _escenario_de,
    _marcar,
    anio_del_plan,
    es_de_carga_nueva,
    nombre_cargas_nuevas,
    objetos_de_variacion,
)
from casos_pf import caso as caso_del_sistema
from digital_twin_snapshot_pf import CASOS, _caso, resultados
from estudios_pf import _num

from igea_dgs.digital_twin.native_snapshot import identidad_nativa
from igea_dgs.native_action import native_action_block_report
from igea_dgs.pide import diagnosticar


#: Los casos de cada año del PIDE, con su papel y su nombre (030:RF-1).
CASOS_DEL_ANIO = (('sin', 'Sin proyecto'), ('cargas', 'Cargas nuevas'), ('con', 'Con proyecto'))


def _carpeta(padre, nombre: str):
    """La subcarpeta ``nombre`` de ``padre``, creada si falta."""
    return next((x for x in padre.GetContents('*.IntFolder') if x.loc_name == nombre), None) \
        or padre.CreateObject('IntFolder', nombre)


def origenes_del_pide(app, plan: dict) -> dict:
    """Los casos del proyecto que se copian a cada año: «Sin proyecto», «Cargas nuevas» y «Con
    proyecto», los del año de medición si los hay (030:RF-1)."""
    anio = anio_del_plan(plan)
    out = {}
    sin = caso_del_sistema(app, 'sin', anio) or _caso(app, 'Sin proyecto')
    if sin is not None:
        out['sin'] = sin
    cargas = _caso(app, nombre_cargas_nuevas(anio))
    if cargas is not None:
        out['cargas'] = cargas
    con = caso_del_sistema(app, 'con', anio)
    if con is not None:
        out['con'] = con
    return out


def fraccion_en(perfil, anio: int) -> float:
    """La fracción del total de una carga nueva en el año ``anio`` del PIDE: la acumulada de sus
    partes hasta él, 0 antes de la primera (030:RF-11, RF-15). ``perfil``: ``[[año, acumulada]]``."""
    vistas = [f for a, f in sorted(perfil or [[0, 1.0]]) if a <= anio]
    return float(vistas[-1]) if vistas else 0.0


def cargas_nuevas_del_proyecto(app, pedidas: list | None = None) -> dict[str, list]:
    """Las cargas (``ElmLod``) de las variaciones de carga nueva con su perfil de ingreso: el de
    ``pedidas`` (``[{'variacion', 'perfil'}]``) o entera en el año 00 (030:RF-9, RF-11, RF-15)."""
    perfiles = {str(p['variacion']): p.get('perfil') or [[int(p.get('anio') or 0), 1.0]]
                for p in pedidas or [] if p.get('variacion')}
    carpeta = app.GetProjectFolder('scheme')
    out: dict[str, list] = {}
    for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else []):
        if not es_de_carga_nueva(v):
            continue
        perfil = next((x for nombre, x in perfiles.items()
                       if v.loc_name == nombre or v.loc_name.startswith(nombre + '(')), [[0, 1.0]])
        for clase, nombre in objetos_de_variacion(v):
            if clase == 'ElmLod':
                out[nombre] = perfil
    return out


def casos_del_anio(app, origenes: dict, anio: int, factor_de, base: dict | None = None,
                   nuevas: dict[str, list] | None = None) -> dict:
    """«PIDE/Año NN» en casos y en escenarios, con un caso y un escenario por papel; la demanda de
    cada carga, por el factor de su alimentador (030:RF-1 a RF-3, RF-5, RF-8). ``factor_de(elm)``:
    el factor del año del ``ElmFeeder``; ``base``: el ``scale0`` de cada carga antes del PIDE, sobre
    el que se aplica, para que un año nunca escale el de otro."""
    base = base if base is not None else {}
    nuevas = nuevas or {}
    etiqueta = f'Año {anio:02d}'
    casos = _carpeta(_carpeta(app.GetProjectFolder('study'), 'PIDE'), etiqueta)
    escenarios = _carpeta(_carpeta(app.GetProjectFolder('scen', 1), 'PIDE'), etiqueta)
    out = {}
    for rol, nombre in CASOS_DEL_ANIO:
        origen = origenes.get(rol)
        if origen is None:
            continue
        esc_origen = _escenario_de(app, origen)
        origen.Activate()                       # el de una corrida anterior no puede estar activo
        for x in casos.GetContents('*.IntCase'):
            if x.loc_name == nombre:
                x.Delete()                      # RF-5: se renueva, sin duplicar
        for x in escenarios.GetContents('*.IntScenario'):
            if x.loc_name == nombre:
                x.Delete()
        caso = casos.AddCopy(origen, nombre)
        _marcar(caso, f'pide_{anio:02d}_{rol}')                              # RF-8
        caso.Activate()
        actual = app.GetActiveScenario()
        if actual is not None:
            actual.Deactivate(0)
        esc = escenarios.AddCopy(esc_origen, nombre) if esc_origen is not None \
            else escenarios.CreateObject('IntScenario', nombre)
        esc.Activate()
        for elm in app.GetActiveProject().GetContents('*.ElmFeeder', 1):
            f = factor_de(elm)
            if f is None:
                continue
            for c in elm.GetObjs('ElmLod'):
                if c.loc_name in nuevas:
                    continue                                                 # RF-9: constante
                b = base.setdefault(clave_pf(c), float(getattr(c, 'scale0', 1.0) or 1.0))
                c.scale0 = b * f                                             # RF-3, en su escenario
        if rol in ('cargas', 'con') and nuevas:
            # RF-11, RF-15: la carga nueva lleva lo que entró hasta este año, sin crecimiento;
            # antes de su primera parte, fuera de servicio.
            for c in app.GetCalcRelevantObjects('*.ElmLod') or []:
                if c.loc_name not in nuevas:
                    continue
                f = fraccion_en(nuevas[c.loc_name], anio)
                b = base.setdefault(clave_pf(c), float(getattr(c, 'scale0', 1.0) or 1.0))
                c.outserv = 0 if f > 0 else 1
                if f > 0:
                    c.scale0 = b * f
        esc.Save()
        out[rol] = {'caso': f'PIDE/{etiqueta}/{nombre}', 'escenario': f'PIDE/{etiqueta}/{nombre}', 'objeto': caso}
    return out


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """Diagnóstico de cada año con la demanda escalada. Devuelve (informe, código)."""
    informe = {'project': plan['project'], 'case': plan.get('case'), 'anios': [], 'avisos': []}
    tasa = plan.get('tasa')
    if tasa is None:
        return {**informe, 'error': 'falta la tasa de crecimiento de la demanda (RF-51)'}, 2
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r}"}, 2
    nombre_caso = CASOS.get(plan.get('case') or '', plan.get('case'))
    if nombre_caso:
        caso = _caso(app, nombre_caso)
        if caso is None:
            return {**informe, 'error': f'el proyecto no tiene el caso «{nombre_caso}»'}, 2
        caso.Activate()
    ldf = app.GetFromStudyCase('ComLdf')
    original = getattr(ldf, 'scLoadFac', None)
    if original is None:
        return {**informe, 'error': 'este DIgSILENT no da el factor de escala de cargas del ComLdf'}, 2
    raiz = clave_pf(proyecto)
    lim = plan['limites']
    # Alimentador y tensión de cada barra y línea: con ellos se construye la obra que
    # resuelve el problema (banco en su barra, terna en su tramo; 024:RF-45, RF-47).
    barras, de_linea = {}, {}
    elms = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
    for feeder in plan.get('feeders') or []:
        elm = elms.get(feeder)
        if elm is None:
            continue
        for b in elm.GetObjs('ElmTerm'):
            barras[identidad_nativa('ElmTerm', clave_pf(b), raiz)] = {
                'nombre': b.loc_name, 'kv': _num(b, 'uknom'), 'alimentador': feeder}
        for ln in elm.GetObjs('ElmLne'):
            de_linea[ln.loc_name] = feeder
    por_nombre = {v['nombre']: v for v in barras.values()}
    informe['barras_mt'] = sorted(v['nombre'] for v in barras.values() if (v['kv'] or 0) >= 1)
    # 029:RF-4: con tasa por alimentador, cada uno escala sus cargas con la suya (``scale0``) y el
    # factor del flujo queda en 1; al terminar, cada carga vuelve a su valor.
    por_alim = {str(a): float(x) for a, x in (plan.get('tasa_por_alimentador') or {}).items()}
    if plan.get('casos_por_anio'):
        return _por_anios(app, plan, informe, proyecto, raiz, lim, barras, de_linea, por_nombre, float(tasa),
                          por_alim)
    cargas = {a: list(elms[a].GetObjs('ElmLod')) for a in por_alim if a in elms}
    base_scale = {clave_pf(c): float(getattr(c, 'scale0', 1.0) or 1.0) for cs in cargas.values() for c in cs}
    try:
        for anio in plan.get('anios') or [0]:
            factor = (1 + float(tasa)) ** int(anio)
            if cargas:
                for a, cs in cargas.items():
                    f = (1 + por_alim[a]) ** int(anio)
                    for c in cs:
                        c.scale0 = base_scale[clave_pf(c)] * f
                # Los alimentadores sin tasa propia, con la del sistema; los demás ya escalados.
                for a, elm in elms.items():
                    if a in cargas or a not in (plan.get('feeders') or []):
                        continue
                    for c in elm.GetObjs('ElmLod'):
                        base_scale.setdefault(clave_pf(c), float(getattr(c, 'scale0', 1.0) or 1.0))
                        c.scale0 = base_scale[clave_pf(c)] * factor
                ldf.scLoadFac = float(original)
            else:
                ldf.scLoadFac = float(original) * factor
            flujo = flujo_de_carga(app)
            fila = {'anio': int(anio), 'factor': factor, 'converge': flujo['converged']}
            if flujo['converged']:
                lectura = {'flujo': resultados(app, proyecto, raiz, list(plan.get('feeders') or [])),
                           'topologia': {'barras': barras}}
                problemas = diagnosticar(lectura, **lim)
                fila['problemas'] = []
                for p in problemas:
                    sitio = por_nombre.get(p.elemento) or {}
                    linea = p.elemento.removesuffix('.ElmLne')
                    fila['problemas'].append({**p.__dict__, 'kv': sitio.get('kv'),
                                              'alimentador': sitio.get('alimentador') or de_linea.get(linea)})
                tensiones = lectura['flujo']['tensiones']['valores']
                fila['vm_min'] = min(tensiones.values()) if tensiones else None
                fila['cabeceras_kw'] = lectura['flujo']['balance']['valores']['cabeceras']
            else:
                fila['problemas'] = [{'tipo': 'flujo', 'elemento': 'red', 'causa': 'no_converge',
                                      'evidencia': 'el flujo no converge con esta demanda'}]
            informe['anios'].append(fila)
    finally:
        ldf.scLoadFac = original
        for elm in elms.values():
            for c in elm.GetObjs('ElmLod'):
                if clave_pf(c) in base_scale:
                    c.scale0 = base_scale[clave_pf(c)]
    if por_alim:
        informe['tasa_por_alimentador'] = por_alim
    return informe, 0


def _por_anios(app, plan, informe, proyecto, raiz, lim, barras, de_linea, por_nombre, tasa, por_alim):
    """030:RF-1 a RF-7: cada año en su carpeta, con sus casos y escenarios, y su diagnóstico en el
    «Sin proyecto» del año. El caso que estaba activo vuelve a estarlo al terminar (RF-6)."""
    inicial = app.GetActiveStudyCase()
    origenes = origenes_del_pide(app, plan)
    if 'sin' not in origenes:
        return {**informe, 'error': 'el proyecto no tiene «Sin proyecto» para copiar a los años del PIDE'}, 2
    feeders = set(plan.get('feeders') or [])
    nuevas = cargas_nuevas_del_proyecto(app, plan.get('cargas_nuevas'))           # RF-9, RF-11
    if nuevas:
        informe['cargas_nuevas'] = nuevas
    origenes['sin'].Activate()
    elms = [e for e in proyecto.GetContents('*.ElmFeeder', 1) if e.loc_name in feeders]
    base = {clave_pf(c): float(getattr(c, 'scale0', 1.0) or 1.0) for e in elms for c in e.GetObjs('ElmLod')}
    try:
        for anio in plan.get('anios') or [0]:
            def factor_de(elm, anio=anio):
                if elm.loc_name not in feeders:
                    return None
                return (1 + por_alim.get(elm.loc_name, tasa)) ** int(anio)

            casos = casos_del_anio(app, origenes, int(anio), factor_de, base, nuevas)
            casos['sin']['objeto'].Activate()
            flujo = flujo_de_carga(app)
            fila = {'anio': int(anio), 'factor': (1 + tasa) ** int(anio), 'converge': flujo['converged'],
                    'casos': {r: {k: v for k, v in c.items() if k != 'objeto'} for r, c in casos.items()}}   # RF-7
            if flujo['converged']:
                lectura = {'flujo': resultados(app, proyecto, raiz, list(plan.get('feeders') or [])),
                           'topologia': {'barras': barras}}
                fila['problemas'] = []
                for p in diagnosticar(lectura, **lim):
                    sitio = por_nombre.get(p.elemento) or {}
                    linea = p.elemento.removesuffix('.ElmLne')
                    fila['problemas'].append({**p.__dict__, 'kv': sitio.get('kv'),
                                              'alimentador': sitio.get('alimentador') or de_linea.get(linea)})
                tensiones = lectura['flujo']['tensiones']['valores']
                fila['vm_min'] = min(tensiones.values()) if tensiones else None
                fila['cabeceras_kw'] = lectura['flujo']['balance']['valores']['cabeceras']
            else:
                fila['problemas'] = [{'tipo': 'flujo', 'elemento': 'red', 'causa': 'no_converge',
                                      'evidencia': 'el flujo no converge con esta demanda'}]
            informe['anios'].append(fila)
    finally:
        # RF-6: los casos del proyecto con su demanda de antes. En DIgSILENT cada escenario guarda
        # la suya y esto no cambia nada; si algo escribió fuera de su escenario, lo deshace.
        for origen in origenes.values():
            origen.Activate()
            for e in elms:
                for c in e.GetObjs('ElmLod'):
                    if clave_pf(c) in base and float(getattr(c, 'scale0', 1.0) or 1.0) != base[clave_pf(c)]:
                        c.scale0 = base[clave_pf(c)]
        if inicial is not None:
            inicial.Activate()
    if por_alim:
        informe['tasa_por_alimentador'] = por_alim
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Cada año del horizonte del PIDE en DIgSILENT, con la '
                                            'demanda escalada y el diagnóstico de la norma (spec 024)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    blocked = native_action_block_report(plan, 'pide')
    if blocked:
        salida.write_text(json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('pide_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17)
        informe, codigo = {'project': plan.get('project'), 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"PIDE de {plan.get('project')}: código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
