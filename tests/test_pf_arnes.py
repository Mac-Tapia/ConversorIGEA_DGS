"""Spec 019 — arnés de DIgSILENT: turno de la máquina y conexión común, sin DIgSILENT."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from igea_dgs import pf_arnes
from igea_dgs.pf_arnes import PFNoDisponible

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def turno(tmp_path, monkeypatch):
    ruta = tmp_path / 'powerfactory.turno'
    monkeypatch.setenv(pf_arnes.VARIABLE_TURNO, str(ruta))
    return ruta


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


def _tomar(**kw):
    kw.setdefault('abierto', lambda: [])
    return pf_arnes.tomar_turno('prueba.py', **kw)


def test_turno_exclusivo_y_se_suelta(turno):
    """019:RF-1 — el turno dice quién lo tiene y se suelta al terminar."""
    with pf_arnes.turno_del_motor('a.py', abierto=lambda: []):
        dueno = pf_arnes.leer_turno()
        assert dueno['pid'] == os.getpid() and dueno['guion'] == 'a.py' and dueno['desde']
    assert not turno.exists()


def test_espera_diciendo_quien_lo_tiene_y_se_rinde_al_limite(turno):
    """019:RF-2 — otro proceso vivo lo tiene: se espera avisando quién y, al límite, error."""
    turno.write_text(json.dumps({'pid': 4242, 'guion': 'obras_pf.py', 'desde': '17:00'}))
    reloj, avisos = Reloj(), []
    with pytest.raises(PFNoDisponible, match='obras_pf.py.*4242.*10 min'):
        _tomar(vivo=lambda pid: True, reloj=reloj, dormir=reloj.dormir, aviso=avisos.append)
    assert reloj.t >= pf_arnes.ESPERA_S
    assert avisos and 'obras_pf.py' in avisos[0] and 'esperando turno' in avisos[0]
    assert len(avisos) <= pf_arnes.ESPERA_S / pf_arnes.AVISO_S + 1, 'sin repetir el aviso a cada vuelta'


def test_espera_y_entra_cuando_queda_libre(turno):
    """019:RF-2 — en cuanto el otro suelta, entra."""
    turno.write_text(json.dumps({'pid': 4242, 'guion': 'x.py', 'desde': ''}))
    reloj = Reloj()

    def dormir(s):
        reloj.dormir(s)
        if reloj.t >= 10:
            turno.unlink(missing_ok=True)

    _tomar(vivo=lambda pid: True, reloj=reloj, dormir=dormir, aviso=lambda m: None)
    assert pf_arnes.leer_turno()['pid'] == os.getpid() and 10 <= reloj.t < 20


def test_dueno_muerto_se_libera_solo(turno):
    """019:RF-4 — una sonda cortada dejó el turno: su proceso ya no vive y se libera."""
    turno.write_text(json.dumps({'pid': 4242, 'guion': 'sonda.py', 'desde': ''}))
    avisos = []
    _tomar(vivo=lambda pid: False, aviso=avisos.append)
    assert pf_arnes.leer_turno()['pid'] == os.getpid()
    assert any('sonda.py' in a and 'liberado' in a for a in avisos)


def test_al_salir_el_turno_sigue_suyo_hasta_que_muere(turno):
    """019:RF-19 — soltado en ``atexit``, el motor aún se cierra: el siguiente espera a que
    el proceso muera, y pasado ``CIERRE_S`` entra igual."""
    pf_arnes.tomar_turno('powerfactory_acceptance.py', abierto=lambda: [])
    pf_arnes.soltar_turno(al_salir=True)
    dueno = pf_arnes.leer_turno()
    assert dueno['pid'] == os.getpid() and dueno['liberado'] > 0
    assert pf_arnes.servidor_vivo() is None
    # Lo «tiene» otro proceso (4242) que se despidió y sigue vivo: se espera hasta que muere.
    turno.write_text(json.dumps({**dueno, 'pid': 4242, 'inicio': None}))
    reloj, avisos, estado = Reloj(), [], {'vivo': True}

    def dormir(s):
        reloj.dormir(s)
        if reloj.t >= 6:
            estado['vivo'] = False

    _tomar(vivo=lambda pid: estado['vivo'], reloj=reloj, dormir=dormir, aviso=avisos.append,
           ahora=lambda: dueno['liberado'] + reloj.t)
    assert 6 <= reloj.t < 10 and pf_arnes.leer_turno()['pid'] == os.getpid()
    assert any('cerrando DIgSILENT' in a for a in avisos)
    # Sigue vivo más de ``CIERRE_S`` tras despedirse: se le toma el turno.
    turno.write_text(json.dumps({'pid': 4242, 'guion': 'x.py', 'desde': '', 'liberado': 0.0}))
    avisos.clear()
    _tomar(vivo=lambda pid: True, aviso=avisos.append, ahora=lambda: pf_arnes.CIERRE_S + 1)
    assert pf_arnes.leer_turno()['pid'] == os.getpid()
    assert any('no terminó de cerrarse' in a for a in avisos)


def test_pid_reutilizado_no_es_el_dueno(turno):
    """019:RF-19 — mismo pid con otro inicio: el dueño murió y Windows dio su número a otro."""
    dueno = {'pid': 4242, 'inicio': 111, 'guion': 'obras_pf.py'}
    assert not pf_arnes.dueno_vivo(dueno, lambda pid: True, lambda pid: 222)
    assert pf_arnes.dueno_vivo(dueno, lambda pid: True, lambda pid: 111)
    assert pf_arnes.dueno_vivo({'pid': 4242}, lambda pid: True, lambda pid: 222)
    propio = pf_arnes.inicio_proceso(os.getpid())
    assert propio is not None and propio == pf_arnes.inicio_proceso(os.getpid())
    turno.write_text(json.dumps(dueno))
    _tomar(vivo=lambda pid: True, inicio=lambda pid: 222, aviso=lambda m: None)
    assert pf_arnes.leer_turno()['pid'] == os.getpid()


def test_liberar_un_muerto_no_borra_el_turno_de_otro(turno):
    """019:RF-19 — quien llega tarde a liberar al muerto no borra el turno ya tomado."""
    muerto = {'pid': 4242, 'guion': 'sonda.py'}
    nuevo = {'pid': 5151, 'guion': 'obras_pf.py'}
    turno.write_text(json.dumps(nuevo))
    pf_arnes._borrar_si_sigue(turno, muerto)
    assert pf_arnes.leer_turno() == nuevo
    pf_arnes._borrar_si_sigue(turno, nuevo)
    assert not turno.exists()


def test_cerrar_servidor_solo_por_su_orden(turno, tmp_path, monkeypatch):
    """019:RF-20 — el corte retira su orden de la cola; cierra el servidor si la atendía o si
    no llegó a conectar, y no si atiende la de otro."""
    from igea_dgs import powerfactory_env

    cola = tmp_path / 'cola'
    cola.mkdir()
    monkeypatch.setenv(pf_arnes.VARIABLE_COLA, str(cola))
    cerrados = []
    monkeypatch.setattr(powerfactory_env, 'terminar_arbol', cerrados.append)
    servidor = {'pid': os.getpid(), 'inicio': pf_arnes.inicio_proceso(os.getpid()),
                'guion': pf_arnes.SERVIDOR, 'conectado': True}

    turno.write_text(json.dumps(servidor))
    (cola / 'mia.orden.json').write_text('{}')
    (cola / 'otra.en_curso.json').write_text('{}')
    assert pf_arnes.cerrar_servidor('mia') is None and cerrados == []
    assert not (cola / 'mia.orden.json').exists() and turno.exists()

    (cola / 'mia.en_curso.json').write_text('{}')
    assert pf_arnes.cerrar_servidor('mia') and cerrados == [os.getpid()]
    assert not turno.exists()

    turno.write_text(json.dumps({**servidor, 'conectado': None}))
    (cola / 'mia.en_curso.json').unlink()
    assert pf_arnes.cerrar_servidor('mia'), 'colgado al conectar: no atiende a nadie'
    assert len(cerrados) == 2


def test_conectar_anota_que_ya_conecto(turno):
    """019:RF-20 — tras responder DIgSILENT, el turno dice ``conectado``."""
    modulo, _estado = _modulo()
    pf_arnes.conectar('a.py', modulo=modulo, aviso=lambda m: None, abierto=lambda: [])
    assert pf_arnes.leer_turno()['conectado'] is True
    pf_arnes.soltar_turno()


def test_digsilent_abierto_a_mano_no_se_lanza():
    """019:RF-13 — con DIgSILENT abierto a mano se avisa y no se toma el turno."""
    with pytest.raises(PFNoDisponible, match='abierto a mano.*1234'):
        pf_arnes.tomar_turno('a.py', abierto=lambda: [1234])
    assert pf_arnes.leer_turno() is None


def test_dos_procesos_a_la_vez_se_turnan(turno, tmp_path):
    """019:RF-1 / 019:RF-2 — dos procesos reales: el segundo espera a que el primero suelte."""
    codigo = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(RAIZ / 'src')!r})
        from igea_dgs import pf_arnes
        with pf_arnes.turno_del_motor(sys.argv[1], abierto=lambda: []):
            print('dentro', sys.argv[1], time.time(), flush=True)
            time.sleep(float(sys.argv[2]))
            print('fuera', sys.argv[1], time.time(), flush=True)
    """)
    guion = tmp_path / 'turnarse.py'
    guion.write_text(codigo, encoding='utf-8')
    env = {**os.environ, pf_arnes.VARIABLE_TURNO: str(turno)}
    a = subprocess.Popen([sys.executable, str(guion), 'A', '3'], stdout=subprocess.PIPE,
                         text=True, env=env)
    import time
    time.sleep(1.0)
    b = subprocess.run([sys.executable, str(guion), 'B', '0'], capture_output=True, text=True,
                       env=env, timeout=60)
    salida_a, _ = a.communicate(timeout=60)
    fuera_a = float(next(line for line in salida_a.splitlines() if line.startswith('fuera')).split()[-1])
    dentro_b = float(next(line for line in b.stdout.splitlines() if line.startswith('dentro')).split()[-1])
    assert dentro_b >= fuera_a, 'B no entra hasta que A suelta el turno'
    assert 'esperando turno' in b.stdout


