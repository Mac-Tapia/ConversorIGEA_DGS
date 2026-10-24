"""Spec 025, T17: reguladores Eaton VR-32 de catálogo y su creación en el proyecto biblioteca."""
from __future__ import annotations

import math
import random

import pytest

import fake_pf
from apoyo import cargar_herramienta
from igea_dgs import catalogo_reguladores as cat

guion = cargar_herramienta('obras_pf.py', 'obras_t17', tools_en_path=True)


@pytest.mark.parametrize('kv, unidad_v', [(10.0, 6600), (22.9, 15000), (13.8, 11000), (33.0, 22000)])
def test_unidad_de_catalogo_que_cubre_la_tension_de_fase(kv, unidad_v):
    """025:RF-59 — en estrella, la tensión nominal de catálogo más baja que cubre kV/√3; el
    tipo lleva la de fase del sistema, la corriente en amperios, ±10 % y 16 pasos a cada lado."""
    assert cat.tension_de_unidad_v(kv) == unidad_v
    unidades = cat.unidades_para(kv)
    assert [u.corriente_a for u in unidades] == sorted(u.corriente_a for u in unidades)
    datos = unidades[0].datos_tipo()
    assert datos['Un'] == pytest.approx(kv / math.sqrt(3))
    assert datos['In'] == unidades[0].corriente_a and datos['pcReg'] == 10.0
    assert (datos['ntapmin'], datos['ntapmax'], datos['nntap0']) == (-16, 16, 0)
    assert '.' not in unidades[0].nombre and 'CA225001EN' in unidades[0].descripcion()


def test_kva_del_catalogo():
    """025:RF-59 — la potencia de regulación es la del catálogo: V × A × 10 %."""
    assert cat.UnidadRegulador(6600, 10.0, 50).kva == pytest.approx(33)
    assert cat.UnidadRegulador(15000, 22.9, 500).kva == pytest.approx(750)


def test_unidad_para_la_corriente():
    """025:RF-60 — la unidad más chica que lleva la corriente; ninguna si la pasa a todas."""
    assert cat.unidad_para_corriente(22.9, 180).corriente_a == 200
    assert cat.unidad_para_corriente(22.9, 654) is None
    with pytest.raises(cat.CatalogoError):
        cat.unidades_para(220.0)


def test_crea_los_tipos_en_el_proyecto_biblioteca_sin_duplicar():
    """025:RF-59 — los tipos de cada tensión en el proyecto biblioteca del usuario, creado si
    falta; repetir no duplica ninguno."""
    app = fake_pf.proyecto(alimentadores=('F1',))
    rng = random.Random(5)
    tensiones = rng.sample([10.0, 22.9, 13.8], 2)
    informe, rc = guion.crear_tipos_regulador(app, {'tensiones_kv': tensiones})
    assert rc == 0, informe
    prj = next(p for p in app.usuario.GetContents('*.IntPrj') if p.loc_name == guion.BIBLIOTECA_TIPOS)
    equip = guion.biblioteca_de_otro(prj)
    tipos = {t.loc_name: t for t in equip.GetContents('*.TypVoltreg')}
    esperados = [u for kv in tensiones for u in cat.unidades_para(kv)]
    assert sorted(tipos) == sorted(u.nombre for u in esperados)
    u = esperados[0]
    assert tipos[u.nombre].Un == pytest.approx(u.tension_sistema_kv / math.sqrt(3))
    assert tipos[u.nombre].In == u.corriente_a
    otra, rc = guion.crear_tipos_regulador(app, {'tensiones_kv': tensiones})
    assert rc == 0 and otra['creados'] == [] and len(otra['existentes']) == len(esperados)
    assert len(equip.GetContents('*.TypVoltreg')) == len(esperados)


def test_tension_sin_unidad_se_avisa():
    """025:RF-59 — una tensión que ninguna unidad cubre se dice y no se crea nada para ella."""
    app = fake_pf.proyecto(alimentadores=('F1',))
    informe, rc = guion.crear_tipos_regulador(app, {'tensiones_kv': [220.0]})
    assert rc == 0 and informe['creados'] == [] and 'ninguna unidad' in informe['avisos'][-1]
