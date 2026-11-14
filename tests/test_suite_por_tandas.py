"""Spec 081: la suite nocturna deja siempre su resultado y sobrevive a la web. Ninguna prueba corre una suite real."""
from __future__ import annotations

import subprocess
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.asistente import almacen, vigilancia
from convertersmartgrid.asistente.vigilancia import (
    EMPEZADA, INTERRUMPIDA, Vigilante, correr_por_tandas, lanzar_suite_separada, revisar_suite, tandas_de_pruebas,
)


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))


def _repo(tmp_path, n):
    (tmp_path / 'tests').mkdir()
    for i in range(n):
        (tmp_path / 'tests' / f'test_{i:03}.py').write_text('', encoding='utf-8')
    (tmp_path / 'tests' / 'apoyo.py').write_text('', encoding='utf-8')
    return tmp_path


def test_tandas_de_ficheros_sin_numero_fijado(tmp_path):
    """081:RF-38 — todos los ficheros de pruebas, en orden, sin los auxiliares; el tamaño de la suite no está fijado."""
    t = tandas_de_pruebas(_repo(tmp_path, 7), 3)
    assert [len(x) for x in t] == [3, 3, 1] and t[0][0] == 'tests/test_000.py' and not any('apoyo' in f for x in t for f in x)


def test_cada_tanda_en_su_proceso_con_un_solo_hilo(tmp_path):
    """081:RF-38 — una tras otra, con ``OPENBLAS_NUM_THREADS=1``."""
    llamadas = []

    def ejecutar(repo, **kw):
        llamadas.append(kw)
        almacen.anotar(kw['registro'], {'codigo': 0})
        return {'codigo': 0, 'resumen': '5 passed', 'segundos': 2, 'fallidas': [], 'omitidas': 0}

    correr_por_tandas(tmp_path, tandas=[['tests/a.py'], ['tests/b.py']], ejecutar=ejecutar, env={'X': '1'})
    assert [c['argumentos'][-1] for c in llamadas] == ['tests/a.py', 'tests/b.py']
    assert all(c['env'] == {'X': '1', 'OPENBLAS_NUM_THREADS': '1'} for c in llamadas)
    # La suite no hereda la vigilancia de la web: una suite no puede lanzar otra.
    llamadas.clear()
    correr_por_tandas(tmp_path, tandas=[['a']], ejecutar=ejecutar, env={'CSG_ASISTENTE_VIGILANCIA': '1'})
    assert 'CSG_ASISTENTE_VIGILANCIA' not in llamadas[0]['env']


def test_resultado_de_cada_tanda_y_el_total(tmp_path):
    """081:RF-39 — lo que falla se suma, y el código de la suite no es 0 si una tanda falla."""
    resultados = iter([{'codigo': 0, 'resumen': '5 passed in 1s', 'segundos': 1, 'fallidas': [], 'omitidas': 0},
                       {'codigo': 1, 'resumen': '1 failed, 4 passed in 1s', 'segundos': 2,
                        'fallidas': [{'prueba': 'tests/b.py::t', 'rf': ['081:RF-39']}], 'omitidas': 1}])
    r = correr_por_tandas(tmp_path, tandas=[['a'], ['b']], ejecutar=lambda *_a, **_k: next(resultados))
    assert r['codigo'] == 1 and r['tandas'] == '2/2' and r['segundos'] == 3 and r['omitidas'] == 1
    assert r['resumen'] == '9 passed, 1 failed, 0 skipped en 2 tandas' and r['fallidas'][0]['rf'] == ['081:RF-39']
    assert almacen.leer('suite')[-1]['resumen'] == r['resumen']


def test_tanda_de_verdad_escribe_su_registro(tmp_path):
    """081:RF-39 — la tanda pasa por ``correr_suite``, y escribe en su propio registro. Un fichero de una prueba, no una suite."""
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_x.py').write_text('def test_bien():\n    assert True\n', encoding='utf-8')
    r = correr_por_tandas(tmp_path)
    assert r['codigo'] == 0 and '1 passed' in r['resumen']
    assert len(almacen.leer('suite_tandas')) == 1 and almacen.leer('suite')[-1]['tandas'] == '1/1'


def test_si_revienta_queda_interrumpida(tmp_path):
    """081:RF-40 — con las tandas que acabaron y su motivo; no se queda en «empezada»."""
    pasos = iter([{'codigo': 0, 'resumen': '1 passed', 'segundos': 1, 'fallidas': [], 'omitidas': 0}])

    def ejecutar(*_a, **_k):
        try:
            return next(pasos)
        except StopIteration:
            raise MemoryError('sin memoria') from None

    r = correr_por_tandas(tmp_path, tandas=[['a'], ['b']], ejecutar=ejecutar)
    assert r['resumen'] == INTERRUMPIDA and r['codigo'] == -1 and 'sin memoria' in r['motivo'] and r['tandas'] == '1/2'
    assert almacen.leer('suite')[-1]['resumen'] == INTERRUMPIDA


