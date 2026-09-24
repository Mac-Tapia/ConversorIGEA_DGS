"""Datos del TXT que se perdían por el camino y ahora llegan a DigSILENT.

El export de la empresa trae tres cosas que el conversor dejaba caer:

* **Número de clientes** por suministro. Es el denominador de SAIFI y SAIDI: los
  índices de la NTCSE se ponderan por cliente, no por carga. Sin él, el análisis de
  fiabilidad de PowerFactory calcula otra cosa con el mismo nombre.
* **Fase real** de cada carga. Escribir una monofásica como trifásica equilibrada
  reparte su corriente entre tres conductores en lugar de uno: subestima la caída de
  tensión del ramal y borra el desequilibrio, que el TdR del VAD manda evaluar.
* **Tipo de cliente y año de alta**, que sirven para agrupar resultados y para apoyar
  la proyección de demanda.

La energía (KWH) también se lee, pero ``ElmLod`` de PowerFactory no tiene ningún
atributo de energía anual —comprobado en ``datascheme.db``, sus 105 atributos—, así que
no se inventa un sitio donde meterla: se usa para el factor de carga, que es para lo
que hace falta en el PIDE.
"""

from __future__ import annotations

import math

import pytest

from igea_dgs.model import (
    FASES_PF,
    PHASE_CODES,
    decode_phase,
    split_by_phase,
)


class TestDecodificacionDeFase:
    """El código de CYMDIST es una enumeración, NO una máscara de bits."""

    @pytest.mark.parametrize('codigo,letras', sorted(PHASE_CODES.items()))
    def test_la_tabla_completa(self, codigo, letras):
        assert decode_phase(str(codigo)) == letras
        assert decode_phase(codigo) == letras

    def test_el_4_es_AB_y_no_una_mascara(self):
        """Como máscara, 4 sería solo la tercera fase. Es AB."""
        assert decode_phase(4) == 'AB'

    def test_el_7_es_ABC(self):
        assert decode_phase(7) == 'ABC'

    def test_acepta_lo_ya_decodificado(self):
        """Da igual si el dato viene del TXT en crudo o de una capa que ya lo tradujo."""
        assert decode_phase('ABC') == 'ABC'
        assert decode_phase('ab') == 'AB'

    def test_lo_que_no_reconoce_queda_vacio(self):
        for basura in ('', 'X', None, '99', 0):
            assert decode_phase(basura) == ''


class TestRepartoPorFase:
    def test_una_monofasica_carga_una_sola_fase(self):
        assert split_by_phase(90.0, '1') == (90.0, 0.0, 0.0)
        assert split_by_phase(90.0, '2') == (0.0, 90.0, 0.0)
        assert split_by_phase(90.0, '3') == (0.0, 0.0, 90.0)

    def test_una_bifasica_reparte_entre_dos(self):
        assert split_by_phase(90.0, '4') == (45.0, 45.0, 0.0)   # AB
        assert split_by_phase(90.0, '5') == (45.0, 0.0, 45.0)   # AC
        assert split_by_phase(90.0, '6') == (0.0, 45.0, 45.0)   # BC

    def test_una_trifasica_reparte_entre_tres(self):
        assert split_by_phase(90.0, '7') == (30.0, 30.0, 30.0)

    def test_la_suma_SIEMPRE_es_el_total(self):
        """Invariante: repartir no puede crear ni destruir potencia."""
        for codigo in list(PHASE_CODES) + ['', 'X']:
            total = sum(split_by_phase(123.456, str(codigo)))
            assert math.isclose(total, 123.456, rel_tol=1e-12)

    def test_sin_fase_conocida_se_reparte_entre_las_tres(self):
        """Es lo que se hacía para TODAS las cargas antes de este cambio."""
        assert split_by_phase(90.0, '') == (30.0, 30.0, 30.0)

    def test_el_orden_de_fases_es_el_de_powerfactory(self):
        assert FASES_PF == ('A', 'B', 'C')


