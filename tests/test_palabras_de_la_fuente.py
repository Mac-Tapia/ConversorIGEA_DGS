"""Spec 056: cada fuente con sus propias palabras (RF-4, RF-5, RF-6).

El 2026-11-01 una conversión de VNR-GIS avisaba «0 conservaron Length del TXT», «CYMDIST B1/B0» o
«revise el export CYMDIST», y el operador creyó que su VNR-GIS se había cargado como TXT.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from convertersmartgrid.model import PALABRAS_POR_FUENTE, palabras_de

PROHIBIDAS = ('IGEA', 'CYMDIST', 'TXT', 'BD_Equipo', 'RED export')


@pytest.mark.parametrize('fuente', ['mdb', 'vnr'])
def test_las_palabras_de_otra_fuente_no_nombran_cymdist(fuente):
    """056:RF-4 — las palabras de una .mdb o de un VNR-GIS no dicen TXT, CYMDIST ni BD_Equipo."""
    for clave, texto in palabras_de(fuente).items():
        assert not any(p in texto for p in PROHIBIDAS), (fuente, clave, texto)
    assert set(palabras_de(fuente)) == set(PALABRAS_POR_FUENTE['txt'])


def test_el_txt_conserva_sus_palabras():
    """056:RF-4 — un TXT, o una fuente sin declarar, sigue con las palabras de siempre."""
    assert palabras_de(None) is palabras_de('txt') is palabras_de('TXT')
    assert palabras_de('txt')['longitud'] == 'Length del TXT'
    assert palabras_de('txt')['export'] == 'export CYMDIST'


def test_la_web_solo_nombra_cymdist_en_la_entrada_de_los_txt():
    """056:RF-5 — en la interfaz, CYMDIST solo en la opción de entrada de los TXT (o de la .mdb)."""
    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    lineas = [(f, ln) for f in raiz.rglob('*.ts*') for ln in f.read_text(encoding='utf-8').splitlines()
              if 'CYMDIST' in ln]
    assert lineas and all("setMode('txt')" in ln or "setMode('mdb')" in ln for _f, ln in lineas), lineas


def _aceptacion():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        'aceptacion_056', Path(__file__).resolve().parents[1] / 'tools' / 'powerfactory_acceptance.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('origen, sigla', [('CYMDIST', 'TXT'), ('Access (.mdb)', 'MDB'), ('VNR-GIS', 'VNR')])
def test_el_proyecto_nuevo_lleva_su_fuente(tmp_path, origen, sigla):
    """056:RF-1 — el proyecto nuevo de DIgSILENT dice su fuente, leída de la cabecera del DGS que se importa,
    sin IGEA ni CYMDIST."""
    mod = _aceptacion()
    dgs = tmp_path / 'NJA202.dgs'
    dgs.write_text('*' * 80 + f'\n*\n* {origen} to DIgSILENT DGS converter\n* Project: NJA202\n', encoding='utf-8')
    fuente = mod.fuente_del_dgs(dgs)
    nombre = mod._generated_project_name('20261101-063543', dgs.stem, fuente)
    assert fuente == sigla and nombre == f'20261101-063543_CSG_{sigla}_NJA202'
    assert 'IGEA' not in nombre and 'CYMDIST' not in nombre
    largo = mod._generated_project_name('20261101-063543', 'SISTEMA_ELECTRICO_MUY_LARGO', fuente)
    assert largo.startswith(f'20261101-063543_CSG_{sigla}_') and len(largo) <= 40


def test_los_proyectos_anteriores_siguen_valiendo(tmp_path):
    """056:RF-2 — un DGS sin fuente en la cabecera da el nombre de antes, y ningún guion reconoce los
    proyectos por su nombre: los ya importados siguen siendo suyos por su vínculo."""
    mod = _aceptacion()
    viejo = tmp_path / 'W12882.dgs'
    viejo.write_text('* algo\n', encoding='utf-8')
    assert mod.fuente_del_dgs(viejo) is None and mod.fuente_del_dgs(tmp_path / 'no.dgs') is None
    assert mod._generated_project_name('20261101-063543', 'W12882', None) == '20261101-063543_CSG_W12882'
    raiz = Path(__file__).resolve().parents[1]
    for carpeta in ('src', 'tools'):
        for f in (raiz / carpeta).rglob('*.py'):
            texto = f.read_text(encoding='utf-8', errors='replace')
            assert "startswith('_CSG_" not in texto and "_CSG_' in" not in texto, f


def test_un_vnr_gis_convertido_no_deja_palabras_de_cymdist(tmp_path):
    """056:RF-6 — un VNR-GIS sintético convertido de punta a punta: ninguna salida dice IGEA, CYMDIST,
    TXT, BD_Equipo ni RED export."""
    from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
    from vnr_etl.connectors import sqlserver_vnr as sv

    from convertersmartgrid.batch import convert_selection
    from test_vnr_sqlserver import _datos, _tablas

    datos, _motor = _datos(_tablas())
    modelo, _avisos = sv.modelo_canonico(datos)
    dataset = canonical_to_cymdist(modelo, source_path=tmp_path / 'copia').dataset
    assert dataset.fuente == 'vnr'
    salida = tmp_path / 'out'
    convert_selection(dataset, None, salida, all_feeders=True, include_geography=False, strict=False)
    ficheros = [f for f in salida.rglob('*') if f.is_file()]
    assert any(f.suffix == '.dgs' for f in ficheros), ficheros
    halladas = {}
    for f in ficheros:
        texto = f.read_text(encoding='utf-8', errors='replace')
        for p in PROHIBIDAS:
            if p in texto:
                linea = next(ln for ln in texto.splitlines() if p in ln)
                halladas.setdefault(f.name, []).append(f'{p}: {linea[:160]}')
    assert not halladas, halladas
