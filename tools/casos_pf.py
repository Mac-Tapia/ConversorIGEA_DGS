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
from igea_dgs.obras_pf import PREFIJO_VARIACION

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


def objetos_de_variacion(variacion) -> list[tuple[str, str]]:
    """``(clase, nombre)`` de lo que graban las etapas de una variación (spec 014).

    Recursivo dentro de cada etapa: la carga nueva de la 007 cuelga de la SED que la etapa
    crea. Se lee una vez por variación y por trabajo, no por carga.
    """
    out = []
    for etapa in variacion.GetContents('*.IntSstage'):
        out += [(o.GetClassName(), o.loc_name) for o in etapa.GetContents('*', 1)]
    return out


def es_ajuste_puro(variacion) -> bool:
    """Un ``Ajuste_…`` cuyas etapas solo cambian cargas: lo dejó el ajuste y nada más.

    CA101 (2026-10-14): el operador cambió el tipo de cuatro transformadores con
    ``Ajuste_CA101_20261013_203247_3`` grabando, y los ajustes siguientes lo desactivaron
    por su nombre. Una variación así es del operador (014:RF-3).
    """
    return (variacion.loc_name.startswith('Ajuste_')
            and all(clase == 'ElmLod' for clase, _ in objetos_de_variacion(variacion)))


def es_de_carga_nueva(variacion) -> bool:
    """Variación de una carga nueva de la spec 007 (``Carga_<SED>_<alim>_…``)."""
    return variacion.loc_name.startswith('Carga_')


def es_del_operador(variacion) -> bool:
    """Ni de carga nueva ni ajuste puro: se conserva tal como la dejó el operador (spec 014)."""
    return not es_de_carga_nueva(variacion) and not es_ajuste_puro(variacion)


def clasificar(variaciones, feeders: list[str], base: list[str], demandas: str | None) -> dict:
    """Separa las variaciones del proyecto por su papel en los casos.

    - ``base``: las del último ajuste (las que da el plan) y la de demandas.
    - ``cargas``: las de cargas nuevas de los alimentadores marcados (``Carga_<SED>_<alim>_…``,
      spec 007, RF-10).
    - ``anteriores``: otros ajustes puros de esos alimentadores (``Ajuste_<alim>_…`` que solo
      cambian cargas), que se desactivan sin borrar (RF-50).
    - ``operador``: cualquier otra, también un ajuste que grabó cambios del operador; no se
      desactiva nunca (014:RF-3, RF-15, RF-20).
    """
    nombres_base = set(base) | ({demandas} if demandas else set())
    out = {'base': [], 'cargas': [], 'anteriores': [], 'operador': []}
    for v in variaciones:
        n = v.loc_name
        if n in nombres_base:
            out['base'].append(v)
        elif es_de_carga_nueva(v):
            if _de_alimentador(n, 'Carga_', feeders):
                out['cargas'].append(v)
        elif es_ajuste_puro(v):
            if _de_alimentador(n, 'Ajuste_', feeders):
                out['anteriores'].append(v)
        else:
            out['operador'].append(v)
    for k in out:
        out[k].sort(key=lambda v: v.loc_name)
    return out


def operador_a_con_proyecto(app, casos: dict, variaciones=None) -> list[str]:
    """Activa en «Con proyecto» las variaciones del operador activas en «Sin proyecto».

    014:RF-21: «Con proyecto» es «Sin proyecto» más las cargas nuevas; un cambio que el
    operador grabó en «Sin proyecto» después de copiarlo también tiene que estar. Solo
    activa, nunca apaga. Devuelve los nombres activados (014:RF-22). Deja activo el caso
    que lo estaba.
    """
    previo = app.GetActiveStudyCase()
    casos['sin'].Activate()
    en_sin = [v for v in (app.GetActiveNetworkVariations() or []) if es_del_operador(v)]
    if variaciones is not None:
        nombres = {v.loc_name for v in variaciones}
        en_sin = [v for v in en_sin if v.loc_name in nombres]
    casos['con'].Activate()
    ya = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
    activadas = []
    for v in en_sin:
        if v.loc_name not in ya:
            v.Activate()
            activadas.append(v.loc_name)
    if previo is not None:
        previo.Activate()
    return sorted(activadas)


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


