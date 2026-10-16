"""La georreferenciación es opcional, pero cuando hay coordenadas deben cuadrar.

Dos requisitos que se sostienen a la vez (C-03 del diagnóstico 2026-09-22):

1. Con ``--no-geography`` un export sin CoordX/CoordY debe convertir. Antes bastaba
   **un** nodo sin coordenadas para tumbar el alimentador, aunque la geografía
   estuviera desactivada, lo que excluía a cualquier cliente sin GIS.
2. Cuando las coordenadas sí existen para todos los elementos, el resultado debe ser
   idéntico con y sin geografía, y su escala debe concordar con las longitudes del
   TXT — si no concuerda, es un error de unidades o de proyección y debe bloquear.

Todo aquí es sintético: no necesita los TXT de la distribuidora.
"""

from __future__ import annotations

import math

import pytest

from igea_dgs.dataset import CymdistDataset
from igea_dgs.model import (
    ModelBuildError,
    build_feeder_model,
    check_length_scale_agreement,
    prove_mt_connections,
)

NETWORK = 'NET_2030_150_NA999'
FEEDER = 'NA999'


def _write_feeder(tmp_path, *, coords: dict[str, tuple[str, str]], length_txt: float = 52.0):
    """N1→N2→N3 con una SED colgando; ``coords`` permite dejar nodos sin georreferencia."""
    red = tmp_path / 'RED.txt'
    loads = tmp_path / 'CARGA.txt'
    equip = tmp_path / 'BD_Equipo.txt'
    node_rows = [f'{nid},{x},{y}' for nid, (x, y) in coords.items()]
    red.write_text(
        '\n'.join([
            '[NODE]',
            'FORMAT_NODE=NodeID,CoordX,CoordY',
            *node_rows,
            '[SOURCE]',
            'FORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage',
            f'{NETWORK},N1,13.2',
            '[SECTION]',
            'FEEDER=' + NETWORK,
            'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
            'SEC_A,N1,N2,ABC',
            'SEC_B,N2,N3,ABC',
            '[LINE CONFIGURATION]',
            'FORMAT_LINE CONFIGURATION=SectionID,LineCableID,Length,Overhead',
            f'SEC_A,DEFAULT,{length_txt},1',
            f'SEC_B,DEFAULT,{length_txt},1',
            '',
        ]),
        encoding='utf-8',
    )
    loads.write_text(
        '\n'.join([
            '[LOADS]',
            'FORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location',
            'SEC_B,DEV_SE41259,SPOT,0,1',
            '[CUSTOMER LOADS]',
            'FORMAT_CUSTOMERLOADS=SectionID,DeviceNumber,CustomerNumber,CustomerType,Year,'
            'Status,CustomerName,CustomerAddress,MeterNumber,BillingNumber,LockStatus,Phase,'
            'ValueType,Value1,Value2,ConnectedKVA,KWH',
            'SEC_B,DEV_SE41259,CUST_SE41259,1,2024,1,,,,,,,ABC,2,10,0.95,50,100',
            '',
        ]),
        encoding='utf-8',
    )
    equip.write_text(
        '\n'.join([
            '[LINE]',
            'FORMAT_LINE=ID,R1,R0,X1,X0,B1,B0,Amps',
            'DEFAULT,0.1,0.2,0.3,0.4,0,0,200',
            '',
        ]),
        encoding='utf-8',
    )
    return CymdistDataset.from_files(red, loads, equip)


# 3-4-5: cada tramo mide 50 m de geometría.
FULL_COORDS = {'N1': ('0', '0'), 'N2': ('30', '40'), 'N3': ('60', '80')}
PARTIAL_COORDS = {'N1': ('0', '0'), 'N2': ('', ''), 'N3': ('60', '80')}


def test_no_geography_converts_without_coordinates(tmp_path):
    ds = _write_feeder(tmp_path, coords=PARTIAL_COORDS)
    model = build_feeder_model(ds, FEEDER, strict=True, include_geography=False)
    # Los tramos sin coordenadas conservan la longitud del TXT.
    assert {line.length_source for line in model.lines} == {'txt'}
    assert all(line.length_m == 52.0 for line in model.lines)


def test_geography_still_requires_complete_coordinates(tmp_path):
    """Desactivar el rigor solo con --no-geography; con geografía ON no se relaja."""
    ds = _write_feeder(tmp_path, coords=PARTIAL_COORDS)
    with pytest.raises(ModelBuildError, match='CoordX/CoordY'):
        build_feeder_model(ds, FEEDER, strict=True, include_geography=True)


