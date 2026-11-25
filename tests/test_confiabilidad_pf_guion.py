"""Spec 012, T7 y T8: ``tools/confiabilidad_pf.py`` contra ``fake_pf``.

T7 (``-k datos``): el libro de la empresa en la variación «Datos de confiabilidad».
T8: ``ComRel3`` y ``ComOpri`` desde ``tools/estudios_pf.py``. Proyectos, equipos y libros
sorteados; ninguna cifra de una empresa. La prueba real la hace el usuario (T13).
"""

from __future__ import annotations

import random

import pytest

import fake_pf
from apoyo import cargar_herramienta, contexto_nativo
from convertersmartgrid.aplicacion import datos_empresa as de

casos_pf = cargar_herramienta('casos_pf.py', 'casos_012', tools_en_path=True)
conf = cargar_herramienta('confiabilidad_pf.py', 'confiabilidad_012', tools_en_path=True)
estudios = cargar_herramienta('estudios_pf.py', 'estudios_012', tools_en_path=True)

SEMILLAS = (4, 23, 58, 91)
#: Clase del export de cada equipo sorteado y su ``aUsage`` en el DGS (011:RF-128).
USO = {'BREAKER': 'cbk', 'RECLOSER': 'cbk', 'FUSE': 'cbk', 'SWITCH': 'dct'}


def _alim(app, f):
    return next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == f)


def _red(rng, *, sin_cabecera=()):
    """Proyecto con casos preparados, equipos de maniobra sorteados en cada tramo y el
    acoplador interno de una SED; ``sin_cabecera``: alimentadores sin fuente (RF-71)."""
    alims = tuple(f'F{i}' for i in range(1, rng.randint(2, 3) + 1))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=rng.randint(2, 4), bt=True, flujo=True)
    clases = {}
    for f in alims:
        elm = _alim(app, f)
        for ln in elm.GetObjs('ElmLne'):
            # En el extremo lejano del tramo: el cubículo de cabecera queda sin interruptor (RF-69).
            cub = [c for b in elm.GetObjs('ElmTerm') for c in b.GetContents('*.StaCubic')
                   if c.obj_id is ln][-1]
            clase = rng.choice(list(USO))
            sw = cub.CreateObject('StaSwitch', f'EQ_{ln.loc_name}')
            sw.aUsage, sw.on_off = USO[clase], 1
            sw.mejora_ens = rng.uniform(0.1, 5)
            elm._objs.append(sw)
            clases[sw.loc_name] = clase
        sub = next(o for o in elm.GetObjs('ElmSubstat'))
        coup = sub.CreateObject('ElmCoup', f'SW_{sub.loc_name}')
        coup.aUsage, coup.on_off, coup.mejora_ens = 'cbk', 1, 99.0
        elm._objs.append(coup)
        for c in elm.GetObjs('ElmLod'):
            c.NrCust = rng.randint(2, 300)
        if f in sin_cabecera:
            elm.obj_id = None
            elm.sin_tension = 1
    base = {'variaciones': [], 'feeders': list(alims), 'excluidos': [],
            'ajustes': [{'feeder': f, 'cuadrado': True} for f in alims]}
    informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': list(alims), 'base': base,
                                              'caso_base_sin_verificar': {}})
    assert codigo == 0, informe
    app.atributos_en_variacion = True
    app.escrituras.clear()
    return app, list(alims), clases


def _libro(rng, *, cero=False, clases=tuple(de.CLASES), tipos=()):
    def x():
        return 0.0 if cero else round(rng.uniform(0.01, 2), 4)

    return de.Libro(nombre='libro.xlsx',
                    tasas={c: de.Tasa(c, x(), None, round(rng.uniform(0.5, 8), 2)) for c in clases},
                    tasas_por_tipo={t: de.Tasa('linea', x(), None, 3.0, t) for t in tipos},
                    tiempos_min={'localizacion': rng.uniform(5, 60), 'manual': rng.uniform(5, 60),
                                 'telemandada': rng.uniform(0.5, 3)})


def _plan(feeders, libro, clases, **extra):
    return {'project': 'P', 'feeders': list(feeders), 'libro': libro.a_dict(), 'clases_equipo': clases,
            'native_action_context': contexto_nativo('P', list(feeders), 'confiabilidad'), **extra}


def _plan_estudio(feeders, estudio, caso='sin', **extra):
    return {'project': 'P', 'feeders': list(feeders), 'estudio': estudio, 'caso': caso,
            'stamp': '20261029_120000',
            'native_action_context': contexto_nativo('P', list(feeders), 'estudios'), **extra}


