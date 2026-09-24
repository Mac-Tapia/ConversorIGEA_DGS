"""Catálogo de parámetros: referencia de ficha, auditoría y corrección del modelo.

Lo que estas pruebas fijan, por orden de importancia:

1. **La referencia reproduce la ficha.** El método que deriva la resistencia de un
   AAAC se comprueba contra las cuatro secciones que la ficha publica. Si esa fórmula
   se desvía, todo lo que la herramienta señale después es ruido.
2. **La auditoría no acusa a lo que está bien.** Un catálogo correcto no debe producir
   hallazgos: una herramienta que marca todo no se usa dos veces.
3. **Nada entra en el modelo por accidente.** Una fila «por_confirmar» no corrige,
   aunque tenga un número escrito.
"""

from __future__ import annotations

import math

import pytest

from igea_dgs.catalog import (
    B_AEREO_MAX,
    B_AEREO_MIN,
    CorreccionConductor,
    GRAVE_PCT,
    aplicar_correcciones,
    auditar,
    construir_hojas,
    escribir_catalogo,
    input_dir,
    leer_catalogo,
    material_de_codigo,
    seccion_de_codigo,
)
from igea_dgs.catalog_data import (
    AAAC_FICHA,
    AAAC_K_7_HILOS,
    AAAC_RHO20_OHM_MM2_KM,
    PARAMETROS,
    TRAFO_PERDIDAS_UE,
    aaac_r20_ohm_km,
    trafo_interpola,
)
from igea_dgs.model import FeederModel, LineType, Line, Load, Node, Sed


def _tipo(code: str, r1: float, *, x1: float = 0.45, r0: float | None = None,
          x0: float | None = None, b1: float = 3.7, amps: float = 150.0,
          tabla: str = 'LINE') -> LineType:
    return LineType(f'{tabla}:{code}', code, tabla, r1, r0 if r0 is not None else r1 * 2.5,
                    x1, x0 if x0 is not None else x1 * 3.0, b1, b1, amps)


def _modelo(tipos: dict[str, LineType], *, km: float = 1.0, kva: float = 160.0) -> FeederModel:
    nodes = {'N1': Node('N1', 0.0, 0.0), 'N2': Node('N2', 100.0, 0.0)}
    lines = [
        Line(f'SEC_{i}', 'N1', 'N2', 'ABC', clave, tipos[clave].code,
             km * 1000.0, tipos[clave].source_table == 'LINE')
        for i, clave in enumerate(tipos)
    ]
    sed = Sed('SE1', 'SE1', 'N2', kva, 'SEC_0', 'D1', ('SEC_0', 'D1'))
    load = Load('SEC_0', 'D1', 'C', '1', 'N2', 0.01, 0.003, 0.95, kva, 0.0, 'ABC',
                sed_code='SE1', display_name='SE1')
    return FeederModel(
        name='AL01', network_id='NET', nominal_kv=22.9, source_node='N1',
        nodes=nodes, lines=lines, loads=[load], devices=[], line_types=dict(tipos),
        seds=[sed],
    )


class TestReferenciaDeFicha:
    """La fórmula debe reproducir la ficha, no aproximarla."""

    @pytest.mark.parametrize('seccion', sorted(AAAC_FICHA))
    def test_reproduce_las_secciones_publicadas(self, seccion):
        assert aaac_r20_ohm_km(seccion) == pytest.approx(AAAC_FICHA[seccion]['r20'])

    def test_la_formula_derivada_concuerda_con_la_ficha(self):
        """ρ20/S · k debe dar lo que publica la ficha en las de 7 hilos."""
        for seccion in (35.0, 50.0, 70.0):
            derivado = AAAC_RHO20_OHM_MM2_KM / seccion * AAAC_K_7_HILOS
            assert derivado == pytest.approx(AAAC_FICHA[seccion]['r20'], rel=1e-3)

    def test_la_resistencia_decrece_al_crecer_la_seccion(self):
        secciones = [10.0, 16.0, 25.0, 35.0, 50.0, 70.0, 95.0, 120.0, 150.0, 185.0]
        valores = [aaac_r20_ohm_km(s) for s in secciones]
        assert valores == sorted(valores, reverse=True)

    def test_seccion_a_partir_del_codigo(self):
        assert seccion_de_codigo('AA12003D') == pytest.approx(120.0)
        assert seccion_de_codigo('AA03503D') == pytest.approx(35.0)
        assert seccion_de_codigo('N205003D') == pytest.approx(50.0)
        assert seccion_de_codigo('DEFAULT') is None
        assert seccion_de_codigo('AAXX03D') is None
        assert seccion_de_codigo('AA') is None

    def test_material_a_partir_del_codigo(self):
        assert material_de_codigo('AA12003D') == 'AAAC'
        assert material_de_codigo('CU01603D') == 'Cobre'
        assert material_de_codigo('N212003D') == 'Cable XLPE'
        assert material_de_codigo('ZZ99999') == ''


