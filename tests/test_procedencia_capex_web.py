"""072:RF-28: recibo CAPEX en consumidores económicos, sin motor nativo."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from types import SimpleNamespace

from convertersmartgrid.web import services
from test_pide_economia import CONFIG, _capex


def perfil():
    return {'planificacion': {'capex': CONFIG, 'crecimiento_demanda_anual': .04,
                             'vida_util_anios': 30, 'horizonte_anios': 20, 'tasa_regulada': .12},
            'escalera': {'moneda': 'USD', 'escala_capex': 1000}}


def test_expresso_preserva_costo_y_enlaza_recibo_real(tmp_path):
    """087:RF-36; 072:RF-28: el resumen de costo conserva fuente, sin crear obras."""
    ruta = _capex(tmp_path)
    avisos = []
    r = services._expreso_costo_y_area(perfil(), str(ruta), [], {}, [], [], 'Prueba propia', avisos)
    assert r['procedencia_capex']['fuente']['sha256'] == hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert r['procedencia_capex']['contexto_unidades']['escala_aplicada'] == 1000
    assert r['procedencia_capex']['contexto_unidades']['moneda'] == 'USD'
    assert r['costo']['celdas'] == 1 and r['costo']['km'] == 0


def test_memo_no_mezcla_rutas_y_conserva_costos_con_su_primera_lectura(tmp_path, monkeypatch):
    """072:RF-17/28: memo costos/recibo emparejado, no sello de otra lectura actual."""
    from convertersmartgrid import perfil_empresa as pe
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir(); b.mkdir()
    ra, rb = _capex(a), _capex(b)
    p = perfil()
    monkeypatch.setattr(pe, 'datos_perfil', lambda: p)
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *a: {'informes': [
        {'feeder': 'F1', 'objetivo': {'kw': 100, 'medidor': 'M1'}}]})
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda *a: [{'alimentador': 'F1'}])
    monkeypatch.setattr(services, '_curva_del_anio', lambda *a: {'F1': [(datetime(2026, 1, 1), 100)]})
    monkeypatch.setattr(services, 'obras_bibliotecas', lambda *a, **k: {'informe': {}})
    monkeypatch.setattr(services, '_valle_del_proyecto', lambda *a, **k: {'avisos': []})
    memo = {}
    ctx = SimpleNamespace(log=lambda *a: None)
    def leer(ruta):
        return services.obras_escalera(SimpleNamespace(), ctx, 'Propio', ['F1'],
                                       capex=str(ruta), anio_casos=2026, solo_comun=True, memo=memo)
    uno = leer(ra)
    dos = leer(rb)
    assert uno['procedencia_capex']['fuente']['ruta'] == str(ra.resolve())
    assert dos['procedencia_capex']['fuente']['ruta'] == str(rb.resolve())
    assert len(memo) == 2
    # Cambiar el archivo propio después no vuelve a sellar costos ya memoizados.
    from openpyxl import load_workbook
    libro = load_workbook(ra)
    libro[CONFIG['hoja']]['I3'] = 1
    libro.save(ra); libro.close()
    tres = leer(ra)
    assert tres['costos'] == uno['costos']
    assert tres['procedencia_capex'] == uno['procedencia_capex']
    assert tres['procedencia_capex']['fuente']['sha256'] != hashlib.sha256(ra.read_bytes()).hexdigest()
