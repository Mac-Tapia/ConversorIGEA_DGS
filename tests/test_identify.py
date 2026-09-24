"""Reconocer cada TXT por su contenido, porque el nombre no dice nada.

Los TXT que entrega la distribuidora no siguen ninguna convención: el nombre lo pone
quien hace la exportación y cambia de una entrega a otra. El conversor funciona con
cualquier nombre —comprobado con ``exportacion_enero.txt``, ``demanda.txt`` y
``catalogo.txt``—, y precisamente por eso el nombre no protege de nada.

La confusión que importa es la que no fallaba: poner el catálogo de equipos en la
casilla de cargas daba un dataset con **0 cargas** y la conversión seguía adelante. El
DGS resultante converge, se importa en DigSILENT y da un flujo de potencia impecable de
una red que no alimenta a nadie. Un error que no falla es peor que uno que falla.
"""

from __future__ import annotations

import pytest

from igea_dgs.identify import (
    CARGA,
    DESCONOCIDO,
    EQUIPOS,
    NOMBRES,
    RED,
    comprobar_ranura,
    identificar,
    repartir,
    tablas_de,
)


def _escribir(tmp_path, nombre: str, tablas: list[str]) -> str:
    """Un TXT mínimo con las tablas indicadas, con el nombre que se quiera."""
    contenido = ['[GENERAL]', 'DATE=01/01/2026', '']
    for t in tablas:
        contenido += [f'[{t}]', f'FORMAT_{t.replace(" ", "")}=ID,A,B', 'X,1,2', '']
    ruta = tmp_path / nombre
    ruta.write_text('\n'.join(contenido), encoding='utf-8')
    return str(ruta)


class TestElNombreNoImporta:
    def test_un_red_con_cualquier_nombre_se_reconoce(self, tmp_path):
        for nombre in ('exportacion_enero.txt', 'x.txt', 'RED_030826(1).txt',
                       'datos finales v3 FINAL.txt'):
            ruta = _escribir(tmp_path, nombre, ['NODE', 'SECTION', 'SOURCE'])
            assert identificar(ruta).tipo == RED, nombre

    def test_una_carga_con_cualquier_nombre_se_reconoce(self, tmp_path):
        for nombre in ('demanda.txt', 'clientes 2026.txt'):
            ruta = _escribir(tmp_path, nombre, ['LOADS', 'CUSTOMER LOADS'])
            assert identificar(ruta).tipo == CARGA, nombre

    def test_un_catalogo_con_cualquier_nombre_se_reconoce(self, tmp_path):
        ruta = _escribir(tmp_path, 'catalogo.txt', ['CONDUCTOR', 'LINE'])
        assert identificar(ruta).tipo == EQUIPOS

    def test_un_fichero_ajeno_no_se_confunde_con_ninguno(self, tmp_path):
        ruta = tmp_path / 'notas.txt'
        ruta.write_text('esto no es un export\nsolo texto\n', encoding='utf-8')
        ident = identificar(ruta)
        assert ident.tipo == DESCONOCIDO
        assert ident.tablas == frozenset()

    def test_un_fichero_que_no_existe_no_revienta(self, tmp_path):
        assert identificar(tmp_path / 'no_esta.txt').tipo == DESCONOCIDO


class TestLaConfusionQueNoFallaba:
    def test_el_catalogo_en_la_casilla_de_carga_se_rechaza(self, tmp_path):
        """Antes pasaba sin ruido y producía una red sin demanda."""
        catalogo = _escribir(tmp_path, 'equipos.txt', ['CONDUCTOR', 'LINE'])
        problema = comprobar_ranura(catalogo, CARGA)
        assert problema
        assert 'BD_Equipo' in problema
        assert 'CARGA' in problema

    def test_el_mensaje_dice_QUE_es_y_QUE_se_esperaba(self, tmp_path):
        red = _escribir(tmp_path, 'algo.txt', ['NODE', 'SECTION'])
        problema = comprobar_ranura(red, EQUIPOS)
        assert NOMBRES[RED].split(' ')[0] in problema
        assert NOMBRES[EQUIPOS].split(' ')[0] in problema

    def test_el_mensaje_enseña_la_evidencia(self, tmp_path):
        """Sin las tablas, el operador no puede comprobar si el aviso tiene razón."""
        red = _escribir(tmp_path, 'algo.txt', ['NODE', 'SECTION'])
        assert '[NODE]' in comprobar_ranura(red, CARGA)

    def test_el_mensaje_aclara_que_el_nombre_da_igual(self, tmp_path):
        red = _escribir(tmp_path, 'algo.txt', ['NODE'])
        assert 'nombre del fichero no importa' in comprobar_ranura(red, CARGA)

    def test_lo_que_encaja_no_da_problema(self, tmp_path):
        assert comprobar_ranura(_escribir(tmp_path, 'a.txt', ['NODE']), RED) == ''
        assert comprobar_ranura(_escribir(tmp_path, 'b.txt', ['CUSTOMER LOADS']), CARGA) == ''
        assert comprobar_ranura(_escribir(tmp_path, 'c.txt', ['CONDUCTOR']), EQUIPOS) == ''

    def test_un_fichero_ajeno_se_explica_como_tal(self, tmp_path):
        ruta = tmp_path / 'x.txt'
        ruta.write_text('hola\n', encoding='utf-8')
        assert 'no parece un export' in comprobar_ranura(ruta, RED)