class TestInterpolacionTransformadores:
    def test_devuelve_el_valor_tabulado(self):
        assert trafo_interpola(630.0, TRAFO_PERDIDAS_UE, 0) == pytest.approx(6500.0)

    def test_interpola_entre_dos_potencias(self):
        """El propio Reglamento manda interpolar linealmente."""
        medio = trafo_interpola(325.0, TRAFO_PERDIDAS_UE, 0)
        assert 3250.0 < medio < 4600.0
        esperado = 3250.0 + (325.0 - 250.0) / (400.0 - 250.0) * (4600.0 - 3250.0)
        assert medio == pytest.approx(esperado)

    def test_no_extrapola_fuera_del_rango(self):
        """Una SED de 5 kVA o de 3 MVA no se parece a nada de la tabla."""
        assert trafo_interpola(5.0, TRAFO_PERDIDAS_UE, 0) is None
        assert trafo_interpola(3000.0, TRAFO_PERDIDAS_UE, 0) is None

    def test_el_nivel_2_es_mas_exigente_que_el_nivel_1(self):
        for kva, (pk1, po1, pk2, po2) in TRAFO_PERDIDAS_UE.items():
            assert pk2 < pk1, kva
            assert po2 < po1, kva


class TestAuditoriaNoAcusaLoCorrecto:
    def test_un_catalogo_conforme_a_la_ficha_no_da_hallazgos_de_resistencia(self):
        tipos = {
            f'LINE:AA{int(s * 10):04d}03D': _tipo(f'AA{int(s * 10):04d}03D',
                                                  aaac_r20_ohm_km(s))
            for s in sorted(AAAC_FICHA)
        }
        aud = auditar([_modelo(tipos)])
        assert [h for h in aud.hallazgos if h.atributo == 'rline'] == []

    def test_no_audita_el_tipo_DEFAULT(self):
        """DEFAULT es el comodín del catálogo; no representa ningún conductor."""
        tipos = {'LINE:DEFAULT': _tipo('DEFAULT', 0.122)}
        aud = auditar([_modelo(tipos)])
        assert [h for h in aud.hallazgos if h.elemento != 'Transformador SED'] == []

    def test_una_susceptancia_normal_no_se_señala(self):
        b = (B_AEREO_MIN + B_AEREO_MAX) / 2
        tipos = {'LINE:AA03503D': _tipo('AA03503D', aaac_r20_ohm_km(35.0), b1=b)}
        aud = auditar([_modelo(tipos)])
        assert [h for h in aud.hallazgos if h.atributo == 'bline'] == []


