"""Motores y web (revisión de motores del 19-11, tarjeta MEJ4-MOTORES): el PIT con DIgSILENT desde la web, el motor que
no converge, el plano que deja elegir motor, sin GPU con su motivo, DIgSILENT ocupado por otra sesión, la versión de
Python que pide la PowerFactory detectada y la recalibración que no se cae a media corrida
(107:RF-23, RF-24; 111:RF-28, RF-29; 086:RF-129 a RF-132).

Todo en CPU, con dobles: el guion de DIgSILENT, el proceso de entrenamiento y la web son funciones de la prueba; nada
conecta con DIgSILENT ni pide la GPU.
"""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apoyo import cargar_herramienta
from datos_pit import perfil_b

from convertersmartgrid.adaptadores import pf_arnes
from convertersmartgrid.adaptadores.pit import motores
from convertersmartgrid.aplicacion.training_coordinator import SinGPU
from convertersmartgrid.presentacion.web import jobs as J
from convertersmartgrid.presentacion.web import services
from convertersmartgrid.presentacion.web.requisitos import UserError
from convertersmartgrid.presentacion.web.rutas_pit import crear_router

RAIZ = Path(__file__).resolve().parents[1]
APP = (RAIZ / 'src' / 'convertersmartgrid' / 'presentacion' / 'web' / 'app.py').read_text(encoding='utf-8')


# ------------------------------------------------------------------ 107:RF-23, RF-24 · el PIT con DIgSILENT

class _Ctx:
    def __init__(self):
        self.avance = []
        self.cancel = SimpleNamespace(is_set=lambda: False)

    def progress(self, i, n, texto=''):
        self.avance.append((i, n, texto))


class _Cola:
    def __init__(self):
        self.trabajos = []

    def submit(self, ws, kind, title, fn, *, lane='engine'):
        ctx = _Ctx()
        self.trabajos.append({'kind': kind, 'lane': lane, 'title': title, 'resultado': fn(ctx), 'ctx': ctx})
        return SimpleNamespace(id=f'j{len(self.trabajos)}')


def _informe_pf(anios, *, converge=True):
    """El informe que deja ``tools/pit_pf.py`` (``estudiar``), por año y orden."""
    return {'motor': 'digsilent', 'cambios': [], 'anios': {
        str(a): {'caso': f'Caso {a}', 'estudios': [
            {'orden': 'ComLdf', 'return_code': 0 if converge else 1, 'hecho': converge,
             **({'tensiones_pu': {'B1': 1.0, 'B2': 0.80}, 'cargabilidad_pct': {'L1': 130.0, 'L2': 40.0}}
                if converge else {})},
            {'orden': 'ComSimoutage', 'return_code': 0, 'hecho': True},
            {'orden': 'ComRel3', 'return_code': 0, 'hecho': True, 'indices': {'c:SAIFI': 1.5}}]}
        for a in anios}}


