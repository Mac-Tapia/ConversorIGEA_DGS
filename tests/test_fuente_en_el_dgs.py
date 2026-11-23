"""Spec 056: la cabecera del DGS dice de qué fuente viene; los TXT no cambian (RF-3, RF-6)."""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from convertersmartgrid.adaptadores.dataset import CymdistDataset
from convertersmartgrid.adaptadores.dgs import _ORIGEN_DGS
from convertersmartgrid.dominio.model import FeederModel


def test_la_cabecera_dice_su_fuente_y_ninguna_dice_cymdist():
    """056:RF-3, 056:RF-8 — la cabecera del DGS de los TXT dice «TXT»: los TXT no los exporta CYMDIST."""
    assert _ORIGEN_DGS['txt'] == 'TXT'
    for fuente in ('txt', 'mdb', 'vnr'):
        assert 'CYMDIST' not in _ORIGEN_DGS[fuente]


def test_el_dataset_y_el_modelo_traen_su_fuente_con_txt_por_defecto():
    """056:RF-3 — un dataset o un modelo sin fuente declarada es un TXT, como hasta ahora."""
    assert {f.name: f.default for f in fields(CymdistDataset)}['fuente'] == 'txt'
    assert {f.name: f.default for f in fields(FeederModel)}['fuente'] == 'txt'


@pytest.mark.parametrize('modulo, fuente', [('convertersmartgrid/adaptadores/access.py', 'mdb'),
                                            ('convertersmartgrid/adaptadores/entrada/vnr/application/cymdist_bridge.py', 'vnr')])
def test_cada_lector_declara_su_fuente(modulo, fuente):
    """056:RF-6 — el lector de Access y el puente de VNR-GIS no dejan la fuente en TXT."""
    raiz = Path(__file__).resolve().parent.parent / 'src'
    assert f"fuente='{fuente}'" in (raiz / modulo).read_text(encoding='utf-8')
