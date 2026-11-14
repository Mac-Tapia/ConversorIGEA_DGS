"""La edición de producto, con todo activo, y lo que el asistente puede hacer sin preguntar (spec 086, T12 y T15).

Cada prueba dice qué pasaba antes de corregirlo: la revisión de la 086 solo leyó el código, y estos fallos se
reprodujeron aquí antes de tocar nada. ``docs/regresiones/`` guarda la reproducción.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid import edicion
from convertersmartgrid.asistente import almacen, mejoras, vigilancia
from convertersmartgrid.asistente.equipo import _NATIVAS, inventario_equipo
from convertersmartgrid.asistente.interprete import Interpretacion
from convertersmartgrid.asistente.plan import Plan, resolver
from convertersmartgrid.asistente.tareas import (EFECTOS, ESCRIBE, LEE, LICENCIA, RED, TAREAS, TAREAS_IDEMPOTENTES,
                                                 requiere_confirmacion)
from convertersmartgrid.digital_twin import integration, temporal
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app
from convertersmartgrid.web.jobs import EventLog

RAIZ = Path(__file__).resolve().parents[1]
#: Las rutas que la 1.0 negaba en la edición de producto hasta el 2026-11-13; ahora se atienden.
RUTAS_ANTES_NEGADAS = (
    ('post', '/api/workspaces/{wid}/digital-twin/entrenar'),
    ('post', '/api/workspaces/{wid}/digital-twin/aprender'),
    ('post', '/api/workspaces/{wid}/digital-twin/temporal'),
    ('post', '/api/workspaces/{wid}/digital-twin/evaluar'),
    ('post', '/api/workspaces/{wid}/digital-twin/deriva'),
    ('get', '/api/workspaces/{wid}/digital-twin/episodes'),
    ('post', '/api/modelos/gemelo/volver'),
    ('post', '/api/workspaces/{wid}/asistente/entrenar'),
    ('post', '/api/workspaces/{wid}/asistente/abc/revision'),
    ('get', '/api/asistente/equipo'),
    ('get', '/api/workspaces/{wid}/asistente/equipo'),
    ('post', '/api/workspaces/{wid}/asistente/mejoras/libreria'),
    ('post', '/api/asistente/mejoras/abc/decision'),
    ('get', '/api/asistente/aceptacion'),
)


class _Modelo:
    version = 'falso'

    def __init__(self, tarea, datos=None):
        self.tarea, self.datos = tarea, datos or {}

    def predecir(self, _texto):
        return {'tarea': self.tarea, 'confianza': 0.99, 'datos': self.datos, 'alternativas': [], 'version': 'falso'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv(edicion.VARIABLE_EDICION, raising=False)
    monkeypatch.delenv(edicion.VARIABLE_BETA_APAGADAS, raising=False)
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'twin'))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as c:
        app.state.asistente_http = c
        yield c


@pytest.fixture
def producto(monkeypatch):
    monkeypatch.setenv(edicion.VARIABLE_EDICION, 'producto')


def _wid(client) -> str:
    return client.post('/api/workspaces', json={'name': 'p'}).json()['id']


def _esperar(client, job_id, limite=30):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        j = client.get(f'/api/jobs/{job_id}').json()
        if j['status'] in ('done', 'failed', 'cancelled', 'parcial', 'no_converge'):
            return j
        time.sleep(0.05)
    raise AssertionError('el trabajo no terminó')


def _orden(client, wid, tarea, monkeypatch, datos=None, texto='haz esto'):
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (_Modelo(tarea, datos), None))
    monkeypatch.setattr(services, '_asistente_requisitos', lambda *_a, **_k: None)
    r = client.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    j = _esperar(client, r.json()['id'])
    assert j['status'] == 'done', j
    return j['result']


# ---------------------------------------------------------------- T12: todo activo en producto (usuario, 2026-11-13)
#
# Orden del usuario del 2026-11-13, confirmada con pregunta expresa: «nada debería estar apagado ni bloqueado». La
# edición de producto entregaba apagados el entrenamiento, el gemelo (PINN y GRU), el pronóstico por modelos, las
# mejoras, el ciclo del 050, la revisión por roles y las preguntas sobre el código: el servidor negaba sus rutas y el
# asistente sus tareas. Ahora se entregan activos; lo que la edición sigue decidiendo es de seguridad (salidas a la
# red apagadas por defecto, 086:RF-22, y CORS sin el servidor de Vite).

#: Las tareas que la 1.0 negaba en producto hasta el 2026-11-13.
TAREAS_ANTES_NEGADAS = ('episodios', 'evaluar_gemelo', 'gemelo_aprender', 'gemelo_entrenar', 'gemelo_temporal', 'pronostico',
                        'entrenar_asistente', 'pregunta')


def _vigilante(tmp_path, hechos, nuevos=(15, 25)):
    return vigilancia.Vigilante(
        listar_trabajos=lambda: [], reintentar=lambda _i: None,
        entrenar_gemelo=lambda: hechos.append('gemelo'), entrenar_asistente=lambda: hechos.append('asistente'),
        contar_nuevos=lambda: nuevos, repo=tmp_path)


def _repo_con_pruebas(tmp_path) -> Path:
    """Un árbol con sus pruebas y la herramienta de la suite, como el de desarrollo."""
    (tmp_path / 'tests').mkdir(exist_ok=True)
    (tmp_path / 'tools').mkdir(exist_ok=True)
    (tmp_path / 'tools' / 'suite_por_tandas.py').write_text('', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('edicion_', ['producto', 'desarrollo'])
def test_la_vigilancia_hace_lo_mismo_en_las_dos_ediciones(tmp_path, monkeypatch, edicion_):
    """086:RF-15 — de noche y con datos nuevos, el producto reentrena y lanza la suite como en desarrollo.
    Antes, en producto, ni avisaba de los datos nuevos ni lanzaba nada."""
    monkeypatch.setenv(edicion.VARIABLE_EDICION, edicion_)
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    hechos = []
    monkeypatch.setattr(vigilancia, 'lanzar_suite_separada', lambda repo, **_k: hechos.append('suite'))
    _vigilante(tmp_path, hechos).tic(fecha=datetime(2026, 11, 4, 23))
    assert hechos == ['gemelo', 'asistente', 'suite']


def test_la_suite_corre_en_producto_donde_estan_sus_pruebas(tmp_path, monkeypatch, producto):
    """086:RF-15 — la edición ya no la para: con las pruebas y su herramienta, se lanza y se corre."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))
    repo = _repo_con_pruebas(tmp_path)
    lanzados = []

    class _Hecho:
        returncode, stdout, stderr = 0, '3 passed in 1.0s\n', ''

    def lanzar(*a, **_k):
        lanzados.append(a)
        return _Hecho()

    assert vigilancia.lanzar_suite_separada(repo, lanzar=lanzar) is True
    monkeypatch.setattr(vigilancia.subprocess, 'run', lanzar)
    assert vigilancia.correr_suite(repo)['codigo'] == 0
    assert len(lanzados) == 2


