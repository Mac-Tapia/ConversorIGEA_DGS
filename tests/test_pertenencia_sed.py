"""Spec 038: la pertenencia de la fuente precede al filtro comercial."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from igea_dgs import demanda_medida as dm
from igea_dgs.web import services
from igea_dgs.web.workspace import Workspace


def test_un_propietario_corrige_sin_agrupar_sufijos():
    """038:RF-1, 038:RF-2 — la SED exacta usa la red y conserva el radial comercial."""
    cliente = dm.ClienteImportante('123', 2, sed='SE10', radial='A1')
    buenos, ambiguos = dm.reconciliar_radiales([cliente], {'SE10': {'B2'}, 'SE10-2': {'C3'}})
    assert not ambiguos
    assert buenos[0].radial == buenos[0].radial_fuente == 'B2'
    assert buenos[0].radial_libro == 'A1'
    assert 'A1' in buenos[0].nota_asignacion and 'B2' in buenos[0].nota_asignacion


def test_ambigua_no_elige_el_primero():
    """038:RF-3 — una SED repetida entre redes se separa sin elegir por orden."""
    cliente = dm.ClienteImportante('123', 2, sed='SE10', radial='A1')
    buenos, ambiguos = dm.reconciliar_radiales([cliente], {'SE10': {'A1', 'B2'}})
    assert not buenos and len(ambiguos) == 1
    assert 'A1' in ambiguos[0].motivo and 'B2' in ambiguos[0].motivo
    assert not ambiguos[0].radial_fuente


def test_ambiguedad_no_se_oculta_por_mayusculas_ni_por_radial_anterior():
    """038:RF-3 — las dos pertenencias siguen visibles al filtrar por la red de destino."""
    cliente = dm.ClienteImportante('123', 2, sed='SE10', radial='ANTERIOR')
    buenos, ambiguos = dm.reconciliar_radiales([cliente], {'SE10': {'A1'}, 'se10': {'B2'}})
    assert not buenos and len(ambiguos) == 1
    _, aparte, _ = dm.del_alimentador(buenos, ambiguos, ['B2'])
    assert len(aparte) == 1


@pytest.mark.parametrize('indice', [None, {}, {'SE10-2': {'B2'}}])
def test_sin_sed_exacta_no_inventa_propietario(indice):
    """038:RF-4 — sin fuente o sin coincidencia exacta conserva el libro."""
    buenos, ambiguos = dm.reconciliar_radiales(
        [dm.ClienteImportante('123', 2, sed='SE10', radial='A1')], indice)
    assert not ambiguos and buenos[0].radial == 'A1'
    assert buenos[0].radial_fuente == ''


def test_indice_de_red_se_reutiliza_y_cambia_con_el_dataset(tmp_path):
    """038:RF-1 — el plan no recorre todas las cargas por cada alimentador; fuente nueva invalida."""
    class Filas(dict):
        lecturas = 0

        def items(self):
            self.lecturas += 1
            return super().items()

    rows = Filas({('SEC_2010_1_SE10', 'DEV_2010_1_SE10'): {'CustomerNumber': 'CUST_2010_1_SE10'}})
    ws = Workspace(id='w', root=tmp_path / 'ws')
    ws.dataset = SimpleNamespace(customer_loads=rows, section_owner={'SEC_2010_1_SE10': 'A1'})
    suministros = [dm.Suministro('123', '', 'SE10', 'ANTERIOR', 2)]
    for _ in range(2):
        buenos, _ = services._cruzar_clientes_en_red(ws, [dm.ClienteImportante('123', 2)], suministros)
        assert buenos[0].radial == 'A1'
    assert rows.lecturas == 1
    ws.dataset = SimpleNamespace(customer_loads=rows, section_owner={'SEC_2010_1_SE10': 'B2'})
    buenos, _ = services._cruzar_clientes_en_red(ws, [dm.ClienteImportante('123', 2)], suministros)
    assert buenos[0].radial == 'B2' and rows.lecturas == 2


def _libro(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'resumen'
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


@pytest.mark.parametrize('con_maximas', [False, True])
def test_filtra_despues_de_reconciliar_y_usa_instante_correcto(tmp_path, monkeypatch, con_maximas):
    """038:RF-1, 038:RF-5 — tabla y planes que la consumen usan la red antes del filtro."""
    suministros = _libro(tmp_path / 's.xlsx', [
        ['Suministro Act', 'SED', 'Radial'], ['123', 'SE10', 'A1'],
    ])
    clientes = _libro(tmp_path / 'c.xlsx', [
        ['Nis', 'Pot', 'EA', 'ERI'], ['123', 10, 100, 20],
    ])
    ws = Workspace(id='w', root=tmp_path / 'ws')
    ws.dataset = SimpleNamespace(
        customer_loads={('SEC_2010_1_SE10', 'DEV_2010_1_SE10'): {'CustomerNumber': 'CUST_2010_1_SE10'}},
        section_owner={'SEC_2010_1_SE10': 'NET_2030_1_B2'},
    )
    monkeypatch.setattr(services, '_demanda_ruta',
                        lambda _ws, tipo, **kw: suministros if tipo == 'suministros' else clientes)
    monkeypatch.setattr(services, 'periodo_clientes_activo', lambda *args:
                        SimpleNamespace(status='CLIENT_PERIOD_MATCH', period='2026-10'))
    registros = []
    def registro(_libro, codigos, instante=None, **_kw):
        registros.append((set(codigos), instante))
        return {}, []
    monkeypatch.setattr(dm, 'registros_de_maxima', registro)
    maxima = {'B2': {'fecha': '2026-10-23 09:00:00', 'kw': 100, 'kvar': 20, 'medidor': 'M'}}
    r = services.demanda_clientes(ws, ['B2'], maximas=maxima if con_maximas else None)
    assert len(r['cruzados']) == 1 and not r['no_cruzados']
    assert r['cruzados'][0]['radial'] == 'B2'
    assert r['cruzados'][0]['radial_libro'] == 'A1'
    assert registros[0][0] == {'123'}
    if con_maximas:
        assert registros[0][1] == datetime.fromisoformat('2026-10-23T09:00:00')
        assert r['cruzados'][0]['alimentador_maxima'] == 'B2'


def test_notas_del_libro_se_leen_y_exportan(tmp_path):
    """038:RF-6 — una corrección documentada sigue visible aunque el libro ya esté corregido."""
    path = _libro(tmp_path / 's.xlsx', [
        ['Suministro Act', 'SED', 'Radial', 'Observacion'],
        ['123', 'SE10', 'B2', 'Corregido A1 a B2 según TXT'],
    ])
    suministros, _ = dm.leer_suministros(path)
    cruzados, _ = dm.cruzar([dm.ClienteImportante('123', 2)], suministros)
    assert cruzados[0].nota_asignacion == 'Corregido A1 a B2 según TXT'
    out = dm.escribir_excel(tmp_path / 'out.xlsx', clientes=[cruzados[0].to_dict()])
    wb = openpyxl.load_workbook(out, data_only=True)
    assert any('Corregido A1 a B2' in str(v) for s in wb for row in s.values for v in row)


def test_web_muestra_notas_y_aclara_alcance_igea():
    """038:RF-2, 038:RF-6, 038:RF-7 — nota visible; planos previos de IGEA fuera del alcance."""
    root = Path(__file__).resolve().parents[1] / 'frontend/src/components'
    demanda = (root / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    assert 'nota_asignacion' in demanda and 'radial_libro' in demanda
    assert 'planos de IGEA previos a la exportación quedan fuera del alcance' in demanda
    assert 'TXT, MDB o VNR-GIS' in demanda
