#!/usr/bin/env python
"""Crea SED nuevas en un proyecto de PowerFactory, con su derivación aérea.

Lo que hace por cada SED del plan:

1. Crea la **barra nueva** (``ElmTerm``) en las coordenadas indicadas — GPS si el plan
   las trae en WGS84, y siempre con el nombre ``NODE_<SED>``.
2. La **conecta al nodo más cercano** ya existente con una **línea aérea** nueva
   (``ElmLne``, ``inAir=1``), cuya longitud es la distancia real entre los dos puntos y
   cuyo tipo es el conductor que el plan eligió. Si el ``TypLne`` no existe en el
   proyecto, se crea desde los parámetros del plan.
3. Crea la **SED** (``ElmSubstat``) con sus dos barras internas (MT y BT), su
   ``TypTr2``/``ElmTr2``, el ``ElmCoup`` de enganche y el ``ElmLod`` con la carga.
4. Cablea los **cubículos** (``StaCubic``) de cada extremo.
5. La **dibuja** en el diagrama del alimentador, con los símbolos del conversor:
   ``PointTerm`` en la barra nueva, ``d_lin`` con sus dos ``IntGrfcon`` en la
   derivación y ``SecSubProd`` en la SED. Sin esto la SED existía en la red y calculaba,
   pero no se veía en el unifilar: había que buscarla por el Data Manager.

   El DGS no guarda con qué escala se dibujó (hoja a medida, A0, red unida…), así que
   se **mide**: el plan trae las coordenadas de terreno de los nodos cercanos, y aquí
   se compara con dónde están sus símbolos en el diagrama (``diagram_transform``).

Se ejecuta en un **proceso aparte** y con el Python que exige la API de PowerFactory
(``powerfactory.pyd`` está atado a una versión de CPython; PF 2024 → 3.12). Por eso
recibe el plan como JSON y no importa nada de ``igea_dgs``: el motor del conversor nunca
enlaza con la API propietaria.

Uso:

    python tools/create_sed_loads.py --plan plan_creacion.json \\
        --project 20260923_IGEA_PA217 [--dry-run] [--run-load-flow] \\
        [--output-json resultado.json]

Códigos de salida: 0 creado, 2 plan inaplicable o algo no se pudo crear,
3 API de PowerFactory no disponible.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Crea SED y su derivación aérea en PowerFactory')
    p.add_argument('--plan', required=True, help='JSON de loads_create.create_plan_to_payload')
    p.add_argument('--project', help='Nombre (o fragmento) del proyecto de PowerFactory')
    p.add_argument('--dry-run', action='store_true', help='No escribe: informa qué haría')
    p.add_argument('--run-load-flow', action='store_true', help='Ejecuta ComLdf al terminar')
    p.add_argument('--output-json', help='Informe del resultado')
    return p


def _activate(app, fragment: str | None):
    """Activa el proyecto y su caso de estudio.

    Sin caso de estudio activo ``GetCalcRelevantObjects`` devuelve 0 elementos, y
    parecería que el proyecto está vacío.
    """
    user = app.GetCurrentUser()
    projects = list(user.GetContents('*.IntPrj'))
    if fragment:
        # Nombre exacto primero; el fragmento solo si no hay coincidencia exacta.
        exactos = [p for p in projects if p.loc_name == fragment]
        projects = exactos or [p for p in projects if fragment in p.loc_name]
    if not projects:
        raise SystemExit(f'ERROR: no se encontró proyecto que contenga {fragment!r}.')
    project = sorted(projects, key=lambda p: p.loc_name)[-1]
    project.Activate()
    # Al activar un proyecto, PowerFactory reactiva su último caso de estudio, y ese
    # caso es el que dice qué variaciones y qué escenario están activos (manual, 12.1).
    # Activar el primero de la carpeta cambiaba la red sobre la que se trabajaba.
    if app.GetActiveStudyCase() is None:
        folder = app.GetProjectFolder('study')
        cases = list(folder.GetContents('*.IntCase')) if folder else []
        if cases:
            cases[0].Activate()
    return project


def _grid_of(app):
    """Red por defecto: la primera que no es el resumen de PowerFactory."""
    nets = app.GetCalcRelevantObjects('*.ElmNet')
    if not nets:
        raise SystemExit('ERROR: el proyecto activo no tiene ninguna ElmNet.')
    # «Summary Grid» es la carpeta resumen de PowerFactory, no la red del alimentador.
    real = [n for n in nets if 'summary' not in n.loc_name.lower()]
    return (real or nets)[0]


def _net_of(obj, default):
    """ElmNet que contiene ``obj``. En una red unida hay varias, y la SED debe ir a la
    del nodo al que se engancha, no a la primera que aparezca."""
    current = obj
    while current is not None:
        try:
            if current.GetClassName() == 'ElmNet':
                return current
            current = current.GetParent()
        except Exception:
            break
    return default


# ------------------------------------------------------------------ diagrama

def diagram_transform(refs):
    """Escala y desplazamiento terreno → diagrama, medidos con nodos ya dibujados.

    ``refs`` son ``(x, y, gx, gy)``: coordenadas del export (m) y del símbolo en el
    diagrama. El conversor dibuja con escala uniforme y sin girar
    (``dgs._diagram_mapper``), así que basta ``g = s·t + b``; ``s`` por mínimos
    cuadrados sobre las dos coordenadas a la vez, que aguanta una calle recta (todos
    los nodos con la misma x). Devuelve ``None`` si no hay dos puntos distintos.
    """
    pts = [tuple(map(float, r)) for r in refs]
    if len(pts) < 2:
        return None
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    mgx = sum(p[2] for p in pts) / len(pts)
    mgy = sum(p[3] for p in pts) / len(pts)
    den = sum((p[0] - mx) ** 2 + (p[1] - my) ** 2 for p in pts)
    if den < 1.0:                       # todos en el mismo metro: no hay escala
        return None
    s = sum((p[0] - mx) * (p[2] - mgx) + (p[1] - my) * (p[3] - mgy) for p in pts) / den
    if s <= 0:
        return None
    bx, by = mgx - s * mx, mgy - s * my
    return lambda x, y: (s * x + bx, s * y + by)


def new_sed_positions(spec, anchor_xy, transform, offset):
    """Dónde dibujar la barra nueva: en su punto si hay coordenadas y escala; si no,
    apartada ``offset`` del nodo de enganche, para que no quede encima."""
    if transform is not None and spec.get('coord_x') is not None and spec.get('coord_y') is not None:
        return transform(float(spec['coord_x']), float(spec['coord_y']))
    return anchor_xy[0] + offset, anchor_xy[1] - offset


def line_rotation(a, b) -> int:
    """Igual que ``dgs._line_irot`` con dos puntos."""
    return int(round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))) % 360


class Diagram:
    """Los símbolos ya dibujados de un proyecto, por objeto de red."""

    def __init__(self, project):
        self.by_obj = {}                 # objeto de red → (IntGrf, IntGrfnet)
        self.sizes = {}                  # sSymNam → (rSizeX, rSizeY)
        for grfnet in project.GetContents('*.IntGrfnet', 1):
            for grf in grfnet.GetContents('*.IntGrf'):
                obj = grf.pDataObj
                if obj is not None:
                    self.by_obj[obj] = (grf, grfnet)
                sym = grf.sSymNam
                if sym and sym not in self.sizes:
                    self.sizes[sym] = (grf.rSizeX, grf.rSizeY)

    def position(self, obj):
        found = self.by_obj.get(obj)
        return (found[0].rCenterX, found[0].rCenterY) if found else None

    def net_of(self, obj):
        found = self.by_obj.get(obj)
        return found[1] if found else None

    def size(self, sym, default=1.0):
        return self.sizes.get(sym, (default, default))


def _symbol(grfnet, name, sym, obj, xy, size, rot=0):
    grf = grfnet.CreateObject('IntGrf', name)
    grf.sSymNam = sym
    grf.pDataObj = obj
    grf.rCenterX, grf.rCenterY = float(xy[0]), float(xy[1])
    grf.rSizeX, grf.rSizeY = float(size[0]), float(size[1])
    grf.iRot = rot
    grf.iVis = 1
    grf.iLevel = 1
    grf.iCol = 1
    return grf


def _connector(grf, name, nr, points):
    con = grf.CreateObject('IntGrfcon', name)
    con.iDatConNr = nr
    # rX/rY son vectores de longitud fija (20 en PF 2024) rellenos con -1: una lista
    # más corta da «setting attribute 'rX' failed».
    size = con.GetAttributeLength('rX') or 20
    for attr, values in (('rX', [p[0] for p in points]), ('rY', [p[1] for p in points])):
        con.SetAttribute(attr, [float(v) for v in values] + [-1.0] * (size - len(values)))
    return con


def plan_drawing(spec, terminals, diagram):
    """Calcula dónde va cada símbolo, sin escribir nada (sirve también en --dry-run).

    Devuelve ``None`` si el nodo de enganche no está en ningún diagrama: entonces la
    SED se crea igual, pero sin dibujo, y se avisa.
    """
    refs, grfnet = [], None
    for ref in spec.get('reference_nodes') or []:
        term = terminals.get(ref['node_id'])
        xy = diagram.position(term) if term is not None else None
        if xy is not None:
            refs.append((ref['x'], ref['y'], xy[0], xy[1]))
            grfnet = grfnet or diagram.net_of(term)
    transform = diagram_transform(refs)
    anchor = terminals.get(spec['connect_to_node'])
    anchor_xy = diagram.position(anchor) if anchor is not None else None
    if anchor_xy is None and transform is not None:
        # Nodo de paso sin símbolo propio: se sitúa por sus coordenadas.
        ref = next((r for r in spec.get('reference_nodes') or []
                    if r['node_id'] == spec['connect_to_node']), None)
        if ref is not None:
            anchor_xy = transform(ref['x'], ref['y'])
    grfnet = diagram.net_of(anchor) or grfnet
    if anchor_xy is None or grfnet is None:
        return None
    offset = 3 * diagram.size('SecSubProd')[0]
    new_xy = new_sed_positions(spec, anchor_xy, transform, offset)
    return {
        'grfnet': grfnet,
        'anchor_xy': anchor_xy,
        'new_xy': new_xy,
        'scaled': transform is not None,
        'references_used': len(refs),
    }


def draw_new_sed(spec, layout, diagram, term, line, substat):
    grfnet = layout['grfnet']
    a, b = layout['anchor_xy'], layout['new_xy']
    centro = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    code, sec = spec['sed_code'], spec['new_section_id']
    created = []
    created.append(_symbol(
        grfnet, f'G_{spec["new_node_id"]}', 'PointTerm', term, b,
        diagram.size('PointTerm'),
    ))
    g_line = _symbol(grfnet, f'G_{sec}', 'd_lin', line, centro, diagram.size('d_lin'),
                     rot=line_rotation(a, b))
    created.append(g_line)
    created.append(_connector(g_line, f'GCO_1_{sec}', 0, [centro, a]))
    created.append(_connector(g_line, f'GCO_2_{sec}', 1, [centro, b]))
    created.append(_symbol(
        grfnet, f'gnoT {code}', 'SecSubProd', substat, b,
        diagram.size('SecSubProd'),
    ))
    return created


def _terminal_type(typ_folder, code: str, spec: dict, nominal_kv: float):
    """Devuelve el TypLne del conductor, creándolo si el proyecto no lo tiene."""
    existing = [t for t in typ_folder.GetContents('*.TypLne') if t.loc_name == code]
    if existing:
        return existing[0], False
    typ = typ_folder.CreateObject('TypLne', code)
    typ.uline = nominal_kv
    typ.sline = spec['conductor_ampacity_a'] / 1000.0
    typ.InomAir = spec['conductor_ampacity_a'] / 1000.0
    typ.cohl_ = 1                      # aéreo
    typ.nlnph = 3
    typ.nneutral = 0
    typ.frnom = 60
    # R/X no viajan en el plan: se dejan a 0 y se avisa. El conversor los tomaría del
    # catálogo BD_Equipo; aquí solo se crea el tipo si no existía ya en el proyecto.
    return typ, True



class Creador:
    """Crea SED en el proyecto activo y acumula el resultado.

    El guion de un plan y el lote por alimentadores (``aplicar_lote_cargas.py``) usan
    la misma clase: crear una SED tiene que ser lo mismo venga de donde venga.
    ``terminals`` limita dónde se puede enganchar: en una red unida, a las barras del
    alimentador que se está procesando.
    """

    def __init__(self, app, project, grid, *, nominal_kv, lv_kv, terminals):
        self.grid = grid
        self.nominal_kv = nominal_kv
        self.lv_kv = lv_kv
        self.terminals = terminals
        self.existing_seds = {s.loc_name for s in app.GetCalcRelevantObjects('*.ElmSubstat')}
        self.typ_folder = app.GetProjectFolder('equip') or project
        self.diagram = Diagram(project)
        self.created, self.failed, self.skipped = [], [], []
        self.types_made, self.undrawn = [], []
        # Objects outside IntScheme stages (types and graphics) need explicit rollback.
        self.rollback_objects = []

    def crear(self, spec, *, dry_run=False):
        code = spec['sed_code']
        if code in self.existing_seds:
            self.skipped.append(f'{code}: ya existe un ElmSubstat con ese nombre')
            return
        anchor = self.terminals.get(spec['connect_to_node'])
        if anchor is None:
            self.failed.append(
                f'{code}: la barra {spec["connect_to_node"]!r} no está en el proyecto'
            )
            return
        net = _net_of(anchor, self.grid)
        layout = plan_drawing(spec, self.terminals, self.diagram)
        if layout is None:
            self.undrawn.append(f'{code}: el nodo {spec["connect_to_node"]} no está en ningún diagrama')
        dibujo = None if layout is None else {
            'x': layout['new_xy'][0], 'y': layout['new_xy'][1],
            'a_escala': layout['scaled'], 'referencias': layout['references_used'],
        }

        if dry_run:
            self.created.append({
                'sed_code': code, 'dry_run': True,
                'connect_to_node': spec['connect_to_node'],
                'distance_m': spec['distance_m'],
                'conductor': spec['conductor_code'],
                'red': net.loc_name,
                'diagrama': dibujo,
            })
            return

        try:
            # 1) Barra nueva en el punto indicado.
            term = net.CreateObject('ElmTerm', spec['new_node_id'])
            term.uknom = self.nominal_kv
            term.iUsage = 1
            term.outserv = 0
            for attr, key in (('GPSlat', 'gps_lat'), ('GPSlon', 'gps_lon')):
                if spec.get(key) is not None:
                    try:
                        setattr(term, attr, float(spec[key]))
                    except Exception:
                        pass

            # 2) Derivación aérea desde el nodo más cercano.
            typ, made = _terminal_type(self.typ_folder, spec['conductor_code'], spec, self.nominal_kv)
            if made:
                self.types_made.append(spec['conductor_code'])
                self.rollback_objects.append(typ)
            line = net.CreateObject('ElmLne', spec['new_section_id'])
            line.typ_id = typ
            line.dline = max(float(spec['length_km']), 1e-6)
            line.nlnum = 1
            line.inAir = 1
            cub_a = anchor.CreateObject('StaCubic', f'Cub1_{spec["new_section_id"]}')
            cub_a.obj_id = line
            cub_a.obj_bus = 0
            cub_b = term.CreateObject('StaCubic', f'Cub2_{spec["new_section_id"]}')
            cub_b.obj_id = line
            cub_b.obj_bus = 1

            # 3) SED con sus barras internas, transformador, acoplador y carga.
            substat = net.CreateObject('ElmSubstat', code)
            substat.sShort = 'T'
            substat.sType = f'{spec["installed_kva"]:g} kVA'
            mt = substat.CreateObject('ElmTerm', code)
            mt.uknom = self.nominal_kv
            mt.iUsage = 0
            bt = substat.CreateObject('ElmTerm', f'{code}_BT')
            bt.uknom = self.lv_kv
            bt.iUsage = 0

            tr_type = self.typ_folder.CreateObject('TypTr2', f'TR_{spec["installed_kva"]:g}kVA_{code}')
            self.rollback_objects.append(tr_type)
            tr_type.nt2ph = 3
            tr_type.strn = float(spec['strn_mva'])
            tr_type.frnom = 60
            tr_type.utrn_h = self.nominal_kv
            tr_type.utrn_l = self.lv_kv
            tr_type.uktr = 4.0
            tr_type.pcutr = max(float(spec['strn_mva']) * 10.0, 0.1)
            tr_type.tr2cn_h = 'D'
            tr_type.tr2cn_l = 'YN'
            tr_type.nt2ag = 5

            tr = substat.CreateObject('ElmTr2', f'TR_{code}')
            tr.typ_id = tr_type
            tr.ntnum = 1
            tr.outserv = 0
            cub_h = mt.CreateObject('StaCubic', f'Cub1_TR_{code}')
            cub_h.obj_id = tr
            cub_h.obj_bus = 0
            cub_l = bt.CreateObject('StaCubic', f'Cub2_TR_{code}')
            cub_l.obj_id = tr
            cub_l.obj_bus = 1

            coup = substat.CreateObject('ElmCoup', f'SW_{code}')
            coup.on_off = 1
            coup.aUsage = 'cbk'
            coup.nphase = 3
            cub_c1 = term.CreateObject('StaCubic', f'Cub1_SW_{code}')
            cub_c1.obj_id = coup
            cub_c1.obj_bus = 0
            cub_c2 = mt.CreateObject('StaCubic', f'Cub2_SW_{code}')
            cub_c2.obj_id = coup
            cub_c2.obj_bus = 1

            load = substat.CreateObject('ElmLod', code)
            load.mode_inp = 'PC'
            load.plini = float(spec['plini_mw'])
            load.qlini = float(spec['qlini_mvar'])
            load.coslini = float(spec['coslini']) or 0.95
            load.slini = float(spec['slini_mva'])
            load.outserv = 0
            cub_load = bt.CreateObject('StaCubic', f'Cub_{code}')
            cub_load.obj_id = load
            cub_load.obj_bus = 0

            # 4) Dibujo. Si falla, la SED ya está en la red y calcula: se avisa, pero
            # no se cuenta como fallo de creación.
            if layout is not None:
                try:
                    self.rollback_objects.extend(
                        draw_new_sed(spec, layout, self.diagram, term, line, substat)
                    )
                except Exception as exc:
                    self.undrawn.append(f'{code}: {type(exc).__name__}: {exc}')
                    dibujo = None

            self.created.append({
                'sed_code': code,
                'new_node': spec['new_node_id'],
                'connect_to_node': spec['connect_to_node'],
                'distance_m': spec['distance_m'],
                'conductor': spec['conductor_code'],
                'length_km': spec['length_km'],
                'installed_kva': spec['installed_kva'],
                'plini_mw': load.plini,
                'qlini_mvar': load.qlini,
                'red': net.loc_name,
                'diagrama': dibujo,
            })
            # Con varios alimentadores en el mismo proceso, la segunda vez que aparezca
            # el código ya existe.
            self.existing_seds.add(code)
            print(
                f'  + {code}: barra {spec["new_node_id"]} → {spec["connect_to_node"]} '
                f'({spec["distance_m"]:.1f} m, {spec["conductor_code"]})'
            )
        except Exception as exc:
            self.failed.append(f'{code}: {type(exc).__name__}: {exc}')



def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    to_create = plan.get('create') or []
    if plan.get('row_errors'):
        print(f'El plan tiene {len(plan["row_errors"])} fila(s) con error: no se crea nada.')
        for err in plan['row_errors'][:10]:
            print('  -', err)
        return 2
    if not to_create:
        print('El plan no contiene SED que crear.')
        return 2

    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de PowerFactory no disponible ({exc}). '
              'Use el Python de PowerFactory (PF 2024 → 3.12) con PYTHONPATH al API.')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:
        print(f'ERROR: no se pudo conectar a PowerFactory: {exc}')
        return 3

    project = _activate(app, args.project)
    print(f'proyecto: {project.loc_name}')
    print(f'caso activo: {app.GetActiveStudyCase()}')

    grid = _grid_of(app)
    print(f'red: {grid.loc_name}')
    nominal_kv = float(plan.get('nominal_kv') or 0) or 22.9
    lv_kv = float(plan.get('lv_kv') or 0.22)

    creador = Creador(
        app, project, grid, nominal_kv=nominal_kv, lv_kv=lv_kv,
        terminals={t.loc_name: t for t in app.GetCalcRelevantObjects('*.ElmTerm')},
    )
    for spec in to_create:
        creador.crear(spec, dry_run=args.dry_run)
    created, failed, skipped = creador.created, creador.failed, creador.skipped
    types_made, undrawn = creador.types_made, creador.undrawn

    print(f'\nSED creadas   : {len(created)}{" (simulación)" if args.dry_run else ""}')
    print(f'SED omitidas  : {len(skipped)}')
    for s in skipped[:10]:
        print('  -', s)
    print(f'Fallos        : {len(failed)}')
    for f in failed[:10]:
        print('  -', f)
    print(f'Sin dibujar   : {len(undrawn)}')
    for u in undrawn[:10]:
        print('  -', u)
    if types_made:
        print(
            f'TypLne creados sin R/X: {", ".join(sorted(set(types_made)))}. '
            'Revíselos en PowerFactory: el plan no transporta impedancias.'
        )

    result = {
        'project': project.loc_name,
        'feeder': plan.get('feeder'),
        'dry_run': bool(args.dry_run),
        'created': created,
        'skipped': skipped,
        'failed': failed,
        'undrawn': undrawn,
        'line_types_created': sorted(set(types_made)),
    }

    if args.run_load_flow and not args.dry_run:
        ldf = app.GetFromStudyCase('ComLdf')
        ret = ldf.Execute()
        valid = app.IsLdfValid()
        result['load_flow'] = {
            'return_code': ret, 'ldf_valid': valid,
            'converged': ret == 0 and bool(valid),
        }
        print(f'\nflujo tras crear: ComLdf -> {ret}  IsLdfValid -> {valid}')
        if ret == 0 and valid:
            voltages = []
            for bus in app.GetCalcRelevantObjects('*.ElmTerm'):
                try:
                    if bus.HasResults():
                        voltages.append((bus.GetAttribute('m:u'), bus.loc_name))
                except Exception:
                    pass
            if voltages:
                voltages.sort()
                result['load_flow']['vm_min'] = voltages[0][0]
                result['load_flow']['vm_min_bus'] = voltages[0][1]
                result['load_flow']['vm_max'] = voltages[-1][0]
                print(
                    f'  tensión min {voltages[0][0]:.4f} p.u. en {voltages[0][1]}  '
                    f'max {voltages[-1][0]:.4f}'
                )
                # Las barras nuevas deben quedar energizadas, no a 0,0 p.u.
                nuevas = {c['new_node'] for c in created if c.get('new_node')}
                muertas = [n for v, n in voltages if n in nuevas and v <= 0.01]
                result['load_flow']['new_buses_unenergised'] = muertas
                if muertas:
                    print(f'  AVISO: barras nuevas sin energizar: {muertas}')

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
        )
        print(f'\nInforme: {args.output_json}')

    return 0 if created and not failed else 2


if __name__ == '__main__':
    raise SystemExit(main())