class TestAuditoriaDetecta:
    def test_resistencia_que_no_corresponde_a_la_seccion(self):
        # 1,0891 Ω/km es lo que el catálogo real pone en un AAAC de 10 mm².
        tipos = {'LINE:AA01003D': _tipo('AA01003D', 1.0891)}
        aud = auditar([_modelo(tipos)])
        graves = [h for h in aud.graves if h.atributo == 'rline']
        assert len(graves) == 1
        assert graves[0].desviacion_pct < -GRAVE_PCT
        assert 'no a los 10 mm²' in graves[0].mensaje

    def test_dice_cuando_el_valor_parece_copiado_de_otra_seccion(self):
        """Media investigación hecha: si coincide con otra sección, es copia."""
        tipos = {'LINE:AA18503D': _tipo('AA18503D', aaac_r20_ohm_km(150.0))}
        aud = auditar([_modelo(tipos)])
        grave = next(h for h in aud.graves if h.atributo == 'rline')
        assert 'fila copiada' in grave.mensaje
        assert '150' in grave.mensaje

    def test_susceptancia_con_error_de_unidad(self):
        # CU07003D en el catálogo real trae 0,000394 en lugar de ~3,9.
        tipos = {'LINE:CU07003D': _tipo('CU07003D', 0.3147, b1=0.000394)}
        aud = auditar([_modelo(tipos)])
        grave = next(h for h in aud.graves if h.atributo == 'bline')
        assert 'error de unidad' in grave.mensaje
        assert '10^4' in grave.mensaje

    def test_susceptancia_ausente_es_aviso_no_grave(self):
        tipos = {'LINE:AA03503D': _tipo('AA03503D', aaac_r20_ohm_km(35.0), b1=0.0)}
        aud = auditar([_modelo(tipos)])
        h = next(x for x in aud.hallazgos if x.atributo == 'bline')
        assert h.severidad == 'aviso'

    def test_homopolar_copiada_de_la_directa(self):
        tipos = {'LINE:AA03503D': _tipo('AA03503D', 0.9651, x1=0.48, r0=0.9651, x0=0.48)}
        aud = auditar([_modelo(tipos)])
        h = next(x for x in aud.hallazgos if 'rline0' in x.atributo)
        assert h.severidad == 'aviso'
        assert 'cortocircuito monofásico' in h.mensaje

    def test_el_cable_usa_su_propio_rango_de_susceptancia(self):
        """3,7 µS/km es normal en aéreo y absurdo en un cable."""
        tipos = {'CABLE:N212003D': _tipo('N212003D', 0.196, b1=3.7,
                                         tabla='CONCENTRIC NEUTRAL CABLE')}
        aud = auditar([_modelo(tipos)])
        assert any(h.atributo == 'bline' and h.severidad == 'grave' for h in aud.hallazgos)

    def test_las_perdidas_fabricadas_del_trafo_se_agregan_en_un_hallazgo(self):
        """El defecto es una fórmula, no 84 transformadores distintos."""
        tipos = {'LINE:AA03503D': _tipo('AA03503D', aaac_r20_ohm_km(35.0))}
        modelos = [_modelo(tipos, kva=kva) for kva in (160.0, 250.0, 400.0, 1000.0)]
        aud = auditar(modelos)
        pfe = [h for h in aud.hallazgos if h.atributo == 'pfe']
        assert len(pfe) == 1
        assert pfe[0].unidad_uso == 'transformadores'
        assert 'fracción fija' in pfe[0].mensaje


class TestResumen:
    def test_los_km_afectados_no_se_cuentan_dos_veces(self):
        """Un tipo con dos hallazgos graves aporta sus km una sola vez."""
        tipos = {'LINE:AA01003D': _tipo('AA01003D', 1.0891, b1=0.000394)}
        aud = auditar([_modelo(tipos, km=10.0)])
        lineas = [h for h in aud.graves if h.codigo == 'AA01003D']
        assert len(lineas) >= 2, 'resistencia y susceptancia, el mismo tipo'
        assert aud.km_afectados == pytest.approx(10.0)

    def test_el_resumen_da_el_porcentaje_de_red(self):
        tipos = {'LINE:AA01003D': _tipo('AA01003D', 1.0891)}
        aud = auditar([_modelo(tipos, km=3.0)])
        assert 'km' in aud.resumen() and '%' in aud.resumen()


