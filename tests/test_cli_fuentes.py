"""El CLI lee con los mismos adaptadores que la web (spec 001, T6).

Antes tenía su propia lectura: no admitía VNR-GIS y no pasaba los alias al catálogo
(diagnóstico B1). Todo con datos sintéticos; la vía Access se prueba con un lector
falso porque la real necesita Windows, el driver de Access y una base de la empresa.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic_export import ExportSpec, write_export


def _args(*argv: str):
    from igea_dgs.cli import _parser

    return _parser().parse_args(list(argv))


def _vnr_package(tmp_path: Path, companies: tuple[str, ...]) -> Path:
    import zipfile

    features = [{
        'type': 'Feature',
        'properties': {'CODEMP': company, 'ANIO': 2031, 'CODTRAMOMT': f'S{i}',
                       'CODSALIDAMT': f'F-{i}', 'CODNORMA': 'COND-1', 'LONGITUD': 100},
        'geometry': {'type': 'LineString',
                     'coordinates': [[-75 + i / 100, -14], [-75 + i / 100 + .001, -14]]},
    } for i, company in enumerate(companies, 1)]
    archive = tmp_path / 'paquete-vnr.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('sections.geojson', json.dumps(
            {'type': 'FeatureCollection', 'features': features}))
    return archive


@pytest.mark.parametrize('layout', ['reducido', 'completo'])
def test_txt_igual_que_el_lector_directo(tmp_path, layout):
    """001:RF-1 — las dos disposiciones de export, por el adaptador común."""
    from igea_dgs.cli import load_dataset
    from igea_dgs.dataset import CymdistDataset

    red, loads, equip = write_export(ExportSpec(feeders=3, layout=layout), tmp_path / 'e')
    ds = load_dataset(_args('list', '--red', str(red), '--loads', str(loads),
                            '--equipment', str(equip)))
    esperado = CymdistDataset.from_files(red, loads, equip)
    assert ds.feeder_ids() == esperado.feeder_ids()
    assert len(ds.sections) == len(esperado.sections)
    assert len(ds.nodes) == len(esperado.nodes)


def test_convert_txt_de_punta_a_punta(tmp_path):
    """001:RF-1 — ``igea-dgs convert`` sigue publicando el DGS con la lectura nueva."""
    from igea_dgs.cli import main

    red, loads, equip = write_export(ExportSpec(feeders=2), tmp_path / 'e')
    out = tmp_path / 'salida'
    rc = main(['convert', '--red', str(red), '--loads', str(loads), '--equipment',
               str(equip), '--all', '--out-dir', str(out), '--no-geography'])
    assert rc == 0
    assert len(list(out.glob('*.dgs'))) == 2


def test_los_alias_llegan_al_catalogo(tmp_path, monkeypatch):
    """001:RF-3 — antes el CLI diagnosticaba el catálogo sin los alias del usuario."""
    import igea_dgs.catalog_merge as catalog_merge

    vistos = {}
    original = catalog_merge.diagnosticar

    def espia(dataset, *, aliases=None):
        vistos['aliases'] = aliases
        return original(dataset, aliases=aliases)

    monkeypatch.setattr(catalog_merge, 'diagnosticar', espia)
    red, loads, equip = write_export(ExportSpec(feeders=1), tmp_path / 'e')
    alias = tmp_path / 'alias.json'
    alias.write_text(json.dumps({'CABLE_X': 'CABLE_Y'}), encoding='utf-8')

    from igea_dgs.cli import load_dataset

    load_dataset(_args('convert', '--red', str(red), '--loads', str(loads), '--equipment',
                       str(equip), '--all', '--out-dir', str(tmp_path / 'o'),
                       '--aliases', str(alias)))
    assert vistos['aliases'] == {'CABLE_X': 'CABLE_Y'}


def test_varios_equipment_extra_conservan_su_orden(tmp_path, monkeypatch):
    """001:RF-1 — el primero que se indica rellena primero, como antes."""
    import igea_dgs.catalog_merge as catalog_merge

    vistos = {}
    original = catalog_merge.completar

    def espia(dataset, extras, *, aliases=None):
        vistos['extras'] = [Path(p).name for p in extras]
        return original(dataset, extras, aliases=aliases)

    monkeypatch.setattr(catalog_merge, 'completar', espia)
    red, loads, equip = write_export(ExportSpec(feeders=1), tmp_path / 'e')
    extras = []
    for nombre in ('b_segundo.txt', 'a_primero.txt', 'c_tercero.txt'):
        extras.append(tmp_path / nombre)
        extras[-1].write_bytes(equip.read_bytes())

    from igea_dgs.cli import load_dataset

    argv = ['list', '--red', str(red), '--loads', str(loads), '--equipment', str(equip)]
    for extra in extras:
        argv += ['--equipment-extra', str(extra)]
    load_dataset(_args(*argv))
    assert vistos['extras'] == ['b_segundo.txt', 'a_primero.txt', 'c_tercero.txt']


def test_vnr_por_el_cli_igual_que_por_la_web(tmp_path):
    """001:RF-2 — mismo adaptador y mismo resultado que la web."""
    pytest.importorskip('fastapi')
    from igea_dgs.cli import load_dataset
    from igea_dgs.sources import adapter_for
    from igea_dgs.web.source_runs import create_source_run
    from igea_dgs.web.workspace import Workspace

    paquete = _vnr_package(tmp_path, ('EMPRESA_A',))
    ds_cli = load_dataset(_args('list', '--vnr-package', str(paquete)))

    ws = Workspace(id='vnr-cli', root=tmp_path / 'ws')
    ws.options['input_mode'] = 'vnr'
    ws.set_input('vnr_package', paquete, origin='server')
    ds_web = adapter_for('vnr').load(create_source_run(ws), aliases={}).dataset

    assert ds_cli.feeder_ids() == ds_web.feeder_ids()
    assert len(ds_cli.sections) == len(ds_web.sections)


def test_vnr_con_varias_empresas_exige_elegir(tmp_path):
    """001:RF-2 — un paquete con dos empresas no se lee sin --company."""
    from igea_dgs.cli import load_dataset

    paquete = _vnr_package(tmp_path, ('EMPRESA_A', 'EMPRESA_B'))
    with pytest.raises(SystemExit) as info:
        load_dataset(_args('list', '--vnr-package', str(paquete)))
    assert 'VNR-GIS' in str(info.value)
    ds = load_dataset(_args('list', '--vnr-package', str(paquete), '--company', 'EMPRESA_B'))
    assert ds.feeder_ids()


def test_mdb_por_el_adaptador_con_ano_de_carga(tmp_path, monkeypatch):
    """001:RF-1 — la vía Access pasa por el adaptador y conserva --load-year."""
    mdb = tmp_path / 'red.mdb'
    mdb.write_bytes(b'base de prueba')
    esperado = object()
    vistos = {}

    def lector_falso(path, **kwargs):
        vistos.update(path=Path(path).name, **kwargs)
        return esperado

    monkeypatch.setattr('igea_dgs.access.read_access_dataset', lector_falso)
    from igea_dgs.cli import load_dataset

    ds = load_dataset(_args('list', '--mdb', str(mdb), '--load-year', '2025'))
    assert ds is esperado
    assert vistos == {'path': 'red.mdb', 'equipment_db': None, 'networks': None,
                      'load_year': 2025}


@pytest.mark.parametrize('argv, mensaje', [
    (['--red', 'r.txt', '--vnr-package', 'p.zip'], 'UNA alternativa'),
    (['--mdb', 'b.mdb', '--vnr-package', 'p.zip'], 'UNA alternativa'),
    ([], 'Falta la entrada'),
    (['--red', 'r.txt'], 'tres ficheros'),
    (['--vnr-package', 'no_existe.zip'], 'no encontrados'),
])
def test_errores_de_uso(tmp_path, monkeypatch, argv, mensaje):
    """001:RF-1 — los mismos mensajes de uso para las tres alternativas."""
    monkeypatch.chdir(tmp_path)
    from igea_dgs.cli import load_dataset

    with pytest.raises(SystemExit, match=mensaje):
        load_dataset(_args('list', *argv))