def _pit(tmp_path, *, licencia=True, digsilent=None, casos=True):
    caso = perfil_b(15)
    espacio = tmp_path / 'ws1'
    espacio.mkdir()
    normativa = tmp_path / 'normativa'
    normativa.mkdir()
    (normativa / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': []}), encoding='utf-8')
    perfil = {**caso['perfil']}
    perfil['pit'] = {**perfil['pit'], 'libro_red': {'hoja': 'Red', 'columnas': {}},
                     'limites': {'tension_min_pu': 0.9, 'tension_max_pu': 1.1, 'cargabilidad_max_pct': 100},
                     'digsilent': {'proyecto': 'TRANSMISION_AREA', 'carpeta': 'PIT',
                                   **({'casos': {str(a): f'Caso {a}' for a in caso['anios']}} if casos else {})}}
    cola = _Cola()
    kw = {'digsilent': digsilent} if 'digsilent' in inspect.signature(crear_router).parameters else {}
    app = FastAPI()
    app.include_router(crear_router(cola, lambda ws: tmp_path / ws, lambda: perfil, normativa,
                                    licencia=lambda: licencia, **kw))
    return TestClient(app), cola, caso


def test_107_rf23_el_pit_con_digsilent_encola_su_guion_en_el_carril_de_digsilent(tmp_path):
    """107:RF-23 — con DIgSILENT disponible, el diagnóstico encola ``tools/pit_pf.py`` en el carril «powerfactory»,
    con el proyecto y el caso de cada año del perfil, y lee su informe de vuelta con el motor que lo dio."""
    assert 'digsilent' in inspect.signature(crear_router).parameters, 'crear_router no recibe cómo lanzar pit_pf.py'
    planes = []

    def guion(wid, ctx, plan, nombre):
        planes.append((wid, plan, nombre))
        return 0, _informe_pf(plan['anios'])

    cliente, cola, caso = _pit(tmp_path, digsilent=guion)
    r = cliente.post('/api/pit/diagnostico', json={'workspace_id': 'ws1', 'area': caso['area'], 'anios': caso['anios'],
                                                   'motor': 'digsilent'})
    assert r.status_code == 200, r.text
    t = cola.trabajos[-1]
    assert t['kind'] == 'pit_diagnostico' and t['lane'] == 'powerfactory'
    wid, plan, _nombre = planes[-1]
    assert wid == 'ws1' and plan['project'] == 'TRANSMISION_AREA' and plan['folder'] == 'PIT'
    assert plan['anios'] == {str(a): f'Caso {a}' for a in caso['anios']} and plan['area'] == caso['area']
    res = t['resultado']
    assert res['motor'] == 'digsilent' and res['completo'] is True and 'estado_trabajo' not in res
    anio = res['anios'][str(caso['anios'][0])]
    assert {v['elemento'] for v in anio['violaciones']} == {'B2', 'L1'}
    assert anio['indices'] == {'c:SAIFI': 1.5}
    assert (tmp_path / 'ws1' / res['salida_relativa']).is_file()


def test_107_rf23_la_web_pasa_la_disponibilidad_real_y_el_guion():
    """107:RF-23 — ``app.py`` monta el PIT con la disponibilidad de DIgSILENT de la web y con ``guion_pf``; el panel
    ofrece DIgSILENT cuando está disponible."""
    assert 'licencia=services.digsilent_disponible' in APP and "'pit_pf.py'" in APP
    panel = (RAIZ / 'frontend' / 'src' / 'features' / 'pit' / 'EstudioPit.tsx').read_text(encoding='utf-8')
    assert "disabled={m === 'digsilent'}" not in panel and '!caps?.licencia' in panel


def test_107_rf23_sin_proyecto_o_sin_caso_no_se_encola(tmp_path):
    """107:RF-23 — sin el caso de un año (ni en el pedido ni en el perfil) es un 422 antes de encolar; sin DIgSILENT
    disponible, también, y dice que no está disponible."""
    cliente, cola, caso = _pit(tmp_path, digsilent=lambda *a: (0, {}), casos=False)
    r = cliente.post('/api/pit/diagnostico', json={'workspace_id': 'ws1', 'area': caso['area'], 'anios': caso['anios'],
                                                   'motor': 'digsilent'})
    assert r.status_code == 422 and 'caso de estudio' in r.json()['detail'] and not cola.trabajos
    r = cliente.post('/api/pit/diagnostico', json={
        'workspace_id': 'ws1', 'area': caso['area'], 'anios': caso['anios'][:1], 'motor': 'digsilent',
        'casos_pf': {str(caso['anios'][0]): 'Mi caso'}})
    assert r.status_code == 200, r.text
    assert cola.trabajos[-1]['lane'] == 'powerfactory'


def test_107_rf24_digsilent_que_no_converge_no_termina_done():
    """107:RF-24 — un flujo de DIgSILENT que no converge da ``estado_trabajo`` «no_converge» con su motivo, y un
    estudio que no terminó, «parcial»."""
    assert hasattr(motores, 'leer_informe_pf'), 'falta leer el informe de pit_pf.py'
    limites = {'cargabilidad_max_pct': {'valor': 100.0}}
    r = motores.leer_informe_pf(_informe_pf([2027], converge=False), 0, limites)
    assert r['estado_trabajo'] == 'no_converge' and 'no converge' in r['motivo'] and r['completo'] is False
    informe = _informe_pf([2027])
    informe['anios']['2027']['estudios'][2].update(hecho=False, return_code=1)
    r = motores.leer_informe_pf(informe, 0, limites)
    assert r['estado_trabajo'] == 'parcial' and 'ComRel3' in r['motivo']


def test_107_rf24_el_diagnostico_abierto_incompleto_lo_dice_la_cola(tmp_path):
    """107:RF-24 — el diagnóstico abierto que queda incompleto (el caso trae un año sin demanda) lleva
    ``estado_trabajo`` y su motivo, en vez de terminar «done» como uno entero."""
    from test_pit_web import _cliente

    caso = perfil_b(15)
    cliente, cola = _cliente(tmp_path, caso)
    r = cliente.post('/api/pit/diagnostico', json={'workspace_id': 'ws1', 'area': caso['area'],
                                                   'anios': caso['anios'], 'libro_red': 'red.xlsx',
                                                   'proyeccion': 'proyeccion.json'})
    assert r.status_code == 200, r.text
    res = cola.trabajos[-1]['resultado']
    assert res['completo'] is False                     # el mismo caso de test_diagnostico_en_cola_con_progreso
    assert res.get('estado_trabajo') in ('parcial', 'no_converge') and res.get('motivo')


# ------------------------------------------------------------------ 111:RF-28, RF-29 · el plano

def test_111_rf28_un_flujo_que_no_converge_termina_no_converge(tmp_path):
    """111:RF-28 — la variación estudiada que no converge deja ``estado_trabajo`` «no_converge» con el motivo del
    motor; el resultado se guarda igual."""
    pytest.importorskip('pandapower')
    from test_plano_api import BASE, _abrir, _montar

    cliente, _ws, fuente, trabajos, alimentador, _seed = _montar(tmp_path, licencia=True, vinculado=True)
    original = fuente.guion
    fuente.guion = lambda ws, ctx, plan: {**original(ws, ctx, plan), 'convergio': False,
                                          'mensajes': ['el flujo no converge en 25 iteraciones']}
    _vista, v = _abrir(cliente, alimentador)
    assert cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={'project': 'P'}).status_code == 202
    res = trabajos[-1]['result']
    assert res.get('estado_trabajo') == 'no_converge' and '25 iteraciones' in res.get('motivo', '')