def crear_con_proyecto(app, sin):
    """«Con proyecto» como copia de «Sin proyecto», con sus variaciones activas (014:RF-18).

    Lo usan la preparación de los casos y las obras: lo que se hizo en «Sin proyecto»
    pasa a «Con proyecto» porque la copia se hace después (016:RF-12). Devuelve el caso,
    marcado y con su escenario, copia del de «Sin proyecto».
    """
    con = app.GetProjectFolder('study').AddCopy(sin, NOMBRES['con'])
    _marcar(con, 'con')
    _escenario_propio(app, con, 'con', _escenario_de(app, sin))
    return con


# =========================================================================== preparar
def _sin_verificar(plan: dict, feeders: list[str]) -> list[str]:
    """Alimentadores de ``feeders`` cuyo «Caso base» no está verificado (015:RF-17).

    El estado lo pone la web desde el vínculo del proyecto (``caso_base_sin_verificar``);
    un plan que no lo trae es de antes de la spec 015 y no se da por verificado.
    """
    if 'caso_base_sin_verificar' not in plan:
        return list(feeders) or ['(sin estado del «Caso base»)']
    fuera = plan.get('caso_base_sin_verificar') or {}
    return [f for f in feeders if f in fuera]


def caso(app, rol: str):
    """El caso del sistema con ese rol, o ``None``."""
    return casos_del_proyecto(app).get(rol)


def _ajenos(app) -> list[str]:
    carpeta = app.GetProjectFolder('study')
    casos = casos_del_proyecto(app)
    return [c.loc_name for c in carpeta.GetContents('*.IntCase')
            if c.loc_name in NOMBRES.values() and c not in casos.values()]


def _de_carga_nueva(app) -> list:
    carpeta = app.GetProjectFolder('scheme')
    return [v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])
            if es_de_carga_nueva(v)]


