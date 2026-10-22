"""Spec 024, T6: registro automático de episodios tras cada acción nativa de la web."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from test_digital_twin_capture import _flujo, _lectura

from igea_dgs.digital_twin import integration as it
from igea_dgs.digital_twin.buffer import BuferEpisodios, Consulta
from igea_dgs.digital_twin.episode import Caso
from igea_dgs.estructura import AlimentadorEstructura, Estructura, Sistema
from igea_dgs.native_action import build_native_action_context

RAIZ = Path(__file__).resolve().parents[1]
H = 'e' * 64
PERFIL = {'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100},
          'informes': {'norma': 'NTCSE'},
          'normas': {'NTCSER': {'tension_min_pu': 0.92, 'tension_max_pu': 1.08}}}


def _plan():
    binding = {'project': 'P_IN111', 'source_run_id': 'r', 'source_mode': 'txt', 'source_fingerprint': H}
    return {'project': 'P_IN111', 'feeders': ['IN111', 'TA225'],
            'native_action_context': build_native_action_context(
                binding, 'P_IN111', ['IN111', 'TA225'], 'obras_ejecutar')}


def _capturar(tmp_path, caso, informe=None, lectura='def', **kw):
    resultado = tmp_path / 'r.json'
    resultado.write_text('{}', encoding='utf-8')
    bufer = kw.pop('bufer', None) or BuferEpisodios(tmp_path / 'twin')
    avisos = []
    out = it.capturar_accion(
        _plan(), informe or {'status': 'OK', 'converged': True, 'cuadrado': True}, caso=caso,
        rutas={'resultado': resultado}, base=tmp_path,
        leer=lambda _p: _lectura() if lectura == 'def' else lectura,
        perfil=PERFIL, estructura=None, bufer=bufer, log=avisos.append, **kw)
    return out, bufer, avisos


def test_cada_accion_queda_en_el_bufer(tmp_path):
    """024:RF-1 — la acción terminada deja su episodio en el búfer, con su artefacto."""
    out, bufer, _ = _capturar(tmp_path, Caso.SIN_PROYECTO)
    assert out['clase'] == 'accepted' and out['caso'] == 'sin_proyecto'
    e = bufer.leer(out['episode_id'])
    assert e.artefactos[0].rol == 'resultado' and e.artefactos[0].ruta == 'r.json'


def test_lectura_que_falla_deja_cuarentena_y_aviso(tmp_path):
    """024:RF-1 / 024:RF-9 — si la lectura falla, cuarentena y aviso; nada se repite."""
    def revienta(_p):
        raise RuntimeError('DIgSILENT ocupado')

    bufer = BuferEpisodios(tmp_path / 'twin')
    avisos = []
    out = it.capturar_accion(_plan(), {'status': 'OK', 'converged': True}, caso=Caso.CON_PROYECTO,
                             rutas={}, base=tmp_path, leer=revienta, perfil=PERFIL,
                             estructura=None, bufer=bufer, log=avisos.append)
    assert out['clase'] == 'quarantine'
    assert any(it.AVISO_CUARENTENA in a for a in avisos)


def test_sin_contexto_firmado_no_hay_episodio(tmp_path):
    """024:RF-1 — una acción sin contexto firmado no se registra."""
    assert it.capturar_accion({'project': 'P'}, {}, caso=Caso.CASO_BASE, rutas={}, base=tmp_path,
                              leer=lambda _p: None, perfil={}, estructura=None) is None


def test_con_proyecto_se_compara_con_el_ultimo_sin_proyecto(tmp_path):
    """024:RF-31 — «Con proyecto» toma de referencia el último «Sin proyecto» aceptado del
    mismo proyecto; sin él, cuarentena."""
    out, bufer, _ = _capturar(tmp_path, Caso.CON_PROYECTO)
    assert out['clase'] == 'quarantine'
    _capturar(tmp_path, Caso.SIN_PROYECTO, bufer=bufer)
    peor = _lectura()
    peor['flujo']['perdidas']['valores']['total'] = 99.0
    out, _, _ = _capturar(tmp_path, Caso.CON_PROYECTO, lectura=peor, bufer=bufer)
    assert out['clase'] == 'converged_with_violations'
    assert any('pérdidas' in v for v in out['violaciones'])
    assert len(bufer.consultar(Consulta(proyecto='P_IN111'))) == 3


def test_limites_por_norma_del_sistema_de_cada_alimentador():
    """024:RF-31 — la norma sale del sistema eléctrico de cada alimentador; con dos normas,
    los límites más estrictos de las dos; sin la de uno, no hay límites."""
    estructura = Estructura(
        zonales=['Z'], sets={},
        alimentadores={'IN111': AlimentadorEstructura('IN111', 'S1', 'SE1'),
                       'PA201': AlimentadorEstructura('PA201', 'S2', 'SE2')},
        sistemas={'SE1': Sistema('SE1', 'Ica', '2', 'NTCSE'),
                  'SE2': Sistema('SE2', 'Palpa', '3', 'NTCSER')})
    assert it.normas_de(estructura, ['IN111', 'PA201']) == ['NTCSE', 'NTCSER']
    lim = it.limites_combinados(PERFIL, ['NTCSE', 'NTCSER'])
    assert (lim.tension_min_pu, lim.tension_max_pu) == (0.95, 1.05)
    assert it.limites_combinados({k: v for k, v in PERFIL.items() if k != 'normas'},
                                 ['NTCSE', 'NTCSER']) is None


def test_obras_al_pide():
    """024:RF-32 — las obras creadas pasan con su alternativa; las fallidas o que no son
    inversión del PIDE, no."""
    obras = [{'clase': 'condensador'}, {'clase': 'consigna'}, {'clase': 'terna'}, {'clase': 'seccion'}]
    filas = [{'obra': 1, 'variacion': 'IGEA obra 1'}, {'obra': 2, 'variacion': 'IGEA obra 2'},
             {'obra': 3, 'variacion': 'IGEA obra 3', 'error': 'no converge'},
             {'obra': 4, 'variacion': 'IGEA obra 4'}]
    assert [o['alternativa'] for o in it.obras_pide(obras, filas)] == ['bancos', 'cambio_seccion']


def test_plan_de_lectura_lleva_contexto_y_variaciones():
    """024:RF-27 — la lectura pide las variaciones que dejó la acción y el mismo contexto."""
    plan = _plan()
    lectura = it.plan_de_lectura(plan, Caso.CON_PROYECTO, {'variaciones_creadas': ['IGEA obra 1']})
    assert lectura['case'] == 'con_proyecto'
    assert lectura['variaciones_esperadas'] == ['IGEA obra 1']
    assert lectura['native_action_context'] == plan['native_action_context']


def test_captura_se_apaga_con_su_variable(monkeypatch):
    """024:RF-1 — sin la variable la captura está activa; ``0`` la apaga."""
    monkeypatch.delenv(it.VARIABLE_CAPTURA)
    assert it.captura_activa()
    monkeypatch.setenv(it.VARIABLE_CAPTURA, '0')
    assert not it.captura_activa()


@pytest.mark.parametrize('funcion', ['cargas_ejecutar', '_correr_guion_ajuste', 'pf_verificar_base',
                                     'obras_ejecutar', 'estudios_ejecutar', 'transferencia_ejecutar',
                                     'guion_ejecutar'])
def test_cada_accion_nativa_de_la_web_registra_su_episodio(funcion):
    """024:RF-1 — toda acción nativa de la web pasa por el único punto de captura."""
    arbol = ast.parse((RAIZ / 'src' / 'igea_dgs' / 'web' / 'services.py').read_text(encoding='utf-8'))
    definicion = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == funcion)
    llamadas = {n.func.id for n in ast.walk(definicion)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert '_gemelo' in llamadas


def test_gemelo_de_la_web_con_la_lectura_del_guion(tmp_path, monkeypatch):
    """024:RF-1 — ``_gemelo`` lanza la lectura con el guion y deja el episodio en el búfer de
    ``IGEA_TWIN_DATA``."""
    from igea_dgs.web import services

    monkeypatch.setenv(it.VARIABLE_CAPTURA, '1')
    pedidos = []

    def guion(_ws, _ctx, script, plan, **_kw):
        pedidos.append((script, plan))
        return 0, _lectura(), tmp_path / 'lectura.json'

    monkeypatch.setattr(services, '_guion_pf', guion)

    class Ctx:
        def log(self, _m):
            pass

    class Ws:
        out_dir = tmp_path

    plan = {**_plan(), 'feeders': ['TA225', 'IN111'], 'folder': 'F'}
    out = services._gemelo(Ws(), Ctx(), plan, {'status': 'OK', 'converged': True, 'cuadrado': True},
                           caso='sin_proyecto', rutas={})
    assert pedidos[0][0] == 'digital_twin_snapshot_pf.py'
    assert pedidos[0][1]['feeders'] == ['TA225', 'IN111']
    assert out['clase'] == 'accepted'
    assert BuferEpisodios().leer(out['episode_id']).caso is Caso.SIN_PROYECTO
    assert json.loads(json.dumps(out))
    assert _flujo()  # el mismo flujo de prueba que la captura