def _modulo(fallos=0, error='Exit with error code 4002'):
    estado = {'llamadas': 0}

    def GetApplicationExt():
        estado['llamadas'] += 1
        if estado['llamadas'] <= fallos:
            raise RuntimeError(error)
        return SimpleNamespace(GetCurrentUser=lambda: SimpleNamespace(loc_name='Operador'))

    return SimpleNamespace(GetApplicationExt=GetApplicationExt), estado


def test_conectar_reintenta_mientras_el_motor_siga_ocupado(capsys):
    """019:RF-3 / 019:RF-6 — 4002 se reintenta; la primera línea sale al responder."""
    modulo, estado = _modulo(fallos=2)
    reloj = Reloj()
    app = pf_arnes.conectar('a.py', modulo=modulo, reloj=reloj, dormir=reloj.dormir,
                            aviso=lambda m: None, abierto=lambda: [])
    assert estado['llamadas'] == 3 and app.GetCurrentUser().loc_name == 'Operador'
    assert 'Conectado a DIgSILENT como Operador' in capsys.readouterr().out
    pf_arnes.soltar_turno()


def test_conectar_otro_error_no_se_reintenta_y_suelta_el_turno():
    """019:RF-3 — un error que no es de motor ocupado no se reintenta, y el turno queda libre."""
    modulo, estado = _modulo(fallos=5, error='licencia caducada')
    with pytest.raises(PFNoDisponible, match='licencia caducada'):
        pf_arnes.conectar('a.py', modulo=modulo, aviso=lambda m: None, abierto=lambda: [])
    assert estado['llamadas'] == 1 and pf_arnes.leer_turno() is None


