"""El doble de DIgSILENT con variaciones que se activan y desactivan (spec 007, T1).

Las pruebas del guion de cargas confían en él para comprobar que la carga *i* no ve la
*i−1*: si el doble dejara en la red lo creado en una variación inactiva, esas pruebas
pasarían sin probar nada.
"""
from __future__ import annotations

from fake_pf import proyecto


def _variacion(app, nombre):
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage(f'Etapa_{nombre}', 0, 1)
    return v


def _carga_colgada(app, barra, nombre, p=0.2):
    """Carga nueva con su barra de baja, colgada de ``barra`` por un interruptor."""
    red = barra.GetParent()
    b_bt = red.CreateObject('ElmTerm', f'{nombre}_BT')
    sw = red.CreateObject('ElmCoup', f'SW_{nombre}')
    for term, lado in ((barra, 0), (b_bt, 1)):
        cub = term.CreateObject('StaCubic', f'c{lado}_SW_{nombre}')
        cub.obj_id, cub.obj_bus = sw, lado
    carga = red.CreateObject('ElmLod', nombre)
    carga.plini, carga.coslini = p, 0.95
    cub = b_bt.CreateObject('StaCubic', f'c_{nombre}')
    cub.obj_id, cub.obj_bus = carga, 0
    return carga


def test_lo_creado_en_una_variacion_inactiva_sale_de_la_red():
    """apoyo de 007:RF-11 / 007:RF-12 — desactivar la variación quita sus objetos."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    barra = alim.GetObjs('ElmTerm')[1]
    v = _variacion(app, 'C1')
    carga = _carga_colgada(app, barra, 'NUEVA')
    assert carga in alim.GetObjs('ElmLod')
    assert carga in app.GetCalcRelevantObjects('*.ElmLod')
    v.Deactivate()
    assert carga not in alim.GetObjs('ElmLod')
    assert carga not in app.GetCalcRelevantObjects('*.ElmLod')
    assert app.GetRecordingStage() is None and app.GetActiveNetworkVariations() == []
    v.Activate()
    assert carga in alim.GetObjs('ElmLod') and app.GetActiveNetworkVariations() == [v]


def test_la_carga_i_no_ve_la_anterior():
    """apoyo de 007:RF-12 — con la variación de la anterior desactivada, el flujo no la suma."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2, bt=True, flujo=True)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    barras = [b for b in alim.GetObjs('ElmTerm') if not b.loc_name.endswith('_BT')]

    def cabecera():
        assert app.ldf.Execute() == 0
        return getattr(alim.obj_id.obj_id, f'm_Psum:bus{alim.obj_id.obj_bus + 1}')

    sin = cabecera()
    v1 = _variacion(app, 'C1')
    _carga_colgada(app, barras[1], 'N1', p=0.3)
    con_1 = cabecera()
    v1.Deactivate()
    v2 = _variacion(app, 'C2')
    _carga_colgada(app, barras[2], 'N2', p=0.1)
    con_2 = cabecera()
    assert con_1 > sin and sin < con_2 < con_1
    v2.Deactivate()
    assert abs(cabecera() - sin) < 1e-12


def test_otro_alimentador_no_ve_la_carga():
    """apoyo de 007:RF-25 — la carga colgada de F1 no es de F2."""
    app = proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=2)
    f1, f2 = app.proyecto.GetContents('*.ElmFeeder', 1)
    _variacion(app, 'C1')
    carga = _carga_colgada(app, f1.GetObjs('ElmTerm')[1], 'NUEVA')
    assert carga in f1.GetObjs('ElmLod') and carga not in f2.GetObjs('ElmLod')
