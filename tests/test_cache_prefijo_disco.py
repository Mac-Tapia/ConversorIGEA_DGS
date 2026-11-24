"""070:RF-94 — la caché del prefijo con los estados en disco: los mismos valores, sin la memoria del proceso.

El 2026-11-24 la guardia cortó la corrida de la 070 T28 con 0,85 GiB libres: la caché de 65 086 frases ocupaba 2,75 GiB del
proceso (2,09 GiB de estados en float16). Con ``carpeta`` los estados van a ficheros y se leen con lecturas normales.
"""
from __future__ import annotations

import pytest

torch = pytest.importorskip('torch')

from test_afinado_ordenes import BaseFalsa, _cfg, _seleccion  # noqa: E402
from test_interprete_codificador import _pequeno  # noqa: E402

from convertersmartgrid.aplicacion.asistente import afinado_ordenes as af       # noqa: E402
from convertersmartgrid.aplicacion.asistente import codificador_ordenes as co   # noqa: E402
from convertersmartgrid.aplicacion.asistente import destilacion_integral as di  # noqa: E402

CPU = torch.device('cpu')
TEXTOS = ['convierte AB101', 'calibra el alimentador CD202 para 2025', 'que hay cargado', 'une AB101 y CD202 en un dgs']


def _cache(carpeta=None, lote=2):
    return af.CachePrefijo(BaseFalsa(), 2, _seleccion(), di.evaluar_alumno, lote=lote, carpeta=carpeta)


def test_070_rf94_en_disco_los_mismos_estados_sin_guardarlos_en_la_ram(tmp_path):
    ram, disco = _cache(), _cache(tmp_path / 'cache')
    ram.asegurar(TEXTOS)
    disco.asegurar(TEXTOS)
    assert set(disco.filas) == set(ram.filas) == set(TEXTOS) and len(disco.filas) == 4
    for t in TEXTOS:
        e_ram, i_ram, tr_ram = ram.filas[t]
        e_disco, i_disco, tr_disco = disco.filas[t]
        assert e_disco.dtype == torch.float16 and torch.equal(e_disco, e_ram)       # bit a bit
        assert i_disco == i_ram and tr_disco == tr_ram
        assert disco.filas.largo(t) == len(e_ram) and disco.filas.tramos(t) == tr_ram
    # Los estados no están en la RAM del proceso: están en sus ficheros, y ocupan lo que pesan en float16.
    assert not disco.filas._ram and disco.filas._meta
    ficheros = sorted((tmp_path / 'cache').glob('tanda_*.f16'))
    assert ficheros and sum(f.stat().st_size for f in ficheros) == sum(2 * ram.filas[t][0].numel() for t in TEXTOS)


def test_070_rf94_largo_y_tramos_no_leen_el_disco(tmp_path, monkeypatch):
    disco = _cache(tmp_path / 'cache')
    disco.asegurar(TEXTOS)
    monkeypatch.setattr(af.FilasPrefijo, '__getitem__', lambda *_a: pytest.fail('leyó los estados del disco'))
    assert [disco.filas.largo(t) for t in TEXTOS] and [disco.filas.tramos(t) for t in TEXTOS]


def test_070_rf94_el_afinado_da_lo_mismo_con_la_caché_en_disco(tmp_path):
    textos = ['convierte AB101', 'que hay cargado']
    salidas = []
    for carpeta in (None, tmp_path / 'cache'):
        torch.manual_seed(0)
        cache = af.CachePrefijo(BaseFalsa(), 2, _seleccion(), di.evaluar_alumno, carpeta=carpeta)
        m = co.entrenar(_pequeno(), _cfg(), cache=cache, dispositivo=CPU)
        salidas.append(([m.predecir(t) for t in textos], {k: v.clone() for k, v in m.red.state_dict().items()}))
    (pred_ram, pesos_ram), (pred_disco, pesos_disco) = salidas
    assert pred_ram == pred_disco
    assert pesos_ram.keys() == pesos_disco.keys() and all(torch.equal(pesos_ram[k], pesos_disco[k]) for k in pesos_ram)


def test_070_rf94_soltar_la_caché_borra_sus_ficheros(tmp_path):
    disco = _cache(tmp_path / 'cache')
    disco.asegurar(TEXTOS)
    disco.asegurar([*TEXTOS, 'calibra Proyecto X'])                    # una tanda nueva, como una vuelta de la cruzada
    assert len(list((tmp_path / 'cache').glob('tanda_*.f16'))) == 2 and len(disco.filas) == 5
    disco.filas.clear()
    assert not len(disco.filas) and not (tmp_path / 'cache').exists()


def test_070_rf94_la_destilación_la_pide_en_su_corrida():
    """La corrida crea la caché en su carpeta ``cache_prefijo`` y la suelta antes de reabrir el candidato."""
    import inspect
    fuente = inspect.getsource(di.entrenar_destilacion)
    assert 'carpeta=Path(destino) / CARPETA_CACHE_PREFIJO' in fuente and 'cache.filas.clear()' in fuente
    assert di.CARPETA_CACHE_PREFIJO == 'cache_prefijo'
