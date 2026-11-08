"""002:RF-2/3/4/5; 050:RF-2/4/8: contratos ligeros y composición operativa real."""
import pytest

from apoyo import cargar_herramienta
from convertersmartgrid import aprendizaje_continuo as ac


def test_muestra_y_error_tienen_un_dueno_puro():
    """002:RF-3; 050:RF-2: todos los productores comparten tipos sin importar el coordinador."""
    assert ac.Muestra.__module__ == 'convertersmartgrid.contratos_aprendizaje'
    assert ac.CicloBloqueado.__module__ == 'convertersmartgrid.contratos_aprendizaje'


@pytest.mark.parametrize('modo', ['ciclo', 'plan'])
def test_cli_y_plan_de_vigilancia_inyectan_productores_antes_de_solo_preparar(tmp_path, monkeypatch, modo):
    """050:RF-4/8: la entrada plan de vigilancia compone igual que CLI, sin modelos ni GPU."""
    from test_aprendizaje_cola import _plan
    cli = cargar_herramienta('aprendizaje_continuo.py')
    llamadas = []
    monkeypatch.setattr(ac, 'congelar_instantanea', lambda *_a, **_kw: {'snapshot_id': 'a' * 64, 'ruta': str(tmp_path)})
    def preflight(*_a, **kw):
        productor = kw.get('productores')
        assert productor is not None, 'el ciclo operativo perdió la composición real'
        assert all(callable(getattr(productor, n, None)) for n in ('lenguaje', 'pinn', 'gru', 'qlora', 'evolutivos'))
        llamadas.append(productor)
        return {'estado': 'preparado', 'entrenamiento_ejecutado': False}
    monkeypatch.setattr(ac, 'preflight_ciclo', preflight)
    if modo == 'plan':
        ruta = _plan(tmp_path)
        plan = ac.cargar_plan_ciclo(ruta)
        args = ['plan', '--archivo', str(ruta), '--plan-hash', plan['plan_hash'], '--solo-preparar']
    else:
        args = ['--raiz', str(tmp_path / 'ap'), 'ciclo', '--contexto', 'a' * 64,
                '--familias', 'transformer', '--fuente', 'dataset=' + str(tmp_path),
                '--politica-hash', 'b' * 64, '--tiempo-s', '1', '--memoria-gib', '12', '--solo-preparar']
    assert cli.main(args) == 0
    assert len(llamadas) == 1


def test_contrato_puro_y_lector_no_importan_preparacion_en_otro_proceso(tmp_path):
    """002:RF-3/4; 050:RF-7: inferir/leer el conjunto no arrastra preparación ni modelos."""
    import os
    import subprocess
    import sys
    script = '''
import sys,pickle
from convertersmartgrid import contratos_aprendizaje as c
assert 'convertersmartgrid.aprendizaje_continuo' not in sys.modules
assert 'convertersmartgrid.training_coordinator' not in sys.modules
assert 'torch' not in sys.modules
from convertersmartgrid.conjuntos_aprendizaje import miembro_en_uso
assert miembro_en_uso('pinn') is None
assert 'convertersmartgrid.aprendizaje_continuo' not in sys.modules
from convertersmartgrid import aprendizaje_continuo as ac
assert ac.Muestra is c.Muestra and ac.CicloBloqueado is c.CicloBloqueado
m=c.Muestra('observada','transformer','a'*64,'observado','operador','entrenamiento')
assert pickle.loads(pickle.dumps(m))==m
assert pickle.loads(b'cconvertersmartgrid.aprendizaje_continuo\\nMuestra\\n.') is c.Muestra
'''
    env = dict(os.environ, CSG_ASISTENTE_DATA=str(tmp_path / 'asistente'))
    result = subprocess.run([sys.executable, '-B', '-c', script], env=env, cwd=tmp_path,
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