def test_una_senal_la_deja_interrumpida(tmp_path):
    """081:RF-40 — una señal de cierre se registra y sigue subiendo."""
    def ejecutar(*_a, **_k):
        raise KeyboardInterrupt('señal 15')

    with pytest.raises(KeyboardInterrupt):
        correr_por_tandas(tmp_path, tandas=[['a']], ejecutar=ejecutar)
    assert almacen.leer('suite')[-1]['resumen'] == INTERRUMPIDA and 'señal 15' in almacen.leer('suite')[-1]['motivo']


def test_la_que_quedo_empezada_se_cierra_y_avisa():
    """081:RF-41 — el fallo real: «empezada» sin resultado. Con el proceso muerto, «interrumpida» y un aviso."""
    fila = almacen.anotar('suite', {'codigo': None, 'resumen': EMPEZADA, 'pid': 123, 'inicio': 9})
    assert revisar_suite([fila], lambda _f: True) is None and almacen.leer('suite')[-1]['resumen'] == EMPEZADA
    aviso = revisar_suite([fila], lambda _f: False)
    assert aviso.nivel == 'error' and 'interrumpió' in aviso.texto and almacen.leer('suite')[-1]['resumen'] == INTERRUMPIDA
    assert revisar_suite(almacen.leer('suite'), lambda _f: False) is None
    assert revisar_suite([], lambda _f: False) is None
    # Una fila anterior a esta spec, sin proceso, tampoco se queda «empezada».
    assert revisar_suite([{'resumen': EMPEZADA, 'fecha': 'x'}], lambda _f: False) is not None


def _vigilante(tmp_path, **kw):
    return Vigilante(listar_trabajos=lambda: [], reintentar=lambda _i: None, entrenar_gemelo=lambda: None,
                     entrenar_asistente=lambda: None, contar_nuevos=lambda: (0, 0), repo=tmp_path, **kw)


def test_la_vigilancia_la_lanza_aparte_y_avisa(tmp_path, monkeypatch):
    """081:RF-37, 081:RF-41 — ya no es un hilo de la web, y de lo que quedó a medias se entera la siguiente vuelta."""
    lanzadas = []
    monkeypatch.setattr(vigilancia, 'lanzar_suite_separada', lanzadas.append)
    almacen.anotar('suite', {'codigo': None, 'resumen': EMPEZADA, 'pid': 1})
    v = _vigilante(tmp_path)
    nuevos = v.tic(fecha=datetime(2026, 11, 3, 9))
    assert any('interrumpió' in a.texto for a in nuevos) and lanzadas == []
    assert any('interrumpió' in x['texto'] for x in almacen.leer('avisos'))
    v.tic(fecha=datetime(2099, 1, 1, 23))
    assert lanzadas == [tmp_path]
    assert 'threading.Thread(target=correr_suite' not in vigilancia.__loader__.get_source(vigilancia.__name__)


def test_lanzar_espera_solo_al_paso_intermedio(tmp_path):
    """081:RF-37, 081:RF-40 — devuelve al terminar el intermedio; si no se pudo, lo registra.
    Con las pruebas y su herramienta en el árbol: sin ellas no se lanza (086:RF-15, ``test_edicion_producto``)."""
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools' / 'suite_por_tandas.py').write_text('', encoding='utf-8')
    llamadas = []

    def lanzar(cmd, **_kw):
        llamadas.append(cmd)
        return SimpleNamespace(returncode=0)

    assert lanzar_suite_separada(tmp_path, lanzar=lanzar) is True
    assert llamadas[0][-1] == '--separar' and llamadas[0][-2].endswith('suite_por_tandas.py')
    assert almacen.leer('suite') == []
    assert lanzar_suite_separada(tmp_path, lanzar=lambda *_a, **_k: SimpleNamespace(returncode=2)) is False
    assert almacen.leer('suite')[-1]['resumen'] == INTERRUMPIDA

    def falla(*_a, **_k):
        raise OSError('no hay python')

    assert lanzar_suite_separada(tmp_path, lanzar=falla) is False and 'no hay python' in almacen.leer('suite')[-1]['motivo']


def test_separar_sale_del_arbol_de_la_web(tmp_path, monkeypatch):
    """081:RF-37 — el proceso de la suite va separado y con su pid registrado: de ahí cuelga RF-41."""
    h = cargar_herramienta('suite_por_tandas.py', 'suite_por_tandas_081')
    abiertos = []

    def abrir(args, **kw):
        abiertos.append((args, kw))
        return SimpleNamespace(pid=4321)

    assert h.separar(abrir=abrir, inicio=lambda _pid: 77) == 0
    cmd, kw = abiertos[0]
    assert cmd[-1] == '--correr' and kw['env']['OPENBLAS_NUM_THREADS'] == '1' and kw['stdin'] == subprocess.DEVNULL
    assert kw['close_fds'] is True and kw['creationflags'] == h._flags_separado()
    fila = almacen.leer('suite')[-1]
    assert (fila['resumen'], fila['pid'], fila['inicio']) == (EMPEZADA, 4321, 77)
    # Un trabajo de Windows que no deja salir: no se queda sin suite.
    intentos = []

    def sin_permiso(args, **kw):
        intentos.append(kw['creationflags'])
        if len(intentos) == 1:
            raise PermissionError('acceso denegado')
        return SimpleNamespace(pid=5)

    assert h.separar(abrir=sin_permiso, inicio=lambda _pid: 1) == 0 and len(intentos) == 2
    assert almacen.leer('suite')[-1]['pid'] == 5


