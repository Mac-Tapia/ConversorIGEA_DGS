"""Spec 108 T12 — el armado de la empresa modelo en cola: cancelable entre sistemas, independiente por sistema y con
el manifiesto escrito siempre (108:RF-1, 108:RF-5, 108:RF-7; P6 y P7). Y el guion ``tools/vad_estudio.py``.

Sistemas y empresas sintéticos, sorteados con semilla; ningún nombre, código ni periodo de una empresa real.
"""
from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from convertersmartgrid.perfil_empresa import PerfilEmpresa
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad.estudio import crear_estudio

RAIZ = Path(__file__).resolve().parents[1]
EMPRESAS = (PerfilEmpresa(nombre='Distribuidora Sintética Norte'), PerfilEmpresa(nombre='Eléctrica Ficticia del Sur'))
SEMILLA = 108_12


def _trabajo():
    assert importlib.util.find_spec('convertersmartgrid.vad.trabajo') is not None, 'falta vad/trabajo.py (108 T12)'
    from convertersmartgrid.vad import trabajo
    return trabajo


class _Cancelado(Exception):
    pass


_Cancelado.__name__ = 'JobCancelled'  # el nombre de la cancelación del carril, sin importar la web


class _Ctx:
    """El JobContext del carril: cancelar es activar un Event; check_cancel lanza la cancelación."""

    def __init__(self, cancelar_en: int | None = None):
        self.cancel = threading.Event()
        self.cancelar_en = cancelar_en
        self.avances, self.lineas = [], []

    def check_cancel(self):
        if self.cancel.is_set():
            raise _Cancelado()

    def progress(self, index, total, label=''):
        self.avances.append((index, total, label))
        if self.cancelar_en is not None and index + 1 == self.cancelar_en:
            self.cancel.set()

    def log(self, text):
        self.lineas.append(text)


def _estudio(tmp_path, perfil=EMPRESAS[0]):
    e = crear_estudio(tmp_path, perfil, grupo=1, periodo='2041-2045', version_tdr='tdr-sintetico')
    return tmp_path, e.id


def _sistemas(n, rng):
    return {f'S{rng.randint(100, 999)}-{i}': {'medir': rng.uniform(1, 10)} for i in range(n)}


@pytest.mark.parametrize('perfil', EMPRESAS, ids=('norte', 'sur'))
def test_108_rf1_cada_sistema_se_arma_y_el_manifiesto_dice_ok_o_fail(tmp_path, perfil):
    """108:RF-1, 108:RF-7 — P6: un sistema cuyo paso falla queda FAIL con el paso y el error, y los demás siguen; el
    manifiesto lleva la empresa, el grupo, el periodo, la versión del TdR y el estado del estudio."""
    trabajo = _trabajo()
    espacio, id_estudio = _estudio(tmp_path, perfil)
    rng = random.Random(SEMILLA)
    entradas = _sistemas(rng.randint(3, 6), rng)
    malo = rng.choice(list(entradas))

    def medir(sistema, valor):
        if sistema == malo:
            raise ValueError('dato imposible')
        return {'doble': 2 * valor}
    ctx = _Ctx()
    m = trabajo.armar_empresa_modelo(ctx, espacio, id_estudio, entradas, [('medir', medir), ('otro', medir)])
    assert m['terminado'] and not m['cancelado']
    assert m['empresa'] == perfil.nombre and m['grupo'] == 1 and m['periodo'] == '2041-2045'
    assert m['estado_estudio'] == 'pendiente_de_comprobar' and m['version_tdr'] == 'tdr-sintetico'
    for s, r in m['sistemas'].items():
        if s == malo:
            assert r['estado'] == 'FAIL' and r['paso'] == 'medir' and 'dato imposible' in r['error']
        else:
            assert r['estado'] == 'OK' and r['pasos']['medir']['doble'] == pytest.approx(2 * entradas[s]['medir'])
            assert r['sin_entrada'] == ['otro'], 'un paso sin entrada en el caso no se inventa'
    en_disco = json.loads((espacio / 'vad' / id_estudio / 'manifiesto.json').read_text(encoding='utf-8'))
    assert en_disco == m
    assert [a[0] for a in ctx.avances] == list(range(len(entradas) + 1))