def test_caso_restituido():
    """019:RF-10 — al terminar queda activo el caso que lo estaba al empezar."""
    activo = {}

    class Caso:
        def __init__(self, n):
            self.n = n

        def Activate(self):
            activo['caso'] = self

    a, b = Caso('a'), Caso('b')
    activo['caso'] = a
    app = SimpleNamespace(GetActiveStudyCase=lambda: activo['caso'])
    with pf_arnes.caso_restituido(app):
        b.Activate()
    assert activo['caso'] is a


def test_ningun_guion_conecta_por_su_cuenta():
    """019:RF-5 — solo ``pf_arnes`` llama a ``GetApplicationExt``."""
    fuera = [str(p.relative_to(RAIZ)) for carpeta in ('tools', 'src')
             for p in (RAIZ / carpeta).rglob('*.py')
             if 'GetApplicationExt(' in p.read_text(encoding='utf-8', errors='replace')
             and p.name != 'pf_arnes.py']
    assert fuera == []


def test_el_servidor_ocioso_cede_el_turno(turno, tmp_path, monkeypatch):
    """019:RF-14 — con el servidor sin órdenes, el guion que espera le pide que se cierre;
    con una orden en curso, no (2026-10-18: cada sonda esperaba sus 2 minutos)."""
    cola = tmp_path / 'cola'
    cola.mkdir()
    monkeypatch.setenv(pf_arnes.VARIABLE_COLA, str(cola))
    servidor = {'pid': 4242, 'guion': pf_arnes.SERVIDOR, 'desde': ''}
    (cola / 'x.en_curso.json').write_text('{}')
    assert not pf_arnes.pedir_cierre_si_ocioso(servidor), 'con una orden en curso no se toca'
    (cola / 'x.en_curso.json').unlink()
    assert not pf_arnes.pedir_cierre_si_ocioso({'pid': 1, 'guion': 'obras_pf.py'})
    turno.write_text(json.dumps(servidor))
    reloj, avisos = Reloj(), []

    def dormir(s):
        reloj.dormir(s)
        if (cola / pf_arnes.CIERRE).exists():       # el servidor atiende el pedido
            turno.unlink(missing_ok=True)

    _tomar(vivo=lambda pid: True, reloj=reloj, dormir=dormir, aviso=avisos.append)
    assert pf_arnes.leer_turno()['pid'] == os.getpid() and reloj.t < pf_arnes.INACTIVIDAD_S
    assert any('019:RF-14' in a for a in avisos)