class TestLoQueSeEscribeAlDgs:
    def _dgs(self, tmp_path, cargas):
        from igea_dgs.dgs import write_dgs
        from igea_dgs.model import FeederModel, Line, LineType, Node

        tipo = LineType('LINE:AA', 'AA12003D', 'LINE', 0.28, 0.7, 0.43, 1.3, 3.7, 3.7, 340.0)
        nodes = {'N1': Node('N1', 0.0, 0.0), 'N2': Node('N2', 100.0, 0.0)}
        modelo = FeederModel(
            name='AL', network_id='NET', nominal_kv=22.9, source_node='N1',
            nodes=nodes,
            lines=[Line('S1', 'N1', 'N2', 'ABC', tipo.key, tipo.code, 100.0, True)],
            loads=list(cargas), devices=[], line_types={tipo.key: tipo}, seds=[],
        )
        destino = tmp_path / 'x.dgs'
        write_dgs(modelo, destino)
        cab, filas, tabla = [], [], None
        for ln in destino.read_text(encoding='latin-1').splitlines():
            if ln.startswith('$$'):
                tabla = ln[2:].split(';')[0]
                if tabla == 'ElmLod':
                    cab = [c.strip().split('(')[0] for c in ln.split(';')][1:]
            elif tabla == 'ElmLod' and ln.strip():
                filas.append(dict(zip(cab, [c.strip() for c in ln.split(';')])))
        return filas

    def _carga(self, **kw):
        from igea_dgs.model import Load

        base = dict(section_id='S1', device_number='D1', customer_number='C1',
                    location='1', node_id='N2', p_mw=0.09, q_mvar=0.03, pf=0.95,
                    connected_kva=100.0, kwh=1000.0, phase='7')
        base.update(kw)
        return Load(**base)

    def test_el_numero_de_clientes_llega(self, tmp_path):
        filas = self._dgs(tmp_path, [self._carga(customers=18)])
        assert filas[0]['NrCust'] == '18'

    def test_sin_dato_de_clientes_NO_se_escribe_cero(self, tmp_path):
        """PowerFactory exige NrCust > 0 y rechaza el cero con un error por carga."""
        filas = self._dgs(tmp_path, [self._carga(customers=0)])
        assert filas[0]['NrCust'] == '', (
            'mandar 0 produce «Condition for Variable NrCust violated» y PowerFactory '
            'se queda con su valor por defecto sin decirlo'
        )

    def test_el_tipo_de_cliente_llega_a_classif(self, tmp_path):
        filas = self._dgs(tmp_path, [self._carga(customer_type='Residencial')])
        assert filas[0]['classif'] == 'Residencial'

    def test_la_potencia_por_fase_de_una_monofasica(self, tmp_path):
        filas = self._dgs(tmp_path, [self._carga(phase='3', p_mw=0.09)])
        f = filas[0]
        assert f['i_sym'] == '0', 'una monofásica no es simétrica'
        assert float(f['plinir']) == 0.0
        assert float(f['plinis']) == 0.0
        assert float(f['plinit']) == pytest.approx(0.09)

    def test_una_trifasica_se_marca_simetrica(self, tmp_path):
        filas = self._dgs(tmp_path, [self._carga(phase='7')])
        assert filas[0]['i_sym'] == '1'

    def test_la_suma_por_fase_es_la_potencia_total(self, tmp_path):
        for fase in ('1', '4', '7'):
            filas = self._dgs(tmp_path, [self._carga(phase=fase, p_mw=0.09, q_mvar=0.03)])
            f = filas[0]
            p = sum(float(f[k]) for k in ('plinir', 'plinis', 'plinit'))
            q = sum(float(f[k]) for k in ('qlinir', 'qlinis', 'qlinit'))
            assert p == pytest.approx(float(f['plini'])), fase
            assert q == pytest.approx(float(f['qlini'])), fase

    def test_el_esquema_declara_los_atributos_nuevos(self):
        """Los nombres están comprobados en datascheme.db de PowerFactory 2024."""
        from igea_dgs.schema import load_schema

        campos = load_schema('pf21_dgs_1_8_4').fields('ElmLod')
        for esperado in ('NrCust', 'i_sym', 'plinir', 'plinis', 'plinit',
                         'qlinir', 'qlinis', 'qlinit'):
            assert esperado in campos, esperado


class TestExportReal:
    def test_el_export_trae_clientes_y_energia(self, ds):
        from igea_dgs.model import build_feeder_model

        total_cli = total_kwh = 0
        con_fase = sin_fase = 0
        for net in ds.feeder_ids()[:20]:
            try:
                m = build_feeder_model(ds, net, strict=False, include_geography=False)
            except Exception:
                continue
            for c in m.loads:
                total_cli += c.customers
                total_kwh += c.kwh
                if decode_phase(c.phase):
                    con_fase += 1
                else:
                    sin_fase += 1
        assert total_cli > 0, 'NumberOfCustomer debe llegar al modelo'
        assert total_kwh > 0, 'KWH debe llegar al modelo'
        assert con_fase > 0, 'la fase debe decodificarse'

    def test_todas_las_fases_del_export_son_reconocibles(self, ds):
        """Un código que no se decodifica se reparte entre tres fases sin avisar."""
        from igea_dgs.model import build_feeder_model

        desconocidas = set()
        for net in ds.feeder_ids()[:20]:
            try:
                m = build_feeder_model(ds, net, strict=False, include_geography=False)
            except Exception:
                continue
            for c in m.loads:
                if c.phase and not decode_phase(c.phase):
                    desconocidas.add(c.phase)
        assert not desconocidas, f'códigos de fase sin traducir: {sorted(desconocidas)}'
