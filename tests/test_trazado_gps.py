"""Spec 010 — cada línea lleva en el DGS su trazado GPS real.

Antes el DGS dejaba ``GPScoords`` vacío y PowerFactory dibujaba cada línea, en la vista
geográfica, como una recta entre sus barras (red unida NA203 + NA205, 2026-10-10). Se
usa el export sintético sorteado, en las dos disposiciones, con varios puntos
intermedios por tramo.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from synthetic_export import ExportSpec, load_export

from igea_dgs.batch import convert_group, convert_selection
from igea_dgs.validate import parse_dgs

pytest.importorskip('pyproj')

LAYOUTS = ('reducido', 'completo')
SEMILLAS = (7, 2026)


def _spec(layout: str, seed: int, **kw) -> ExportSpec:
    return ExportSpec(feeders=3, sections_per_feeder=6, loads_per_feeder=2,
                      intermediate_per_section=3, layout=layout, seed=seed, **kw)


def _convertir(tmp_path: Path, layout: str, seed: int, *, geo: bool = True, **kw) -> Path:
    ds = load_export(_spec(layout, seed), tmp_path / f'export_{layout}_{seed}')
    out = tmp_path / f'out_{layout}_{seed}_{geo}'
    man = convert_selection(ds, None, out, all_feeders=True, aliases={}, strict=True,
                            include_geography=geo, source_crs='EPSG:32718',
                            target_crs='EPSG:4326', **kw)
    assert man['summary']['failed'] == 0, man['summary']
    return out


def _trazados(dgs: Path) -> dict[str, list[tuple[float, float]]]:
    """Trazado de cada línea, por ``loc_name``, leído de la tabla ``Matrix``."""
    tablas = parse_dgs(dgs)
    matriz: dict[str, dict[int, dict[int, float]]] = {}
    for fila in tablas.get('Matrix', {}).get('rows_dict', []):
        matriz.setdefault(fila['FID'], {}).setdefault(int(fila['MatRow']), {})[
            int(fila['MatColumn'])] = float(fila['Val'])
    out = {}
    for fila in tablas['ElmLne']['rows_dict']:
        puntos = matriz.get(fila['GPScoords'], {})
        out[fila['loc_name']] = [(puntos[i][0], puntos[i][1]) for i in sorted(puntos)]
    return out


def _geografia(path: Path) -> dict[str, list[tuple[float, float]]]:
    lines = json.loads(path.read_text(encoding='utf-8'))['lines']
    return {sid: [(p['lat'], p['lon']) for p in g['path']] for sid, g in lines.items()}


def _iguales(a, b) -> bool:
    return len(a) == len(b) and all(
        math.isclose(x, y, rel_tol=0.0, abs_tol=1e-9) for p, q in zip(a, b) for x, y in zip(p, q))


@pytest.mark.parametrize('seed', SEMILLAS)
@pytest.mark.parametrize('layout', LAYOUTS)
def test_cada_linea_lleva_su_trazado_punto_a_punto(tmp_path, layout, seed):
    """010:RF-1 — inicio, intermedios del origen en su orden y final, en cada línea."""
    out = _convertir(tmp_path, layout, seed)
    largos = []
    for dgs in sorted(out.glob('*.dgs')):
        trazados = _trazados(dgs)
        geografia = _geografia(dgs.with_name(f'{dgs.stem}_geography.json'))
        assert set(trazados) == set(geografia), dgs.name
        for sid, puntos in geografia.items():
            assert _iguales(trazados[sid], puntos), (dgs.name, sid)
        largos += [len(p) for p in trazados.values()]
    # Hay intermedios de verdad en la entrega (el sorteo puede dejar sin ellos a un
    # alimentador suelto) y tramos de dos puntos.
    assert max(largos) > 2 and min(largos) >= 2, largos


@pytest.mark.parametrize('layout', LAYOUTS)
def test_los_extremos_son_el_gps_de_las_barras(tmp_path, layout):
    """010:RF-2 — primer y último punto con el mismo valor que el GPS de su barra."""
    out = _convertir(tmp_path, layout, SEMILLAS[0])
    for dgs in sorted(out.glob('*.dgs')):
        tablas = parse_dgs(dgs)
        fid_barra = {f['FID']: f for f in tablas['ElmTerm']['rows_dict']}
        cub = {f['FID']: f for f in tablas['StaCubic']['rows_dict']}
        lineas = {f['FID']: f['GPScoords'] for f in tablas['ElmLne']['rows_dict']}
        crudo: dict[str, dict[tuple[int, int], str]] = {}
        for f in tablas['Matrix']['rows_dict']:
            crudo.setdefault(f['FID'], {})[(int(f['MatRow']), int(f['MatColumn']))] = f['Val']
        comprobadas = 0
        for c in cub.values():
            matriz = lineas.get(c['obj_id'])
            if matriz is None:
                continue
            filas = crudo[matriz]
            n = max(r for r, _ in filas)
            fila = 0 if c['obj_bus'] == '0' else n
            barra = fid_barra[c['fold_id']]
            # Igualdad de texto: el mismo número escrito con el mismo formato.
            assert (filas[(fila, 0)], filas[(fila, 1)]) == (barra['GPSlat'], barra['GPSlon'])
            comprobadas += 1
        assert comprobadas == 2 * len(lineas), dgs.name


@pytest.mark.parametrize('layout', LAYOUTS)
def test_sin_georreferenciacion_no_hay_trazado(tmp_path, layout):
    """010:RF-3 — líneas sin trazado y sin tabla Matrix."""
    out = _convertir(tmp_path, layout, SEMILLAS[0], geo=False)
    for dgs in sorted(out.glob('*.dgs')):
        tablas = parse_dgs(dgs)
        assert 'Matrix' not in tablas, dgs.name
        assert all(f['GPScoords'] == '' for f in tablas['ElmLne']['rows_dict']), dgs.name


@pytest.mark.parametrize('layout', LAYOUTS)
def test_la_red_unida_lleva_el_trazado_de_todas_sus_lineas(tmp_path, layout):
    """010:RF-4 — igual que en un alimentador suelto."""
    ds = load_export(_spec(layout, SEMILLAS[1]), tmp_path / 'export')
    nombres = [n for n in ds.feeder_ids() if ds.feeders.get(n)]
    man = convert_group(ds, nombres, tmp_path / 'out', name='RED', aliases={},
                        source_crs='EPSG:32718', target_crs='EPSG:4326')
    assert man['status'] == 'ok', man.get('error')
    trazados = _trazados(tmp_path / 'out' / 'RED.dgs')
    geografia = _geografia(tmp_path / 'out' / 'RED_geography.json')
    assert trazados and set(trazados) == set(geografia)
    for sid, puntos in geografia.items():
        assert _iguales(trazados[sid], puntos), sid


def test_el_validador_detecta_un_trazado_alterado(tmp_path):
    """010:RF-5 — un punto movido en la tabla Matrix es un error de validación."""
    from igea_dgs.dgs import write_dgs
    from igea_dgs.geography import build_geography
    from igea_dgs.model import build_feeder_model
    from igea_dgs.validate import validate_dgs

    ds = load_export(_spec('reducido', SEMILLAS[0]), tmp_path / 'export')
    nid = next(n for n in ds.feeder_ids() if ds.feeders.get(n))
    model = build_feeder_model(ds, nid, strict=True)
    geo = build_geography(ds, model, source_crs='EPSG:32718')
    dgs = tmp_path / 'red.dgs'
    write_dgs(model, dgs, geography=geo)
    assert validate_dgs(model, dgs, geography=geo)['errors_total'] == 0

    lineas = dgs.read_text(encoding='utf-8').split('\n')
    i = lineas.index(next(l for l in lineas if l.startswith('$$Matrix'))) + 3
    campos = lineas[i].split(';')
    campos[-1] = format(float(campos[-1]) + 0.001, '.12g')
    lineas[i] = ';'.join(campos)
    dgs.write_text('\n'.join(lineas), encoding='utf-8')
    errores = validate_dgs(model, dgs, geography=geo)['geographic_errors']
    assert any('trazado GPS' in e for e in errores), errores


def test_el_trazado_no_rompe_el_determinismo_en_paralelo(tmp_path):
    """010 — DGS idéntico byte a byte con un proceso y con dos."""
    huellas = []
    for workers in (1, 2):
        out = _convertir(tmp_path / str(workers), 'reducido', SEMILLAS[1], workers=workers)
        huellas.append({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(out.glob('*.dgs'))})
    assert huellas[0] == huellas[1]