def test_108_rf1_cancelar_entre_sistemas_deja_el_manifiesto_escrito(tmp_path):
    """108:RF-1 — P7: el armado comprueba la cancelación entre sistemas; al cancelar, los sistemas armados quedan con
    su estado, los que no llegaron quedan CANCELADO y el manifiesto está escrito."""
    trabajo = _trabajo()
    espacio, id_estudio = _estudio(tmp_path)
    entradas = _sistemas(5, random.Random(SEMILLA + 1))
    vistos = []
    ctx = _Ctx(cancelar_en=2)
    with pytest.raises(_Cancelado):
        trabajo.armar_empresa_modelo(ctx, espacio, id_estudio, entradas,
                                     [('medir', lambda s, v: vistos.append(s) or {'v': v})])
    m = json.loads((espacio / 'vad' / id_estudio / 'manifiesto.json').read_text(encoding='utf-8'))
    assert m['cancelado'] and not m['terminado']
    estados = [m['sistemas'][s]['estado'] for s in entradas]
    assert estados == ['OK', 'OK', 'CANCELADO', 'CANCELADO', 'CANCELADO'] and vistos == list(entradas)[:2]


def test_108_rf1_el_manifiesto_se_escribe_aunque_el_trabajo_falle(tmp_path):
    """108:RF-1 — un error que no es de un sistema (se acaba la memoria, se cae el proceso) también deja el manifiesto,
    con el error; sin sistemas o sin pasos no hay armado."""
    trabajo = _trabajo()
    espacio, id_estudio = _estudio(tmp_path)
    entradas = _sistemas(3, random.Random(SEMILLA + 2))

    def revienta(s, v):
        raise MemoryError('sin memoria')
    with pytest.raises(MemoryError):
        trabajo.armar_empresa_modelo(_Ctx(), espacio, id_estudio, entradas, [('medir', revienta)])
    m = json.loads((espacio / 'vad' / id_estudio / 'manifiesto.json').read_text(encoding='utf-8'))
    assert 'MemoryError' in m['error'] and not m['cancelado'] and not m['terminado']
    with pytest.raises(VadError, match='ningún sistema'):
        trabajo.armar_empresa_modelo(_Ctx(), espacio, id_estudio, {}, [('medir', revienta)])
    with pytest.raises(VadError, match='al menos un paso'):
        trabajo.armar_empresa_modelo(_Ctx(), espacio, id_estudio, entradas, [])


def test_108_rf5_el_guion_arma_un_caso_con_el_anexo2_y_su_ayuda_no_necesita_digsilent(tmp_path):
    """108:RF-5, 108:RF-1 — `tools/vad_estudio.py --help` sale con 0 sin importar DIgSILENT, y con un caso sintético
    (sistemas.json y las tablas de un sistema) valida el anexo 2 de cada sistema y deja el manifiesto."""
    trabajo = _trabajo()
    guion = RAIZ / 'tools' / 'vad_estudio.py'
    assert guion.is_file(), 'falta tools/vad_estudio.py (108 T12)'
    r = subprocess.run([sys.executable, str(guion), '--help'], capture_output=True, text=True, encoding='utf-8',
                       cwd=RAIZ, check=False)
    assert r.returncode == 0 and 'sistemas.json' in r.stdout, r.stderr
    sondeo = chr(10).join(['import runpy, sys', 'sys.argv = ["vad_estudio.py", "--help"]', 'try:',
                         f'    runpy.run_path(r"{guion}", run_name="__main__")', 'except SystemExit:', '    pass',
                         'print("powerfactory" in sys.modules)'])
    r2 = subprocess.run([sys.executable, '-c', sondeo], capture_output=True, text=True, encoding='utf-8', cwd=RAIZ,
                        check=False)
    assert r2.stdout.strip().endswith('False'), r2.stdout + r2.stderr
    espacio, id_estudio = _estudio(tmp_path / 'esp')
    caso = tmp_path / 'caso'
    caso.mkdir()
    (caso / 'a.json').write_text(json.dumps({}), encoding='utf-8')
    (caso / 'sistemas.json').write_text(json.dumps({'sistemas': {'SX1': {'anexo2': 'a.json'}, 'SX2': {}}}),
                                        encoding='utf-8')
    entradas = trabajo.leer_caso(caso)
    assert entradas['SX1']['anexo2'] == str((caso / 'a.json').resolve()) and entradas['SX2'] == {}
    r3 = subprocess.run([sys.executable, str(guion), '--espacio', str(espacio), '--estudio', id_estudio, '--caso',
                         str(caso)], capture_output=True, text=True, encoding='utf-8', cwd=RAIZ, check=False)
    m = json.loads((espacio / 'vad' / id_estudio / 'manifiesto.json').read_text(encoding='utf-8'))
    assert r3.returncode in (0, 2), r3.stdout + r3.stderr
    assert m['terminado'] and m['sistemas']['SX1']['pasos']['anexo2']['huecos'], m
    assert m['sistemas']['SX2']['sin_entrada'] == ['anexo2']
    with pytest.raises(VadError, match='sistemas.json'):
        trabajo.leer_caso(tmp_path)
