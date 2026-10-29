"""Cargas de SED por libro Excel/CSV, en el formato real de la empresa.

Formato nativo (``referencia/PA217.xlsx``): **una hoja por alimentador**, el nombre de la
hoja es el alimentador, y las columnas son ``SED · Kw · Kvar · (kVA) · FP``.

Lo que se fija aquí:

- Cada fila trae un par: ``Kw``/``Kvar``, ``Kw``/``FP`` o ``(kVA)``/``FP``. El último
  es el del fichero real, donde las dos primeras columnas vienen en blanco.
- Si trae más de un par y no coinciden, es un error de fila: nunca manda uno en silencio.
- Una fila en blanco no toca la SED.
- ``FP = 0`` y ``kVA = 0`` no es un error: es una SED sin dato, y se cuenta aparte.

El cruce con el modelo de la conversión se retiró (spec 004): qué SED existe lo decide
``tools/cargas_pf.py`` en el proyecto de DIgSILENT.

Spec 034: 034:RF-6.
"""

from __future__ import annotations

import math

import pytest

from igea_dgs.loads import (
    ACTION_SKIP,
    SHEET_COLUMNS,
    LoadTemplateError,
    canonical_columns,
    read_sheet,
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

    @pytest.mark.parametrize('cabecera', ['cos fi', 'Cos φ', 'FdP'])
    def test_power_factor_spellings(self, cabecera):
        assert canonical_columns(['SED', cabecera])[1] == 'FP'

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

    def test_kw_and_power_factor_give_kvar(self):
        """Medidor que da kW y cos φ, sin reactiva."""
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '46', '', '', '0.92']], 'AL01')
        assert sheet.errors == []
        row = sheet.rows[0]
        assert row.derived is True
        assert row.kw == pytest.approx(46.0)
        assert row.kvar == pytest.approx(46.0 * math.tan(math.acos(0.92)))
        assert row.kva == pytest.approx(50.0)

    def test_kw_with_unit_power_factor_has_no_reactive(self):
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '30', '', '', '1']], 'AL01')
        assert sheet.rows[0].kvar == pytest.approx(0.0)

    def test_disagreeing_pairs_are_an_error_not_a_silent_choice(self):
        """Antes Kw/Kvar mandaban y el (kVA)/FP escrito se perdía sin aviso."""
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '100', '30', '999', '0.5']], 'AL01')
        assert sheet.rows == []
        assert len(sheet.errors) == 1
        assert 'fila 2' in sheet.errors[0] and 'no coincide' in sheet.errors[0]

    def test_kw_fp_against_a_different_kva_is_an_error(self):
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '46', '', '80', '0.92']], 'AL01')
        assert any('(kVA)' in e for e in sheet.errors)

    def test_agreeing_pairs_within_rounding_are_accepted(self):
        """kW 46 y kvar 19,6 dan FP 0,9200; una hoja con FP a dos decimales cuadra."""
        sheet = read_sheet(list(SHEET_COLUMNS), [['SE1001', '46', '19.6', '50', '0.92']], 'AL01')
        assert sheet.errors == []
        assert sheet.rows[0].kw == pytest.approx(46.0)

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
