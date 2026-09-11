"""Tests for DGS tabular export (TSV always; Excel if pandas/openpyxl present)."""

from __future__ import annotations

from pathlib import Path

import pytest

from igea_dgs.export_tables import load_dgs_table_rows, write_dgs_tsv, write_dgs_xlsx


MINI_DGS = """\
********************************************************************************
*
* test dgs
*
********************************************************************************

$$General;FID(a:40);Descr(a:40);Val(a:40)
  1;Version;7.0

$$ElmNet;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);frnom(r);pDiagram(p)
  2;C;DEMO;;;60;

$$ElmTerm;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);typ_id(p);systype(i);iUsage(i);uknom(r);unknom(r);iminus(i);outserv(i);GPSlat(r);GPSlon(r);vtarget(r)
  3;C;N1;2;;0;1;13.2;7.62;0;0;-12.05;-77.04;1
  4;C;N2;2;;0;1;13.2;7.62;0;0;-12.051;-77.039;1

$$TypLne;FID(a:40);OP(a:1);loc_name(a:40);uline(r);sline(r);InomAir(r);cohl_(i);rline(r);xline(r);rline0(r);xline0(r);Ithr(r);tmax(r);rtemp(r);systp(i);nlnph(i);nneutral(i);frnom(r);mlei(a:2);bline(r);bline0(r)
  5;C;AAAC;13.2;0.4;0.4;1;0.3;0.4;0.9;1.2;0;80;75;0;3;0;60;Al;0;0

$$ElmLne;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);typ_id(p);dline(r);fline(r);GPScoords:MATRIX;nlnum(i);inAir(i)
  6;C;SEC1;2;5;0.12;1;;1;1

"""


@pytest.fixture()
def mini_dgs(tmp_path: Path) -> Path:
    path = tmp_path / 'DEMO.dgs'
    path.write_text(MINI_DGS, encoding='utf-8')
    return path


def test_load_dgs_table_rows(mini_dgs: Path):
    tables = load_dgs_table_rows(mini_dgs)
    assert set(tables) >= {'General', 'ElmNet', 'ElmTerm', 'TypLne', 'ElmLne'}
    assert len(tables['ElmTerm']) == 2
    assert tables['ElmLne'][0]['loc_name'] == 'SEC1'
    assert tables['TypLne'][0]['rline'] == '0.3'


def test_write_dgs_tsv(mini_dgs: Path, tmp_path: Path):
    out = write_dgs_tsv(mini_dgs, tmp_path / 'tables')
    assert (out / 'ElmTerm.tsv').is_file()
    assert (out / 'ElmLne.tsv').is_file()
    text = (out / 'ElmLne.tsv').read_text(encoding='utf-8')
    assert 'SEC1' in text
    assert '\t' in text


def test_write_dgs_xlsx_optional(mini_dgs: Path, tmp_path: Path):
    pytest.importorskip('pandas')
    pytest.importorskip('openpyxl')
    out = write_dgs_xlsx(mini_dgs, tmp_path / 'DEMO.xlsx')
    assert out.is_file()
    import pandas as pd

    sheets = pd.read_excel(out, sheet_name=None, dtype=str)
    assert 'ElmTerm' in sheets
    assert 'ElmLne' in sheets
    assert len(sheets['ElmTerm']) == 2
