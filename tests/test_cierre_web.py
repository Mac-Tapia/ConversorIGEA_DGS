"""Spec 081: por qué se cerró la web, y las dos vías demostradas por las que se cerraba sola."""
from __future__ import annotations

import pytest

from convertersmartgrid.asistente import almacen
from convertersmartgrid.web import __main__ as lanzador
from convertersmartgrid.web import app as app_mod
from convertersmartgrid.web import cierre
from convertersmartgrid.web.runtime import huella_del_codigo
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))


def test_cada_arranque_y_cierre_con_su_motivo():
    """081:RF-42 — quién lo pidió y por qué, en un registro; la primera vez no hay nada que avisar."""
    assert cierre.anotar_arranque('h1') == []
    cierre.anotar_cierre('otra versión del código (lanzador 9)', quien='lanzador 9')
    filas = almacen.leer(cierre.REGISTRO)
    assert [f['evento'] for f in filas] == ['arranque', 'cierre']
    assert filas[1]['motivo'].startswith('otra versión') and filas[1]['quien'] == 'lanzador 9'
    assert cierre.anotar_arranque('h1', vivo=lambda _f: False) == []


def test_caida_sin_cierre_se_avisa_al_arrancar():
    """081:RF-43 — el fallo real: la web cayó y nadie supo por qué. El siguiente arranque lo dice."""
    cierre.anotar_arranque('h1')
    almacen.anotar(cierre.REGISTRO, {'evento': cierre.ARRANQUE, 'pid': 777777})
    avisos = cierre.anotar_arranque('h1', vivo=lambda f: f['pid'] != 777777)
    assert len(avisos) == 1 and avisos[0]['nivel'] == 'error' and '777777' in avisos[0]['texto']
    assert almacen.leer('avisos')[-1]['texto'] == avisos[0]['texto']
    # No se avisa dos veces, y la otra web de otra carpeta sigue viva: no es una caída.
    assert cierre.anotar_arranque('h1', vivo=lambda f: f['pid'] != 777777) == []


def test_la_peticion_de_cierre_deja_su_motivo(tmp_path, monkeypatch):
    """081:RF-42 — el motivo que manda el lanzador llega al cierre del servidor, también con la vigilancia encendida."""
    monkeypatch.setattr(app_mod, '_cierre', [lambda: None])
    monkeypatch.setattr(app_mod, '_motivo_cierre', [])
    monkeypatch.setenv('CSG_ASISTENTE_VIGILANCIA', '1')
    monkeypatch.setattr(app_mod, 'arrancar_vigilancia', lambda _jobs: type('V', (), {'parar': lambda self: None})())
    with TestClient(app_mod.create_app(tmp_path), client=('127.0.0.1', 50000)) as cliente:
        r = cliente.post('/api/sistema/cerrar', headers={app_mod.CABECERA_LANZADOR: '1', app_mod.CABECERA_MOTIVO: 'otra version'})
        assert r.status_code == 202
    filas = almacen.leer(cierre.REGISTRO)
    assert [f['evento'] for f in filas] == ['arranque', 'cierre'] and filas[1]['motivo'] == 'otra version'


def test_sin_peticion_se_dice_que_fue_senal_o_ventana(tmp_path, monkeypatch):
    """081:RF-42 — cerrar sin pedirlo también deja fila: una señal o la ventana. Solo falta si lo matan."""
    monkeypatch.setattr(app_mod, '_motivo_cierre', [])
    monkeypatch.setenv('CSG_ASISTENTE_VIGILANCIA', '1')
    monkeypatch.setattr(app_mod, 'arrancar_vigilancia', lambda _jobs: type('V', (), {'parar': lambda self: None})())
    with TestClient(app_mod.create_app(tmp_path)):
        pass
    assert 'señal' in almacen.leer(cierre.REGISTRO)[-1]['motivo']


def test_quien_termina_a_la_fuerza_lo_escribe():
    """081:RF-42 — ``taskkill /F`` no le deja hacerlo al servidor: lo anota el lanzador, con el proceso que termina."""
    lanzador._anotar_terminado(555, 'no respondió en 60 s')
    fila = almacen.leer(cierre.REGISTRO)[-1]
    assert fila['pid'] == 555 and fila['motivo'] == 'no respondió en 60 s' and fila['quien'].startswith('lanzador ')


def _salud(raiz):
    return {'slots': {}, 'version': 'x', 'servidor': {'pid': 1, 'huella': 'otra', 'trabajos_en_curso': 0,
                                                      'raiz': raiz, 'paginas_abiertas': 0}}