def test_111_rf29_el_operador_elige_el_motor_y_disponible_no_es_licencia(tmp_path, monkeypatch):
    """111:RF-29 — con DIgSILENT posible, el operador puede pedir el motor abierto; pedir DIgSILENT sin poder usarlo es
    un 422 con su motivo; la web mira que DIgSILENT esté disponible, no que haya un intérprete."""
    pytest.importorskip('pandapower')
    from convertersmartgrid.presentacion.web.plano_api import FuenteWeb
    from test_plano_api import BASE, _abrir, _montar

    assert hasattr(FuenteWeb, 'disponible'), 'FuenteWeb confunde la licencia con haber intérprete'
    monkeypatch.setattr(services, 'powerfactory_status', lambda refresh=False: {'interpreter': 'python.exe',
                                                                                'available': False})
    assert FuenteWeb().disponible() is False
    cliente, _ws, fuente, trabajos, alimentador, _seed = _montar(tmp_path, licencia=True, vinculado=True)
    plano = cliente.get(BASE, params={'alimentador': alimentador, 'project': 'P'}).json()
    assert plano['motor']['digsilent_posible'] is True
    _vista, v = _abrir(cliente, alimentador)
    r = cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={'project': 'P', 'motor': 'abierto'})
    assert r.status_code == 202, r.text
    assert trabajos[-1]['lane'] == 'engine' and fuente.planes == []
    fuente.lic = False
    r = cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={'project': 'P', 'motor': 'DIgSILENT'})
    assert r.status_code == 422 and 'no está disponible' in r.json()['detail']
    from convertersmartgrid.adaptadores import resultados_plano as rp
    assert 'licencia' not in rp.elegir_motor(licencia=False, vinculado=True)['motivo']


# ------------------------------------------------------------------ 086:RF-129 · sin GPU, error claro

def test_086_rf131_el_entrenamiento_sin_gpu_deja_su_informe_y_su_codigo(tmp_path, monkeypatch):
    """086:RF-129 — ``tools/digital_twin_entrenar.py`` captura ``SinGPU``: informe con ``sin_gpu`` y el motivo, y el
    código 3; antes salía sin informe."""
    from convertersmartgrid.adaptadores.digital_twin import oraculo

    guion = cargar_herramienta('digital_twin_entrenar.py', 'digital_twin_entrenar_mej4')

    def sin_gpu(*_a, **_k):
        raise SinGPU('no hay GPU CUDA en este equipo')

    monkeypatch.setattr(oraculo, 'dispositivo', sin_gpu)
    salida = tmp_path / 'informe.json'
    try:
        rc = guion.main(['--output-json', str(salida), '--raiz', str(tmp_path / 'bufer')])
    except SinGPU:
        rc = None
    assert rc == 3 and salida.is_file()
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['sin_gpu'] is True and 'GPU' in informe['motivo'] and informe['entrenado'] is False


def _ctx_que_escribe(informe):
    def run_process(cmd, **_kw):
        if informe is not None:
            Path(cmd[cmd.index('--output-json') + 1]).write_text(json.dumps(informe), encoding='utf-8')
        return 3 if informe and informe.get('sin_gpu') else 1
    return SimpleNamespace(job=SimpleNamespace(id='j1'), run_process=run_process, log=lambda *_a, **_k: None)


