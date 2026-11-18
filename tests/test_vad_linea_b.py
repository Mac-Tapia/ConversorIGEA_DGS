"""Spec 108, T30 (tramo B) — la línea del VAD desde la red y las fuentes de la empresa del espacio (108:RF-26).

El modelo rural sale de la red convertida del espacio, el dimensionamiento del sustento que declara el caso y el costo
estándar del SICODI vigente de la empresa, firmado tal como llega. Con la red, el catálogo, los rangos y el SICODI
sintéticos de las pruebas del dimensionamiento (T6) y del costo estándar (T7): ningún dato de una empresa.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.presentacion.web import services

pytest.importorskip('pandapower')

TDR = 'rcd-174-2025-os-cd'


@pytest.fixture
def web_vad(tmp_path, monkeypatch):
    import convertersmartgrid.dominio.perfil_empresa as perfil_empresa
    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setattr(perfil_empresa, 'cargar_perfil',
                        lambda *a, **k: perfil_empresa.PerfilEmpresa(nombre='Distribuidora Sintética Norte'))
    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        yield cliente, app


def _exige():
    """Lo nuevo del tramo B: su ausencia es la falla de la aserción, no un error de clave."""
    from convertersmartgrid.adaptadores.vad import linea
    assert 'modelo_rural' in linea.PASOS_LINEA, 'falta el tramo B de la línea del VAD (108 T30)'


def _esperar(cliente, trabajo: dict) -> dict:
    limite = time.monotonic() + 300
    while time.monotonic() < limite:
        r = cliente.get(f"/api/jobs/{trabajo['id']}").json()
        if r['status'] in ('done', 'failed', 'cancelled', 'parcial'):
            return r
        time.sleep(0.1)
    pytest.fail('la cola no terminó')


def _estudio(cliente) -> tuple[str, str]:
    wid = cliente.post('/api/workspaces').json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/vad/estudios', json={'grupo': 1, 'periodo': '2041-2045', 'version_tdr': TDR})
    assert r.status_code == 200, r.text
    return wid, r.json()['id']


def _empresa(raiz: Path, tmp_path: Path, *, con_red: bool = True) -> bytes:
    """Deja en el espacio la red convertida y el SICODI de la empresa, y devuelve el caso (zip) con su sustento."""
    from convertersmartgrid.aplicacion import fuentes_empresa as fe
    from test_vad_costos import CODIGO, CODIGO_SED, ESTRUCTURA, FUENTE, _sicodi
    from test_vad_dimensionamiento import NO_NORMALIZADAS, POTENCIAS, RANGOS, SECTORES, SUSTENTO, TIPOS, _entradas, _vnr

    vnr = _vnr(7, 'EMPRESA_A')
    for s in vnr.sections:
        s.conductor_code = CODIGO[s.conductor_code]
    for c in vnr.conductor_types:
        c.conductor_code = CODIGO[c.conductor_code]
    entradas = _entradas(vnr, 7)
    carpeta = tmp_path / 'sicodi'
    carpeta.mkdir(exist_ok=True)
    zip_sicodi = _sicodi(carpeta, 'linea_b')
    huella = __import__('hashlib').sha256(zip_sicodi.read_bytes()).hexdigest()
    if con_red:
        fe.guardar_red(raiz, fuente='vnr', empresa='EMPRESA_A', alimentadores=[f.feeder_id for f in vnr.feeders],
                       canonical=vnr.to_dict())
    fe.registrar(raiz, 'sicodi', zip_sicodi, nombre='sicodi.zip')
    dimensionamiento = {
        'rangos': [{'conductor': CODIGO[c], 'desde': a, 'hasta': b, 'sustento': SUSTENTO} for c, a, b in RANGOS],
        'demanda': {s: {'kw': d.kw, 'kvar': d.kvar, 'fases': d.fases, 'origen': d.origen}
                    for s, d in entradas['demanda'].items()},
        'tabla': {'potencias': {f'{s}|{t}': list(POTENCIAS) for s in SECTORES for t in TIPOS}, 'huella': huella,
                  'no_normalizadas': sorted(NO_NORMALIZADAS)},
        'sector_de': entradas['sector_de'], 'tipo_de_sed': entradas['tipo_de_sed'],
        'factor_carga': entradas['factor_carga']}
    costo = {**FUENTE, 'moneda': 'USD', 'estructura_de': {a: ESTRUCTURA for a in entradas['sector_de']},
             'codigo_sed': {f'{t}|{p}': c for (t, p), c in CODIGO_SED.items()}}
    paquete = io.BytesIO()
    with zipfile.ZipFile(paquete, 'w') as z:
        z.writestr('sistemas.json', json.dumps({'sistemas': {'S1': {'anexo2': 'a.json'}},
                                                'estudio': {'dimensionamiento': 'dim.json', 'costo': 'costo.json'}}))
        z.writestr('a.json', '{}')
        z.writestr('dim.json', json.dumps(dimensionamiento))
        z.writestr('costo.json', json.dumps(costo))
    return paquete.getvalue()


def _armar(cliente, wid, eid, caso: bytes) -> dict:
    r = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/armar', files=[('files', ('caso.zip', caso, 'application/zip'))])
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    return cliente.get(f'/api/workspaces/{wid}/vad/{eid}').json()['linea']['pasos']


def test_108_rf26_el_tramo_b_dimensiona_y_valora_la_red_de_la_empresa_del_espacio(web_vad, tmp_path):
    """108:RF-26 (T30, tramo B) — con la red convertida del espacio y el SICODI de la empresa, la línea arma el modelo
    rural, dimensiona la empresa modelo con el sustento del caso y la valora con el SICODI firmado; la tabla 2 lleva el
    costo estándar por sistema eléctrico."""
    _exige()
    cliente, app = web_vad
    wid, eid = _estudio(cliente)
    raiz = Path(app.state.store.get(wid).root)
    pasos = _armar(cliente, wid, eid, _empresa(raiz, tmp_path))
    assert pasos['modelo_rural']['estado'] == 'OK' and pasos['modelo_rural']['tramos'] > 0, pasos['modelo_rural']
    assert pasos['modelo_rural']['red']['empresa'] == 'EMPRESA_A'
    assert pasos['dimensionamiento']['estado'] in ('OK', 'INCOMPLETO') and pasos['dimensionamiento']['sed'] > 0, \
        pasos['dimensionamiento']
    assert pasos['costo_estandar']['estado'] in ('OK', 'INCOMPLETO') and pasos['costo_estandar']['elementos'] > 0, \
        pasos['costo_estandar']
    from openpyxl import load_workbook
    libro = load_workbook(raiz / 'vad' / eid / 'tablas_resultados.xlsx')
    hoja = next(h for h in libro.worksheets if str(h['A1'].value or '').startswith('Tabla 2.'))
    assert any(str(c.value or '').startswith('EMPRESA_A') for c in hoja['A']), 'la tabla 2 lleva el sistema eléctrico'


def test_108_rf26_sin_la_red_del_espacio_el_tramo_b_lo_dice_y_no_inventa(web_vad, tmp_path):
    """108:RF-26 (T30, tramo B) — sin la red convertida del espacio, el modelo rural, el dimensionamiento y el costo
    quedan «SIN_ENTRADA» con su motivo; los demás pasos siguen."""
    _exige()
    cliente, app = web_vad
    wid, eid = _estudio(cliente)
    raiz = Path(app.state.store.get(wid).root)
    pasos = _armar(cliente, wid, eid, _empresa(raiz, tmp_path, con_red=False))
    for p in ('modelo_rural', 'dimensionamiento', 'costo_estandar'):
        assert pasos[p]['estado'] == 'SIN_ENTRADA' and pasos[p]['motivo'], pasos[p]
    assert 'red convertida' in pasos['modelo_rural']['motivo']
    assert pasos['tablas']['estado'] == 'OK' and pasos['informes']['estado'] == 'OK'
