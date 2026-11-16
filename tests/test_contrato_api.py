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


def test_espacio_guardado_con_obras_e_indice_se_abre(tmp_path):
    """065:RF-26 — lo ya guardado se abre: campos propios de cada obra e índice de cabecera (025:RF-28)."""
    from convertersmartgrid.web.app import create_app

    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        wid = cliente.post('/api/workspaces').json()['id']
        ws = app.state.store.get(wid)
        comunes = {'alimentador': 'A1', 'casos': ['Con proyecto']}
        ws.obras_aplicadas = [
            {'project': 'P', 'variacion': 'V', 'aplicada': 1.0, 'obra': {
                'clase': 'enlace', **comunes, 'cede': 'A2', 'enlace': {'recibe': 'A1', 'cede': 'A2', 'kv_recibe': 22.9}}},
            {'project': 'P', 'variacion': 'V', 'aplicada': 2.0, 'obra': {
                'clase': 'seccion', **comunes, 'tramos': ['T1'], 'km': 6.58}},
        ]
        ws.demanda = {'cabecera': {'name': 'carpeta', 'origin': 'server', 'indice': [
            {'relativa': '2025/libro.xlsx', 'anio': 2025, 'size': 10, 'mtime_ns': 1793645327878408100,
             'hojas': ['H'], 'meses': ['2025-01'], 'error': None}]}}
        ws.save()
        respuesta = cliente.get(f'/api/workspaces/{wid}')
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo['obras_aplicadas'][0]['obra']['enlace']['recibe'] == 'A1'
        assert cuerpo['obras_aplicadas'][1]['obra']['km'] == 6.58
        assert cuerpo['demanda']['cabecera']['indice'][0]['relativa'] == '2025/libro.xlsx'


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


#: 002:RF-38 (aclaración): la base del trinquete, medida el 2026-11-14 sobre 00d30651 con H10 y H13. Solo puede bajar;
#: subirla es cambiar la spec, no la prueba.
BASE_RUTAS_SIN_MODELO = 5


def _herramienta():
    spec = importlib.util.spec_from_file_location('rutas_sin_modelo', RAIZ / 'tools' / 'rutas_sin_modelo.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _lista_guardada(modulo) -> dict:
    """El fichero tal como está en el repositorio, leído sin la herramienta: la prueba no se fía de quien lo escribe."""
    import json
    return json.loads(modulo.LISTA.read_text(encoding='utf-8'))


def _medidas_ahora(tmp_path) -> list[str]:
    """Lo que mide la herramienta, ahora, sobre la aplicación que construye el código."""
    from convertersmartgrid.web.app import create_app
    return _herramienta().rutas_sin_modelo(create_app(tmp_path / 'web'))


def test_002_rf38_la_herramienta_mide_las_rutas_json_sin_modelo():
    """002:RF-38 — la medida no sale del fichero: sobre una aplicación mínima, cuenta las rutas de /api que devuelven JSON
    sin modelo, y no las que llevan modelo, devuelven HTML, responden 204 o están fuera de /api."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel

    class Modelo(BaseModel):
        x: int

    app = FastAPI()
    app.get('/api/con', response_model=Modelo)(lambda: {'x': 1})
    app.get('/api/sin')(lambda: {'x': 1})
    app.post('/api/sin')(lambda: {'x': 1})
    app.get('/api/pagina', response_class=HTMLResponse)(lambda: '<p>')
    app.delete('/api/borrar', status_code=204)(lambda: None)
    app.get('/fuera')(lambda: {'x': 1})
    assert _herramienta().rutas_sin_modelo(app) == ['GET /api/sin', 'POST /api/sin']


def test_002_rf38_la_lista_esta_al_dia_con_el_codigo(tmp_path):
    """002:RF-38 (aclaración), frescura — las rutas de la lista son exactamente las que la herramienta mide ahora sobre
    el código: ni una ruta nueva sin modelo fuera de ella, ni una que ya tenga modelo o ya no exista dentro."""
    modulo = _herramienta()
    guardadas = sorted(_lista_guardada(modulo)['rutas'])
    medidas = _medidas_ahora(tmp_path)
    nuevas, sobran = sorted(set(medidas) - set(guardadas)), sorted(set(guardadas) - set(medidas))
    assert not nuevas, f'rutas de /api sin response_model que no están en la lista (póngales su modelo): {nuevas}'
    assert not sobran, f'quítelas de {modulo.LISTA.name} con «tools/rutas_sin_modelo.py --escribir»: {sobran}'


def test_002_rf38_el_numero_no_sube_y_cada_ruta_dice_por_que(tmp_path):
    """002:RF-38 (aclaración), trinquete — la cifra la da la lista, no un número del texto; no sube de la base del
    2026-11-14 y cada ruta lleva su motivo, en orden estable."""
    lista = _lista_guardada(_herramienta())
    rutas = lista['rutas']
    assert isinstance(rutas, dict), 'cada ruta lleva su motivo: {"MÉTODO /ruta": "motivo"}'
    assert len(rutas) <= BASE_RUTAS_SIN_MODELO, f'{len(rutas)} rutas sin modelo: la base es {BASE_RUTAS_SIN_MODELO}'
    assert list(rutas) == sorted(rutas)
    sin_motivo = [r for r, m in rutas.items() if not isinstance(m, str) or len(m.strip()) < 15]
    assert not sin_motivo, f'rutas sin un motivo escrito: {sin_motivo}'
    assert len(_medidas_ahora(tmp_path)) <= BASE_RUTAS_SIN_MODELO


def test_002_rf38_escribir_solo_baja_y_conserva_los_motivos(tmp_path, monkeypatch, capsys):
    """002:RF-38 (aclaración) — ``--escribir`` quita las rutas que ya tienen modelo, conserva el motivo de las que
    quedan y se niega, sin tocar el fichero, si aparece una ruta nueva sin modelo."""
    import json
    modulo = _herramienta()
    lista = tmp_path / 'rutas_sin_modelo.json'
    lista.write_text(json.dumps({'rutas': {'GET /api/a': 'devuelve un fichero', 'GET /api/b': 'devuelve un zip'}}),
                     encoding='utf-8')
    monkeypatch.setattr(modulo, 'LISTA', lista)
    monkeypatch.setattr(modulo, 'de_la_aplicacion', lambda: ['GET /api/b'])
    assert modulo.main(['--escribir']) == 0
    assert json.loads(lista.read_text(encoding='utf-8'))['rutas'] == {'GET /api/b': 'devuelve un zip'}
    antes = lista.read_bytes()
    monkeypatch.setattr(modulo, 'de_la_aplicacion', lambda: ['GET /api/b', 'POST /api/nueva'])
    assert modulo.main(['--escribir']) == 1
    salida = capsys.readouterr()
    assert 'POST /api/nueva' in salida.err and 'la lista solo baja' in salida.err
    assert lista.read_bytes() == antes, 'una ruta nueva sin modelo no entra en la lista'


@pytest.mark.parametrize('contenido,error', [(None, 'no existe'), ('{no es json', 'no es JSON'),
                                             ('{"rutas": 3}', '«rutas»'), ('{"rutas": {"GET /api/a": 7}}', 'motivo')])
def test_002_rf38_una_lista_rota_se_dice(tmp_path, contenido, error):
    """002:RF-38 — una lista que falta, que no es JSON o que no tiene la forma esperada se rechaza con un mensaje claro."""
    modulo = _herramienta()
    lista = tmp_path / 'rutas_sin_modelo.json'
    if contenido is not None:
        lista.write_text(contenido, encoding='utf-8')
    with pytest.raises(ValueError, match=error):
        modulo.leer_lista(lista)
