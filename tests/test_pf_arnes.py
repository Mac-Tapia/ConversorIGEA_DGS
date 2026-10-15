"""Spec 019 — arnés de DIgSILENT: turno de la máquina y conexión común, sin DIgSILENT."""
from __future__ import annotations

import json
import os
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
