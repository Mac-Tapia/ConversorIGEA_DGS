"""108 T28 (108:RF-23, 108:RF-24): el estudio VNR desde la web (Guía del VNR, RCD 232-2017-OS/CD). El inventario es un canonical.json sintético
y el lector del SICODI se sustituye por una tabla sintética: el libro real no entra en la suite."""
import json
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from convertersmartgrid.adaptadores.entrada.vnr.models.canonical import (CanonicalModel, Load, Node, Section,
                                                                         Transformer)


@dataclass(frozen=True)
class _Costo:
    componentes: dict


@dataclass(frozen=True)
class _Fuente:
    huella: str = 'f' * 64


class _Tabla:
    def __init__(self):
        self.filas = {('XX', 'D', 'C', 'ST2'): _Costo({'total': 1.0})}
        self.fuente = _Fuente()

    def resolver(self, codigo, tension, estructura, sector, subfamilia='', tipo=''):
        return _Costo({'total': 10_000.0}), ''


def _canonical() -> bytes:
    m = CanonicalModel()
    m.nodes += [Node('N1', 300_100, 8_600_100, 10.0), Node('N2', 300_600, 8_600_100, 10.0),
                Node('S1', 300_600, 8_600_100, 0.22)]
    m.transformers.append(Transformer('SED1', 'S1', hv_kv=10.0, lv_kv=0.22, sn_kva=250.0))
    m.loads.append(Load('C1', 'S1', kw=200.0))
    m.sections.append(Section('MT1', 'N1', 'N2', conductor_code='CP05003D', nominal_kv=10.0, length_m=500.0,
                              geometry=[[300_100, 8_600_100], [300_600, 8_600_100]]))
    return json.dumps(m.to_dict()).encode()


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    from convertersmartgrid import costos_fuentes
    from convertersmartgrid.web.jobs import Job, JobContext
    from convertersmartgrid.web.vnr_api import registrar_rutas_vnr
    from convertersmartgrid.web.workspace import WorkspaceStore

    # La copia de leer_sicodi que vad.costos toma al importarse no debe ser la falsa de esta prueba: si vad.costos se
    # importara por primera vez con el parche activo, las pruebas siguientes (test_vad_linea_b) leerían una tabla falsa.
    import convertersmartgrid.vad.costos  # noqa: F401
    monkeypatch.setattr(costos_fuentes, 'leer_sicodi', lambda *a, **k: _Tabla())
    ws = WorkspaceStore(tmp_path / 'web').create()

    def submit(w, kind, title, fn, *, lane='engine'):
        job = Job(kind, title, w.id, lane, fn)
        job.result, job.status = fn(JobContext(job, lambda *a: None)), 'done'
        return job.public()

    def guardar(destino, subida):
        destino.write_bytes(subida.file.read())

    app = FastAPI()
    registrar_rutas_vnr(app, ws_or_404=lambda wid: ws, submit=submit, guardar_subida=guardar)
    with TestClient(app) as c:
        yield c, ws


DATOS = {'sector': 'urbano_alta', 'sector_sicodi': 'ST2', 'resolucion': 'RR VAD 2023-2027', 'anio': '2023',
         'moneda': 'PEN'}


def test_108_t28_web_lanza_el_estudio_y_deja_resultado_y_libro_de_formatos(cliente):
    c, ws = cliente
    base = f'/api/workspaces/{ws.id}/vnr/estudio'
    assert c.get(base).json() == {}
    r = c.post(base, data=DATOS, files=[('canonical', ('canonical.json', _canonical(), 'application/json')),
                                        ('sicodi', ('sicodi.xlsx', b'PK', 'application/octet-stream'))])
    assert r.status_code == 202
    res = c.get(base).json()
    assert res['completo'] and res['vnr_total'] > 0 and res['moneda'] == 'PEN' and res['huella_sicodi'] == 'f' * 64
    assert res['zonas_mt'] == {'Alta 1': 1} and res['seds'][0]['tipo'] == 'Compacta Pedestal 3ø'
    assert res['formula'].startswith('VNR = MIE * CEIE + MINE * CINE')
    assert (ws.out_dir / res['libro']).is_file() and res['libro'] == 'vnr/formatos_vnr.xlsx'
    assert 'anualidad' in res['anualidad_vnr_real'] or 'error' in res['anualidad_vnr_real']


@pytest.mark.parametrize('cambio, ficheros, texto', [
    ({'sector': 'urbano'}, None, 'Sector típico'),
    ({'moneda': ' '}, None, 'moneda'),
    ({}, [('canonical', ('inv.csv', b'x', 'text/csv')), ('sicodi', ('s.xlsx', b'PK', 'x'))], 'canonical.json'),
    ({}, [('canonical', ('c.json', b'{}', 'x')), ('sicodi', ('s.pdf', b'%PDF', 'x'))], 'SICODI')])
def test_108_t28_web_rechaza_lo_que_no_es_un_estudio_vnr(cliente, cambio, ficheros, texto):
    c, ws = cliente
    ficheros = ficheros or [('canonical', ('c.json', b'{}', 'x')), ('sicodi', ('s.xlsx', b'PK', 'x'))]
    r = c.post(f'/api/workspaces/{ws.id}/vnr/estudio', data={**DATOS, **cambio}, files=ficheros)
    assert r.status_code == 400 and texto in r.json()['detail']


def test_109_rf24_el_estudio_vnr_toma_la_red_del_espacio_y_el_sicodi_de_la_empresa(cliente, tmp_path):
    """109:RF-25 y RF-26 — sin subir nada: el inventario es la red que dejó la carga del espacio (el mismo conversor) y el
    SICODI es el libro vigente de la empresa. Sin red cargada ni SICODI, el error dice qué falta y dónde se carga."""
    from convertersmartgrid import fuentes_empresa as fe
    c, ws = cliente
    base = f'/api/workspaces/{ws.id}/vnr/estudio'
    r = c.post(base, data=DATOS)
    assert r.status_code == 400 and 'red VNR-GIS' in r.json()['detail']
    fe.guardar_red(ws.root, fuente='vnr', empresa='EMPA', alimentadores=['AL1'], canonical=json.loads(_canonical()))
    r = c.post(base, data=DATOS)
    assert r.status_code == 400 and 'sicodi' in r.json()['detail']
    libro = tmp_path / 'SICODI.xlsx'
    libro.write_bytes(b'PK')
    fe.registrar(ws.root, 'sicodi', libro, periodo='RR VAD 2023-2027')
    r = c.post(base, data=DATOS)
    assert r.status_code == 202 and c.get(base).json()['completo']
