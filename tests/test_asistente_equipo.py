"""065:RF-22 / 065:RF-23 — permisos reales del equipo, sin invocar motores."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from convertersmartgrid.asistente import almacen
from convertersmartgrid.asistente.ejecutor import ClienteWeb, Paso, ejecutar, pasos
from convertersmartgrid.asistente.plan import Plan
from convertersmartgrid.asistente.equipo import GobiernoEquipo, PermisoDenegado, inventario_equipo


@pytest.fixture(autouse=True)
def almacenamiento(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'equipo'))


def preparar(tarea='convertir', *, rol='operador', confirmar=True):
    ws = SimpleNamespace(id='espacio-a', loaded_source_fingerprint='fuente-a', loaded_source_mode='txt')
    plan = Plan('plan-a', 'orden del operador', tarea, True, 'trabajo',
                datos={'alimentadores': ['F1']} if tarea == 'convertir' else {})
    gobierno = GobiernoEquipo.desde_plan(ws, plan, rol=rol)
    if confirmar:
        gobierno.confirmar(plan)
    return ws, plan, gobierno


class HTTP:
    def __init__(self, resultado=None):
        self.llamadas = []
        self.resultado = resultado or {'fichero': 'F1.dgs'}

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        return SimpleNamespace(status_code=200, content=b'json', json=lambda: self.resultado)


def test_operador_confirmado_ejecuta_herramienta_y_reabre_evidencia():
    """065:RF-22 / 065:RF-23 / 047:RF-10 — trazabilidad durable, sin aprobación científica."""
    _, plan, gobierno = preparar()
    http = HTTP()
    cliente = ClienteWeb(http, 'http://127.0.0.1:8765', 'espacio-a', gobierno=gobierno)
    r = ejecutar(pasos(plan.tarea, plan.datos), cliente)
    assert r['completo'] and len(http.llamadas) == 1
    registro = almacen.leer('equipo_acciones')
    assert registro[-1]['estado'] == 'terminada'
    assert registro[-1]['responsable'] == 'operador'
    assert registro[-1]['alcance']['fuente'] == 'fuente-a'
    assert registro[-1]['carril'] == 'engine'
    assert registro[-1]['entrada_sha256'] and registro[-1]['salida_sha256']
    assert registro[-1]['revision']['decision'] == 'confirmada_operador'
    assert registro[-1]['aceptacion_cientifica'] is False


@pytest.mark.parametrize('rol', ['fuentes', 'fisica', 'coste', 'riesgo', 'llm', 'desconocido'])
def test_rol_sin_permiso_no_hace_http(rol):
    """065:RF-22 / 047:RF-10 — un rol nominal o revisor no ejecuta herramientas."""
    _, plan, gobierno = preparar(rol=rol)
    http = HTTP()
    with pytest.raises(PermisoDenegado, match='rol'):
        ejecutar(pasos(plan.tarea, plan.datos), ClienteWeb(http, '', 'espacio-a', gobierno=gobierno))
    assert not http.llamadas


def test_sin_confirmacion_no_hay_escritura():
    """065:RF-22 / 027:RF-19 — la confianza o el modelo no conceden confirmación."""
    _, plan, gobierno = preparar(confirmar=False)
    http = HTTP()
    with pytest.raises(PermisoDenegado, match='confirm'):
        ejecutar(pasos(plan.tarea, plan.datos), ClienteWeb(http, '', 'espacio-a', gobierno=gobierno))
    assert not http.llamadas


@pytest.mark.parametrize('campo,valor', [('loaded_source_fingerprint', 'otra'), ('id', 'espacio-b')])
def test_cambio_de_contexto_despues_de_confirmar_bloquea(campo, valor):
    """065:RF-23 / 047:RF-2 — cada acción conserva su fuente y espacio."""
    ws, plan, gobierno = preparar()
    setattr(ws, campo, valor)
    http = HTTP()
    with pytest.raises(PermisoDenegado, match='contexto'):
        ejecutar(pasos(plan.tarea, plan.datos), ClienteWeb(http, '', 'espacio-a', gobierno=gobierno))
    assert not http.llamadas


def test_no_reutiliza_confirmacion_con_otra_orden():
    """065:RF-23 / 047:RF-10 — la confirmación sella tarea y entradas."""
    _, plan, gobierno = preparar(confirmar=False)
    plan.datos['alimentadores'] = ['F2']
    with pytest.raises(PermisoDenegado, match='plan'):
        gobierno.confirmar(plan)


@pytest.mark.parametrize('paso', [Paso('oculta', 'DELETE', '/convert'),
    Paso('oculta', 'POST', '/api/workspaces/otro/convert', {}),
    Paso('oculta', 'POST', '/convert', {'feeders': ['F2'], 'all': False}),
    Paso('oculta', 'POST', '/digital-twin/entrenar', {'forzar': True})])
def test_paso_fuera_del_plan_no_llama_ruta(paso):
    """065:RF-22 / 065:RF-23 — allowlist efectiva de ruta, método y parámetros."""
    _, _, gobierno = preparar()
    http = HTTP()
    with pytest.raises(PermisoDenegado, match='paso'):
        ejecutar([paso], ClienteWeb(http, '', 'espacio-a', gobierno=gobierno))
    assert not http.llamadas


def test_proceso_confirmado_tambien_pasa_por_gobierno():
    """065:RF-22 / 065:RF-23 — la rama proceso no evade permisos ni bitácora."""
    _, plan, gobierno = preparar('entrenar_asistente')
    r = gobierno.ejecutar_proceso(lambda: {'entrenado': False, 'codigo': 0})
    assert r['codigo'] == 0
    assert almacen.leer('equipo_acciones')[-1]['herramienta'] == plan.tarea
    _, _, denegado = preparar('entrenar_asistente', rol='fuentes')
    with pytest.raises(PermisoDenegado):
        denegado.ejecutar_proceso(lambda: pytest.fail('un rol revisor no lanza procesos'))


def test_exclusion_por_espacio_y_liberacion_tras_error():
    """065:RF-23 — no hay dos acciones del asistente simultáneas sobre un espacio."""
    _, _, primero = preparar('entrenar_asistente')
    _, _, segundo = preparar('entrenar_asistente')
    def durante():
        with pytest.raises(PermisoDenegado, match='concurrencia'):
            segundo.ejecutar_proceso(lambda: None)
        raise RuntimeError('fallo deliberado')
    with pytest.raises(RuntimeError, match='deliberado'):
        primero.ejecutar_proceso(durante)
    assert segundo.ejecutar_proceso(lambda: {'codigo': 0}) == {'codigo': 0}


def test_inventario_no_otorga_permisos_por_modelo():
    """065:RF-22 — catálogo completo, permisos de ejecución solo del operador."""
    from convertersmartgrid.asistente.tareas import TAREAS
    inventario = inventario_equipo()
    assert {t['herramienta'] for t in inventario['herramientas']} == set(TAREAS)
    assert inventario['modelos_conceden_permisos'] is False
    assert all(r['puede_ejecutar'] is False for r in inventario['roles'] if r['rol'] != 'operador')


def test_fallo_de_persistencia_no_inicia_accion(monkeypatch):
    """065:RF-23 / 061:RF-10 — evidencia durable antes de tocar la API."""
    _, plan, gobierno = preparar()
    monkeypatch.setattr(almacen, 'anotar', lambda *_a, **_kw: (_ for _ in ()).throw(OSError('disco')))
    http = HTTP()
    with pytest.raises(OSError, match='disco'):
        ejecutar(pasos(plan.tarea, plan.datos), ClienteWeb(http, '', 'espacio-a', gobierno=gobierno))
    assert not http.llamadas


def test_cliente_no_puede_cambiar_espacio_del_permiso():
    """065:RF-23 — la URL efectiva debe pertenecer al espacio autorizado."""
    _, plan, gobierno = preparar()
    http = HTTP()
    with pytest.raises(PermisoDenegado, match='espacio'):
        ejecutar(pasos(plan.tarea, plan.datos), ClienteWeb(http, '', 'otro', gobierno=gobierno))
    assert not http.llamadas


def test_base_remota_rechazada_antes_de_enviar_datos():
    """065:RF-22 / 047:RF-10 — P9: ni el Host recibido autoriza enviar datos fuera."""
    _, plan, gobierno = preparar()
    http = HTTP()
    with pytest.raises(PermisoDenegado, match='local'):
        ejecutar(pasos(plan.tarea, plan.datos),
                 ClienteWeb(http, 'https://example.org', 'espacio-a', gobierno=gobierno))
    assert not http.llamadas


def test_orquestador_aplica_gobierno_a_cada_etapa_y_proceso(tmp_path):
    """065:RF-23 / 061:RF-5 — las etapas del agente no evaden los permisos."""
    from convertersmartgrid.asistente.orquestador import Etapa, PuntoDeControl, ejecutar_proyecto
    _, _, gobierno = preparar('entrenar_asistente', rol='fuentes')
    with pytest.raises(PermisoDenegado, match='rol'):
        ejecutar_proyecto({}, cliente=ClienteWeb(HTTP(), '', 'espacio-a'),
            control=PuntoDeControl.abrir(tmp_path / 'control.json'),
            proceso=lambda *_a: pytest.fail('proceso sin permiso'),
            etapas=(Etapa('modelo', 'entrenar_asistente', proceso=True),),
            gobierno_etapa=lambda *_a: gobierno)
    _, _, gobierno = preparar('entrenar_asistente')
    r = ejecutar_proyecto({}, cliente=ClienteWeb(HTTP(), '', 'espacio-a'),
        control=PuntoDeControl.abrir(tmp_path / 'control.json'), proceso=lambda *_a: {'codigo': 0},
        etapas=(Etapa('modelo', 'entrenar_asistente', proceso=True),),
        gobierno_etapa=lambda *_a: gobierno)
    assert r['completo'] and almacen.leer('equipo_acciones')[-1]['estado'] == 'terminada'


@pytest.mark.parametrize('rol', ['operador', 'fuentes'])
def test_cliente_directo_no_evade_plan_y_rol(rol):
    """065:RF-22 / 047:RF-10 — ni una llamada directa al cliente concede escritura."""
    _, _, gobierno = preparar(rol=rol)
    http = HTTP()
    with pytest.raises(PermisoDenegado):
        ClienteWeb(http, '', 'espacio-a', gobierno=gobierno).pedir('POST', '/convert', json={})
    assert not http.llamadas


def test_archivo_del_plan_no_se_sustituye_tras_proponer(tmp_path):
    """065:RF-23 — una ruta idéntica no permite confirmar otro libro de cargas."""
    ruta = tmp_path / 'cargas.xlsx'
    ruta.write_bytes(b'libro original de contrato')
    ws = SimpleNamespace(id='espacio-a', loaded_source_fingerprint='fuente-a', loaded_source_mode='txt')
    plan = Plan('plan-cargas', 'integrar libro', 'cargas_nuevas', True, 'trabajo',
                datos={'proyecto': 'P1', 'alimentadores': ['F1'], 'ruta': str(ruta)})
    gobierno = GobiernoEquipo.desde_plan(ws, plan)
    ruta.write_bytes(b'otro libro con el mismo nombre')
    with pytest.raises(PermisoDenegado, match='archivo'):
        gobierno.confirmar(plan)


def test_http_local_no_hereda_proxy_del_entorno():
    """065:RF-22 — P9: una URL loopback tampoco debe viajar por un proxy externo."""
    import requests
    class SesionLocal(requests.Session):
        def request(self, metodo, url, **kw):
            assert self.trust_env is False
            assert kw['allow_redirects'] is False
            return SimpleNamespace(status_code=200, content=b'json', json=lambda: {'ok': True})
    _, plan, gobierno = preparar()
    r = ejecutar(pasos(plan.tarea, plan.datos),
        ClienteWeb(SesionLocal(), 'http://127.0.0.1:8765', 'espacio-a', gobierno=gobierno))
    assert r['completo']