class TestHojas:
    def test_hay_una_hoja_por_familia_de_equipo(self):
        tipos = {'LINE:AA03503D': _tipo('AA03503D', 0.9651)}
        hojas = construir_hojas(auditar([_modelo(tipos)]))
        for nombre in ('conductores_aereos', 'cables_subterraneos',
                       'transformadores_sed', 'condensadores', 'reguladores',
                       'parametros_por_elemento', 'hallazgos'):
            assert nombre in hojas

    def test_los_aereos_y_los_cables_van_en_hojas_distintas(self):
        tipos = {
            'LINE:AA03503D': _tipo('AA03503D', 0.9651),
            'CABLE:N212003D': _tipo('N212003D', 0.196, b1=95.6,
                                    tabla='CONCENTRIC NEUTRAL CABLE'),
        }
        hojas = construir_hojas(auditar([_modelo(tipos)]))
        aereos = [f[0] for f in hojas['conductores_aereos'][1]]
        cables = [f[0] for f in hojas['cables_subterraneos'][1]]
        assert aereos == ['AA03503D']
        assert cables == ['N212003D']

    def test_la_hoja_de_parametros_cubre_los_equipos_que_pidio_el_usuario(self):
        hojas = construir_hojas(auditar([_modelo({'LINE:A': _tipo('AA03503D', 0.9651)})]))
        elementos = ' '.join(str(f[0]) for f in hojas['parametros_por_elemento'][1])
        for esperado in ('Tramo MT aéreo', 'Cable MT subterráneo', 'Transformador SED',
                         'Condensador shunt', 'Regulador de tensión'):
            assert esperado in elementos

    def test_cada_parametro_dice_que_ficha_hace_falta_y_que_afecta(self):
        for p in PARAMETROS:
            assert p.ficha_necesaria.strip(), p.atributo
            assert p.impacto.strip(), p.atributo
            assert p.origen in ('txt', 'fabricado', 'cero', 'ausente'), p.atributo

    def test_marca_como_ficha_solo_lo_publicado_y_derivado_lo_demas(self):
        tipos = {
            'LINE:AA03503D': _tipo('AA03503D', 0.9651),   # publicada
            'LINE:AA01603D': _tipo('AA01603D', 2.111),    # derivada
        }
        hojas = construir_hojas(auditar([_modelo(tipos)]))
        cols = hojas['conductores_aereos'][0]
        i_cod, i_est = cols.index('codigo'), cols.index('estado')
        estados = {f[i_cod]: f[i_est] for f in hojas['conductores_aereos'][1]}
        assert estados['AA03503D'] == 'ficha'
        assert estados['AA01603D'] == 'derivado'


class TestFicheroDeEntrada:
    def test_se_escribe_en_input(self, tmp_path):
        pytest.importorskip('openpyxl')
        tipos = {'LINE:AA03503D': _tipo('AA03503D', 0.9651)}
        destino = escribir_catalogo(auditar([_modelo(tipos)]), base=tmp_path)
        assert destino.parent == tmp_path / 'input'
        assert destino.exists()

    def test_input_se_crea_si_no_existe(self, tmp_path):
        carpeta = input_dir(tmp_path)
        assert carpeta.is_dir() and carpeta.name == 'input'

    def test_el_libro_lleva_todas_las_hojas(self, tmp_path):
        openpyxl = pytest.importorskip('openpyxl')
        tipos = {'LINE:AA03503D': _tipo('AA03503D', 0.9651)}
        destino = escribir_catalogo(auditar([_modelo(tipos)]), base=tmp_path)
        wb = openpyxl.load_workbook(destino)
        assert 'hallazgos' in wb.sheetnames
        assert 'parametros_por_elemento' in wb.sheetnames
        assert wb['conductores_aereos']['A1'].value == 'codigo'


