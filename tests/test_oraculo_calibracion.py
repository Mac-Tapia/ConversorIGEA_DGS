"""Spec 083: el oráculo antes de calibrar. La red es sintética; DIgSILENT se prueba por la web (T3)."""
from __future__ import annotations

import pytest

from convertersmartgrid.ajuste_cabecera import MedidaConjunta, Objetivo, Reparto, cuadrar_conjunto
from convertersmartgrid.digital_twin.native_snapshot import identidad_nativa
from convertersmartgrid.oraculo_calibracion import arranque_con_oraculo


def _id(nombre, clase):
    return identidad_nativa(clase, f'{nombre}.{clase}', '')


def _grafo(r=2.0, x=1.5):
    nodos = {_id('S', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': True, 'v_pu': 1.0},
             _id('A', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': False},
             _id('B', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': False}}
    ramas = [{'id': _id('T1', 'ElmLne'), 'desde': _id('S', 'ElmTerm'), 'hasta': _id('A', 'ElmTerm'),
              'r_ohm': r, 'x_ohm': x, 'inom_ka': 0.3, 'cerrada': True},
             {'id': _id('T2', 'ElmLne'), 'desde': _id('A', 'ElmTerm'), 'hasta': _id('B', 'ElmTerm'),
              'r_ohm': r, 'x_ohm': x, 'inom_ka': 0.3, 'cerrada': True}]
    return {'nodos': nodos, 'ramas': ramas}


def _reparto(a=1.0):
    base = {'SA': (300.0, 60.0), 'SB': (500.0, 100.0)}
    return Reparto(fijas={}, base=base, origen={'SA': 'kva', 'SB': 'kva'}, kva={'SA': 400.0, 'SB': 630.0}, a=a, b=a, solo_kw=True)


def _datos():
    nodos = {'F': {'SA': _id('A', 'ElmTerm'), 'SB': _id('B', 'ElmTerm')}}
    return nodos, {'F': [_id('T1', 'ElmLne'), _id('T2', 'ElmLne')]}


def test_el_oraculo_halla_el_factor_y_cuenta_las_perdidas():
    """083:RF-1, 083:RF-2, 083:RF-5 — cuadra sin DIgSILENT; la medida lleva las pérdidas de sus ramas, y lo dice en el informe."""
    nodos, ramas = _datos()
    obj = {'F': Objetivo(1200.0, 200.0, 'M')}
    r = arranque_con_oraculo(_grafo(), nodos, ramas, {'F': _reparto()}, obj)
    assert r.cuadrado and r.modelo == 'fisica' and r.evaluaciones >= 1
    # Con pérdidas, las cargas consumen menos que la cabecera: 1 200 kW serían a = 1,5 sin ellas.
    assert r.factores['F'] < 1.5
    inf = r.informe()
    assert inf['modelo'] == 'fisica' and inf['factores'] == r.factores


def test_arrancar_del_oraculo_gasta_menos_flujos():
    """083:RF-1 — el mismo flujo como si fuera DIgSILENT: del arranque del oráculo cuadra en menos intentos."""
    nodos, ramas = _datos()
    obj = {'F': Objetivo(1200.0, 200.0, 'M')}

    def flujo_falso(reps):
        return MedidaConjunta(True, kw={'F': sum(d.kw for d in reps['F'].demandas.values()) * 1.02}, kvar={'F': 0.0})

    sin = cuadrar_conjunto({'F': _reparto(0.2)}, obj, flujo_falso, tolerancia=0.001)
    con_oraculo = arranque_con_oraculo(_grafo(), nodos, ramas, {'F': _reparto(0.2)}, obj)
    con = cuadrar_conjunto(con_oraculo.repartos, obj, flujo_falso, tolerancia=0.001)
    assert sin.cuadrado and con.cuadrado and con.flujos <= sin.flujos


def test_sin_converger_lo_dice_y_no_propone_arranque():
    """083:RF-4 — una red que no da el flujo no bloquea: lo dice, y la calibración sigue con el de siempre."""
    nodos, ramas = _datos()
    r = arranque_con_oraculo(_grafo(r=400.0, x=400.0), nodos, ramas, {'F': _reparto(5.0)},
                             {'F': Objetivo(9000.0, 2000.0, 'M')})
    assert not r.cuadrado and r.motivo


class _PinnFuera:
    """Un PINN que dice estar fuera de su dominio: decide el flujo físico (071:RF-2)."""

    def predecir(self, _grafo):
        return {'fuera_de_dominio': True}


def test_pinn_fuera_de_dominio_decide_el_flujo_fisico():
    """083:RF-3 — se dice cuál se usó."""
    nodos, ramas = _datos()
    r = arranque_con_oraculo(_grafo(), nodos, ramas, {'F': _reparto()}, {'F': Objetivo(1200.0, 200.0, 'M')},
                             pinn=_PinnFuera())
    assert r.cuadrado and r.modelo == 'fisica'


@pytest.mark.parametrize('n', (2, 4))
def test_vale_para_cualquier_numero_de_alimentadores(n):
    """083:RF-1 — cada uno con su factor; los que comparten red no se mezclan."""
    nodos, ramas = _datos()
    reps = {f'F{i}': _reparto() for i in range(n)}
    obj = {k: Objetivo(900.0, 150.0, 'M') for k in reps}
    r = arranque_con_oraculo(_grafo(), {k: {} for k in reps} | {'F0': nodos['F']}, {'F0': ramas['F']}, reps, obj)
    assert set(r.factores) == set(reps)


def test_con_central_en_un_tramo_usa_el_arranque_de_siempre():
    """083:RF-6, 083:RF-4 — sus zonas se miden de otra forma: lo dice y no toca los repartos; un fallo tampoco bloquea."""
    from apoyo import cargar_herramienta

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion', tools_en_path=True)
    reps = {'F': _reparto()}
    salen, inf = guion._arranque_del_oraculo(None, None, {'F': {'central': True}}, reps, {}, (), 0.01)
    assert salen is reps and 'RF-6' in inf['motivo'] and inf['modelo'] is None
    salen, inf = guion._arranque_del_oraculo(None, None, {'F': {'central': False}}, reps, {}, (), 0.01)
    assert salen is reps and inf['modelo'] is None and inf['motivo']


# ------------------------------------------------------------------ cuadre robusto
class _RedFalsa:
    """Un flujo de juguete: lo que consumen las escaladas más un acople; los primeros flujos pueden no converger."""

    def __init__(self, acople=0.0, sin_converger_hasta=0, perdida=1.02):
        self.acople, self.sin_converger_hasta, self.perdida = acople, sin_converger_hasta, perdida
        self.n = 0

    def __call__(self, reps):
        self.n += 1
        if self.n <= self.sin_converger_hasta:
            return MedidaConjunta(False, motivo='no converge')
        total = {k: sum(d.kw for d in r.demandas.values()) for k, r in reps.items()}
        suma = sum(total.values())
        return MedidaConjunta(True, kw={k: v * self.perdida + self.acople * (suma - v) for k, v in total.items()},
                              kvar={k: 0.0 for k in reps})


def test_sin_flujo_bueno_prueba_casi_cero_y_no_gasta_medios_caminos():
    """083:RF-7 — si ni con las escaladas casi en cero converge, lo señala y va al remedio siguiente."""
    remedios = []

    def remedio(nombre, _a):
        remedios.append(nombre)
        return [nombre]

    red = _RedFalsa(sin_converger_hasta=4)
    res = cuadrar_conjunto({'F': _reparto()}, {'F': Objetivo(1200.0, 200.0, 'M')}, red, remedio=remedio, tolerancia=0.01)
    assert res.fijas_sospechosas and res.cuadrado
    # Dos flujos por remedio: el objetivo y casi cero. Antes eran cinco.
    assert red.n <= 7 and len(remedios) == 2


def test_si_casi_cero_converge_no_acusa_a_las_fijas():
    """083:RF-7 — eran las escaladas: sigue con la secante desde ese flujo bueno."""
    res = cuadrar_conjunto({'F': _reparto()}, {'F': Objetivo(1200.0, 200.0, 'M')}, _RedFalsa(sin_converger_hasta=1))
    assert res.cuadrado and not res.fijas_sospechosas


def test_un_solo_alimentador_tambien():
    """083:RF-13 — ``cuadrar`` hace lo mismo."""
    from convertersmartgrid.ajuste_cabecera import Medida, cuadrar

    n = {'v': 0}

    def flujo(rep):
        n['v'] += 1
        if n['v'] <= 2:
            return Medida(False, motivo='no converge')
        kw = sum(d.kw for d in rep.demandas.values()) * 1.02
        return Medida(True, kw=kw, kvar=100.0, carga_kw=kw / 1.02, carga_kvar=100.0)

    res = cuadrar(_reparto(), Objetivo(1200.0, 200.0, 'M'), flujo, remedio=lambda nombre, _a: [nombre])
    assert res.fijas_sospechosas and res.cuadrado


def test_el_que_ya_cuadro_no_se_mueve():
    """083:RF-10 — el factor de F1 sigue igual mientras F2 cuadra."""
    reps = {'F1': _reparto(1.0), 'F2': _reparto(0.3)}
    obj = {'F1': Objetivo(816.0, 100.0, 'M1'), 'F2': Objetivo(800.0, 100.0, 'M2')}
    res = cuadrar_conjunto(reps, obj, _RedFalsa(), tolerancia=0.01)
    assert res.cuadrado and res.repartos['F1'].a == 1.0 and res.metodos.get('quietos', 0) >= 1


def test_el_factor_no_se_sale_del_intervalo_conocido():
    """083:RF-11 — con puntos a los dos lados, un salto fuera vuelve al medio; sin los dos, no se toca."""
    from convertersmartgrid.ajuste_cabecera import _acotar

    assert _acotar(5.0, [(1.0, 90.0), (2.0, 110.0)], 100.0) == (1.5, True)
    assert _acotar(1.2, [(1.0, 90.0), (2.0, 110.0)], 100.0) == (1.2, False)
    assert _acotar(5.0, [(1.0, 90.0)], 100.0) == (5.0, False)


def test_broyden_aprende_el_acople_entre_alimentadores():
    """083:RF-12 — resuelve el sistema con su acople tras un par de datos."""
    from convertersmartgrid.ajuste_cabecera import _Broyden

    b = _Broyden(('A', 'B'), {'A': 100.0, 'B': 100.0})
    medir = lambda x: [100.0 * x[0] + 30.0 * x[1], 30.0 * x[0] + 100.0 * x[1]]
    x = [1.0, 1.0]
    objetivo = [200.0, 150.0]
    for _ in range(12):
        y = medir(x)
        b.actualizar(list(x), y)
        paso = b.paso([o - v for o, v in zip(objetivo, y, strict=True)])
        x = [v + p for v, p in zip(x, paso, strict=True)]
    assert medir(x) == pytest.approx(objetivo, rel=1e-4)


def test_recalibrar_arranca_del_factor_de_la_ultima():
    """083:RF-9 — si lo guardó; sin él, como siempre."""
    from apoyo import cargar_herramienta

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion2', tools_en_path=True)
    reps = {'F': _reparto(), 'G': _reparto()}
    salen = guion._desde_la_ultima_calibracion(reps, {'F': {'ultima_calibracion': {'factor_escala': 0.42}}, 'G': {}})
    assert salen['F'].a == 0.42 and salen['G'] is reps['G']


# ------------------------------------------------------------------ libros de clientes
def _libro(ruta, filas_por_hoja):
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for hoja, filas in filas_por_hoja.items():
        ws = wb.create_sheet(hoja)
        for f in filas:
            ws.append(f)
    wb.save(ruta)


def test_registro_del_cliente_sin_maestro_en_las_dos_disposiciones(tmp_path):
    """083:RF-14 — la hoja por su contenido y el registro de la fecha de la barra, en los dos formatos."""
    from datetime import datetime

    from convertersmartgrid import demanda_medida as dm

    ruta = tmp_path / 'c.xlsx'
    _libro(ruta, {
        'resumen': [['Nis', 'EA'], ['999', 1.0]],
        'Iqf_181546': [['', 276.7, '', '', '', 181000546, '', '', '', 'Medición'], ['', 'Fuente'], ['', '', '', '', '', '', 'factor', 1.0],
                       ['', '', '', '', '', 'EA', 'ERI', 'ERC', '', 'EA', 'ERI', 'ERC', 'Pot'],
                       ['día', 'hora', 'f1p2', 'pp', '', 1, 2, 0, '', 7, 8, 0, 9],
                       [23, '12:15', 1, 1, '23-12:15', 0.1, 0.2, 0, 6, 10.0, 5.0, 0, 40.0],
                       [23, '12:30', 1, 1, '23-12:30', 0.1, 0.2, 0, 7, 20.0, 6.0, 0, 80.0]],
        'Admacon': [['CLIENTE', 281000289, '', 'CONCESION'], [''], ['SUMINISTRADOR'], [''],
                    ['SUMINISTRO', 'FECHA', 'HORA', 'EA', 'ERI', 'ERC', 'POT'],
                    [281000289, '23/01/2026', '12:15', 3.0, 1.0, 0.0, 12.0]]})
    t = datetime(2026, 1, 23, 12, 15)
    reg, avisos = dm.registros_de_maxima(ruta, {'181000546': 80.0, '281000289': 12.0, '555': 1.0}, instante=t, solo_instante=True)
    assert avisos == []
    assert reg['181000546'] == ('23/01/2026 12:15', pytest.approx(20.0), pytest.approx(40.0))
    assert reg['281000289'] == ('23/01/2026 12:15', pytest.approx(4.0), pytest.approx(12.0))
    assert '555' not in reg
    # Con hoja y sin ese registro, no toma otro (039:RF-4).
    otro, _ = dm.registros_de_maxima(ruta, {'181000546': 80.0}, instante=datetime(2026, 1, 24, 12, 15), solo_instante=True)
    assert otro['181000546'] is None


def test_la_q_que_no_reproduce_la_precision_de_digsilent_no_es_un_fallo():
    """083:RF-15 — el margen crece con la P: una Q pequeña con un FP casi 1."""
    from apoyo import cargar_herramienta

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion3', tools_en_path=True)
    assert guion._cerca(10.411, 10.412, abs_=max(1e-3, 490.0 * guion.MARGEN_Q_DE_P))
    assert not guion._cerca(10.5, 10.412, abs_=max(1e-3, 490.0 * guion.MARGEN_Q_DE_P))


def test_las_muestras_corren_en_el_oraculo_y_no_en_digsilent():
    """083:RF-20 — DIgSILENT solo confirma el P50; la lectura del oráculo da carga y banda por SED."""
    from apoyo import cargar_herramienta

    from convertersmartgrid.ajuste_cabecera import Probabilistico
    from convertersmartgrid.oraculo_calibracion import FlujoOraculo

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion4', tools_en_path=True)
    nodos, ramas = _datos()
    oraculo = FlujoOraculo(_grafo(), nodos, ramas, trafos_de={'SA': [_id('T1', 'ElmLne')], 'SB': [_id('T2', 'ElmLne')]})
    obj = {'F': Objetivo(1200.0, 200.0, 'M')}
    res = cuadrar_conjunto({'F': _reparto()}, obj, oraculo, tolerancia=0.01)
    assert res.cuadrado
    lectura = oraculo.lectura('F', res.repartos['F'], [0.95, 1.05])
    assert set(lectura['carga']) == {'SA', 'SB'} and lectura['carga']['SA'] > 0 and lectura['fuera_de_banda'] in (True, False)

    en_digsilent = []

    def flujo_real(reps):
        en_digsilent.append(1)
        return oraculo(reps)

    prob = Probabilistico(dispersion=0.2, pendiente=0.0, n=8, semilla=3, fuente='prueba')
    guion.preparar_probabilistico = lambda _plan, _rep: (prob, None)
    preps = {'F': {'central': False, 'plan': {'banda_tension': [0.95, 1.05]}, 'cargas': {}}}
    informes = {'F': {'avisos': []}}
    final = guion._probabilistico_del_proyecto(res, preps, informes, obj, flujo_real, None, quietas=(), tolerancia=0.01,
                                               max_flujos=10, remedio=lambda n, a: [], cancelado=lambda: False, con_q=(),
                                               oraculo=oraculo)
    assert final.cuadrado and informes['F']['probabilistico']
    # Ocho muestras: DIgSILENT hace solo el cuadre final del P50, no uno por muestra.
    assert 1 <= len(en_digsilent) <= 4


def test_el_cronometro_suma_por_etapa_y_lo_escribe(tmp_path, monkeypatch, capsys):
    """083:RF-21, 083:RF-22 — los segundos de cada etapa, también en un fichero si se pide; marcar las cargas es una sola etapa."""
    from apoyo import cargar_herramienta

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion5', tools_en_path=True)
    ruta = tmp_path / 't.log'
    monkeypatch.setenv('CSG_AJUSTE_TIEMPOS', str(ruta))
    c = guion.Cronometro()
    c.marca('flujo en DIgSILENT')
    c.marca('flujo en DIgSILENT')
    c.marca('oráculo')
    assert set(c.etapas) == {'flujo en DIgSILENT', 'oráculo'}
    assert 'tiempo oráculo' in capsys.readouterr().out and ruta.read_text(encoding='utf-8').count('flujo en DIgSILENT') == 2


def test_oraculo_para_las_muestras_con_los_factores_cuadrados_y_su_entrada(tmp_path, monkeypatch):
    """083:RF-23, 083:RF-24 — si converge con lo cuadrado se usa; si no, ``None``; y la entrada queda guardada."""
    import json
    import tempfile

    from apoyo import cargar_herramienta

    from convertersmartgrid.oraculo_calibracion import FlujoOraculo

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion6', tools_en_path=True)
    nodos, ramas = _datos()
    bueno = FlujoOraculo(_grafo(), nodos, ramas)
    assert guion.oraculo_para_muestras(bueno, {'F': _reparto()}) is bueno
    malo = FlujoOraculo(_grafo(r=400.0, x=400.0), nodos, ramas)
    assert guion.oraculo_para_muestras(malo, {'F': _reparto(5.0)}) is None
    assert guion.oraculo_para_muestras(None, {'F': _reparto()}) is None
    from convertersmartgrid import pf_arnes

    monkeypatch.setattr(pf_arnes, 'ruta_turno', lambda: tmp_path / 'powerfactory.turno')
    ruta = guion.guardar_entrada_del_oraculo(_grafo(), nodos, ramas, {}, {'F': _reparto()}, {'F': Objetivo(1200.0, 200.0, 'M')})
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    assert set(datos) == {'grafo', 'nodos', 'ramas', 'trafos', 'repartos', 'objetivos'} and datos['repartos']['F']['a'] == 1.0


def test_las_muestras_en_digsilent_paran_al_tope_de_tiempo():
    """083:RF-25 — con al menos 20 hechas y el tope alcanzado, para, escribe el P50 de las hechas y lo dice."""
    from convertersmartgrid.ajuste_cabecera import Probabilistico, montecarlo

    t = {'v': 0.0}

    def reloj():
        return t['v']

    def cuadrar_muestra(m):
        t['v'] += 10.0                       # 10 s por muestra, como un flujo de DIgSILENT
        return m, {}

    prob = Probabilistico(dispersion=0.2, pendiente=0.0, n=200, semilla=1, fuente='prueba')
    resumen, p50 = montecarlo(_reparto(), prob, cuadrar_muestra, tope_s=180.0, reloj=reloj)
    assert resumen['muestras_hechas'] == 20 and '083:RF-25' in resumen['aviso_tope'] and p50 is not None
    t['v'] = 0.0
    resumen, _ = montecarlo(_reparto(), Probabilistico(dispersion=0.2, pendiente=0.0, n=30, semilla=1, fuente='p'),
                            cuadrar_muestra, reloj=reloj)
    assert 'aviso_tope' not in resumen


def test_lo_escrito_por_la_aplicacion_no_es_manual_y_el_ajuste_heredado_vuelve_a_cero(tmp_path, monkeypatch):
    """083:RF-26, 083:RF-27 — una carga con lo que escribió la aplicación no es manual; un cambio distinto, sí; iopt_lev a 0."""
    from types import SimpleNamespace

    from apoyo import cargar_herramienta

    from convertersmartgrid import pf_arnes

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion7', tools_en_path=True)
    monkeypatch.setattr(pf_arnes, 'ruta_turno', lambda: tmp_path / 'powerfactory.turno')

    def carga(kw):
        return SimpleNamespace(plini=kw / 1000.0, qlini=kw / 5000.0, scale0=1.0, i_sym=0)

    cargas = {'S1': carga(100.0), 'S2': carga(50.0)}
    ultima = {'sed': {'S1': [80.0, 16.0], 'S2': [40.0, 8.0]}, 'escrita': {'S1': [80.0, 16.0], 'S2': [40.0, 8.0]}}
    assert {m['sed'] for m in guion.cambios_manuales(cargas, ultima)[0]} == {'S1', 'S2'}
    guion.guardar_lo_escrito('P (prueba)', {'F': {'S1': cargas['S1']}})
    escrito = guion.lo_escrito('P (prueba)')
    assert {m['sed'] for m in guion.cambios_manuales(cargas, ultima, escrito)[0]} == {'S2'}
    cargas['S1'].plini = 0.2                     # el operador lo cambia después: vuelve a ser manual
    assert {m['sed'] for m in guion.cambios_manuales(cargas, ultima, escrito)[0]} == {'S1', 'S2'}

    ldf = SimpleNamespace(iopt_lev=1, iopt_pq=0, GetAttribute=lambda a: getattr(ldf, a))
    app = SimpleNamespace(GetFromStudyCase=lambda _n: ldf)
    assert guion.ajustes_heredados_a_cero(app) == {'iopt_lev': 1} and ldf.iopt_lev == 0
    assert guion.ajustes_heredados_a_cero(app) == {}


def test_el_que_no_puede_cuadrar_se_nombra_y_no_tumba_el_arranque():
    """083:RF-28 — una fija mayor que la medida: ese alimentador se nombra; los demás tienen su factor."""
    nodos, ramas = _datos()
    rep = Reparto(fijas={'SA': (900.0, 100.0)}, base={'SB': (500.0, 100.0)}, origen={'SA': 'cliente', 'SB': 'kva'},
                  kva={'SA': 400.0, 'SB': 630.0}, a=1.0, b=1.0, solo_kw=True)
    r = arranque_con_oraculo(_grafo(), nodos, ramas, {'F': rep}, {'F': Objetivo(800.0, 100.0, 'M')}, max_evaluaciones=20)
    assert not r.cuadrado and r.repartos and 'F' in r.sin_cuadre
    assert r.sin_cuadre['F']['fijas_kw'] == 900.0 and r.informe()['sin_cuadre']


def test_el_ajuste_heredado_vuelve_a_cero_en_los_dos_casos_y_no_en_el_del_operador():
    """083:RF-26 — «Sin» y «Con proyecto» tienen cada uno su ComLdf; el caso activo se conserva; sin caso del sistema no se toca."""
    from types import SimpleNamespace

    from apoyo import cargar_herramienta

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion8', tools_en_path=True)
    estado = {}

    def caso(lev):
        ldf = SimpleNamespace(iopt_lev=lev, iopt_pq=0)
        ldf.GetAttribute = lambda a: getattr(ldf, a)
        c = SimpleNamespace(ldf=ldf)
        c.Activate = lambda: estado.update(activo=c)
        return c

    sin, con, operador = caso(0), caso(1), caso(1)
    estado['activo'] = operador
    app = SimpleNamespace(GetFromStudyCase=lambda _n: estado['activo'].ldf, GetActiveStudyCase=lambda: estado['activo'])
    assert guion.heredados_en_los_casos(app, None, None) == {} and operador.ldf.iopt_lev == 1
    assert guion.heredados_en_los_casos(app, sin, con) == {'iopt_lev': 1}
    assert con.ldf.iopt_lev == 0 and estado['activo'] is operador


def test_las_variaciones_del_conversor_vuelven_a_estar_activas_en_los_dos_casos(monkeypatch):
    """083:RF-29 — Pisco: una calibración fallida apagaba ``SED_NTP_`` y la siguiente veía los transformadores viejos."""
    from types import SimpleNamespace

    from apoyo import cargar_herramienta

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion9', tools_en_path=True)
    estado = {}

    def caso(nombre):
        c = SimpleNamespace(loc_name=nombre, activas=[])
        c.Activate = lambda: estado.update(activo=c)
        return c

    def variacion(nombre):
        v = SimpleNamespace(loc_name=nombre)
        v.Activate = lambda: estado['activo'].activas.append(v)
        return v

    sed, fichas = variacion('SED_NTP_P'), variacion('Fichas_P')
    sin, con = caso('Sin proyecto'), caso('Con proyecto')
    sin.activas.append(fichas)
    estado['activo'] = sin
    app = SimpleNamespace(GetActiveStudyCase=lambda: estado['activo'],
                          GetActiveNetworkVariations=lambda: list(estado['activo'].activas))
    monkeypatch.setattr(guion, 'variacion_propia', lambda _a, n: {'SED_NTP_P': sed, 'Fichas_P': fichas}.get(n))
    hechas = guion.variaciones_del_conversor_activas(app, 'P', sin, con)
    assert sed in sin.activas and sed in con.activas and fichas in con.activas and sin.activas.count(fichas) == 1
    assert len(hechas) == 3 and estado['activo'] is sin
    assert guion.variaciones_del_conversor_activas(app, 'P', sin, con) == []
    assert guion.variaciones_del_conversor_activas(app, 'P', None, None) == []


def test_las_fijas_que_pasan_de_la_medida_se_corrigen_hasta_el_tope():
    """083:RF-30 — PA219: la fija y sus pérdidas pasan de la cabecera. Dentro del tope se baja y queda dicho; las escaladas siguen con carga."""
    from convertersmartgrid.ajuste_cabecera import fijas_corregidas

    nodos, ramas = _datos()
    rep = Reparto(fijas={'SA': (820.0, 100.0)}, base={'SB': (500.0, 100.0)}, origen={'SA': 'cliente', 'SB': 'kva'},
                  kva={'SA': 400.0, 'SB': 630.0}, a=1.0, b=1.0, solo_kw=True)
    r = arranque_con_oraculo(_grafo(), nodos, ramas, {'F': rep}, {'F': Objetivo(800.0, 100.0, 'M')}, max_evaluaciones=30)
    assert r.cuadrado and not r.sin_cuadre
    cambios = fijas_corregidas(rep, r.repartos['F'])
    assert cambios[0]['sed'] == 'SA' and cambios[0]['antes_kw'] == 820.0 and cambios[0]['despues_kw'] < 800.0
    assert r.repartos['F'].a > 0



def test_la_grabacion_vuelve_a_la_ultima_etapa_del_conversor():
    """083:RF-29 — con las fichas grabando no se aplicaba la etapa posterior de los transformadores (CA101 + CHN102)."""
    from types import SimpleNamespace

    from apoyo import cargar_herramienta

    guion = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_oraculo_guion_etapas', tools_en_path=True)
    estado = {}

    def etapa(t):
        s = SimpleNamespace(tAcTime=t, loc_name=f'E{t}')
        s.Activate = lambda _graba=1: estado.update(graba=s)
        return s

    fichas, sed, ajena = etapa(10), etapa(11), etapa(99)
    variacion = lambda nombre, *ss: SimpleNamespace(loc_name=nombre, GetContents=lambda _p: list(ss))
    activas = [variacion('Fichas_P', fichas), variacion('SED_NTP_P', sed), variacion('Obra_del_operador', ajena)]
    app = SimpleNamespace(GetActiveNetworkVariations=lambda: activas, GetRecordingStage=lambda: estado.get('graba'))
    estado['graba'] = fichas
    guion._grabar_en_la_ultima_del_conversor(app)
    assert estado['graba'] is sed, 'la de los transformadores, no la de una obra del operador'
    guion._grabar_en_la_ultima_del_conversor(app)
    assert estado['graba'] is sed
    estado['graba'] = None
    guion._grabar_en_la_ultima_del_conversor(app)
    assert estado['graba'] is None, 'sin nada grabando no se pone a grabar'
