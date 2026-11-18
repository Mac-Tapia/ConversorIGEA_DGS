"""Spec 108, T30 (tramo A) — la línea del VAD de punta a punta desde el caso, por la web (108:RF-26).

Tras la empresa modelo, el armado encadena resultados, PIDE, calidad, explotación, tablas e informes, cada paso con su
estado y su hueco nombrado si el caso no trae su entrada; el Informe Definitivo usa lo que la línea deja. Con el registro
del TdR real y valores sintéticos sacados de sus propias fórmulas: ningún dato de una empresa.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.web import services

RAIZ = Path(__file__).resolve().parents[1]
TDR = 'rcd-174-2025-os-cd'


@pytest.fixture
def web_vad(tmp_path, monkeypatch):
    import convertersmartgrid.perfil_empresa as perfil_empresa
    from convertersmartgrid.web.app import create_app

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
    """Lo nuevo de la T30: su ausencia es la falla de la aserción, no un error al importar."""
    import importlib.util
    assert importlib.util.find_spec('convertersmartgrid.vad.linea') is not None, 'falta vad/linea.py (108 T30)'


def _esperar(cliente, trabajo: dict) -> dict:
    limite = time.monotonic() + 180
    while time.monotonic() < limite:
        r = cliente.get(f"/api/jobs/{trabajo['id']}").json()
        if r['status'] in ('done', 'failed', 'cancelled', 'parcial'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def _resultados_sinteticos(registro) -> dict:
    """Un sistema del primer ámbito del registro, con cada variable de sus fórmulas a 2 (sin dividir por cero)."""
    from convertersmartgrid.vad.formulas import variables
    from convertersmartgrid.vad.resultados_vad import ambitos, conceptos

    ambito = ambitos(registro)[0]
    valores, variantes = {}, {}
    for c in conceptos(registro, ambito):
        try:
            opciones = registro.regla(f'vad.variantes.{c}').regla.valor
        except Exception:  # noqa: BLE001 - un concepto sin variantes
            opciones = None
        clave = f'vad.formula.{c}'
        if opciones:
            variantes[c] = opciones[0]
            clave = f'{clave}.{opciones[0]}'
        valores.update({v: 2.0 for v in variables(str(registro.regla(clave).regla.valor))})
    for v in (registro.regla('vad.ponderacion').regla.valor or {}).values():
        valores.setdefault(v, 2.0)
    return {'ambito': ambito, 'moneda': 'USD', 'valores': valores, 'variantes': variantes}


def _caso(registro, *, estudio=None) -> bytes:
    from convertersmartgrid.vad.costos_explotacion import rubros

    rubro = rubros(registro)[0]
    explotacion = {rubro.clave: [{'descripcion': 'cuadrilla', 'cantidad': 2, 'costo_unitario': 10.0, 'moneda': 'USD',
                                  'fuente': 'dimensionado'}]}
    sistemas = {'S1': {'anexo2': 'a.json', 'resultados': 'r1.json', 'explotacion': 'x1.json'},
                'S2': {'resultados': 'r2.json'}}
    paquete = io.BytesIO()
    with zipfile.ZipFile(paquete, 'w') as z:
        z.writestr('sistemas.json', json.dumps({'sistemas': sistemas, **({'estudio': estudio} if estudio else {})}))
        z.writestr('a.json', '{}')
        z.writestr('r1.json', json.dumps(_resultados_sinteticos(registro)))
        z.writestr('r2.json', json.dumps(_resultados_sinteticos(registro)))
        z.writestr('x1.json', json.dumps(explotacion))
    return paquete.getvalue()


def _registro():
    from convertersmartgrid.registro_normativo import cargar_registro
    return cargar_registro(RAIZ / 'config' / 'vad', RAIZ / 'config' / 'normativa')


def _estudio(cliente) -> tuple[str, str]:
    wid = cliente.post('/api/workspaces').json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/vad/estudios', json={'grupo': 1, 'periodo': '2041-2045', 'version_tdr': TDR})
    assert r.status_code == 200, r.text
    return wid, r.json()['id']


def test_108_rf26_la_linea_encadena_los_pasos_desde_el_caso_y_nombra_lo_que_falta(web_vad):
    """108:RF-26 (T30) — el armado deja, tras la empresa modelo, el VAD de cada sistema y de la empresa, los costos de
    explotación, el libro de tablas (la 13 con el VAD por sistema) y los informes; el PIDE y la calidad, que el caso no
    trae, quedan «SIN_ENTRADA» con su motivo. El detalle enseña el estado de cada paso y sus salidas."""
    _exige()
    cliente, app = web_vad
    wid, eid = _estudio(cliente)
    r = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/armar',
                     files=[('files', ('caso.zip', _caso(_registro()), 'application/zip'))])
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    d = cliente.get(f'/api/workspaces/{wid}/vad/{eid}').json()
    pasos = d['linea']['pasos']
    assert d['linea']['terminada'] is True and set(pasos) == {
        'modelo_rural', 'dimensionamiento', 'costo_estandar', 'resultados', 'pide', 'calidad', 'explotacion', 'tablas',
        'informes'}
    assert pasos['resultados']['estado'] in ('OK', 'INCOMPLETO') and pasos['resultados']['sistemas'] == 2
    assert pasos['explotacion']['estado'] == 'OK' and pasos['tablas']['estado'] == 'OK'
    assert pasos['informes']['estado'] == 'OK', pasos['informes']
    # Sin la red del espacio ni el sustento del caso, el tramo B (108 T30) también se nombra.
    for p in ('modelo_rural', 'dimensionamiento', 'costo_estandar', 'pide', 'calidad'):
        assert pasos[p]['estado'] == 'SIN_ENTRADA' and pasos[p]['motivo'], pasos[p]
    for s in (f'vad/{eid}/tablas_resultados.xlsx', f'vad/{eid}/informe_resultados_relevantes.docx',
              f'vad/{eid}/informe_estudio.docx', f'vad/{eid}/resultados_vad.json'):
        assert s in d['salidas'], s
    from openpyxl import load_workbook
    libro = load_workbook(Path(app.state.store.get(wid).root) / 'vad' / eid / 'tablas_resultados.xlsx')
    hoja = next(h for h in libro.worksheets if str(h['A1'].value or '').startswith('Tabla 13'))
    assert {c.value for c in hoja['A'] if c.value in ('S1', 'S2')} == {'S1', 'S2'}, 'la tabla 13 trae el VAD por sistema'


def test_108_rf26_el_informe_definitivo_usa_lo_que_dejo_la_linea(web_vad):
    """108:RF-26 (T30) — tras la línea, el Informe Definitivo ya tiene el libro de las tablas de resultados: ese documento
    deja de ser un hueco."""
    _exige()
    cliente, _app = web_vad
    wid, eid = _estudio(cliente)
    r = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/armar',
                     files=[('files', ('caso.zip', _caso(_registro()), 'application/zip'))])
    assert _esperar(cliente, r.json())['status'] == 'done'
    r = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/informe-definitivo')
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    assert not any('sin el libro de las tablas de resultados' in h for h in fin['result']['huecos']), fin['result']['huecos']


def test_108_rf26_cada_documento_escrito_del_informe_definitivo_se_descarga(web_vad):
    """108:RF-26 (T30) — cada documento escrito del Informe Definitivo se descarga por la ruta de ficheros que usa el
    panel. El recorrido en navegador real (frontend/test/e2e/f06_vad_linea.e2e.mjs) vio un 404: el VAD escribe en la
    raíz del espacio y la ruta solo miraba «salida/»."""
    _exige()
    cliente, _app = web_vad
    wid, eid = _estudio(cliente)
    r = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/armar',
                     files=[('files', ('caso.zip', _caso(_registro()), 'application/zip'))])
    assert _esperar(cliente, r.json())['status'] == 'done'
    assert _esperar(cliente, cliente.post(f'/api/workspaces/{wid}/vad/{eid}/informe-definitivo').json())['status'] == 'done'
    docs = cliente.get(f'/api/workspaces/{wid}/vad/{eid}').json()['informe_definitivo']['documentos']
    escritos = [d['ruta_relativa'] for d in docs if d.get('ruta_relativa')]
    assert escritos, docs
    for rel in escritos:
        r = cliente.get(f'/api/workspaces/{wid}/files/{rel}', params={'download': '1'})
        assert r.status_code == 200 and r.content, f'{rel}: {r.status_code}'


def test_108_rf26_una_entrada_del_estudio_que_no_existe_o_mal_nombrada_se_rechaza_antes(web_vad):
    """108:RF-26 (T30) — «estudio» con un paso que no es del estudio, o que nombra un fichero que no viene, da 422 antes de
    encolar."""
    _exige()
    cliente, _app = web_vad
    wid, eid = _estudio(cliente)
    ruta = f'/api/workspaces/{wid}/vad/{eid}/armar'
    for estudio, esperado in (({'otro': 'p.json'}, 'otro'), ({'pide': 'no_viene.json'}, 'no_viene.json')):
        r = cliente.post(ruta, files=[('files', ('caso.zip', _caso(_registro(), estudio=estudio), 'application/zip'))])
        assert r.status_code == 422 and esperado in r.json()['detail'], r.text
