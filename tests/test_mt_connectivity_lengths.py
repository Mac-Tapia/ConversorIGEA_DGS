"""MT From/To georef connectivity, geo lengths, and SED→node TXT proof."""

from __future__ import annotations

import math

import pytest

from igea_dgs.dataset import CymdistDataset
from igea_dgs.geography import build_geography
from igea_dgs.model import ModelBuildError, build_feeder_model, prove_mt_connections
from igea_dgs.dgs import write_dgs
from igea_dgs.validate import validate_dgs


def _write_mini_feeder(tmp_path, *, length_txt: float = 52.0, location: str = '1'):
    """Two-node feeder: N1(0,0) → N2(30,40) so georef length is 50 m.

    ``length_txt`` defaults to a plausible 52 m (4 % slack over the straight line):
    the georeferenced polyline still overrides it, but the two agree in scale, as a
    real export does. ``check_length_scale_agreement`` rejects order-of-magnitude
    disagreements, so an implausible value here would (correctly) block the build —
    see ``test_scale_oracle_blocks_txt_length_disagreeing_by_orders_of_magnitude``.
    """
    red = tmp_path / 'RED.txt'
    loads = tmp_path / 'CARGA.txt'
    equip = tmp_path / 'BD_Equipo.txt'
    red.write_text(
        '\n'.join([
            '[NODE]',
            'FORMAT_NODE=NodeID,CoordX,CoordY',
            'N1,0,0',
            'N2,30,40',
            '[SOURCE]',
            'FORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage',
            'NET_2030_150_NA999,N1,13.2',
            '[SECTION]',
            'FEEDER=NET_2030_150_NA999',
            'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
            'SEC_MAIN,N1,N2,ABC',
            'SEC_SED,N2,N2,ABC',
            '[LINE CONFIGURATION]',
            'FORMAT_LINE CONFIGURATION=SectionID,LineCableID,Length,Overhead',
            f'SEC_MAIN,DEFAULT,{length_txt},1',
            'SEC_SED,DEFAULT,0.3,0',
            '[INTERMEDIATE NODES]',
            'FORMAT_INTERMEDIATENODE=SectionID,SeqNumber,CoordX,CoordY',
            '',
        ]),
        encoding='utf-8',
    )
    # SEC_SED From=To=N2 keeps a stub; for SED Location=1 still resolves to N2.
    loads.write_text(
        '\n'.join([
            '[LOADS]',
            'FORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location',
            f'SEC_SED,DEV_SE41259,SPOT,0,{location}',
            '[CUSTOMER LOADS]',
            'FORMAT_CUSTOMERLOADS=SectionID,DeviceNumber,CustomerNumber,CustomerType,Year,Status,CustomerName,CustomerAddress,MeterNumber,BillingNumber,LockStatus,Phase,ValueType,Value1,Value2,ConnectedKVA,KWH',
            'SEC_SED,DEV_SE41259,CUST_SE41259,1,2024,1,,,,,,,ABC,2,10,0.95,50,100',
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


def test_georef_length_replaces_txt_length(tmp_path):
    ds = _write_mini_feeder(tmp_path, length_txt=52.0)
    model = build_feeder_model(ds, 'NA999')
    main = model.section_by_id['SEC_MAIN']
    assert main.length_source == 'georef'
    assert main.txt_length_m == 52.0        # el valor del TXT se conserva…
    assert math.isclose(main.length_m, 50.0, abs_tol=1e-9)   # …pero manda la geometría
    assert math.isclose(main.length_km, 0.05, abs_tol=1e-12)


def test_scale_oracle_blocks_txt_length_disagreeing_by_orders_of_magnitude(tmp_path):
    """TXT 999 m sobre una geometría de 50 m: 20× solo puede ser un error de unidades."""
    ds = _write_mini_feeder(tmp_path, length_txt=999.0)
    with pytest.raises(ModelBuildError, match='Escala de coordenadas incoherente'):
        build_feeder_model(ds, 'NA999', strict=True)

    # En modo no estricto se degrada a aviso y la conversión continúa.
    model = build_feeder_model(ds, 'NA999', strict=False)
    assert any('Escala de coordenadas incoherente' in w for w in model.warnings)


def test_prove_mt_connections_from_to_and_sed(tmp_path):
    ds = _write_mini_feeder(tmp_path, location='1')
    model = build_feeder_model(ds, 'NA999')
    proof = prove_mt_connections(model, ds)
    assert proof['ok'] is True
    assert proof['lines_checked'] == proof['lines_total'] == 2
    assert proof['seds_checked'] == proof['seds_total'] == 1
    sed = model.seds[0]
    assert sed.node_id == 'N2'
    assert sed.code == 'SE41259'


def test_sed_location_0_connects_to_from_node(tmp_path):
    ds = _write_mini_feeder(tmp_path, location='0')
    # SEC_SED From=To=N2, so Location 0 also yields N2 — rebuild with a real From≠To stub.
    red = tmp_path / 'RED.txt'
    red.write_text(
        '\n'.join([
            '[NODE]',
            'FORMAT_NODE=NodeID,CoordX,CoordY',
            'N1,0,0',
            'N2,30,40',
            'N3,30,40.3',
            '[SOURCE]',
            'FORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage',
            'NET_2030_150_NA999,N1,13.2',
            '[SECTION]',
            'FEEDER=NET_2030_150_NA999',
            'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
            'SEC_MAIN,N1,N2,ABC',
            'SEC_SED,N2,N3,ABC',
            '[LINE CONFIGURATION]',
            'FORMAT_LINE CONFIGURATION=SectionID,LineCableID,Length,Overhead',
            'SEC_MAIN,DEFAULT,52,1',
            'SEC_SED,DEFAULT,0.3,0',
            '',
        ]),
        encoding='utf-8',
    )
    loads = tmp_path / 'CARGA.txt'
    loads.write_text(
        '\n'.join([
            '[LOADS]',
            'FORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location',
            'SEC_SED,DEV_SE41259,SPOT,0,0',
            '[CUSTOMER LOADS]',
            'FORMAT_CUSTOMERLOADS=SectionID,DeviceNumber,CustomerNumber,CustomerType,Year,Status,CustomerName,CustomerAddress,MeterNumber,BillingNumber,LockStatus,Phase,ValueType,Value1,Value2,ConnectedKVA,KWH',
            'SEC_SED,DEV_SE41259,CUST_SE41259,1,2024,1,,,,,,,ABC,2,10,0.95,50,100',
            '',
        ]),
        encoding='utf-8',
    )
    ds = CymdistDataset.from_files(red, loads, tmp_path / 'BD_Equipo.txt')
    model = build_feeder_model(ds, 'NA999')
    assert model.seds[0].node_id == 'N2'
    assert prove_mt_connections(model, ds)['ok'] is True


def test_missing_node_coords_fail_strict_proof(tmp_path):
    ds = _write_mini_feeder(tmp_path)
    red = tmp_path / 'RED.txt'
    text = red.read_text(encoding='utf-8').replace('N2,30,40', 'N2,,')
    red.write_text(text, encoding='utf-8')
    ds = CymdistDataset.from_files(red, tmp_path / 'CARGA.txt', tmp_path / 'BD_Equipo.txt')
    try:
        build_feeder_model(ds, 'NA999', strict=True)
        raise AssertionError('expected ModelBuildError for missing georef')
    except ModelBuildError as exc:
        assert 'prueba de conexión' in str(exc).lower() or 'georreferen' in str(exc).lower()


def test_dgs_sed_gps_matches_txt_node(tmp_path):
    ds = _write_mini_feeder(tmp_path)
    model = build_feeder_model(ds, 'NA999')
    geo = build_geography(ds, model, source_crs='EPSG:32718')
    out = tmp_path / 'NA999.dgs'
    write_dgs(model, out, geography=geo)
    report = validate_dgs(model, out, geography=geo)
    assert report['connection_errors'] == []
    assert report['geographic_errors'] == []
    assert report['length_km']['georef_lines'] == len(model.lines)
