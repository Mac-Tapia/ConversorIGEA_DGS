"""El oráculo pandapower: la validación física que da la web antes de PowerFactory.

Hasta el 2026-10-08 ninguna prueba lo ejecutaba (0 % de sus líneas). Funcionaba —sobre
los 96 alimentadores de la entrega de 03/08: 95 convergen y 1 da tensión imposible—,
pero nada habría avisado si una versión nueva de pandapower lo rompía, y la web habría
seguido mostrando un veredicto sin calcularlo. Estas pruebas lo ejecutan sobre exports
sintéticos con las dos disposiciones.
"""

from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip('pandapower')

from igea_dgs import oraculo  # noqa: E402
from igea_dgs.model import build_feeder_model  # noqa: E402
from synthetic_export import ExportSpec, load_export  # noqa: E402

LAYOUTS = ('reducido', 'completo')


def _modelos(tmp_path, layout='reducido', **kw):
    spec = ExportSpec(feeders=3, sections_per_feeder=5, loads_per_feeder=3,
                      layout=layout, **kw)
    ds = load_export(spec, tmp_path / layout)
    return [build_feeder_model(ds, net, strict=True) for net in ds.feeder_ids()]


@pytest.mark.parametrize('layout', LAYOUTS)
def test_calcula_la_red_que_se_escribe_en_el_dgs(tmp_path, layout):
    for modelo in _modelos(tmp_path, layout, seed=7):
        inf = oraculo.validar(modelo)
        assert inf.disponible and inf.convergio, inf.resumen()
        # Una barra por nodo más el lado de baja de cada SED, como en el DGS.
        assert inf.barras == len(modelo.nodes) + len(modelo.seds)
        assert inf.lineas == sum(
            1 for ln in modelo.lines if ln.length_m >= oraculo._LARGO_CONEXION_M)
        assert inf.transformadores == len(modelo.seds)
        assert inf.cargas == len(modelo.loads)
        assert not inf.errores, [h.linea() for h in inf.errores]


def test_un_tramo_de_0_m_no_impide_converger(tmp_path):
    """La disposición completa cuelga cada carga del punto medio de una derivación
    virtual de 0 m. Llevada a 1 mm, su impedancia (10⁻⁷ Ω) dejaba la matriz mal
    condicionada y el oráculo daba «no converge» en redes sanas: lo descubrió esta
    misma prueba al escribirla. Se calcula como conexión."""
    modelos = _modelos(tmp_path, 'completo')
    assert any(ln.length_m == 0 for m in modelos for ln in m.lines), (
        'la prueba necesita tramos de 0 m; si el generador ya no los produce, '
        'hay que fabricarlos aquí')
    for modelo in modelos:
        inf = oraculo.validar(modelo)
        assert inf.convergio, inf.resumen()


def test_una_conexion_con_su_maniobra_abierta_queda_abierta(tmp_path):
    """Calcular un tramo corto como conexión no puede cerrar lo que estaba abierto."""
    modelo = _modelos(tmp_path, 'completo')[0]
    corto = next(ln for ln in modelo.lines if ln.length_m == 0)
    net, _barra, _inf = oraculo.red_pandapower(modelo)
    fila = net.switch[net.switch.name == corto.section_id]
    assert len(fila) == 1 and bool(fila.closed.iloc[0])

    abierta = next(iter(modelo.devices))
    modelo.devices = type(modelo.devices)(
        [dataclasses.replace(abierta, section_id=corto.section_id, on_off=0)])
    net, _barra, _inf = oraculo.red_pandapower(modelo)
    fila = net.switch[net.switch.name == corto.section_id]
    assert not bool(fila.closed.iloc[0])


def test_el_balance_de_potencia_cuadra(tmp_path):
    """Lo que entrega la fuente es la carga más las pérdidas: si no cuadra, el flujo
    no ha calculado la red que dice."""
    for modelo in _modelos(tmp_path):
        inf = oraculo.validar(modelo)
        assert inf.p_carga_mw > 0
        assert inf.perdidas_mw is not None and inf.perdidas_mw >= 0
        assert inf.p_fuente_mw == pytest.approx(inf.p_carga_mw + inf.perdidas_mw, abs=1e-6)
        assert 0.9 < inf.v_min_pu <= inf.v_max_pu <= 1.0 + 1e-9


def test_no_modifica_el_modelo_y_es_determinista(tmp_path):
    modelo = _modelos(tmp_path)[0]
    antes = (repr(sorted(modelo.lines, key=lambda ln: ln.section_id)),
             repr(sorted(modelo.loads, key=lambda ld: ld.section_id)),
             repr(modelo.line_types))
    primero = oraculo.validar(modelo).as_dict()
    segundo = oraculo.validar(modelo).as_dict()
    despues = (repr(sorted(modelo.lines, key=lambda ln: ln.section_id)),
               repr(sorted(modelo.loads, key=lambda ld: ld.section_id)),
               repr(modelo.line_types))
    assert antes == despues, 'el oráculo valida; corregir el modelo no es asunto suyo'
    assert primero == segundo


def test_una_impedancia_nula_es_error_y_no_se_calcula(tmp_path):
    """Con R1 = X1 = 0 la matriz es singular: el oráculo dice la causa en vez de un
    «no converge» que la tape, y no lanza excepción."""
    modelo = _modelos(tmp_path)[0]
    clave = next(iter(modelo.lines)).type_key
    modelo.line_types[clave] = dataclasses.replace(
        modelo.line_types[clave], r1_ohm_km=0.0, x1_ohm_km=0.0)
    inf = oraculo.validar(modelo)
    assert not inf.convergio
    assert 'impedancia_nula' in {h.codigo for h in inf.errores}
    assert 'no_converge' not in {h.codigo for h in inf.hallazgos}


def test_la_red_unida_no_se_calcula(tmp_path):
    """Una red unida mezcla tensiones de varios alimentadores: el oráculo no la calcula
    y lo dice, en vez de dar un veredicto sin sentido."""
    modelo = _modelos(tmp_path)[0]
    modelo.combined = object()
    inf = oraculo.validar(modelo)
    assert not inf.disponible
    assert 'red unida' in inf.motivo_no_disponible


def test_sin_pandapower_lo_dice_y_no_falla(tmp_path, monkeypatch):
    modelo = _modelos(tmp_path)[0]
    monkeypatch.setattr(oraculo, 'disponible', lambda: False)
    inf = oraculo.validar(modelo)
    assert not inf.disponible
    assert 'pandapower' in inf.motivo_no_disponible


def test_no_llena_la_salida_de_avisos_de_numba(tmp_path, capfd):
    """Sin numba, pandapower imprimía un aviso de cuatro líneas por cada alimentador:
    96 avisos en un lote de la entrega real, tapando el Registro."""
    for modelo in _modelos(tmp_path):
        oraculo.validar(modelo)
    salida = capfd.readouterr()
    assert 'numba' not in (salida.out + salida.err).lower()