class TestRepartoAutomatico:
    def test_asigna_cada_uno_a_su_papel_en_cualquier_orden(self, tmp_path):
        a = _escribir(tmp_path, 'uno.txt', ['CONDUCTOR'])
        b = _escribir(tmp_path, 'dos.txt', ['NODE', 'SECTION'])
        c = _escribir(tmp_path, 'tres.txt', ['CUSTOMER LOADS'])
        rep = repartir([a, b, c])
        assert rep[RED].name == 'dos.txt'
        assert rep[CARGA].name == 'tres.txt'
        assert rep[EQUIPOS].name == 'uno.txt'

    def test_ante_dos_del_mismo_tipo_deja_la_casilla_sin_duplicar(self, tmp_path):
        """Mejor una casilla vacía que rellenarla con el fichero equivocado."""
        a = _escribir(tmp_path, 'red1.txt', ['NODE'])
        b = _escribir(tmp_path, 'red2.txt', ['NODE'])
        rep = repartir([a, b])
        assert rep[RED].name == 'red1.txt'
        assert CARGA not in rep and EQUIPOS not in rep

    def test_ignora_los_que_no_reconoce(self, tmp_path):
        basura = tmp_path / 'z.txt'
        basura.write_text('nada\n', encoding='utf-8')
        red = _escribir(tmp_path, 'r.txt', ['NODE'])
        assert set(repartir([basura, red])) == {RED}


class TestElMotorAborta:
    def test_from_files_rechaza_las_casillas_cruzadas(self, tmp_path):
        from igea_dgs.dataset import CymdistDataset

        red = _escribir(tmp_path, 'a.txt', ['NODE', 'SECTION', 'SOURCE'])
        carga = _escribir(tmp_path, 'b.txt', ['CUSTOMER LOADS'])
        equipos = _escribir(tmp_path, 'c.txt', ['CONDUCTOR', 'LINE'])
        with pytest.raises(ValueError, match='no corresponden con su casilla'):
            CymdistDataset.from_files(red, equipos, carga)

    def test_el_error_menciona_los_dos_ficheros_mal_puestos(self, tmp_path):
        from igea_dgs.dataset import CymdistDataset

        red = _escribir(tmp_path, 'a.txt', ['NODE', 'SECTION'])
        carga = _escribir(tmp_path, 'b.txt', ['CUSTOMER LOADS'])
        equipos = _escribir(tmp_path, 'c.txt', ['CONDUCTOR'])
        with pytest.raises(ValueError) as exc:
            CymdistDataset.from_files(red, equipos, carga)
        mensaje = str(exc.value)
        assert 'c.txt' in mensaje and 'b.txt' in mensaje


class TestExportReal:
    """Contra el export de verdad. Las fixtures RED/LOAD/EQUIP tapan las constantes
    del módulo dentro de estas funciones, así que aquí los tipos se nombran por su
    valor literal."""

    def test_los_tres_ficheros_reales_se_reconocen(self, RED, LOAD, EQUIP):
        assert identificar(RED).tipo == 'red'
        assert identificar(LOAD).tipo == 'carga'
        assert identificar(EQUIP).tipo == 'equipos'

    def test_el_export_real_funciona_con_nombres_arbitrarios(self, tmp_path, RED, LOAD, EQUIP):
        """Lo que hace falta: que la próxima entrega se llame como sea."""
        import shutil

        from igea_dgs.dataset import CymdistDataset

        r = tmp_path / 'exportacion_enero.txt'
        c = tmp_path / 'demanda.txt'
        e = tmp_path / 'catalogo.txt'
        for origen, destino in ((RED, r), (LOAD, c), (EQUIP, e)):
            shutil.copy(origen, destino)
        ds = CymdistDataset.from_files(r, c, e)
        assert ds.feeder_ids()
        assert ds.customer_loads, 'las cargas deben llegar igual que con los nombres de siempre'

    def test_el_reparto_automatico_acierta_con_el_export_real(self, RED, LOAD, EQUIP):
        rep = repartir([EQUIP, LOAD, RED])
        assert rep['red'] == RED
        assert rep['carga'] == LOAD
        assert rep['equipos'] == EQUIP

    def test_leer_las_tablas_no_recorre_el_fichero_entero(self, RED):
        """Un export pesa cientos de megas; reconocerlo debe costar milisegundos."""
        import time

        t0 = time.perf_counter()
        tablas = tablas_de(RED)
        assert 'NODE' in tablas
        assert time.perf_counter() - t0 < 2.0
