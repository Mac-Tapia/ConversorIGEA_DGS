"""El vocabulario del asistente nombra los alimentadores como el operador (026:RF-6).

Prueba del auditor (2026-11-14): «convierte el PA217» respondía que faltaban alimentadores, porque el vocabulario
era el NetworkID de la fuente («NET_2030_179_PA217») y no el código del alimentador. Ahora es el código corto,
el mismo de la tabla de la web y de las demás rutas, y una orden con el NetworkID resuelve al mismo alimentador.
Con las dos disposiciones del TXT, cada convención de NetworkID y las filas de inventario de una .mdb y de un
paquete VNR-GIS, con alimentadores sorteados: ningún tamaño ni nombre fijo.
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.asistente.interprete import Interpretacion
from convertersmartgrid.asistente.plan import resolver
from convertersmartgrid.inventory import build_dataset_inventory
from convertersmartgrid.web import services
from synthetic_export import ExportSpec, load_export

SEMILLA = random.randrange(10**6)


def _espacio(filas: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(inventory={'feeders': filas}, conversions={}, feeder_readiness={}, active_run_id=None,
                           loaded_run_id=None, loaded_source_mode=None, loaded_source_fingerprint=None)


def _vocabulario(monkeypatch, filas: list[dict]) -> list[str]:
    monkeypatch.setattr(services, 'pf_proyectos_guardados', lambda _ws: {'projects': []})
    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: None)
    return services.asistente_vocabulario(_espacio(filas))['alimentadores']


def _plan(texto: str, valores: list[str], vocab: list[str]):
    datos = {'alimentadores': [{'valor': v} for v in valores]}
    return resolver(Interpretacion(texto, 'convertir', 1.0, 'transformer', datos), {'alimentadores': vocab})


def _comprobar(monkeypatch, filas: list[dict]) -> None:
    vocab = _vocabulario(monkeypatch, filas)
    assert vocab == [f['feeder'] for f in filas], f'semilla {SEMILLA}'
    fila = random.Random(SEMILLA).choice(filas)
    corto, red = fila['feeder'], fila['network_id']
    for valor in (corto, red, corto.lower()):
        plan = _plan(f'convierte el {valor}', [valor], vocab)
        assert plan.datos.get('alimentadores') == [corto] and not plan.dudas, (valor, plan.faltan, plan.dudas, SEMILLA)
    # Sin marcar nada, el código corto se toma del texto.
    assert _plan(f'convierte el {corto}', [], vocab).datos.get('alimentadores') == [corto], SEMILLA
    assert _plan('convierte todos los alimentadores', ['todos'], vocab).datos['alimentadores'] == vocab


@pytest.mark.parametrize('layout', ['reducido', 'completo'])
@pytest.mark.parametrize('naming', ['net', 'dash', 'dotted', 'plain'])
def test_txt_de_las_dos_disposiciones(tmp_path, monkeypatch, layout, naming):
    """026:RF-6 — con el TXT de cualquier disposición y convención de NetworkID, el alimentador se nombra por su
    código corto, por su NetworkID o en minúsculas, y resuelve al mismo."""
    rnd = random.Random(f'{SEMILLA}-{layout}-{naming}')
    spec = ExportSpec(feeders=rnd.randint(2, 9), naming=naming, layout=layout, seed=rnd.randrange(10**6))
    filas = build_dataset_inventory(load_export(spec, tmp_path))['feeders']
    _comprobar(monkeypatch, filas)


@pytest.mark.parametrize('fuente', ['mdb', 'vnr'])
def test_filas_de_mdb_y_vnr(monkeypatch, fuente):
    """026:RF-6 — una .mdb trae el NetworkID de CYMDIST y un VNR-GIS el código operativo como NetworkID
    (``cymdist_bridge``): en los dos el vocabulario es el código del alimentador."""
    rnd = random.Random(f'{SEMILLA}-{fuente}')
    codigos = sorted({f'{rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")}{rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")}{rnd.randint(100, 399)}'
                      for _ in range(rnd.randint(2, 9))})
    filas = [{'feeder': c, 'network_id': (f'NET_{rnd.randint(2000, 2099)}_{rnd.randint(1, 999)}_{c}' if fuente == 'mdb' else c)}
             for c in codigos]
    _comprobar(monkeypatch, filas)


def test_un_codigo_de_dos_redes_se_pregunta(monkeypatch):
    """026:RF-6 — el mismo código en dos redes (dos SET, o repetido en la fuente) no se resuelve con la primera:
    el plan pregunta cuál y nombra las dos; con el nombre de la red, resuelve a esa."""
    from convertersmartgrid.web.reconstruction_service import resolve_selection

    rnd = random.Random(f'{SEMILLA}-repetido')
    codigo = f'AB{rnd.randint(100, 399)}'
    redes = [f'NET_2030_{rnd.randint(1, 499)}_{codigo}', f'NET_2031_{rnd.randint(500, 999)}_{codigo}']
    filas = [{'feeder': codigo, 'network_id': r} for r in redes] + [{'feeder': 'CD410', 'network_id': 'NET_2030_7_CD410'}]
    vocab = _vocabulario(monkeypatch, filas)
    assert vocab == [*redes, 'CD410'], SEMILLA
    for valores in ([codigo], []):
        plan = _plan(f'convierte el {codigo}', valores, vocab)
        assert 'alimentadores' not in plan.datos, (valores, plan.datos)
        assert any('cuál' in f and all(r in f for r in redes) for f in plan.faltan), plan.faltan
    plan = _plan(f'convierte el {redes[1]}', [redes[1]], vocab)
    assert plan.datos['alimentadores'] == [redes[1]] and not plan.faltan, plan.faltan
    # La ruta, con el código solo, toma una de las dos sin decirlo: por eso pregunta el plan.
    ws = _espacio(filas)
    assert len(resolve_selection(ws, [codigo], all_feeders=False)[1]) == 1
    assert resolve_selection(ws, [redes[1]], all_feeders=False)[1] == [redes[1]]


def test_de_punta_a_punta_por_la_web(tmp_path, monkeypatch):
    """026:RF-6 — con la fuente cargada por la web, «convierte el <alimentador sorteado>» da el plan listo con su
    paso, y confirmado, la ruta real convierte ese alimentador del inventario."""
    import time

    from fastapi.testclient import TestClient

    from convertersmartgrid.web.app import create_app
    from synthetic_export import CRS_SINTETICO, write_export

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    rnd = random.Random(f'{SEMILLA}-web')
    red, carga, equipo = write_export(ExportSpec(feeders=rnd.randint(2, 6), seed=rnd.randrange(10**6)), tmp_path / 'export')

    def esperar(cliente, trabajo):
        limite = time.monotonic() + 90
        while time.monotonic() < limite:
            r = cliente.get(f'/api/jobs/{trabajo}').json()
            if r['status'] in ('done', 'parcial', 'failed', 'cancelled'):
                return r
            time.sleep(0.05)
        pytest.fail('la cola no terminó')

    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        wid = cliente.post('/api/workspaces').json()['id']
        for slot, ruta in (('red', red), ('loads', carga), ('equipment', equipo)):
            with ruta.open('rb') as fh:
                assert cliente.post(f'/api/workspaces/{wid}/inputs/{slot}', files={'file': (ruta.name, fh)}).status_code == 200
        cliente.put(f'/api/workspaces/{wid}/options', json={'include_geography': False, 'source_crs': CRS_SINTETICO})
        assert esperar(cliente, cliente.post(f'/api/workspaces/{wid}/load').json()['id'])['status'] == 'done'
        ws = app.state.store.get(wid)
        fila = rnd.choice(ws.inventory['feeders'])

        class Modelo:
            tareas = ('convertir',)

            def predecir(self, texto):
                return {'tarea': 'convertir', 'confianza': 1.0, 'datos': {'alimentadores': [{'valor': fila['feeder']}]}}

        monkeypatch.setattr(services, '_asistente_modelos', lambda: (Modelo(), None))
        orden = esperar(cliente, cliente.post(f'/api/workspaces/{wid}/asistente/orden',
                                              json={'texto': f"convierte el {fila['feeder']}"}).json()['id'])
        plan = orden['result']['plan']
        assert plan['listo'] and plan['datos']['alimentadores'] == [fila['feeder']], (plan['faltan'], plan['dudas'])
        assert plan['pasos'] == ['convertir']
        fin = esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
        assert fin['status'] == 'done', fin.get('error')
        assert set(ws.conversions) == {fila['network_id']}, (sorted(ws.conversions), SEMILLA)


MDB, VNR_BAK = (os.environ.get(v, '').strip() for v in ('CSG_MDB', 'CSG_VNR_BAK'))


def _comprobar_real(monkeypatch, filas: list[dict]) -> None:
    vocab = _vocabulario(monkeypatch, filas)
    unicos = [f for f in filas if f['feeder'] in vocab]
    assert unicos, 'la fuente no tiene ningún código único'
    for fila in random.Random(SEMILLA).sample(unicos, min(5, len(unicos))):
        for valor in (fila['feeder'], fila['network_id']):
            plan = _plan(f'convierte el {valor}', [valor], vocab)
            assert plan.datos.get('alimentadores') == [fila['feeder']], (valor, plan.faltan, plan.dudas, SEMILLA)


@pytest.mark.skipif(not MDB, reason='Defina CSG_MDB con una base de red CYMDIST (.mdb)')
def test_mdb_real(monkeypatch):
    """026:RF-6 — con una .mdb real, el vocabulario reconoce los códigos de sus alimentadores."""
    pytest.importorskip('pyodbc')
    from convertersmartgrid.access import read_access_dataset

    dataset = read_access_dataset(MDB, equipment_db=os.environ.get('CSG_EQUIPMENT_MDB') or None)
    _comprobar_real(monkeypatch, build_dataset_inventory(dataset)['feeders'])


@pytest.mark.skipif(not VNR_BAK, reason='Defina CSG_VNR_BAK con una copia de VNR-GIS y SQL Server en marcha')
def test_vnr_real(monkeypatch):
    """026:RF-6 — con una copia real de VNR-GIS, el vocabulario reconoce los códigos operativos de sus alimentadores."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    modelo, _avisos, _alcance = sv.cargar_copia(VNR_BAK)
    dataset = canonical_to_cymdist(modelo, source_path=Path(VNR_BAK)).dataset
    _comprobar_real(monkeypatch, build_dataset_inventory(dataset)['feeders'])
