#!/usr/bin/env python
"""Deja en DIgSILENT los tres casos de estudio de la spec 011.

Por qué tres casos. Los estudios solo dicen algo de la red real sobre la red calibrada
(specs 006 a 008), y lo que se evalúa de las cargas nuevas es la diferencia entre la red
con ellas y sin ellas. El usuario lo ordena así (2026-10-11):

- **Caso base**: el caso en que se calibró, renombrado, sin las variaciones del ajuste,
  de las demandas ni de las cargas nuevas: la red tal como vino (RF-2, RF-3).
- **Sin proyecto**: copia del anterior con la base calibrada activa: el último ajuste de
  cada alimentador y las demandas en bloque (RF-4, RF-7, RF-50).
- **Con proyecto**: copia de «Sin proyecto» con, además, todas las cargas nuevas de los
  alimentadores marcados (RF-5, RF-8).

En DIgSILENT las variaciones activas y el escenario son de cada caso: por eso basta con
activar el caso y activar o desactivar en él. Cada caso tiene su propio escenario de
operación (RF-46 a RF-48), para que un cambio de operación en uno no llegue a otro.

Los casos se reconocen por su nombre **y** por una marca en su descripción: un caso del
operador que se llame igual no se toca (RF-10). Si se vuelve a ejecutar, se reutilizan y
solo cambian sus variaciones activas (RF-6): así las cargas nuevas añadidas después
entran en «Con proyecto».

    python tools/casos_pf.py --plan plan.json --output-json informe.json

El plan trae el proyecto, los alimentadores marcados, la base del último ajuste (la de
``services.base_del_ajuste``) y, si la hay, la variación de las demandas en bloque.

Códigos de salida: 0 hecho, 2 no se pudo preparar (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, error_inesperado, nombre_pf
from igea_dgs.native_action import native_action_block_report

#: Rol → nombre del caso. Fijos y reutilizados (usuario, 2026-10-11).
NOMBRES = {'base': 'Caso base', 'sin': 'Sin proyecto', 'con': 'Con proyecto'}

#: Marca en la descripción de un caso creado o renombrado por el sistema.
MARCA = 'igea-dgs:011:'


# =========================================================================== marcas
def _desc(obj) -> list[str]:
    """``desc`` es un vector de cadenas en DIgSILENT; en un objeto nuevo puede faltar."""
    d = getattr(obj, 'desc', None)
    if d is None:
        return []
    return [str(x) for x in d] if isinstance(d, (list, tuple)) else [str(d)]


def rol_de(caso) -> str | None:
    """El rol que el sistema dio a este caso, o ``None`` si no es uno suyo."""
    for linea in _desc(caso):
        if linea.startswith(MARCA):
            return linea[len(MARCA):]
    return None


def _marcar(caso, rol: str) -> None:
    caso.desc = [x for x in _desc(caso) if not x.startswith(MARCA)] + [MARCA + rol]


def casos_del_proyecto(app) -> dict[str, object]:
    """Rol → caso, de los que el sistema ya dejó en el proyecto (RF-51 a RF-54 los usan)."""
    carpeta = app.GetProjectFolder('study')
    out = {}
    for caso in (carpeta.GetContents('*.IntCase') if carpeta else []):
        rol = rol_de(caso)
        if rol in NOMBRES and caso.loc_name == NOMBRES[rol]:
            out[rol] = caso
    return out


def tres_casos(app) -> dict[str, object]:
    """Los tres casos si el sistema ya los dejó todos; si falta alguno, vacío.

    Es la condición de RF-51 a RF-54: mientras no existan los tres, el ajuste y las
    cargas trabajan en el caso activo, como antes de esta spec.
    """
    casos = casos_del_proyecto(app)
    return casos if len(casos) == len(NOMBRES) else {}


def ajustes_de(app, feeder: str) -> list:
    """Variaciones de ajuste (``Ajuste_<alimentador>_…``) de un alimentador."""
    carpeta = app.GetProjectFolder('scheme')
    todas = carpeta.GetContents('*.IntScheme', 1) if carpeta else []
    return [v for v in todas if _de_alimentador(v.loc_name, 'Ajuste_', [feeder])]


def _pct(x) -> str:
    return f'{x * 100:.1f}'.replace('.', ',') + ' %' if isinstance(x, (int, float)) else '?'


# =========================================================================== variaciones
def _de_alimentador(nombre: str, prefijo: str, feeders: list[str]) -> str | None:
    """El alimentador de una variación ``<prefijo>_…_<alimentador>_…`` de las specs 006 y 007."""
    if not nombre.startswith(prefijo):
        return None
    for f in feeders:
        token = nombre_pf(f)
        if nombre.startswith(f'{prefijo}{token}_') or f'_{token}_' in nombre[len(prefijo):]:
            return f
    return None


def clasificar(variaciones, feeders: list[str], base: list[str], demandas: str | None) -> dict:
    """Separa las variaciones del proyecto por su papel en los casos.

    - ``base``: las del último ajuste (las que da el plan) y la de demandas.
    - ``cargas``: las de cargas nuevas de los alimentadores marcados (``Carga_<SED>_<alim>_…``,
      spec 007, RF-10).
    - ``anteriores``: otros ajustes de esos alimentadores (``Ajuste_<alim>_…``), que se
      desactivan sin borrar (RF-50).
    """
    nombres_base = set(base) | ({demandas} if demandas else set())
    out = {'base': [], 'cargas': [], 'anteriores': []}
    for v in variaciones:
        n = v.loc_name
        if n in nombres_base:
            out['base'].append(v)
        elif _de_alimentador(n, 'Ajuste_', feeders):
            out['anteriores'].append(v)
        elif n.startswith('Carga_') and _de_alimentador(n, 'Carga_', feeders):
            out['cargas'].append(v)
    for k in out:
        out[k].sort(key=lambda v: v.loc_name)
    return out


def _dejar_activas(app, caso, activas: list, inactivas: list) -> list[str]:
    """En ``caso``, activa ``activas`` y desactiva ``inactivas``; devuelve lo que queda activo."""
    caso.Activate()
    for v in inactivas:
        v.Deactivate()
    for v in activas:
        v.Activate()
    return sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))


# =========================================================================== escenarios
def _escenario_propio(app, caso, rol: str, origen) -> str:
    """Deja en ``caso`` un escenario con su nombre: copia del de ``origen`` o uno nuevo.

    Un caso reutilizado que ya tiene escenario lo conserva: puede haberlo cambiado el
    operador en DIgSILENT, y no se sobrescribe (casos límite de la spec).
    """
    caso.Activate()
    actual = app.GetActiveScenario()
    if actual is not None and actual.loc_name == NOMBRES[rol]:
        return actual.loc_name
    carpeta = app.GetProjectFolder('scen', 1)
    existente = next((e for e in carpeta.GetContents('*.IntScenario')
                      if e.loc_name == NOMBRES[rol]), None)
    if existente is not None:
        nuevo = existente
    elif origen is not None:
        nuevo = carpeta.AddCopy(origen, NOMBRES[rol])
    else:
        nuevo = carpeta.CreateObject('IntScenario', NOMBRES[rol])
    nuevo.Activate()
    return nuevo.loc_name


# =========================================================================== preparar
def preparar(app, plan: dict) -> tuple[dict, int]:
    """Deja los tres casos. Devuelve (informe, código de salida)."""
    informe = {'project': plan.get('project'), 'avisos': [], 'excluidos': [], 'casos': {}}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2

    base = plan.get('base') or {}
    if not base.get('variaciones'):
        return {**informe, 'error': 'El proyecto no tiene ningún ajuste a la máxima aplicado: '
                                    'primero hay que calibrar (paso 2).'}, 2

    marcados = list(plan.get('feeders') or [])
    ajustados = {a['feeder']: a for a in base.get('ajustes') or []}
    informe['excluidos'] = list(base.get('excluidos') or [])
    ya_fuera = {x['feeder'] for x in informe['excluidos']}
    for f in marcados:
        if f not in ajustados and f not in ya_fuera:
            informe['excluidos'].append({'feeder': f, 'motivo': 'no tiene variación de ajuste'})
    feeders = [f for f in marcados if f in ajustados]
    informe['feeders'] = feeders
    for f in feeders:
        a = ajustados[f]
        if not a.get('cuadrado'):
            d = a.get('desvio') or {}
            informe['avisos'].append(
                f"{f}: su ajuste no cuadró (error en la cabecera {_pct(d.get('kw'))} en kW, "
                f"{_pct(d.get('kvar'))} en kVAR); se estudia igual.")

    carpeta_var = app.GetProjectFolder('scheme')
    todas = carpeta_var.GetContents('*.IntScheme', 1) if carpeta_var else []
    por_nombre = {v.loc_name for v in todas}
    demandas = plan.get('variacion_demandas')
    faltan = [n for n in list(base['variaciones']) + ([demandas] if demandas else [])
              if n not in por_nombre]
    if faltan:
        return {**informe, 'error': 'Ya no están en el proyecto estas variaciones de la base: '
                                    + ', '.join(faltan) + '. Vuelva a calibrar.'}, 2

    carpeta = app.GetProjectFolder('study')
    casos = casos_del_proyecto(app)
    ajenos = [c.loc_name for c in carpeta.GetContents('*.IntCase')
              if c.loc_name in NOMBRES.values() and c not in casos.values()]
    if ajenos:
        return {**informe, 'error': 'Hay en el proyecto un caso de estudio que no creó el sistema '
                                    'con el nombre ' + ', '.join(f'«{n}»' for n in ajenos)
                                    + ': renómbrelo en DIgSILENT y vuelva a preparar.'}, 2

    grupos = clasificar(todas, feeders, list(base['variaciones']), demandas)
    calibrada = grupos['base']
    no_base = grupos['cargas'] + grupos['anteriores']
    inicial = app.GetActiveStudyCase()
    try:
        # Caso base: el de la calibración, o el que ya se marcó como tal.
        caso_base = casos.get('base') or inicial
        creado_base = 'base' not in casos
        if creado_base:
            caso_base.loc_name = NOMBRES['base']
            _marcar(caso_base, 'base')
        caso_base.Activate()
        esc_original = app.GetActiveScenario()
        activas = _dejar_activas(app, caso_base, [], calibrada + no_base)
        informe['casos']['base'] = {'nombre': caso_base.loc_name, 'creado': creado_base,
                                    'variaciones': activas,
                                    'escenario': _escenario_propio(app, caso_base, 'base', None)
                                    if esc_original is None else esc_original.loc_name}

        # Sin proyecto: copia del base (ya limpio), con la base calibrada.
        sin = casos.get('sin')
        if sin is None:
            sin = carpeta.AddCopy(caso_base, NOMBRES['sin'])
            _marcar(sin, 'sin')
        esc_base = _escenario_de(app, caso_base)
        informe['casos']['sin'] = {
            'nombre': sin.loc_name, 'creado': 'sin' not in casos,
            'escenario': _escenario_propio(app, sin, 'sin', esc_base),
            'variaciones': _dejar_activas(app, sin, calibrada, no_base), 'estudiable': True}

        # Con proyecto: copia de «Sin proyecto», con todas las cargas nuevas.
        con = casos.get('con')
        if con is None:
            con = carpeta.AddCopy(sin, NOMBRES['con'])
            _marcar(con, 'con')
        estudiable = bool(grupos['cargas'])
        informe['casos']['con'] = {
            'nombre': con.loc_name, 'creado': 'con' not in casos,
            'escenario': _escenario_propio(app, con, 'con', _escenario_de(app, sin)),
            'variaciones': _dejar_activas(app, con, calibrada + grupos['cargas'], grupos['anteriores']),
            'estudiable': estudiable}
        if not estudiable:
            informe['avisos'].append('Ningún alimentador marcado tiene cargas nuevas: «Con '
                                     'proyecto» queda igual que «Sin proyecto» y no se estudia.')
        if grupos['anteriores']:
            informe['avisos'].append(
                'Ajustes anteriores desactivados en «Sin proyecto» y «Con proyecto» (siguen en el '
                'proyecto): ' + ', '.join(v.loc_name for v in grupos['anteriores']))
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def _escenario_de(app, caso):
    previo = app.GetActiveStudyCase()
    caso.Activate()
    esc = app.GetActiveScenario()
    if previo is not None:
        previo.Activate()
    return esc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Los tres casos de estudio de la spec 011 en DIgSILENT')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, 'estudios')
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de DIgSILENT no disponible ({exc}).')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR: no se pudo conectar a DIgSILENT: {exc}')
        return 3
    try:
        informe, codigo = preparar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, False, exc), 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
