"""DIgSILENT de cualquier versión instalada (spec 103)."""
from __future__ import annotations

from pathlib import Path

import pytest

from convertersmartgrid import powerfactory_env as pe


def _instalar(raiz: Path, nombre: str, pythons: tuple[str, ...]) -> Path:
    """Una PowerFactory simulada: su carpeta y una carpeta ``Python\\3.x`` con la API por cada versión."""
    carpeta = raiz / 'DIgSILENT' / nombre
    for v in pythons:
        api = carpeta / 'Python' / v
        api.mkdir(parents=True)
        (api / 'powerfactory.pyd').write_bytes(b'')
    return carpeta


@pytest.fixture
def maquina(tmp_path):
    """2021 con 3.9, 2022 SP1 con 3.9 y 3.10, 2024 con 3.8 a 3.12 y, en otra unidad, 2025 con 3.10 a 3.13."""
    c = tmp_path / 'C' / 'Program Files'
    d = tmp_path / 'D' / 'Program Files'
    _instalar(c, 'PowerFactory 2021 SP3', ('3.9',))
    _instalar(c, 'PowerFactory 2022 SP1', ('3.9', '3.10'))
    _instalar(c, 'PowerFactory 2024', ('3.8', '3.9', '3.10', '3.11', '3.12'))
    _instalar(d, 'PowerFactory 2025', ('3.10', '3.11', '3.12', '3.13'))
    return [c / 'DIgSILENT', d / 'DIgSILENT']


def _interpretes(*versiones):
    """Solo hay intérprete para estas versiones."""
    return lambda v: (Path(f'C:/python{v}/python.exe'), f'prueba {v}') if v in versiones else (None, f'sin {v}')


def test_103_rf1_encuentra_todas_las_instalaciones(maquina):
    """103:RF-1 — en cada unidad, con su año y service pack, y las carpetas de API que traen la extensión."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    assert [i.nombre for i in encontradas] == ['PowerFactory 2025', 'PowerFactory 2024', 'PowerFactory 2022 SP1',
                                              'PowerFactory 2021 SP3']
    assert encontradas[0].version == (2025, 0) and encontradas[2].version == (2022, 1)
    assert [a.name for a in encontradas[1].apis] == ['3.12', '3.11', '3.10', '3.9', '3.8']


def test_103_rf1_lee_las_que_registra_windows(tmp_path):
    """103:RF-1 — una instalación fuera de las carpetas habituales se encuentra por el registro, sin repetirse."""
    fuera = _instalar(tmp_path / 'Otra', 'PowerFactory 2023 SP5', ('3.11',))
    encontradas = pe.instalaciones(raices=[fuera.parent], registro=[str(fuera) + '\\'])
    assert [i.nombre for i in encontradas] == ['PowerFactory 2023 SP5']


def test_103_rf2_elige_la_api_que_tiene_interprete(maquina):
    """103:RF-2 — 2025 trae 3.13, pero con el Python 3.12 del programa se elige su carpeta 3.12, no la más alta."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    api, interprete, _motivo = pe.elegir_api(encontradas[0], _interpretes('3.12'))
    assert api.name == '3.12' and interprete == Path('C:/python3.12/python.exe')
    # 2021 solo trae 3.9: con un 3.9 embebido carga; sin él, no hay carpeta que sirva.
    assert pe.elegir_api(encontradas[3], _interpretes('3.12', '3.9'))[0].name == '3.9'
    assert pe.elegir_api(encontradas[3], _interpretes('3.12')) is None


def test_103_rf2_el_python_del_programa_primero(maquina, monkeypatch):
    """103:RF-2 — si el Python del programa encaja, se usa ese antes que cualquier otro."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    actual = f'{pe.sys.version_info.major}.{pe.sys.version_info.minor}'
    api, interprete, motivo = pe.elegir_api(encontradas[1], pe.interprete_para)
    assert api.name == actual and interprete == Path(pe.sys.executable) and 'actual' in motivo


def test_103_rf2_los_embebidos_del_instalador(tmp_path, monkeypatch):
    """103:RF-2, RF-6 — un Python embebido en la carpeta del programa sirve para su versión."""
    embebido = tmp_path / pe.CARPETA_PYTHON_EMBEBIDOS / '3.9' / 'python.exe'
    embebido.parent.mkdir(parents=True)
    embebido.write_bytes(b'')
    monkeypatch.setattr(pe, 'raiz_programa', lambda: tmp_path)
    monkeypatch.setattr(pe, '_sondear_py', lambda _v: None)
    assert pe.interprete_para('3.9')[0] == embebido


def test_103_rf4_el_diagnostico_dice_lo_instalado_y_lo_que_falta(maquina, monkeypatch):
    """103:RF-4 — sin versión fija: cada PowerFactory con su API, o el Python que le falta."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    lineas = pe.resumen_instalaciones(encontradas, _interpretes('3.12'))
    assert lineas[0] == 'PowerFactory 2025: API 3.12 con prueba 3.12.'
    assert lineas[-1] == 'PowerFactory 2021 SP3: falta un intérprete de Python 3.9 para cargar su API.'
    from convertersmartgrid.web import doctor
    monkeypatch.setattr(pe, 'resumen_instalaciones', lambda: [])
    c = doctor._digsilent(lambda: None)
    assert '2024' not in c.arreglo and '3.12' not in c.arreglo and '2021 o posterior' in c.arreglo


def test_103_rf4_ningun_mensaje_con_una_version_fija():
    """103:RF-4 — ni rutas ni mensajes que pidan una versión concreta de PowerFactory o de Python."""
    raiz = Path(__file__).resolve().parents[1]
    prohibidos = (r'PowerFactory 2024\Python', 'PF 2024 pide', 'Abra PF 2024', 'PowerFactory 2024 con su Python')
    for fichero in ('src/convertersmartgrid/powerfactory_env.py', 'src/convertersmartgrid/web/doctor.py',
                    'tools/check_pf_license.py', 'tools/powerfactory_acceptance.py'):
        texto = (raiz / fichero).read_text(encoding='utf-8')
        assert not [p for p in prohibidos if p in texto], fichero


def test_103_rf7_sin_digsilent_se_sigue_convirtiendo(monkeypatch):
    """103:RF-7 — sin ninguna PowerFactory el diagnóstico no lo pone como obligatorio y dice que el DGS sigue."""
    from convertersmartgrid.web import doctor
    monkeypatch.setattr(pe, 'resumen_instalaciones', lambda: [])
    c = doctor._digsilent(lambda: None)
    assert c.ok is False and c.obligatoria is False and 'Convertir a DGS sigue funcionando' in c.afecta