def test_el_lanzador_de_la_suite_responde_a_help(capsys):
    """081:RF-37 — herramienta con su ayuda en español, sin arrancar nada (009)."""
    h = cargar_herramienta('suite_por_tandas.py', 'suite_por_tandas_081b')
    with pytest.raises(SystemExit) as e:
        h.main(['--help'])
    assert e.value.code == 0 and '--separar' in capsys.readouterr().out


@pytest.mark.parametrize('cortar_suite', [False, True], ids=['sobrevive-web', 'interrupcion-real'])
def test_suite_propia_separada_sobrevive_o_registra_su_muerte(tmp_path, cortar_suite):
    """081:RF-37 / 081:RF-39 / 081:RF-41 — procesos reales; una prueba propia, sin suite completa ni motor."""
    import psutil

    (tmp_path / 'repo').mkdir()
    repo = _repo(tmp_path / 'repo', 0)
    test = repo / 'tests' / 'test_propio.py'
    test.write_text(
        "import time\nfrom pathlib import Path\n"
        f"RAIZ=Path({str(tmp_path)!r})\n"
        "def test_propio():\n"
        "    (RAIZ/'tanda_lista').touch()\n"
        "    limite=time.monotonic()+20\n"
        "    while not (RAIZ/'seguir').exists() and time.monotonic()<limite: time.sleep(.02)\n"
        "    assert (RAIZ/'seguir').exists()\n", encoding='utf-8')
    herramienta = Path(__file__).resolve().parents[1] / 'tools' / 'suite_por_tandas.py'
    corredor = tmp_path / 'corredor.py'
    corredor.write_text(
        'import runpy\nfrom pathlib import Path\n'
        f'h=runpy.run_path({str(herramienta)!r},run_name="ensayo")\n'
        f'h["correr"].__globals__["_REPO"]=Path({str(repo)!r})\n'
        'raise SystemExit(h["correr"]())\n', encoding='utf-8')
    intermedio = tmp_path / 'intermedio.py'
    intermedio.write_text(
        'import runpy,subprocess,sys\n'
        f'h=runpy.run_path({str(herramienta)!r},run_name="ensayo")\n'
        'def abrir(**kw):\n'
        # Solo se dirige la suite al repositorio propio diminuto; los flags y el diario son los del producto.
        f'    kw["args"]=[sys.executable,{str(corredor)!r}]\n'
        '    return subprocess.Popen(**kw)\n'
        'raise SystemExit(h["separar"](abrir=abrir))\n', encoding='utf-8')
    servidor = tmp_path / 'web_propia.py'
    servidor.write_text(
        'import subprocess,sys,time,os,json\nfrom pathlib import Path\n'
        f'subprocess.run([sys.executable,{str(intermedio)!r}],check=True)\n'
        f'Path({str(tmp_path / "web_lista.json")!r}).write_text(json.dumps({{"pid":os.getpid()}}))\n'
        'time.sleep(60)\n', encoding='utf-8')
    proceso = subprocess.Popen([sys.executable, str(servidor)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, env=dict(os.environ))
    suite = None
    def hasta(condicion):
        limite = time.monotonic() + 20
        while time.monotonic() < limite:
            if condicion(): return
            time.sleep(.02)
        raise AssertionError('el ensayo no alcanzó el punto esperado')
    try:
        hasta(lambda: (tmp_path / 'web_lista.json').exists() and (tmp_path / 'tanda_lista').exists())
        fila = almacen.leer('suite')[-1]
        suite = psutil.Process(fila['pid'])
        assert fila['resumen'] == EMPEZADA and suite.is_running()
        psutil.Process(json.loads((tmp_path / 'web_lista.json').read_text())['pid']).kill()
        proceso.wait(10)
        assert suite.is_running(), 'la suite se murió con su servidor'
        if cortar_suite:
            hijos = suite.children(recursive=True)
            suite.kill()
            suite.wait(10)
            for hijo in hijos:
                try: hijo.kill()
                except psutil.NoSuchProcess: pass
            psutil.wait_procs(hijos, timeout=10)
            aviso = revisar_suite(almacen.leer('suite'), lambda f: psutil.pid_exists(f['pid']))
            assert aviso is not None and 'interrumpió' in aviso.texto
            assert almacen.leer('suite')[-1]['resumen'] == INTERRUMPIDA
        else:
            (tmp_path / 'seguir').touch()
            suite.wait(20)
            hasta(lambda: almacen.leer('suite')[-1]['resumen'] != EMPEZADA)
            final = almacen.leer('suite')[-1]
            assert final['codigo'] == 0 and final['tandas'] == '1/1' and '1 passed' in final['resumen']
    finally:
        (tmp_path / 'seguir').touch()
        if suite is not None and suite.is_running():
            suite.kill()
            suite.wait(10)
        if proceso.poll() is None:
            proceso.kill()
            proceso.wait(10)