def _activas(app, rol):
    caso = casos_pf.casos_del_proyecto(app)[rol]
    caso.Activate()
    return {v.loc_name for v in app.GetActiveNetworkVariations()}


def _aplicado(rng, **kw):
    app, alims, clases = _red(rng, **kw)
    informe, rc = conf.aplicar_datos(app, _plan(alims, _libro(rng), clases))
    assert rc == 0, informe
    return app, alims, clases


# =========================================================================== T7: datos
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_datos_en_su_variacion_solo_en_sin_y_con_proyecto(semilla):
    """012:RF-20, 012:RF-21, 012:RF-22 — los modelos se asignan a los elementos dentro de
    «Datos de confiabilidad», activa en «Sin proyecto» y «Con proyecto» y no en el «Caso
    base»; ningún tipo existente cambia; el informe nombra el libro."""
    rng = random.Random(semilla)
    app, alims, clases = _red(rng)
    informe, rc = conf.aplicar_datos(app, _plan(alims, _libro(rng), clases))
    assert rc == 0, informe
    assert informe['libro'] == 'libro.xlsx' and informe['variacion'] == conf.VARIACION
    assert conf.VARIACION in _activas(app, 'sin') and conf.VARIACION in _activas(app, 'con')
    assert conf.VARIACION not in _activas(app, 'base')
    assert not any(o.GetClassName().startswith('Typ') for o, *_ in app.escrituras)       # RF-22
    _activas(app, 'sin')
    for f in alims:
        elm = _alim(app, f)
        assert all(getattr(o, 'pStoch', None) is not None for o in elm.GetObjs('ElmLne') + elm.GetObjs('ElmTr2'))
    _activas(app, 'base')
    assert all(getattr(ln, 'pStoch', None) is None for f in alims for ln in _alim(app, f).GetObjs('ElmLne'))


def test_datos_por_tipo_y_por_km():
    """012:RF-9, 012:RF-11, 012:RF-8 — una línea de un tipo con fila propia lleva ese modelo;
    las demás, el de su clase; la tasa va por km tal cual, sin multiplicar por la longitud."""
    rng = random.Random(8)
    app, alims, clases = _red(rng)
    tipo = _alim(app, alims[0]).GetObjs('ElmLne')[0].typ_id.loc_name
    libro = _libro(rng, tipos=(tipo,))
    informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    assert rc == 0, informe
    _activas(app, 'sin')
    ln0 = _alim(app, alims[0]).GetObjs('ElmLne')[0]
    ln1 = _alim(app, alims[1]).GetObjs('ElmLne')[0]
    assert ln0.pStoch.loc_name == f'{conf.PREFIJO_MODELO}tipo_{tipo}'
    assert ln0.pStoch.DnFr == libro.tasas_por_tipo[tipo].permanente
    assert ln1.pStoch.loc_name == f'{conf.PREFIJO_MODELO}linea'
    assert ln1.pStoch.DnFr == libro.tasas['linea'].permanente


def test_datos_clase_sin_fallas_va_sin_modelo_y_se_dice():
    """012:RF-93 — una clase que el histórico deja sin fallas (λ = 0, reparación 0) no lleva modelo: DIgSILENT rechaza
    un tiempo de reparación de 0 y antes se caía todo el libro («setting attribute 'RepMu' … failed», 2026-11-20)."""
    import dataclasses

    rng = random.Random(77)
    app, alims, clases = _red(rng)
    libro = _libro(rng)
    libro.tasas['barra'] = dataclasses.replace(libro.tasas['barra'], permanente=0.0, reparacion_h=0.0)
    try:
        informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    except AttributeError as exc:            # el rechazo de DIgSILENT: la prueba falla por su aserción, con el motivo
        informe, rc = {'error': str(exc)}, 1
    assert rc == 0, informe
    modelos = {o.loc_name for o in conf._carpeta_modelos(app).GetContents('*')}
    assert f'{conf.PREFIJO_MODELO}barra' not in modelos
    assert {f'{conf.PREFIJO_MODELO}linea', f'{conf.PREFIJO_MODELO}transformador'} <= modelos
    assert informe['sin_modelo'] == ['barra']
    assert any('Sin modelo de falla' in a and 'barra' in a for a in informe['avisos'])
    for f in alims:
        assert informe['alimentadores'][f]['asignados']['barra'] == 0


