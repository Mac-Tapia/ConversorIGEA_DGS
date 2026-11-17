"""108 T28 (108:RF-21 a RF-23): el estudio VNR completo desde el inventario VNR-GIS (modelo canónico del módulo ``vnr``)
con la Guía del VNR (RCD 232-2017-OS/CD). Inventarios sintéticos de dos concesiones; tabla de costos sintética."""
from dataclasses import dataclass
from pathlib import Path

import pytest

from convertersmartgrid.adaptadores.entrada.vnr.models.canonical import (CanonicalModel, Load, Node, Section,
                                                                         Transformer)
from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad.vnr_estudio import estudio_vnr, instalacion_de_codigo, letra_de_tension
from convertersmartgrid.vad.vnr_guia import VnrGuiaError, cargar_anexo2, cargar_anexo6

RAIZ = Path(__file__).resolve().parents[1]
REG = cargar_registro(RAIZ / 'config' / 'normativa' / 'rcd_232_2017.json')
A2 = cargar_anexo2(RAIZ / 'config' / 'vnr' / 'anexo2_codigos.json')
A6 = cargar_anexo6(RAIZ / 'config' / 'vnr' / 'anexo6_equivalencias.json')


@dataclass(frozen=True)
class _Costo:
    componentes: dict


class _Tabla:
    def __init__(self, costo=1000.0):
        self.filas = {('XX', 'D', 'C', 'ST2'): _Costo({'total': costo})}
        self.costo = costo
        self.pedidos = []

    def resolver(self, codigo, tension, estructura, sector, subfamilia='', tipo=''):
        self.pedidos.append((codigo, tension, estructura, sector, subfamilia))
        return _Costo({'total': self.costo}), ''


def _modelo(x0=300_000.0, y0=8_600_000.0, md=200.0, con_carga=True):
    m = CanonicalModel()
    m.nodes += [Node('N1', x0 + 100, y0 + 100, 10.0), Node('N2', x0 + 600, y0 + 100, 10.0),
                Node('S1', x0 + 600, y0 + 100, 0.22)]
    m.transformers.append(Transformer('SED1', 'S1', hv_kv=10.0, lv_kv=0.22, sn_kva=250.0))
    if con_carga:
        m.loads.append(Load('C1', 'S1', kw=md))
    m.sections += [
        Section('MT1', 'N1', 'N2', conductor_code='CP05003D', nominal_kv=10.0, length_m=500.0,
                geometry=[[x0 + 100, y0 + 100], [x0 + 600, y0 + 100]]),
        Section('BT1', 'S1', 'S1', conductor_code='CU03513X', nominal_kv=0.22, length_m=200.0,
                geometry=[[x0 + 600, y0 + 100], [x0 + 600, y0 + 300]], feeder_id='SED1')]
    return m


def test_108_t28_codigo_vnr_del_inventario_se_lee_al_reves_por_el_anexo_2():
    i = instalacion_de_codigo(A2, 'CP05003')
    assert (i.nivel, i.subterranea, i.material, i.seccion_mm2, i.conductores) == ('MT', False, 'cu protegido', 50, 3)
    assert instalacion_de_codigo(A2, 'NY07013').subterranea
    with pytest.raises(VnrGuiaError):
        instalacion_de_codigo(A2, 'SM03004')  # una SED no es un código de red


def test_108_t28_letras_de_la_tabla_9_del_anexo_3():
    assert (letra_de_tension(A2, 10.0), letra_de_tension(A2, 22.9)) == ('D', 'G')
    assert (letra_de_tension(A2, 0.22, baja=True), letra_de_tension(A2, 0.38, baja=True)) == ('X', 'Y')
    assert letra_de_tension(A2, 33.3) is None


@pytest.mark.parametrize('x0, y0', [(300_000.0, 8_600_000.0), (700_000.0, 9_400_000.0)])  # dos concesiones
def test_108_t28_estudio_completo_zonifica_adapta_codifica_y_valoriza(x0, y0):
    tabla = _Tabla(1000.0)
    e = estudio_vnr(_modelo(x0, y0), sector='urbano_alta', sector_sicodi='ST2', tabla_costos=tabla, registro=REG,
                    anexo2=A2, anexo6=A6)
    assert e.zonas_mt == {'Alta 1': 1}  # 200 kW en 0,0625 km²: 3,2 MW/km²
    assert {a.material for a in e.adaptados_mt} == {'AA Desnudo'}  # CU protegido → AA desnudo (no corrosivo)
    (sed,) = e.seds
    assert sed['kva_adaptado'] == pytest.approx(200 / 0.675) and sed['tipo'] == 'Compacta Pedestal 3ø'
    assert e.resultado.completo and e.resultado.total > 0
    assert any(p[0] == sed['codigo'] and p[1] == 'D' and p[2] == 'X' for p in tabla.pedidos)
    assert any('ambiente corrosivo' in h for h in e.huecos)  # sin franja costera se dice


def test_108_t28_sed_sin_demanda_es_hueco_y_el_tramo_con_codigo_desconocido_tambien():
    m = _modelo(con_carga=False)
    m.sections.append(Section('MT9', 'N1', 'N2', conductor_code='ZZ99999D', length_m=10.0,
                              geometry=[[300_100, 8_600_100], [300_110, 8_600_100]]))
    e = estudio_vnr(m, sector='urbano_media_baja', sector_sicodi='ST2', tabla_costos=_Tabla(), registro=REG,
                    anexo2=A2, anexo6=A6, corrosivo=lambda x, y: True)
    assert not e.seds and any('SED SED1: sin máxima demanda' in h for h in e.huecos)
    assert any(h.startswith('tramo MT9') for h in e.huecos)
    assert {a.material for a in e.adaptados_mt} == {'CU Desnudo'}  # corrosivo → cobre desnudo
    assert not any('ambiente corrosivo' in h for h in e.huecos)