def test_la_salida_va_linea_a_linea():
    """019:RF-15 — redirigida a un fichero, la salida del guion no espera a llenar un bloque."""
    codigo = textwrap.dedent('''
        import sys, time
        from igea_dgs import pf_arnes
        pf_arnes.salida_sin_bufer()
        print('primera')
        time.sleep(30)
    ''')
    import tempfile
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as fichero:
        proc = subprocess.Popen([sys.executable, '-c', codigo], stdout=fichero,
                                env={**os.environ, 'PYTHONPATH': str(RAIZ / 'src')})
        try:
            import time
            fin = time.monotonic() + 20
            leido = ''
            while time.monotonic() < fin and 'primera' not in leido:
                time.sleep(0.2)
                fichero.seek(0)
                leido = fichero.read()
            assert 'primera' in leido
        finally:
            proc.kill()
            proc.wait()


def test_la_api_se_busca_en_la_instalacion(tmp_path, monkeypatch):
    """019:RF-16 — sin ``powerfactory`` en la ruta, se añade la carpeta de la instalación y
    se vuelve a importar; si tampoco está, se dice dónde se buscó."""
    monkeypatch.setattr(sys, 'path', list(sys.path))
    llamadas = []

    def importar(nombre):
        llamadas.append(str(tmp_path) in sys.path)
        if str(tmp_path) not in sys.path:
            raise ImportError("No module named 'powerfactory'")
        return 'api'

    assert pf_arnes.importar_api(importar, lambda: tmp_path) == 'api'
    assert llamadas == [False, True]
    monkeypatch.setattr(sys, 'path', [p for p in sys.path if p != str(tmp_path)])

    def nunca(nombre):
        raise ImportError('no está')

    with pytest.raises(PFNoDisponible, match=re.escape(str(tmp_path))):
        pf_arnes.importar_api(nunca, lambda: tmp_path)
    with pytest.raises(PFNoDisponible, match='no disponible'):
        pf_arnes.importar_api(nunca, lambda: None)
