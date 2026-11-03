"""Spec 072: proyección anual medida contra lo ocurrido, sin mirar el futuro."""
from __future__ import annotations

import pytest

from convertersmartgrid.proyeccion_mercado import (METODOS, MercadoError, SerieMercado, comparar_metodos,
                                                   errores_contra_lo_ocurrido, leer_hoja_formato_01,
                                                   perfiles_distintos, sector_tipico, sin_crecimiento, tasa_de_un_anio, tasa_media,
                                                   tendencia_logaritmica)

CRECE = {2000 + i: 100.0 * 1.05 ** i for i in range(10)}


def _hoja():
    return [(None,), ('Formato N° 01:',), ('Empresa',), ('Nombre:', 'EMPRESA X'), ('Sistema Eléctrico',),
            ('Código:', 'SE1'), ('Nombre:', 'Sistema Uno'), ('Sector:', '2'),
            ('Año', None, 'MW.h', 'Tasa (%)', 'MW'), ('Histórico',),
            ('2020', 1, 100.0, None, None), ('2021', 2, 110.0, 0.1, None), ('Proyección',),
            ('2022', 1, 120.0, 0.09, 5.0), ('2023', 2, None, None, None)]


def test_lee_el_formato_por_sus_rotulos():
    """072:RF-11 — la historia, lo proyectado por el entregable y el sector, sin confundir la empresa."""
    s = leer_hoja_formato_01(_hoja())
    assert s.codigo == 'SE1' and s.nombre == 'Sistema Uno' and s.sector == 'ST2'
    assert s.historico == {2020: 100.0, 2021: 110.0} and s.proyeccion_entregable == {2022: 120.0}
    assert leer_hoja_formato_01([('Otra hoja',), (1, 2)]) is None
    # Como en el libro real: la sección va en otra columna que el año.
    hoja = list(_hoja())
    hoja[9] = (None, 'Histórico')
    hoja[12] = (None, 'Proyección')
    assert leer_hoja_formato_01(hoja).historico == {2020: 100.0, 2021: 110.0}
    # Bajo «Año» va también el índice, con 00 en el año base: no se toma por año.
    real = hoja[:10] + [(None, '2024', 10, 90.0), (None, '2025', '00', 95.0)] + hoja[12:]
    real[8] = (None, 'Año', None, 'MW.h')
    real = [(f[0], f[1], f[2], f[3]) if len(f) > 3 else f for f in real]
    assert leer_hoja_formato_01(real).historico == {2024: 90.0, 2025: 95.0}


@pytest.mark.parametrize('texto, sector', [('2', 'ST2'), ('SECTOR TIPICO 4', 'ST4'), ('SER', 'SER'), ('', ''),
                                                  ('1900-01-03 00:00:00', 'ST3')])
def test_sector_como_lo_usa_el_sicodi(texto, sector):
    """072:RF-7 — el sector del Formato 01 sirve para buscar el costo."""
    assert sector_tipico(texto) == sector


@pytest.mark.parametrize('metodo', list(METODOS.values()))
def test_ningun_metodo_mira_el_futuro(metodo):
    """072:RF-11 — cambiar lo que viene después del corte no cambia el pronóstico."""
    a = metodo(CRECE, 2005, [2006, 2007])
    b = metodo({**CRECE, 2006: 9e9, 2009: 1.0}, 2005, [2006, 2007])
    assert a == b


def test_cada_metodo_hace_lo_que_dice():
    """072:RF-10 — sobre un crecimiento exacto del 5 %, aciertan los que proyectan; el último valor, no."""
    for metodo in (tasa_de_un_anio, tasa_media, tendencia_logaritmica):
        assert metodo(CRECE, 2005, [2009])[2009] == pytest.approx(CRECE[2009])
    assert sin_crecimiento(CRECE, 2005, [2009])[2009] == pytest.approx(CRECE[2005])


def test_la_tasa_de_un_anio_se_deja_llevar_por_el_ultimo():
    """072:RF-10 — un año raro arrastra a la referencia; por eso se compara."""
    raro = {2000: 100.0, 2001: 100.0, 2002: 100.0, 2003: 50.0}
    assert tasa_de_un_anio(raro, 2003, [2004])[2004] == pytest.approx(25.0)
    assert tendencia_logaritmica(raro, 2003, [2004])[2004] > 25.0


def test_el_error_es_contra_lo_ocurrido():
    """072:RF-11 — porcentaje absoluto, y solo en años con dato."""
    e = errores_contra_lo_ocurrido({2000: 100.0, 2001: 100.0, 2002: 100.0, 2003: 110.0}, [2002], 4)
    assert e['sin_crecimiento'] == pytest.approx([100 * 10 / 110])


def test_las_copias_a_escala_no_cuentan_como_pruebas():
    """072:RF-11 — dos series proporcionales son un perfil; otra forma, otro."""
    copia = {a: v * 3.0 for a, v in CRECE.items()}
    otra = {2000 + i: 100.0 + (i % 3) * 20 for i in range(10)}
    r = comparar_metodos([SerieMercado('A', 'A', 'ST2', CRECE), SerieMercado('B', 'B', 'ST2', copia),
                          SerieMercado('C', 'C', 'ST2', otra)], horizonte=2)
    assert r['sistemas'] == 3 and r['perfiles'] == 2
    assert len(perfiles_distintos([SerieMercado('A', 'A', '', CRECE)])) == 1


def test_el_ganador_sale_de_la_medida():
    """072:RF-10 — la referencia solo se cambia si otro la supera; y lo que no da, se dice."""
    r = comparar_metodos([SerieMercado('S', 'S', '2', CRECE)], horizonte=3)
    assert r['sistemas'] == 1 and r['perfiles'] == 1 and r['referencia'] == 'tasa_de_un_anio'
    assert r['mediana_error_pct']['sin_crecimiento'] > r['mediana_error_pct'][r['ganador']]
    igual = {2000 + i: 100.0 for i in range(6)}
    assert comparar_metodos([SerieMercado('S', 'S', '2', igual)], horizonte=2)['ganador'] == 'tasa_de_un_anio'
    with pytest.raises(MercadoError):
        comparar_metodos([SerieMercado('S', 'S', '2', {2000: 1.0})], horizonte=2)
    with pytest.raises(MercadoError):
        tasa_de_un_anio({2000: 1.0}, 2000, [2001])
