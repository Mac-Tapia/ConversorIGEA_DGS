"""Generador de exports IGEA/CYMDIST sintéticos, parametrizable.

Existe por dos motivos:

1. **Flexibilidad.** El conversor no debe estar afinado a un export concreto. Con este
   generador se prueban lotes con más o menos alimentadores, otras convenciones de
   nombre, otros CRS, y tablas opcionales ausentes — sin depender del TXT de ninguna
   distribuidora.
2. **Contribuibilidad.** La suite podía ejecutarse en serio solo con los TXT reales,
   que no son publicables. Esto permite ejecutarla en cualquier máquina.

Las columnas imitan las del export real, incluidas las que el motor ignora, para que
las pruebas ejerciten también el descarte de columnas sobrantes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

# Mismas columnas que un export CYMDIST real (el motor solo usa algunas).
FMT_HEADNODES = 'NodeID,NetworkID'
FMT_NODE = (
    'NodeID,CoordX,CoordY,TagText,TagProperties,TagDeltaX,TagDeltaY,TagAngle,'
    'TagAlignment,TagBorder,TagBackground,TagTextColor,TagBorderColor,TagBackgroundColor'
)
FMT_SOURCE = 'SourceID,DeviceNumber,NodeID,NetworkID,DesiredVoltage'
FMT_LINECONF = 'SectionID,LineCableID,Length,Overhead'
FMT_FEEDER = 'NetworkID,HeadNodeID,CoordSet,Year,Description,Color,LoadFactor'
FMT_SECTION = (
    'SectionID,FromNodeID,ToNodeID,Phase,Mask,ZoneID,SubNetworkId,TagProperties,'
    'TagDisplay,TagLeft,TagBottom,TagRight,TagTop,TagText'
)
FMT_SWITCH = 'SectionID,EqID,EqNumber,EqPhase,Location,Status,Locked,EqState'
FMT_INTERMEDIATE = 'SectionID,SeqNumber,CoordX,CoordY'
FMT_LOADS = 'SectionID,DeviceNumber,LoadType,Connection,Location'
FMT_CUSTOMERLOADS = (
    'SectionID,DeviceNumber,LoadType,CustomerNumber,CustomerType,Status,'
    'LockDuringLoadAllocation,Year,LoadModelID,NormalPriority,EmergencyPriority,'
    'ValueType,Phase,Value1,Value2,ConnectedKVA,KWH,NumberOfCustomer,CenterTapPercent'
)
# --- La otra disposicion que exporta CYMDIST -------------------------------------
# El mismo contenido, dicho de otra forma. Se vio en la entrega de la distribuidora: un
# export de 21 MB que declara la tension de fuente entre fase y neutro, parte el
# conductor de cada tramo en dos tablas de ajuste, pone FORMAT_SECTION *antes* del
# primer FEEDER= y llama [CABLE] al catalogo de cables. Con una sola de las dos
# disposiciones probada, el conversor solo servia para un fichero concreto.
FMT_SOURCE_COMPLETO = (
    'SourceID,DeviceNumber,NodeID,NetworkID,OperatingVoltageA,OperatingVoltageB,'
    'OperatingVoltageC,UseSecondLevelImpedance,SinglePhaseCenterTap,CenterTapPhase'
)
FMT_SECTION_COMPLETO = (
    'SectionID,FromNodeID,FromNodeIndex,ToNodeID,ToNodeIndex,Phase,ZoneID,SubNetworkId'
)
FMT_OVERHEAD_SETTING = (
    'SectionID,DeviceNumber,DeviceStage,Flags,InitFromEquipFlags,LineCableID,Length,'
    'ConnectionStatus,NominalRating,AmpacityDeratingFactor,CoordX,CoordY,HarmonicModel'
)
FMT_UNDERGROUND_SETTING = (
    'SectionID,DeviceNumber,DeviceStage,Flags,InitFromEquipFlags,LineCableID,Length,'
    'AmpacityDeratingFactor,CoordX,CoordY,ConnectionStatus,HarmonicModel'
)

FMT_BD_LINE = 'ID,PhaseCondID,NeutralCondID,SpacingID,R1,R0,X1,X0,B1,B0,Amps,Amps_2,LockImpedance'
FMT_BD_CABLE = 'ID,R1,R0,X1,X0,B1,B0,Amps'


def _pad(values: list[str], columns: str) -> str:
    """Rellena hasta el número de columnas del FORMAT_, como hace un export real."""
    total = len(columns.split(','))
    return ','.join(values + [''] * (total - len(values)))


@dataclass(frozen=True)
class ExportSpec:
    """Forma del export a generar.

    ``naming`` elige la convención del NetworkID, para probar que el nombre corto se
    resuelve igual con cualquiera:

    - ``'net'``    → ``NET_2030_150_AL01``  (el estilo del export de referencia)
    - ``'dash'``   → ``ALIMENTADOR-01``
    - ``'dotted'`` → ``Feeder.A01``
    - ``'plain'``  → ``AL01``
    """

    feeders: int = 3
    sections_per_feeder: int = 4
    loads_per_feeder: int = 2
    switches_per_feeder: int = 1
    intermediate_per_section: int = 1
    naming: str = 'net'
    # Origen en un UTM cualquiera; el espaciado son metros reales.
    origin_x: float = 500000.0
    origin_y: float = 8500000.0
    spacing_m: float = 40.0
    feeder_gap_m: float = 5000.0
    nominal_kv: float = 13.2
    header_only_feeders: int = 0   # alimentadores con SOURCE pero sin SECTION
    with_switch_table: bool = True
    with_intermediate_table: bool = True
    with_cable_catalog: bool = True
    #: Cual de las dos disposiciones de export se genera. ``'reducido'`` es la del
    #: export de referencia; ``'completo'`` la del export largo de CYMDIST. El
    #: conversor debe dar el mismo modelo con las dos.
    layout: str = 'reducido'

    def network_id(self, index: int) -> str:
        code = f'AL{index:02d}'
        if self.naming == 'dash':
            return f'ALIMENTADOR-{index:02d}'
        if self.naming == 'dotted':
            return f'Feeder.A{index:02d}'
        if self.naming == 'plain':
            return code
        return f'NET_2030_{150 + index}_{code}'

    def short_name(self, index: int) -> str:
        """Nombre corto que el motor debe deducir del NetworkID."""
        return self.network_id(index).replace('.', '_').split('_')[-1].split('-')[-1]

    @property
    def total_feeders(self) -> int:
        return self.feeders + self.header_only_feeders

    @property
    def total_sections(self) -> int:
        return self.feeders * self.sections_per_feeder


def write_export(spec: ExportSpec, out_dir: Path) -> tuple[Path, Path, Path]:
    """Escribe RED/CARGA/BD_Equipo y devuelve sus rutas."""
    out_dir.mkdir(parents=True, exist_ok=True)
    red = out_dir / 'RED.txt'
    carga = out_dir / 'CARGA.txt'
    equipo = out_dir / 'BD_Equipo.txt'

    headnodes: list[str] = []
    nodes: list[str] = []
    sources: list[str] = []
    feeder_rows: list[str] = []
    section_blocks: list[str] = []
    lineconf: list[str] = []
    overhead_setting: list[str] = []
    underground_setting: list[str] = []
    completo = spec.layout == 'completo'
    switches: list[str] = []
    intermediate: list[str] = []
    loads: list[str] = []
    customer_loads: list[str] = []

    for f in range(1, spec.total_feeders + 1):
        net = spec.network_id(f)
        header_only = f > spec.feeders
        base_x = spec.origin_x + (f - 1) * spec.feeder_gap_m
        head = f'N{f}_0'
        headnodes.append(_pad([head, net], FMT_HEADNODES))
        nodes.append(_pad([head, f'{base_x:.3f}', f'{spec.origin_y:.3f}'], FMT_NODE))
        if completo:
            # Entre fase y neutro, como lo da el export largo.
            fn = f'{spec.nominal_kv / math.sqrt(3.0):.6f}'
            sources.append(_pad(
                [f'SRC_{net}', f'DEV_{net}', head, net, fn, fn, fn], FMT_SOURCE_COMPLETO))
        else:
            sources.append(_pad(
                [f'SRC_{net}', f'DEV_{net}', head, net, f'{spec.nominal_kv}'], FMT_SOURCE))
        feeder_rows.append(_pad([net, head], FMT_FEEDER))

        # En la disposicion completa el FORMAT_SECTION va una sola vez, antes del
        # primer FEEDER=, y no se repite: es justo lo que hacia perder los tramos.
        block = [f'FEEDER={_pad([net, head], FMT_FEEDER)}']
        if not completo:
            block.append(f'FORMAT_SECTION={FMT_SECTION}')
        if header_only:
            section_blocks.append('\n'.join(block))
            continue

        for s in range(spec.sections_per_feeder):
            a, b = f'N{f}_{s}', f'N{f}_{s + 1}'
            x = base_x + (s + 1) * spec.spacing_m
            nodes.append(_pad([b, f'{x:.3f}', f'{spec.origin_y:.3f}'], FMT_NODE))
            sid = f'SEC_{f}_{s}'
            # Fase variada: el modelo debe conservar lo que diga el TXT.
            phase = ('ABC', 'AB', 'A')[s % 3]
            aerea = s % 2 == 0
            if completo:
                block.append(_pad([sid, a, '0', b, '0', phase], FMT_SECTION_COMPLETO))
                fila = _pad(
                    [sid, sid, '', '0', '0', 'DEFAULT', f'{spec.spacing_m}'],
                    FMT_OVERHEAD_SETTING if aerea else FMT_UNDERGROUND_SETTING)
                (overhead_setting if aerea else underground_setting).append(fila)
            else:
                block.append(_pad([sid, a, b, phase], FMT_SECTION))
                lineconf.append(_pad(
                    [sid, 'DEFAULT', f'{spec.spacing_m}', '1' if aerea else '0'],
                    FMT_LINECONF))
            for k in range(spec.intermediate_per_section):
                # Punto intermedio sobre el segmento, para no alterar su longitud.
                frac = (k + 1) / (spec.intermediate_per_section + 1)
                px = base_x + s * spec.spacing_m + frac * spec.spacing_m
                intermediate.append(_pad([sid, str(k + 1), f'{px:.3f}', f'{spec.origin_y:.3f}'], FMT_INTERMEDIATE))
        stub_sections: list[str] = []

        for i in range(min(spec.loads_per_feeder, spec.sections_per_feeder)):
            sid = f'SEC_{f}_{i}'
            dev = f'DEV_{f}_{i}_SE{f}{i:03d}'
            if completo:
                # El export largo no cuelga la carga del tramo de red: le hace una
                # derivacion propia de 0,300 m que acaba en un nudo _VIRTUAL, y la
                # declara en el punto medio de esa derivacion. Reproducirlo importa:
                # es lo que hace inocuo tratar Location='2' como el nudo final.
                sid = f'SEC_{f}_{i}_SE{f}{i:03d}'
                raiz = f'N{f}_{i + 1}'
                virtual = f'{raiz}_SE{f}{i:03d}_VIRTUAL'
                vx = spec.origin_x + (f - 1) * spec.feeder_gap_m + (i + 1) * spec.spacing_m
                nodes.append(_pad(
                    [virtual, f'{vx:.3f}', f'{spec.origin_y:.3f}'], FMT_NODE))
                stub_sections.append(
                    _pad([sid, raiz, '0', virtual, '0', 'ABC'], FMT_SECTION_COMPLETO))
                underground_setting.append(_pad(
                    [sid, sid, '', '0', '0', 'DEFAULT', '0.300000'],
                    FMT_UNDERGROUND_SETTING))
            # El export completo declara las cargas en el punto medio del tramo.
            loads.append(_pad(
                [sid, dev, 'SPOT', '0', '2' if completo else '1'], FMT_LOADS))
            row = [''] * len(FMT_CUSTOMERLOADS.split(','))
            cols = FMT_CUSTOMERLOADS.split(',')
            for key, val in (
                ('SectionID', sid), ('DeviceNumber', dev), ('LoadType', 'SPOT'),
                ('CustomerNumber', f'CUST_{f}_{i}_SE{f}{i:03d}'), ('CustomerType', '1'),
                ('Status', '1'), ('Year', '2026'), ('ValueType', '2'), ('Phase', 'ABC'),
                ('Value1', '12.5'), ('Value2', '0.95'), ('ConnectedKVA', '50'),
                ('KWH', '1200'), ('NumberOfCustomer', '1'),
            ):
                row[cols.index(key)] = val
            customer_loads.append(','.join(row))

        for i in range(min(spec.switches_per_feeder, spec.sections_per_feeder)):
            sid = f'SEC_{f}_{i}'
            switches.append(_pad([sid, f'EQ_{f}_{i}', f'SW_{f}_{i}', 'ABC', 'S', '1', '0', '0'], FMT_SWITCH))

        block.extend(stub_sections)
        section_blocks.append('\n'.join(block))

    red_parts = [
        '[GENERAL]', 'FORMAT_GENERAL=Comment', 'Export sintetico de prueba',
        '[HEADNODES]', f'FORMAT_HEADNODES={FMT_HEADNODES}', *headnodes,
        '[NODE]', f'FORMAT_NODE={FMT_NODE}', *nodes,
    ]
    if completo:
        red_parts += [
            '[SOURCE]', f'FORMAT_SOURCE={FMT_SOURCE_COMPLETO}', *sources,
            '[OVERHEADLINE SETTING]',
            f'FORMAT_OVERHEADLINESETTING={FMT_OVERHEAD_SETTING}', *overhead_setting,
            '[UNDERGROUNDLINE SETTING]',
            f'FORMAT_UNDERGROUNDLINESETTING={FMT_UNDERGROUND_SETTING}',
            *underground_setting,
            # El FORMAT de tramo, una sola vez y antes del primer FEEDER=.
            '[SECTION]', f'FORMAT_SECTION={FMT_SECTION_COMPLETO}',
            f'FORMAT_FEEDER={FMT_FEEDER}', *section_blocks,
        ]
    else:
        red_parts += [
            '[SOURCE]', f'FORMAT_SOURCE={FMT_SOURCE}', *sources,
            '[LINE CONFIGURATION]',
            f'FORMAT_LINECONFIGURATION={FMT_LINECONF}', *lineconf,
            '[SECTION]', *section_blocks,
        ]
    if spec.with_switch_table:
        red_parts += ['[SWITCH SETTING]', f'FORMAT_SWITCHSETTING={FMT_SWITCH}', *switches]
    if spec.with_intermediate_table:
        red_parts += ['[INTERMEDIATE NODES]', f'FORMAT_INTERMEDIATENODE={FMT_INTERMEDIATE}', *intermediate]
    red.write_text('\n'.join(red_parts) + '\n', encoding='utf-8')

    carga.write_text(
        '\n'.join([
            '[LOADS]', f'FORMAT_LOADS={FMT_LOADS}', *loads,
            '[CUSTOMER LOADS]', f'FORMAT_CUSTOMERLOADS={FMT_CUSTOMERLOADS}', *customer_loads,
        ]) + '\n',
        encoding='utf-8',
    )

    equip_parts = [
        '[LINE]', f'FORMAT_LINE={FMT_BD_LINE}',
        _pad(['DEFAULT', 'COND', 'COND', 'SP', '0.31', '0.48', '0.39', '1.42', '2.9', '1.1', '250', '300', '0'], FMT_BD_LINE),
        _pad(['AA05001D', 'COND', 'COND', 'SP', '0.62', '0.79', '0.41', '1.51', '2.7', '1.0', '170', '200', '0'], FMT_BD_LINE),
    ]
    if spec.with_cable_catalog:
        tabla = 'CABLE' if completo else 'CONCENTRIC NEUTRAL CABLE'
        etiqueta = tabla.replace(' ', '')
        equip_parts += [
            f'[{tabla}]', f'FORMAT_{etiqueta}={FMT_BD_CABLE}',
            _pad(['DEFAULT', '0.25', '0.40', '0.11', '0.33', '52', '20', '310'], FMT_BD_CABLE),
        ]
    equipo.write_text('\n'.join(equip_parts) + '\n', encoding='utf-8')
    return red, carga, equipo


def load_export(spec: ExportSpec, out_dir: Path):
    """Genera el export y lo devuelve ya leído como ``CymdistDataset``."""
    from igea_dgs.dataset import CymdistDataset

    red, carga, equipo = write_export(spec, out_dir)
    return CymdistDataset.from_files(red, carga, equipo)
