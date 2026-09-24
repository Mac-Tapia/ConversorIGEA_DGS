"""Segunda alternativa de entrada: base Access de CYMDIST, y estudio opcional.

Los tests del estudio son sintéticos y siempre corren. Los de la base necesitan un
``.mdb`` real —que no es publicable— y se activan con variables de entorno:

    set IGEA_MDB=D:\\ruta\\BaseDatos.mdb
    set IGEA_EQUIPMENT_MDB=D:\\ruta\\OtraBase.mdb   (opcional)
    set IGEA_STUDY=D:\\ruta\\estudio.zxst           (opcional)

La prueba que de verdad valida el mapeo es
``TestAccessMatchesTxt::test_same_network_from_both_inputs``: lee el mismo sistema por
las dos vías y exige que coincidan alimentadores, nodos, tramos, cargas y tensiones.
Requiere además los TXT (``IGEA_RED`` etc.) del mismo sistema.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from igea_dgs.study import STUDY_SUFFIXES, StudyReadError, describe, study_networks


def _write_study(path: Path, networks: list[str], *, zipped: bool = True) -> Path:
    """Estudio CYMDIST mínimo con la estructura observada en un .zxst real."""
    items = ''.join(f'    <NetworkID>{n}</NetworkID>\n' for n in networks)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!--Copyright (c) 1986-2026, CYME International T&amp;D-->\n'
        '<Cyme>\n'
        '  <Networks>\n' + items + '  </Networks>\n'
        # Otros elementos también llevan NetworkID, pero son ajustes, no el alcance.
        '  <LoadFlowLoadScalingFactors>\n'
        '    <CurrentNetworkID>OTRA_RED_QUE_NO_CUENTA</CurrentNetworkID>\n'
        '    <NetworkID>OTRA_RED_QUE_NO_CUENTA</NetworkID>\n'
        '  </LoadFlowLoadScalingFactors>\n'
        '</Cyme>\n'
    )
    if not zipped:
        path.write_text(xml, encoding='utf-8')
        return path
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f'{path.stem}.xst', xml)
    return path


class TestStudyReader:
    """El estudio es opcional y solo aporta el alcance: qué alimentadores incluir."""

    def test_reads_networks_from_a_zipped_study(self, tmp_path):
        path = _write_study(tmp_path / 'estudio.zxst', ['NET_A', 'NET_B', 'NET_C'])
        assert study_networks(path) == ['NET_A', 'NET_B', 'NET_C']

    def test_reads_networks_from_a_plain_xst(self, tmp_path):
        path = _write_study(tmp_path / 'estudio.xst', ['NET_B', 'NET_A'], zipped=False)
        assert study_networks(path) == ['NET_A', 'NET_B']

    def test_only_the_networks_element_defines_the_scope(self, tmp_path):
        """Los NetworkID de factores de escala o arc flash no amplían el alcance."""
        path = _write_study(tmp_path / 'e.zxst', ['NET_A'])
        assert study_networks(path) == ['NET_A']

    def test_duplicates_are_collapsed(self, tmp_path):
        path = _write_study(tmp_path / 'e.zxst', ['NET_A', 'NET_A', 'NET_B'])
        assert study_networks(path) == ['NET_A', 'NET_B']

    def test_describe_summarises_for_the_manifest(self, tmp_path):
        path = _write_study(tmp_path / 'base2026.zxst', ['NET_A', 'NET_B'])
        info = describe(path)
        assert info['study_name'] == 'base2026'
        assert info['network_count'] == 2
        assert info['networks'] == ['NET_A', 'NET_B']

    def test_missing_file_is_reported(self, tmp_path):
        with pytest.raises(StudyReadError, match='No se encuentra'):
            study_networks(tmp_path / 'no-existe.zxst')

    def test_zip_without_xst_is_reported(self, tmp_path):
        path = tmp_path / 'malo.zxst'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('leeme.txt', 'no soy un estudio')
        with pytest.raises(StudyReadError, match='no contiene ningún .xst'):
            study_networks(path)

    def test_study_without_networks_is_reported(self, tmp_path):
        path = tmp_path / 'vacio.zxst'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('vacio.xst', '<?xml version="1.0"?><Cyme></Cyme>')
        with pytest.raises(StudyReadError, match='<Networks>'):
            study_networks(path)

    def test_unreadable_xml_is_reported(self, tmp_path):
        path = tmp_path / 'roto.xst'
        path.write_text('<Cyme><Networks>', encoding='utf-8')
        with pytest.raises(StudyReadError, match='XML ilegible'):
            study_networks(path)

    def test_known_suffixes(self):
        assert '.zxst' in STUDY_SUFFIXES and '.xst' in STUDY_SUFFIXES


class TestNominalVoltageReconstruction:
    """CYMSOURCE guarda la fase-neutro; la nominal es ×√3 y hay que redondearla."""

    def test_phase_to_phase_is_recovered_exactly(self):
        from igea_dgs.access import _nominal_kv

        # Valores reales de un export: 5.773503 → 10 kV, 13.221321 → 22.9 kV.
        assert _nominal_kv(5.773503) == '10'
        assert _nominal_kv(13.221321) == '22.9'
        assert _nominal_kv(7.621024) == '13.2'

    def test_absent_or_invalid_voltage_yields_empty(self):
        from igea_dgs.access import _nominal_kv

        assert _nominal_kv(None) == ''
        assert _nominal_kv('no-es-numero') == ''
        assert _nominal_kv(float('nan')) == ''


class TestPhaseCodeDecoding:
    """La base guarda la fase como código numérico; el motor espera letras.

    Este fue un error real del lector: escribía '7' donde el TXT dice 'ABC', en los
    38.657 tramos. No lo detectó ninguna prueba porque hoy ``dgs.py`` **ignora**
    ``line.phase`` y fuerza las tres fases (hallazgo C-04 del diagnóstico): la fase
    nunca llegaba al DGS. En cuanto se implemente el modelo por fase, un fallo así
    produciría un modelo eléctricamente falso — de ahí esta prueba.
    """

    def test_codes_map_to_the_letters_the_engine_uses(self):
        from igea_dgs.access import _phase

        assert _phase(1) == 'A'
        assert _phase(2) == 'B'
        assert _phase(3) == 'C'
        assert _phase(4) == 'AB'
        assert _phase(5) == 'AC'
        assert _phase(6) == 'BC'
        assert _phase(7) == 'ABC'

    def test_it_is_an_enumeration_not_a_bitmask(self):
        """3 es 'C', no 'A+B': tratarlo como máscara de bits daría fases erróneas."""
        from igea_dgs.access import _phase

        assert _phase(3) == 'C'
        assert _phase(4) == 'AB'

    def test_unknown_or_absent_code_is_empty(self):
        from igea_dgs.access import _phase

        assert _phase(None) == ''
        assert _phase(0) == ''
        assert _phase(99) == ''
        assert _phase('x') == ''

    def test_real_database_phases_match_the_txt(self, access_dataset, ds):
        if set(access_dataset.feeder_ids()) != set(ds.feeder_ids()):
            pytest.skip('la base y los TXT no son del mismo sistema')
        wrong = [
            s for s, row in ds.sections.items()
            if access_dataset.sections[s]['Phase'] != row['Phase']
        ]
        assert not wrong[:5], f'{len(wrong)} tramos con fase distinta'

    def test_device_phase_comes_from_its_section(self, access_dataset):
        """ClosedPhase describe qué fases están cerradas, no las del equipo."""
        by_section = access_dataset.sections
        for row in list(access_dataset.sectionalizer_settings)[:200]:
            expected = by_section.get(row['SectionID'], {}).get('Phase', '')
            assert row['EqPhase'] == expected, row['SectionID']


class TestAccessErrorsAreActionable:
    def test_missing_database_is_reported(self, tmp_path):
        pytest.importorskip('pyodbc')
        from igea_dgs.access import AccessReadError, read_access_dataset

        with pytest.raises(AccessReadError, match='No se encuentra'):
            read_access_dataset(tmp_path / 'no-existe.mdb')

    def test_available_reports_driver_presence(self):
        from igea_dgs.access import available

        assert isinstance(available(), bool)


# ---------------------------------------------------------------- integración real

MDB = os.environ.get('IGEA_MDB', '').strip()
SKIP_MDB = 'Defina IGEA_MDB con la ruta de una base de red CYMDIST (.mdb)'


@pytest.fixture(scope='session')
def access_dataset():
    if not MDB or not Path(MDB).is_file():
        pytest.skip(SKIP_MDB)
    pytest.importorskip('pyodbc')
    from igea_dgs.access import AccessReadError, read_access_dataset

    try:
        return read_access_dataset(MDB, equipment_db=os.environ.get('IGEA_EQUIPMENT_MDB') or None)
    except AccessReadError as exc:
        pytest.skip(f'No se pudo leer {MDB}: {exc}')


class TestAccessDatasetIsUsable:
    def test_dataset_has_the_expected_shape(self, access_dataset):
        ds = access_dataset
        assert ds.feeders, 'debe haber alimentadores'
        assert ds.nodes and ds.sections and ds.line_configurations
        assert any(ds.equipment_tables.get(t) for t in ('LINE', 'CONCENTRIC NEUTRAL CABLE'))
        # Todo tramo debe tener configuración de línea, o el modelo no se puede construir.
        sin_config = [s for s in ds.sections if s not in ds.line_configurations]
        assert not sin_config[:5], f'{len(sin_config)} tramos sin LINE CONFIGURATION'

    def test_every_feeder_converts(self, access_dataset, tmp_path):
        from igea_dgs.batch import convert_selection

        manifest = convert_selection(
            access_dataset, None, tmp_path / 'out', all_feeders=True,
            include_geography=True, source_crs='EPSG:32718', strict=True,
        )
        # Lo que se prueba es el lector Access. Los únicos fallos aceptables son los de
        # la política de islas con carga, que es independiente de la vía de entrada.
        otros = [
            f"{it['feeder']}: {it.get('error')}"
            for it in manifest['feeders']
            if it['status'] != 'ok' and not (it.get('islands') or {}).get('has_loads')
        ]
        assert not otros, otros[:5]
        # Sin modo estricto, la vía Access debe convertir absolutamente todo.
        todo = convert_selection(
            access_dataset, None, tmp_path / 'ns', all_feeders=True,
            include_geography=True, source_crs='EPSG:32718', strict=False,
        )
        assert todo['summary']['failed'] == 0, [
            it['error'] for it in todo['feeders'] if it['status'] != 'ok'
        ][:5]

    def test_study_limits_the_networks_read(self, access_dataset):
        from igea_dgs.access import read_access_dataset

        subset = sorted(access_dataset.feeder_ids())[:2]
        if len(subset) < 2:
            pytest.skip('se necesitan al menos 2 alimentadores')
        limited = read_access_dataset(
            MDB, equipment_db=os.environ.get('IGEA_EQUIPMENT_MDB') or None, networks=subset,
        )
        assert set(limited.feeder_ids()) == set(subset)
        # Los nodos NO se filtran: hay tramos que referencian nodos de otra red.
        assert len(limited.nodes) == len(access_dataset.nodes)


class TestAccessMatchesTxt:
    """La prueba que valida el mapeo: el mismo sistema por las dos vías."""

    @pytest.fixture
    def both(self, access_dataset, ds):
        if set(access_dataset.feeder_ids()) != set(ds.feeder_ids()):
            pytest.skip('la base y los TXT no son del mismo sistema')
        return access_dataset, ds

    def test_same_network_from_both_inputs(self, both):
        access, txt = both
        assert set(access.feeder_ids()) == set(txt.feeder_ids())
        assert set(access.sections) == set(txt.sections)
        assert set(access.nodes) == set(txt.nodes)
        assert set(access.customer_loads) == set(txt.customer_loads)
        assert len(access.intermediate_nodes) == len(txt.intermediate_nodes)
        assert len(access.switch_settings) == len(txt.switch_settings)
        assert len(access.sectionalizer_settings) == len(txt.sectionalizer_settings)

    def test_nominal_voltages_agree(self, both):
        access, txt = both
        for network_id, row in txt.sources.items():
            a = float(access.sources[network_id]['DesiredVoltage'])
            t = float(row['DesiredVoltage'])
            assert abs(a - t) < 1e-6, f'{network_id}: base={a} txt={t}'

    def test_lengths_agree(self, both):
        access, txt = both
        for section_id, row in txt.line_configurations.items():
            a = float(access.line_configurations[section_id]['Length'] or 0)
            t = float(row['Length'] or 0)
            assert abs(a - t) < 1e-3, f'{section_id}: base={a} txt={t}'

    def test_overhead_flag_agrees(self, both):
        access, txt = both
        for section_id, row in txt.line_configurations.items():
            assert access.line_configurations[section_id]['Overhead'] == row['Overhead'], section_id

    def test_access_never_has_less_type_information(self, both):
        """La base puede tener el conductor real donde el TXT dice DEFAULT, no al revés."""
        access, txt = both
        txt_default = {s for s, v in txt.line_configurations.items() if v['LineCableID'] == 'DEFAULT'}
        access_default = {s for s, v in access.line_configurations.items() if v['LineCableID'] == 'DEFAULT'}
        perdidos = access_default - txt_default
        assert not perdidos, (
            f'{len(perdidos)} tramos con código real en el TXT y DEFAULT en la base: '
            'el lector estaría perdiendo información'
        )
