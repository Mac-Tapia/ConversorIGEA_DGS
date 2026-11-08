"""Spec 056: la cabecera del DGS dice de qué fuente viene; los TXT no cambian (RF-3, RF-6)."""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from convertersmartgrid.dataset import CymdistDataset
from convertersmartgrid.dgs import _ORIGEN_DGS
from convertersmartgrid.model import FeederModel


def test_el_txt_sigue_diciendo_cymdist_y_las_otras_fuentes_no():
    """056:RF-3 — CYMDIST solo para su TXT, que así da el mismo DGS que antes."""
    assert _ORIGEN_DGS['txt'] == 'CYMDIST'
    for fuente in ('mdb', 'vnr'):
        assert 'CYMDIST' not in _ORIGEN_DGS[fuente]


def test_el_dataset_y_el_modelo_traen_su_fuente_con_txt_por_defecto():
    """056:RF-3 — un dataset o un modelo sin fuente declarada es un TXT, como hasta ahora."""
    assert {f.name: f.default for f in fields(CymdistDataset)}['fuente'] == 'txt'
    assert {f.name: f.default for f in fields(FeederModel)}['fuente'] == 'txt'


@pytest.mark.parametrize('modulo, fuente', [('convertersmartgrid/access.py', 'mdb'),
                                            ('convertersmartgrid/adaptadores/entrada/vnr/application/cymdist_bridge.py', 'vnr')])
def test_cada_lector_declara_su_fuente(modulo, fuente):
    """056:RF-6 — el lector de Access y el puente de VNR-GIS no dejan la fuente en TXT."""
    raiz = Path(__file__).resolve().parent.parent / 'src'
    assert f"fuente='{fuente}'" in (raiz / modulo).read_text(encoding='utf-8')
