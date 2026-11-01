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
from convertersmartgrid import datos_empresa as de

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
