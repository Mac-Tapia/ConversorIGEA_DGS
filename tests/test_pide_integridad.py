"""072:RF-23 a RF-28: fallos de la revisión independiente del PIDE anual."""
import copy
import math
from pathlib import Path
from types import SimpleNamespace

import fake_pf
import pytest

from test_pide_anual import anual, _json
from test_pide_anual_web import raw, api, fuentes


def _fases_corto(load):
    """Datos explícitos del doble local: solo r demanda, s/t cero son legítimas."""
    object.__setattr__(load, 'i_sym', 1)
    for fase in 'rst':
        object.__setattr__(load, f'plini{fase}', load.plini if fase == 'r' else 0.0)
        object.__setattr__(load, f'qlini{fase}', load.qlini if fase == 'r' else 0.0)
    object.__setattr__(load, 'GetAttributeUnit', lambda a: 'Mvar' if a.startswith('qlini') else 'MW')


@pytest.mark.parametrize('recorrido', ['medida', 'anual'])
def test_barra_retirada_no_se_acepta_con_resultados_finitos_almacenados(anual, monkeypatch, recorrido):
    """072:RF-25/28: el estado físico del terminal prevalece sobre medidas antiguas válidas."""
    tool, app, plan, _perfil, _origen, load, *_ = anual
    object.__setattr__(load.bus1.cterm, 'outserv', 1)
    copias = []
    copiar = tool.casos_del_anio
    def copia(*a, **kw):
        copias.append(1)
        return copiar(*a, **kw)
    monkeypatch.setattr(tool, 'casos_del_anio', copia)
    if recorrido == 'medida':
        medida = tool._medida_anual(app, app.proyecto, plan, {}, cargas={tool.clave_pf(load): (load, 'Red_A')})
        assert medida['converge'] and not medida['cumple'], medida
        assert any(p['causa'] == 'conexion_fuera_de_servicio' for p in medida['problemas'])
    else:
        report, rc = tool.ejecutar(app, plan)
        assert rc != 0 and report['estado'] != 'completo', report
        assert not report['corto_plazo']['cumple'] and not report['anios'], report
        assert report['restitucion']['ok'], report
    assert not copias


@pytest.mark.parametrize('atributo,valor', [
    (a, v) for a in ('plini', 'qlini', 'scale0', 'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit')
    for v in (float('nan'), float('inf'), None) if v is not None or a not in ('plini', 'qlini', 'scale0')])
def test_corto_por_fases_rechaza_cada_entrada_no_finita_antes_del_flujo(anual, monkeypatch, atributo, valor):
    """072:RF-24/28: sin filas anuales también se verifican las seis entradas por fase."""
    tool, app, plan, _perfil, _origen, load, *_ = anual
    _fases_corto(load)
    if atributo in ('plini', 'qlini', 'scale0'):
        setattr(load, atributo, valor)
    else:
        object.__setattr__(load, atributo, valor)
    flujos = []
    monkeypatch.setattr(tool, 'flujo_de_carga', lambda *_a, **_kw: flujos.append(1) or {'converged': True})
    with pytest.raises(tool.PideError, match='demanda|fase'):
        tool._medida_anual(app, app.proyecto, plan, {}, por_fase=True, demanda_absoluta=False,
                          cargas={tool.clave_pf(load): (load, 'Red_A')})
    assert not flujos


@pytest.mark.parametrize('atributo', ['plini', 'qlini', 'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit'])
def test_corto_sin_filas_verifica_unidad_de_cada_entrada(anual, monkeypatch, atributo):
    """072:RF-24/28: un valor finito no autoriza interpretar kW como MW ni fases sin unidad."""
    tool, app, plan, _perfil, _origen, load, *_ = anual
    _fases_corto(load)
    unidad = load.GetAttributeUnit
    object.__setattr__(load, 'GetAttributeUnit', lambda a: '' if a == atributo else unidad(a))
    flujos = []
    monkeypatch.setattr(tool, 'flujo_de_carga', lambda *_a, **_kw: flujos.append(1) or {'converged': True})
    with pytest.raises(tool.PideError, match='unidades'):
        tool._medida_anual(app, app.proyecto, plan, {}, por_fase=True, demanda_absoluta=False,
                          cargas={tool.clave_pf(load): (load, 'Red_A')})
    assert not flujos


