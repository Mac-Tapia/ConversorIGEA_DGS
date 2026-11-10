"""089:RF-89, RF-90 — ``tools/entrenar_alimentadores_gpu.py``: un alimentador tras otro en la GPU, sin rutas fijas."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from apoyo import cargar_herramienta


@pytest.fixture(scope='module')
def herramienta():
    return cargar_herramienta('entrenar_alimentadores_gpu.py', 'entrenar_alimentadores_prueba')


def test_los_libros_se_piden_y_no_hay_rutas_fijas(herramienta, capsys):
    """089:RF-89 — sin ``--cabecera`` ni ``--equivalencia`` no corre: ningún libro de la distribuidora por defecto."""
    with pytest.raises(SystemExit):
        herramienta.main(['--salida', 'x'])
    assert '--cabecera' in capsys.readouterr().err
    assert 'D:/' not in herramienta.Path(herramienta.__file__).read_text(encoding='utf-8')


def test_seleccion_de_alimentadores(herramienta):
    """089:RF-89 — los del libro (solo alimentadores, sin repetir), o los pedidos, y el límite."""
    puntos = [SimpleNamespace(codigo=c, clase=k) for c, k in
              (('PI102', 'alimentador'), ('PA217', 'alimentador'), ('PI102', 'alimentador'), ('M1', 'cliente'))]
    assert herramienta.seleccion(puntos, None, None) == ['PA217', 'PI102']
    assert herramienta.seleccion(puntos, None, 1) == ['PA217']
    assert herramienta.seleccion(puntos, ' ca101, CA101,pe104 ', None) == ['CA101', 'PE104']


def test_un_error_sigue_con_los_demas_y_termina_con_1(herramienta, tmp_path, monkeypatch, capsys):
    """089:RF-90 — el fallo de uno no detiene a los otros, queda en el resumen y la orden termina con código 1."""
    import convertersmartgrid.pronostico_demanda as pd_mod
    import convertersmartgrid.training_coordinator as tc

    monkeypatch.setattr(tc, 'dispositivo', lambda: 'cuda:0')
    monkeypatch.setattr(tc, 'exigir_memoria_ml', lambda **_k: None)
    monkeypatch.setattr(pd_mod, 'equivalencias', lambda _r: ([SimpleNamespace(codigo='A', clase='alimentador'),
                                                              SimpleNamespace(codigo='B', clase='alimentador')], []))

    def entrenar(codigo, *_a, **_k):
        if codigo == 'A':
            raise RuntimeError('CUDA sin memoria')
        return {'alimentador': codigo, 'status': 'ENTRENADO'}

    monkeypatch.setattr(herramienta, 'entrenar_un_alimentador', entrenar)
    rc = herramienta.main(['--cabecera', str(tmp_path), '--equivalencia', str(tmp_path / 'e.xlsx'),
                           '--salida', str(tmp_path / 'salida')])
    assert rc == 1
    resumen = json.loads((tmp_path / 'salida' / 'resumen.json').read_text(encoding='utf-8'))
    assert [r['status'] for r in resumen] == ['ERROR', 'ENTRENADO']
    assert 'CUDA sin memoria' in resumen[0]['error']
    assert '1 entrenado(s), 1 con error: A.' in capsys.readouterr().out


def test_retoma_el_ya_entrenado_con_el_mismo_modelo(herramienta, tmp_path):
    """089:RF-89 — un ``resultado.json`` ENTRENADO con el mismo algoritmo no se repite."""
    previo = {'alimentador': 'A', 'status': 'ENTRENADO', 'algoritmo': 'nhits'}
    (tmp_path / 'A').mkdir()
    (tmp_path / 'A' / 'resultado.json').write_text(json.dumps(previo), encoding='utf-8')
    assert herramienta.entrenar_un_alimentador('A', {}, tmp_path, algoritmo='nhits', pasos=1) == previo
