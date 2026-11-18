"""Spec 108 T18 — calidad de servicio con el criterio del num. 6.11 del TdR (108:RF-18, RF-13), tarjeta VAD-CAL.

SAIFI y SAIDI vigentes (RCD 074-2004-OS/CD consolidada con la RCD 177-2012-OS/CD, mensual y anual en MT), el % de
clientes que no excede N y D por semestre (Cuadro 21, NTCSE y NTCSER), los Cuadros 22 y 23 y los límites del registro.
Los datos son SINTÉTICOS (ejemplos de cc, z9 y z9c, comprobables a mano), de ninguna empresa.

Tarjeta VAD-CAL: las pruebas del criterio anterior (un valor medio por sistema contra un límite) se cambiaron, porque
ese criterio no es el del 6.11 y no da el Cuadro 21.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from convertersmartgrid.dominio.registro_normativo import RegistroError, RegistroNormativo, cargar_registro
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.aplicacion.vad.calidad import (
    CaidaTension,
    Cliente,
    Interrupcion,
    RegistroAnexo1,
    cuadro_21,
    cuadro_costos,
    filtrar_mt,
    limite_de,
    verificar_tension,
    n_d_por_cliente,
    saifi_saidi_anual_mt,
    saifi_saidi_mensual,
    verificar_calidad,
)

RAIZ = Path(__file__).resolve().parents[1]
FECHA = '2026-11-15'


@pytest.fixture(scope='module')
def reg():
    return cargar_registro(RAIZ / 'config' / 'normativa', RAIZ / 'config' / 'vad')


# Ejemplo z9c de cc (SINTÉTICO): un sistema, T_USUARIOS = 1000 en los meses 1 a 3; 20 registros del Anexo 1.
# (id, mes, E, G, L, N, O, P, T, resultado de la solicitud)
Z9C = [(1, 1, 2, 3, 200, 300.0, 'NF', 'D', 'N', None), (2, 1, 3, 4, 50, 100.0, 'PM', 'D', 'N', None),
       (3, 1, 1, 3, 400, 200.0, 'NF', 'D', 'N', None), (4, 1, 4, 5, 30, 90.0, 'NF', 'D', 'N', None),
       (5, 1, 2, 1, 300, 300.0, 'NF', 'D', 'N', None), (6, 1, 2, 3, 100, 100.0, 'NR', 'D', 'N', None),
       (7, 1, 2, 3, 150, 300.0, 'NF', 'T', 'N', None), (8, 2, 2, 3, 250, 500.0, 'NO', 'D', 'N', None),
       (9, 2, 6, 5, 80, 120.0, 'PE', 'D', 'N', None), (10, 2, 3, 4, 60, 60.0, 'NT', 'D', 'N', None),
       (11, 2, 2, 3, 500, 1500.0, 'NC', 'D', 'S', 'Fundada'), (12, 2, 2, 3, 120, 120.0, 'NF', 'D', 'S', 'Infundada'),
       (13, 2, 5, 3, 40, 80.0, 'NF', 'G', 'N', None), (14, 2, 2, 2, 90, 90.0, 'NF', 'D', 'N', None),
       (15, 3, 1, 5, 300, 300.0, 'NF', 'D', 'N', None), (16, 3, 2, 3, 70, 280.0, 'PM', 'D', 'N', None),
       (17, 3, 4, 3, 60, 60.0, 'NF', 'D', 'N', None), (18, 3, 2, 3, 200, 100.0, 'NR', 'D', 'N', None),
       (19, 3, 3, 4, 100, 100.0, 'NF', 'D', 'S', 'En trámite'), (20, 3, 2, 3, 110, 220.0, 'NF', 'D', 'S', 'Improcedente')]
REGISTROS = [RegistroAnexo1(i, 'SIS1', m, e, g, ell, n, o, p, t, res) for i, m, e, g, ell, n, o, p, t, res in Z9C]
USUARIOS = {('SIS1', m): 1000 for m in (1, 2, 3)}


def test_saifi_saidi_mensual_del_ejemplo_z9c(reg):
    """108:RF-18 (VAD-CAL) — por sistema y mes, SAIFI = ΣL/T_USUARIOS y SAIDI = ΣN/T_USUARIOS con TODOS los
    registros del mes (Anexo 2 de la RCD 074-2004 consolidada): 1,23 y 1,39 h; 1,14 y 2,47; 0,84 y 1,06."""
    r = saifi_saidi_mensual(reg, REGISTROS, USUARIOS, FECHA)
    assert {k: (round(v.saifi, 6), round(v.saidi, 6)) for k, v in r.items()} == {
        ('SIS1', 1): (1.23, 1.39), ('SIS1', 2): (1.14, 2.47), ('SIS1', 3): (0.84, 1.06)}
    assert r[('SIS1', 1)].registros == (1, 2, 3, 4, 5, 6, 7)
    assert r[('SIS1', 1)].regla == 'vad.calidad.saifi_saidi.mensual'


def test_saifi_saidi_anual_mt_del_ejemplo_z9c_con_los_excluidos_por_filtro(reg):
    """108:RF-18 (VAD-CAL) — anual en MT (Anexo 3): la suma de los 12 meses con los registros que pasan E, G, O, P y
    T: SAIFI_MT 1,64 y SAIDI_MT 2,20 h; fuera por filtro, los que cc marcó; dentro, los 10 que quedan."""
    r = saifi_saidi_anual_mt(reg, REGISTROS, USUARIOS, FECHA)
    assert {k: (round(v.saifi, 6), round(v.saidi, 6)) for k, v in r.items()} == {'SIS1': (1.64, 2.2)}
    a = r['SIS1']
    assert a.registros == (1, 2, 3, 8, 9, 10, 12, 15, 16, 20)
    assert a.fuera_por_filtro == {'E': (4, 17), 'G': (5, 14), 'O': (6, 18), 'P': (7, 13), 'T': (11, 19)}
    dentro, fuera = filtrar_mt(reg, REGISTROS, FECHA)
    assert [x.id for x in dentro] == list(a.registros) and fuera['T'] == [11, 19]
    # mutación de cc: el 12 «Fundada» sale por T y el SAIFI MT baja de 1,64 a 1,52.
    mut = [dataclasses.replace(x, resultado_T='Fundada') if x.id == 12 else x for x in REGISTROS]
    assert round(saifi_saidi_anual_mt(reg, mut, USUARIOS, FECHA)['SIS1'].saifi, 6) == 1.52
    with pytest.raises(VadError, match='T_USUARIOS'):
        saifi_saidi_anual_mt(reg, REGISTROS, {('SIS1', 1): 1000}, FECHA)


def _bt_z9(fila='Urbano Densidad Media'):
    """Ejemplo z9 de cc (SINTÉTICO): 10 clientes BT urbanos y 9 interrupciones en un semestre."""
    clientes = [Cliente(f'c{i}', fila, 'BT', sector_tipico='3') for i in range(10)]
    c = [x.id for x in clientes]
    ints = [Interrupcion(tuple(c), 2.0), Interrupcion(tuple(c[:5]), 4.0, 'mantenimiento'),
            Interrupcion(tuple(c[:2]), 3.0), Interrupcion((c[0],), 1.5)]
    ints += [Interrupcion(tuple(c[:2]), 0.5) for _ in range(5)]
    return clientes, ints


def test_el_criterio_antiguo_no_produce_el_cuadro_21(reg):
    """108:RF-18 (VAD-CAL, rojo pedido por 28) — con las medias dentro de N' y D' (2,8 ≤ 6 y 4,25 ≤ 10 h) el criterio
    anterior, que comparaba la media del sistema, daba «cumple»; el 6.11 pide el % de clientes que exceden: 20 %
    (c0 por N y por D; c1 por N), y la verificación lo nombra."""
    clientes, ints = _bt_z9()
    c21 = cuadro_21(reg, clientes, ints, FECHA)
    llenas = [(x.fila, x.nivel, x.clientes, round(x.frecuencia, 6), round(x.duracion, 6), x.pct_excedido, x.estado)
              for x in c21.celdas if x.clientes]
    assert llenas == [('Urbano Densidad Media', 'BT', 10, 2.8, 4.25, 20.0, 'no_cumple'),
                      ('Total Empresa Modelo', 'BT', 10, 2.8, 4.25, 20.0, 'no_cumple')]
    assert 2.8 <= 6 and 4.25 <= 10  # las medias cumplen: el criterio anterior no veía a c0 ni a c1
    celda = c21.celda('Urbano Densidad Media', 'BT')
    assert celda.excede_n == ('c0', 'c1') and celda.excede_d == ('c0',)
    r = verificar_calidad(reg, clientes, ints, fecha=FECHA)
    assert r.estado == 'no_cumple'
    assert {(v.sistema, v.indicador, v.valor) for v in r.no_cumplen} == {
        ('Urbano Densidad Media / cliente BT', 'interrupciones', 20.0),
        ('Urbano Densidad Media / cliente BT', 'duracion', 10.0),
        ('Total Empresa Modelo / cliente BT', 'interrupciones', 20.0),
        ('Total Empresa Modelo / cliente BT', 'duracion', 10.0)}
    assert 'c0, c1' in next(v.motivo for v in r.no_cumplen if v.indicador == 'interrupciones')


def test_cuadro_21_por_semestre_con_mt_y_bt(reg):
    """108:RF-18 (VAD-CAL) — el Cuadro 21 se calcula por semestre: filas y columnas del registro (pág. 50), MT con el
    +30 % del Sector Típico 2 (N' 6, D' 10) y BT urbano (6 y 10)."""
    bt, ints1 = _bt_z9()
    mt = [Cliente('m0', 'Urbano Alta Densidad', 'MT', sector_tipico='2'),
          Cliente('m1', 'Urbano Alta Densidad', 'MT', sector_tipico='2')]
    ints1 = ints1 + [Interrupcion(('m0', 'm1'), 1.0) for _ in range(5)]
    s1 = cuadro_21(reg, bt + mt, ints1, FECHA)
    assert s1.titulo == 'Interrupciones medias por semestre'
    assert s1.filas == ('Urbano Muy Alta Densidad', 'Urbano Alta Densidad', 'Urbano Densidad Media',
                        'Urbano Densidad Baja', 'Urbano Rural', 'Rural', 'Total Empresa Modelo')
    assert len(s1.celdas) == 14
    assert [(x.fila, x.nivel, x.frecuencia, x.duracion, x.pct_excedido) for x in s1.celdas if x.nivel == 'MT'
            and x.clientes] == [('Urbano Alta Densidad', 'MT', 5.0, 5.0, 0.0), ('Total Empresa Modelo', 'MT', 5.0,
                                                                              5.0, 0.0)]
    ints2 = [Interrupcion(tuple(c.id for c in bt), 1.0)] + [Interrupcion(('m0',), 0.1) for _ in range(7)]
    s2 = cuadro_21(reg, bt + mt, ints2, FECHA)
    assert [(x.fila, x.nivel, round(x.frecuencia, 6), round(x.duracion, 6), x.pct_excedido, x.estado)
            for x in s2.celdas if x.clientes] == [
        ('Urbano Alta Densidad', 'MT', 3.5, 0.35, 50.0, 'no_cumple'),
        ('Urbano Densidad Media', 'BT', 1.0, 1.0, 0.0, 'cumple'),
        ('Total Empresa Modelo', 'MT', 3.5, 0.35, 50.0, 'no_cumple'),
        ('Total Empresa Modelo', 'BT', 1.0, 1.0, 0.0, 'cumple')]
    assert s2.celda('Urbano Rural', 'BT').estado == 'sin_clientes'


def test_cuadro_21_en_la_ntcser_con_nic_y_dic_del_ser(reg):
    """108:RF-18 (VAD-CAL) — en un SER, NIC y DIC son promedios del SER y el nivel (NTCSER 5.1.2): el SER disperso
    con NIC 5,5 ≤ 10 no excede aunque dos de sus clientes tengan 11; el concentrado con 11 y 33 h excede (10 y 25)."""
    r = [Cliente(f'r{i}', 'Rural', 'BT', 'NTCSER', '5', sistema='S1') for i in range(4)]
    q = [Cliente(f'q{i}', 'Rural', 'BT', 'NTCSER', '4', sistema='S2') for i in range(2)]
    ints = [Interrupcion(('r0', 'r1'), 1.0) for _ in range(11)] + [Interrupcion(('q0', 'q1'), 3.0) for _ in range(11)]
    c = cuadro_21(reg, r + q, ints, FECHA)
    assert [(x.fila, x.clientes, round(x.frecuencia, 4), round(x.duracion, 4), round(x.pct_excedido, 4),
             x.excede_n, x.excede_d) for x in c.celdas if x.clientes] == [
        ('Rural', 6, 7.3333, 14.6667, 33.3333, ('q0', 'q1'), ('q0', 'q1')),
        ('Total Empresa Modelo', 6, 7.3333, 14.6667, 33.3333, ('q0', 'q1'), ('q0', 'q1'))]
    with pytest.raises(VadError, match='SER'):
        cuadro_21(reg, [Cliente('x', 'Rural', 'BT', 'NTCSER', '5')], [], FECHA)


def test_n_y_d_por_cliente_con_las_ponderaciones_de_la_norma(reg):
    """108:RF-18 (VAD-CAL) — NTCSE 6.1.2-6.1.3: expansión al 50 % en N y Ki 0,25; mantenimiento Ki 0,5; la diferencia
    con lo programado a 1 (real mayor) o a 0 (real menor); fuera las de menos de 3 min, la fuerza mayor y el rechazo de
    carga. En la NTCSER (5.1.2) NIC no pondera y el rechazo de carga cuenta."""
    ints = [Interrupcion(('a',), 2.0, 'expansion'), Interrupcion(('a',), 3.0, 'mantenimiento', 2.0),
            Interrupcion(('a',), 1.0, 'mantenimiento', 2.0), Interrupcion(('a',), 0.04),
            Interrupcion(('a',), 1.0, fuerza_mayor=True), Interrupcion(('a',), 1.0, rechazo_carga=True)]
    assert n_d_por_cliente(reg, ints, ['a', 'b'], 'NTCSE', FECHA) == {'a': (2.5, 3.0), 'b': (0.0, 0.0)}
    assert n_d_por_cliente(reg, ints, ['a'], 'NTCSER', FECHA) == {'a': (4.0, 4.0)}
    with pytest.raises(VadError, match='CAL-DS'):
        n_d_por_cliente(reg, [Interrupcion(('a',), 1.0, inaplicada='DS 020-2026-EM')], ['a'], 'NTCSE', FECHA)


def test_limites_del_registro_con_su_cita_y_el_30_por_ciento_del_st2(reg):
    """108:RF-18 (VAD-CAL) — N' y D' de la NTCSE oficial (6.1.4 y 6.1.5), con el +30 % del Sector Típico 2 redondeado
    al entero superior (DS 009-99-EM art. 4, texto del DS 040-2001-EM), y NIC' y DIC' de la NTCSER (5.1.3). Cada regla
    citada y obligatoria, y las de la NTCSE y la NTCSER en la misma entrada de su acto."""
    claves = {r.clave: n.acto for n in reg.normas.values() for r in n.reglas}
    assert {k: claves.get(k) for k in ('vad.calidad.limite.interrupciones', 'vad.calidad.limite.duracion',
                                       'vad.calidad.limite.incremento_sector_tipico_2',
                                       'vad.calidad.limite.interrupciones_ser', 'vad.calidad.limite.duracion_ser',
                                       'calidad.tension.tolerancia_ntcse')} == {
        'vad.calidad.limite.interrupciones': 'DS 020-97-EM', 'vad.calidad.limite.duracion': 'DS 020-97-EM',
        'vad.calidad.limite.incremento_sector_tipico_2': 'DS 009-99-EM',
        'vad.calidad.limite.interrupciones_ser': 'RD 016-2008-EM/DGE',
        'vad.calidad.limite.duracion_ser': 'RD 016-2008-EM/DGE', 'calidad.tension.tolerancia_ntcse': 'DS 020-97-EM'}
    assert sum('020-97' in a for a in reg.normas) == 1 and sum('016-2008' in a for a in reg.normas) == 1
    st2 = reg.regla('vad.calidad.limite.incremento_sector_tipico_2', FECHA)
    assert st2.obligatoria and 'treinta por ciento (30%)' in st2.regla.cita_literal
    # v2 (regla del auditor 28): el redondeo se aplica porque lo dice la norma, con su cita literal (DS 040-2001-EM,
    # art. 4, pdf 14); sin ella el límite sería el valor exacto (4 × 1,3 = 5,2).
    assert 'Tales incrementos se redondean al entero superior' in st2.regla.cita_literal
    assert st2.regla.valor['redondeo'] == 'entero_superior' and 'DS 040-2001-EM' in st2.norma.modificada_por
    assert ': 4 Interrupciones/semestre' in reg.regla('vad.calidad.limite.interrupciones').regla.cita_literal
    casos = {('MT', 'NTCSE', '3', 'urbano'): (4, 7), ('BT', 'NTCSE', '3', 'urbano'): (6, 10),
             ('BT', 'NTCSE', '3', 'urbano_rural'): (9, 20), ('BT', 'NTCSE', '3', 'rural'): (9, 35),
             ('MT', 'NTCSE', '3', 'rural'): (4, 7), ('MT', 'NTCSE', '2', 'urbano'): (6, 10),
             ('BT', 'NTCSE', '2', 'urbano'): (8, 13), ('MT', 'NTCSER', '4', 'urbano'): (7, 17),
             ('BT', 'NTCSER', 'Especial', 'urbano'): (10, 40), ('MT', 'NTCSER', '5', 'urbano'): (7, 28)}
    obtenido = {k: (lambda x: (x.n, x.d))(limite_de(reg, Cliente('x', 'Rural', k[0], k[1], k[2], k[3]), FECHA))
                for k in casos}
    assert obtenido == casos
    assert 'vad.calidad.limite.incremento_sector_tipico_2' in limite_de(
        reg, Cliente('x', 'Rural', 'MT', 'NTCSE', '2'), FECHA).reglas


def test_vigencias_por_su_clausula_o_por_el_art_109(reg):
    """108:RF-18 (VAD-CAL v2, regla del auditor 28) — la vigencia de cada norma sale de su cláusula de vigencia y, si
    no la tiene, del art. 109 de la Constitución (el día siguiente a la publicación), y la nota dice cuál se aplicó: ni
    el DS 040-2001-EM (publicado el 17-07-2001) ni la RCD 177-2012-OS/CD (29-08-2012) la tienen en el texto oficial."""
    actos = {'DS 009-99-EM': '2001-07-18', 'RCD 074-2004-OS/CD': '2012-08-30'}
    assert {a: reg.normas[a].vigencia_desde if a in reg.normas else None for a in actos} == actos
    for acto in actos:
        nota = reg.normas[acto].nota
        assert 'art. 109 de la Constitución' in nota and 'día siguiente de su publicación' in nota, acto
    assert 'Primera.- Disponer que el OSINERG adecue' in reg.normas['DS 009-99-EM'].nota
    assert 'es de la RCD 074-2004 de 2004, no de la modificatoria' in reg.normas['RCD 074-2004-OS/CD'].nota
    # el día de la publicación todavía no rigen; el siguiente, sí.
    with pytest.raises(RegistroError, match='incremento_sector_tipico_2'):
        reg.regla('vad.calidad.limite.incremento_sector_tipico_2', '2001-07-17')
    assert reg.regla('vad.calidad.limite.incremento_sector_tipico_2', '2001-07-18').obligatoria
    with pytest.raises(RegistroError, match='anual_mt'):
        reg.regla('vad.calidad.saifi_saidi.anual_mt', '2012-08-29')
    assert reg.regla('vad.calidad.saifi_saidi.anual_mt', '2012-08-30').obligatoria


def test_huecos_nombrados_rm_163_2011_y_curvas_de_distribucion(reg):
    """108:RF-18 (VAD-CAL) — la RM 163-2011-MEM/DM no tiene copia oficial: el SAIFI/SAIDI anual MT lleva su hueco y la
    cita del 9.4; las curvas de distribución del 6.11 no las regula ninguna norma: el Cuadro 21 lleva su hueco; el
    ST 2 con el 6.1.5 a la vez no tiene regla de combinación: hueco, nunca «cumple»."""
    anual = saifi_saidi_anual_mt(reg, REGISTROS, USUARIOS, FECHA)
    assert [h.clave for x in anual.values() for h in x.huecos] == ['rm_163_2011']
    a = anual['SIS1']
    assert '9.4' in reg.regla(a.regla).regla.cita_literal and '163-2011' in reg.regla(a.regla).regla.cita_literal
    clientes, ints = _bt_z9()
    c21 = cuadro_21(reg, clientes, ints, FECHA)
    assert [h.clave for h in c21.huecos] == ['curvas_distribucion']
    assert 'curvas de distribución' in reg.regla('vad.calidad.criterio_6_11').regla.cita_literal
    lim = limite_de(reg, Cliente('x', 'Rural', 'BT', 'NTCSE', '2', 'rural'), FECHA)
    assert (lim.n, lim.d, lim.hueco.clave if lim.hueco else None) == (None, None, 'st2_y_6_1_5')
    r = verificar_calidad(reg, [Cliente('x', 'Rural', 'BT', 'NTCSE', '2', 'rural')], [], fecha=FECHA)
    assert r.estado == 'sin_verificar' and 'Sector Típico 2' in r.sin_verificar[0].motivo
    assert [h.clave for h in r.huecos] == ['curvas_distribucion']


def test_cuadros_22_y_23_con_su_estructura(reg):
    """108:RF-18 (VAD-CAL) — los Cuadros 22 (inversión) y 23 (OyM anual) con las filas del registro (págs. 50-51) en
    US$: lo no dimensionado se nombra y queda fuera del total; «Otros (especificar)» exige especificación."""
    c22 = cuadro_costos(reg, 22, {'Equipamiento para trabajos con tensión en MT.': 1000.0},
                        {'Telemando de reconectadores': 250.0}, FECHA)
    assert (c22.titulo, c22.columnas, c22.total) == ('Costos de Inversión', ('Inversión', 'US$'), 1250.0)
    assert [f.concepto for f in c22.filas] == [
        'Sistemas de cómputo calidad de suministro (Software, hardware.)',
        'Equipos de medición y registro de calidad de producto y suministro',
        'Equipamiento de protección, seccionamiento y maniobra MT.', 'Equipamiento para trabajos con tensión en MT.',
        'Enlaces y cierres asociados a la calidad del servicio eléctrico.', 'Otros (especificar)']
    assert c22.filas[-1].especificacion == 'Telemando de reconectadores' and len(c22.sin_dimensionar) == 4
    c23 = cuadro_costos(reg, 23, {}, None, FECHA)
    assert (c23.titulo, len(c23.filas), c23.total) == ('Costos de Operación y Mantenimiento Anual', 6, 0.0)
    assert c23.columnas == ('Operación y mantenimiento', 'US$') and len(c23.sin_dimensionar) == 6
    assert reg.regla('vad.calidad.cuadro_23').regla.moneda == 'USD'
    with pytest.raises(VadError, match='no tiene las filas'):
        cuadro_costos(reg, 22, {'Otra fila': 1.0}, None, FECHA)
    with pytest.raises(VadError, match='sin especificar'):
        cuadro_costos(reg, 23, {}, {' ': 1.0}, FECHA)
    with pytest.raises(VadError, match='no negativo'):
        cuadro_costos(reg, 22, {'Equipamiento para trabajos con tensión en MT.': -1.0}, None, FECHA)


def test_un_caso_que_cumple_en_el_limite_exacto(reg):
    """108:RF-18 — cambiada por VAD-CAL: un cliente BT urbano con N = 6 y D = 10 h exactos cumple; todo en norma da
    «cumple» (antes era un valor medio por sistema en su límite)."""
    ints = [Interrupcion(('c',), 1.0) for _ in range(5)] + [Interrupcion(('c',), 5.0)]
    c = [Cliente('c', 'Urbano Densidad Baja', 'BT', sector_tipico='3')]
    assert [(x.fila, x.frecuencia, x.duracion, x.estado) for x in cuadro_21(reg, c, ints, FECHA).celdas
            if x.clientes] == [('Urbano Densidad Baja', 6.0, 10.0, 'cumple'), ('Total Empresa Modelo', 6.0, 10.0,
                                                                              'cumple')]
    r = verificar_calidad(reg, c, ints,
                          [CaidaTension('S1', 'MT', 5.0)], FECHA)
    assert r.estado == 'cumple' and not r.no_cumplen and not r.sin_verificar
    assert r.cuadro_21.celda('Urbano Densidad Baja', 'BT').pct_excedido == 0.0


def test_limite_que_no_obliga_no_se_da_por_cumplido(reg):
    """108:RF-18 — cambiada por VAD-CAL: con la NTCSE en un estado que no obliga, la celda queda sin verificar y lo
    dice; nunca «cumple»."""
    n = reg.normas['DS 020-97-EM']
    otro = RegistroNormativo({**reg.normas, n.acto: dataclasses.replace(n, estado_juridico='prepublicada')})
    lim = limite_de(otro, Cliente('c', 'Urbano Densidad Baja', 'BT', sector_tipico='3'), FECHA)
    assert (lim.n, lim.d, lim.hueco.clave if lim.hueco else None) == (None, None, 'limite_no_obliga')
    r = verificar_calidad(otro, [Cliente('c', 'Urbano Densidad Baja', 'BT', sector_tipico='3')], [], fecha=FECHA)
    assert r.estado == 'sin_verificar' and 'no obliga' in r.sin_verificar[0].motivo


def test_caida_de_tension_con_las_tolerancias_registradas(reg):
    """108:RF-18 — cambiada por VAD-CAL: calidad de producto con calidad.tension.tolerancia_ntcse y _ntcser (NTCSE
    5.1.2, NTCSER 4.1.2), sin repetir la cita: 5,5 % en MT urbano no cumple (5 %); 7 % en BT rural (7,5 %) y 5,9 % en
    MT de un SER (6 %) cumplen."""
    sueltas = [verificar_tension(reg, CaidaTension('S1', 'BT', 7.6, 'NTCSE', 'urbano_rural'), FECHA),
               verificar_tension(reg, CaidaTension('S1', 'BT', 5.1), FECHA)]
    assert [(v.estado, v.limite) for v in sueltas] == [('no_cumple', 7.5), ('no_cumple', 5.0)]
    bt, ints = [Cliente('c', 'Rural', 'BT', sector_tipico='3')], []
    r = verificar_calidad(reg, bt, ints, [CaidaTension('S1', 'MT', 5.5), CaidaTension('S1', 'BT', 7.0, 'NTCSE',
                                                                                         'rural'),
                                          CaidaTension('S2', 'MT', 5.9, 'NTCSER')], FECHA)
    assert [(v.sistema, v.indicador, v.estado, v.limite) for v in r.verificaciones if 'caida' in v.indicador] == [
        ('S1', 'caida_tension_mt', 'no_cumple', 5.0), ('S1', 'caida_tension_bt', 'cumple', 7.5),
        ('S2', 'caida_tension_mt', 'cumple', 6.0)]
    assert 'supera la tolerancia 5 %' in r.no_cumplen[0].motivo


def test_entradas_invalidas_se_rechazan(reg):
    """108:RF-18 — cambiada por VAD-CAL: sin clientes, con una fila que el Cuadro 21 no tiene, con interrupciones de
    clientes desconocidos, con un tipo o un nivel que no existen o sin registros, se rechaza con mensaje."""
    c = Cliente('c', 'Rural', 'BT')
    with pytest.raises(VadError, match='ningún cliente'):
        cuadro_21(reg, [], [], FECHA)
    with pytest.raises(VadError, match='fila'):
        cuadro_21(reg, [Cliente('c', 'Selva', 'BT')], [], FECHA)
    with pytest.raises(VadError, match='no están'):
        cuadro_21(reg, [c], [Interrupcion(('z',), 1.0)], FECHA)
    with pytest.raises(VadError, match='tipo'):
        cuadro_21(reg, [c], [Interrupcion(('c',), 1.0, 'otra')], FECHA)
    with pytest.raises(VadError, match='nivel'):
        limite_de(reg, Cliente('c', 'Rural', 'AT'), FECHA)
    with pytest.raises(VadError, match='ningún registro'):
        saifi_saidi_mensual(reg, [], USUARIOS, FECHA)