@pytest.mark.parametrize('invalida', [True, False])
def test_ciclo_valida_fases_del_corto_antes_de_copias_y_conserva_ceros(anual, tmp_path, monkeypatch, invalida):
    """072:RF-24/25/27/28: proyección futura correcta no subsana un corto con fase NaN."""
    tool, app, plan, perfil, _origen, load, *_ = anual
    _fases_corto(load)
    if invalida:
        object.__setattr__(load, 'plinir', float('nan'))
    for indice, fila in enumerate(perfil['filas'], 1):
        # La fase r aislada debe caber físicamente en el trafo corto del doble;
        # 200 kW en una fase incumplirían aunque sus ceros s/t sean legítimos.
        fila['p_kw'], fila['q_kvar'] = 20.0 * indice, 0.0
        fila['fases'] = {f: {'p_kw': fila['p_kw'] if f == 'r' else 0.0,
                             'q_kvar': fila['q_kvar'] if f == 'r' else 0.0} for f in 'rst'}
    plan['proyeccion_anual'] = _json(tmp_path / 'fases_segunda_revision.json', perfil)
    flujos, copias, demandas = [], [], []
    flujo, copiar, demanda = tool.flujo_de_carga, tool.casos_del_anio, tool._demanda_del_anio
    def calcular(*a, **kw):
        flujos.append(1)
        return flujo(*a, **kw)
    def copia(*a, **kw):
        copias.append(1)
        return copiar(*a, **kw)
    def escribir(*a, **kw):
        demandas.append(1)
        return demanda(*a, **kw)
    monkeypatch.setattr(tool, 'flujo_de_carga', calcular)
    monkeypatch.setattr(tool, 'casos_del_anio', copia)
    monkeypatch.setattr(tool, '_demanda_del_anio', escribir)
    report, rc = tool.ejecutar(app, plan)
    if invalida:
        assert rc != 0 and report['estado'] != 'completo', report
        assert not flujos and not copias and not demandas and not report['anios'], report
        assert 'corto_plazo' not in report, report
        assert math.isnan(load.plinir)  # se conserva el dato inválido, no se sustituye por cero
    else:
        assert rc == 0, report.get('error')
        assert report['estado'] == 'completo' and report['restitucion']['ok'], report
        assert report['corto_plazo']['cumple'] and len(report['anios']) == 3
        assert load.plinis == 0 and load.plinit == 0 and load.qlinis == 0 and load.qlinit == 0


@pytest.mark.parametrize('frontera', ['lectura', 'demanda'])
def test_cancelacion_durante_lectura_interior_impide_el_flujo_corto(anual, monkeypatch, frontera):
    """072:RF-27: una lectura terminada con cancelación no autoriza iniciar el motor."""
    import threading
    tool, app, plan, *_ = anual
    evento = threading.Event()
    leer = tool.leer_proyeccion_anual
    lecturas, flujos = [], []
    def lectura(*a, **kw):
        resultado = leer(*a, **kw)
        lecturas.append(1)
        if len(lecturas) == 2 and frontera == 'lectura':
            evento.set()
        return resultado
    comprobar = tool._comprobar_demanda_anual
    def demanda(*a, **kw):
        resultado = comprobar(*a, **kw)
        if frontera == 'demanda':
            evento.set()
        return resultado
    flujo = tool.flujo_de_carga
    def calcular(*a, **kw):
        flujos.append(evento.is_set())
        return flujo(*a, **kw)
    monkeypatch.setattr(tool, 'leer_proyeccion_anual', lectura)
    monkeypatch.setattr(tool, '_comprobar_demanda_anual', demanda)
    monkeypatch.setattr(tool, 'flujo_de_carga', calcular)
    report, rc = tool.ejecutar(app, plan, cancelado=evento.is_set)
    assert len(lecturas) == 2
    assert not flujos, 'se inició el flujo con cancelación conocida'
    assert rc == 0 and report['estado'] == 'cancelado' and report['restitucion']['ok'], report
    assert not report['anios']


