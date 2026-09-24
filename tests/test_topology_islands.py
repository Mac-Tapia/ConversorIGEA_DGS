"""Política de islas eléctricas (opción C).

Una **isla** es un conjunto de elementos sin ningún camino eléctrico hasta el SOURCE.
La política implementada distingue dos casos:

- **Isla vacía** (sin cargas ni SED): ruido del GIS — un fragmento dibujado y nunca
  conectado. Se avisa y se convierte.
- **Isla con cargas**: error de modelo. Esa carga no puede recibir energía, y la cadena
  entera lo silencia: el conversor la escribía con ``errors_total = 0``, PowerFactory la
  importa **en servicio** y su flujo devuelve **U = 0,0 p.u. como resultado válido**, sin
  marcar el área como no energizada. Bloquea en modo estricto.

``--non-strict`` sigue convirtiendo todo, degradando el error a aviso: es la vía para
quien acepta explícitamente un modelo con carga no alimentable.

Medido en el export de referencia: 10 de 93 alimentadores tienen isla; 8 arrastran carga
(20 cargas en total) y 2 están vacías (SL143, SM218).
"""

from __future__ import annotations

import pytest

from igea_dgs.batch import convert_selection
from igea_dgs.dataset import CymdistDataset
from igea_dgs.model import (
    IslandWithLoadsError,
    ModelBuildError,
    build_feeder_model,
    describe_islands,
    find_topology_islands,
)

NETWORK = 'NET_2030_150_NA999'


