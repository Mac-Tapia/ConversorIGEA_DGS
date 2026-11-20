"""Matriz de operaciones del asistente, derivada del código (026:RF-51; A0 del plan de control integral).

El asistente tiene un catálogo de tareas (``tareas.py``), un inventario del equipo con sus efectos, carril y confirmación
(``equipo.inventario_equipo``), vías directas que dejan recibo sin plan (``equipo.recibo_directo``) y herramientas de
lectura del proyecto. Nada de eso decía qué operación está probada, cuál falta y quién la lleva: una tabla a mano se
desfasaría como la de estado de specs (033). Aquí todo se deriva cada vez:

- una fila por tarea del catálogo, con su vía (consulta, plan, proceso o etapas), función, efectos, carril,
  confirmación y las pruebas que la citan por su nombre;
- una fila por vía directa con recibo, sacada del código con ``ast`` (cada ``recibo_directo('…')``);
- una fila por herramienta de lectura del proyecto;
- una fila «pendiente» por cada tarea abierta de las specs del asistente, leída con ``estado_specs`` (el único lector de
  specs, 033), con su criterio de hecho y su responsable.

Los niveles no se mezclan: «declarada» (está en el catálogo), «probada» (alguna prueba la cita) y la aceptación del
dominio, que esta herramienta nunca da por medida. Una operación que falla no sale del denominador.

Uso:
    python tools/matriz_operaciones.py                 # tabla en markdown
    python tools/matriz_operaciones.py --json          # la misma matriz en JSON
    python tools/matriz_operaciones.py --salida F      # la escribe en F (.md o .json), fuera de git
    python tools/matriz_operaciones.py --comprobar     # sale con 1 si hay una operación sin prueba o un hueco sin dueño
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: Specs cuyas tareas abiertas son operaciones del asistente que aún no existen (026:RF-51).
SPECS_DEL_ASISTENTE = ('026', '047', '070')

#: Responsable de cada hueco, del tablero del 18-11 (acta A0–A6 de ce). Solo puede bajar: una tarea que se cierra sale de
#: aquí, y una abierta sin fila hace fallar ``--comprobar``.
RESPONSABLES: dict[str, str] = {
    '026:T16': 'ce (ASISTENTE-B)',
    '047:T4': 'sin asignar: evaluación real (GPU)', '047:T7': 'sin asignar: destilación del LLM (GPU)',
    '047:T8': 'sin asignar: revisión que distingue defectos',
    '070:T11': 'usuario: candidato en DIgSILENT',
    '070:T22': 'ce: reentreno en GPU (turno 6 de TURNOS_GPU_ce_2026-11-19)',
}

_VIA = {'consulta': 'consulta', 'trabajo': 'plan', 'proceso': 'proceso', 'etapas': 'etapas'}


def _importar_paquete(raiz: Path):
    src = str(raiz / 'src')
    if src not in sys.path:
        sys.path.insert(0, src)
    from convertersmartgrid.aplicacion.asistente.equipo import inventario_equipo

    return inventario_equipo()


def _estado_specs(raiz: Path):
    herramientas = str(raiz / 'tools')
    sys.path.insert(0, herramientas)
    try:
        import estado_specs
    finally:
        sys.path.remove(herramientas)
    return estado_specs


def _textos_de_pruebas(raiz: Path) -> list[tuple[str, str]]:
    return [(p.name, p.read_text(encoding='utf-8', errors='replace')) for p in sorted((raiz / 'tests').glob('test_*.py'))]


def _citan(nombre: str, pruebas: list[tuple[str, str]]) -> list[str]:
    patron = re.compile(r"""['"]""" + re.escape(nombre) + r"""['"]""")
    return [f for f, texto in pruebas if patron.search(texto)]