@pytest.mark.parametrize('fallo', ['caso_rc', 'caso_falso', 'esc_rc', 'esc_falso',
    'copy_caso_none', 'copy_caso_origen', 'copy_esc_none', 'copy_esc_origen',
    'copy_caso_ajeno', 'copy_esc_ajeno', 'esc_deactivar', 'save'])
def test_fallo_de_creacion_nunca_guarda_la_demanda_anual_en_el_original(anual, monkeypatch, fallo):
    """072:RF-23, 072:RF-27, 072:RF-28: el original de 50 kW no recibe ni un Save anual."""
    tool, app, plan, _perfil, origen, load, _trafo, _obras = anual
    escenario_original = app.GetActiveScenario()
    datos_originales = copy.deepcopy(escenario_original._datos)
    desc_original = getattr(origen, 'desc', None)
    guardados = []
    provocados = []
    guardar = fake_pf.Escenario.Save
    def save(self):
        guardados.append((self, load.plini))
        if fallo == 'save' and 'PIDE' in tool.clave_pf(self):
            provocados.append(self)
            return 1
        return guardar(self)
    monkeypatch.setattr(fake_pf.Escenario, 'Save', save)
    if fallo == 'esc_deactivar':
        desactivar = fake_pf.Escenario.Deactivate
        def deactivate(self, *a):
            if 'PIDE' in tool.clave_pf(app.GetActiveStudyCase()):
                provocados.append(self)
                return 1
            return desactivar(self, *a)
        monkeypatch.setattr(fake_pf.Escenario, 'Deactivate', deactivate)
    elif fallo.startswith(('caso_', 'esc_')):
        clase = fake_pf.Caso if fallo.startswith('caso_') else fake_pf.Escenario
        activar = clase.Activate
        intentos = []
        def activate(self, *a):
            if 'PIDE' in tool.clave_pf(self) and not intentos:
                intentos.append(self)
                provocados.append(self)
                return 0 if fallo.endswith('falso') else 1
            return activar(self, *a)
        monkeypatch.setattr(clase, 'Activate', activate)
    elif fallo.startswith('copy_'):
        copiar = fake_pf.Obj.AddCopy
        clase = 'IntCase' if 'caso' in fallo else 'IntScenario'
        def addcopy(self, obj, *a):
            if 'PIDE' in tool.clave_pf(self) and obj.GetClassName() == clase:
                provocados.append(obj)
                if fallo.endswith('ajeno'):
                    ajeno = fake_pf.Obj(app, 'IntPrj', 'Proyecto_ajeno', app.usuario)
                    return ajeno.CreateObject(clase, 'Sin proyecto')
                return None if fallo.endswith('none') else obj
            return copiar(self, obj, *a)
        monkeypatch.setattr(fake_pf.Obj, 'AddCopy', addcopy)
    report, rc = tool.ejecutar(app, plan)
    assert provocados, report
    assert not [(s, p) for s, p in guardados if s is escenario_original], guardados
    assert escenario_original._datos == datos_originales
    assert getattr(origen, 'desc', None) == desc_original
    assert load.plini == .05
    assert rc != 0 and report['estado'] != 'completo', report
    assert report['restitucion']['ok'], report


def _solo_quinto(tool, plan, perfil, tmp_path):
    plan['anio_fin'] = 5
    perfil['filas'] = perfil['filas'][:1]
    plan['proyeccion_anual'] = _json(tmp_path / 'perfil_quinto.json', perfil)
    plan['obras_por_anio'] = plan['obras_por_anio'][:1]