def test_086_rf131_el_trabajo_sin_gpu_falla_con_su_motivo(tmp_path):
    """086:RF-129 — el pronóstico y el reentrenamiento de la web fallan con el motivo del informe (sin GPU, ``SinGPU``;
    sin informe, su error), en vez de terminar «done» con «código 1 sin informe»."""
    ws = SimpleNamespace(out_dir=tmp_path / 'out')
    pedido = {'clase': 'cabecera', 'libros': ['m.xlsx'], 'zona_horaria': 'America/Lima', 'cadencia_min': 15}
    sin = {'status': 'ERROR_ENTORNO', 'error': 'no hay GPU CUDA', 'sin_gpu': True, 'motivo': 'no hay GPU CUDA'}
    lanzado = None
    try:
        services.gemelo_pronostico(ws, _ctx_que_escribe(sin), pedido)
    except SinGPU as exc:
        lanzado = exc
    assert lanzado is not None and 'GPU' in str(lanzado)
    lanzado = None
    try:
        services.gemelo_pronostico(ws, _ctx_que_escribe(None), pedido)
    except UserError as exc:
        lanzado = exc
    assert lanzado is not None and 'sin informe' in str(lanzado)
    assert 'estricto' in inspect.signature(services.gemelo_entrenar).parameters
    with pytest.raises(SinGPU, match='GPU'):
        services.gemelo_entrenar(ws, _ctx_que_escribe({'entrenado': False, **sin}), estricto=True)
    assert 'estricto=True' in APP


# ------------------------------------------------------------------ 086:RF-130 · ocupado no es licencia

def test_086_rf132_digsilent_ocupado_por_otra_sesion_no_dice_licencia(tmp_path):
    """086:RF-130 — con el turno en manos de otra sesión viva, la causa dice «ocupado por otra sesión; espere su
    turno», no «compruebe su licencia»; el servidor propio que quedó abierto no cuenta como otra sesión."""
    assert 'turno' in inspect.signature(pf_arnes.causa_sin_conexion).parameters, 'la causa no mira el turno'
    otra = {'pid': os.getpid(), 'guion': 'ajuste_cabecera_pf.py', 'desde': '2026-11-19T10:00:00', 'codigo': 'D:/otra'}
    texto = pf_arnes.causa_sin_conexion(abierto=lambda: [], cola=tmp_path, turno=lambda: otra)
    assert 'DIgSILENT está ocupado por otra sesión; espere su turno' in texto and 'licencia' not in texto
    assert 'ajuste_cabecera_pf.py' in texto
    from convertersmartgrid.adaptadores.powerfactory_env import tools_dir
    propio = {**otra, 'guion': pf_arnes.SERVIDOR, 'codigo': os.path.normcase(str(tools_dir().resolve()))}
    texto = pf_arnes.causa_sin_conexion(abierto=lambda: [], cola=tmp_path, turno=lambda: propio)
    assert 'otra sesión' not in texto


# ------------------------------------------------------------------ 086:RF-131 · la versión que pide la PowerFactory

def test_086_rf133_los_mensajes_dicen_el_python_que_pide_la_powerfactory(monkeypatch, tmp_path):
    """086:RF-131 (amplía 103:RF-4) — ``_require_pf`` y el doctor dicen la versión de Python que pide la PowerFactory
    detectada y que se reinstale el programa; ni «solo carga en 3.12» ni «instale esa versión»."""
    from convertersmartgrid.presentacion.web import doctor

    fuente = Path(doctor.__file__).read_text(encoding='utf-8')
    assert 'cuya API solo carga en 3.12' not in fuente, 'el doctor fija la versión de Python de DIgSILENT'
    monkeypatch.setattr(services, 'powerfactory_status', lambda refresh=False: {
        'interpreter': None, 'api_dir': 'C:/DIgSILENT/PowerFactory 2022/Python/3.10', 'api_version': '3.10',
        'instalacion': 'PowerFactory 2022', 'running_python': '3.12', 'available': False})
    with pytest.raises(UserError) as exc:
        services._require_pf()
    texto = str(exc.value)
    assert 'PowerFactory 2022' in texto and 'Python 3.10' in texto and 'Reinstale el programa' in texto
    assert 'CSG_PF_INTERPRETER' not in texto and 'Instale esa versión' not in texto
    api = tmp_path / 'PowerFactory 2022' / 'Python' / '3.10'
    api.mkdir(parents=True)
    (api / 'powerfactory.pyd').write_bytes(b'')
    c = doctor._digsilent(lambda: api, interprete=lambda d: (None, 'no se encontro Python 3.10'))
    assert c.ok is False and 'Python 3.10' in c.detalle and 'Reinstale el programa' in c.arreglo