def _write_feeder(tmp_path, *, island_has_load: bool, with_island: bool = True):
    """N1→N2 alimentado, más un fragmento N9→N10 sin conexión al SOURCE."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    red, carga, equipo = tmp_path / 'RED.txt', tmp_path / 'CARGA.txt', tmp_path / 'BD_Equipo.txt'
    secciones = ['SEC_MAIN,N1,N2,ABC']
    conf = ['SEC_MAIN,DEFAULT,50,1']
    nodos = ['N1,0,0', 'N2,30,40']
    if with_island:
        nodos += ['N9,1000,0', 'N10,1030,40']
        secciones.append('SEC_ISLA,N9,N10,ABC')
        conf.append('SEC_ISLA,DEFAULT,50,1')
    red.write_text(
        '\n'.join([
            '[NODE]', 'FORMAT_NODE=NodeID,CoordX,CoordY', *nodos,
            '[SOURCE]', 'FORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage', f'{NETWORK},N1,13.2',
            '[SECTION]', 'FEEDER=' + NETWORK,
            'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase', *secciones,
            '[LINE CONFIGURATION]',
            'FORMAT_LINE CONFIGURATION=SectionID,LineCableID,Length,Overhead', *conf,
            '',
        ]),
        encoding='utf-8',
    )
    # La carga va en la isla o en la parte alimentada, segun el caso.
    seccion_carga = 'SEC_ISLA' if (with_island and island_has_load) else 'SEC_MAIN'
    carga.write_text(
        '\n'.join([
            '[LOADS]', 'FORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location',
            f'{seccion_carga},DEV_SE1001,SPOT,0,1',
            '[CUSTOMER LOADS]',
            'FORMAT_CUSTOMERLOADS=SectionID,DeviceNumber,CustomerNumber,CustomerType,'
            'Status,Year,ValueType,Phase,Value1,Value2,ConnectedKVA,KWH',
            f'{seccion_carga},DEV_SE1001,CUST_SE1001,1,1,2026,2,ABC,12.5,0.95,50,1200',
            '',
        ]),
        encoding='utf-8',
    )
    equipo.write_text(
        '[LINE]\nFORMAT_LINE=ID,R1,R0,X1,X0,B1,B0,Amps\nDEFAULT,0.3,0.5,0.4,1.4,0,0,250\n',
        encoding='utf-8',
    )
    return CymdistDataset.from_files(red, carga, equipo)


class TestIslandDetection:
    def test_no_island_in_a_connected_feeder(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=False, with_island=False)
        model = build_feeder_model(ds, 'NA999', strict=True)
        islands = find_topology_islands(model.source_node, model.lines, model.loads, model.seds)
        assert islands['sections'] == []
        assert islands['has_loads'] is False

    def test_island_is_reported_structurally(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=False)
        model = build_feeder_model(ds, 'NA999', strict=True)
        islands = find_topology_islands(model.source_node, model.lines, model.loads, model.seds)
        assert islands['sections'] == ['SEC_ISLA']
        assert sorted(islands['nodes']) == ['N10', 'N9']
        assert islands['loads'] == [] and islands['seds'] == []
        assert islands['has_loads'] is False

    def test_island_with_load_is_flagged(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=True)
        model = build_feeder_model(ds, 'NA999', strict=False)
        islands = find_topology_islands(model.source_node, model.lines, model.loads, model.seds)
        assert islands['has_loads'] is True
        assert islands['loads'] == ['DEV_SE1001']
        assert islands['seds'] == ['SE1001']


class TestEmptyIslandOnlyWarns:
    def test_conversion_succeeds_in_strict_mode(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=False)
        manifest = convert_selection(
            ds, ['NA999'], tmp_path / 'out', include_geography=False, strict=True,
        )
        item = manifest['feeders'][0]
        assert item['status'] == 'ok'
        assert item['errors_total'] == 0

    def test_the_warning_explains_it_carries_no_load(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=False)
        model = build_feeder_model(ds, 'NA999', strict=True)
        text = ' '.join(model.warnings)
        assert 'desconectados del SOURCE' in text
        assert 'no arrastra cargas' in text

    def test_the_island_reaches_the_manifest(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=False)
        manifest = convert_selection(
            ds, ['NA999'], tmp_path / 'out', include_geography=False, strict=True,
        )
        islands = manifest['feeders'][0]['islands']
        assert islands['sections'] == ['SEC_ISLA']
        assert islands['has_loads'] is False


class TestIslandWithLoadsBlocksInStrictMode:
    def test_strict_mode_fails_the_feeder(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=True)
        with pytest.raises(IslandWithLoadsError) as excinfo:
            build_feeder_model(ds, 'NA999', strict=True)
        assert excinfo.value.islands['loads'] == ['DEV_SE1001']
        assert isinstance(excinfo.value, ModelBuildError), 'debe seguir siendo ModelBuildError'

    def test_the_error_explains_the_consequence(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=True)
        with pytest.raises(IslandWithLoadsError) as excinfo:
            build_feeder_model(ds, 'NA999', strict=True)
        message = str(excinfo.value)
        assert 'no pueden recibir energía' in message
        assert '0,0 p.u.' in message
        assert '--non-strict' in message

    def test_no_dgs_is_published(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=True)
        out = tmp_path / 'out'
        manifest = convert_selection(ds, ['NA999'], out, include_geography=False, strict=True)
        item = manifest['feeders'][0]
        assert item['status'] == 'failed'
        assert item['dgs_published'] is False
        assert not (out / 'NA999.dgs').exists()

    def test_the_manifest_carries_the_island_on_failure(self, tmp_path):
        """Quien recibe el fallo debe saber qué tramos y cargas están afectados."""
        ds = _write_feeder(tmp_path / 'src', island_has_load=True)
        manifest = convert_selection(
            ds, ['NA999'], tmp_path / 'out', include_geography=False, strict=True,
        )
        islands = manifest['feeders'][0]['islands']
        assert islands['sections'] == ['SEC_ISLA']
        assert islands['loads'] == ['DEV_SE1001']
        assert islands['has_loads'] is True

    def test_non_strict_converts_and_degrades_to_warning(self, tmp_path):
        ds = _write_feeder(tmp_path / 'src', island_has_load=True)
        out = tmp_path / 'out'
        manifest = convert_selection(ds, ['NA999'], out, include_geography=False, strict=False)
        item = manifest['feeders'][0]
        assert item['status'] == 'ok'
        assert (out / 'NA999.dgs').is_file()
        assert any('no pueden recibir energía' in w for w in item['warnings'])


class TestIslandMessage:
    def test_message_distinguishes_the_two_cases(self):
        vacia = {'sections': ['S1'], 'nodes': ['N9'], 'loads': [], 'seds': [], 'has_loads': False}
        con_carga = {'sections': ['S1'], 'nodes': ['N9'], 'loads': ['D1'], 'seds': ['SE1'], 'has_loads': True}
        texto_vacia = describe_islands('AL01', 'N1', vacia)
        texto_carga = describe_islands('AL01', 'N1', con_carga)
        assert 'no arrastra cargas' in texto_vacia
        assert 'no pueden recibir energía' not in texto_vacia
        assert 'no pueden recibir energía' in texto_carga
        assert 'no arrastra cargas' not in texto_carga

    def test_message_truncates_long_section_lists(self):
        islands = {
            'sections': [f'S{i}' for i in range(20)],
            'nodes': [], 'loads': [], 'seds': [], 'has_loads': False,
        }
        text = describe_islands('AL01', 'N1', islands)
        assert '+12 más' in text


class TestRealBatchIslandPolicy:
    """Sobre el export real: 8 alimentadores bloquean, 2 solo avisan."""

    def test_strict_blocks_only_islands_with_loads(self, ds, tmp_path):
        manifest = convert_selection(
            ds, None, tmp_path / 'strict', all_feeders=True,
            include_geography=True, source_crs='EPSG:32718', strict=True,
        )
        for item in manifest['feeders']:
            islands = item.get('islands') or {}
            if islands.get('has_loads'):
                assert item['status'] == 'failed', item['feeder']
            else:
                assert item['status'] == 'ok', f"{item['feeder']}: {item.get('error')}"

    def test_non_strict_converts_the_whole_batch(self, ds, tmp_path):
        manifest = convert_selection(
            ds, None, tmp_path / 'ns', all_feeders=True,
            include_geography=True, source_crs='EPSG:32718', strict=False,
        )
        assert manifest['summary']['failed'] == 0
        assert manifest['summary']['ok'] == len(ds.feeder_ids())