@pytest.mark.parametrize('fallo', ['outserv', 'escala', 'p', 'fase', 'sin_consumo_p', 'sin_consumo_q', 'sin_barra'])
def test_obra_no_puede_suplir_la_proyeccion_retirando_servicio_o_cambiando_demanda(anual, tmp_path, monkeypatch, fallo):
    """072:RF-24, 072:RF-25, 072:RF-28: convergencia con menos servicio no es solución."""
    tool, app, plan, perfil, _origen, load, _trafo, obras = anual
    _solo_quinto(tool, plan, perfil, tmp_path)
    original = (load.plini, load.qlini, load.scale0, load.i_sym, load.bus1, getattr(load, 'outserv', 0))
    if fallo in ('outserv', 'fase', 'sin_barra'):
        atributo, valor = {'outserv': ('outserv', 1), 'fase': ('i_sym', 1), 'sin_barra': ('bus1', None)}[fallo]
        variacion = fake_pf.variacion_del_operador(app, 'Obra_incompatible', [(load, atributo, valor)])
        variacion.Deactivate()
        plan['obras_por_anio'].append({'anio': 5, 'variacion': tool.clave_pf(variacion)})
    activar = obras[1].Activate
    activaciones = []
    def activate(*a):
        rc = activar(*a)
        activaciones.append(1)
        if fallo in ('escala', 'p'):
            attr, valor = {'escala': ('scale0', .1), 'p': ('plini', .02)}[fallo]
            setattr(load, attr, valor)
        return rc
    monkeypatch.setattr(obras[1], 'Activate', activate)
    flujo = tool.flujo_de_carga
    def calcular(*a, **kw):
        result = flujo(*a, **kw)
        if obras[1] in app.GetActiveNetworkVariations() and fallo.startswith('sin_consumo'):
            object.__setattr__(load, 'm_Psum:bus1' if fallo.endswith('_p') else 'm_Qsum:bus1', 0.0)
        return result
    monkeypatch.setattr(tool, 'flujo_de_carga', calcular)
    report, rc = tool.ejecutar(app, plan)
    assert activaciones, report
    assert rc != 0 and report['estado'] != 'completo', report
    assert report.get('error'), report
    assert (load.plini, load.qlini, load.scale0, load.i_sym, load.bus1, getattr(load, 'outserv', 0)) == original
    assert report['restitucion']['ok'], report


@pytest.mark.parametrize('faltante', ['loading', 'tension', 'grupo_loading', 'unidad'])
def test_medidas_parciales_no_cubren_el_inventario_fisico(anual, monkeypatch, faltante):
    """072:RF-25, 072:RF-28: un mapa no vacío tampoco acredita los elementos omitidos."""
    tool, app, plan, _perfil, _origen, _load, _trafo, _obras = anual
    lector = tool.resultados
    numero = lector.__globals__['_num']
    def leer(obj, attr):
        if (faltante == 'loading' and attr == 'c:loading') or (
                faltante == 'tension' and attr == 'm:u' and (numero(obj, 'uknom') or 0) < 1):
            return None
        return numero(obj, attr)
    monkeypatch.setitem(lector.__globals__, '_num', leer)
    def resultado(*a, **kw):
        value = lector(*a, **kw)
        if faltante == 'grupo_loading':
            value['cargabilidad']['valores']['transformadores'] = {}
        if faltante == 'unidad':
            value['tensiones']['unidad'] = 'kV'
        return value
    monkeypatch.setattr(tool, 'resultados', resultado)
    report, rc = tool.ejecutar(app, plan)
    assert rc != 0 and report['estado'] != 'completo', report


def test_cancelar_despues_de_demanda_no_inicia_el_flujo_siguiente(anual, monkeypatch):
    """072:RF-27: una llamada terminada no autoriza otra etapa tras pedir cancelar."""
    tool, app, plan, *_ = anual
    escribir, medir = tool._demanda_del_anio, tool._medida_anual
    cancelar = False
    def demanda(*a, **kw):
        nonlocal cancelar
        out = escribir(*a, **kw)
        if a[7] == 'con':
            cancelar = True
        return out
    def medida(*a, **kw):
        assert not cancelar, 'se inició otro flujo con la cancelación pedida'
        return medir(*a, **kw)
    monkeypatch.setattr(tool, '_demanda_del_anio', demanda)
    monkeypatch.setattr(tool, '_medida_anual', medida)
    report, rc = tool.ejecutar(app, plan, cancelado=lambda: cancelar)
    assert rc == 0 and report['estado'] == 'cancelado', report
    assert report['restitucion']['ok'] and not report['anios'], report