def test_datos_maniobra_manual_cero_va_al_minimo_y_se_dice():
    """012:RF-94 — el histórico deja la maniobra manual en 0 cuando no separa localización y maniobra; DIgSILENT
    rechaza Tswitch = 0 en un ElmCoup («setting attribute 'Tswitch' … failed», 2026-11-20): va al mínimo, con su
    aviso."""
    import dataclasses

    rng = random.Random(78)
    app, alims, clases = _red(rng)
    libro = _libro(rng)
    libro = dataclasses.replace(libro, tiempos_min={**libro.tiempos_min, 'manual': 0.0})
    try:
        informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    except AttributeError as exc:            # el rechazo de DIgSILENT: la prueba falla por su aserción, con el motivo
        informe, rc = {'error': str(exc)}, 1
    assert rc == 0, informe
    _activas(app, 'sin')                      # lo escrito está en «Datos de confiabilidad», activa en «Sin proyecto»
    for f in alims:
        coup = next(o for o in _alim(app, f).GetObjs('ElmCoup'))
        assert coup.Tswitch == conf.TSWITCH_MINIMO_MIN
        assert informe['alimentadores'][f]['tswitch_al_minimo'] >= 1
    assert informe['tswitch_al_minimo'] >= len(alims)
    assert any('Tiempo de maniobra 0' in a for a in informe['avisos'])
    assert conf.tiempo_de_maniobra(12.5) == (12.5, False)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_datos_la_etapa_de_confiabilidad_no_queda_grabando(semilla):
    """012:RF-98 — al terminar de aplicar el libro, «Etapa_confiabilidad» no queda grabando en «Sin proyecto»: un cambio
    a mano del operador iría a «Datos de confiabilidad», que se borra al aplicar otro libro (bloque DIgSILENT del 20-11,
    sonda_caso_base.json). Sin ninguna etapa grabando antes, ninguna queda grabando; los modelos siguen en su sitio."""
    rng = random.Random(semilla)
    app, alims, clases = _red(rng)
    casos_pf.casos_del_proyecto(app)['sin'].Activate()
    app.grabando = None
    informe, rc = conf.aplicar_datos(app, _plan(alims, _libro(rng), clases))
    assert rc == 0, informe
    _activas(app, 'sin')
    graba = app.GetRecordingStage()
    assert graba is None or graba.GetParent().loc_name != conf.VARIACION, (semilla, graba.loc_name)
    assert informe['grabando'] is None, informe.get('grabando')
    assert conf.VARIACION in _activas(app, 'sin')
    assert all(getattr(ln, 'pStoch', None) is not None for f in alims for ln in _alim(app, f).GetObjs('ElmLne'))


def test_datos_la_grabacion_vuelve_a_la_etapa_del_operador():
    """012:RF-98 — si en «Sin proyecto» grababa una etapa del operador antes de aplicar el libro, la grabación vuelve a
    ella al terminar (como 032:RF-12 en las fichas), y la hora del estudio no cambia."""
    rng = random.Random(7)
    app, alims, clases = _red(rng)
    sin = casos_pf.casos_del_proyecto(app)['sin']
    sin.Activate()
    hora = int(sin.iStudyTime)
    propia = app.carpetas['scheme'].CreateObject('IntScheme', 'Cambios_del_operador')
    propia.NewStage('Etapa_operador', hora - 7 * 24 * 3600, 1)
    sin.iStudyTime = hora
    etapa = next(s for s in propia.GetContents('*.IntSstage'))
    assert app.GetRecordingStage() is etapa
    informe, rc = conf.aplicar_datos(app, _plan(alims, _libro(rng), clases))
    assert rc == 0, informe
    sin.Activate()
    assert app.GetRecordingStage() is etapa, app.GetRecordingStage()
    assert int(sin.iStudyTime) == hora
    assert informe['grabando'] == 'Etapa_operador'


def test_main_admite_el_cancel_file_de_la_web(tmp_path):
    """012:RF-95 — la web pasa ``--cancel-file`` a todo guion cancelable; antes argparse salía con 2 sin informe
    («unrecognized arguments: --cancel-file», 2026-11-20) y la web decía «sin dejar informe»."""
    plan = tmp_path / 'plan.json'
    plan.write_text('{"project": "P", "feeders": ["F1"]}', encoding='utf-8')
    informe = tmp_path / 'informe.json'
    try:
        rc = conf.main(['--plan', str(plan), '--output-json', str(informe), '--aplicar-datos',
                        '--cancel-file', str(tmp_path / 'cancelar.flag')])
    except SystemExit as exc:                # argparse: la prueba falla por su aserción, con el código
        rc = exc.code
    assert informe.is_file(), rc            # llegó a escribir su informe: argparse no lo cortó


