"""072:RF-23 a RF-28: continuación anual sin inventar demanda ni obras físicas."""
import hashlib
import json
from pathlib import Path

import fake_pf
import pytest

from apoyo import cargar_herramienta, contexto_nativo
from convertersmartgrid.pide import PideError


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return {'ruta': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def anual(tmp_path, monkeypatch):
    tool = cargar_herramienta('pide_pf.py', tools_en_path=True)
    cases = cargar_herramienta('casos_pf.py', tools_en_path=True)
    monkeypatch.setattr(cases, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    app = fake_pf.proyecto(alimentadores=('Red_A',), cargas_por_alim=1, bt=True, flujo=True, escenario=True)
    app.proyecto.Activate()
    app.escenario_manda = True
    app.atributos_en_variacion = True
    object.__setattr__(app.ldf, 'scLoadFac', 100.0)
    object.__setattr__(app.ldf, 'iopt_net', 0)
    plan_cases = {'project': 'P', 'feeders': ['Red_A'], 'folder': None,
                  'base': {'variaciones': [], 'feeders': ['Red_A'], 'ajustes': [], 'excluidos': []},
                  'caso_base_sin_verificar': {}}
    assert cases.preparar_sin(app, plan_cases)[1] == 0
    assert cases.preparar_con(app, plan_cases)[1] == 0
    source = cases.casos_del_proyecto(app)['con']
    source.Activate()
    load = app.proyecto.GetContents('*.ElmLod', 1)[0]
    load.mode_inp = 'PQ'
    object.__setattr__(load, 'GetAttributeUnit', lambda a: {'plini': 'MW', 'qlini': 'Mvar'}[a])
    transformer = app.proyecto.GetContents('*.ElmTr2', 1)[0]
    types = []
    for name, rating in [('Corto', 0.15), ('Anual_A', 0.30), ('Anual_B', 0.60)]:
        typ = app.carpetas['equip'].CreateObject('TypTr2', name)
        typ.strn = rating
        types.append(typ)
    works = []
    for name, typ in zip(('Obra_Corta', 'Obra_A', 'Obra_B'), types):
        v = fake_pf.variacion_del_operador(app, name, [(transformer, 'typ_id', typ)])
        works.append(v)
        v.Deactivate()
    works[0].Activate()
    app.GetActiveScenario().Save()
    short = {'caso': tool.clave_pf(source), 'escenario': tool.clave_pf(app.GetActiveScenario()),
             'anio': 4, 'anio_base': 2030, 'variaciones': [tool.clave_pf(works[0])]}
    short['evidencia'] = _json(tmp_path / 'corto.json', {**short, 'estado': 'aceptado'})
    evaluation = _json(tmp_path / 'evaluacion.json', {'estado': 'aceptado', 'uso': 'planeamiento_anual',
        'modelo': 'modelo_de_prueba', 'dataset_sha256': 'd' * 64, 'horizonte_anios': 7, 'anio_base': 2030})
    projection = {'proyecto': 'P', 'anio_base': 2030, 'modelo': 'modelo_de_prueba',
        'dataset_sha256': 'd' * 64, 'evaluacion': evaluation, 'filas': [
            {'anio': year, 'alimentador': 'Red_A', 'carga': tool.clave_pf(load), 'clase': 'escaladas',
             'objetivo': 'Red_A', 'p_kw': p, 'q_kvar': q}
            for year, p, q in [(5, 200, 20), (6, 400, 10), (7, 420, -10)]]}
    plan = {'project': 'P', 'feeders': ['Red_A'], 'modo': 'anual', 'estudio_id': 'prueba_anual',
        'anio_fin': 7, 'tasa': 0.05, 'corto_plazo': short, 'proyeccion_anual': _json(tmp_path / 'proyeccion.json', projection),
        'obras_por_anio': [{'anio': 5, 'variacion': tool.clave_pf(works[1])},
                           {'anio': 6, 'variacion': tool.clave_pf(works[2])}],
        'limites': {'tension_min_pu': 0.1, 'tension_max_pu': 2.0, 'cargabilidad_max_pct': 10000,
                    'transformador_max_pct': 80},
        'native_action_context': contexto_nativo('P', ['Red_A'], 'pide')}
    return tool, app, plan, projection, source, load, transformer, works


def test_cada_anio_copia_obras_previas_y_mide_pq_aceptadas(anual):
    """072:RF-23, 072:RF-24, 072:RF-25, 072:RF-26, 072:RF-27 — refuerzos acumulados y origen intacto."""
    tool, app, plan, projection, source, load, transformer, works = anual
    before = (load.plini, load.qlini, load.scale0, tool.clave_pf(transformer.typ_id),
              tool.clave_pf(app.GetActiveScenario()))
    report, rc = tool.ejecutar(app, plan)
    assert rc == 0, report
    assert report['primer_anio_incumplimiento'] == 5
    assert [row['anio'] for row in report['anios']] == [5, 6, 7]
    assert [row['obras_aplicadas'] for row in report['anios']] == [[tool.clave_pf(works[1])], [tool.clave_pf(works[2])], []]
    assert all(row['despues']['cumple'] for row in report['anios'])
    assert [len(row['obras_acumuladas']) for row in report['anios']] == [2, 3, 3]
    assert report['restitucion']['ok'] is True
    assert app.GetActiveStudyCase() is source
    assert before == (load.plini, load.qlini, load.scale0, tool.clave_pf(transformer.typ_id), tool.clave_pf(app.GetActiveScenario()))
    output_cases = app.carpetas['study'].GetContents('*.IntCase', 1)
    for year, p, q in [(5, .2, .02), (6, .4, .01), (7, .42, -.01)]:
        case = next(c for c in output_cases if f'Año {year:02d}' in tool.clave_pf(c) and c.loc_name == 'Con proyecto')
        case.Activate()
        assert load.plini * load.scale0 == pytest.approx(p)
        assert load.qlini * load.scale0 == pytest.approx(q)
    source.Activate()


@pytest.mark.parametrize('failure', ['missing_profile', 'hash', 'short_horizon', 'rejected', 'nan', 'missing_load', 'phase', 'missing_work', 'collision'])
def test_faltantes_anuales_bloquean_y_conservan_origen(anual, tmp_path, failure):
    """072:RF-24, 072:RF-25, 072:RF-27, 072:RF-28 — ninguna tasa ni magnitud ficticia cubre un dato ausente."""
    tool, app, plan, projection, source, load, transformer, works = anual
    before = (load.plini, load.qlini, load.scale0, tool.clave_pf(transformer.typ_id))
    if failure == 'missing_profile':
        plan.pop('proyeccion_anual')
    elif failure == 'hash':
        plan['proyeccion_anual']['sha256'] = 'a' * 64
    elif failure in ('short_horizon', 'rejected'):
        evidence = json.loads(Path(projection['evaluacion']['ruta']).read_text())
        evidence['horizonte_anios' if failure == 'short_horizon' else 'estado'] = 1 if failure == 'short_horizon' else 'rechazado'
        projection['evaluacion'] = _json(tmp_path / 'evaluacion.json', evidence)
        plan['proyeccion_anual'] = _json(tmp_path / 'proyeccion.json', projection)
    elif failure in ('nan', 'missing_load'):
        projection['filas'][0]['p_kw' if failure == 'nan' else 'carga'] = float('nan') if failure == 'nan' else 'no_existe.ElmLod'
        plan['proyeccion_anual'] = _json(tmp_path / 'proyeccion.json', projection)
    elif failure == 'phase':
        load.i_sym = 1
    elif failure == 'missing_work':
        plan['obras_por_anio'] = []
    elif failure == 'collision':
        folder = app.carpetas['study'].CreateObject('IntFolder', 'PIDE')
        folder.CreateObject('IntFolder', plan['estudio_id'])
    report, rc = tool.ejecutar(app, plan)
    assert rc != 0 and report.get('error'), report
    assert report['estado'] != 'completo'
    assert (load.plini, load.qlini, load.scale0, tool.clave_pf(transformer.typ_id)) == before
    assert app.GetActiveStudyCase() is source


def test_error_entre_anios_restituye_y_no_declara_exito(anual, monkeypatch):
    """072:RF-27, 072:RF-28 — una caída posterior al primer año deja informe parcial y restaura."""
    tool, app, plan, projection, source, load, transformer, works = anual
    original = tool.casos_del_anio
    def fail(*args, **kwargs):
        if args[2] == 6:
            raise RuntimeError('caída de prueba entre años')
        return original(*args, **kwargs)
    monkeypatch.setattr(tool, 'casos_del_anio', fail)
    before = (load.plini, load.qlini, load.scale0)
    report, rc = tool.ejecutar(app, plan)
    assert rc != 0 and len(report['anios']) == 1
    assert report['restitucion']['ok']
    assert (load.plini, load.qlini, load.scale0) == before
    assert app.GetActiveStudyCase() is source


@pytest.mark.parametrize('failure', ['save', 'insufficient_work', 'units', 'short_hash', 'year', 'nan_readback', 'restore'])
def test_fallos_de_persistencia_y_datos_no_se_confunden_con_aceptacion(anual, monkeypatch, tmp_path, failure):
    """072:RF-25, 072:RF-27, 072:RF-28 — persistencia, conservación y aceptación eléctrica se separan."""
    tool, app, plan, projection, source, load, transformer, works = anual
    if failure == 'save':
        monkeypatch.setattr(fake_pf.Escenario, 'Save', lambda self: 1)
    elif failure == 'insufficient_work':
        plan['obras_por_anio'] = [plan['obras_por_anio'][0]]
    elif failure == 'units':
        object.__setattr__(load, 'GetAttributeUnit', lambda a: 'kW')
    elif failure == 'short_hash':
        plan['corto_plazo']['evidencia']['sha256'] = 'b' * 64
    elif failure == 'year':
        projection['anio_base'] += 1
        plan['proyeccion_anual'] = _json(tmp_path / 'proyeccion.json', projection)
    elif failure == 'nan_readback':
        original = tool.resultados
        def nan(*args, **kwargs):
            result = original(*args, **kwargs)
            result['tensiones']['valores'][next(iter(result['tensiones']['valores']))] = float('nan')
            return result
        monkeypatch.setattr(tool, 'resultados', nan)
    elif failure == 'restore':
        original = tool.casos_del_anio
        def fail(*args, **kwargs):
            if args[2] == 6:
                object.__setattr__(source, 'Activate', lambda: 1)
                raise RuntimeError('caída y restauración fallida de prueba')
            return original(*args, **kwargs)
        monkeypatch.setattr(tool, 'casos_del_anio', fail)
    report, rc = tool.ejecutar(app, plan)
    assert rc != 0 and report.get('error')
    assert report['estado'] != 'completo'
    if failure == 'restore':
        assert report['estado'] == 'bloqueado_restitucion' and report['restitucion']['ok'] is False
    else:
        assert report['restitucion']['ok'] is True
        assert app.GetActiveStudyCase() is source


def test_demanda_por_fase_explica_cada_valor_y_no_modifica_origen(anual, tmp_path):
    """072:RF-24, 072:RF-27, 072:RF-28 — fases explícitas por año, sin repartir total ni cambiar i_sym."""
    tool, app, plan, projection, source, load, transformer, works = anual
    load.i_sym = 1
    load.phtech = '3PH PH-E'
    load.qlini = .003
    for phase, p in zip('rst', [.01, .02, .02]):
        setattr(load, f'plini{phase}', p)
        setattr(load, f'qlini{phase}', .001)
    object.__setattr__(load, 'GetAttributeUnit', lambda a: 'MW' if a.startswith('plini') else 'Mvar')
    before = {a: getattr(load, a) for a in ['i_sym', 'phtech', *[f'{v}{f}' for v in ('plini', 'qlini') for f in 'rst']]}
    for row in projection['filas']:
        row['fases'] = {phase: {'p_kw': row['p_kw'] * share, 'q_kvar': row['q_kvar'] * share}
                        for phase, share in zip('rst', [.2, .3, .5])}
    plan['proyeccion_anual'] = _json(tmp_path / 'proyeccion.json', projection)
    plan['obras_por_anio'] = []
    report, rc = tool.ejecutar(app, plan)
    assert rc == 0, report
    assert report['restitucion']['ok']
    assert before == {a: getattr(load, a) for a in before}
    cases = app.carpetas['study'].GetContents('*.IntCase', 1)
    for row in projection['filas']:
        case = next(c for c in cases if f'Año {row["anio"]:02d}' in tool.clave_pf(c) and c.loc_name == 'Con proyecto')
        case.Activate()
        for phase, value in row['fases'].items():
            assert getattr(load, f'plini{phase}') == pytest.approx(value['p_kw'] / 1000)
            assert getattr(load, f'qlini{phase}') == pytest.approx(value['q_kvar'] / 1000)
        assert load.i_sym == 1 and load.phtech == before['phtech']
    source.Activate()
    assert before == {a: getattr(load, a) for a in before}


@pytest.mark.parametrize('failure', ['missing_phase', 'inconsistent_sum', 'nan_phase'])
def test_perfil_por_fase_incompleto_se_bloquea_antes_de_escribir(anual, tmp_path, failure):
    """072:RF-24, 072:RF-28 — un total no se reparte para suplir la fase que falta."""
    tool, app, plan, projection, source, load, transformer, works = anual
    load.i_sym = 1
    for row in projection['filas']:
        row['fases'] = {f: {'p_kw': row['p_kw'] * share, 'q_kvar': row['q_kvar'] * share}
                        for f, share in zip('rst', [.2, .3, .5])}
    if failure == 'missing_phase':
        del projection['filas'][0]['fases']['t']
    elif failure == 'inconsistent_sum':
        projection['filas'][0]['fases']['r']['p_kw'] += 1
    else:
        projection['filas'][0]['fases']['r']['p_kw'] = float('nan')
    plan['proyeccion_anual'] = _json(tmp_path / 'proyeccion.json', projection)
    before = list(app.creados)
    report, rc = tool.ejecutar(app, plan)
    assert rc != 0 and report.get('error')
    assert app.creados == before and load.i_sym == 1


def test_demanda_absoluta_no_hereda_el_factor_de_flujo_del_corto_plazo(anual):
    """072:RF-24, 072:RF-27 — P/Q ya son absolutas; un factor antiguo no las vuelve a escalar."""
    tool, app, plan, projection, source, load, transformer, works = anual
    app.ldf.scLoadFac = 80.0
    report, rc = tool.ejecutar(app, plan)
    assert rc == 0 and app.ldf.scLoadFac == 80.0, report
    assert report['anios'][0]['antes']['problemas'][0]['valor'] > 130


def test_devuelve_el_caso_del_operador_aunque_no_sea_el_origen_corto(anual):
    """072:RF-27 — el caso del operador puede ser Sin proyecto; no se deja Con proyecto activo."""
    tool, app, plan, projection, source, load, transformer, works = anual
    initial = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == 'Sin proyecto')
    initial.Activate()
    before = (tool.clave_pf(app.GetActiveScenario()), load.plini, load.qlini, load.scale0, tool.clave_pf(transformer.typ_id))
    report, rc = tool.ejecutar(app, plan)
    assert rc == 0 and report['restitucion']['ok'], report
    assert app.GetActiveStudyCase() is initial
    assert before == (tool.clave_pf(app.GetActiveScenario()), load.plini, load.qlini, load.scale0, tool.clave_pf(transformer.typ_id))


def test_aceptacion_documental_no_cubre_corto_plazo_que_ya_incumple(anual):
    """072:RF-23, 072:RF-28 — una red modificada tras aceptarse no se toma como corto plazo resuelto."""
    tool, app, plan, projection, source, load, transformer, works = anual
    load.plini = 1.0
    before = list(app.creados)
    report, rc = tool.ejecutar(app, plan)
    assert rc != 0 and 'corto plazo' in report['error']
    assert report['anios'] == [] and app.creados == before
    assert report['restitucion']['ok'] and load.plini == 1.0