@pytest.mark.parametrize('fallo', ['evaluacion', 'perfil', 'procedencia', 'publicacion'])
def test_fallo_de_custodia_no_publica_token_parcial_ni_abandona_copias(tmp_path, monkeypatch, fallo):
    """072:RF-24, 072:RF-28: custodia completa o ninguna, incluidos IO/rename fallidos."""
    import hashlib
    from convertersmartgrid.web import services
    for nombre in ('RUNTIME', 'CACHE', 'TEMP'):
        monkeypatch.setenv(f'CSG_{nombre}_HOME', str(tmp_path / nombre.lower()))
    ws = SimpleNamespace(plans_dir=tmp_path / 'planes')
    evaluacion = raw({'estado': 'aceptado'})
    perfil = raw({'evaluacion': {'ruta': 'Z:/NO_ABRIR.json', 'sha256': hashlib.sha256(evaluacion).hexdigest()}})
    corto = raw({'estado': 'aceptado', 'caso': 'P/C.IntCase', 'escenario': 'P/E.IntScenario',
                 'anio': 4, 'anio_base': 2030, 'variaciones': []})
    write, write_text, rename = Path.write_bytes, Path.write_text, Path.rename
    def escribir(path, value):
        if path.name == f'{fallo}.json':
            raise OSError('disco de prueba no disponible')
        return write(path, value)
    def texto(path, value, *a, **kw):
        if path.name == f'{fallo}.json':
            raise OSError('disco de prueba no disponible')
        return write_text(path, value, *a, **kw)
    def publicar(path, target):
        if fallo == 'publicacion' and Path(target).parent.name == 'pide_fuentes':
            raise OSError('rename de prueba no disponible')
        return rename(path, target)
    monkeypatch.setattr(Path, 'write_bytes', escribir)
    monkeypatch.setattr(Path, 'write_text', texto)
    monkeypatch.setattr(Path, 'rename', publicar)
    with pytest.raises((OSError, services.UserError)):
        services.pide_custodiar_fuentes(ws, perfil, evaluacion, corto)
    assert not list((ws.plans_dir / 'pide_fuentes').glob('*'))
    assert not [p for p in tmp_path.rglob('*.json') if p.name != 'owner.json']


def test_maniobra_por_ruta_alternativa_conserva_el_servicio_y_el_perfil(anual, tmp_path):
    """072:RF-25, 072:RF-26: abrir una ruta es admisible cuando otra sigue sirviendo las cargas."""
    tool, app, plan, perfil, origen, load, _trafo, _obras = anual
    _solo_quinto(tool, plan, perfil, tmp_path)
    linea = app.proyecto.GetContents('*.ElmLne', 1)[0]
    grabando = app.grabando
    app.grabando = None
    # La ruta maniobrada es posterior al medidor: su cabecera sigue siendo
    # la misma y el lector común puede recorrer ambas rutas alternativas.
    cabecera = linea.bus1.cterm.GetParent().CreateObject('ElmTerm', 'Cabecera_maniobra')
    cabecera.uknom = linea.bus1.cterm.uknom
    estable = linea.GetParent().CreateObject('ElmLne', 'Salida_del_medidor')
    estable.typ_id, estable.nlnum, estable.outserv, estable.dline = linea.typ_id, 1, 0, .1
    object.__setattr__(estable, 'c:loading', 10.0)
    for lado, barra in enumerate((cabecera, linea.bus1.cterm), 1):
        cub = barra.CreateObject('StaCubic', f'medidor_{lado}')
        cub.obj_id, cub.obj_bus = estable, lado - 1
        setattr(estable, f'bus{lado}', cub)
    feeder = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    feeder.obj_id = estable.bus1
    feeder._objs.extend([estable, cabecera])
    alternativa = linea.GetParent().CreateObject('ElmLne', 'Ruta_alternativa')
    alternativa.typ_id, alternativa.nlnum, alternativa.outserv, alternativa.dline = linea.typ_id, 1, 1, linea.dline
    object.__setattr__(alternativa, 'c:loading', 10.0)
    for lado in (1, 2):
        barra = getattr(linea, f'bus{lado}').cterm
        cub = barra.CreateObject('StaCubic', f'alterna_{lado}')
        cub.obj_id, cub.obj_bus = alternativa, lado - 1
        setattr(alternativa, f'bus{lado}', cub)
    feeder._objs.append(alternativa)
    app.grabando = grabando
    maniobra = fake_pf.variacion_del_operador(app, 'Ruta_que_sigue_sirviendo',
        [(linea, 'outserv', 1), (alternativa, 'outserv', 0)])
    maniobra.Deactivate()
    app.topologia_viva = True
    plan['obras_por_anio'].append({'anio': 5, 'variacion': tool.clave_pf(maniobra)})
    report, rc = tool.ejecutar(app, plan)
    assert rc == 0 and report['estado'] == 'completo' and report['restitucion']['ok'], report
    assert linea.outserv == 0 and alternativa.outserv == 1
    caso = next(c for c in app.proyecto.GetContents('*.IntCase', 1)
                if 'Año 05' in tool.clave_pf(c) and c.loc_name == 'Con proyecto')
    caso.Activate()
    assert linea.outserv == 1 and alternativa.outserv == 0
    assert load.plini == .2 and load.scale0 == 1 and not getattr(load, 'outserv', 0)
    assert load.bus1.cterm.IsEnergized() == 1
    origen.Activate()


