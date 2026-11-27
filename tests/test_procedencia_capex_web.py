"""072:RF-28: recibo CAPEX en consumidores económicos, sin motor nativo."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from types import SimpleNamespace

from convertersmartgrid.presentacion.web import services
from test_pide_economia import CONFIG, _capex


def perfil():
    return {'planificacion': {'capex': CONFIG, 'crecimiento_demanda_anual': .04,
                             'vida_util_anios': 30, 'horizonte_anios': 20, 'tasa_regulada': .12},
            'escalera': {'moneda': 'USD', 'escala_capex': 1000}}


def test_pide_guarda_plan_y_resultado_con_recibo_de_su_lectura(tmp_path, monkeypatch):
    """072:RF-28: fuente efectiva en plan/resultado; diagnóstico doble, sin motor ni ML."""
    from convertersmartgrid.dominio import perfil_empresa as pe
    from convertersmartgrid.aplicacion import pide_economia as ec
    from convertersmartgrid.adaptadores.asistente import ejemplos_pide
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
    ws = SimpleNamespace(out_dir=tmp_path, plans_dir=tmp_path / 'planes')
    ctx = SimpleNamespace(log=lambda *a: None)
    r = services.pide_ejecutar(ws, ctx, 'Propio', ['F1'], capex=str(ruta), implementar=False)
    recibo = r['procedencia_capex']
    assert recibo['fuente']['sha256'] == hashlib.sha256(ruta.read_bytes()).hexdigest()
    # 025:RF-77 en el PIDE (hallazgo H1 del auditor, 2026-11-14): la escala y la moneda son las del perfil, como en
    # la escalera. Antes el recibo blindaba escala 1 y moneda None, y el PIDE tomaba los kUSD del libro como USD.
    assert recibo['contexto_unidades']['escala_aplicada'] == 1000
    assert recibo['contexto_unidades']['moneda'] == 'USD'
    assert not recibo['unidades_no_declaradas']
    plan = json.loads((tmp_path / 'plan_persistido.json').read_text(encoding='utf-8'))
    assert plan['procedencia_capex'] == recibo
    resultado = tmp_path / 'resultado.json'
    resultado.write_text(json.dumps(r), encoding='utf-8')
    assert json.loads(resultado.read_text(encoding='utf-8'))['procedencia_capex'] == recibo
    costos_libro = ec.costos_por_alternativa(ec.leer_capex(ruta, CONFIG)[0])
    costos_usd = ec.costos_en_moneda_de_trabajo(costos_libro, 1000)
    # Una sola vez: los 3500 kUSD por banco del libro son 3 500 000 USD, ni 3500 ni 3 500 000 000.
    assert costos_libro['bancos']['costo_unitario'] == 3500
    assert costos_usd['bancos']['costo_unitario'] == 3_500_000
    esperado = ec.propuesta_pide(informe, p['planificacion'], costos=costos_usd,
                                bancos_kvar=None, factor_carga=None, precio_compra_kwh=None, coym_pct_anual=None)
    assert r['obras']
    # 072:RF-47: la web pasa el registro normativo y cada obra lleva su traza legal; las obras y sus costes no cambian.
    assert all('normativa' in obra for obra in r['obras'])
    fuera = ('procedencia_capex', 'normativa')
    sin_traza = [{k: v for k, v in obra.items() if k != 'normativa'} for obra in esperado['obras']]
    assert [{k: v for k, v in obra.items() if k not in fuera} for obra in r['obras']] == sin_traza
    con_costo = [o for o in r['obras'] if o['ci']]
    assert con_costo and all(o['ci'] == costos_usd[o['alternativa']]['costo_unitario'] for o in con_costo)


def test_pide_sin_escala_del_libro_en_el_perfil_lo_dice_y_no_supone_1(tmp_path, monkeypatch):
    """025:RF-77 (H1): con costos en el libro y sin ``escalera.escala_capex`` el PIDE no sigue con escala 1."""
    import pytest
    from convertersmartgrid.dominio import perfil_empresa as pe
    p = perfil()
    del p['escalera']['escala_capex']
    p['estudios'] = {'tension_min_pu': .95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}
    monkeypatch.setattr(pe, 'datos_perfil', lambda: p)
    monkeypatch.setattr(pe, 'estructura_empresa', lambda: None)
    monkeypatch.setattr(services, 'native_action_context', lambda ws, project, feeders, action: {'feeders': feeders})
    monkeypatch.setattr(services, 'carpeta_de', lambda *a: 'Propia')
    monkeypatch.setattr(services, '_ingreso_de_las_cargas', lambda *a: [])
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: pytest.fail('no debe llegar a DIgSILENT'))
    ws = SimpleNamespace(out_dir=tmp_path, plans_dir=tmp_path / 'planes')
    ctx = SimpleNamespace(log=lambda *a: None)
    with pytest.raises(services.UserError, match='escala_capex'):
        services.pide_ejecutar(ws, ctx, 'Propio', ['F1'], capex=str(_capex(tmp_path)), implementar=False)


def test_pide_con_tarifas_en_soles_y_sin_tipo_de_cambio_lo_dice_en_el_resultado(tmp_path, monkeypatch):
    """025:RF-68 / 025:RF-77 (H4): tarifas y precio de compra en PEN, CAPEX en USD y sin tipo de cambio: el
    resultado que ve la web trae el aviso y ninguna obra lleva VAN privada."""
    from convertersmartgrid.dominio import perfil_empresa as pe
    from convertersmartgrid.adaptadores.asistente import ejemplos_pide
    p = perfil()
    p['planificacion'].update(tarifas={'moneda': 'PEN', 'MT3': {'energia_kwh': 0.29}}, tasa_privada=.12,
                              factor_carga=.6, precio_compra_kwh=.20)
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
    reporte = tmp_path / 'diagnostico.json'
    reporte.write_text(json.dumps(informe), encoding='utf-8')
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, deepcopy(informe), reporte))
    ws = SimpleNamespace(out_dir=tmp_path, plans_dir=tmp_path / 'planes')
    ctx = SimpleNamespace(log=lambda *a: None)
    r = services.pide_ejecutar(ws, ctx, 'Propio', ['F1'], capex=str(_capex(tmp_path)), implementar=False)
    assert any('tipo de cambio' in a and 'PEN' in a and 'USD' in a for a in r['avisos'])
    assert r['obras'] and all(o['privada'] is None for o in r['obras'])


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
    from convertersmartgrid.dominio import perfil_empresa as pe
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
    from convertersmartgrid.presentacion.web.workspace import WorkspaceStore
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


def test_042_rf113_en_blanco_se_usa_el_capex_de_las_referencias(tmp_path, monkeypatch):
    """042:RF-113 — con la casilla en blanco, el libro CAPEX vigente: el de las referencias del espacio (el más reciente
    con la hoja del perfil, por su contenido y no por su nombre); el del perfil local manda; lo escrito manda siempre."""
    import os
    from openpyxl import Workbook

    from convertersmartgrid.dominio import perfil_empresa as pe

    refs = tmp_path / 'referencias'
    (refs / '1.-medidores').mkdir(parents=True)
    medidores = refs / '1.-medidores' / 'medidores.xlsx'
    Workbook().save(medidores)
    viejo = _capex(tmp_path)
    viejo = viejo.rename(refs / 'libro_a.xlsx')
    os.utime(viejo, (1_700_000_000, 1_700_000_000))
    nuevo = _capex(tmp_path).rename(refs / 'libro_b.xlsx')
    otro = Workbook()
    otro.active.title = 'Otra'
    otro.save(refs / 'CAPEX_sin_su_hoja.xlsx')
    p = perfil()
    monkeypatch.setattr(pe, 'datos_perfil', lambda: p)
    ws = SimpleNamespace(demanda={'medidores': {'path': str(medidores)}, 'vacia': {}})
    vigente = services.capex_vigente(ws)
    assert vigente == {'ruta': str(nuevo), 'nombre': 'libro_b.xlsx', 'origen': 'referencias'}
    assert services.capex_o_vigente(ws, '') == str(nuevo)
    assert services.capex_o_vigente(ws, 'D:/otro.xlsx') == 'D:/otro.xlsx'
    p['planificacion']['capex'] = {**CONFIG, 'libro': str(viejo)}
    assert services.capex_vigente(ws)['origen'] == 'perfil'
    p['planificacion']['capex'] = CONFIG
    assert services.capex_vigente(SimpleNamespace(demanda={})) is None

