"""Spec 019, RF-7 a RF-9 — proceso que mantiene DIgSILENT abierto y su cliente, sin DIgSILENT."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from apoyo import cargar_herramienta
from igea_dgs import carpeta_pf, pf_arnes, powerfactory_env

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def cola(tmp_path, monkeypatch):
    monkeypatch.setenv(pf_arnes.VARIABLE_TURNO, str(tmp_path / 'turno'))
    monkeypatch.setenv(pf_arnes.VARIABLE_COLA, str(tmp_path / 'cola'))
    (tmp_path / 'cola').mkdir()
    return tmp_path / 'cola'


@pytest.fixture
def servidor():
    return cargar_herramienta('pf_servidor.py', 'pf_servidor_prueba', tools_en_path=True)


@pytest.fixture
def cliente():
    return cargar_herramienta('pf_cliente.py', 'pf_cliente_prueba', tools_en_path=True)


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


def _orden(cola, ident, guion='verificar_pf.py', argv=()):
    (cola / f'{ident}.orden.json').write_text(json.dumps(
        {'id': ident, 'guion': guion, 'argv': list(argv)}), encoding='utf-8')


def test_dos_ordenes_con_una_sola_conexion_y_cierre_por_inactividad(cola, servidor, monkeypatch):
    """019:RF-7 / 019:RF-8 — el servidor atiende las órdenes en su proceso con su conexión
    (el guion no vuelve a conectar) y, sin órdenes 2 minutos, se cierra."""
    conexiones = []
    app = SimpleNamespace(GetCurrentUser=lambda: SimpleNamespace(loc_name='Operador'))
    pf_arnes.compartir_app(app)

    def main(argv):
        conexiones.append(pf_arnes.conectar('verificar_pf.py') is app)
        print('trabajando', *argv)
        return 7

    monkeypatch.setattr(servidor, '_cargar', lambda guion: SimpleNamespace(main=main))
    _orden(cola, 'a', argv=['--plan', 'p1'])
    _orden(cola, 'b', argv=['--plan', 'p2'])
    reloj = Reloj()
    try:
        assert servidor.servir(120.0, reloj=reloj, dormir=reloj.dormir) == 0
    finally:
        pf_arnes.compartir_app(None)
    assert conexiones == [True, True]
    for ident, plan in (('a', 'p1'), ('b', 'p2')):
        log = (cola / f'{ident}.log').read_text(encoding='utf-8')
        assert 'proceso que se queda abierto' in log and f'trabajando --plan {plan}' in log
        assert json.loads((cola / f'{ident}.fin.json').read_text())['codigo'] == 7
    assert reloj.t >= 120.0 and not list(cola.glob('*.orden.json'))


def test_una_orden_que_revienta_no_tumba_el_servidor(cola, servidor, monkeypatch):
    """019:RF-8 — un guion que lanza una excepción da código 1 con su traza; el servidor sigue."""
    def main(argv):
        raise RuntimeError('fallo del guion')

    monkeypatch.setattr(servidor, '_cargar', lambda guion: SimpleNamespace(main=main))
    _orden(cola, 'x')
    assert servidor.atender({'id': 'x', 'guion': 'verificar_pf.py', 'argv': []}, cola) == 1
    assert 'fallo del guion' in (cola / 'x.log').read_text(encoding='utf-8')


def test_el_servidor_solo_atiende_sus_guiones(servidor):
    """019:RF-7 — la aceptación y otros guiones siguen en su propio proceso."""
    with pytest.raises(ValueError, match='no atiende'):
        servidor._cargar('powerfactory_acceptance.py')


def test_el_cliente_reescribe_la_salida_y_devuelve_el_codigo(cola, cliente, servidor, monkeypatch):
    """019:RF-7 — la web ve la salida del guion línea a línea y su código, como si lo lanzara."""
    monkeypatch.setattr(pf_arnes, 'servidor_vivo', lambda ruta=None: {'pid': 1})
    monkeypatch.setattr(servidor, '_cargar', lambda guion: SimpleNamespace(
        main=lambda argv: print('Conectado a DIgSILENT como X.', 'linea', *argv) or 2))
    hilo = threading.Thread(target=servidor.servir, args=(1.5,), daemon=True)
    hilo.start()
    salida = []
    monkeypatch.setattr(sys.stdout, 'write', lambda s: salida.append(s) or len(s))
    codigo = cliente.enviar('verificar_pf.py', ['--plan', 'p'], cola)
    hilo.join(timeout=10)
    assert codigo == 2 and 'linea --plan p' in ''.join(salida)
    assert not list(cola.glob('*.log')) and not list(cola.glob('*.fin.json'))


def test_el_cliente_avisa_si_el_servidor_muere(cola, cliente, monkeypatch, capsys):
    """019:RF-8 — sin servidor vivo a mitad de la orden, error y código 3."""
    monkeypatch.setattr(pf_arnes, 'servidor_vivo', lambda ruta=None: None)
    assert cliente.enviar('verificar_pf.py', [], cola, dormir=lambda s: None) == 3
    assert 'terminó sin acabar la orden' in capsys.readouterr().out


def test_asegurar_servidor_lo_arranca_o_espera_su_turno(cola, cliente, monkeypatch, capsys):
    """019:RF-2 / 019:RF-7 — con el turno libre arranca el servidor; con el turno de otro
    proceso vivo, espera diciendo quién y se rinde al límite."""
    vivo = {'servidor': None}
    lanzados = []

    def lanzar(c):
        lanzados.append(c)
        vivo['servidor'] = {'pid': 1, 'guion': pf_arnes.SERVIDOR}
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(pf_arnes, 'servidor_vivo', lambda ruta=None: vivo['servidor'])
    reloj = Reloj()
    assert cliente.asegurar_servidor(cola, lanzar=lanzar, reloj=reloj, dormir=reloj.dormir)
    assert len(lanzados) == 1

    vivo['servidor'] = None
    turno = Path(os.environ[pf_arnes.VARIABLE_TURNO])
    turno.write_text(json.dumps({'pid': os.getpid(), 'guion': 'obras_pf.py', 'desde': '17:00'}))
    reloj = Reloj()
    assert not cliente.asegurar_servidor(cola, 60.0, lanzar=lanzar, reloj=reloj,
                                         dormir=reloj.dormir)
    salida = capsys.readouterr().out
    assert 'ocupado por obras_pf.py' in salida and 'sigue ocupado' in salida
    assert len(lanzados) == 1, 'con el turno de otro no se arranca otro servidor'


def test_el_proyecto_activo_no_se_vuelve_a_activar(monkeypatch):
    """019:RF-7 — en el servidor, el proyecto de la orden anterior sigue activo."""
    activaciones = []
    proyecto = SimpleNamespace(GetFullName=lambda: r'\U\C\P.IntPrj',
                               Activate=lambda: activaciones.append(1))
    monkeypatch.setattr(carpeta_pf, 'buscar_proyecto', lambda app, ruta, carpeta: proyecto)
    app = SimpleNamespace(GetActiveProject=lambda: None)
    assert carpeta_pf.activar_proyecto(app, 'P', 'C') is proyecto and activaciones == [1]
    app = SimpleNamespace(GetActiveProject=lambda: proyecto)
    assert carpeta_pf.activar_proyecto(app, 'P', 'C') is proyecto and activaciones == [1]


def test_el_servidor_no_es_un_huerfano_que_cerrar():
    """019:RF-7 — vive sin su cliente a propósito: la limpieza de huérfanos no lo cierra."""
    lista = [{'pid': 10, 'ppid': 999, 'name': 'python.exe',
              'cmd': r'python D:\x\tools\pf_servidor.py'},
             {'pid': 11, 'ppid': 999, 'name': 'python.exe', 'cmd': r'python D:\x\tools\obras_pf.py'}]
    huerfanos = powerfactory_env.guiones_pf_huerfanos(lista, {'pf_servidor.py', 'obras_pf.py'}, 1)
    assert [h['pid'] for h in huerfanos] == [11]


def test_la_web_manda_los_guiones_al_servidor(cola, monkeypatch):
    """019:RF-7 — ``run_process`` lanza el cliente en lugar del guion; ``IGEA_PF_SERVIDOR=0``
    lo apaga."""
    from test_carpeta_pf import _contexto_real

    monkeypatch.setattr(powerfactory_env, 'cerrar_guiones_pf_huerfanos', lambda: [])
    ctx, registro = _contexto_real()
    guion = str(RAIZ / 'tools' / 'verificar_pf.py')
    env = {**os.environ, 'PF_PYTHON': 'x'}
    for apagado, esperado in (('0', 'verificar_pf.py --help'), ('1', 'pf_cliente.py')):
        env['IGEA_PF_SERVIDOR'] = apagado
        ctx.run_process([sys.executable, guion, '--help'], env=env, limite_arranque_s=60)
        assert any(l.startswith('$ ') and esperado in l for l in registro), (apagado, registro)


def test_orden_cortada_cierra_el_servidor(tmp_path, monkeypatch):
    """019:RF-9 — si la web corta la orden (límite o cancelación), cierra también el proceso
    de DIgSILENT que la atendía."""
    from test_carpeta_pf import _contexto_real
    from igea_dgs.web.jobs import TIEMPO_AGOTADO

    monkeypatch.setattr(powerfactory_env, 'cerrar_guiones_pf_huerfanos', lambda: [])
    cerrados = []
    monkeypatch.setattr(pf_arnes, 'cerrar_servidor', lambda: cerrados.append(1) or {'pid': 1})
    (tmp_path / 'verificar_pf.py').write_text('', encoding='utf-8')
    (tmp_path / 'pf_cliente.py').write_text(
        "import time\nprint('Conectado', flush=True)\ntime.sleep(60)\n", encoding='utf-8')
    ctx, registro = _contexto_real()
    rc = ctx.run_process([sys.executable, str(tmp_path / 'verificar_pf.py')],
                         env={**os.environ, 'PF_PYTHON': 'x', 'IGEA_PF_SERVIDOR': '1'},
                         limite_s=2)
    assert rc == TIEMPO_AGOTADO and cerrados == [1]
    assert any('Se cierra el proceso de DIgSILENT' in l for l in registro)


def test_el_servidor_se_cierra_si_otro_pide_el_motor(cola, servidor):
    """019:RF-14 — sin órdenes y con el pedido de cierre, el servidor termina enseguida y se
    lo dice; un pedido viejo de antes de arrancar no lo cierra."""
    reloj = Reloj()
    (cola / pf_arnes.CIERRE).write_text('1')

    def dormir(s):
        reloj.dormir(s)
        if reloj.t >= 5 and not (cola / pf_arnes.CIERRE).exists() and reloj.t < 6:
            (cola / pf_arnes.CIERRE).write_text('2')

    assert servidor.servir(120.0, reloj=reloj, dormir=dormir) == 0
    assert 5 <= reloj.t < 120, 'no espera la inactividad'
    assert not (cola / pf_arnes.CIERRE).exists()
