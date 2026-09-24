"""Informa de qué módulos de PowerFactory puede usar esta licencia.

Por qué hace falta. El manual documenta los 50 capítulos de funciones, pero la licencia
decide cuáles se pueden ejecutar. Diseñar el PIDE sobre un módulo que la licencia no
cubre es trabajo tirado, y no hay forma de saberlo leyendo el manual.

Por qué no basta con preguntar a la API. ``app.LicenceHasModule()`` existe, pero es para
las **extensiones de terceros** —el mecanismo con el que un integrador vende scripts DPL
protegidos, descrito en ``LicenceExtensionReference_en.pdf``—, no para los módulos
funcionales de DIgSILENT. Preguntarle por «Reliability Analysis» devuelve 0 aunque el
módulo esté licenciado, que es justo la respuesta que induce a error.

Cómo lo resuelve. Empíricamente: crea cada orden de cálculo en un caso de estudio real y
la ejecuta. Un módulo sin licencia falla con un error de licencia; uno licenciado
devuelve un código de cálculo. Es la única prueba que no miente.

    py -3.12 tools\\check_pf_license.py --project 20260921-034855_IGEA_AL104

Sin ``--project`` usa el proyecto activo. Conviene elegir un alimentador pequeño: algunas
órdenes recorren toda la red.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover
        pass


def _pf_dir() -> Path | None:
    env = os.environ.get('PF_PYTHON', '').strip()
    if env and Path(env).is_dir():
        return Path(env)
    root = Path(r'C:\Program Files\DIgSILENT')
    if root.is_dir():
        # Por número de versión, no por texto: «3.9» ordena después de «3.12» si se
        # comparan como cadenas, y entonces se elige la carpeta equivocada y la
        # importación falla con «DLL load failed», que no dice nada de la causa.
        def clave(p: Path) -> tuple[int, ...]:
            return tuple(int(x) if x.isdigit() else -1 for x in p.name.split('.'))

        for cand in sorted(root.glob('PowerFactory */Python/3.*'), key=clave, reverse=True):
            if (cand / 'powerfactory.pyd').is_file():
                return cand
    return None


#: ``(clase de orden, qué hace, capítulo del manual, para qué sirve en el PIDE)``.
#: El orden es el de utilidad para el plan, no el del manual.
ORDENES = (
    ('ComLdf', 'Flujo de potencia', 24, 'Base de todo el análisis'),
    ('ComShc', 'Cortocircuito', 25, 'Dimensionar protecciones, verificar Ithr'),
    ('ComSimoutage', 'Contingencias N-1', 26, 'Respaldo entre alimentadores'),
    ('ComRel3', 'Fiabilidad', 45, 'SAIDI, SAIFI y ENS a 1 US$/kWh'),
    ('ComRelreport', 'Informe de fiabilidad', 45, 'Salida del análisis de fiabilidad'),
    ('ComOpf', 'Flujo óptimo de potencia', 38, 'Optimización con restricciones de red'),
    ('ComTececo', 'Evaluación técnico-económica', 43, 'VAN de la estrategia de expansión'),
    ('ComTececocmp', 'Comparación técnico-económica de casos', 43,
     'Comparar alternativas de inversión — el núcleo del PIDE'),
    ('ComStatsim', 'Simulación cuasi-dinámica', 27, 'Factor de pérdidas real, no típico'),
    ('ComCapo', 'Colocación óptima de condensadores', 41, 'Compensación del Anexo 6'),
    ('ComTieopt', 'Punto de apertura óptimo', 41, 'Reconfiguración de la red'),
    ('ComBbone', 'Cálculo de troncal (backbone)', 41, 'Troncal vs. derivaciones del TdR'),
    ('ComBalance', 'Balance de fases', 41, 'Desbalance de carga que el TdR nombra'),
    ('ComVoltplan', 'Optimización del perfil de tensión', 41, 'Caída de tensión'),
    ('ComVsag', 'Huecos de tensión', 41, 'Calidad de producto'),
    ('ComLvldf', 'Flujo de potencia de BT', 41, 'Etapa BT del Anexo 6'),
    ('ComProtgraphic', 'Coordinación de protecciones', 32, 'Selectividad; calidad'),
    ('ComHldf', 'Flujo armónico', 35, 'Calidad de producto'),
)



def _clasificar(mensaje: str) -> str:
    """Traduce el error de PowerFactory a una respuesta sobre la licencia."""
    m = mensaje.lower()
    if any(k in m for k in ('licen', 'not authorized', 'no autoriz', 'module')):
        return 'SIN LICENCIA'
    if any(k in m for k in ('unknown class', 'clase desconocida', 'invalid class')):
        return 'NO EXISTE en esta versión'
    return f'error de ejecución ({mensaje[:70]})'


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--project', help='Proyecto a activar. Por defecto, el activo.')
    p.add_argument('--list-projects', action='store_true')
    p.add_argument('--no-execute', action='store_true',
                   help='Solo crear las órdenes, sin ejecutarlas (más rápido, menos fiable).')
    args = p.parse_args(argv)

    pf = _pf_dir()
    if pf is None:
        print('No se encontró powerfactory.pyd. Defina PF_PYTHON.', file=sys.stderr)
        return 2
    sys.path.insert(0, str(pf))
    try:
        import powerfactory  # type: ignore
    except ImportError as exc:
        print(f'No se pudo importar powerfactory desde {pf}: {exc}', file=sys.stderr)
        print(f'Intérprete actual: {sys.version.split()[0]}; PF 2024 pide 3.12.',
              file=sys.stderr)
        return 2

    app = powerfactory.GetApplication()
    if app is None:
        print('PowerFactory no respondió. ¿Está abierto en otra sesión?', file=sys.stderr)
        return 3

    usuario = app.GetCurrentUser()
    if args.list_projects:
        for pr in (usuario.GetContents('*.IntPrj') if usuario else []):
            print(pr.loc_name)
        return 0

    if args.project:
        app.ActivateProject(args.project)
    proyecto = app.GetActiveProject()
    if proyecto is None:
        print('No hay proyecto activo. Use --project o actívelo en PowerFactory.',
              file=sys.stderr)
        print('Con --list-projects se ven los disponibles.', file=sys.stderr)
        return 3

    caso = app.GetActiveStudyCase()
    if caso is None:
        # Sin caso activo, GetCalcRelevantObjects devuelve vacío y las órdenes no
        # tienen dónde vivir. Se activa el primero que haya.
        casos = proyecto.GetContents('*.IntCase', 1)
        if casos:
            casos[0].Activate()
            caso = app.GetActiveStudyCase()
    if caso is None:
        print('El proyecto no tiene caso de estudio que activar.', file=sys.stderr)
        return 3

    print(f'Proyecto: {proyecto.loc_name}')
    print(f'Caso:     {caso.loc_name}')
    print(f'Barras:   {len(app.GetCalcRelevantObjects("ElmTerm"))}')
    print()
    print('Nota: LicenceHasModule() NO sirve para esto —es para extensiones de')
    print('terceros—, así que cada módulo se comprueba ejecutándolo de verdad.')
    print()

    ancho = max(len(c) for c, _, _, _ in ORDENES)
    disponibles, ausentes = [], []
    for clase, que, cap, para in ORDENES:
        try:
            orden = app.GetFromStudyCase(clase)
        except Exception as exc:  # noqa: BLE001 - la API lanza tipos propios
            estado = _clasificar(str(exc))
            ausentes.append((clase, que, cap, estado))
            print(f'  {clase:<{ancho}}  {que:<34} {estado}')
            continue
        if orden is None:
            ausentes.append((clase, que, cap, 'no se pudo crear la orden'))
            print(f'  {clase:<{ancho}}  {que:<34} no se pudo crear la orden')
            continue
        # Cuidado: GetFromStudyCase con un nombre de clase que no existe **no falla**,
        # crea una IntFolder con ese nombre. Sin esta comprobación el sondeo confunde
        # «la clase se llama de otra forma» con «el módulo no está», y además va
        # dejando carpetas espurias en el caso de estudio del usuario.
        real = orden.GetClassName()
        if real != clase:
            try:
                orden.Delete()
            except Exception:  # noqa: BLE001
                pass
            ausentes.append((clase, que, cap, f'la clase no existe (se creó {real})'))
            print(f'  {clase:<{ancho}}  {que:<34} la clase no existe en esta versión')
            continue
        if args.no_execute:
            print(f'  {clase:<{ancho}}  {que:<34} orden creada (sin ejecutar)')
            continue
        try:
            rc = orden.Execute()
            estado = 'DISPONIBLE' if rc == 0 else f'DISPONIBLE (no convergió, rc={rc})'
            disponibles.append((clase, que, cap, para))
        except Exception as exc:  # noqa: BLE001
            estado = _clasificar(str(exc))
            ausentes.append((clase, que, cap, estado))
        print(f'  {clase:<{ancho}}  {que:<34} {estado}')

    print()
    print(f'Disponibles: {len(disponibles)}   No disponibles: {len(ausentes)}')
    if disponibles:
        print()
        print('Utilizables para el PIDE:')
        for clase, que, cap, para in disponibles:
            print(f'  · {que} (cap. {cap}) — {para}')
    if ausentes:
        print()
        print('No utilizables, y qué se pierde:')
        for clase, que, cap, estado in ausentes:
            print(f'  · {que} (cap. {cap}) — {estado}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