def test_confiabilidad_flujo_invalidado_no_pasa_por_sin_tension(monkeypatch):
    """012:RF-96 — en un caso del operador el estudio activa su variación y DIgSILENT invalida el flujo base; antes
    se miraba la tensión sin flujo y todo alimentador salía «sin tensión» con los índices nulos (2026-11-20)."""
    from apoyo import TOOLS

    monkeypatch.syspath_prepend(str(TOOLS))  # como la otra prueba de estudios: el guion se importa desde tools/
    import confiabilidad_pf as cp            # el que importa estudios_pf

    rng = random.Random(23)
    app, alims, _ = _aplicado(rng)
    original = cp.con_datos

    def invalida(app_):                      # como DIgSILENT al activar una variación: sin resultados de flujo
        for o in app_.proyecto.GetContents('*.ElmTerm', 1):
            if hasattr(o, 'm_u'):
                object.__delattr__(o, 'm_u')
        return original(app_)

    monkeypatch.setattr(cp, 'con_datos', invalida)
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'fiabilidad'))
    assert rc == 0, informe
    for f in alims:
        assert (informe['red'][f]['saifi'] or 0) > 0, informe['red'][f]


def test_confiabilidad_orden_fallida_dice_la_causa_de_digsilent(monkeypatch):
    """012:RF-97 — ComRel3 con código 1 dice los errores de DIgSILENT («Active power of the following elements is
    outside the limit. CT_X», 2026-11-20), no solo el código."""
    rng = random.Random(24)
    app, alims, _ = _aplicado(rng)

    def falla(self):
        fake_pf._dice(self._app, 'info - Reliability calculation started',
                      'err  - Violated constraints in base case found.',
                      'err  - Active power of the following elements is outside the limit.',
                      'err  -     CT_X', 'err  - Calculation failed.')
        return 1

    monkeypatch.setattr(fake_pf.Fiabilidad, 'Execute', falla)
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'fiabilidad'))
    assert rc == 2 and 'Violated constraints in base case found' in informe['error']
    assert 'CT_X' in informe['error'] and informe['causa_orden'].count('Calculation failed') == 1


def test_datos_un_libro_nuevo_reemplaza_sin_otra_variacion():
    """012:RF-23 — aplicar otro libro reescribe los modelos, borra los que ya no tienen fila y
    deja una sola «Datos de confiabilidad»."""
    rng = random.Random(9)
    app, alims, clases = _red(rng)
    tipo = _alim(app, alims[0]).GetObjs('ElmLne')[0].typ_id.loc_name
    assert conf.aplicar_datos(app, _plan(alims, _libro(rng, tipos=(tipo,)), clases))[1] == 0
    nuevo = _libro(rng)
    informe, rc = conf.aplicar_datos(app, _plan(alims, nuevo, clases))
    assert rc == 0, informe
    nombres = [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)]
    assert nombres.count(conf.VARIACION) == 1
    modelos = {o.loc_name: o for o in conf._carpeta_modelos(app).GetContents('*')}
    assert f'{conf.PREFIJO_MODELO}tipo_{tipo}' not in modelos
    assert modelos[f'{conf.PREFIJO_MODELO}linea'].DnFr == nuevo.tasas['linea'].permanente


