"""Reglas del proyecto: lo que se aplica a TODO alimentador, venga de TXT o de base.

Son las decisiones tomadas con la distribuidora al convertir sus entregas reales. Viven
aquí, en un solo sitio, y las aplican todas las vías —lote (``batch``), red unida en un
DGS (``batch.convert_group``), interfaz web, CLI, GUI heredada y los módulos de cargas—
para que un alimentador salga igual lo convierta quien lo convierta.

Sobre el **dataset** (una vez por entrada):

* Coordenadas que faltan → por el grafo de la red (:mod:`igea_dgs.coordenadas`).
* Catálogo de parámetros del proyecto (``input/catalogo_parametros.xlsx``): completa
  los códigos de conductor que el BD_Equipo / la base no trae (por material y sección),
  y es la fuente entera cuando la base no tiene tablas ``CYMEQ*``.

Sobre cada **modelo** (por alimentador):

1. Tramos puente ``DEFAULT`` fundidos; sus seccionadores pasan a ``ElmCoup``
   (:mod:`igea_dgs.puentes`).
2. Trafomix —medición MT registrada como SED ``M…``— excluidos (:mod:`igea_dgs.trafomix`).
3. SED con más carga que kVA → tamaño normalizado que la cubre, listado
   (:mod:`igea_dgs.sed_potencia`).
4. Correcciones de ficha del catálogo (filas ``ficha``/``derivado``), conservando código,
   sección y tipo.
5. Diagrama en hoja **A0**, símbolos según la cuadrícula, todos los tramos dibujados.

Y sobre el **resultado**: auditoría de completitud contra la entrada
(:func:`auditar_completitud`). Un alimentador que pierde un elemento no es «ok».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .powerfactory_env import project_root

#: Marcador de tipo para los tramos puente mientras se construye el modelo. Se funden
#: antes de escribir y ningún DGS lo lleva (lo comprueba la auditoría).
MARCADOR_DEFAULT = {'ID': 'DEFAULT', 'R1': '0.4', 'R0': '0.4', 'X1': '0.4', 'X0': '1.4',
                    'B1': '0', 'B0': '0', 'Amps': '400'}


@dataclass(frozen=True)
class Reglas:
    hoja: str | None = 'A0'
    fundir_puentes: bool = True
    excluir_trafomix: bool = True
    redimensionar_sed: bool = True
    dibujar_todo: bool = True


#: Las reglas del proyecto. Es lo que usan todas las vías por defecto.
REGLAS_PROYECTO = Reglas()
#: Conversión literal de la entrada, sin ninguna regla (pruebas de fidelidad).
SIN_REGLAS = Reglas(hoja=None, fundir_puentes=False, excluir_trafomix=False,
                    redimensionar_sed=False, dibujar_todo=False)


def catalogo_del_proyecto() -> Path | None:
    """``input/catalogo_parametros.xlsx`` del proyecto, si existe."""
    from .catalog import CATALOG_FILENAME, input_dir

    ruta = input_dir(project_root()) / CATALOG_FILENAME
    return ruta if ruta.is_file() else None


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

@dataclass
class InformeEntrada:
    coordenadas: str = ''
    catalogo: str = ''
    completados_catalogo: dict[str, str] = field(default_factory=dict)
    sin_parametros: list[str] = field(default_factory=list)

    def texto(self) -> str:
        return ' '.join(x for x in (self.coordenadas, self.catalogo) if x)


def codigos_en_red(dataset) -> set[tuple[str, bool]]:
    return {(str(lc.get('LineCableID', '')), str(lc.get('Overhead', '1')) == '1')
            for lc in dataset.line_configurations.values() if lc.get('LineCableID')}


def preparar_dataset(dataset, *, catalogo: Path | str | None = None) -> InformeEntrada:
    """Aplica al dataset las reglas de entrada. Idempotente."""
    from .coordenadas import completar_coordenadas

    informe = InformeEntrada()
    informe.coordenadas = completar_coordenadas(dataset).texto()

    tablas = dataset.equipment_tables
    usados = codigos_en_red(dataset)
    if catalogo:
        from .catalog import tablas_equipo_desde_catalogo
        from .dataset import TABLAS_TIPOS_AEREO, TABLAS_TIPOS_SUBTERRANEO

        presentes = {str(f.get('ID', '')) for t in (TABLAS_TIPOS_AEREO + TABLAS_TIPOS_SUBTERRANEO)
                     for f in tablas.get(t, ())}
        faltan = {(c, aereo) for c, aereo in usados if c not in presentes and c.upper() != 'DEFAULT'}
        if faltan:
            eq = tablas_equipo_desde_catalogo(catalogo, codigos_en_red=faltan)
            codigos_faltan = {c for c, _ in faltan}
            for tabla, filas in eq.tablas.items():
                nuevas = [f for f in filas if f['ID'] in codigos_faltan]
                if nuevas:
                    tablas[tabla] = tuple(tablas.get(tabla, ())) + tuple(nuevas)
            informe.completados_catalogo = dict(eq.completados)
            informe.sin_parametros = sorted(eq.sin_resolver)
            añadidos = len(codigos_faltan) - len(eq.sin_resolver)
            informe.catalogo = (f'Catálogo del proyecto: {añadidos} código(s) de conductor que la '
                                f'entrada no traía, tomados de {Path(catalogo).name}.')
            if eq.sin_resolver:
                informe.catalogo += f' Sin parámetros en ningún sitio: {", ".join(eq.sin_resolver)}.'

    # Los puentes necesitan un tipo mientras se construye el modelo, y no uno
    # «parecido» por nombre: el marcador, que se funde antes de escribir.
    if any(c.upper() == 'DEFAULT' for c, _ in usados):
        for tabla in ('LINE', 'CONCENTRIC NEUTRAL CABLE'):
            if not any(str(f.get('ID', '')).upper() == 'DEFAULT' for f in tablas.get(tabla, ())):
                tablas[tabla] = tuple(tablas.get(tabla, ())) + (dict(MARCADOR_DEFAULT),)
    return informe


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

def aplicar_reglas(model, reglas: Reglas = REGLAS_PROYECTO, *,
                   correcciones: dict | None = None) -> dict[str, Any]:
    """Aplica al modelo, en el sitio, las reglas del proyecto. Devuelve lo que hizo."""
    informe: dict[str, Any] = {}
    if correcciones:
        from .catalog import aplicar_correcciones

        informe['catalogo'] = [c.linea() for c in aplicar_correcciones(model, dict(correcciones))]
    if reglas.fundir_puentes:
        from .puentes import fundir_puentes

        p = fundir_puentes(model)
        informe['puentes'] = {'tramos': p.tramos, 'fundidos': p.fundidos,
                              'interruptores': p.interruptores, 'texto': p.texto()}
    if reglas.excluir_trafomix:
        from .trafomix import excluir_trafomix

        t = excluir_trafomix(model)
        informe['trafomix'] = {'excluidos': t.excluidos,
                               'cargas_nulas_quitadas': t.cargas_nulas_quitadas,
                               'con_carga_en_mt': t.cargas_conservadas_mt}
    if reglas.redimensionar_sed:
        from .sed_potencia import redimensionar_sobrecargadas

        informe['sed_redimensionadas'] = [r.linea() for r in redimensionar_sobrecargadas(model)]
    if reglas.hoja:
        model.diagram_sheet = reglas.hoja
    if reglas.dibujar_todo:
        model.diagram_max_stub_m = -1.0
    return informe


# ---------------------------------------------------------------------------
# Completitud
# ---------------------------------------------------------------------------

def auditar_completitud(dataset, networks: Iterable[str], model, tablas: dict,
                        informes: Iterable[dict]) -> dict[str, Any]:
    """Cada elemento de la entrada, en su sitio del DGS; si no, un fallo que lo dice.

    ``informes`` son los de :func:`aplicar_reglas` de cada alimentador: lo que las
    reglas quitaron o transformaron a propósito no cuenta como pérdida.
    """
    from .model import _calc_p_q

    informes = list(informes)
    nets = list(networks)
    secciones = {s for n in nets for s in dataset.feeders.get(n, ())}
    cargas = [(k, r) for n in nets for k, r in dataset.customer_loads_by_feeder.get(n, ())
              if k in dataset.load_placements]
    kw = kvar = 0.0
    for _k, fila in cargas:
        p, q, _pf = _calc_p_q(fila)
        kw += p * 1000.0
        kvar += q * 1000.0
    maniobras = sum(len(dataset.switching_by_feeder.get(n, ())) for n in nets)

    puentes = sum((i.get('puentes') or {}).get('tramos', 0) for i in informes)
    interruptores = sum((i.get('puentes') or {}).get('interruptores', 0) for i in informes)
    nulas = sum((i.get('trafomix') or {}).get('cargas_nulas_quitadas', 0) for i in informes)

    def n(cls: str) -> int:
        return len(tablas.get(cls, {}).get('rows_dict', []))

    kw_dgs = sum(float(r.get('plini') or 0) for r in tablas.get('ElmLod', {}).get('rows_dict', [])) * 1000
    kvar_dgs = sum(float(r.get('qlini') or 0) for r in tablas.get('ElmLod', {}).get('rows_dict', [])) * 1000
    # Los interruptores de red de un puente van como ElmCoup; los enlaces entre
    # alimentadores también, pero esos no vienen de ningún dispositivo de la base.
    enlaces = len(getattr(getattr(model, 'combined', None), 'ties', ()) or ())

    fallos = []
    if n('ElmLne') + puentes != len(secciones):
        fallos.append(f'tramos: entrada {len(secciones)} ≠ ElmLne {n("ElmLne")} + puentes {puentes}')
    if n('ElmLod') + nulas != len(cargas):
        fallos.append(f'cargas: entrada {len(cargas)} ≠ ElmLod {n("ElmLod")} + trafomix de 0 kW {nulas}')
    if abs(kw_dgs - kw) > max(0.5, 1e-4 * abs(kw)):
        fallos.append(f'kW: entrada {kw:,.1f} ≠ DGS {kw_dgs:,.1f}')
    if abs(kvar_dgs - kvar) > max(0.5, 1e-4 * abs(kvar)):
        fallos.append(f'kvar: entrada {kvar:,.1f} ≠ DGS {kvar_dgs:,.1f}')
    if n('StaSwitch') + interruptores != maniobras:
        fallos.append(f'maniobras: entrada {maniobras} ≠ StaSwitch {n("StaSwitch")} '
                      f'+ interruptores de puente {interruptores}')
    # Un TypLne DEFAULT solo es legítimo si lo usa una línea real (> 10 m); si vale el
    # marcador de los puentes, algún puente se quedó sin fundir.
    from .puentes import es_puente

    if any('puentes' in i for i in informes) and any(es_puente(ln) for ln in model.lines):
        fallos.append('quedan tramos puente DEFAULT sin fundir en el DGS')
    return {
        'entrada': {'tramos': len(secciones), 'cargas': len(cargas), 'kW': round(kw, 3),
                    'kvar': round(kvar, 3), 'maniobras': maniobras},
        'dgs': {'ElmLne': n('ElmLne'), 'ElmLod': n('ElmLod'), 'ElmSubstat': n('ElmSubstat'),
                'StaSwitch': n('StaSwitch'), 'ElmCoup_red': interruptores + enlaces,
                'kW': round(kw_dgs, 3), 'kvar': round(kvar_dgs, 3)},
        'fallos': fallos,
    }