# ------------------------------------------------------------------ 086:RF-132 · la recalibración no se cae

def _job(id_, kind, workspace='w1', status='running', title='Recalibrar · P'):
    return SimpleNamespace(id=id_, kind=kind, workspace_id=workspace, status=status, title=title, lane='asistente')


def test_086_rf134_una_accion_de_digsilent_espera_o_se_rechaza_antes_de_empezar():
    """086:RF-132 — con una recalibración en curso en el espacio, un trabajo de DIgSILENT de otro se rechaza antes de
    empezar con su motivo; los pasos de la propia recalibración (su cabecera) entran; otro espacio no se ve afectado."""
    assert hasattr(J, 'reserva_de_digsilent'), 'la cola no reserva DIgSILENT para la recalibración'
    activos = [_job('r1', 'recalibrar')]
    motivo = J.reserva_de_digsilent(activos, 'w1', 'powerfactory', '')
    assert motivo and 'Recalibrar · P' in motivo and 'espere' in motivo
    assert J.reserva_de_digsilent(activos, 'w1', 'powerfactory', 'r1') is None
    assert J.reserva_de_digsilent(activos, 'w2', 'powerfactory', '') is None
    assert J.reserva_de_digsilent(activos, 'w1', 'engine', '') is None
    assert J.reserva_de_digsilent([_job('r1', 'recalibrar', status='done')], 'w1', 'powerfactory', '') is None
    assert 'app.add_middleware(TrabajoPropio)' in APP


def test_086_rf134_la_cabecera_del_trabajo_llega_a_la_ruta():
    """086:RF-132 — el middleware deja el trabajo dueño de la petición a la vista de la cola, también en una ruta
    síncrona."""
    assert hasattr(J, 'TrabajoPropio')
    app = FastAPI()
    app.add_middleware(J.TrabajoPropio)

    @app.get('/quien')
    def quien() -> dict:
        return {'propio': J.TRABAJO_PROPIO.get()}

    c = TestClient(app)
    assert c.get('/quien', headers={'X-CSG-Trabajo-Propio': 'r1'}).json() == {'propio': 'r1'}
    assert c.get('/quien').json() == {'propio': ''}


class _Respuesta:
    def __init__(self, status, cuerpo):
        self.status_code, self._cuerpo = status, cuerpo
        self.text = json.dumps(cuerpo, ensure_ascii=False)

    def json(self):
        return self._cuerpo


def test_086_rf134_sistema_web_espera_su_carril_en_vez_de_caerse(monkeypatch):
    """086:RF-132 (amplía 028:RF-21) — un paso de ``tools/sistema_web.py`` que recibe «Ya hay un trabajo en curso»
    espera a los demás trabajos del espacio y repite, con la cabecera de su trabajo; antes lanzaba ``RuntimeError`` y
    la recalibración se caía."""
    sw = cargar_herramienta('sistema_web.py', 'sistema_web_mej4')
    monkeypatch.setattr(sw, 'cabeceras_locales', lambda url: {})
    monkeypatch.setattr(sw.time, 'sleep', lambda s: None)
    monkeypatch.setenv('CSG_TRABAJO_PROPIO', 'r1')
    web = sw.Web('http://servidor-de-prueba', 'w1', pausa=0)
    vistos = []
    respuestas = [_Respuesta(409, {'detail': 'Ya hay un trabajo en curso en este espacio: «Estudios»'}),
                  _Respuesta(202, {'id': 'j9', 'status': 'queued'})]

    def pedir(metodo, url, **_kw):
        vistos.append((metodo, url, dict(web.http.headers)))
        if metodo == 'GET':
            return _Respuesta(200, {'jobs': [{'id': 'r1', 'status': 'running', 'title': 'Recalibrar'}]})
        return respuestas.pop(0)

    monkeypatch.setattr(web.http, 'request', pedir)
    try:
        r = web.post('/demanda/calibrar', json={})
    except RuntimeError:
        r = None
    assert r == {'id': 'j9', 'status': 'queued'}
    assert all(h.get('X-CSG-Trabajo-Propio') == 'r1' for _m, _u, h in vistos)
    assert J.CABECERA_TRABAJO_PROPIO == 'x-csg-trabajo-propio'