def preparar_sin(app, plan: dict) -> tuple[dict, int]:
    """«Sin proyecto» como copia del «Caso base» verificado (015:RF-16 a RF-18, RF-27).

    Solo con el «Caso base» verificado. Si aún no hay casos, el activo pasa a ser el
    «Caso base»; «Sin proyecto» sale de él con una copia de su escenario de operación y
    sin activar ninguna variación: las modificaciones del operador se graban en la red
    (RF-27). Una vez creado, el «Caso base» no se vuelve a tocar (RF-19).
    """
    informe = {'project': plan.get('project'), 'avisos': [], 'casos': {}}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    fuera = _sin_verificar(plan, list(plan.get('feeders') or []))
    if fuera:
        return {**informe, 'error': 'El «Caso base» de ' + ', '.join(fuera) + ' no está '
                                    'verificado: verifíquelo (paso 1.1) antes de crear «Sin '
                                    'proyecto» (015:RF-17).'}, 2
    ajenos = _ajenos(app)
    if ajenos:
        return {**informe, 'error': 'Hay en el proyecto un caso de estudio que no creó el sistema '
                                    'con el nombre ' + ', '.join(f'«{n}»' for n in ajenos)
                                    + ': renómbrelo en DIgSILENT y vuelva a preparar.'}, 2
    carpeta = app.GetProjectFolder('study')
    casos = casos_del_proyecto(app)
    inicial = app.GetActiveStudyCase()
    try:
        caso_base = casos.get('base') or inicial
        creado_base = 'base' not in casos
        sin = casos.get('sin')
        if sin is None:
            if creado_base:
                caso_base.loc_name = NOMBRES['base']
                _marcar(caso_base, 'base')
            caso_base.Activate()
            # 014:RF-16: ninguna carga nueva en el base ni, por tanto, en su copia.
            for v in _de_carga_nueva(app):
                v.Deactivate()
            if app.GetActiveScenario() is None:
                _escenario_propio(app, caso_base, 'base', None)
            sin = carpeta.AddCopy(caso_base, NOMBRES['sin'])
            _marcar(sin, 'sin')
        caso_base.Activate()
        activas_base = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))
        esc_base = app.GetActiveScenario()
        informe['casos']['base'] = {
            'nombre': caso_base.loc_name, 'creado': creado_base, 'variaciones': activas_base,
            'escenario': esc_base.loc_name if esc_base is not None else None}
        if activas_base:
            # 015:RF-31: se avisa y no se toca; son del operador.
            informe['avisos'].append('Variaciones activas en el «Caso base»: '
                                     + ', '.join(activas_base))
        informe['casos']['sin'] = {
            'nombre': sin.loc_name, 'creado': 'sin' not in casos,
            'escenario': _escenario_propio(app, sin, 'sin', esc_base),
            'variaciones': sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or [])),
            'estudiable': True}
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def preparar_con(app, plan: dict) -> tuple[dict, int]:
    """«Con proyecto» como copia de «Sin proyecto», antes de insertar cargas (015:RF-28).

    Con su propio escenario, copia del de «Sin proyecto». Activa las cargas nuevas de los
    alimentadores marcados y lo que el operador tenga activo en «Sin proyecto»
    (014:RF-21); los ajustes puros de antes de la spec 015 se desactivan sin borrar.
    """
    informe, rc = preparar_sin(app, plan)
    if rc:
        return informe, rc
    casos = casos_del_proyecto(app)
    sin = casos['sin']
    carpeta_var = app.GetProjectFolder('scheme')
    todas = carpeta_var.GetContents('*.IntScheme', 1) if carpeta_var else []
    grupos = clasificar(todas, list(plan.get('feeders') or []), [], None)
    inicial = app.GetActiveStudyCase()
    try:
        con = casos.get('con')
        if con is None:
            con = crear_con_proyecto(app, sin)
        escenario_con = _escenario_propio(app, con, 'con', _escenario_de(app, sin))
        _dejar_activas(app, con, grupos['cargas'], grupos['anteriores'])
        del_operador = operador_a_con_proyecto(app, {'sin': sin, 'con': con})
        con.Activate()
        activas = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))
        # Un informe de estudio no trae cliente nuevo: lo que distingue «Con proyecto» son
        # las obras de mejora (017:RF-30). Antes solo contaban las cargas nuevas, y en CA101
        # (2026-10-15) «Con proyecto» con obras se quedaba sin estudiar.
        obras = [v for v in activas if v.startswith(PREFIJO_VARIACION)]
        estudiable = bool(grupos['cargas'] or obras)
        informe['casos']['con'] = {
            'nombre': con.loc_name, 'creado': 'con' not in casos, 'escenario': escenario_con,
            'variaciones': activas,
            'variaciones_operador_activadas': del_operador, 'estudiable': estudiable}
        if not estudiable:
            informe['avisos'].append('Ningún alimentador marcado tiene cargas nuevas ni obras: '
                                     '«Con proyecto» queda igual que «Sin proyecto» y no se estudia.')
        if grupos['anteriores']:
            informe['avisos'].append(
                'Ajustes de antes de la spec 015 desactivados en «Con proyecto» (siguen en el '
                'proyecto): ' + ', '.join(v.loc_name for v in grupos['anteriores']))
        if del_operador:
            informe['avisos'].append('Activadas en «Con proyecto» porque están activas en «Sin '
                                     'proyecto»: ' + ', '.join(del_operador))
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def preparar(app, plan: dict) -> tuple[dict, int]:
    """Los tres casos para los estudios (spec 011 con la 015). Devuelve (informe, código).

    Los alimentadores sin calibrar quedan fuera con su motivo; el que no cuadró, con
    aviso (011:RF-14, RF-15). La calibración ya no es una variación: está en el
    escenario de «Sin proyecto» (015:RF-26).
    """
    base = plan.get('base') or {}
    marcados = list(plan.get('feeders') or [])
    ajustados = {a['feeder']: a for a in base.get('ajustes') or []}
    excluidos = list(base.get('excluidos') or [])
    ya_fuera = {x['feeder'] for x in excluidos}
    for f in marcados:
        if f not in ajustados and f not in ya_fuera:
            excluidos.append({'feeder': f, 'motivo': 'no está calibrado'})
    feeders = [f for f in marcados if f in ajustados]
    if not feeders:
        return {'project': plan.get('project'), 'avisos': [], 'excluidos': excluidos, 'casos': {},
                'error': 'Ningún alimentador marcado está calibrado: primero hay que calibrar '
                         '(paso 2).'}, 2
    informe, rc = preparar_con(app, {**plan, 'feeders': feeders})
    informe['excluidos'] = excluidos
    informe['feeders'] = feeders
    for f in feeders:
        a = ajustados[f]
        if not a.get('cuadrado'):
            d = a.get('desvio') or {}
            informe['avisos'].append(
                f"{f}: su ajuste no cuadró (error en la cabecera {_pct(d.get('kw'))} en kW, "
                f"{_pct(d.get('kvar'))} en kVAR); se estudia igual.")
    return informe, rc


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
    # Primera línea solo con DIgSILENT ya respondiendo: la web la espera un tiempo
    # limitado y, si no llega, corta el guion en vez de dejar ocupado el carril (005:RF-21).
    print(f'Conectado a DIgSILENT como {getattr(app.GetCurrentUser(), "loc_name", "?")}.',
          flush=True)
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