def test_datos_bloquea_sin_una_clase_de_la_red_o_sin_clase_de_equipos():
    """012:RF-17, 012:RF-26 — sin una clase que tiene la red, o sin saber la clase de los
    equipos (ni entrada ni ``aUsage`` que la diga), no se escribe nada y se dice qué falta."""
    rng = random.Random(10)
    app, alims, clases = _red(rng)
    sin_barra = _libro(rng, clases=tuple(c for c in de.CLASES if c != 'barra'))
    informe, rc = conf.aplicar_datos(app, _plan(alims, sin_barra, clases))
    assert rc == 2 and 'Barra' in informe['error'] and 'elemento' in informe['error']
    if any(USO[v] == 'cbk' for v in clases.values()):
        informe, rc = conf.aplicar_datos(app, _plan(alims, _libro(rng), {}))
        assert rc == 2 and 'vuelva a convertir' in informe['error'] and informe['sin_clase']
    assert conf.VARIACION not in [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)]


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_datos_equipos_que_despejan_aislan_y_telemandados(semilla):
    """012:RF-27, 012:RF-13, 012:RF-12, 012:RF-69 — interruptores, reconectadores y fusibles
    despejan; los seccionadores solo aíslan y reponen; los telemandados con su tiempo; cada
    cabecera sin interruptor recibe uno cerrado y con protección en la variación."""
    rng = random.Random(semilla)
    app, alims, clases = _red(rng)
    libro = _libro(rng)
    libro.telemandados = tuple(rng.sample(sorted(clases), 1))
    informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    assert rc == 0, informe
    _activas(app, 'sin')
    for f in alims:
        elm = _alim(app, f)
        assert informe['alimentadores'][f]['interruptor_cabecera']
        cab = [s for s in elm.obj_id.GetContents('*.StaSwitch') if s.loc_name.startswith(conf.NOMBRE_CABECERA)]
        assert cab and cab[0].rel_hasProt == 1 and cab[0].on_off == 1
        for sw in elm.GetObjs('StaSwitch'):
            if sw.loc_name not in clases:
                continue
            clase = clases[sw.loc_name]
            assert sw.rel_hasProt == (0 if clase == 'SWITCH' else 1)
            assert sw.rel_hasRecl == (1 if clase == 'RECLOSER' else 0)
            esperado = libro.tiempos_min['telemandada' if sw.loc_name in libro.telemandados else 'manual']
            assert sw.Tswitch == pytest.approx(esperado)
        assert elm.GetObjs('ElmTerm')[0].AccessTime == pytest.approx(libro.tiempos_min['localizacion'])
    _activas(app, 'base')
    assert not [s for s in _alim(app, alims[0]).obj_id.GetContents('*.StaSwitch')
                if s.loc_name.startswith(conf.NOMBRE_CABECERA)]


def test_012_rf69_si_digsilent_no_crea_el_interruptor_de_cabecera_se_avisa_y_sigue(monkeypatch):
    """012:RF-69 — Pisco (2026-11-25): DIgSILENT devolvió ``None`` al crear el interruptor de cabecera en un
    cubículo vacío y el guion se cayó con «'NoneType' object has no attribute 'aUsage'» sin aplicar nada del
    libro. Ahora ese alimentador queda sin interruptor creado, se dice cuál y por qué, y el libro se aplica."""
    rng = random.Random(7)
    app, alims, clases = _red(rng)
    cub = _alim(app, alims[0]).obj_id
    original = cub.CreateObject
    monkeypatch.setattr(cub, 'CreateObject',
                        lambda clase, *a, **k: None if clase == 'StaSwitch' else original(clase, *a, **k))
    informe, rc = conf.aplicar_datos(app, _plan(alims, _libro(rng), clases))
    assert rc == 0, informe
    assert informe['alimentadores'][alims[0]]['interruptor_cabecera'] is False
    assert any(alims[0] in a and 'interruptor de cabecera' in a for a in informe['avisos']), informe['avisos']
    assert all(informe['alimentadores'][f]['interruptor_cabecera'] for f in alims[1:])


def test_datos_clientes_un_cliente_y_sin_clientes():
    """012:RF-24, 012:RF-25, 012:RF-70 — se usa el número de clientes de cada carga; se cuentan
    las que no lo tienen y se avisa si todas tienen uno."""
    rng = random.Random(12)
    app, alims, clases = _red(rng)
    for c in _alim(app, alims[0]).GetObjs('ElmLod'):
        c.NrCust = 1
    _alim(app, alims[1]).GetObjs('ElmLod')[0].NrCust = 0
    informe, rc = conf.aplicar_datos(app, _plan(alims, _libro(rng), clases))
    assert rc == 0, informe
    assert any(alims[0] in a and 'un solo cliente' in a for a in informe['avisos'])
    assert informe['alimentadores'][alims[1]]['cargas_sin_clientes'] == 1