def test_grupo_de_transformadores_vacio_es_valido_solo_sin_esa_clase(anual):
    """072:RF-28: la ausencia física de una clase se distingue de sus medidas ausentes."""
    tool, _app, plan, *_ = anual
    app = fake_pf.proyecto(alimentadores=('Red_A',), cargas_por_alim=1, con_trafos=False, bt=True, flujo=True)
    app.proyecto.Activate()
    for linea in app.proyecto.GetContents('*.ElmLne', 1):
        object.__setattr__(linea, 'c:loading', 10.0)
    load = app.proyecto.GetContents('*.ElmLod', 1)[0]
    object.__setattr__(load, 'GetAttributeUnit', lambda a: {'plini': 'MW', 'qlini': 'Mvar'}[a])
    assert not app.proyecto.GetContents('*.ElmTr2', 1)
    result = tool._medida_anual(app, app.proyecto, plan, {}, cargas={tool.clave_pf(load): (load, 'Red_A')})
    assert result['converge'] and result['cumple'], result


@pytest.mark.parametrize('valor', [0.0, None])
def test_fase_requerida_sin_tension_o_medida_no_puede_aceptarse(anual, tmp_path, monkeypatch, valor):
    """072:RF-24, 072:RF-28: consumo total no encubre una fase prevista no servida."""
    tool, app, plan, perfil, _origen, load, *_ = anual
    _solo_quinto(tool, plan, perfil, tmp_path)
    plan['obras_por_anio'] = []
    load.i_sym = 1
    load.phtech = '3PH PH-E'
    load.qlini = .003
    for fase, p in zip('rst', [.01, .02, .02]):
        setattr(load, f'plini{fase}', p)
        setattr(load, f'qlini{fase}', .001)
    object.__setattr__(load, 'GetAttributeUnit', lambda a: 'MW' if a.startswith('plini') else 'Mvar')
    for fila in perfil['filas']:
        fila['fases'] = {f: {'p_kw': fila['p_kw'] * parte, 'q_kvar': fila['q_kvar'] * parte}
                         for f, parte in zip('rst', [.2, .3, .5])}
    plan['proyeccion_anual'] = _json(tmp_path / 'fases.json', perfil)
    flujo = tool.flujo_de_carga
    def calcular(*a, **kw):
        out = flujo(*a, **kw)
        if 'Año 05' in tool.clave_pf(app.GetActiveStudyCase()):
            object.__setattr__(load.bus1.cterm, 'm_u:A', valor)
        return out
    monkeypatch.setattr(tool, 'flujo_de_carga', calcular)
    report, rc = tool.ejecutar(app, plan)
    assert rc != 0 and report['estado'] != 'completo', report
    assert report['restitucion']['ok'], report