def vias_directas(raiz: Path = RAIZ) -> list[dict]:
    """Cada ``recibo_directo('herramienta', …)`` del paquete: lo que escribe sin plan (067:RF-41)."""
    out: dict[str, set[str]] = {}
    for f in sorted((raiz / 'src' / 'convertersmartgrid').rglob('*.py')):
        try:
            arbol = ast.parse(f.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for n in ast.walk(arbol):
            if (isinstance(n, ast.Call) and getattr(n.func, 'id', getattr(n.func, 'attr', None)) == 'recibo_directo'
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                out.setdefault(n.args[0].value, set()).add(f.relative_to(raiz).as_posix())
    return [{'herramienta': h, 'ficheros': sorted(fs)} for h, fs in sorted(out.items())]


def matriz(raiz: Path = RAIZ) -> dict:
    """Las operaciones del asistente con su nivel de evidencia y los huecos con su dueño (026:RF-51)."""
    inventario = _importar_paquete(raiz)
    pruebas = _textos_de_pruebas(raiz)
    filas = []
    for h in inventario['herramientas']:
        citan = _citan(h['herramienta'], pruebas)
        filas.append({'operacion': f"tarea.{h['herramienta']}", 'via': _VIA.get(h['modo'], h['modo']),
                      'funcion': h['funcion'], 'escribe': h['escribe'], 'efectos': h['efectos'], 'carril': h['carril'],
                      'confirmacion': h['confirmacion_obligatoria'], 'pruebas': citan,
                      'estado': 'probada' if citan else 'declarada', 'aceptacion_dominio': 'no medida'})
    for d in vias_directas(raiz):
        citan = _citan(d['herramienta'], pruebas)
        filas.append({'operacion': f"directa.{d['herramienta']}", 'via': 'directa con recibo', 'funcion': d['ficheros'][0],
                      'escribe': True, 'efectos': ['escribe'], 'carril': 'engine', 'confirmacion': 'el clic o la decisión '
                      'anotada (067:RF-41)', 'pruebas': citan, 'estado': 'probada' if citan else 'declarada',
                      'aceptacion_dominio': 'no medida'})
    for h in inventario['lectura_proyecto']['herramientas']:
        nombre = h['nombre'] if isinstance(h, dict) else str(h)
        citan = _citan(nombre, pruebas)
        filas.append({'operacion': f'lectura.{nombre}', 'via': 'lectura del proyecto', 'funcion': 'lectura_proyecto',
                      'escribe': False, 'efectos': ['lee'], 'carril': 'consulta', 'confirmacion': False,
                      'pruebas': citan, 'estado': 'probada' if citan else 'declarada', 'aceptacion_dominio': 'no medida'})
    es = _estado_specs(raiz)
    pendientes = []
    for spec in es.leer_specs(raiz):
        if spec.numero not in SPECS_DEL_ASISTENTE:
            continue
        for t in spec.abiertas:
            clave = f'{spec.numero}:{t.id}'
            lineas = t.texto.splitlines()
            criterio = next((l.strip() for l in lineas if l.strip().startswith('Hecho cuando')), '')
            pendientes.append({'operacion': clave, 'estado': 'pendiente', 'que': lineas[0].strip(),
                               'rf': sorted(es.rf_de_texto(t.texto)), 'criterio': criterio,
                               'responsable': RESPONSABLES.get(clave, '')})
    return {'operaciones': filas, 'pendientes': pendientes,
            'recuento': {'operaciones': len(filas), 'probadas': sum(f['estado'] == 'probada' for f in filas),
                         'pendientes': len(pendientes), 'aceptadas_en_el_dominio': 0},
            'autonomia_habilitada': inventario['autonomia_habilitada']}


def problemas(m: dict) -> list[str]:
    """Lo que ``--comprobar`` no acepta: una operación sin prueba, un hueco sin criterio o sin dueño, y un dueño de una
    tarea que ya no está abierta (la tabla solo baja)."""
    out = [f"{f['operacion']}: ninguna prueba la cita" for f in m['operaciones'] if f['estado'] != 'probada']
    for p in m['pendientes']:
        if not p['responsable']:
            out.append(f"{p['operacion']}: hueco sin responsable en RESPONSABLES")
        if not p['criterio'] and not re.search(r'\[(DIgSILENT|GPU)\]', p['que']):
            out.append(f"{p['operacion']}: hueco sin «Hecho cuando»")
    abiertas = {p['operacion'] for p in m['pendientes']}
    out += [f'{k}: ya no está abierta; quítela de RESPONSABLES' for k in sorted(set(RESPONSABLES) - abiertas)]
    return out


def tabla(m: dict) -> str:
    r = m['recuento']
    lineas = ['# Matriz de operaciones del asistente (026:RF-51)', '',
              f"{r['operaciones']} operaciones, {r['probadas']} con prueba que las cita, {r['pendientes']} pendientes; "
              'aceptación del dominio: no medida por esta herramienta. Autonomía habilitada: '
              f"{'sí' if m['autonomia_habilitada'] else 'no'}.", '',
              '| Operación | Vía | Escribe | Efectos | Carril | Confirmación | Pruebas | Estado |',
              '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for f in m['operaciones']:
        lineas.append(f"| `{f['operacion']}` | {f['via']} | {'sí' if f['escribe'] else 'no'} | {', '.join(f['efectos'])} "
                      f"| {f['carril']} | {f['confirmacion']} | {len(f['pruebas'])} | {f['estado']} |")
    lineas += ['', '## Pendientes', '', '| Operación | Qué | RF | Criterio | Responsable |', '| --- | --- | --- | --- | --- |']
    for p in m['pendientes']:
        lineas.append(f"| `{p['operacion']}` | {p['que'][:90]} | {', '.join(p['rf'])} | {p['criterio'][:80]} "
                      f"| {p['responsable']} |")
    return '\n'.join(lineas) + '\n'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--json', action='store_true', help='la matriz en JSON')
    ap.add_argument('--salida', type=Path, help='fichero de salida (.md o .json), fuera de git')
    ap.add_argument('--comprobar', action='store_true', help='sale con 1 si hay operaciones sin prueba o huecos sin dueño')
    a = ap.parse_args(argv)
    m = matriz(RAIZ)
    if a.comprobar:
        malos = problemas(m)
        for x in malos:
            print(x)
        return 1 if malos else 0
    texto = json.dumps(m, ensure_ascii=False, indent=2) if a.json or (a.salida and a.salida.suffix == '.json') else tabla(m)
    if a.salida:
        from convertersmartgrid.dominio.util import publicar_duradero

        publicar_duradero(a.salida, texto)
    else:
        sys.stdout.write(texto)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