# =========================================================================== T8: estudios
@pytest.mark.parametrize('rol', ['sin', 'con'])
def test_confiabilidad_por_alimentador_en_cada_caso(rol):
    """012:RF-2, 012:RF-28, 012:RF-29, 012:RF-30 — ``ComRel3`` propio con flujo de carga y red
    de distribución, en el caso pedido, con índices por alimentador; la orden se borra."""
    rng = random.Random(20)
    app, alims, _ = _aplicado(rng)
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'fiabilidad', rol))
    assert rc == 0, informe
    assert set(informe['red']) == set(alims) and informe['fiable']
    for f in alims:
        fila = informe['red'][f]
        assert fila['saifi'] > 0 and fila['ens_kwh'] > 0
        assert fila['caidi'] == pytest.approx(fila['saidi'] / fila['saifi'])
    (rel,) = [o for o in app.creados if o.GetClassName() == 'ComRel3']
    assert (rel.iopt_type, rel.iopt_net) == (1, 1)
    assert not app.GetActiveStudyCase().GetContents('*.ComRel3')
    assert not any('No protection devices' in x for x in app.salida)                    # RF-69


def test_confiabilidad_sin_libro_aplicado_no_se_ejecuta():
    """012:RF-21, 012:RF-19 — sin «Datos de confiabilidad» activa no hay estudio."""
    app, alims, _ = _red(random.Random(21))
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'fiabilidad'))
    assert rc == 2 and 'aplique primero' in informe['error']


def test_confiabilidad_sin_tension_y_con_tasas_cero():
    """012:RF-71, 012:RF-33 — un alimentador sin tensión, o con todas las tasas a cero, no da
    índices: dice por qué."""
    rng = random.Random(22)
    app, alims, clases = _red(rng, sin_cabecera=('F1',))
    assert conf.aplicar_datos(app, _plan(alims, _libro(rng), clases))[1] == 0
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'fiabilidad'))
    assert rc == 0, informe
    assert informe['red']['F1']['saifi'] is None and 'sin tensión' in informe['red']['F1']['motivo']
    app2, alims2, clases2 = _red(rng)
    assert conf.aplicar_datos(app2, _plan(alims2, _libro(rng, cero=True), clases2))[1] == 0
    informe, rc = estudios.ejecutar(app2, _plan_estudio(alims2, 'fiabilidad'))
    assert rc == 0 and all('cero' in informe['red'][f]['motivo'] for f in alims2)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_reconectadores_solo_interruptores_sin_cambiar_la_red(semilla):
    """012:RF-34 a RF-39, 012:RF-60 — candidatos solo interruptores y reconectadores (ni
    fusibles, ni seccionadores, ni el interno de la SED, ni el de cabecera); objetivo y
    máximos del operador; su variación se borra y la hora del caso vuelve.
    012:RF-35, 012:RF-36, 012:RF-37, 012:RF-38"""
    rng = random.Random(semilla)
    app, alims, clases = _aplicado(rng)
    caso = casos_pf.casos_del_proyecto(app)['sin']
    hora = caso.iStudyTime
    previas = {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)}
    opciones = {'objetivo': rng.choice(['ens', 'saidi']), 'max_total': rng.randint(1, 4),
                'max_por_alimentador': rng.randint(1, 2)}
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'reconectadores', opciones=opciones,
                                                       clases_equipo=clases))
    assert rc == 0, informe
    validas = {k for k, v in clases.items() if v in ('BREAKER', 'RECLOSER')}
    propuestos = [p for v in informe['propuesta']['por_alimentador'].values() for p in v]
    assert {p['elemento'] for p in propuestos} <= validas
    assert len(propuestos) <= opciones['max_total']
    opri = next(o for o in app.creados if o.GetClassName() == 'ComOpri')
    assert opri.objective == conf.OBJETIVO_OPRI[opciones['objetivo']] and opri.exclCableProt == 1
    excluidos = {o.loc_name for o in opri.excludedSwts.All()}
    assert excluidos >= {k for k, v in clases.items() if v in ('FUSE', 'SWITCH')}
    assert not excluidos & validas
    assert {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)} == previas
    assert caso.iStudyTime == hora and informe['fiable']
    if propuestos:
        assert informe['mejora'] is not None and all(p['tramo'] for p in propuestos)


def test_reconectadores_alimentador_sin_candidatos():
    """012:RF-39 — un alimentador sin interruptor ni reconectador candidato se dice."""
    rng = random.Random(30)
    app, alims, clases = _aplicado(rng)
    solo_fusibles = {k: 'FUSE' for k in clases}
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'reconectadores', clases_equipo=solo_fusibles))
    assert rc == 0, informe
    assert all(v == [] for v in informe['propuesta']['por_alimentador'].values())
    assert len(informe['propuesta']['avisos']) == len(alims)


