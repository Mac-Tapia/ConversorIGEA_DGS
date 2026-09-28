"""Cargas de SED por libro Excel/CSV, en el formato real de la empresa.

Formato nativo (``referencia/PA217.xlsx``): **una hoja por alimentador**, el nombre de la
hoja es el alimentador, y las columnas son ``SED · Kw · Kvar · (kVA) · FP``.

Lo que se fija aquí:

- ``Kw``/``Kvar`` vacías con ``(kVA)`` y ``FP`` presentes → se **derivan**
  (``Kw = kVA·FP``, ``Kvar = kVA·√(1−FP²)``). Es el caso del fichero real, donde las dos
  primeras columnas vienen en blanco.
- Si se rellenan ``Kw``/``Kvar``, **mandan** y no se deriva nada.
- ``FP = 0`` y ``kVA = 0`` no es un error: es una SED sin dato, y se cuenta aparte.
- Una sola fila inválida bloquea toda la actualización.
- SED de la hoja que no están en el modelo → ``unknown``, nunca se inventan.
- SED del modelo que la hoja no menciona → ``untouched``.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from igea_dgs.loads import (
    ACTION_SKIP,
    EXTRA_COLUMNS,
    SHEET_COLUMNS,
    LoadTemplateError,
    build_plan,
    canonical_columns,
    model_sed_loads,
    plan_to_payload,
    read_sheet,
    read_workbook,
    write_template,
)
from igea_dgs.model import FeederModel, Load, Node, Sed

REAL_XLSX = Path(__file__).resolve().parents[1] / 'referencia' / 'PA217.xlsx'


def _model(n: int = 3, name: str = 'AL01') -> FeederModel:
    nodes = {f'N{i}': Node(f'N{i}', float(i) * 10, 0.0) for i in range(n + 1)}
    loads, seds = [], []
    for i in range(1, n + 1):
        code = f'SE{1000 + i}'
        section, device = f'SEC_{i}', f'DEV_{i}_{code}'
        loads.append(Load(
            section_id=section, device_number=device, customer_number=f'CUST_{code}',
            location='1', node_id=f'N{i}', p_mw=0.010 * i, q_mvar=0.003 * i,
            pf=0.95, connected_kva=50.0 * i, kwh=0.0, phase='ABC',
            sed_code=code, display_name=code,
        ))
        seds.append(Sed(
            code=code, loc_name=code, node_id=f'N{i}', design_kva=50.0 * i,
            section_id=section, device_number=device, load_key=(section, device),
        ))
    return FeederModel(
        name=name, network_id=f'NET_{name}', nominal_kv=10.0, source_node='N0',
        nodes=nodes, lines=[], loads=loads, devices=[], line_types={}, seds=seds,
    )


class TestColumnRecognition:
    def test_native_header_is_recognised(self):
        mapping = canonical_columns(list(SHEET_COLUMNS))
        assert set(mapping.values()) == set(SHEET_COLUMNS)

    def test_spelling_variants_are_tolerated(self):
        """Un fichero con «P (kW)» o «cos phi» debe entenderse igual."""
        mapping = canonical_columns(['SED', 'P (kW)', 'Q kvar', 'S kVA', 'cos phi'])
        assert mapping[1] == 'Kw'
        assert mapping[2] == 'Kvar'
        assert mapping[3] == '(kVA)'
        assert mapping[4] == 'FP'

    def test_unknown_columns_are_ignored(self):
        mapping = canonical_columns(['SED', 'Kw', 'zona', 'comentario'])
        assert set(mapping.values()) == {'SED', 'Kw'}

    def test_sheet_without_sed_column_is_rejected(self):
        with pytest.raises(LoadTemplateError, match='código de SED'):
            read_sheet(['nombre', 'Kw'], [['X', 1]], 'AL01')


class TestPowerDerivation:
    def test_kw_kvar_are_derived_from_kva_and_fp(self):
        """El caso del fichero real: Kw y Kvar vienen vacías."""
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '', '', '0.3633217774', '0.936182876']], 'AL01')
        assert sheet.errors == []
        row = sheet.rows[0]
        assert row.derived is True
        assert row.kw == pytest.approx(0.3401, abs=1e-4)
        assert row.kvar == pytest.approx(0.1277, abs=1e-4)
        # El módulo debe reconstruir el kVA de partida.
        assert math.hypot(row.kw, row.kvar) == pytest.approx(0.3633217774, rel=1e-9)

    def test_explicit_kw_kvar_without_redundant_pair_are_used(self):
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '100', '30', '', '']], 'AL01')
        row = sheet.rows[0]
        assert row.derived is False
        assert row.kw == pytest.approx(100.0)
        assert row.kvar == pytest.approx(30.0)
        assert row.kva == pytest.approx(math.hypot(100.0, 30.0))

    def test_only_kw_given_leaves_q_at_zero(self):
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '80', '', '', '']], 'AL01')
        row = sheet.rows[0]
        assert row.kw == pytest.approx(80.0)
        assert row.kvar == pytest.approx(0.0)

    def test_zero_kva_and_zero_fp_is_no_data_not_an_error(self):
        """En el fichero real son 59 filas: sin dato, no un fallo."""
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '', '', '0', '0']], 'AL01')
        assert sheet.errors == []
        assert sheet.no_data == ['SE1001']
        assert sheet.rows[0].kw == 0.0 and sheet.rows[0].kvar == 0.0

    def test_comma_decimal_separator(self):
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '', '', '1,5', '0,9']], 'AL01')
        assert sheet.errors == []
        assert sheet.rows[0].kw == pytest.approx(1.35)

    def test_inconsistent_pq_and_kva_fp_blocks_row(self):
        sheet = read_sheet(
            list(SHEET_COLUMNS),
            [['SE1001', '80', '60', '130', '0.8']],
            'AL01',
        )

        assert sheet.rows == []
        assert any('incoherentes' in error and '1 %' in error for error in sheet.errors)

    def test_consistent_redundant_power_is_accepted(self):
        sheet = read_sheet(
            list(SHEET_COLUMNS),
            [['SE1001', '80', '60', '100.5', '0.8']],
            'AL01',
        )

        assert sheet.errors == []
        assert sheet.rows[0].kw == pytest.approx(80.0)
        assert sheet.rows[0].kvar == pytest.approx(60.0)


class TestRowValidation:
    def _read(self, row):
        return read_sheet(list(SHEET_COLUMNS) + ['accion'], [row], 'AL01')

    def test_non_numeric_is_reported_with_sheet_and_row(self):
        sheet = self._read(['SE1001', 'mucho', '', '', '', ''])
        assert len(sheet.errors) == 1
        assert 'hoja AL01' in sheet.errors[0] and 'fila 2' in sheet.errors[0]
        assert 'Kw' in sheet.errors[0]

    def test_power_factor_out_of_range(self):
        sheet = self._read(['SE1001', '', '', '10', '1.4', ''])
        assert any('FP' in e and 'fuera de' in e for e in sheet.errors)

    def test_negative_value_is_reported(self):
        sheet = self._read(['SE1001', '-5', '', '', '', ''])
        assert any('negativo' in e for e in sheet.errors)

    def test_duplicate_sed_is_reported(self):
        """El fichero real trae dos: SE30800 y SE30583."""
        sheet = read_sheet(
            list(SHEET_COLUMNS),
            [['SE1001', '', '', '1', '0.9'], ['SE1001', '', '', '2', '0.9']],
            'AL01',
        )
        assert any('repetida' in e for e in sheet.errors)
        assert len(sheet.rows) == 1

    def test_blank_rows_are_skipped_silently(self):
        sheet = read_sheet(list(SHEET_COLUMNS), [['', '', '', '', ''], ['SE1001', '', '', '1', '0.9']], 'AL01')
        assert sheet.errors == []
        assert len(sheet.rows) == 1

    def test_invalid_action_is_reported(self):
        sheet = self._read(['SE1001', '', '', '1', '0.9', 'borrar'])
        assert any('accion' in e for e in sheet.errors)

    def test_skip_action_excludes_the_sed(self):
        sheet = self._read(['SE1001', '', '', '1', '0.9', ACTION_SKIP])
        assert sheet.rows == []
        assert sheet.skipped == ['SE1001']


class TestTemplateGeneration:
    def test_xlsx_has_one_sheet_per_feeder_in_the_native_format(self, tmp_path):
        from openpyxl import load_workbook

        feeders = {'PA217': model_sed_loads(_model(3, 'PA217')),
                   'IN111': model_sed_loads(_model(2, 'IN111'))}
        path = write_template(feeders, tmp_path / 'cargas.xlsx')
        wb = load_workbook(path)
        assert wb.sheetnames == ['PA217', 'IN111']
        header = [c.value for c in wb['PA217'][1]]
        assert header[:len(SHEET_COLUMNS)] == list(SHEET_COLUMNS)
        assert header[len(SHEET_COLUMNS):] == list(EXTRA_COLUMNS)
        assert wb['PA217'].max_row == 4          # cabecera + 3 SED
        assert wb['IN111'].max_row == 3

    def test_template_round_trip_preserves_the_seds(self, tmp_path):
        model = _model(4, 'PA217')
        path = write_template({'PA217': model_sed_loads(model)}, tmp_path / 'c.xlsx')
        libro = read_workbook(path)
        assert list(libro) == ['PA217']
        assert {r.sed_code for r in libro['PA217'].rows} == {s.code for s in model.seds}

    def test_csv_carries_the_feeder_in_a_column(self, tmp_path):
        feeders = {'PA217': model_sed_loads(_model(2, 'PA217')),
                   'IN111': model_sed_loads(_model(2, 'IN111'))}
        path = write_template(feeders, tmp_path / 'cargas.csv')
        with path.open(encoding='utf-8-sig', newline='') as fh:
            rows = list(csv.reader(fh, delimiter=';'))
        assert rows[0][0] == 'feeder'
        libro = read_workbook(path)
        assert set(libro) == {'PA217', 'IN111'}

    def test_list_instead_of_dict_is_accepted(self, tmp_path):
        path = write_template(model_sed_loads(_model(2, 'AL01')), tmp_path / 'c.xlsx')
        assert list(read_workbook(path)) == ['AL01']

    def test_unsupported_extension_is_rejected(self, tmp_path):
        with pytest.raises(LoadTemplateError, match='no soportada'):
            write_template(model_sed_loads(_model(1)), tmp_path / 'c.txt')


class TestWorkbookReading:
    def test_empty_sheets_are_ignored(self, tmp_path):
        """El fichero real trae IN111 y PA219 vacías: no deben ser un error."""
        from openpyxl import Workbook

        wb = Workbook()
        wb.remove(wb.active)
        ws = wb.create_sheet('PA217')
        ws.append(list(SHEET_COLUMNS))
        ws.append(['SE1001', '', '', '1.5', '0.9'])
        wb.create_sheet('IN111')            # totalmente vacía
        solo_cabecera = wb.create_sheet('PA219')
        solo_cabecera.append(list(SHEET_COLUMNS))
        path = tmp_path / 'c.xlsx'
        wb.save(path)

        libro = read_workbook(path)
        assert list(libro) == ['PA217']

    def test_a_broken_sheet_does_not_sink_the_workbook(self, tmp_path):
        from openpyxl import Workbook

        wb = Workbook()
        wb.remove(wb.active)
        buena = wb.create_sheet('PA217')
        buena.append(list(SHEET_COLUMNS))
        buena.append(['SE1001', '', '', '1.5', '0.9'])
        ajena = wb.create_sheet('NOTAS')
        ajena.append(['esto', 'no', 'es', 'una', 'hoja de cargas'])
        ajena.append(['x', 'y', 'z', '', ''])
        path = tmp_path / 'c.xlsx'
        wb.save(path)

        libro = read_workbook(path)
        assert libro['PA217'].errors == []
        assert libro['NOTAS'].errors, 'la hoja ajena debe reportar su problema'

    def test_missing_file_is_reported(self, tmp_path):
        with pytest.raises(LoadTemplateError, match='No se encuentra'):
            read_workbook(tmp_path / 'no-existe.xlsx')

    def test_workbook_without_data_is_reported(self, tmp_path):
        from openpyxl import Workbook

        wb = Workbook()
        path = tmp_path / 'vacio.xlsx'
        wb.save(path)
        with pytest.raises(LoadTemplateError, match='ninguna hoja con datos'):
            read_workbook(path)

    def test_uncached_xlsx_formula_is_blocking(self, tmp_path):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = 'AL01'
        ws.append(list(SHEET_COLUMNS))
        ws.append(['SE1001', '=40+2', '', '', ''])
        path = tmp_path / 'formula_sin_cache.xlsx'
        wb.save(path)

        sheet = read_workbook(path)['AL01']

        assert sheet.rows == []
        assert any('fórmula' in error and 'resultado calculado' in error for error in sheet.errors)


class TestPlanDiff:
    def _sheet(self, rows, feeder='AL01'):
        return read_sheet(list(SHEET_COLUMNS), rows, feeder)

    def test_existing_seds_are_updated(self):
        model = _model(3)
        sheet = self._sheet([['SE1001', '120', '40', '', '']])
        plan = build_plan(model, sheet)
        assert len(plan.updates) == 1
        actual, nueva = plan.updates[0]
        assert actual.kw == pytest.approx(10.0)      # 0,010 MW
        assert nueva.kw == pytest.approx(120.0)
        # La identidad la pone el modelo, no la hoja.
        assert nueva.section_id == 'SEC_1'
        assert nueva.node_id == 'N1'

    def test_unknown_sed_is_not_invented(self):
        model = _model(2)
        sheet = self._sheet([['SE1001', '10', '3', '', ''], ['5SE9999', '25', '8', '', '']])
        plan = build_plan(model, sheet)
        assert [r.sed_code for r in plan.unknown] == ['5SE9999']
        assert len(plan.updates) == 1
        assert 'módulo de creación' in plan.report()

    def test_sed_absent_from_the_sheet_is_untouched(self):
        model = _model(3)
        plan = build_plan(model, self._sheet([['SE1001', '10', '3', '', '']]))
        assert plan.untouched == ['SE1002', 'SE1003']

    def test_one_bad_row_blocks_the_whole_update(self):
        model = _model(3)
        sheet = self._sheet([['SE1001', 'mucho', '', '', ''], ['SE1002', '10', '3', '', '']])
        plan = build_plan(model, sheet)
        assert plan.row_errors
        assert plan.is_applicable is False

    def test_four_zero_values_are_no_data_and_leave_existing_load_untouched(self):
        model = _model(1)
        sheet = read_sheet(
            list(SHEET_COLUMNS) + ['accion'],
            [['SE1001', '0', '0', '0', '0', 'actualizar']],
            'AL01',
        )

        plan = build_plan(model, sheet)

        assert plan.updates == []
        assert plan.no_data == ['SE1001']
        assert plan.untouched == []

    def test_four_blank_values_are_no_data(self):
        model = _model(1)
        sheet = read_sheet(
            list(SHEET_COLUMNS) + ['accion'],
            [['SE1001', '', '', '', '', '']],
            'AL01',
        )

        plan = build_plan(model, sheet)

        assert plan.updates == []
        assert plan.no_data == ['SE1001']

    def test_put_zero_is_an_explicit_update(self):
        model = _model(1)
        sheet = read_sheet(
            list(SHEET_COLUMNS) + ['accion'],
            [['SE1001', '0', '0', '0', '0', 'poner_cero']],
            'AL01',
        )

        plan = build_plan(model, sheet)
        payload = plan_to_payload(plan)

        assert plan.row_errors == []
        assert len(plan.updates) == 1
        assert payload['updates'][0]['plini_mw'] == 0.0
        assert payload['updates'][0]['qlini_mvar'] == 0.0

    def test_summary_counts_every_category(self):
        model = _model(4)
        sheet = read_sheet(
            list(SHEET_COLUMNS) + ['accion'],
            [
                ['SE1001', '', '', '1', '0.9', ACTION_SKIP],
                ['SE1002', '50', '15', '', '', ''],
                ['SE1003', '', '', '0', '0', ''],          # sin datos
                ['SE9999', '10', '3', '', '', ''],          # no está en el modelo
            ],
            'AL01',
        )
        plan = build_plan(model, sheet)
        assert plan.summary() == {
            'feeder': 'AL01', 'updates': 1, 'unknown': 1, 'untouched': 1,
            'skipped': 1, 'no_data': 1, 'row_errors': 0, 'applicable': True,
        }


class TestPayloadForPowerFactory:
    def test_units_are_converted_to_mw_for_powerfactory(self):
        model = _model(2)
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '120', '50', '', '']], 'AL01')
        payload = plan_to_payload(build_plan(model, sheet))
        item = payload['updates'][0]
        assert item['plini_mw'] == pytest.approx(0.120)
        assert item['qlini_mvar'] == pytest.approx(0.050)
        assert item['slini_mva'] == pytest.approx(math.hypot(0.120, 0.050))
        assert item['previous']['plini_mw'] == pytest.approx(0.010)

    def test_derived_flag_travels_to_the_payload(self):
        model = _model(1)
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '', '', '10', '0.9']], 'AL01')
        payload = plan_to_payload(build_plan(model, sheet))
        assert payload['updates'][0]['derived_from_kva_fp'] is True

    def test_payload_is_json_serialisable(self):
        import json

        model = _model(3)
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '1', '1', '', '']], 'AL01')
        payload = plan_to_payload(build_plan(model, sheet))
        assert json.loads(json.dumps(payload))['summary']['updates'] == 1


@pytest.mark.skipif(not REAL_XLSX.is_file(), reason='referencia/PA217.xlsx no está presente')
class TestRealCompanyWorkbook:
    """El libro real de la empresa, con sus problemas de datos incluidos."""

    def test_the_real_workbook_is_read(self):
        libro = read_workbook(REAL_XLSX)
        assert 'PA217' in libro
        sheet = libro['PA217']
        assert len(sheet.rows) > 100
        # Kw/Kvar vienen vacías: la mayoría de cargas deben salir derivadas.
        assert sum(1 for r in sheet.rows if r.derived) > 50

    def test_it_reports_the_duplicate_seds_it_contains(self):
        sheet = read_workbook(REAL_XLSX)['PA217']
        duplicados = [e for e in sheet.errors if 'repetida' in e]
        assert duplicados, 'el fichero real tiene SED repetidas y deben detectarse'

    def test_plan_against_the_real_model(self, ds):
        from igea_dgs.model import build_feeder_model

        try:
            model = build_feeder_model(ds, 'PA217', strict=False)
        except KeyError:
            pytest.skip('PA217 no está en el export cargado')
        plan = build_plan(model, read_workbook(REAL_XLSX)['PA217'])
        # La mayoría de las SED de la hoja existen en el modelo.
        assert len(plan.updates) > 150
        # Y el fichero trae una SED que no existe: '5SE31022', un SE31022 con un 5 de más.
        assert any(r.sed_code.startswith('5') for r in plan.unknown)
        # Las SED con prefijo M del modelo no están en la hoja.
        assert plan.untouched
        # Con filas repetidas, el plan NO es aplicable hasta corregirlas.
        assert plan.is_applicable is False
