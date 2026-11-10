"""031:RF-17, RF-18 — ``tools/lanzar_pronostico_pide_gpu.py``: el PIDE en la GPU en un paso, con el ganador por métricas."""
from __future__ import annotations

import sys
from types import ModuleType

import pytest
from apoyo import cargar_herramienta


@pytest.fixture
def herramienta():
    return cargar_herramienta('lanzar_pronostico_pide_gpu.py', 'lanzar_pide_prueba')


def test_sin_libros_ni_dataset_no_corre(herramienta, capsys):
    """031:RF-18 — no hay modo de demostración con series inventadas."""
    with pytest.raises(SystemExit):
        herramienta.main(['--proyecto', 'P', '--anio-base', '2026', '--salida', 'x'])
    assert 'series inventadas' in capsys.readouterr().err
    texto = herramienta.Path(herramienta.__file__).read_text(encoding='utf-8')
    assert 'pronostico_sintetico' not in texto and "'ganador'" not in texto


def _falsos(monkeypatch, llamadas, *, sin_gpu=False):
    import convertersmartgrid.training_coordinator as tc

    def dispositivo():
        if sin_gpu:
            raise RuntimeError('sin GPU CUDA')
        return 'cuda:0'

    monkeypatch.setattr(tc, 'dispositivo', dispositivo)
    monkeypatch.setattr(tc, 'exigir_memoria_ml', lambda **k: llamadas.append(('memoria', k)))
    falso = ModuleType('proyeccion_anual')
    falso.main = lambda argv: llamadas.append(('proyeccion', argv)) or 0
    monkeypatch.setitem(sys.modules, 'proyeccion_anual', falso)


def test_pasa_las_redes_y_el_horizonte_del_pide(herramienta, monkeypatch):
    """031:RF-17 — las redes compiten en proyeccion_anual (que elige por métricas), con 5 y 30 años por defecto."""
    llamadas = []
    _falsos(monkeypatch, llamadas)
    assert herramienta.main(['--cabecera', 'c', '--equivalencia', 'e', '--proyecto', 'P', '--anio-base', '2026',
                             '--salida', 's']) == 0
    assert llamadas[0][0] == 'memoria'
    argv = llamadas[1][1]
    assert argv[:argv.index('--modelos')] == ['--cabecera', 'c', '--equivalencia', 'e', '--proyecto', 'P',
                                              '--anio-base', '2026', '--salida', 's']
    assert argv[argv.index('--modelos') + 1] == 'nhits,tft,patchtst,tide'
    assert argv[argv.index('--anio-corto') + 1] == '5' and argv[argv.index('--anio-fin') + 1] == '30'
    llamadas.clear()
    herramienta.main(['--dataset', 'd', '--proyecto', 'P', '--anio-base', '2026', '--salida', 's',
                      '--modelos', 'itransformer', '--anio-fin', '20'])
    argv = llamadas[1][1]
    assert argv[argv.index('--modelos') + 1] == 'itransformer' and argv[argv.index('--anio-fin') + 1] == '20'


def test_sin_gpu_se_dice_antes_de_leer_nada(herramienta, monkeypatch):
    """031:RF-18 — sin CUDA, el error sale antes de llamar a la proyección."""
    llamadas = []
    _falsos(monkeypatch, llamadas, sin_gpu=True)
    with pytest.raises(RuntimeError, match='sin GPU'):
        herramienta.main(['--dataset', 'd', '--proyecto', 'P', '--anio-base', '2026', '--salida', 's'])
    assert llamadas == []