def test_un_estudio_que_cambia_algo_se_deshace_y_no_es_fiable(monkeypatch):
    """012:RF-60, 012:RF-61 — si el estudio deja una demanda cambiada o una variación nueva, se
    deshace, se nombra y el resultado queda como no fiable."""
    rng = random.Random(31)
    app, alims, _ = _aplicado(rng)
    carga = _alim(app, alims[0]).GetObjs('ElmLod')[0]
    p0 = carga.plini

    def travieso(app_, plan, alims_, feeders, informe):
        carga.plini = p0 * 3
        app_.carpetas['scheme'].CreateObject('IntScheme', 'Huella')
        informe['red'] = {}

    from apoyo import TOOLS

    monkeypatch.syspath_prepend(str(TOOLS))
    import confiabilidad_pf
    monkeypatch.setattr(confiabilidad_pf, 'fiabilidad', travieso)
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'fiabilidad'))
    assert rc == 0 and not informe['fiable']
    assert any(carga.loc_name in c for c in informe['cambios']) and 'la variación Huella' in informe['cambios']
    assert carga.plini == pytest.approx(p0)
    assert 'Huella' not in [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)]


def test_sin_licencia_se_dice_con_el_modulo(monkeypatch):
    """012:RF-4 — si DIgSILENT rechaza la orden por licencia, el informe nombra el módulo."""
    rng = random.Random(32)
    app, alims, _ = _aplicado(rng)

    def sin_lic(self):
        app.salida.append('err  - No licence available for Reliability Analysis')
        return 1

    monkeypatch.setattr(fake_pf.Fiabilidad, 'Execute', sin_lic)
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'fiabilidad'))
    assert rc == 2 and informe['sin_licencia'] == 'ComRel3' and 'ComRel3' in informe['error']


def test_ayuda_sin_digsilent():
    """012:RF-6 — la herramienta responde a ``--help`` sin abrir DIgSILENT (spec 009)."""
    with pytest.raises(SystemExit) as e:
        conf.main(['--help'])
    assert e.value.code == 0


# =========================================================================== exposición de DIgSILENT
def _historico_del_proyecto(app, alims, rng, tmp_path, **kw):
    """Un histórico sorteado cuyos alimentadores son los del proyecto falso (los demás quedan
    fuera de la red), y un alimentador con cables de longitud sorteada."""
    from test_historico_interrupciones import _escribir, _historico

    filas, exp, _e, _p = _historico(rng)
    nombres = dict(zip(exp, alims))
    filas = [([nombres.get(e[0], e[0]), *e[1:]], ini) for e, ini in filas]
    cable = app.carpetas['equip'].CreateObject('TypLne', 'XLPE_cable')
    cable.cohl_ = 0
    for ln in _alim(app, alims[-1]).GetObjs('ElmLne')[::2]:
        ln.typ_id = cable
    for f in alims:
        for ln in _alim(app, f).GetObjs('ElmLne'):
            ln.dline = round(rng.uniform(0.05, 3), 3)
    return _escribir(tmp_path / 'historico.xlsx', filas, rng, **kw)


