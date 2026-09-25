"""Segunda vía de entrada: base de datos Access de CYMDIST (``.mdb``).

El conversor tiene dos alternativas de entrada, no una:

1. **TXT** (``RED`` / ``CARGA`` / ``BD_Equipo``) — la vía principal. No necesita
   CYMDIST, ni licencia, ni driver de Access, y funciona en cualquier sistema.
2. **Access** (este módulo) — lee la base de CYMDIST directamente y ahorra el paso
   manual de exportar. Requiere Windows con el driver «Microsoft Access Driver» y
   ``pyodbc`` (extra ``igea-dgs[access]``).

Ambas producen el **mismo** ``CymdistDataset``, de modo que el resto del motor
—modelo, DGS, validación, lote— es idéntico y ya está probado. La equivalencia entre
las dos vías se verifica en ``tests/test_access_input.py``.

Correspondencia verificada contra un export real de 96 alimentadores y 38.657 tramos:

===========================  ==========================================
Tabla Access                 Sección del TXT
===========================  ==========================================
``CYMNODE``                  ``[NODE]``
``CYMSECTION``               ``[SECTION]``
``CYMHEADNODE``              ``[HEADNODES]``
``CYMSOURCE``                ``[SOURCE]``
``CYMOVERHEADLINE`` +
``CYMUNDERGROUNDLINE``       ``[LINE CONFIGURATION]``
``CYMSECTIONDEVICE``         el enlace dispositivo↔tramo que el TXT ya trae resuelto
``CYMCUSTOMERLOAD``          ``[CUSTOMER LOADS]``
``CYMSWITCH``                ``[SWITCH SETTING]``
``CYMSECTIONALIZER``         ``[SECTIONALIZER SETTING]``
``CYMINTERMEDIATEPOINT``     ``[INTERMEDIATE NODES]``
``CYMEQOVERHEADLINE``        ``[LINE]`` del BD_Equipo
``CYMEQCABLE``               ``[CONCENTRIC NEUTRAL CABLE]`` del BD_Equipo
===========================  ==========================================

Dos conversiones que no son evidentes y están comprobadas contra el TXT:

- ``CYMSOURCE.OperatingVoltageA`` es la tensión **fase-neutro**: la tensión nominal
  del TXT es ese valor por ``√3`` (5,7735 → 10,0 kV; 13,2213 → 22,9 kV).
- ``CYMCUSTOMERLOAD`` guarda **varios años de carga** por dispositivo (8.055 filas
  para 7.287 dispositivos). El export TXT toma el año más reciente, y eso es lo que
  se replica por defecto. ``load_year`` permite elegir otro escenario — información
  que el TXT no lleva.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .dataset import CymdistDataset

ACCESS_DRIVER = 'Microsoft Access Driver (*.mdb, *.accdb)'

# CYMSECTIONDEVICE.DeviceType
DEV_UNDERGROUND_LINE = 1
DEV_OVERHEAD_LINE = 2
DEV_SECTIONALIZER = 12
DEV_SWITCH = 13
DEV_SPOT_LOAD = 20

# CYMSECTIONDEVICE.Location: 0 = el tramo entero (líneas), 1 = extremo From, 2 = extremo To.
_LOAD_LOCATION = {1: '0', 2: '1'}        # el TXT usa '0'=FromNode, '1'=ToNode
_SWITCH_LOCATION = {1: 'S', 2: 'L'}      # el TXT usa 'S'=lado fuente, 'L'=lado carga

# CYMSECTION.Phase es un CÓDIGO NUMÉRICO, no texto: la base guarda 7 donde el TXT
# escribe 'ABC'. No es una máscara de bits (3 es 'C', no 'A+B'), sino una enumeración
# de las siete combinaciones posibles. Comprobado tramo a tramo contra un export real:
# 0 discrepancias en 38.657 tramos.
# La decodificación vive en model.py: el TXT y esta base traen el mismo código y deben
# traducirlo igual. Se reexporta el nombre para no romper a quien ya lo importaba de aquí.
from .model import PHASE_CODES, decode_phase as _phase  # noqa: F401


class AccessReadError(RuntimeError):
    """No se pudo leer la base Access (driver ausente, fichero bloqueado, esquema ajeno)."""


def _connect(path: Path):
    try:
        import pyodbc
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise AccessReadError(
            'La entrada por base de datos Access necesita pyodbc. '
            'Instale con: pip install "igea-dgs[access]"  '
            '(o use la entrada por ficheros TXT, que no requiere driver).'
        ) from exc
    if not path.is_file():
        raise AccessReadError(f'No se encuentra la base de datos: {path}')
    try:
        # ReadOnly: nunca se escribe en la base de la distribuidora.
        return pyodbc.connect(
            f'DRIVER={{{ACCESS_DRIVER}}};DBQ={path};ReadOnly=1;',
            readonly=True, timeout=60,
        )
    except Exception as exc:
        raise AccessReadError(
            f'No se pudo abrir {path.name}: {exc}. '
            'Compruebe que el driver «Microsoft Access Driver» esté instalado con la '
            'misma arquitectura que Python (64 bits), y que la base no esté abierta en '
            'exclusiva por CYMDIST (fichero .ldb presente).'
        ) from exc


def _fetch(cursor, table: str, columns: str) -> list[tuple]:
    try:
        cursor.execute(f'SELECT {columns} FROM [{table}]')
        return cursor.fetchall()
    except Exception as exc:
        raise AccessReadError(
            f'No se pudo leer la tabla [{table}]: {exc}. '
            'La base no parece un proyecto CYMDIST con el esquema esperado.'
        ) from exc


def _txt(value: Any) -> str:
    """Todo el motor trabaja con cadenas, como el TXT."""
    if value is None:
        return ''
    if isinstance(value, float):
        if not math.isfinite(value):
            return ''
        return repr(value) if value != int(value) else str(int(value))
    return str(value).strip()


def _nominal_kv(operating_voltage_a: Any) -> str:
    """Tensión nominal entre fases a partir de la fase-neutro de ``CYMSOURCE``.

    ``OperatingVoltageA`` es fase-neutro, así que la nominal es ese valor por ``√3``.
    La base la almacena con ~7 cifras significativas (5.773503, 13.221321), de modo
    que el producto solo es significativo hasta ~6: sin redondear saldría
    ``10.000000534`` en lugar de ``10``, y ``22.899999715`` en lugar de ``22.9``.

    Se redondea a 6 cifras significativas. Comprobado en las 96 fuentes de un export
    real: reproduce exactamente el ``DesiredVoltage`` del TXT en todas. Es una
    reconstrucción, no un valor almacenado — si una base trae la nominal en un campo
    propio, conviene preferirlo.
    """
    if operating_voltage_a is None:
        return ''
    try:
        nominal = float(operating_voltage_a) * math.sqrt(3.0)
    except (TypeError, ValueError):
        return ''
    if not math.isfinite(nominal):
        return ''
    return f'{float(f"{nominal:.6g}"):.10g}'


def available() -> bool:
    """True si esta máquina puede leer bases Access."""
    try:
        import pyodbc
    except ImportError:
        return False
    return any(ACCESS_DRIVER.split('(')[0].strip() in d for d in pyodbc.drivers())


def list_networks(network_db: Path | str) -> list[str]:
    """NetworkId presentes en la base, sin cargar el resto."""
    path = Path(network_db)
    cn = _connect(path)
    try:
        cur = cn.cursor()
        return sorted({_txt(r[0]) for r in _fetch(cur, 'CYMHEADNODE', 'NetworkId') if r[0]})
    finally:
        cn.close()


def read_access_dataset(
    network_db: Path | str,
    *,
    equipment_db: Path | str | None = None,
    load_year: int | None = None,
    networks: list[str] | None = None,
    equipment_tables: dict[str, tuple[dict[str, str], ...]] | None = None,
) -> CymdistDataset:
    """Lee una base CYMDIST y devuelve el mismo ``CymdistDataset`` que el lector TXT.

    ``equipment_db`` permite indicar otra base para el catálogo de equipos: no siempre
    vive en la misma (hay bases de red con ``CYMEQOVERHEADLINE`` vacía). Si se omite,
    se usa la propia base de red.

    ``load_year`` elige el escenario de carga; por defecto el año más reciente de cada
    dispositivo, que es lo que hace el export TXT.

    ``networks`` limita la lectura a los ``NetworkId`` indicados, por ejemplo los de un
    estudio (ver :func:`igea_dgs.study.study_networks`).

    ``equipment_tables`` da el catálogo ya construido, con los nombres de campo del
    BD_Equipo, para bases que traen la red y ninguna tabla ``CYMEQ*`` (por ejemplo
    desde el Excel de catálogo: :func:`igea_dgs.catalog.tablas_equipo_desde_catalogo`).
    """
    net_path = Path(network_db)
    eq_path = Path(equipment_db) if equipment_db else net_path
    wanted = set(networks) if networks else None

    cn = _connect(net_path)
    try:
        cur = cn.cursor()

        # Los nodos NO se filtran por red aunque se pida un subconjunto: hay tramos que
        # referencian nodos pertenecientes a otra red (puntos de enlace entre
        # alimentadores). Filtrarlos dejaba 47 de 96 alimentadores con «references
        # missing node». Cargarlos todos es barato y el modelo solo usa los que sus
        # propios tramos referencian.
        nodes: dict[str, dict[str, str]] = {}
        for node_id, x, y, _net in _fetch(cur, 'CYMNODE', 'NodeId, X, Y, NetworkId'):
            nodes[_txt(node_id)] = {
                'NodeID': _txt(node_id), 'CoordX': _txt(x), 'CoordY': _txt(y),
            }

        headnodes: dict[str, str] = {}
        for net, node_id in _fetch(cur, 'CYMHEADNODE', 'NetworkId, NodeId'):
            headnodes[_txt(node_id)] = _txt(net)

        sources: dict[str, dict[str, str]] = {}
        for dev, node_id, net, volt_a in _fetch(
            cur, 'CYMSOURCE', 'DeviceNumber, NodeId, NetworkId, OperatingVoltageA',
        ):
            network_id = _txt(net)
            if wanted is not None and network_id not in wanted:
                continue
            sources[network_id] = {
                'SourceID': _txt(dev), 'DeviceNumber': _txt(dev), 'NodeID': _txt(node_id),
                'NetworkID': network_id,
                'DesiredVoltage': _nominal_kv(volt_a),
            }

        sections: dict[str, dict[str, str]] = {}
        section_owner: dict[str, str] = {}
        feeder_rows: dict[str, list[str]] = defaultdict(list)
        for sid, net, from_node, to_node, phase in _fetch(
            cur, 'CYMSECTION', 'SectionId, NetworkId, FromNodeId, ToNodeId, Phase',
        ):
            network_id = _txt(net)
            if wanted is not None and network_id not in wanted:
                continue
            section_id = _txt(sid)
            sections[section_id] = {
                'SectionID': section_id, 'FromNodeID': _txt(from_node),
                'ToNodeID': _txt(to_node), 'Phase': _phase(phase) or 'ABC',
            }
            section_owner[section_id] = network_id
            feeder_rows[network_id].append(section_id)

        # Un alimentador puede existir sin tramos (solo cabecera).
        for network_id in sources:
            feeder_rows.setdefault(network_id, [])

        # Puente dispositivo↔tramo. El TXT ya viene resuelto; aquí hay que unirlo.
        device_section: dict[tuple[int, str], tuple[str, int]] = {}
        for dev, dev_type, net, sid, location in _fetch(
            cur, 'CYMSECTIONDEVICE', 'DeviceNumber, DeviceType, NetworkId, SectionId, Location',
        ):
            if wanted is not None and _txt(net) not in wanted:
                continue
            device_section[(int(dev_type), _txt(dev))] = (_txt(sid), int(location or 0))

        line_configurations: dict[str, dict[str, str]] = {}
        for table, type_col, dev_type, overhead in (
            ('CYMOVERHEADLINE', 'LineId', DEV_OVERHEAD_LINE, '1'),
            ('CYMUNDERGROUNDLINE', 'CableId', DEV_UNDERGROUND_LINE, '0'),
        ):
            for dev, net, type_id, length in _fetch(
                cur, table, f'DeviceNumber, NetworkId, {type_col}, Length',
            ):
                if wanted is not None and _txt(net) not in wanted:
                    continue
                located = device_section.get((dev_type, _txt(dev)))
                if located is None:
                    continue
                section_id = located[0]
                line_configurations[section_id] = {
                    'SectionID': section_id, 'LineCableID': _txt(type_id),
                    'Length': _txt(length), 'Overhead': overhead,
                }

        load_placements: dict[tuple[str, str], dict[str, str]] = {}
        customer_loads: dict[tuple[str, str], dict[str, str]] = {}
        # Varias filas por dispositivo (un año de carga cada una): quedarse con una.
        best: dict[str, tuple[int, tuple]] = {}
        for row in _fetch(
            cur, 'CYMCUSTOMERLOAD',
            'DeviceNumber, NetworkId, CustomerNumber, LoadYear, LoadValueType, Phase, '
            'LoadValue1, LoadValue2, ConnectedKVA, KWHUsage, Status',
        ):
            dev, net = _txt(row[0]), _txt(row[1])
            if wanted is not None and net not in wanted:
                continue
            year = int(row[3] or 0)
            if load_year is not None and year != load_year:
                continue
            current = best.get(dev)
            if current is None or year > current[0]:
                best[dev] = (year, row)

        for dev, (_year, row) in best.items():
            located = device_section.get((DEV_SPOT_LOAD, dev))
            if located is None:
                continue
            section_id, location = located
            key = (section_id, dev)
            load_placements[key] = {
                'SectionID': section_id, 'DeviceNumber': dev, 'LoadType': 'SPOT',
                'Location': _LOAD_LOCATION.get(location, _txt(location)),
            }
            customer_loads[key] = {
                'SectionID': section_id, 'DeviceNumber': dev,
                'CustomerNumber': _txt(row[2]), 'ValueType': _txt(row[4]),
                # La fase de la carga se conserva tal cual: tanto la base como el TXT
                # la guardan como código numérico, y sus valores no siempre coinciden
                # (el TXT parece tomarla de otra fila de año). Hoy el motor no la usa;
                # cuando se implemente el modelo por fase habrá que unificarla.
                'Phase': _txt(row[5]), 'Value1': _txt(row[6]), 'Value2': _txt(row[7]),
                'ConnectedKVA': _txt(row[8]), 'KWH': _txt(row[9]), 'Status': _txt(row[10]),
            }

        switch_settings: list[dict[str, str]] = []
        sectionalizer_settings: list[dict[str, str]] = []
        for table, dev_type, sink in (
            ('CYMSWITCH', DEV_SWITCH, switch_settings),
            ('CYMSECTIONALIZER', DEV_SECTIONALIZER, sectionalizer_settings),
        ):
            for dev, net, eq_id, closed_phase, normal_status, locked in _fetch(
                cur, table,
                'DeviceNumber, NetworkId, EquipmentId, ClosedPhase, NormalStatus, Locked',
            ):
                if wanted is not None and _txt(net) not in wanted:
                    continue
                located = device_section.get((dev_type, _txt(dev)))
                if located is None:
                    continue
                section_id, location = located
                sink.append({
                    'SectionID': section_id, 'EqID': _txt(eq_id), 'EqNumber': _txt(dev),
                    # ClosedPhase describe qué fases quedan cerradas, no las del equipo:
                    # vale 7 en las 15.196 maniobras del export. La fase del equipo es la
                    # de su tramo (verificado: 0 discrepancias contra el TXT).
                    'EqPhase': sections.get(section_id, {}).get('Phase', ''),
                    'Location': _SWITCH_LOCATION.get(location, _txt(location)),
                    'Status': _txt(normal_status), 'Locked': _txt(locked), 'EqState': '0',
                })

        intermediate_nodes: list[dict[str, str]] = []
        for sid, index, net, x, y in _fetch(
            cur, 'CYMINTERMEDIATEPOINT', 'SectionId, PointIndex, NetworkId, X, Y',
        ):
            if wanted is not None and _txt(net) not in wanted:
                continue
            intermediate_nodes.append({
                'SectionID': _txt(sid), 'SeqNumber': _txt(index),
                'CoordX': _txt(x), 'CoordY': _txt(y),
            })
    finally:
        cn.close()

    if equipment_tables is None:
        equipment_tables = _read_equipment(eq_path)

    if not nodes or not sources:
        raise AccessReadError(
            f'{net_path.name}: la base no contiene nodos o fuentes. '
            'Compruebe que es una base de red CYMDIST y no otra cosa.'
        )
    if not any(equipment_tables.get(name) for name in ('LINE', 'CONCENTRIC NEUTRAL CABLE')):
        # Regla del proyecto: una base con la red y sin tablas CYMEQ* toma los
        # parámetros del catálogo Excel del proyecto (igea_dgs.reglas), conservando la
        # identidad —código, material, sección, aéreo o subterráneo— de la base.
        from .reglas import catalogo_del_proyecto

        catalogo = catalogo_del_proyecto()
        if catalogo is not None:
            from .catalog import tablas_equipo_desde_catalogo

            usados = {(lc['LineCableID'], lc['Overhead'] == '1')
                      for lc in line_configurations.values() if lc.get('LineCableID')}
            equipment_tables = dict(
                tablas_equipo_desde_catalogo(catalogo, codigos_en_red=usados).tablas)
            eq_path = catalogo
    if not any(equipment_tables.get(name) for name in ('LINE', 'CONCENTRIC NEUTRAL CABLE')):
        raise AccessReadError(
            f'{eq_path.name}: no contiene catálogo de equipos '
            '(CYMEQOVERHEADLINE / CYMEQCABLE están vacías). Sin parámetros eléctricos no '
            'se puede convertir ningún alimentador. Indique la base que sí lo tenga con '
            '--equipment-db.'
        )

    return CymdistDataset(
        red_path=net_path,
        loads_path=net_path,
        equipment_path=eq_path,
        headnodes=headnodes,
        nodes=nodes,
        sources=sources,
        line_configurations=line_configurations,
        sections=sections,
        section_owner=section_owner,
        feeders={key: tuple(value) for key, value in feeder_rows.items()},
        switch_settings=tuple(switch_settings),
        sectionalizer_settings=tuple(sectionalizer_settings),
        intermediate_nodes=tuple(intermediate_nodes),
        load_placements=load_placements,
        customer_loads=customer_loads,
        equipment_tables=equipment_tables,
    )


def _read_equipment(path: Path) -> dict[str, tuple[dict[str, str], ...]]:
    """Catálogo de conductores y cables, con los nombres de campo del BD_Equipo TXT."""
    cn = _connect(path)
    try:
        cur = cn.cursor()
        tables: dict[str, tuple[dict[str, str], ...]] = {}
        for table, target in (
            ('CYMEQOVERHEADLINE', 'LINE'),
            ('CYMEQCABLE', 'CONCENTRIC NEUTRAL CABLE'),
        ):
            try:
                rows = _fetch(
                    cur, table,
                    'EquipmentId, PositiveSequenceResistance, ZeroSequenceResistance, '
                    'PositiveSequenceReactance, ZeroSequenceReactance, PosSeqShuntSusceptance, '
                    'ZeroSequenceShuntSusceptance, NominalRating',
                )
            except AccessReadError:
                rows = []
            tables[target] = tuple(
                {
                    'ID': _txt(r[0]), 'R1': _txt(r[1]), 'R0': _txt(r[2]),
                    'X1': _txt(r[3]), 'X0': _txt(r[4]), 'B1': _txt(r[5]),
                    'B0': _txt(r[6]), 'Amps': _txt(r[7]),
                }
                for r in rows
            )
        return tables
    finally:
        cn.close()
