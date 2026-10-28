"""Spec 027, T21: el proyecto desde cero, cortado a mitad y retomado sin repetir etapas."""
from __future__ import annotations

import pytest

from igea_dgs.asistente.ejecutor import ClienteWeb, PasoFallido
from igea_dgs.asistente.orquestador import ETAPAS, PuntoDeControl, ejecutar_proyecto


class _Respuesta:
    def __init__(self, codigo, datos):
        self.status_code, self._datos = codigo, datos
        self.content = b'x'
        self.text = str(datos)

    def json(self):
        return self._datos


class WebFalsa:
    """La API de la web: cada POST es un trabajo que termina; ``fallar`` corta una ruta una vez."""

    def __init__(self, fallar: str | None = None):
        self.fallar, self.llamadas = fallar, []

    def request(self, metodo, url, **kw):
        ruta = url.split('/api/workspaces/w', 1)[-1] if '/api/workspaces/w' in url else url.split('/api', 1)[-1]
        self.llamadas.append((metodo, ruta))
        if ruta.startswith('/jobs/'):
            return _Respuesta(200, {'id': ruta[6:], 'status': 'done', 'result': {'ok': ruta}})
        if self.fallar and ruta.startswith(self.fallar):
            self.fallar = None
            return _Respuesta(409, {'detail': 'DIgSILENT ocupado'})
        if metodo == 'GET' and ruta == '':
            return _Respuesta(200, {'pf_projects': {'SISTEMA_PISCO': 'P_PISCO'}})
        if metodo == 'GET' and ruta.startswith('/demanda/sistema'):
            return _Respuesta(200, {'sistema': {'alimentadores': ['PI101', 'PI102']}})
        if metodo == 'GET' and ruta == '/obras':
            return _Respuesta(200, [{'id': 'o1', 'alimentador': 'PI101'}])
        if metodo == 'GET':
            return _Respuesta(200, {'ofrecidos': [{'clave': 'n1'}]})
        if ruta == '/pf/estudios/plan':
            return _Respuesta(200, {'token': 'tk'})
        return _Respuesta(202, {'id': ruta.strip('/').replace('/', '_'), 'status': 'queued'})


def _cliente(web):
    return ClienteWeb(web, 'http://x', 'w', intervalo_s=0)


def test_cortado_a_mitad_y_retomado_sin_repetir(tmp_path):
    """027:RF-43 / 027:RF-44 — las etapas van por las rutas de la web; cortado en los estudios,
    la segunda vez retoma ahí y no repite la fuente, el sistema ni el «Caso base»."""
    procesos = []
    proceso = lambda tarea, d: procesos.append((tarea, d['sistema'], d['periodo'])) or {'codigo': 0}
    control = PuntoDeControl.abrir(tmp_path / 'agente.json')
    web = WebFalsa(fallar='/pf/estudios/plan')
    with pytest.raises(PasoFallido):
        ejecutar_proyecto({'sistema': 'Pisco', 'periodo': '2026-07'}, cliente=_cliente(web), control=control,
                          proceso=proceso)
    hechas = {k for k, v in control.estado['etapas'].items() if v['estado'] in ('hecha', 'omitida')}
    assert hechas == {'fuente', 'sistema', 'caso_base', 'cargas_nuevas', 'obras'}
    assert control.estado['etapas']['cargas_nuevas']['estado'] == 'omitida'
    assert control.estado['datos']['proyecto'] == 'P_PISCO'
    assert procesos == [('sistema_completo', 'Pisco', '2026-07')]
    # Se reinicia la web: el punto de control se lee del disco.
    web2 = WebFalsa()
    r = ejecutar_proyecto({'sistema': 'Pisco', 'periodo': '2026-07'}, cliente=_cliente(web2),
                          control=PuntoDeControl.abrir(tmp_path / 'agente.json'), proceso=proceso)
    assert r['completo'] and len(procesos) == 1, 'el sistema no se repite'
    rutas = [rt for m, rt in web2.llamadas if m == 'POST']
    assert '/load' not in rutas and '/powerfactory/caso-base' not in rutas and '/pf/obras/aplicar' not in rutas
    assert '/pf/estudios/plan' in rutas and '/pide' in rutas
    assert r['etapas']['informe']['estado'] == 'omitida' and r['datos']['alimentadores'] == ['PI101', 'PI102']
    assert [e.nombre for e in ETAPAS][-1] == 'informe'


def test_ruta_de_la_web(tmp_path, monkeypatch):
    """027:RF-43 — la ruta valida el sistema y el periodo y lanza el agente en su carril."""
    from apoyo import esperar_trabajo
    from fastapi.testclient import TestClient

    from igea_dgs.web import services
    from igea_dgs.web.app import create_app

    vistos = []
    monkeypatch.setattr(services, 'agente_proyecto', lambda ws, ctx, datos, base, http=None, reiniciar=False: (
        vistos.append((datos, reiniciar)) or {'completo': True}))
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        wid = c.post('/api/workspaces').json()['id']
        assert c.post(f'/api/workspaces/{wid}/agente/proyecto', json={'sistema': 'Pisco', 'periodo': 'julio'}).status_code == 422
        job = c.post(f'/api/workspaces/{wid}/agente/proyecto',
                     json={'sistema': 'Pisco', 'periodo': '2026-07', 'reiniciar': True}).json()
        assert job['lane'] == 'asistente' and esperar_trabajo(c, job)['status'] == 'done'
    assert vistos == [({'sistema': 'Pisco', 'periodo': '2026-07'}, True)]