def test_un_lanzador_de_otra_carpeta_no_cierra_la_web(monkeypatch, capsys):
    """081:RF-44 — la vía demostrada: otro worktree, con otra huella, cerraba la web del operador. Ahora, puerto siguiente."""
    monkeypatch.setattr(lanzador, 'conversor_en', lambda *_a, **_k: _salud('D:/otra/carpeta'))
    monkeypatch.setattr(lanzador, 'pedir_cierre', lambda *_a, **_k: pytest.fail('no debe pedir cerrar'))
    monkeypatch.setattr(lanzador, '_terminar', lambda *_a: pytest.fail('no debe terminar'))
    monkeypatch.setattr(lanzador, 'puerto_libre_siguiente', lambda *_a: 8766)
    assert lanzador.resolver_puerto('127.0.0.1', 8765, abrir=False) == ('arrancar', 8766)
    assert 'otra carpeta' in capsys.readouterr().out
    monkeypatch.setattr(lanzador, 'puerto_libre_siguiente', lambda *_a: None)
    assert lanzador.resolver_puerto('127.0.0.1', 8765, abrir=False) == ('salir', 2)


def test_la_misma_carpeta_con_otro_codigo_se_sigue_sustituyendo(monkeypatch):
    """081:RF-44, 001:RF-29 — tras cambiar el código, el acceso directo sigue reemplazando la web."""
    from convertersmartgrid.powerfactory_env import project_root

    pedidos = []
    monkeypatch.setattr(lanzador, 'conversor_en', lambda *_a, **_k: _salud(str(project_root())))
    monkeypatch.setattr(lanzador, 'pedir_cierre', lambda url, motivo: pedidos.append(motivo) or True)
    monkeypatch.setattr(lanzador, 'esperar_puerto_libre', lambda *_a: True)
    monkeypatch.setattr(lanzador, 'puerto_ocupado', lambda *_a: False)
    assert lanzador.resolver_puerto('127.0.0.1', 8765, abrir=False) == ('arrancar', 8765)
    assert pedidos == ['otra versión del código']


def test_la_salud_dice_de_que_carpeta_es(tmp_path):
    """081:RF-44 — es lo que mira el lanzador."""
    from convertersmartgrid.powerfactory_env import project_root

    assert TestClient(app_mod.create_app(tmp_path)).get('/api/health').json()['servidor']['raiz'] == str(project_root())
    assert huella_del_codigo(app_mod.frontend_dist()) is not None


def test_no_se_termina_sin_dar_un_plazo(monkeypatch):
    """081:RF-45 — la otra vía: ``taskkill /F`` tras 8 s sin contestar, por una noche cargada. Se le da un plazo, y si contesta sigue."""
    esperas, terminados = [], []
    monkeypatch.setattr(lanzador, 'conversor_en', lambda *_a, **_k: None)
    monkeypatch.setattr(lanzador, 'quien_escucha', lambda _p: (4242, 'python -m convertersmartgrid.web'))
    monkeypatch.setattr(lanzador, 'esperar_respuesta', lambda _u, s: esperas.append(s) or None)
    monkeypatch.setattr(lanzador, '_terminar', terminados.append)
    monkeypatch.setattr(lanzador, 'esperar_puerto_libre', lambda *_a: True)
    monkeypatch.setattr(lanzador, 'puerto_ocupado', lambda *_a: False)
    from convertersmartgrid.web import jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, 'trabajos_anotados', lambda _p: 0)
    assert lanzador.resolver_puerto('127.0.0.1', 8765, abrir=False) == ('arrancar', 8765)
    assert esperas == [lanzador.ESPERA_SIN_RESPUESTA_S] and lanzador.ESPERA_SIN_RESPUESTA_S >= 60 and terminados == [4242]
    assert 'no respondió' in almacen.leer(cierre.REGISTRO)[-1]['motivo']
    # Si contesta durante el plazo, no se termina nada.
    terminados.clear()
    from convertersmartgrid.powerfactory_env import project_root

    respuesta = _salud(str(project_root()))
    respuesta['servidor']['huella'] = huella_del_codigo(app_mod.frontend_dist())
    monkeypatch.setattr(lanzador, 'esperar_respuesta', lambda _u, _s: respuesta)
    assert lanzador.resolver_puerto('127.0.0.1', 8765, abrir=False) == ('salir', 0) and terminados == []
