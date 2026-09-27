"""Publicación atómica, cancelación y alimentadores solo-cabecera.

Cubre P0.4 del plan y la regla «si existe, se dibuja»:

- Nada se publica a medias. Cada alimentador se escribe en un área de preparación
  y solo se mueve a su sitio cuando está completo y validado, de modo que cerrar la
  ventana, cancelar o un corte no pueden dejar un ``.dgs`` truncado indistinguible
  de uno válido (F-02, K-09).
- Cancelar conserva lo ya convertido y descarta entero el alimentador en curso.
- El manifiesto se escribe siempre, incluso si el lote revienta (checklist backend).
- Un FEEDER=/SOURCE sin filas SECTION ya no se omite: se dibuja su barra de cabecera,
  que es lo único que el export contiene.
"""

from __future__ import annotations

import json
import threading

import pytest

from igea_dgs.batch import STAGE_PREFIX, convert_selection
from igea_dgs.dataset import CymdistDataset

NETWORK = 'NET_2030_150_NA999'
SECOND = 'NET_2030_151_NB888'


def _write_two_feeders(tmp_path, *, second_broken: bool = False):
    """Dos alimentadores independientes; el segundo puede romperse a voluntad."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    red = tmp_path / 'RED.txt'
    loads = tmp_path / 'CARGA.txt'
    equip = tmp_path / 'BD_Equipo.txt'
    # Un nodo inexistente en el segundo alimentador lo hace fallar sin tocar al primero.
    second_to = 'N_FANTASMA' if second_broken else 'M2'
    red.write_text(
        '\n'.join([
            '[NODE]',
            'FORMAT_NODE=NodeID,CoordX,CoordY',
            'N1,0,0',
            'N2,30,40',
            'M1,1000,0',
            'M2,1030,40',
            '[SOURCE]',
            'FORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage',
            f'{NETWORK},N1,13.2',
            f'{SECOND},M1,13.2',
            '[SECTION]',
            'FEEDER=' + NETWORK,
            'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
            'SEC_A,N1,N2,ABC',
            'FEEDER=' + SECOND,
            'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
            f'SEC_B,M1,{second_to},ABC',
            '[LINE CONFIGURATION]',
            'FORMAT_LINE CONFIGURATION=SectionID,LineCableID,Length,Overhead',
            'SEC_A,DEFAULT,50,1',
            'SEC_B,DEFAULT,50,1',
            '',
        ]),
        encoding='utf-8',
    )
    loads.write_text('[LOADS]\nFORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location\n', encoding='utf-8')
    equip.write_text(
        '[LINE]\nFORMAT_LINE=ID,R1,R0,X1,X0,B1,B0,Amps\nDEFAULT,0.1,0.2,0.3,0.4,0,0,200\n',
        encoding='utf-8',
    )
    return CymdistDataset.from_files(red, loads, equip)


def _write_source_only(tmp_path):
    """Cabecera real (SOURCE + headnode + nodo georreferenciado) sin filas SECTION."""
    red = tmp_path / 'RED.txt'
    loads = tmp_path / 'CARGA.txt'
    equip = tmp_path / 'BD_Equipo.txt'
    red.write_text(
        '\n'.join([
            '[HEADNODES]',
            'FORMAT_HEADNODES=NodeID,NetworkID',
            f'N1,{NETWORK}',
            '[NODE]',
            'FORMAT_NODE=NodeID,CoordX,CoordY',
            'N1,368978.941,8485182.089',
            '[SOURCE]',
            'FORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage',
            f'{NETWORK},N1,10.0',
            '[SECTION]',
            'FEEDER=' + NETWORK,
            'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
            '',
        ]),
        encoding='utf-8',
    )
    loads.write_text('[LOADS]\nFORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location\n', encoding='utf-8')
    equip.write_text(
        '[LINE]\nFORMAT_LINE=ID,R1,R0,X1,X0,B1,B0,Amps\nDEFAULT,0.1,0.2,0.3,0.4,0,0,200\n',
        encoding='utf-8',
    )
    return CymdistDataset.from_files(red, loads, equip)


def _stages(out_dir):
    return [p for p in out_dir.iterdir() if p.name.startswith(STAGE_PREFIX)]


class TestSourceOnlyFeeders:
    def test_header_only_feeder_is_drawn_not_skipped(self, tmp_path):
        ds = _write_source_only(tmp_path)
        out = tmp_path / 'out'
        manifest = convert_selection(ds, None, out, all_feeders=True, include_geography=False)

        assert manifest['summary'] == {
            'status': 'completed', 'selected': 1, 'requested': 1,
            'ok': 1, 'skipped': 0, 'failed': 0, 'not_processed': 0,
        }
        item = manifest['feeders'][0]
        assert item['topology'] == 'source_only'
        assert (out / 'NA999.dgs').is_file()

    def test_source_only_feeder_is_flagged_as_not_modelled(self, tmp_path):
        ds = _write_source_only(tmp_path)
        manifest = convert_selection(ds, None, tmp_path / 'out', all_feeders=True, include_geography=False)
        warnings = ' '.join(manifest['feeders'][0]['warnings'])
        assert 'solo trae la cabecera' in warnings
        assert 'NO es un alimentador modelado' in warnings

    def test_source_only_dgs_contains_only_what_exists(self, tmp_path):
        """No se inventa nada: una barra, su red externa, ni un tramo ni una carga."""
        from igea_dgs.validate import parse_dgs

        ds = _write_source_only(tmp_path)
        out = tmp_path / 'out'
        convert_selection(ds, None, out, all_feeders=True, include_geography=False)
        tables = parse_dgs(out / 'NA999.dgs')
        assert len(tables['ElmTerm']['rows']) == 1
        assert len(tables['ElmXnet']['rows']) == 1
        assert len(tables['ElmLne']['rows']) == 0
        assert len(tables['ElmLod']['rows']) == 0


class TestAtomicPublication:
    def test_no_staging_directory_survives_a_successful_batch(self, tmp_path):
        ds = _write_two_feeders(tmp_path)
        out = tmp_path / 'out'
        convert_selection(ds, None, out, all_feeders=True, include_geography=False)
        assert _stages(out) == []

    def test_failed_feeder_leaves_no_partial_dgs(self, tmp_path):
        ds = _write_two_feeders(tmp_path, second_broken=True)
        out = tmp_path / 'out'
        manifest = convert_selection(ds, None, out, all_feeders=True, include_geography=False, strict=True)

        assert manifest['summary']['ok'] == 1
        assert manifest['summary']['failed'] == 1
        assert (out / 'NA999.dgs').is_file()      # el bueno sí se publica
        assert (out / 'NA999_feeder_metadata.json').is_file()
        assert (out / 'NA999_name_alimentador.csv').is_file()
        assert not (out / 'NB888.dgs').exists()   # el roto no deja nada
        assert not (out / 'NB888_feeder_metadata.json').exists()
        assert not (out / 'NB888_name_alimentador.csv').exists()
        assert _stages(out) == []

    def test_failed_rerun_keeps_the_previous_good_dgs(self, tmp_path):
        """Reconvertir con datos rotos no puede destruir el resultado bueno anterior."""
        out = tmp_path / 'out'
        good = _write_two_feeders(tmp_path / 'good')
        convert_selection(good, ['NB888'], out, include_geography=False)
        previous = (out / 'NB888.dgs').read_bytes()
        assert previous

        broken = _write_two_feeders(tmp_path / 'broken', second_broken=True)
        manifest = convert_selection(broken, ['NB888'], out, include_geography=False, strict=True)

        assert manifest['summary']['failed'] == 1
        assert (out / 'NB888.dgs').read_bytes() == previous

    def test_manifest_records_whether_the_dgs_was_published(self, tmp_path):
        ds = _write_two_feeders(tmp_path, second_broken=True)
        manifest = convert_selection(
            ds, None, tmp_path / 'out', all_feeders=True, include_geography=False, strict=True,
        )
        by_feeder = {item['feeder']: item for item in manifest['feeders']}
        assert by_feeder['NA999']['dgs_published'] is True
        assert by_feeder['NB888']['dgs_published'] is False


class TestCancellation:
    def test_cancel_before_start_processes_nothing(self, tmp_path):
        ds = _write_two_feeders(tmp_path)
        out = tmp_path / 'out'
        cancel = threading.Event()
        cancel.set()

        manifest = convert_selection(
            ds, None, out, all_feeders=True, include_geography=False, cancel=cancel,
        )
        assert manifest['summary']['status'] == 'cancelled'
        assert manifest['summary']['requested'] == 0
        assert manifest['summary']['not_processed'] == 2
        assert not list(out.glob('*.dgs'))

    def test_cancel_midway_keeps_what_was_already_converted(self, tmp_path):
        ds = _write_two_feeders(tmp_path)
        out = tmp_path / 'out'
        cancel = threading.Event()

        def on_progress(network_id, index, total):
            if index == 1:
                cancel.set()   # cancelar tras empezar el primero

        manifest = convert_selection(
            ds, None, out, all_feeders=True, include_geography=False,
            cancel=cancel, on_progress=on_progress,
        )
        assert manifest['summary']['status'] == 'cancelled'
        assert manifest['summary']['ok'] == 1        # el primero se completó y publicó
        assert manifest['summary']['not_processed'] == 1
        assert _stages(out) == []                    # sin residuos a medias
        assert len(list(out.glob('*.dgs'))) == 1

    def test_manifest_is_written_even_when_cancelled(self, tmp_path):
        ds = _write_two_feeders(tmp_path)
        out = tmp_path / 'out'
        cancel = threading.Event()
        cancel.set()

        convert_selection(ds, None, out, all_feeders=True, include_geography=False, cancel=cancel)
        path = out / 'batch_manifest.json'
        assert path.is_file()
        assert json.loads(path.read_text(encoding='utf-8'))['summary']['status'] == 'cancelled'

    def test_manifest_is_written_even_when_the_batch_crashes(self, tmp_path, monkeypatch):
        """Un lote sin manifiesto es un lote sin traza, pase lo que pase."""
        import igea_dgs.batch as batch_module

        ds = _write_two_feeders(tmp_path)
        out = tmp_path / 'out'

        def boom(*args, **kwargs):
            raise MemoryError('simulado')

        monkeypatch.setattr(batch_module, 'build_feeder_model', boom)
        with pytest.raises(MemoryError):
            convert_selection(ds, None, out, all_feeders=True, include_geography=False)

        manifest = json.loads((out / 'batch_manifest.json').read_text(encoding='utf-8'))
        assert manifest['summary']['requested'] == 0
        assert _stages(out) == []


class TestShortNameCollisions:
    """K-20: dos NetworkID distintos con el mismo nombre corto (lote multiempresa).

    Antes, la colisión lanzaba ValueError **antes** del bucle: el lote entero se caía
    y no se convertía ni un alimentador, en contra de la regla de independencia por
    alimentador del skill de backend.
    """

    @staticmethod
    def _colliding(tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        red = tmp_path / 'RED.txt'
        # NET_2030_150_NA999 y NET_9000_77_NA999 comparten el nombre corto NA999.
        other = 'NET_9000_77_NA999'
        red.write_text(
            '\n'.join([
                '[NODE]',
                'FORMAT_NODE=NodeID,CoordX,CoordY',
                'N1,0,0', 'N2,30,40', 'M1,1000,0', 'M2,1030,40',
                '[SOURCE]',
                'FORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage',
                f'{NETWORK},N1,13.2',
                f'{other},M1,13.2',
                '[SECTION]',
                'FEEDER=' + NETWORK,
                'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
                'SEC_A,N1,N2,ABC',
                'FEEDER=' + other,
                'FORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase',
                'SEC_B,M1,M2,ABC',
                '[LINE CONFIGURATION]',
                'FORMAT_LINE CONFIGURATION=SectionID,LineCableID,Length,Overhead',
                'SEC_A,DEFAULT,50,1',
                'SEC_B,DEFAULT,50,1',
                '',
            ]),
            encoding='utf-8',
        )
        (tmp_path / 'CARGA.txt').write_text(
            '[LOADS]\nFORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location\n', encoding='utf-8')
        (tmp_path / 'BD_Equipo.txt').write_text(
            '[LINE]\nFORMAT_LINE=ID,R1,R0,X1,X0,B1,B0,Amps\nDEFAULT,0.1,0.2,0.3,0.4,0,0,200\n', encoding='utf-8')
        return CymdistDataset.from_files(red, tmp_path / 'CARGA.txt', tmp_path / 'BD_Equipo.txt')

    def test_collision_no_longer_aborts_the_whole_batch(self, tmp_path):
        ds = self._colliding(tmp_path / 'src')
        out = tmp_path / 'out'
        manifest = convert_selection(ds, None, out, all_feeders=True, include_geography=False)

        assert manifest['summary']['ok'] == 2
        assert manifest['summary']['failed'] == 0
        assert len(list(out.glob('*.dgs'))) == 2   # dos ficheros, ninguno pisa al otro

    def test_colliding_outputs_get_a_deterministic_suffix(self, tmp_path):
        ds = self._colliding(tmp_path / 'src')
        first = convert_selection(ds, None, tmp_path / 'a', all_feeders=True, include_geography=False)
        second = convert_selection(ds, None, tmp_path / 'b', all_feeders=True, include_geography=False)

        names = sorted(item['feeder'] for item in first['feeders'])
        assert names == sorted(item['feeder'] for item in second['feeders']), 'debe ser reproducible'
        assert all(n.startswith('NA999__') for n in names)
        assert len(set(names)) == 2
        for item in first['feeders']:
            assert item['short_name'] == 'NA999'   # el nombre corto real se conserva
        assert set(first['disambiguated_output_names'].values()) == set(names)

    def test_names_without_collision_keep_their_short_name(self, tmp_path):
        ds = _write_two_feeders(tmp_path / 'src')
        manifest = convert_selection(
            ds, None, tmp_path / 'out', all_feeders=True, include_geography=False,
        )
        assert sorted(item['feeder'] for item in manifest['feeders']) == ['NA999', 'NB888']
        assert manifest['disambiguated_output_names'] == {}
