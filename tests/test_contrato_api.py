"""Contratos observables y regeneración de tipos para 002 y 065."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

RAIZ = Path(__file__).resolve().parents[1]


def modelos():
    from convertersmartgrid.web import api_contract
    return api_contract


def generador():
    spec = importlib.util.spec_from_file_location('generar_contrato_api', RAIZ / 'tools/generar_contrato_api.py')
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_job_real_preserva_envoltorio_y_resultado_extensible():
    """065:RF-17; 002:RF-16 — el resultado nativo es variable; su sobre es un contrato fijo."""
    from convertersmartgrid.web.jobs import Job, JobContext
    job = Job('conversion', 'Convertir', 'w', 'engine', lambda ctx: None)
    JobContext(job, lambda *args: None).progress(1, 3, 'alimentador')
    job.result = {'informe_nativo': {'tension': [1.0, None]}, 'avisos': []}
    assert modelos().JobRespuesta.model_validate(job.public()).model_dump() == job.public()
    for cambio in ({'lane': 'otra'}, {'status': 'desconocido'}, {'progress': {'index': 'error'}}):
        with pytest.raises(ValidationError):
            modelos().JobRespuesta.model_validate({**job.public(), **cambio})
    sin_id = job.public()
    sin_id.pop('id')
    with pytest.raises(ValidationError):
        modelos().JobRespuesta.model_validate(sin_id)


def test_workspace_real_no_pierde_campos(tmp_path):
    """065:RF-17; 002:RF-16 — el modelo preserva todos los campos del espacio real vacío."""
    from convertersmartgrid.web.workspace import WorkspaceStore
    ws = WorkspaceStore(tmp_path / 'web').create()
    publico = ws.public()
    validado = modelos().EspacioRespuesta.model_validate(publico).model_dump(exclude_unset=True)
    assert validado == publico
    with pytest.raises(ValidationError):
        modelos().EspacioRespuesta.model_validate({**publico, 'loaded': 'quizás'})
    with pytest.raises(ValidationError):
        modelos().EspacioRespuesta.model_validate({**publico, 'campo_sin_contrato': 1})


def test_grupo_no_acepta_campos_sin_contrato():
    """065:RF-17 — el grupo convertido mantiene sus campos explícitos y rechaza deriva anidada."""
    with pytest.raises(ValidationError):
        modelos().GrupoDgsRespuesta.model_validate({
            'name': 'GRUPO', 'feeders': ['UNO', 'DOS'], 'status': 'ok',
            'campo_sin_contrato': {'valor': 1},
        })


def test_health_workspace_y_job_publican_modelos_reales(tmp_path, monkeypatch):
    """065:RF-17; 002:RF-16 — OpenAPI y la respuesta HTTP comparten modelos anidados."""
    from convertersmartgrid.web.app import create_app
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        esquema = cliente.get('/openapi.json').json()
        for ruta, metodo, estado, modelo in (
            ('/api/health', 'get', '200', 'HealthRespuesta'),
            ('/api/workspaces', 'post', '201', 'EspacioRespuesta'),
            ('/api/workspaces/{wid}', 'get', '200', 'EspacioRespuesta'),
            ('/api/jobs/{job_id}', 'get', '200', 'JobRespuesta'),
        ):
            respuesta = esquema['paths'][ruta][metodo]['responses'][estado]
            assert respuesta['content']['application/json']['schema']['$ref'].endswith('/' + modelo)
        health = cliente.get('/api/health')
        assert health.status_code == 200
        assert modelos().HealthRespuesta.model_validate(health.json()).model_dump(exclude_unset=True) == health.json()
        nuevo = cliente.post('/api/workspaces')
        assert nuevo.status_code == 201
        wid = nuevo.json()['id']
        detalle = cliente.get(f'/api/workspaces/{wid}')
        assert detalle.status_code == 200
        assert modelos().EspacioRespuesta.model_validate(detalle.json()).model_dump(exclude_unset=True) == detalle.json()
        schemas = esquema['components']['schemas']
        assert schemas['JobRespuesta']['additionalProperties'] is False
        assert schemas['EspacioRespuesta']['properties']['options']['$ref'].endswith('/OpcionesRespuesta')
        assert schemas['HealthRespuesta']['properties']['capabilities']['$ref'].endswith('/CapacidadesRespuesta')


def test_todas_las_admisiones_lentas_exponen_job(tmp_path):
    """065:RF-17 — las rutas de trabajos nuevos y anteriores no vuelven a dict sin forma."""
    from convertersmartgrid.web.app import create_app
    app = create_app(tmp_path / 'web')
    rutas = [r for r in app.routes if getattr(r, 'status_code', None) == 202
             and r.path != '/api/sistema/cerrar']
    assert len(rutas) > 20
    assert [(r.path, r.response_model) for r in rutas if r.response_model is not modelos().JobRespuesta] == []


def test_generacion_reproducible_y_detecta_deriva(tmp_path):
    """065:RF-17; 002:RF-17 — regenera con la dependencia real y detecta una edición del tipo."""
    h = generador()
    esquema = h.esquema_publico(RAIZ, tmp_path / 'web')
    primero = h.generar(esquema, RAIZ, tmp_path / 'primero con espacios ñ')
    segundo = h.generar(esquema, RAIZ, tmp_path / 'segundo')
    assert primero == segundo
    assert h.comprobar(primero, RAIZ / 'frontend/src/api/esquema.ts') == []
    alterado = tmp_path / 'esquema.ts'
    alterado.write_text(primero.replace('HealthRespuesta', 'TipoManipulado'), encoding='utf-8')
    assert h.comprobar(primero, alterado)
    esquema['info']['version'] += '-deriva'
    assert h.generar(esquema, RAIZ, tmp_path / 'tercero') != primero


@pytest.mark.parametrize('disposicion', ['reducido', 'completo'])
def test_contrato_preserva_espacio_cargado_y_obra_real(tmp_path, disposicion):
    """065:RF-17; 002:RF-16 — contratos anidados sobre lector y obra reales, sin motor nativo."""
    from convertersmartgrid.web.app import create_app
    from synthetic_export import CRS_SINTETICO, ExportSpec, write_export
    from apoyo import esperar_trabajo

    rutas = write_export(ExportSpec(feeders=2, layout=disposicion), tmp_path / 'fuente')
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        nuevo = cliente.post('/api/workspaces')
        assert nuevo.status_code == 201
        wid = nuevo.json()['id']
        for casilla, ruta in zip(('red', 'loads', 'equipment'), rutas):
            with ruta.open('rb') as entrada:
                subida = cliente.post(f'/api/workspaces/{wid}/inputs/{casilla}',
                                      files={'file': (ruta.name, entrada)})
            assert subida.status_code == 200
            assert modelos().EntradaAsignadaRespuesta.model_validate(
                subida.json()).model_dump(exclude_unset=True) == subida.json()
        opciones = cliente.put(f'/api/workspaces/{wid}/options', json={
            'source_crs': CRS_SINTETICO, 'include_geography': False})
        assert opciones.status_code == 200
        admitido = cliente.post(f'/api/workspaces/{wid}/load')
        assert admitido.status_code == 202
        fin = esperar_trabajo(cliente, admitido.json())
        assert fin['status'] == 'done', fin
        estado = cliente.get(f'/api/workspaces/{wid}')
        assert estado.status_code == 200
        publico = estado.json()
        assert publico['loaded'] is True
        assert publico['totals']['feeders'] == 2
        assert modelos().EspacioRespuesta.model_validate(publico).model_dump(exclude_unset=True) == publico
        # La dataclass devuelve todas las variantes, incluso campos vacíos de SET nueva.
        obra = cliente.post(f'/api/workspaces/{wid}/obras', json={
            'clase': 'condensador', 'alimentador': 'SINTETICO', 'casos': ['Con proyecto'],
            'barra': 'BARRA', 'q_kvar': 100, 'escalones': 1})
        assert obra.status_code == 201, obra.text
        assert modelos().ObraRespuesta.model_validate(obra.json()).model_dump(exclude_unset=True) == obra.json()
        publico = cliente.get(f'/api/workspaces/{wid}').json()
        assert modelos().EspacioRespuesta.model_validate(publico).model_dump(exclude_unset=True) == publico
