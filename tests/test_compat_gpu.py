"""Spec 106, RF-18 y RF-19: el controlador de NVIDIA no tumba el proceso al iniciar CUDA, y el doctor lo dice.

Caso real (2026-11-13, controlador 560.94): ``torch.cuda.is_available()`` dejaba un hilo en ``nvdxgdmal64.dll`` ya
descargada y el proceso moría con 0xC0000005 a los ~90 s (rojo en ``D:/csg/NV/rojo_*.log``). Las unitarias simulan el
registro y kernel32; la lenta repite el caso en Windows real con la protección del paquete.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from convertersmartgrid import compat_gpu as CG
from convertersmartgrid.web import doctor as DR

CARPETA = r'C:\Windows\System32\DriverStore\FileRepository\nvx.inf_amd64_0001'


class _Clave:
    def __init__(self, valores=None, hijas=None, abre=True):
        self.valores, self.hijas, self.abre = dict(valores or {}), dict(hijas or {}), abre

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Registro:
    """Lo que ``compat_gpu`` usa de ``winreg``, sobre un árbol en memoria."""
    HKEY_LOCAL_MACHINE = 'HKLM'

    def __init__(self, adaptadores: dict[str, dict] | None, *, sin_clase: bool = False):
        hijas = {n: _Clave(v) for n, v in (adaptadores or {}).items()}
        hijas['Properties'] = _Clave(abre=False)        # en Windows, «Acceso denegado» sin ser administrador
        self.clase = None if sin_clase else _Clave(hijas=hijas)

    def OpenKey(self, padre, nombre):
        if padre == self.HKEY_LOCAL_MACHINE:
            if self.clase is None or nombre != CG.CLASE_PANTALLA:
                raise FileNotFoundError(nombre)
            return self.clase
        hija = padre.hijas.get(nombre)
        if hija is None or not hija.abre:
            raise PermissionError(nombre)
        return hija

    def QueryInfoKey(self, clave):
        return (len(clave.hijas), len(clave.valores), 0)

    def EnumKey(self, clave, i):
        return list(clave.hijas)[i]

    def QueryValueEx(self, clave, nombre):
        if nombre not in clave.valores:
            raise FileNotFoundError(nombre)
        return clave.valores[nombre], 1


class _Kernel32:
    def __init__(self):
        self.cargadas, self.fijadas = [], []

    def LoadLibraryExW(self, ruta, _archivo, banderas):
        self.cargadas.append((ruta, banderas))
        return 0x7FF000000000

    def GetModuleHandleExW(self, bandera, ruta, _salida):
        self.fijadas.append((bandera, ruta))
        return 1


def _nvidia(version='32.0.15.6094'):
    return {'0000': {'DriverDesc': 'NVIDIA GeForce RTX', 'ProviderName': 'NVIDIA', 'DriverVersion': version,
                     'UserModeDriverName': [CARPETA + r'\nvldumdx.dll', CARPETA + r'\nvldumdx.dll']},
            '0001': {'DriverDesc': 'Intel(R) UHD Graphics', 'ProviderName': 'Intel Corporation',
                     'UserModeDriverName': [r'C:\Windows\System32\DriverStore\FileRepository\iigd\igd.dll']}}


@pytest.fixture(autouse=True)
def _sin_estado(monkeypatch):
    """Cada prueba decide de cero: el estado del proceso de pytest (ya fijado en conftest) no se toca."""
    monkeypatch.setattr(CG, '_estado', None)


def _fijar(registro, k32=None, existe=lambda r: True, plataforma='win32'):
    k32 = k32 or _Kernel32()
    return CG.fijar_dll_nvidia(plataforma=plataforma, winreg=registro, kernel32=lambda: k32, existe=existe), k32


def test_elige_la_carpeta_de_nvidia_y_fija_la_dll():
    """106:RF-18 — la DLL de la carpeta del controlador NVIDIA (no la de Intel), cargada y fijada con PIN."""
    estado, k32 = _fijar(_Registro(_nvidia()))
    ruta = os.path.join(CARPETA, CG.DLL_NVIDIA)
    assert estado.accion == 'fijada' and estado.activa and estado.rutas == (ruta,)
    assert k32.cargadas == [(ruta, CG._BUSQUEDA_SEGURA)]
    assert k32.fijadas == [(CG._FLAG_PIN, ruta)] and CG._FLAG_PIN == 0x1
    assert CG.estado_fijado() == estado


@pytest.mark.parametrize('version', ['31.0.15.5585', '32.0.15.6094', '32.0.15.7000', '33.0.16.9999', ''])
def test_la_dll_se_fija_con_cualquier_version_del_controlador(version):
    """106:RF-18 — se fija siempre que esté la DLL, sin mirar la versión (auditor c7, 2026-11-13): no se sabe qué
    versiones tienen el defecto, y el PIN es inocuo con un controlador sano. La versión solo la usa el aviso del doctor."""
    estado, k32 = _fijar(_Registro(_nvidia(version)))
    assert estado.accion == 'fijada' and len(k32.fijadas) == 1


def test_la_segunda_llamada_no_vuelve_a_cargar_nada():
    """106:RF-18 — idempotente: la segunda llamada devuelve lo mismo sin tocar kernel32."""
    registro, k32 = _Registro(_nvidia()), _Kernel32()
    primera, _ = _fijar(registro, k32)
    segunda, _ = _fijar(registro, k32)
    assert segunda == primera and len(k32.cargadas) == 1 and len(k32.fijadas) == 1


@pytest.mark.parametrize('registro, accion', [
    (_Registro({'0001': _nvidia()['0001']}), 'sin_nvidia'),
    (_Registro(None, sin_clase=True), 'sin_nvidia'),
])
def test_sin_nvidia_o_sin_la_clave_no_hace_nada(registro, accion):
    """106:RF-18 — sin adaptador NVIDIA, o sin la clave de la clase de pantalla, no carga nada ni falla."""
    estado, k32 = _fijar(registro)
    assert estado.accion == accion and not estado.activa and not k32.cargadas


def test_si_la_ruta_del_driverstore_no_existe_no_hace_nada():
    """106:RF-18 — la carpeta del registro sin la DLL (otro controlador, o borrada): nada que fijar, sin fallo."""
    estado, k32 = _fijar(_Registro(_nvidia()), existe=lambda r: False)
    assert estado.accion == 'sin_dll' and not k32.cargadas


def test_si_windows_no_la_carga_lo_dice_sin_lanzar():
    """106:RF-18 — un LoadLibraryExW que falla queda en el estado, no tumba al que importa torch."""
    class _Falla(_Kernel32):
        def LoadLibraryExW(self, ruta, _archivo, banderas):
            raise OSError('acceso denegado')

    estado, _ = _fijar(_Registro(_nvidia()), _Falla())
    assert estado.accion == 'error' and 'acceso denegado' in estado.detalle


def test_fuera_de_windows_no_hace_nada():
    """106:RF-18 — en Linux (GitHub Actions) ni se lee el registro."""
    class _Prohibido:
        def __getattr__(self, nombre):
            raise AssertionError('no se lee el registro fuera de Windows')

    estado, k32 = _fijar(_Prohibido(), plataforma='linux')
    assert estado.accion == 'no_windows' and not k32.cargadas


def test_version_de_nvidia_desde_la_de_windows():
    """106:RF-19 — 32.0.15.6094 es la 560.94; una cadena rara no da versión."""
    assert CG.version_nvidia('32.0.15.6094') == (560, 94)
    assert CG.version_nvidia('31.0.15.5585') == (555, 85)
    assert CG.version_nvidia('32.0.15.7000') == (570, 0)
    assert CG.version_nvidia('') is None and CG.version_nvidia('x.y') is None


def test_el_buscador_fija_al_importar_torch_una_sola_vez(monkeypatch):
    """106:RF-18 — un único punto: el primer ``import torch`` fija la DLL y el buscador se retira."""
    llamadas = []
    monkeypatch.setattr(CG, 'fijar_dll_nvidia', lambda: llamadas.append(1))
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys, 'meta_path', [b for b in sys.meta_path if not isinstance(b, CG._AntesDeTorch)])
    monkeypatch.delitem(sys.modules, 'torch', raising=False)
    assert CG.instalar_antes_de_torch() and CG.instalar_antes_de_torch()
    buscadores = [b for b in sys.meta_path if isinstance(b, CG._AntesDeTorch)]
    assert len(buscadores) == 1 and sys.meta_path[0] is buscadores[0]
    assert buscadores[0].find_spec('numpy') is None and not llamadas
    assert buscadores[0].find_spec('torch') is None and llamadas == [1]
    assert not any(isinstance(b, CG._AntesDeTorch) for b in sys.meta_path)


def test_el_paquete_deja_el_buscador_puesto_en_cada_proceso():
    """106:RF-18 — un hijo que importa el paquete (trabajadores_ml, tools/) lo tiene sin llamarlo; no importa torch."""
    codigo = ('import sys, convertersmartgrid; from convertersmartgrid import compat_gpu as c; '
              'print(any(isinstance(b, c._AntesDeTorch) for b in sys.meta_path), "torch" in sys.modules, c.estado_fijado())')
    r = subprocess.run([sys.executable, '-c', codigo], capture_output=True, text=True, timeout=120, env=os.environ.copy())
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == [str(sys.platform == 'win32'), 'False', 'None']


def _adaptador(version):
    return lambda: [CG.Adaptador('NVIDIA GeForce RTX', version, CARPETA)]


def test_doctor_aconseja_actualizar_un_controlador_con_el_fallo():
    """106:RF-19 — 560.94 con la DLL: aviso que no bloquea, con la protección activa dicha."""
    c = DR._controlador_nvidia(_adaptador('32.0.15.6094'), existe=lambda r: True, mitigacion=lambda: True)
    assert not c.ok and not c.obligatoria
    assert '560.94' in c.detalle and 'protección activa' in c.detalle
    assert 'actualizar' in c.arreglo and '560.94' in c.arreglo
    sin = DR._controlador_nvidia(_adaptador('32.0.15.6094'), existe=lambda r: True, mitigacion=lambda: False)
    assert 'protección NO activa' in sin.detalle


@pytest.mark.parametrize('version, existe', [('32.0.15.7000', True), ('32.0.15.6094', False)])
def test_doctor_no_avisa_con_un_controlador_posterior_o_sin_la_dll(version, existe):
    """106:RF-19 — un controlador posterior al último con el fallo, o sin la DLL, queda en verde."""
    c = DR._controlador_nvidia(_adaptador(version), existe=lambda r: existe, mitigacion=lambda: True)
    assert c.ok and not c.arreglo


def test_doctor_sin_nvidia_en_verde_y_en_el_informe(tmp_path):
    """106:RF-19 — sin NVIDIA no avisa; la comprobación va en el informe y no cambia «listo»."""
    assert DR._controlador_nvidia(lambda: []).ok
    programa = tmp_path / 'programa'
    (programa / 'frontend' / 'dist').mkdir(parents=True)
    (programa / 'frontend' / 'dist' / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    controlador = tmp_path / 'nvx.inf_amd64'
    controlador.mkdir()
    (controlador / CG.DLL_NVIDIA).write_bytes(b'')
    informe = DR.diagnosticar(importer=lambda n: object(), drivers=lambda: (), version=(3, 12), carpeta_pf=lambda: None,
                              programa=programa, buscar_modulo=lambda n: None, buscar_programa=lambda n: None,
                              adaptadores_nvidia=lambda: [CG.Adaptador('NVIDIA GeForce RTX', '32.0.15.6094', str(controlador))])
    fila = next(c for c in informe['comprobaciones'] if c['clave'] == 'controlador_nvidia')
    assert fila['obligatoria'] is False and '[aviso] Controlador NVIDIA' in DR.texto_del_informe(informe)


#: Lo que hace conftest._hay_cuda y cualquier modelo: iniciar CUDA y seguir vivo más que el aviso del sistema (~90 s).
ESPERA_S = 200


def _dll_nvidia_presente() -> bool:
    return sys.platform == 'win32' and any(
        os.path.isfile(os.path.join(a.carpeta, CG.DLL_NVIDIA)) for a in CG.adaptadores_nvidia())


@pytest.mark.gpu
@pytest.mark.skipif(not _dll_nvidia_presente(), reason='solo en Windows con un controlador NVIDIA que trae la DLL')
def test_con_la_proteccion_iniciar_cuda_no_tumba_el_proceso(tmp_path):
    """106:RF-18 — en Windows real: el paquete, torch.cuda.is_available() y 200 s vivo; rc 0.

    Sin la protección, el mismo subproceso (``import torch`` sin el paquete) salió con 0xC0000005 en esta máquina
    (D:/csg/NV/rojo_*.log). Va en el turno de la GPU por su marca.
    """
    codigo = ('import sys, time, convertersmartgrid, torch; from convertersmartgrid import compat_gpu as c; '
              'print("cuda", torch.cuda.is_available(), flush=True); print("estado", c.estado_fijado(), flush=True); '
              f'time.sleep({ESPERA_S}); print("fin sin fallo", flush=True)')
    r = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', codigo], capture_output=True, text=True,
                       timeout=ESPERA_S + 240, env=os.environ.copy())
    (tmp_path / 'salida.log').write_text(f'rc={r.returncode}\n{r.stdout}\n{r.stderr}', encoding='utf-8')
    assert r.returncode == 0, f'rc={r.returncode:#x}\n{r.stdout}\n{r.stderr}'
    assert "accion='fijada'" in r.stdout and 'fin sin fallo' in r.stdout


#: Lee la traza de descargas de ntdll (RtlGetUnloadEventTraceEx): ahí queda «nvdxgdmal64.dll» cuando el controlador la
#: saca de memoria, la condición del 0xC0000005 de RF-18, sin esperar los ~90 s del aviso del sistema que la dispara.
_TRAZA_DE_DESCARGAS = r'''
import ctypes
from ctypes import wintypes
class _E(ctypes.Structure):
    _fields_ = [('Base', ctypes.c_void_p), ('Tam', ctypes.c_size_t), ('Seq', wintypes.ULONG), ('Fecha', wintypes.ULONG),
                ('Suma', wintypes.ULONG), ('Nombre', wintypes.WCHAR * 32), ('Version', wintypes.ULONG * 2)]
def descargadas():
    f = ctypes.WinDLL('ntdll').RtlGetUnloadEventTraceEx
    f.argtypes = [ctypes.POINTER(ctypes.POINTER(wintypes.ULONG))] * 2 + [ctypes.POINTER(ctypes.c_void_p)]
    tam, n, traza = ctypes.POINTER(wintypes.ULONG)(), ctypes.POINTER(wintypes.ULONG)(), ctypes.c_void_p()
    f(ctypes.byref(tam), ctypes.byref(n), ctypes.byref(traza))
    base = ctypes.c_void_p.from_address(traza.value).value if traza.value else None
    if not base:
        return []
    return [_E.from_address(base + i * tam.contents.value).Nombre.lower() for i in range(n.contents.value)]
'''

#: Lo que hace el reentreno del pronóstico con «todo activo» dentro de la web, con la GPU oculta: torch entrena en CPU
#: (su primer backward cuenta los dispositivos de cada backend y eso llama a cuInit, sin pedir CUDA) y LightGBM entrena
#: en el mismo proceso, con su runtime de OpenMP (vcomp140) junto al de torch (libiomp5md).
_ENTRENAR_TORCH_Y_LIGHTGBM = r'''
import numpy as np, lightgbm as lgb
a = torch.randn(8, 4, requires_grad=True)
(a * a).sum().backward()
x = np.random.default_rng(0).normal(size=(2000, 6))
lgb.train({'objective': 'l1', 'verbosity': -1, 'deterministic': True, 'force_col_wise': True}, lgb.Dataset(x, x[:, 0]),
          num_boost_round=5).predict(x[:10])
print('cuda', torch.cuda.is_available(), 'descargadas', sorted(set(descargadas())), flush=True)
'''


@pytest.mark.skipif(not _dll_nvidia_presente(), reason='solo en Windows con un controlador NVIDIA que trae la DLL')
def test_con_la_gpu_oculta_entrenar_en_cpu_tambien_descarga_la_dll_y_el_paquete_lo_impide(tmp_path):
    """106:RF-18 — ``CUDA_VISIBLE_DEVICES=-1`` no protege: un backward en CPU y un ``lgb.train`` en el mismo proceso
    descargan ``nvdxgdmal64.dll`` (rojo, sin el paquete), y con el paquete importado antes de torch no sale de memoria.

    Caso real (2026-11-14, auditoría de c7): ``tests/test_pronostico_demanda.py`` entero, con la GPU oculta, caía con
    0xC0000005 a mitad; se sospechó de dos OpenMP (libiomp5md de torch y vcomp140 de LightGBM). Reproducción en
    D:/csg/OPENMP: sin fijar la DLL caen a la vez dos procesos sin relación entre sí, solo cuInit o torch con LightGBM;
    con la DLL fijada, torch y LightGBM conviven 1018 vueltas en 480 s. La causa es la de RF-18, no OpenMP.
    """
    entorno = {**os.environ, 'CUDA_VISIBLE_DEVICES': '-1'}
    salidas = {}
    for caso, cabecera in (('sin_paquete', 'import torch'), ('con_paquete', 'import convertersmartgrid, torch')):
        codigo = _TRAZA_DE_DESCARGAS + cabecera + '\n' + _ENTRENAR_TORCH_Y_LIGHTGBM
        r = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', codigo], capture_output=True, text=True,
                           timeout=300, env=entorno)
        (tmp_path / f'{caso}.log').write_text(f'rc={r.returncode}\n{r.stdout}\n{r.stderr}', encoding='utf-8')
        assert r.returncode == 0, f'{caso}: rc={r.returncode:#x}\n{r.stdout}\n{r.stderr}'
        salidas[caso] = r.stdout
    assert 'cuda False' in salidas['sin_paquete'], 'la GPU debía quedar oculta con CUDA_VISIBLE_DEVICES=-1'
    assert CG.DLL_NVIDIA in salidas['sin_paquete'], 'sin la protección el controlador debía descargar la DLL (rojo de RF-18)'
    assert CG.DLL_NVIDIA not in salidas['con_paquete'], salidas['con_paquete']