class TestLecturaYCorreccion:
    def _catalogo(self, tmp_path, estado: str, r1: float = 2.111):
        openpyxl = pytest.importorskip('openpyxl')
        tipos = {'LINE:AA01603D': _tipo('AA01603D', 1.0891)}
        destino = escribir_catalogo(auditar([_modelo(tipos)]), base=tmp_path)
        wb = openpyxl.load_workbook(destino)
        ws = wb['conductores_aereos']
        cab = [c.value for c in ws[1]]
        ws.cell(row=2, column=cab.index('R1_ficha_ohm_km') + 1, value=r1)
        ws.cell(row=2, column=cab.index('estado') + 1, value=estado)
        wb.save(destino)
        return destino

    def test_una_fila_marcada_ficha_corrige(self, tmp_path):
        destino = self._catalogo(tmp_path, 'ficha')
        correcciones = leer_catalogo(destino)
        assert 'AA01603D' in correcciones
        modelo = _modelo({'LINE:AA01603D': _tipo('AA01603D', 1.0891)})
        cambios = aplicar_correcciones(modelo, correcciones)
        assert len(cambios) == 1
        assert modelo.line_types['LINE:AA01603D'].r1_ohm_km == pytest.approx(2.111)

    def test_una_fila_por_confirmar_no_corrige_aunque_tenga_numero(self, tmp_path):
        """La salvaguarda: un valor provisional no entra como si fuera de fabricante."""
        destino = self._catalogo(tmp_path, 'por_confirmar')
        assert leer_catalogo(destino) == {}

    def test_aplicar_no_toca_lo_que_ya_coincide(self, tmp_path):
        destino = self._catalogo(tmp_path, 'ficha', r1=1.0891)
        modelo = _modelo({'LINE:AA01603D': _tipo('AA01603D', 1.0891)})
        assert aplicar_correcciones(modelo, leer_catalogo(destino)) == []

    def test_aplicar_solo_toca_los_codigos_del_catalogo(self):
        modelo = _modelo({
            'LINE:AA01603D': _tipo('AA01603D', 1.0891),
            'LINE:AA03503D': _tipo('AA03503D', 0.9651),
        })
        aplicar_correcciones(modelo, {
            'AA01603D': CorreccionConductor('AA01603D', r1_ohm_km=2.111),
        })
        assert modelo.line_types['LINE:AA03503D'].r1_ohm_km == pytest.approx(0.9651)

    def test_un_catalogo_que_no_existe_lo_dice(self, tmp_path):
        from igea_dgs.catalog import CatalogError

        with pytest.raises(CatalogError, match='No existe'):
            leer_catalogo(tmp_path / 'no_esta.xlsx')

    def test_corregir_borra_el_hallazgo(self, tmp_path):
        """La prueba de que la herramienta cierra el ciclo que abre."""
        modelo = _modelo({'LINE:AA01603D': _tipo('AA01603D', 1.0891)})
        assert [h for h in auditar([modelo]).graves if h.atributo == 'rline']
        aplicar_correcciones(modelo, {
            'AA01603D': CorreccionConductor('AA01603D',
                                            r1_ohm_km=aaac_r20_ohm_km(16.0)),
        })
        assert [h for h in auditar([modelo]).graves if h.atributo == 'rline'] == []


class TestCatalogoReal:
    """Contra el export real, que es donde el método se gana la confianza."""

    def test_las_secciones_dominantes_coinciden_con_la_ficha(self, ds):
        from igea_dgs.model import build_feeder_model

        modelos = []
        for net in ds.feeder_ids()[:25]:
            try:
                modelos.append(build_feeder_model(ds, net, strict=False))
            except Exception:
                continue
        if not modelos:
            pytest.skip('No se pudo construir ningún alimentador del export')
        aud = auditar(modelos)
        # Los tipos «...3D» de 35, 50, 70 y 120 mm² son los que más km llevan y
        # coinciden con la ficha al cuarto decimal: si esto falla, la referencia
        # dejó de reproducir el catálogo real y todo lo demás sobra.
        for codigo in ('AA03503D', 'AA05003D', 'AA07003D', 'AA12003D'):
            uso = aud.usos.get(codigo)
            if uso is None:
                continue
            seccion = seccion_de_codigo(codigo)
            assert uso.tipo.r1_ohm_km == pytest.approx(aaac_r20_ohm_km(seccion), abs=1e-4)
            assert not [h for h in aud.hallazgos
                        if h.codigo == codigo and h.atributo == 'rline']

    def test_el_export_real_produce_hallazgos_con_su_cuenta_hecha(self, ds):
        from igea_dgs.model import build_feeder_model

        modelos = []
        for net in ds.feeder_ids()[:25]:
            try:
                modelos.append(build_feeder_model(ds, net, strict=False))
            except Exception:
                continue
        if not modelos:
            pytest.skip('No se pudo construir ningún alimentador del export')
        aud = auditar(modelos)
        assert aud.km_total > 0
        for h in aud.hallazgos:
            assert h.fuente.strip(), f'{h.codigo}.{h.atributo} sin fuente'
            assert h.mensaje.strip()
            assert h.severidad in ('grave', 'aviso', 'dato')
