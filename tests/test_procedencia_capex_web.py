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


def test_pide_guarda_plan_y_resultado_con_recibo_de_su_lectura(tmp_path, monkeypatch):
    """072:RF-28: fuente efectiva en plan/resultado; diagnóstico doble, sin motor ni ML."""
    from convertersmartgrid import perfil_empresa as pe, pide_economia as ec
    from convertersmartgrid.asistente import ejemplos_pide
    ruta = _capex(tmp_path)
    p = perfil()
    p['estudios'] = {'tension_min_pu': .95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}
    monkeypatch.setattr(pe, 'datos_perfil', lambda: p)
    monkeypatch.setattr(pe, 'estructura_empresa', lambda: None)
    monkeypatch.setattr(ejemplos_pide, 'ultimo_ejemplos', lambda *a: None)
    monkeypatch.setattr(services, 'native_action_context', lambda ws, project, feeders, action: {'feeders': feeders})
    monkeypatch.setattr(services, 'carpeta_de', lambda *a: 'Propia')
    monkeypatch.setattr(services, '_ingreso_de_las_cargas', lambda *a: [])
    monkeypatch.setattr(services, '_pide_optimizar', lambda *a: [])
    monkeypatch.setattr(services, '_formatos_del_pide', lambda *a: {'filas': {}, 'huecos': []})
    informe = {'anios': [{'anio': 0, 'cabeceras_kw': {'F1': 100}, 'vm_min': .90,
                          'problemas': [{'tipo': 'tension', 'elemento': 'B9', 'valor': .90, 'limite': .95,
                                         'causa': 'caida_de_tension', 'kv': 10., 'alimentador': 'F1'}]}], 'avisos': []}
    def guion(ws, ctx, script, plan, **kwargs):
        (tmp_path / 'plan_persistido.json').write_text(json.dumps(plan), encoding='utf-8')
        reporte = tmp_path / 'diagnostico_doble.json'
        reporte.write_text(json.dumps(informe), encoding='utf-8')
        return 0, deepcopy(informe), reporte
    monkeypatch.setattr(services, '_guion_pf', guion)
    ws = SimpleNamespace(out_dir=tmp_path)
    ctx = SimpleNamespace(log=lambda *a: None)
    r = services.pide_ejecutar(ws, ctx, 'Propio', ['F1'], capex=str(ruta), implementar=False)
    recibo = r['procedencia_capex']
    assert recibo['fuente']['sha256'] == hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert recibo['contexto_unidades']['escala_aplicada'] == 1
    assert recibo['contexto_unidades']['moneda'] is None
    plan = json.loads((tmp_path / 'plan_persistido.json').read_text(encoding='utf-8'))
    assert plan['procedencia_capex'] == recibo
    resultado = tmp_path / 'resultado.json'
    resultado.write_text(json.dumps(r), encoding='utf-8')
    assert json.loads(resultado.read_text(encoding='utf-8'))['procedencia_capex'] == recibo
    esperado = ec.propuesta_pide(informe, p['planificacion'],
                                costos=ec.costos_por_alternativa(ec.leer_capex(ruta, CONFIG)[0]),
                                bancos_kvar=None, factor_carga=None, precio_compra_kwh=None, coym_pct_anual=None)
    assert r['obras']
    assert [{k: v for k, v in obra.items() if k != 'procedencia_capex'} for obra in r['obras']] == esperado['obras']


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


def test_obra_nueva_persiste_recibo_y_conserva_historica_sin_atribucion(tmp_path, monkeypatch):
    """072:RF-28: registro real del espacio releído; obra física solo doble del guion."""
    from convertersmartgrid.adaptadores.entrada.capex import leer_capex_con_procedencia
    from convertersmartgrid.web.workspace import WorkspaceStore
    ruta = _capex(tmp_path)
    _, _, recibo = leer_capex_con_procedencia(ruta, CONFIG, contexto_unidades={'moneda': 'USD', 'escala_aplicada': 1000})
    raiz = tmp_path / 'espacios'
    store = WorkspaceStore(raiz)
    ws = store.create()
    ws.obras = [{'id': 'propia', 'clase': 'condensador', 'alimentador': 'F1', 'barra': 'B9', 'q_kvar': 300}]
    antigua = {'project': 'Propio', 'variacion': 'Historica', 'obra': {'q_kvar': 300}}
    ws.obras_aplicadas = [deepcopy(antigua)]
    ws.save()
    monkeypatch.setattr(services, 'native_action_context', lambda ws, p, fs, a: {'feeders': fs})
    monkeypatch.setattr(services, 'carpeta_de', lambda *a: 'Propia')
    monkeypatch.setattr(services, '_gemelo', lambda *a, **k: None)
    def guion(ws, ctx, script, plan, **kw):
        ws.plans_dir.mkdir(parents=True, exist_ok=True)
        (ws.plans_dir / 'plan_propio.json').write_text(json.dumps(plan), encoding='utf-8')
        informe = {'obras': [{'obra': 1, 'variacion': 'NuevaPropia'}], 'procedencia_capex': plan['procedencia_capex']}
        salida = ws.out_dir / 'guion_doble.json'
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(json.dumps(informe), encoding='utf-8')
        return 0, informe, salida
    monkeypatch.setattr(services, '_guion_pf', guion)
    services.obras_ejecutar(ws, SimpleNamespace(log=lambda *a: None), 'Propio', ['F1'], ['propia'], '',
                            simular=False, eleccion={'procedencia_capex': recibo})
    releido = WorkspaceStore(raiz).get(ws.id)
    assert releido.obras_aplicadas[0] == antigua
    assert releido.obras_aplicadas[1]['eleccion']['procedencia_capex'] == recibo
    assert releido.obras_aplicadas[1]['obra']['q_kvar'] == 300
    assert json.loads((ws.plans_dir / 'plan_propio.json').read_text())['procedencia_capex'] == recibo
    assert json.loads((ws.out_dir / 'guion_doble.json').read_text())['procedencia_capex'] == recibo