def _exposicion_esperada(app, alims):
    out = {}
    for f in alims:
        elm = _alim(app, f)
        lineas = elm.GetObjs('ElmLne')
        out[f] = {'linea': sum(ln.dline for ln in lineas if getattr(ln.typ_id, 'cohl_', 1) != 0),
                  'cable': sum(ln.dline for ln in lineas if getattr(ln.typ_id, 'cohl_', 1) == 0),
                  'transformador': float(len(elm.GetObjs('ElmTr2'))),
                  'barra': float(len(elm.GetObjs('ElmTerm')))}
    return out


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_datos_historico_sin_red_lee_la_exposicion_del_proyecto(semilla, tmp_path):
    """012:RF-87 — el histórico subido a un espacio sin red convertida se aplica igual: la longitud
    de las líneas aéreas y de los cables, los transformadores y las barras de cada alimentador se leen
    del proyecto de DIgSILENT, las tasas salen de ellos como saldrían de la red convertida, y los
    modelos escritos llevan esas tasas."""
    rng = random.Random(semilla)
    app, alims, clases = _red(rng)
    ruta = _historico_del_proyecto(app, alims, rng, tmp_path)
    libro = de.leer_libro(ruta, red=None)
    assert libro.tasas == {} and libro.historico['reconocido']
    esperada = _exposicion_esperada(app, alims)
    informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    assert rc == 0, informe
    leida = informe['exposicion']['alimentadores']
    assert set(leida) == set(alims)
    for f in alims:
        assert leida[f] == pytest.approx(esperada[f]), f
    assert 'DIgSILENT' in informe['exposicion']['origen']
    directo = de.leer_libro(ruta, red=esperada)
    derivado = de.Libro.desde_dict(informe['libro_derivado'])
    assert set(derivado.tasas) == set(directo.tasas)
    for clase, t in directo.tasas.items():
        assert derivado.tasas[clase].permanente == pytest.approx(t.permanente, rel=1e-9, abs=1e-15)
    _activas(app, 'sin')
    modelos = {o.loc_name: o for o in conf._carpeta_modelos(app).GetContents('*')}
    # El modelo de falla de barras (StoTypbar) no tiene DnFr: su falla permanente es DnFr1 (datascheme.db de
    # PowerFactory 2024, build 22038; StoTyplne y StoTyptrf sí llevan DnFr). Es lo que escribe la herramienta.
    for clase in ('linea', 'transformador', 'barra'):
        atributo = 'DnFr1' if clase == 'barra' else 'DnFr'
        if not conf.con_modelo(directo.tasas[clase]):
            # 012:RF-93: sin ninguna falla en el histórico sorteado, la clase va sin modelo y el informe lo dice.
            assert f'{conf.PREFIJO_MODELO}{clase}' not in modelos and clase in informe['sin_modelo']
            continue
        assert getattr(modelos[f'{conf.PREFIJO_MODELO}{clase}'], atributo) == pytest.approx(directo.tasas[clase].permanente)
    assert any('DIgSILENT' in a and 'km' in a for a in informe['avisos'])


def test_datos_historico_con_tasas_no_relee_la_exposicion(tmp_path):
    """012:RF-87 — con la red convertida las tasas ya vienen del libro: el guion no las rehace."""
    rng = random.Random(31)
    app, alims, clases = _red(rng)
    ruta = _historico_del_proyecto(app, alims, rng, tmp_path)
    libro = de.leer_libro(ruta, red=_exposicion_esperada(app, alims))
    informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    assert rc == 0, informe
    assert 'exposicion' not in informe and 'libro_derivado' not in informe


def test_datos_historico_sin_causa_no_escribe_nada_y_lo_dice(tmp_path):
    """012:RF-89 — si con la exposición del proyecto el histórico no da ninguna tasa (sin columna de
    causa), no se escribe nada y se dice en una frase qué revisar del histórico."""
    from convertersmartgrid.aplicacion import historico_interrupciones as hi

    rng = random.Random(32)
    app, alims, clases = _red(rng)
    ruta = _historico_del_proyecto(app, alims, rng, tmp_path, sin=('causa',))
    libro = de.leer_libro(ruta, red=None)
    informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    assert rc == 2 and hi.SIN_TASAS in informe['error'], informe
    assert informe['exposicion']['alimentadores']
    assert conf.VARIACION not in [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)]


def test_datos_historico_sin_columna_del_alimentador_no_escribe_nada_y_nombra_los_titulos(tmp_path):
    """012:RF-92 — si ninguna columna del histórico es la del alimentador (ni por título ni por
    contenido), el guion no escribe nada, sale con rc=2 y el error nombra los títulos encontrados."""
    rng = random.Random(33)
    app, alims, clases = _red(rng)
    ruta = _historico_del_proyecto(app, alims, rng, tmp_path, sin=('alimentador',))
    libro = de.leer_libro(ruta, red=None)
    informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    assert rc == 2 and 'columna del alimentador' in informe['error'] and '«Observación»' in informe['error'], informe
    assert conf.VARIACION not in [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)]


def test_datos_historico_sin_titulo_elige_la_columna_por_contenido(tmp_path):
    """012:RF-90, 012:RF-91 — con la columna del alimentador bajo otro título, el guion la elige por su
    contenido con los alimentadores del proyecto, lo dice en los avisos y escribe las tasas."""
    rng = random.Random(34)
    app, alims, clases = _red(rng)
    ruta = _historico_del_proyecto(app, alims, rng, tmp_path, sin=('alimentador',),
                                   extra=(('Instalación', lambda a, _n: a),))
    libro = de.leer_libro(ruta, red=None)
    informe, rc = conf.aplicar_datos(app, _plan(alims, libro, clases))
    assert rc == 0, informe
    assert any('«Instalación», por contenido' in a and 'del proyecto' in a for a in informe['avisos'])