def test_complete_coordinates_give_the_same_model_either_way(tmp_path):
    """Si las coordenadas existen para todos los elementos, el flag no cambia nada."""
    ds = _write_feeder(tmp_path, coords=FULL_COORDS)
    with_geo = build_feeder_model(ds, FEEDER, strict=True, include_geography=True)
    without_geo = build_feeder_model(ds, FEEDER, strict=True, include_geography=False)

    assert [line.length_m for line in with_geo.lines] == [line.length_m for line in without_geo.lines]
    assert [line.length_source for line in with_geo.lines] == [line.length_source for line in without_geo.lines]
    assert {line.length_source for line in with_geo.lines} == {'georef'}
    for line in with_geo.lines:
        assert math.isclose(line.length_m, 50.0, abs_tol=1e-9)


def test_proof_counts_missing_coordinates_instead_of_failing(tmp_path):
    ds = _write_feeder(tmp_path, coords=PARTIAL_COORDS)
    model = build_feeder_model(ds, FEEDER, strict=True, include_geography=False)

    proof = prove_mt_connections(model, ds, require_coordinates=False)
    assert proof['ok'] is True
    assert proof['lines_without_coords'] == 2      # ambos tramos tocan N2
    assert proof['coordinates_required'] is False

    strict_proof = prove_mt_connections(model, ds, require_coordinates=True)
    assert strict_proof['ok'] is False
    assert strict_proof['errors_total'] > 0


def test_topology_is_proven_even_without_coordinates(tmp_path):
    """Quitar la exigencia de GPS no debe relajar la prueba topológica."""
    ds = _write_feeder(tmp_path, coords=PARTIAL_COORDS)
    model = build_feeder_model(ds, FEEDER, strict=True, include_geography=False)
    model.lines[0] = type(model.lines[0])(
        **{**model.lines[0].__dict__, 'to_node': 'N3'}  # ya no coincide con el TXT
    )
    model.section_by_id = {line.section_id: line for line in model.lines}

    proof = prove_mt_connections(model, ds, require_coordinates=False)
    assert proof['ok'] is False
    assert any('no coinciden con TXT' in e for e in proof['errors'])


class TestScaleAgreement:
    """El oráculo independiente: las coordenadas deben concordar con el TXT."""

    def test_matching_scale_reports_ratio_one(self, tmp_path):
        ds = _write_feeder(tmp_path, coords=FULL_COORDS, length_txt=50.0)
        model = build_feeder_model(ds, FEEDER, strict=True)
        scale = check_length_scale_agreement(model)
        assert scale['ok'] is True
        assert scale['compared'] == 2
        assert math.isclose(scale['median_ratio'], 1.0, rel_tol=1e-9)
        assert scale['outside_warn_band'] == 0
        assert scale['error'] is None and scale['warning'] is None

    def test_small_physical_difference_is_only_a_warning(self, tmp_path):
        # 50 m de geometría frente a 52 m de TXT: holgura plausible, no error.
        ds = _write_feeder(tmp_path, coords=FULL_COORDS, length_txt=52.0)
        model = build_feeder_model(ds, FEEDER, strict=True)
        scale = check_length_scale_agreement(model)
        assert scale['ok'] is True
        assert scale['error'] is None

    def test_coordinates_in_centimetres_are_rejected(self, tmp_path):
        """Pasan la comprobación de CRS (declara metros) y fallan aquí."""
        cm = {nid: (str(float(x) * 100), str(float(y) * 100)) for nid, (x, y) in FULL_COORDS.items()}
        ds = _write_feeder(tmp_path, coords=cm, length_txt=50.0)
        with pytest.raises(ModelBuildError, match='Escala de coordenadas incoherente'):
            build_feeder_model(ds, FEEDER, strict=True)

    def test_scale_check_runs_with_geography_disabled(self, tmp_path):
        """El oráculo no depende de pyproj ni del flag de geografía."""
        cm = {nid: (str(float(x) * 100), str(float(y) * 100)) for nid, (x, y) in FULL_COORDS.items()}
        ds = _write_feeder(tmp_path, coords=cm, length_txt=50.0)
        with pytest.raises(ModelBuildError, match='Escala de coordenadas incoherente'):
            build_feeder_model(ds, FEEDER, strict=True, include_geography=False)

    def test_no_comparable_sections_is_not_an_error(self, tmp_path):
        ds = _write_feeder(tmp_path, coords=PARTIAL_COORDS)
        model = build_feeder_model(ds, FEEDER, strict=True, include_geography=False)
        scale = check_length_scale_agreement(model)
        assert scale['compared'] == 0
        assert scale['ok'] is True
        assert scale['median_ratio'] is None