def test_fallo_publicacion_web_informa_y_conserva_custodia_anterior(api, monkeypatch):
    """072:RF-24, 072:RF-28: un upload fallido no publica ni afecta el token previo."""
    c, wid = api
    aceptada = fuentes(c, wid)
    assert aceptada.status_code == 200
    carpeta = Path(aceptada.json()['proyeccion_anual']['ruta']).parent
    antes = {p.name: p.read_bytes() for p in carpeta.iterdir()}
    rename = Path.rename
    def fallar(stage, target):
        if Path(target).parent == carpeta.parent:
            assert not Path(target).exists()
            assert {p.name for p in stage.iterdir()} == set(antes)
            raise OSError('disco no disponible al publicar el token')
        return rename(stage, target)
    monkeypatch.setattr(Path, 'rename', fallar)
    fallida = fuentes(c, wid)
    assert fallida.status_code == 422 and 'publicar' in fallida.json()['detail']
    assert list(carpeta.parent.iterdir()) == [carpeta]
    assert antes == {p.name: p.read_bytes() for p in carpeta.iterdir()}


@pytest.mark.parametrize('atributo', ['plini', 'qlini', 'scale0'])
def test_demanda_nativa_no_finita_se_bloquea_antes_de_otro_flujo(anual, tmp_path, monkeypatch, atributo):
    """072:RF-24, 072:RF-28: NaN no satisface la comparación de P/Q por una resta NaN."""
    tool, app, plan, perfil, _origen, load, _trafo, obras = anual
    _solo_quinto(tool, plan, perfil, tmp_path)
    activar, flujo = obras[1].Activate, tool.flujo_de_carga
    llamadas_no_validas = []
    def activate(*a):
        rc = activar(*a)
        setattr(load, atributo, float('nan'))
        return rc
    def calcular(*a, **kw):
        if not math.isfinite(getattr(load, atributo)):
            llamadas_no_validas.append(1)
        return flujo(*a, **kw)
    monkeypatch.setattr(obras[1], 'Activate', activate)
    monkeypatch.setattr(tool, 'flujo_de_carga', calcular)
    report, rc = tool.ejecutar(app, plan)
    assert not llamadas_no_validas
    assert rc != 0 and report['estado'] != 'completo' and report['restitucion']['ok'], report


@pytest.mark.parametrize('publicar', [False, True])
def test_fallo_del_recibo_temporal_no_abandona_payload_ni_oculta_publicacion(tmp_path, monkeypatch, publicar):
    """072:RF-24, 072:RF-28: disco fallido también al cerrar staging; verdad de publicación conservada."""
    import hashlib
    from convertersmartgrid.web import services
    for nombre in ('RUNTIME', 'CACHE', 'TEMP'):
        monkeypatch.setenv(f'CSG_{nombre}_HOME', str(tmp_path / nombre.lower()))
    ws = SimpleNamespace(plans_dir=tmp_path / 'planes')
    evaluacion = raw({'estado': 'aceptado'})
    perfil = raw({'evaluacion': {'ruta': 'Z:/NO_ABRIR.json', 'sha256': hashlib.sha256(evaluacion).hexdigest()}})
    corto = raw({'estado': 'aceptado', 'caso': 'P/C.IntCase', 'escenario': 'P/E.IntScenario',
                 'anio': 4, 'anio_base': 2030, 'variaciones': []})
    write, text = Path.write_bytes, Path.write_text
    def bytes_io(path, value):
        if not publicar and path.name == 'evaluacion.json':
            raise OSError('fallo de payload')
        return write(path, value)
    def text_io(path, value, *a, **kw):
        if path.name == 'owner.json' and '"estado": "terminado"' in value:
            raise OSError('fallo del recibo de cierre de staging')
        return text(path, value, *a, **kw)
    monkeypatch.setattr(Path, 'write_bytes', bytes_io)
    monkeypatch.setattr(Path, 'write_text', text_io)
    if publicar:
        referencia = services.pide_custodiar_fuentes(ws, perfil, evaluacion, corto)
        assert Path(referencia['proyeccion_anual']['ruta']).is_file()
    else:
        with pytest.raises(services.UserError):
            services.pide_custodiar_fuentes(ws, perfil, evaluacion, corto)
        assert not list((ws.plans_dir / 'pide_fuentes').glob('*'))
    assert not [p for p in (tmp_path / 'runtime').rglob('*.json') if p.name != 'owner.json']