def test_sin_pruebas_instaladas_la_vigilancia_no_anota_falsos_fallos(tmp_path, monkeypatch, producto):
    """086:RF-15 — el programa instalado no trae ``tests/`` ni la herramienta de la suite (086 D4). Sin la negación por
    edición, la vigilancia lanzaba cada noche una herramienta que no existe y anotaba una suite «interrumpida»; ahora
    no la lanza ni anota nada."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))
    lanzados = []
    assert vigilancia.lanzar_suite_separada(tmp_path, lanzar=lambda *a, **_k: lanzados.append(a)) is False
    assert not lanzados and not almacen.leer('suite')


def test_las_mejoras_se_preparan_en_producto(tmp_path, monkeypatch, producto):
    """086:RF-15 — proponer una librería prepara su rama también en producto: la edición ya no la corta antes de
    validar la propuesta."""
    class _Validada(Exception):
        pass

    def validar(_p):
        raise _Validada

    monkeypatch.setattr(mejoras, 'validar', validar)
    with pytest.raises(_Validada):
        mejoras.preparar_rama(tmp_path, {'id': 'x', 'paquete': 'y'})


def _instalado_simulado(tmp_path, monkeypatch) -> None:
    """Un programa instalado, como en la 086:RF-36: lo decide su carpeta, no la variable."""
    instalado = tmp_path / 'sitio' / 'convertersmartgrid' / '_programa'
    instalado.mkdir(parents=True)
    monkeypatch.setattr(edicion, 'raiz_programa', lambda: instalado)
    monkeypatch.delenv(edicion.VARIABLE_EDICION, raising=False)
    assert edicion.es_instalado() and edicion.es_edicion_producto()


def test_en_el_instalado_las_mejoras_dicen_que_son_de_desarrollo(tmp_path, monkeypatch):
    """086:RF-15 — el equipo del cliente no trae git ni el código fuente: la mejora lo dice en palabras del operador,
    sin llegar a git ni a la red. Antes habría fallado con «git worktree: fatal: not a git repository»."""
    _instalado_simulado(tmp_path, monkeypatch)
    llamadas = []
    monkeypatch.setattr(mejoras, '_git', lambda *a: llamadas.append(a) or '')
    monkeypatch.setattr(mejoras, 'validar', lambda _p: llamadas.append('validar'))
    with pytest.raises(edicion.SoloDesarrollo) as exc:
        mejoras.preparar_rama(tmp_path, {'id': 'x', 'paquete': 'y'})
    texto = str(exc.value)
    assert texto == edicion.MENSAJE_SOLO_DESARROLLO and 'desarrollo' in texto
    assert not re.search(r'git|Traceback|\.py|RF-\d', texto) and not llamadas
    monkeypatch.setattr(services, 'asistente_vocabulario', lambda _ws: pytest.fail('no consulta PyPI'))
    with pytest.raises(edicion.SoloDesarrollo):
        services.asistente_proponer_libreria(None, None, 'paquete', 'motivo')


def test_en_el_instalado_la_mejora_falla_sin_traza_en_el_registro(tmp_path, monkeypatch):
    """086:RF-15 — el trabajo de la mejora termina con el aviso y el Registro lo dice en una línea."""
    from convertersmartgrid.web.jobs import JobManager

    _instalado_simulado(tmp_path, monkeypatch)
    eventos = []
    jobs = JobManager(lambda *a: eventos.append(a))
    try:
        j = jobs.submit('w', 'asistente_mejora', 'Proponer una librería',
                        lambda _ctx: services.asistente_proponer_libreria(None, None, 'p', 'm'))
        fin = time.monotonic() + 10
        while j.status not in ('failed', 'done') and time.monotonic() < fin:
            time.sleep(0.02)
        assert j.status == 'failed' and j.error == edicion.MENSAJE_SOLO_DESARROLLO
        assert not any('Traceback' in str(e) for e in eventos)
    finally:
        jobs.shutdown(timeout_s=2)


def test_en_desarrollo_las_mejoras_siguen_igual(tmp_path, monkeypatch):
    """086:RF-15 — en el árbol, también con ``CSG_EDICION=producto``, la mejora sigue hasta su validación."""
    monkeypatch.setenv(edicion.VARIABLE_EDICION, 'producto')
    assert not edicion.es_instalado()

    class _Validada(Exception):
        pass

    def validar(_p):
        raise _Validada

    monkeypatch.setattr(mejoras, 'validar', validar)
    with pytest.raises(_Validada):
        mejoras.preparar_rama(tmp_path, {'id': 'x', 'paquete': 'y'})


@pytest.mark.parametrize('nombre, llamada', [
    ('gemelo_entrenar', lambda: services.gemelo_entrenar(None, None)),
    ('asistente_entrenar', lambda: services.asistente_entrenar(None, None)),
    ('gemelo_aprender', lambda: services.gemelo_aprender(None, None, 'P', [])),
    ('gemelo_pronostico', lambda: services.gemelo_pronostico(None, None, {})),
    ('gemelo_temporal', lambda: services.gemelo_temporal(None, None, 'j', {})),
    ('gemelo_evaluar', lambda: services.gemelo_evaluar(None, None)),
    ('gemelo_deriva', lambda: services.gemelo_deriva(None, None)),
    ('asistente_revisar_plan', lambda: services.asistente_revisar_plan(None, None, 'p')),
    ('asistente_proponer_libreria', lambda: services.asistente_proponer_libreria(None, None, 'p', 'm')),
    ('asistente_calcular_vectores', lambda: services.asistente_calcular_vectores(None, None)),
])
def test_los_servicios_ya_no_se_niegan_en_producto(producto, monkeypatch, nombre, llamada):
    """086:RF-15 — cada servicio entra en su trabajo: con argumentos vacíos falla por ellos, nunca por la edición.
    Antes, todos respondían «Esta función no forma parte de esta versión del programa»."""
    from convertersmartgrid.digital_twin import oraculo

    def sin_gpu(*_a, **_k):                     # el controlador de la GPU no se toca en estas pruebas
        raise oraculo.SinGPU('No hay GPU CUDA para el gemelo digital')

    monkeypatch.setattr(oraculo, 'dispositivo', sin_gpu)
    try:
        llamada()
    except Exception as exc:                   # noqa: BLE001 - lo que importa es el motivo
        assert 'esta versión' not in str(exc), nombre
    assert not hasattr(services, '_fuera_de_la_version')


def test_024_rf1_en_producto_la_captura_sigue_activa_y_solo_la_apaga_el_operador(monkeypatch, producto):
    """024:RF-1; 086:RF-15 — orden del usuario (2026-11-13): «nada debería estar apagado ni bloqueado». Cada corrida de
    la web deja su episodio también en la edición de producto, y el ciclo de aprendizaje lo usa; solo lo apaga el operador."""
    monkeypatch.delenv(integration.VARIABLE_CAPTURA, raising=False)
    assert integration.captura_activa() is True
    monkeypatch.setenv(integration.VARIABLE_CAPTURA, '0')                 # la orden explícita del operador
    assert integration.captura_activa() is False


def test_el_oraculo_usa_la_pinn_promovida_en_producto(tmp_path, monkeypatch, producto):
    """086:RF-15 — en producto decide la PINN promovida, como en desarrollo; antes se ignoraba aunque la hubiera."""
    from convertersmartgrid.digital_twin import buffer, oraculo

    promovida = object()
    monkeypatch.setattr(buffer, 'BuferEpisodios', lambda *_a, **_k: 'búfer')
    monkeypatch.setattr(oraculo, 'cargar', lambda bufer: promovida if bufer == 'búfer' else None)
    assert services._pinn_promovido() is promovida


def test_el_ciclo_del_050_se_encola_en_producto(tmp_path, monkeypatch, producto):
    """086:RF-15; 050:RF-4 — con su permiso y su plan, el producto encola el ciclo común; antes devolvía None."""
    import json
    import threading

    from convertersmartgrid import aprendizaje_continuo as ac
    from convertersmartgrid.web import app as web_app
    from convertersmartgrid.web.jobs import JobManager

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_AUTOENTRENAMIENTO', '1')
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'schema': ac.ESQUEMA_PLAN, 'workspace_id': 'espacio', 'raiz': str(tmp_path / 'ap'),
                                'contexto': 'a' * 64, 'fuentes': {'dataset': str(tmp_path / 'dataset')},
                                'familias': ['transformer'], 'politica_hash': 'b' * 64, 'tiempo_s': 600,
                                'memoria_gib': 4, 'usa_gpu': True, 'parametros': {}}), encoding='utf-8')
    monkeypatch.setenv('CSG_APRENDIZAJE_PLAN', str(plan))
    jobs = JobManager(lambda *_args: None)
    ocupado, liberar = threading.Event(), threading.Event()

    def mantener(_ctx):                         # el carril ocupado: el ciclo queda en cola y no se ejecuta aquí
        ocupado.set()
        assert liberar.wait(5)

    jobs.submit('otro', 'aprendizaje:otro', 'otro ciclo', mantener)
    assert ocupado.wait(2)
    try:
        trabajo = web_app.encolar_ciclo_aprendizaje(jobs, ['datos nuevos'])
        assert trabajo is not None and trabajo is not False and trabajo.kind.startswith('aprendizaje:')
        jobs.cancel(trabajo.id)
    finally:
        liberar.set()
        jobs.shutdown(timeout_s=2)


# ---------------------------------------------------------------- T12: rutas y tareas

@pytest.mark.parametrize('metodo, ruta', RUTAS_ANTES_NEGADAS)
def test_el_servidor_ya_no_niega_rutas_por_la_edicion(producto, metodo, ruta):
    """086:RF-16 — las rutas que la 1.0 negaba (403) se atienden en producto. Se mira la puerta, sin llamarlas:
    varias lanzarían un entrenamiento de verdad."""
    assert edicion.motivo_ruta_negada(ruta.format(wid='w')) is None, ruta


def test_las_de_solo_lectura_responden_en_producto(client, producto):
    """086:RF-16 — por la API real: el equipo, la aceptación y los episodios del gemelo, en producto."""
    for ruta in ('/api/asistente/aceptacion', '/api/asistente/equipo', f'/api/workspaces/{_wid(client)}/digital-twin/episodes'):
        assert client.get(ruta).status_code == 200, ruta


def test_ninguna_ruta_se_niega_en_producto_si_no_se_apaga_una_beta(client, producto):
    """086:RF-16 — recorre toda la API: sin ``CSG_BETA_APAGADAS``, la edición de producto no niega ninguna."""
    rutas = [r.path for r in client.app.routes if getattr(r, 'path', '').startswith('/api/')]
    assert rutas
    assert not [r for r in rutas if edicion.motivo_ruta_negada(r) is not None]


def test_las_tareas_se_ofrecen_en_producto(producto):
    """086:RF-16 — la orden da su plan en producto; antes se contestaba «no forma parte de esta versión»."""
    assert not hasattr(edicion, 'TAREAS_FUERA_DE_ALCANCE') and not hasattr(edicion, 'MENSAJE_FUERA_DE_ALCANCE')
    for tarea in TAREAS_ANTES_NEGADAS:
        assert tarea in TAREAS, tarea
        plan = resolver(Interpretacion('orden', tarea, 0.9, 'x', {}, [], []), {})
        assert plan.tarea == tarea and not any('esta versión' in d for d in plan.dudas), tarea


def test_un_plan_guardado_de_entrenar_se_atiende_en_producto(producto):
    """086:RF-16 — confirmar un plan de entrenar ya no se niega: llega a su propia comprobación (aquí, incompleto)."""
    guardado = {'plan': Plan('p', 't', 'entrenar_asistente', True, 'proceso', faltan=['un dato']), 'extras': {}, 'gobierno': None}
    with pytest.raises(services.UserError, match='no está completo'):
        services._asistente_ejecutar_plan(None, None, guardado, 'http://x', None, None)


def test_el_doctor_informa_de_la_gpu_cuda_y_su_memoria(monkeypatch):
    """086:RF-40 — entrenar y el gemelo piden una tarjeta NVIDIA con CUDA: el doctor dice cuál, su CUDA y su memoria
    libre, y sin ella qué funciones afecta y cómo arreglarlo, sin trazas."""
    from convertersmartgrid.web import doctor

    hay = doctor._gpu(lambda: {'nombre': 'NVIDIA RTX de prueba', 'cuda': '12.6', 'memoria_total_mib': 8192,
                               'memoria_libre_mib': 6144, 'controlador': '560.94'})
    assert hay.ok and not hay.obligatoria and all(t in hay.detalle for t in ('NVIDIA RTX de prueba', 'CUDA 12.6', '6,0', '8,0'))
    falta = doctor._gpu(lambda: None)
    assert not falta.ok and not falta.obligatoria
    assert 'gemelo' in falta.afecta and 'Entrenar' in falta.afecta and 'NVIDIA' in falta.arreglo
    assert not re.search(r'Traceback|Error\b|\.py', falta.detalle + falta.arreglo)


def test_sin_gpu_el_error_es_para_el_operador():
    """086:RF-15 — sin CUDA, el gemelo no cae a la CPU (regla del proyecto) y lo dice sin órdenes de pip."""
    from convertersmartgrid.training_coordinator import SinGPU, mensaje_sin_gpu

    texto = mensaje_sin_gpu()
    assert issubclass(SinGPU, RuntimeError) and 'GPU' in texto and 'CUDA' in texto and 'complemento de IA' in texto
    assert 'pip ' not in texto and 'http' not in texto and 'CPU' in texto


def test_un_trabajo_sin_gpu_no_deja_traza_en_el_registro(tmp_path):
    """086:RF-15 — el trabajo falla con el mensaje, y el Registro lo dice en una línea en lugar de una traza."""
    from convertersmartgrid.training_coordinator import SinGPU
    from convertersmartgrid.web.jobs import JobManager

    eventos = []
    jobs = JobManager(lambda *a: eventos.append(a))

    def sin_gpu(_ctx):
        raise SinGPU('No hay GPU CUDA para el gemelo digital')

    try:
        j = jobs.submit('w', 'gemelo_entrenar', 'Entrenar el gemelo', sin_gpu)
        fin = time.monotonic() + 10
        while j.status not in ('failed', 'done') and time.monotonic() < fin:
            time.sleep(0.02)
        assert j.status == 'failed' and j.error.startswith('No hay GPU CUDA')
        textos = [str(e) for e in eventos]
        assert not any('Traceback' in t for t in textos)
    finally:
        jobs.shutdown(timeout_s=2)


def test_health_dice_la_edicion(client, producto, monkeypatch):
    """086:RF-16 — la web sabe qué edición es y qué está en beta, sin decidirlo ella."""
    e = client.get('/api/health').json()['edicion']
    assert e['producto'] is True and {b['clave'] for b in e['beta']} == {'asistente', 'set_nueva', 'pide', 'confiabilidad'}
    assert all(b['activa'] and b['aviso'] for b in e['beta'])
    monkeypatch.delenv(edicion.VARIABLE_EDICION)
    assert client.get('/api/health').json()['edicion'] == {'producto': False, 'beta': []}


def test_una_beta_se_puede_apagar(client, producto, monkeypatch):
    """086:RF-16 — «desactivable»: apagada, su ruta se niega y la web lo sabe; las demás siguen."""
    wid = _wid(client)
    assert client.post(f'/api/workspaces/{wid}/pide', json={}).status_code != 403
    monkeypatch.setenv(edicion.VARIABLE_BETA_APAGADAS, 'pide, confiabilidad')
    r = client.post(f'/api/workspaces/{wid}/pide', json={})
    assert r.status_code == 403 and 'desactivada' in r.json()['detail']
    assert client.get(f'/api/workspaces/{wid}/pf/datos-empresa').status_code == 403
    assert client.get(f'/api/workspaces/{wid}/asistente/planes').status_code == 200
    activas = {b['clave']: b['activa'] for b in client.get('/api/health').json()['edicion']['beta']}
    assert activas == {'asistente': True, 'set_nueva': True, 'pide': False, 'confiabilidad': False}


# ---------------------------------------------------------------- T15: efectos y confirmación

def test_cada_tarea_declara_su_efecto():
    """086:RF-23 — una tarea nueva sin declarar hace fallar esto. Antes no había dónde mirarlo, y 16 no pedían confirmar."""
    assert set(EFECTOS) == set(TAREAS)
    for nombre, efectos in EFECTOS.items():
        assert efectos and set(efectos) <= {LEE, LICENCIA, RED, ESCRIBE}, nombre
        assert not (LEE in efectos and len(efectos) > 1), f'{nombre}: «lee» es no hacer ninguna otra cosa'
        assert (ESCRIBE in efectos) == TAREAS[nombre].escribe, nombre


def test_lo_que_abre_digsilent_declara_la_licencia():
    """086:RF-23 — lo que va por el carril de DIgSILENT consume licencia, aunque no escriba."""
    sin_declarar = [n for n in _NATIVAS if LICENCIA not in EFECTOS[n]]
    assert not sin_declarar
    assert EFECTOS['buscar_internet'] == (RED,)


def test_el_inventario_dice_efecto_y_confirmacion():
    """086:RF-23 — el catálogo del asistente lo enseña, y ya no dice que una lectura con licencia no se confirma."""
    filas = {h['herramienta']: h for h in inventario_equipo()['herramientas']}
    assert filas['leer_proyectos']['efectos'] == [LICENCIA] and filas['leer_proyectos']['confirmacion_obligatoria'] is True
    assert filas['estado']['confirmacion_obligatoria'] is False


@pytest.mark.parametrize('tarea', [n for n, e in EFECTOS.items() if LICENCIA in e or RED in e])
def test_lo_que_usa_licencia_o_red_espera(tarea):
    """086:RF-24 — toda tarea con licencia o red espera al operador, escriba o no."""
    assert requiere_confirmacion(tarea)
    assert Plan('x', 't', tarea, TAREAS[tarea].escribe, TAREAS[tarea].modo).espera_confirmacion is True


def test_una_lectura_de_digsilent_no_se_lanza_sola(client, monkeypatch):
    """086:RF-24 — «lee los proyectos» abría DIgSILENT y gastaba licencia sin preguntar; ahora espera su clic."""
    llamadas = []
    monkeypatch.setattr(services, 'pf_projects', lambda ws, ctx: llamadas.append(1) or {'projects': []})
    wid = _wid(client)
    r = _orden(client, wid, 'leer_proyectos', monkeypatch)
    assert 'trabajo' not in r and r['plan']['espera_confirmacion'] is True and r['plan']['efectos'] == [LICENCIA]
    assert r['plan']['equipo']['permiso_efectivo'] is False
    time.sleep(0.1)
    assert not llamadas, 'nada se ejecuta solo'
    hecho = client.post(f"/api/workspaces/{wid}/asistente/{r['plan']['id']}/confirmar")
    assert _esperar(client, hecho.json()['id'])['status'] == 'done' and llamadas == [1]


def test_una_busqueda_en_internet_no_sale_sin_confirmar(client, monkeypatch):
    """086:RF-24 — buscar en internet se respondía al momento, porque es una consulta; salía a la red sin preguntar."""
    salidas = []
    monkeypatch.setattr(services, 'asistente_buscar', lambda ws, texto: salidas.append(texto) or {'texto': 'dos resultados'})
    wid = _wid(client)
    r = _orden(client, wid, 'buscar_internet', monkeypatch, {'texto': [{'valor': 'flujo', 'confianza': 0.9}]})
    assert not r.get('respuesta') and r['plan']['espera_confirmacion'] is True and not salidas
    hecho = client.post(f"/api/workspaces/{wid}/asistente/{r['plan']['id']}/confirmar")
    fin = _esperar(client, hecho.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert salidas == ['flujo'] and fin['result']['texto'] == 'dos resultados'


def test_una_consulta_local_sigue_al_momento(client, monkeypatch):
    """086:RF-24 — lo que solo lee no se vuelve molesto: se responde sin preguntar."""
    r = _orden(client, _wid(client), 'estado', monkeypatch)
    assert r['respuesta'] and r['plan']['espera_confirmacion'] is False and r['plan']['efectos'] == [LEE]


def test_el_guion_guardado_exige_su_confirmacion(client, monkeypatch):
    """086:RF-25 — un guion del proyecto hace lo que quiera en la red: antes bastaba una petición para lanzarlo."""
    llamadas = []
    monkeypatch.setattr(services, 'guion_ejecutar', lambda *a, **_k: llamadas.append(a) or {'resultados': []})
    wid = _wid(client)
    ruta = f'/api/workspaces/{wid}/pf/guiones/ejecutar'
    sin = client.post(ruta, json={'project': 'P', 'nombre': 'Revisar'})
    assert sin.status_code == 409 and 'Confirme' in sin.json()['detail'] and not llamadas
    con = client.post(ruta, json={'project': 'P', 'nombre': 'Revisar', 'confirmado': True})
    assert con.status_code == 202
    assert _esperar(client, con.json()['id'])['status'] == 'done' and len(llamadas) == 1


# ---------------------------------------------------------------- T15: reintentos

def _fallido(i, kind, error='DIgSILENT devolvió 4002 al conectar'):
    return {'id': i, 'kind': kind, 'title': f'{kind} {i}', 'status': 'failed', 'lane': 'powerfactory', 'error': error,
            'created_at': 0, 'started_at': 0, 'finished_at': 1, 'result': None}


def test_la_vigilancia_solo_reintenta_lo_idempotente():
    """086:RF-26 — un 4002 en unas obras a medias las volvía a lanzar: cada intento dejaba otra variación."""
    avisos = {a.clave: a for a in vigilancia.revisar_trabajos(
        [_fallido('a', 'obras_con_proyecto'), _fallido('b', 'pf_projects'), _fallido('c', 'guion_ejecutar')], ahora=10)}
    assert avisos['fallo:a'].accion is None and avisos['fallo:c'].accion is None
    assert avisos['fallo:b'].accion == 'reintentar'


def test_los_trabajos_idempotentes_declarados_existen():
    """086:RF-26 — la lista no se queda con nombres que ya no son de ningún trabajo, ni con nada que escriba en DIgSILENT."""
    fuentes = (RAIZ / 'src/convertersmartgrid/web/app.py').read_text(encoding='utf-8')
    for kind in vigilancia.TRABAJOS_IDEMPOTENTES:
        assert re.search(rf"submit\(\w+(?:\(\w+\))?, '{kind}'", fuentes), kind


def test_las_tareas_idempotentes_no_escriben_en_digsilent():
    """086:RF-26 — un plan que escribe en un proyecto no se repite solo tras un fallo."""
    assert TAREAS_IDEMPOTENTES <= set(TAREAS)
    assert not [n for n in TAREAS_IDEMPOTENTES if {ESCRIBE, LICENCIA} <= set(EFECTOS[n])]


def _plan_que_falla(client, wid, tarea, monkeypatch, datos):
    """El plan listo, con cada paso fallando como un 4002, y las veces que se intentó."""
    from convertersmartgrid.asistente import ejecutor

    vocabulario = {'alimentadores': ['A1'], 'proyecto': ['P'], 'sistema': [], 'set': [], 'periodos': []}
    monkeypatch.setattr(services, 'asistente_vocabulario', lambda _ws: vocabulario)
    plan = _orden(client, wid, tarea, monkeypatch, datos)['plan']
    assert plan['listo'], plan
    intentos = []

    def falla(*_a, **_k):
        intentos.append(1)
        raise ejecutor.PasoFallido('POST /obras: DIgSILENT ocupado (4002)')

    monkeypatch.setattr(ejecutor, 'ejecutar', falla)
    monkeypatch.setattr(ejecutor, 'pasos', lambda *_a, **_k: [])
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    return plan, intentos


def test_el_asistente_no_repite_un_plan_que_escribe(client, monkeypatch):
    """086:RF-26 — «transfiere la carga» falló a mitad y el asistente volvía a ejecutar todos sus pasos."""
    wid = _wid(client)
    datos = {'proyecto': [{'valor': 'P', 'confianza': 1.0}], 'alimentadores': [{'valor': 'A1', 'confianza': 1.0}]}
    plan, intentos = _plan_que_falla(client, wid, 'transferencia', monkeypatch, datos)
    fin = _esperar(client, client.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'failed' and 'no se repite sola' in fin['error'] and intentos == [1]
    assert almacen.leer('reintentos')[-1]['accion'] == 'no_repetir'


def test_el_asistente_si_repite_lo_idempotente(client, monkeypatch):
    """086:RF-26 — convertir publica de forma atómica: repetirlo da lo mismo, y conserva el único reintento de 027:RF-20."""
    assert 'convertir' in TAREAS_IDEMPOTENTES
    wid = _wid(client)
    datos = {'alimentadores': [{'valor': 'A1', 'confianza': 1.0}]}
    plan, intentos = _plan_que_falla(client, wid, 'convertir', monkeypatch, datos)
    fin = _esperar(client, client.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'failed' and 'único reintento' in fin['error'] and intentos == [1, 1]


# ---------------------------------------------------------------- T15: sin GPU

def _sin_gpu(monkeypatch):
    """Lo que ve el gemelo en un equipo sin CUDA, también si alguien pasa a instalar torch sin ella."""
    from convertersmartgrid.digital_twin import oraculo

    def sin(*_a, **_k):
        raise oraculo.SinGPU('No hay GPU CUDA para el gemelo digital')

    monkeypatch.setattr(oraculo, 'dispositivo', sin)


def test_el_modelo_temporal_sin_gpu_sigue_con_aviso_y_sin_cpu(monkeypatch):
    """086:RF-27 — sin CUDA, ``modelo_temporal`` reventaba con SinGPU. Queda el estacional, que no entrena, y lo dice.
    La GRU no cae a la CPU: es regla del proyecto."""
    _sin_gpu(monkeypatch)
    m = temporal.elegido(temporal.modelo_temporal(), [1.0] * 400)
    assert isinstance(m, temporal.ModeloEstacional) and m.nombre == 'estacional'
    assert 'GPU' in m.aviso and 'CPU' not in m.aviso


def test_sin_pytorch_tambien_lo_dice():
    """086:RF-27 — antes el estacional sustituía a la GRU sin una palabra."""
    import builtins

    original = builtins.__import__

    def sin_torch(nombre, *a, **k):
        if nombre == 'torch':
            raise ImportError('sin torch')
        return original(nombre, *a, **k)

    builtins.__import__ = sin_torch
    try:
        m = temporal.modelo_temporal()
    finally:
        builtins.__import__ = original
    assert isinstance(m, temporal.ModeloEstacional) and m.aviso


def test_si_la_gpu_se_queda_sin_memoria_entrenando_sigue(monkeypatch):
    """086:RF-27 — con otra sesión en la tarjeta falla al entrenar, no al crear el modelo: tampoco tumba el trabajo."""
    class SinMemoria:
        nombre = 'gru'

        def entrenar(self, _serie):
            raise RuntimeError('CUDA out of memory. Tried to allocate 2 GiB')

    m = temporal.elegido(SinMemoria(), [1.0] * 10)
    assert isinstance(m, temporal.ModeloEstacional) and 'GPU' in m.aviso


def test_un_error_de_verdad_no_se_tapa_de_estacional():
    """086:RF-27 — solo la falta de GPU se perdona: un fallo del propio modelo sigue siendo un fallo."""
    class Roto:
        def entrenar(self, _serie):
            raise RuntimeError('la serie no tiene forma')

    with pytest.raises(RuntimeError, match='la serie'):
        temporal.elegido(Roto(), [1.0])


def test_el_trabajo_temporal_termina_sin_gpu_y_lo_avisa(tmp_path, monkeypatch):
    """086:RF-27 — el trabajo «Gemelo temporal del mes» fallaba entero sin CUDA; ahora termina y avisa."""
    _sin_gpu(monkeypatch)
    from datetime import timedelta
    from types import SimpleNamespace
    import threading

    inicio = datetime(2026, 7, 1)
    curva = [[inicio + timedelta(minutes=15 * i), 100.0 + (i % 96)] for i in range(96 * 8)]
    registro = []
    ws = SimpleNamespace(lock=threading.RLock(), curvas_cabecera={'j': {'M1': {'curva': curva}}})
    ctx = SimpleNamespace(log=registro.append)
    r = services.gemelo_temporal(ws, ctx, 'j', {'A1': 'M1'})
    assert r['alimentadores']['A1']['modelo'] == 'estacional'
    (aviso,) = r['avisos']
    assert 'GPU' in aviso and any(aviso in linea for linea in registro)


# ---------------------------------------------------------------- T35: los avisos de la corrida

def test_los_avisos_de_la_corrida_no_llevan_codigos(tmp_path):
    """086:RF-12 — la web los enseña ahora, y también van al Word: «(086:RF-11)» no le dice nada a quien lo lee."""
    avisos = services._avisos_de_la_corrida(None, {'sin': {'_fichero': 'f.json', 'medidas': {'A1': {}}}}, 'A1')
    assert avisos and 'sin registro' in avisos[0] and not re.search(r'\d{3}:RF-', avisos[0])
    fuente = (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    ini = fuente.index('def _avisos_de_la_corrida')
    fin = fuente.index('\ndef ', ini + 10)
    # Los comentarios sí citan el requisito: se comprueba solo lo que va entre comillas.
    assert not re.search(r"""['"][^'"\n]*\d{3}:RF-[^'"\n]*['"]""", re.sub(r'""".*?"""', '', fuente[ini:fin], flags=re.DOTALL))


# ---------------------------------------------------------------- T35: el Registro tras reiniciar

def test_el_registro_sigue_tras_reiniciar_el_servidor():
    """086:RF-9 — una pestaña abierta pedía ``since=67`` y el proceso nuevo numeraba desde 1: no veía el Registro nuevo."""
    antes = EventLog()
    for i in range(67):
        antes.append('log', {'text': str(i)})
    ultimo_visto = antes.last_seq
    time.sleep(0.01)
    despues = EventLog()
    nuevo = despues.append('log', {'text': 'lo nuevo'})
    assert nuevo['seq'] > ultimo_visto
    assert [e['data']['text'] for e in despues.since(ultimo_visto)] == ['lo nuevo']
    assert despues.since(0)[0]['data']['text'] == 'lo nuevo'


def test_el_registro_tras_reiniciar_por_la_api(tmp_path, monkeypatch):
    """086:RF-9 — lo mismo con dos servidores sobre los mismos datos: el segundo entrega lo suyo al que venía del primero."""
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as primero:
        wid = _wid(primero)
        primero.app.state.store.get(wid).events.append('log', {'text': 'del primero'})
        visto = primero.get(f'/api/workspaces/{wid}/events').json()[-1]['seq']
    time.sleep(0.01)
    with TestClient(create_app(tmp_path / 'web')) as segundo:
        segundo.app.state.store.get(wid).events.append('log', {'text': 'del segundo'})
        nuevos = segundo.get(f'/api/workspaces/{wid}/events', params={'since': visto}).json()
    assert [e['data']['text'] for e in nuevos] == ['del segundo']


def test_la_conversion_tras_reiniciar_lo_dice_y_el_espacio_ya_no_figura_cargado(tmp_path, monkeypatch):
    """086:RF-9 — el 400 es del servidor nuevo, que no tiene la fuente en memoria; el espacio ya dice ``loaded: false``.
    Quien no lo veía era la pestaña abierta, que no volvía a preguntar al reconectar (``useWorkspace.ts``)."""
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as primero:
        wid = _wid(primero)
        primero.app.state.store.get(wid).dataset = object()
        assert primero.get(f'/api/workspaces/{wid}').json()['loaded'] is True
    with TestClient(create_app(tmp_path / 'web')) as segundo:
        assert segundo.get(f'/api/workspaces/{wid}').json()['loaded'] is False
        assert segundo.post(f'/api/workspaces/{wid}/convert', json={'all': True}).status_code == 400
