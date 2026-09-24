"""Catálogo de estudios del año 0: qué se puede correr y qué dato falta.

La distinción que estas pruebas protegen es la que da valor al módulo: **se ejecuta**
no es lo mismo que **es defendible**. ``ComRel3`` corre sin problemas con todas las
tasas de falla a cero y devuelve SAIDI = 0. No falla, miente. Si esa distinción se
diluye, el informe pasa de ser útil a ser peligroso, porque presentaría como resultado
del año 0 un número que nadie puede sostener ante Osinergmin.
"""

from __future__ import annotations

import pytest

from igea_dgs.studies import (
    AUSENTE,
    DISPONIBLE,
    ESTUDIOS,
    PARCIAL,
    POR_DEFECTO,
    Entrada,
    Estudio,
    auditar_datos,
    datos_que_faltan,
    entradas_por_nombre,
    estudios_bloqueados,
    estudios_ejecutables,
)


class TestEstadoDeUnaEntrada:
    def test_lo_ausente_bloquea(self):
        assert Entrada('x', AUSENTE, 'de ningún sitio', 'nada funciona').bloquea

    def test_un_valor_por_defecto_TAMBIEN_bloquea(self):
        """Es el caso traicionero: la columna existe y trae el mismo valor en todo."""
        assert Entrada('x', POR_DEFECTO, 'catálogo', 'sale igual en toda la red').bloquea

    def test_lo_disponible_no_bloquea(self):
        assert not Entrada('x', DISPONIBLE, 'el export', 'nada').bloquea

    def test_lo_parcial_no_bloquea_pero_se_anota(self):
        """Está en el export aunque el conversor no lo use: es trabajo, no un dato que pedir."""
        assert not Entrada('x', PARCIAL, 'el export', 'se pierde').bloquea


class TestCatalogoDeEstudios:
    def test_cada_estudio_dice_que_aporta_al_pide(self):
        for e in ESTUDIOS:
            assert e.aporta_al_pide.strip(), e.clave

    def test_cada_estudio_apunta_a_una_clase_de_powerfactory(self):
        for e in ESTUDIOS:
            assert e.clase_pf.startswith('Com'), e.clave
            assert 24 <= e.capitulo <= 46, e.clave

    def test_cada_entrada_dice_de_donde_sale_y_que_pasa_sin_ella(self):
        """Un requisito sin «de dónde sale» no se puede accionar."""
        for e in ESTUDIOS:
            for entrada in e.entradas:
                assert entrada.donde.strip(), f'{e.clave}/{entrada.nombre}'
                assert entrada.sin_esto.strip(), f'{e.clave}/{entrada.nombre}'
                assert entrada.estado in (DISPONIBLE, PARCIAL, POR_DEFECTO, AUSENTE)

    def test_las_claves_no_se_repiten(self):
        claves = [e.clave for e in ESTUDIOS]
        assert len(claves) == len(set(claves))

    def test_todos_los_estudios_necesitan_topologia(self):
        """Si alguno no la pide, es que se olvidó de declarar sus entradas."""
        for e in ESTUDIOS:
            assert e.entradas, e.clave

    def test_listos_y_bloqueados_suman_el_total(self):
        assert len(estudios_ejecutables()) + len(estudios_bloqueados()) == len(ESTUDIOS)

    def test_ninguno_esta_en_las_dos_listas(self):
        listos = {e.clave for e in estudios_ejecutables()}
        bloq = {e.clave for e in estudios_bloqueados()}
        assert not (listos & bloq)


class TestQueEstaListoYQueNo:
    """Estas fijan el estado real de HOY con el export de Electro Dunas."""

    def _por_clave(self, clave: str) -> Estudio:
        return next(e for e in ESTUDIOS if e.clave == clave)

    def test_el_flujo_de_potencia_esta_listo(self):
        assert self._por_clave('flujo').defendible

    def test_las_contingencias_estan_listas(self):
        """Solo tienen sentido en la red unida, y ya la hay."""
        assert self._por_clave('contingencias').defendible

    def test_el_punto_de_apertura_esta_listo(self):
        """Necesita enlaces declarados, que es lo que dan los interruptores abiertos."""
        assert self._por_clave('punto_apertura').defendible

    def test_la_fiabilidad_NO_es_defendible_sin_tasas_de_falla(self):
        estudio = self._por_clave('fiabilidad')
        assert not estudio.defendible
        assert any('falla' in x.nombre.lower() for x in estudio.bloqueantes)

    def test_el_cortocircuito_NO_es_defendible_con_la_impedancia_por_defecto(self):
        estudio = self._por_clave('cortocircuito')
        assert not estudio.defendible
        falta = estudio.bloqueantes[0]
        assert falta.estado == POR_DEFECTO
        assert '200 MVA' in falta.donde, 'debe citar el valor que se repite'

    def test_lo_economico_NO_es_defendible_sin_precios(self):
        for clave in ('economico', 'comparacion'):
            estudio = self._por_clave(clave)
            assert not estudio.defendible
            assert any('recio' in x.nombre for x in estudio.bloqueantes), clave


class TestListaDeLaCompra:
    def test_se_ordena_por_cuantos_estudios_desbloquea(self):
        faltan = list(datos_que_faltan().values())
        assert faltan == sorted(faltan, key=len, reverse=True), (
            'pedir primero el dato que desbloquea más rinde más'
        )

    def test_los_precios_encabezan_la_lista(self):
        """Es lo que más estudios desbloquea, y es un dato que la empresa ya tiene."""
        primero = next(iter(datos_que_faltan()))
        assert 'recios' in primero

    def test_solo_aparecen_datos_que_de_verdad_bloquean(self):
        entradas = entradas_por_nombre()
        for dato in datos_que_faltan():
            assert entradas[dato].bloquea, dato

    def test_cada_dato_lista_los_estudios_que_lo_esperan(self):
        nombres = {e.nombre for e in ESTUDIOS}
        for dato, estudios in datos_que_faltan().items():
            assert estudios, dato
            assert set(estudios) <= nombres, dato


class TestAuditoriaContraElExportReal:
    """La tabla dice qué debería haber; esto mira qué hay."""

    def test_encuentra_la_energia_que_el_conversor_no_escribe(self, ds):
        aud = auditar_datos(ds)
        if not aud.cargas_totales:
            pytest.skip('el export cargado no trae cargas')
        assert aud.cargas_con_energia > 0, (
            'el campo KWH de [CUSTOMER LOADS] debe detectarse'
        )
        assert aud.energia_kwh > 0
        assert any('KWH' in h for h in aud.hallazgos)

    def test_detecta_que_las_tasas_de_falla_estan_a_cero(self, ds):
        aud = auditar_datos(ds)
        assert aud.tasas_falla_no_cero == 0, (
            'si esto deja de ser cero, la empresa ya cargó el histórico y el estudio '
            'de fiabilidad deja de estar bloqueado'
        )
        assert any('SAIDI' in h for h in aud.hallazgos)

    def test_detecta_la_impedancia_de_fuente_repetida(self, ds):
        aud = auditar_datos(ds)
        if not aud.subestaciones:
            pytest.skip('el export cargado no trae [SUBSTATION]')
        assert aud.subestaciones_distintas <= 1, (
            'si aparecen impedancias diferenciadas, el cortocircuito pasa a ser usable'
        )

    def test_la_auditoria_no_revienta_con_un_dataset_vacio(self):
        class Vacio:
            customer_loads = {}
            equipment_tables = {}

        aud = auditar_datos(Vacio())
        assert aud.cargas_totales == 0
        assert isinstance(aud.texto(), str)
