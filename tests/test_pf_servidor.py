"""Spec 019, RF-7 a RF-9 — proceso que mantiene DIgSILENT abierto y su cliente, sin DIgSILENT."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
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


def test_la_orden_de_un_cliente_muerto_se_descarta(cola, servidor, monkeypatch, capsys):
    """019:RF-17 — la orden que dejó un cliente ya cortado no se ejecuta: la del cliente
    vivo, que esperaba detrás, se atiende enseguida."""
    atendidas = []
    monkeypatch.setattr(servidor, '_cargar', lambda guion: SimpleNamespace(
        main=lambda argv: atendidas.append(argv[0]) or 0))
    (cola / 'a.orden.json').write_text(json.dumps(
        {'id': 'a', 'guion': 'pf_proyectos.py', 'argv': ['huerfana'], 'cliente': 111}))
    (cola / 'b.orden.json').write_text(json.dumps(
        {'id': 'b', 'guion': 'pf_proyectos.py', 'argv': ['viva'], 'cliente': 222}))
    reloj = Reloj()
    assert servidor.servir(1.0, reloj=reloj, dormir=reloj.dormir,
                           vivo=lambda pid: pid == 222) == 0
    assert atendidas == ['viva']
    assert not (cola / 'a.log').exists() and not list(cola.glob('a.*'))
    assert 'Orden a descartada' in capsys.readouterr().out


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


def test_todo_guion_que_conecta_va_por_el_servidor():
    """019:RF-7 — un guion con ``conectar`` y ``main`` fuera de la lista cierra el servidor y
    abre DIgSILENT por su cuenta (2026-10-23: la lectura del gemelo tras cada ajuste de
    AL105 + AL108 sumaba 2,5 min, y la acción siguiente volvía a esperar 73 s de conexión)."""
    con_conexion = {p.name for p in (RAIZ / 'tools').glob('*.py')
                    if "conectar('" in (texto := p.read_text(encoding='utf-8'))
                    and 'def main(' in texto}
    assert con_conexion - pf_arnes.GUIONES_SERVIBLES == set()


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

    def tomada(c):                          # el servidor la tomó y murió a mitad
        for o in c.glob('*.orden.json'):
            o.replace(o.with_name(o.name.replace('.orden.json', '.en_curso.json')))
        return True

    assert cliente.enviar('verificar_pf.py', [], cola, dormir=lambda s: None,
                          asegurar=tomada) == 3
    assert 'terminó sin acabar la orden' in capsys.readouterr().out


def test_orden_en_la_cola_de_un_servidor_que_se_cerro_arranca_otro(cola, cliente, servidor,
                                                                   monkeypatch):
    """019:RF-22 — el servidor se cerró por inactividad justo al dejar la orden: el cliente
    arranca otro en vez de fallar; si no puede, código 3 y la orden se retira."""
    vivo = {'servidor': None}
    arrancados = []
    monkeypatch.setattr(pf_arnes, 'servidor_vivo', lambda ruta=None: vivo['servidor'])
    monkeypatch.setattr(servidor, '_cargar', lambda guion: SimpleNamespace(
        main=lambda argv: print('hecho') or 0))

    def asegurar(c):
        arrancados.append(1)
        vivo['servidor'] = {'pid': 1}
        threading.Thread(target=servidor.servir, args=(1.0,), daemon=True).start()
        return True

    assert cliente.enviar('verificar_pf.py', [], cola, asegurar=asegurar) == 0
    assert arrancados == [1]
    vivo['servidor'] = None
    assert cliente.enviar('verificar_pf.py', [], cola, dormir=lambda s: None,
                          asegurar=lambda c: False) == 3
    assert not list(cola.glob('*.orden.json'))


def test_el_cliente_dice_que_espera_detras_de_otra_orden(cola, cliente, monkeypatch, capsys):
    """019:RF-22 — con su orden en fila tras la de otro, lo dice (la web no lo corta)."""
    monkeypatch.setattr(pf_arnes, 'servidor_vivo', lambda ruta=None: {'pid': 1})
    (cola / 'otra.en_curso.json').write_text(json.dumps({'guion': 'ajuste_cabecera_pf.py'}))
    reloj = Reloj()

    def dormir(s):
        reloj.dormir(s)
        if reloj.t > 3:                      # el servidor acaba la otra y atiende esta
            (cola / 'otra.en_curso.json').unlink(missing_ok=True)
            for o in cola.glob('*.orden.json'):
                ident = o.name[:-len('.orden.json')]
                o.unlink()
                (cola / f'{ident}.fin.json').write_text('{"codigo": 0}')

    assert cliente.enviar('verificar_pf.py', [], cola, dormir=dormir, reloj=reloj,
                          ident='mia') == 0
    salida = capsys.readouterr().out
    assert 'atiende otra orden (ajuste_cabecera_pf.py)' in salida
    assert salida.count('atiende otra orden') == 1, 'sin repetir el aviso a cada vuelta'


def test_el_servidor_arranca_con_la_cola_limpia(cola, servidor):
    """019:RF-21 — la orden que dejó a medias el servidor anterior acaba con código 3 para
    su cliente; los restos de más de un día se borran; una orden ilegible no lo tumba."""
    (cola / 'medias.en_curso.json').write_text('{}')
    antiguo = time.time() - servidor.RESTOS_S - 60
    for viejo in ('a.log', 'a.fin.json', 'b.tmp', 'servidor.log'):
        (cola / viejo).write_text('x')
        os.utime(cola / viejo, (antiguo, antiguo))
    (cola / 'reciente.log').write_text('x')
    servidor.limpiar_cola(cola)
    assert json.loads((cola / 'medias.fin.json').read_text())['codigo'] == 3
    assert 'murió a mitad' in (cola / 'medias.log').read_text(encoding='utf-8')
    assert not any((cola / n).exists()
                   for n in ('a.log', 'a.fin.json', 'b.tmp', 'medias.en_curso.json'))
    assert (cola / 'servidor.log').exists() and (cola / 'reciente.log').exists()

    (cola / 'rota.orden.json').write_text('{no es json')
    reloj = Reloj()
    assert servidor.servir(1.0, reloj=reloj, dormir=reloj.dormir) == 0
    assert not list(cola.glob('rota.*'))


def test_el_servidor_no_cuelga_del_cliente(cola, cliente, tmp_path, monkeypatch):
    """019:RF-20 — el servidor arranca fuera del árbol del cliente: ``taskkill /T`` sobre un
    cliente cortado no se lleva la orden que atiende para otro."""
    falso = tmp_path / 'herramientas'
    falso.mkdir()
    (falso / pf_arnes.SERVIDOR).write_text('import time\ntime.sleep(60)\n', encoding='utf-8')
    monkeypatch.setattr(cliente, 'HERE', falso)
    proceso = cliente._lanzar_servidor(cola)
    try:
        assert proceso.poll() is None
        padres = {p['pid']: p['ppid'] for p in powerfactory_env.procesos()}
        cadena, pid = [], proceso.pid
        while pid in padres and pid not in cadena:
            cadena.append(pid)
            pid = padres[pid]
        assert os.getpid() not in cadena, 'el servidor sigue colgando de este proceso'
    finally:
        powerfactory_env.terminar_arbol(proceso.pid)


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
    monkeypatch.setattr(pf_arnes, 'cerrar_servidor',
                        lambda orden=None: cerrados.append(orden) or {'pid': 1})
    (tmp_path / 'verificar_pf.py').write_text('', encoding='utf-8')
    (tmp_path / 'pf_cliente.py').write_text(
        "import time\nprint('Conectado', flush=True)\ntime.sleep(60)\n", encoding='utf-8')
    ctx, registro = _contexto_real()
    rc = ctx.run_process([sys.executable, str(tmp_path / 'verificar_pf.py')],
                         env={**os.environ, 'PF_PYTHON': 'x', 'IGEA_PF_SERVIDOR': '1'},
                         limite_s=2)
    assert rc == TIEMPO_AGOTADO and len(cerrados) == 1 and cerrados[0]
    assert any('Se cierra el proceso de DIgSILENT' in l for l in registro)


def test_el_reintento_vuelve_a_pasar_por_el_servidor(tmp_path, monkeypatch):
    """019:RF-20 — el reintento de la web tras un guion mudo usa la orden original: vuelve
    al cliente con otra orden y, si también se corta, cierra el servidor colgado."""
    from test_carpeta_pf import _contexto_real
    from igea_dgs.web import jobs

    monkeypatch.setattr(powerfactory_env, 'cerrar_guiones_pf_huerfanos', lambda: [])
    monkeypatch.setattr(powerfactory_env, 'powerfactory_abierto', lambda: [])
    monkeypatch.setattr(jobs, 'LIMITE_ARRANQUE_PF_S', 1.0)
    cerrados = []
    monkeypatch.setattr(pf_arnes, 'cerrar_servidor',
                        lambda orden=None: cerrados.append(orden) or None)
    (tmp_path / 'verificar_pf.py').write_text('', encoding='utf-8')
    (tmp_path / 'pf_cliente.py').write_text('import time\ntime.sleep(60)\n', encoding='utf-8')
    ctx, registro = _contexto_real()
    with pytest.raises(jobs.PowerFactorySinRespuesta):
        ctx.run_process([sys.executable, str(tmp_path / 'verificar_pf.py')],
                        env={**os.environ, 'PF_PYTHON': 'x', 'IGEA_PF_SERVIDOR': '1'})
    lanzados = [l for l in registro if l.startswith('$ ')]
    assert len(lanzados) == 2 and all('pf_cliente.py' in l for l in lanzados)
    assert 'pf_cliente.py' not in lanzados[1].split('pf_cliente.py', 1)[1]
    assert len(cerrados) == 2 and cerrados[0] != cerrados[1]


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
