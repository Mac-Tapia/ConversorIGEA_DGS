"""Spec 011, T11 a T15: ``tools/obras_pf.py`` contra ``fake_pf``.

T11: lo que el formulario de las obras ofrece para elegir, leído de DIgSILENT, y la copia
de un tipo a la biblioteca del proyecto. La prueba real la hace el usuario (T19).
"""
from __future__ import annotations

import math
import random

import pytest

import fake_pf
from apoyo import cargar_herramienta

guion = cargar_herramienta('obras_pf.py', 'obras_t11', tools_en_path=True)

SEMILLAS = (3, 29, 61, 97)


def _red(rng, **extra):
    """Proyecto con alimentadores sorteados, cabecera y barras de baja."""
    alims = tuple(f'F{i}' for i in range(1, rng.randint(1, 4) + 1))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=rng.randint(1, 5), bt=True, **extra)
    return app, list(alims)


def _tipo(carpeta, clase, nombre, **datos):
    t = carpeta.CreateObject(clase, nombre)
    for k, v in datos.items():
        setattr(t, k, v)
    return t


def _otro_proyecto(app, nombre='Otro'):
    """Un proyecto importado más, con su biblioteca de equipos dentro de «Library»."""
    prj = fake_pf.nuevo_proyecto(app, app.usuario, nombre)
    lib = next(c for c in prj.GetContents('*.IntPrjfolder') if getattr(c, 'iopt_typ', '') == 'lib')
    equip = lib.CreateObject('IntPrjfolder', 'Equipment Type Library')
    equip.iopt_typ = 'equip'
    return prj, equip


def _plan(feeders, **extra):
    return {'project': 'P', 'feeders': feeders, **extra}


def _limpio(app):
    app.escrituras.clear()
    app.creados.clear()


# --------------------------------------------------------------------------- lectura
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_biblioteca_barras_y_tramos_de_cada_alimentador(semilla):
    """011:RF-88 — de cada alimentador marcado, sus barras con su tensión, sus tramos con
    su tipo y sus ternas, y sus SED con el tipo de transformador, por nombre."""
    rng = random.Random(semilla)
    app, alims = _red(rng)
    elegidos = sorted(rng.sample(alims, rng.randint(1, len(alims))))
    informe, codigo = guion.bibliotecas(app, _plan(elegidos + ['NO_ESTA']))
    assert codigo == 0, informe
    assert sorted(informe['alimentadores']) == elegidos
    assert any('NO_ESTA' in a for a in informe['avisos'])
    for f in elegidos:
        leido = informe['alimentadores'][f]
        elm = next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == f)
        assert leido['kv'] == 10.0
        assert [b['nombre'] for b in leido['barras']] == sorted(b.loc_name for b in elm.GetObjs('ElmTerm'))
        assert {b['kv'] for b in leido['barras']} <= {10.0, 0.38}
        assert [t['nombre'] for t in leido['tramos']] == sorted(ln.loc_name for ln in elm.GetObjs('ElmLne'))
        assert {t['tipo'] for t in leido['tramos']} == {f'AAAC_{f}'}
        assert all(t['nlnum'] == 1 for t in leido['tramos'])
        assert {t['tipo'] for t in leido['trafos']} == {f'TR100_{f}'}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_biblioteca_del_proyecto_y_global_con_sus_datos(semilla):
    """011:RF-89, 011:RF-90, 011:RF-94 — los tipos de la clase pedida del proyecto y de la
    biblioteca global, con los datos que deciden la elección."""
    rng = random.Random(semilla)
    app, alims = _red(rng)
    equip = app.carpetas['equip']
    _tipo(equip, 'TypVoltreg', 'VR_PRJ', Un=10.0, In=200.0, pcReg=10.0, ntapmin=-16, ntapmax=16)
    glob = app.GetGlobalLibrary()
    sub = glob.CreateObject('IntFolder', 'Lineas')          # la global tiene subcarpetas
    secciones = sorted(rng.sample([35, 70, 120, 240], rng.randint(1, 4)))
    for s in secciones:
        _tipo(sub, 'TypLne', f'AAAC_{s}', uline=22.9, sline=0.003 * s, qurs=float(s), rline=30.0 / s)
    _tipo(glob, 'TypTr2', 'TR250', strn=0.25, utrn_h=22.9, utrn_l=0.38)
    _limpio(app)

    informe, codigo = guion.bibliotecas(app, _plan(alims))
    assert codigo == 0, informe
    por = {(t['origen'], t['clase'], t['nombre']): t for t in informe['tipos']}
    for f in alims:
        assert ('proyecto', 'TypLne', f'AAAC_{f}') in por
        assert por[('proyecto', 'TypTr2', f'TR100_{f}')]['resumen'] == '0.1 MVA · 10 kV · 0.38 kV'
    # 025:RF-59: en DIgSILENT, ``In`` de un TypVoltreg va en amperios.
    assert por[('proyecto', 'TypVoltreg', 'VR_PRJ')]['resumen'] == '10 kV · 200 A · 10 % · 16 pasos'
    for s in secciones:
        t = por[('global', 'TypLne', f'AAAC_{s}')]
        assert t['datos']['qurs'] == s and t['resumen'].endswith(f'{s} mm²')
    assert ('global', 'TypTr2', 'TR250') in por

    solo, _ = guion.bibliotecas(app, _plan(alims, clases=['TypLne']))
    assert {t['clase'] for t in solo['tipos']} == {'TypLne'}
    malo, codigo = guion.bibliotecas(app, _plan(alims, clases=['TypXyz']))
    assert codigo == 2 and 'TypXyz' in malo['error']


def test_biblioteca_de_otro_proyecto_sin_activarlo():
    """011:RF-91 — con otro proyecto como origen se listan también sus tipos, sin activarlo:
    el proyecto del operador sigue activo."""
    app, alims = _red(random.Random(0))
    _otro, equip = _otro_proyecto(app)
    _tipo(equip, 'TypLne', 'XLPE_240', uline=22.9, sline=0.5, qurs=240.0)
    _limpio(app)
    informe, codigo = guion.bibliotecas(app, _plan(alims, otro_proyecto='Otro'))
    assert codigo == 0, informe
    ajenos = [t for t in informe['tipos'] if t['origen'] == 'otro']
    assert [(t['nombre'], t['proyecto']) for t in ajenos] == [('XLPE_240', 'Otro')]
    assert app.GetActiveProject() is app.proyecto

    sin, codigo = guion.bibliotecas(app, _plan(alims, otro_proyecto='NoExiste'))
    assert codigo == 0 and any('NoExiste' in a for a in sin['avisos'])
    assert not [t for t in sin['tipos'] if t['origen'] == 'otro']


def test_biblioteca_leer_no_escribe_en_ningun_proyecto():
    """011:RF-88 a 011:RF-91 — leer para el formulario no crea ni cambia nada."""
    app, alims = _red(random.Random(1))
    _otro_proyecto(app)
    _tipo(app.GetGlobalLibrary(), 'TypLne', 'AAAC_120', uline=22.9)
    _limpio(app)
    guion.bibliotecas(app, _plan(alims, otro_proyecto='Otro'))
    assert app.escrituras == [] and app.creados == []


def test_biblioteca_sin_el_proyecto_lo_dice():
    """011:RF-88 — un proyecto que no existe no deja un informe vacío sino el motivo."""
    app, alims = _red(random.Random(2))
    informe, codigo = guion.bibliotecas(app, {**_plan(alims), 'project': 'NoEsta'})
    assert codigo == 2 and 'NoEsta' in informe['error']


# --------------------------------------------------------------------------- copia
def test_biblioteca_global_copiada_al_proyecto_y_reutilizada(monkeypatch):
    """011:RF-92, 011:RF-93 — un tipo de la global se copia a la biblioteca del proyecto con
    ``PasteCopy``, sin tocar el original; pedirlo otra vez reutiliza esa copia."""
    app, _ = _red(random.Random(4))
    glob = _tipo(app.GetGlobalLibrary(), 'TypLne', 'AAAC_120', uline=22.9, sline=0.36, qurs=120.0)
    pegados = []
    original_paste = fake_pf.Obj.PasteCopy
    monkeypatch.setattr(fake_pf.Obj, 'PasteCopy',
                        lambda self, obj, *a: pegados.append(obj) or original_paste(self, obj, *a))
    copia, reutiliza, aviso = guion.copiar_tipo(app, glob, 'AAAC_120')
    assert (reutiliza, aviso) == (False, '') and pegados == [glob]
    assert copia is not glob and copia.GetParent() is app.carpetas['equip']
    assert guion.datos_tipo(copia) == guion.datos_tipo(glob)
    otra, reutiliza, _ = guion.copiar_tipo(app, glob, 'AAAC_120')
    assert otra is copia and reutiliza and pegados == [glob]


def test_biblioteca_copia_con_otros_datos_no_toca_el_original():
    """011:RF-59, 011:RF-60, 011:RF-63 — una copia dentro del proyecto con datos nuevos
    (``AddCopy``) deja el original como estaba; si el nombre ya lo usa un tipo con otros
    datos, la copia toma otro nombre y se dice."""
    app, alims = _red(random.Random(5))
    equip = app.carpetas['equip']
    original = next(t for t in equip.GetContents('*.TypTr2') if t.loc_name == f'TR100_{alims[0]}')
    antes = guion.datos_tipo(original)
    ocupado = _tipo(equip, 'TypTr2', f'TR100_{alims[0]}_22_9kV', strn=0.1, utrn_h=33.0, utrn_l=0.38)
    copia, reutiliza, aviso = guion.copiar_tipo(app, original, f'TR100_{alims[0]}_22_9kV',
                                                {'utrn_h': 22.9})
    assert not reutiliza and copia is not ocupado
    assert copia.loc_name == f'TR100_{alims[0]}_22_9kV_2' and 'otros datos' in aviso
    assert guion.datos_tipo(copia) == {**antes, 'utrn_h': 22.9}
    assert guion.datos_tipo(original) == antes
    assert guion.datos_tipo(ocupado)['utrn_h'] == 33.0


def test_biblioteca_copia_desde_otro_proyecto():
    """011:RF-91, 011:RF-92 — un tipo de otro proyecto queda copiado en el del operador,
    que ya no depende del otro."""
    app, _ = _red(random.Random(6))
    _otro, equip_otro = _otro_proyecto(app)
    ajeno = _tipo(equip_otro, 'TypVoltreg', 'VR_OTRO', Un=22.9, In=0.2, pcReg=10.0,
                  ntapmin=-16, ntapmax=16)
    copia, reutiliza, _ = guion.copiar_tipo(app, ajeno, 'VR_OTRO')
    assert not reutiliza and copia.GetParent() is app.carpetas['equip']
    ajeno.Delete()
    assert guion.datos_tipo(copia)['Un'] == 22.9


# =========================================================================== T12
casos_pf = cargar_herramienta('casos_pf.py', 'casos_t12', tools_en_path=True)
SIN, CON, BASE = 'Sin proyecto', 'Con proyecto', 'Caso base'


def _calibrada(rng, n_min=2, cargas_min=2):
    """Proyecto con alimentadores sorteados, ajustados y con los tres casos preparados.

    Cada alimentador tiene tantos tramos como cargas: ``cargas_min`` asegura los que pide
    una prueba.
    """
    alims = tuple(f'F{i}' for i in range(1, rng.randint(n_min, 4) + 1))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=rng.randint(cargas_min, 5),
                           bt=True, flujo=True)
    ajustes = []
    for f in alims:
        v = app.carpetas['scheme'].CreateObject('IntScheme', f'Ajuste_{f}_20261011_090000')
        v.NewStage(f'Etapa_{f}', 0, 1)
        app.grabando = None
        ajustes.append({'feeder': f, 'variacion': v.loc_name, 'cuadrado': True})
    base = {'variaciones': [a['variacion'] for a in ajustes], 'feeders': list(alims),
            'ajustes': ajustes, 'excluidos': []}
    informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': list(alims), 'base': base,
                                              'caso_base_sin_verificar': {}})
    assert codigo == 0, informe
    # Como en DIgSILENT: lo que escribe una etapa es de su variación, y desactivarla lo deshace.
    app.atributos_en_variacion = True
    _limpio(app)
    return app, list(alims)


def _activas(app, nombre_caso):
    """Las variaciones activas en el caso, dejándolo activo."""
    caso = next(c for c in casos_pf.casos_del_proyecto(app).values() if c.loc_name == nombre_caso)
    caso.Activate()
    return {v.loc_name for v in app.GetActiveNetworkVariations()}


def _terna(ctx):
    for e in ctx.fila['elementos']:
        ln = ctx.objeto('ElmLne', e['elemento'])
        ln.nlnum = int(getattr(ln, 'nlnum', 1) or 1) + 1


def _seccion(ctx):
    (copia,) = ctx.tipos.values()
    for e in ctx.fila['elementos']:
        ctx.objeto('ElmLne', e['elemento']).typ_id = copia


def _sobrecarga(ctx):
    """Una «obra» que cuelga una carga enorme del alimentador: el flujo deja de converger.

    Se crea dentro de la variación de la obra, así que solo existe donde está activa.
    Escribir la P de las cargas existentes no serviría: en ``fake_pf`` no pasa por la
    variación (en DIgSILENT es un dato de operación, que va al escenario).
    """
    barra = ctx.objeto('ElmTerm', f'{ctx.obra.alimentador}_B1')
    carga = barra.GetParent().CreateObject('ElmLod', 'Carga_enorme')
    carga.plini, carga.coslini = 1000.0, 0.95
    barra.CreateObject('StaCubic', 'c_enorme').obj_id = carga


def _toca_a_otro(ctx):
    """Una «obra» que cambia, además, otro alimentador: lo que RF-64 tiene que ver.

    El cambio en las cargas del otro no pasa por la variación, como el de un tipo
    compartido en DIgSILENT: se ve en todos los casos, también en «Sin proyecto».
    """
    _terna(ctx)
    otro = next(a for a in ctx.proyecto.GetContents('*.ElmFeeder', 1)
                if a.loc_name != ctx.obra.alimentador)
    for c in otro.GetObjs('ElmLod'):
        c.plini = c.plini * 2


def _obra_terna(f, casos, tramos=('L1',)):
    return {'clase': 'terna', 'alimentador': f, 'casos': casos,
            'tramos': [f'{f}_{t}' for t in tramos]}


def _banco(f, casos):
    return {'clase': 'condensador', 'alimentador': f, 'casos': casos, 'barra': f'{f}_B1',
            'q_kvar': 300, 'escalones': 1}


def _variaciones(app):
    return {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_comunes_una_variacion_por_obra_activa_solo_en_sus_casos(semilla, monkeypatch):
    """011:RF-57, 011:RF-58 — cada obra en su variación, activa solo en los casos que eligió
    el operador y nunca en el «Caso base»."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    pedidas = [rng.choice([[CON], [SIN, CON]]) for _ in alims]
    plan = _plan(alims, obras=[_obra_terna(f, c) for f, c in zip(alims, pedidas)])
    informe, codigo = guion.aplicar(app, plan)
    assert codigo == 0, informe
    nombres = [o['variacion'] for o in informe['obras']]
    assert len(set(nombres)) == len(alims)
    for nombre, casos in zip(nombres, pedidas):
        for caso in (SIN, CON):
            assert (nombre in _activas(app, caso)) == (caso in casos), (nombre, caso)
        assert nombre not in _activas(app, BASE)
    for o, casos in zip(informe['obras'], pedidas):
        assert o['casos_activos'] == casos and all(x['converge'] for x in o['flujo'].values())


def test_comunes_el_caso_activo_vuelve_a_ser_el_de_antes(monkeypatch):
    """011:RF-57 — aplicar recorre los casos y deja activo el que tenía el operador."""
    app, alims = _calibrada(random.Random(8))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    antes = app.GetActiveStudyCase()
    guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [SIN, CON])]))
    assert app.GetActiveStudyCase() is antes


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_comunes_tipo_copiado_y_asignado_en_la_variacion(semilla, monkeypatch):
    """011:RF-59, 011:RF-60 — la obra asigna una copia del tipo dentro de su variación: en
    el caso sin la obra el tramo conserva su tipo, y ningún tipo existente cambia."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'seccion', _seccion)
    glob = _tipo(app.GetGlobalLibrary(), 'TypLne', 'AAAC_120', uline=22.9, sline=0.36, qurs=120.0)
    f = rng.choice(alims)
    tramo = f'{f}_L1'
    obra = {'clase': 'seccion', 'alimentador': f, 'casos': [CON], 'tramos': [tramo],
            'tipo': {'nombre': 'AAAC_120', 'clase': 'TypLne', 'origen': 'global'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    (copia,) = informe['obras'][0]['tipos']
    assert copia['nombre'] == 'AAAC_120_10kV' and copia['datos']['uline'] == 10.0
    assert glob.uline == 22.9
    linea = next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == tramo)
    _activas(app, CON)
    assert linea.typ_id.loc_name == 'AAAC_120_10kV'
    _activas(app, SIN)
    assert linea.typ_id.loc_name == f'AAAC_{f}'


def test_comunes_obra_que_no_converge_queda_inactiva_y_se_conserva(monkeypatch):
    """011:RF-66, 011:RF-67 — con una obra que no deja converger, la obra queda inactiva en
    ese caso, sigue en el proyecto y el informe da el diagnóstico de la spec 006."""
    app, alims = _calibrada(random.Random(9))
    app.ldf.limite = 5.0
    monkeypatch.setitem(guion.CONSTRUCTORES, 'condensador', _sobrecarga)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_banco(alims[0], [SIN, CON])]))
    assert codigo == 2
    o = informe['obras'][0]
    assert o['casos_activos'] == []
    for caso in (SIN, CON):
        assert o['flujo'][caso]['converge'] is False
        assert 'barras_sin_tension' in o['flujo'][caso]['diagnostico']
        assert o['variacion'] not in _activas(app, caso)
    assert o['variacion'] in _variaciones(app)
    _activas(app, SIN)
    assert app.ldf.Execute() == 0          # sin la obra, el caso vuelve a converger


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_comunes_sin_proyecto_no_cambia_donde_no_hay_obras(semilla, monkeypatch):
    """011:RF-64, 011:RF-65 — después de las obras, en «Sin proyecto» los alimentadores sin
    obras tienen la misma cabecera y tensión mínima; si una obra toca otro alimentador, el
    informe lo dice con el alimentador y el valor."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    f = rng.choice(alims)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(f, [SIN, CON])]))
    assert codigo == 0, informe
    assert informe['comprobacion'] == {'alimentadores': [a for a in alims if a != f],
                                       'diferencias': []}

    app, alims = _calibrada(random.Random(semilla + 1))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _toca_a_otro)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [SIN, CON])]))
    assert codigo == 2
    tocados = {d['alimentador'] for d in informe['comprobacion']['diferencias']}
    assert tocados and alims[0] not in tocados
    assert any(t in a and 'compartido' in a for t in tocados for a in informe['avisos'])


def test_comunes_obra_que_falla_al_construirse_no_deja_variacion(monkeypatch):
    """011:RF-56 — una obra que no se puede construir no deja su variación a medias, y las
    demás se aplican."""
    app, alims = _calibrada(random.Random(10))

    def falla(_ctx):
        raise RuntimeError('tramo bloqueado')

    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', falla)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'condensador', lambda ctx: None)
    obras = [_obra_terna(alims[0], [SIN, CON]), _banco(alims[0], [SIN, CON])]
    informe, codigo = guion.aplicar(app, _plan(alims, obras=obras))
    assert codigo == 2
    terna, banco = informe['obras']
    assert 'tramo bloqueado' in terna['error'] and terna['variacion'] == ''
    assert not any(n.startswith('Obra_terna') for n in _variaciones(app))
    assert banco['variacion'] in _variaciones(app) and not banco['error']


def test_comunes_clase_sin_constructor_se_rechaza(monkeypatch):
    """011:RF-56 — una clase de obra que aún no se sabe construir se rechaza sin crear nada."""
    app, alims = _calibrada(random.Random(11))
    monkeypatch.setattr(guion, 'CONSTRUCTORES', {})
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [SIN, CON])]))
    assert codigo == 2 and 'todavía no' in informe['obras'][0]['error']
    assert not any(n.startswith('Obra_') for n in _variaciones(app))


def test_comunes_simular_no_escribe_nada():
    """011:RF-69 — simular dice por obra su variación, elementos y tipos, sin escribir."""
    app, alims = _calibrada(random.Random(12))
    _tipo(app.GetGlobalLibrary(), 'TypLne', 'AAAC_120', uline=22.9, qurs=120.0)
    _limpio(app)
    obras = [_obra_terna(alims[0], [SIN, CON]),
             {'clase': 'seccion', 'alimentador': alims[0], 'casos': [CON],
              'tramos': [f'{alims[0]}_L1'],
              'tipo': {'nombre': 'AAAC_120', 'clase': 'TypLne', 'origen': 'global'}}]
    informe, codigo = guion.aplicar(app, _plan(alims, obras=obras), simular=True)
    assert codigo == 0, informe
    assert [o['variacion'] for o in informe['obras']] == [
        f'Obra_terna_{alims[0]}', f'Obra_seccion_{alims[0]}']
    assert informe['obras'][1]['tipos'][0]['nombre'] == 'AAAC_120_10kV'
    assert app.creados == [] and app.escrituras == []


def test_comunes_sin_los_tres_casos_no_aplica():
    """011:RF-57 — sin los casos preparados no hay dónde activar las obras: no se aplica."""
    app, alims = _red(random.Random(13))
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [SIN, CON])]))
    assert codigo == 2 and 'prepare los casos' in informe['error']


def test_comunes_obra_en_el_caso_base_no_aplica_nada():
    """011:RF-58 — una obra en el «Caso base» se rechaza con el plan entero, sin escribir."""
    app, alims = _calibrada(random.Random(14))
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [BASE])]))
    assert codigo == 2 and 'Caso base' in informe['error']
    assert app.creados == []


# =========================================================================== T13
def _elm(app, f):
    return next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == f)


def _barra(app, nombre):
    return next(b for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == nombre)


def _linea(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == nombre)


def _cubiculo_de(app, linea, barra):
    return next(c for c in barra.GetContents('*.StaCubic') if c.obj_id is linea)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_condensador_fijo_en_su_barra_solo_en_su_caso(semilla):
    """011:RF-71 — un ``ElmShnt`` capacitivo en la barra, con la potencia total repartida en
    sus escalones y la tensión de la barra, que solo existe en el caso de la obra."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    f = rng.choice(alims)
    barra = f'{f}_B{rng.randint(1, 2)}'
    q, n = rng.choice([300, 600, 900, 1200]), rng.randint(1, 4)
    obra = {'clase': 'condensador', 'alimentador': f, 'casos': [CON], 'barra': barra,
            'q_kvar': q, 'escalones': n}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, CON)
    (banco,) = _elm(app, f).GetObjs('ElmShnt')
    assert banco.shtype == guion.SHUNT_C and banco.ushnm == 10.0
    assert banco.qcapn * banco.ncapa * 1000 == pytest.approx(q)
    assert banco.ncapx == banco.ncapa == n and banco.iswitch == 0
    assert any(c.obj_id is banco for c in _barra(app, barra).GetContents('*.StaCubic'))
    _activas(app, SIN)
    assert _elm(app, f).GetObjs('ElmShnt') == []


def test_condensador_regulando_su_consigna():
    """011:RF-72 — con consigna, el banco queda maniobrable por escalones con la banda
    alrededor de ella; si el flujo no ajusta los condensadores, se avisa."""
    app, alims = _calibrada(random.Random(21))
    f = alims[0]
    obra = {'clase': 'condensador', 'alimentador': f, 'casos': [SIN, CON], 'barra': f'{f}_B1',
            'q_kvar': 600, 'escalones': 3, 'consigna_pu': 1.02}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, SIN)
    (banco,) = _elm(app, f).GetObjs('ElmShnt')
    assert banco.iswitch == 1 and banco.i_cont == 0
    assert (banco.usetp_mn, banco.usetp_mx) == pytest.approx((1.01, 1.03))
    assert any('iopt_asht' in a for a in informe['obras'][0]['avisos'])

    app, alims = _calibrada(random.Random(22))
    app.ldf.iopt_asht = 1
    obra['alimentador'], obra['barra'] = alims[0], f'{alims[0]}_B1'
    informe, _ = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert not any('iopt_asht' in a for a in informe['obras'][0]['avisos'])


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_reconectador_al_principio_del_tramo(semilla):
    """011:RF-73 — un interruptor cerrado, con protección y reenganche, en el cubículo del
    extremo del tramo más cercano a la cabecera, con un relé y su bloque de reenganche."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    f = rng.choice(alims)
    k = rng.randint(1, 2)
    obra = {'clase': 'reconectador', 'alimentador': f, 'casos': [SIN, CON], 'tramo': f'{f}_L{k}'}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, SIN)
    cub = _cubiculo_de(app, _linea(app, f'{f}_L{k}'), _barra(app, f'{f}_B{k - 1}'))
    (sw,) = cub.GetContents('*.StaSwitch')
    assert (sw.aUsage, sw.on_off, sw.rel_hasProt, sw.rel_hasRecl) == ('cbk', 1, 1, 1)
    (rele,) = cub.GetContents('*.ElmRelay')
    assert [b.GetClassName() for b in rele.GetContents()] == ['RelRecl']
    lejos = _cubiculo_de(app, _linea(app, f'{f}_L{k}'), _barra(app, f'{f}_B{k}'))
    assert lejos.GetContents('*.StaSwitch') == []


def test_reconectador_con_tipo_de_reenganche_de_la_global():
    """011:RF-73, 011:RF-92 — el tipo de reenganche elegido en la global se copia al proyecto
    y es el del bloque del relé."""
    app, alims = _calibrada(random.Random(23))
    _tipo(app.GetGlobalLibrary(), 'TypRecl', 'Recl_3_disparos', roplockout=3)
    f = alims[0]
    obra = {'clase': 'reconectador', 'alimentador': f, 'casos': [SIN, CON], 'tramo': f'{f}_L1',
            'tipo': {'nombre': 'Recl_3_disparos', 'clase': 'TypRecl', 'origen': 'global'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, SIN)
    cub = _cubiculo_de(app, _linea(app, f'{f}_L1'), _barra(app, f'{f}_B0'))
    (bloque,) = cub.GetContents('*.ElmRelay')[0].GetContents()
    assert bloque.typ_id.GetParent() is app.carpetas['equip']
    assert bloque.typ_id.loc_name == 'Recl_3_disparos'


def test_reconectador_en_un_cubiculo_con_interruptor_lo_reutiliza():
    """011:RF-73 — un cubículo admite un interruptor: si ya hay uno, pasa a reconectador y se
    dice, en vez de crear un segundo."""
    app, alims = _calibrada(random.Random(24))
    f = alims[0]
    cub = _cubiculo_de(app, _linea(app, f'{f}_L1'), _barra(app, f'{f}_B0'))
    viejo = cub.CreateObject('StaSwitch', 'SECC_1')
    viejo.aUsage, viejo.on_off = 'dct', 1
    _limpio(app)
    obra = {'clase': 'reconectador', 'alimentador': f, 'casos': [SIN, CON], 'tramo': f'{f}_L1'}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, SIN)              # el cambio del interruptor es de la variación de la obra
    assert cub.GetContents('*.StaSwitch') == [viejo] and viejo.rel_hasRecl == 1
    assert any('SECC_1' in a for a in informe['obras'][0]['avisos'])


def test_reconectador_avisa_que_no_cambia_los_estudios():
    """011:RF-74 — el informe dice que el reconectador no cambia el flujo ni los estudios de
    esta iteración, y la cabecera es la misma con él y sin él."""
    app, alims = _calibrada(random.Random(25))
    f = alims[0]
    obra = {'clase': 'reconectador', 'alimentador': f, 'casos': [CON], 'tramo': f'{f}_L1'}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    assert any('fiabilidad' in a for a in informe['obras'][0]['avisos'])
    rama = _linea(app, f'{f}_L1')
    medidas = []
    for caso in (SIN, CON):
        _activas(app, caso)
        app.ldf.Execute()
        medidas.append(getattr(rama, 'm_Psum:bus1'))
    assert medidas[0] == medidas[1]


def test_principio_de_un_tramo_dibujado_al_reves():
    """011:RF-73, 011:RF-75 — el principio del tramo lo da el camino a la cabecera, no el
    orden de sus cubículos."""
    app, alims = _calibrada(random.Random(26))
    f = alims[0]
    elm = _elm(app, f)
    ultima = max(elm.GetObjs('ElmTerm'), key=lambda b: int(b.loc_name.rsplit('B', 1)[1]))
    red = ultima.GetParent()
    lejana = red.CreateObject('ElmTerm', f'{f}_LEJOS')
    lejana.uknom = 10.0
    linea = red.CreateObject('ElmLne', f'{f}_ALREVES')
    for barra, lado in ((lejana, 0), (ultima, 1)):
        c = barra.CreateObject('StaCubic', f'c{lado}_ALREVES')
        c.obj_id, c.obj_bus = linea, lado
    elm._objs.extend([lejana, linea])
    cub, barra = guion.principio_del_tramo(elm, linea)
    assert barra is ultima and cub.obj_bus == 1


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_regulador_intercalado_al_principio_del_tramo(semilla):
    """011:RF-75, 011:RF-76 — una barra nueva entre el regulador y el tramo: el cubículo del
    tramo pasa a ella, el regulador va de la barra de origen (lado S) a la nueva (lado L),
    con la consigna, la banda, y un tipo con el rango y los pasos a cada lado."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    _tipo(app.GetGlobalLibrary(), 'TypVoltreg', 'VR_200A', Un=13.2, In=0.2, pcReg=10.0,
          ntapmin=-16, ntapmax=16, nntap0=0)
    f = rng.choice(alims)
    k = rng.randint(1, 2)
    pasos, rango, consigna = rng.choice([8, 16, 32]), rng.choice([5, 10]), rng.choice([1.0, 1.02])
    obra = {'clase': 'regulador', 'alimentador': f, 'casos': [CON], 'tramo': f'{f}_L{k}',
            'consigna_pu': consigna, 'rango_pct': rango, 'pasos': pasos,
            'tipo': {'nombre': 'VR_200A', 'clase': 'TypVoltreg', 'origen': 'global'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, CON)
    elm = _elm(app, f)
    (reg,) = elm.GetObjs('ElmVoltreg')
    origen = _barra(app, f'{f}_B{k - 1}')
    nueva = next(b for b in elm.GetObjs('ElmTerm') if b.loc_name == f'{f}_L{k}_REG')
    assert nueva.uknom == origen.uknom == 10.0
    assert _cubiculo_de(app, _linea(app, f'{f}_L{k}'), nueva) is not None
    assert not any(c.obj_id is _linea(app, f'{f}_L{k}') for c in origen.GetContents('*.StaCubic'))
    lados = {c.obj_bus: c.GetParent() for b in (origen, nueva) for c in b.GetContents('*.StaCubic')
             if c.obj_id is reg}
    assert lados == {0: origen, 1: nueva}
    assert reg.usetp == consigna and reg.ntrcn == 1
    assert (reg.usp_low, reg.usp_up) == pytest.approx((consigna - 0.01, consigna + 0.01))
    tipo = reg.typ_id
    assert tipo.GetParent() is app.carpetas['equip']
    # 025:RF-59: ``Un`` es la de cada unidad monofásica; en estrella, la de fase.
    assert tipo.Un == pytest.approx(10.0 / math.sqrt(3))
    assert (tipo.pcReg, tipo.ntapmax, tipo.ntapmin, tipo.nntap0) == (rango, pasos, -pasos, 0)


def test_regulador_usa_el_tipo_del_proyecto_si_ya_tiene_los_datos():
    """011:RF-76 — si el tipo del proyecto elegido ya tiene la tensión, el rango y los pasos,
    se asigna ese y no se copia ninguno."""
    app, alims = _calibrada(random.Random(27))
    equip = app.carpetas['equip']
    vr = _tipo(equip, 'TypVoltreg', 'VR_10kV', Un=10.0 / math.sqrt(3), In=200.0, pcReg=10.0,
               ntapmin=-16, ntapmax=16, nntap0=0)
    antes = len(equip.GetContents('*.TypVoltreg'))
    f = alims[0]
    obra = {'clase': 'regulador', 'alimentador': f, 'casos': [SIN, CON], 'tramo': f'{f}_L1',
            'consigna_pu': 1.0, 'rango_pct': 10, 'pasos': 16,
            'tipo': {'nombre': 'VR_10kV', 'clase': 'TypVoltreg'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    assert informe['obras'][0]['tipos'] == []
    _activas(app, SIN)
    assert _elm(app, f).GetObjs('ElmVoltreg')[0].typ_id is vr
    assert len(equip.GetContents('*.TypVoltreg')) == antes


def test_regulador_que_no_puede_mover_el_cubiculo_no_deja_nada():
    """011:RF-75 — si DIgSILENT no deja pasar el cubículo a la barra nueva, la obra no queda a
    medias: su variación se borra y el informe lo dice."""
    app, alims = _calibrada(random.Random(28))
    app.fallar_mover = True
    _tipo(app.carpetas['equip'], 'TypVoltreg', 'VR', Un=10.0, pcReg=10.0, ntapmin=-16,
          ntapmax=16, nntap0=0)
    f = alims[0]
    obra = {'clase': 'regulador', 'alimentador': f, 'casos': [SIN, CON], 'tramo': f'{f}_L1',
            'consigna_pu': 1.0, 'rango_pct': 10, 'pasos': 16,
            'tipo': {'nombre': 'VR', 'clase': 'TypVoltreg'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 2 and 'cubículo' in informe['obras'][0]['error']
    assert not any(n.startswith('Obra_regulador') for n in _variaciones(app))


# =========================================================================== T14
class _Troncal(fake_pf.Obj):
    """``ElmBbone`` del doble: su camino de barras y líneas."""

    def GetCompleteBbPath(self, _reverso, _hasta_enlace=0):
        return list(self.camino)


def _con_troncal(app, largo=2):
    """Una derivación corta en cada alimentador y un ``ComBbone`` que las obras no usan.

    Desde la spec 016 la troncal de las obras es la del camino más largo (016:RF-1): en el
    doble, la cadena de líneas ``<F>_L1…Ln`` de 1 km. La derivación ``<F>_LD`` sale de
    ``<F>_B1`` con 0,5 km, así que nunca es troncal. ``ComBbone`` sigue registrado para
    comprobar que las obras ya no lo ejecutan (016:RF-10); su efecto deja una troncal que
    no coincide con la del camino más largo.
    """
    for a in app.proyecto.GetContents('*.ElmFeeder', 1):
        red = a.GetParent()
        f = a.loc_name
        b1 = next(b for b in a.GetObjs('ElmTerm') if b.loc_name == f'{f}_B1')
        bd = red.CreateObject('ElmTerm', f'{f}_BD')
        bd.uknom, bd.GPSlat, bd.GPSlon = b1.uknom, b1.GPSlat + 0.002, b1.GPSlon
        ld = red.CreateObject('ElmLne', f'{f}_LD')
        ld.typ_id, ld.nlnum, ld.outserv, ld.dline = b1.GetContents('*.StaCubic')[0].obj_id.typ_id, 1, 0, 0.5
        for lado, b in ((0, b1), (1, bd)):
            cub = b.CreateObject('StaCubic', f'c{lado}_{ld.loc_name}')
            cub.obj_id, cub.obj_bus = ld, lado
        a._objs.extend([bd, ld])

    def efecto(app_, _orden):
        for a in app_.proyecto.GetContents('*.ElmFeeder', 1):
            red = a.GetParent()
            t = _Troncal(app_, 'ElmBbone', f'BB_{a.loc_name}', red)
            red._hijos.append(t)
            lineas = sorted(a.GetObjs('ElmLne'), key=lambda o: o.loc_name)[:largo]
            t.pBbStart = a
            t.camino = [o for par in zip(a.GetObjs('ElmTerm'), lineas) for o in par]
    orden = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=efecto)
    app.ordenes['ComBbone'] = orden
    _limpio(app)
    return orden


def _troncal_esperada(f, app=None):
    """La cadena entera del alimentador: su camino más largo (016:RF-1)."""
    elm = next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == f)
    return sorted((ln.loc_name for ln in elm.GetObjs('ElmLne') if ln.loc_name != f'{f}_LD'),
                  key=lambda n: int(n.rsplit('_L', 1)[1]))


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_seccion_en_la_troncal_si_no_se_indican_tramos(semilla):
    """011:RF-77, 016:RF-1, 016:RF-10 — sin tramos, el tipo nuevo va a los tramos de la
    troncal del camino más largo (no a la de ``ComBbone``, que las obras ya no ejecutan),
    solo en el caso de la obra; las derivaciones conservan el suyo."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    bb = _con_troncal(app)
    _tipo(app.carpetas['equip'], 'TypLne', 'AAAC_240', uline=10.0, sline=0.6, qurs=240.0)
    _limpio(app)
    f = rng.choice(alims)
    obra = {'clase': 'seccion', 'alimentador': f, 'casos': [CON],
            'tipo': {'nombre': 'AAAC_240', 'clase': 'TypLne'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    assert bb.ejecuciones == 0
    assert [e['elemento'] for e in informe['obras'][0]['elementos']] == _troncal_esperada(f, app)
    assert informe['obras'][0]['tipos'] == []          # mismo tipo y tensión: no se copia
    _activas(app, CON)
    lineas = {ln.loc_name: ln for ln in _elm(app, f).GetObjs('ElmLne')}
    for nombre, ln in lineas.items():
        esperado = 'AAAC_240' if nombre in _troncal_esperada(f, app) else f'AAAC_{f}'
        assert ln.typ_id.loc_name == esperado, nombre
    _activas(app, SIN)
    assert {ln.typ_id.loc_name for ln in lineas.values()} == {f'AAAC_{f}'}
    # Las troncales que creó el cálculo no quedan en el proyecto.
    assert app.GetCalcRelevantObjects('*.ElmBbone') == []


def test_seccion_solo_en_los_tramos_indicados_y_avisa_fuera_de_la_troncal():
    """011:RF-78, 011:RF-87 — con tramos indicados se cambian solo esos; uno que no es de la
    troncal se cambia igual y se anota."""
    app, alims = _calibrada(random.Random(31), cargas_min=3)
    _con_troncal(app)
    _tipo(app.carpetas['equip'], 'TypLne', 'AAAC_240', uline=10.0, qurs=240.0)
    f = alims[0]
    tramos = [f'{f}_L1', f'{f}_LD']
    obra = {'clase': 'seccion', 'alimentador': f, 'casos': [SIN, CON], 'tramos': tramos,
            'tipo': {'nombre': 'AAAC_240', 'clase': 'TypLne'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, SIN)
    lineas = {ln.loc_name: ln.typ_id.loc_name for ln in _elm(app, f).GetObjs('ElmLne')}
    assert {n for n, t in lineas.items() if t == 'AAAC_240'} == set(tramos)
    avisos = informe['obras'][0]['avisos']
    assert any(f'{f}_LD' in a and 'troncal' in a for a in avisos)
    assert not any(f'{f}_L1 ' in a and 'no es de la troncal' in a for a in avisos)


def test_seccion_de_otra_tension_se_copia_a_la_del_alimentador():
    """011:RF-79 — un tipo que no está a la tensión del alimentador se copia a ella y se
    asigna la copia; el original no cambia."""
    app, alims = _calibrada(random.Random(33))
    _con_troncal(app)
    glob = _tipo(app.GetGlobalLibrary(), 'TypLne', 'AAAC_240', uline=22.9, sline=0.6, qurs=240.0)
    f = alims[0]
    obra = {'clase': 'seccion', 'alimentador': f, 'casos': [SIN, CON],
            'tipo': {'nombre': 'AAAC_240', 'clase': 'TypLne', 'origen': 'global'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    _activas(app, SIN)
    tipos = {ln.typ_id for ln in _elm(app, f).GetObjs('ElmLne') if ln.loc_name in _troncal_esperada(f, app)}
    (copia,) = tipos
    assert copia.loc_name == 'AAAC_240_10kV' and copia.uline == 10.0 and copia.qurs == 240.0
    assert copia.GetParent() is app.carpetas['equip'] and glob.uline == 22.9


def test_seccion_con_un_tipo_que_no_existe_se_rechaza_diciendo_cual():
    """011:RF-79 — si el tipo indicado no está en ninguna biblioteca, la obra se rechaza con
    su nombre y no se crea nada."""
    app, alims = _calibrada(random.Random(34))
    _con_troncal(app)
    f = alims[0]
    obra = {'clase': 'seccion', 'alimentador': f, 'casos': [SIN, CON],
            'tipo': {'nombre': 'NO_EXISTE_95', 'clase': 'TypLne'}}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 2 and 'NO_EXISTE_95' in informe['obras'][0]['error']
    assert not any(n.startswith('Obra_') for n in _variaciones(app))


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_terna_mas_en_la_troncal(semilla):
    """011:RF-80 — una terna más en cada tramo de la troncal, con el mismo tipo, solo en el
    caso de la obra."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    _con_troncal(app)
    f = rng.choice(alims)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[
        {'clase': 'terna', 'alimentador': f, 'casos': [CON]}]))
    assert codigo == 0, informe
    _activas(app, CON)
    for ln in _elm(app, f).GetObjs('ElmLne'):
        dentro = ln.loc_name in _troncal_esperada(f, app)
        assert int(getattr(ln, 'nlnum', 1)) == (2 if dentro else 1), ln.loc_name
        assert ln.typ_id.loc_name == f'AAAC_{f}'
    _activas(app, SIN)
    assert {int(getattr(ln, 'nlnum', 1)) for ln in _elm(app, f).GetObjs('ElmLne')} == {1}


def test_terna_y_seccion_en_el_mismo_tramo_se_suman():
    """011:RF-77, 011:RF-80 — dos obras sobre el mismo tramo y caso se aplican las dos, en el
    orden en que llegan (casos límite de la spec)."""
    app, alims = _calibrada(random.Random(35))
    _con_troncal(app)
    _tipo(app.carpetas['equip'], 'TypLne', 'AAAC_240', uline=10.0, qurs=240.0)
    f = alims[0]
    obras = [{'clase': 'seccion', 'alimentador': f, 'casos': [SIN, CON], 'tramos': [f'{f}_L1'],
              'tipo': {'nombre': 'AAAC_240', 'clase': 'TypLne'}},
             {'clase': 'terna', 'alimentador': f, 'casos': [SIN, CON], 'tramos': [f'{f}_L1']},
             {'clase': 'terna', 'alimentador': f, 'casos': [SIN, CON], 'tramos': [f'{f}_L1']}]
    informe, codigo = guion.aplicar(app, _plan(alims, obras=obras))
    assert codigo == 0, informe
    _activas(app, SIN)
    linea = _linea(app, f'{f}_L1')
    assert linea.typ_id.loc_name == 'AAAC_240' and linea.nlnum == 3


def test_terna_sin_troncal_ni_tramos_se_rechaza():
    """011:RF-80 — sin troncal calculada ni tramos indicados no hay dónde sumar la terna: se
    rechaza pidiéndolos. Desde la 016 la troncal sale de la red; falta si el ``ElmFeeder``
    no dice su cabecera."""
    app, alims = _calibrada(random.Random(36))
    f = alims[0]
    object.__setattr__(_elm(app, f), 'obj_id', None)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[
        {'clase': 'terna', 'alimentador': f, 'casos': [SIN, CON]}]))
    assert codigo == 2 and 'indique los tramos' in informe['obras'][0]['error']
    assert any('cabecera' in a for a in informe['avisos'])


# =========================================================================== T15
def _migracion(f, destino, casos=(CON,)):
    return {'clase': 'tension', 'alimentador': f, 'casos': list(casos), 'kv_destino': destino}


def _sin_grabar(obj, **attrs):
    """Escribe en la red tal como está, fuera de toda variación (lo que ya había)."""
    for k, v in attrs.items():
        object.__setattr__(obj, k, v)


def _colgar(app, elm, barra, clase, nombre, **attrs):
    """Un elemento que ya estaba en el alimentador, conectado a ``barra``."""
    red = barra.GetParent()
    obj = fake_pf.Obj(app, clase, nombre, red)
    red._hijos.append(obj)
    _sin_grabar(obj, **attrs)
    cub = fake_pf.Obj(app, 'StaCubic', f'c_{nombre}', barra)
    barra._hijos.append(cub)
    _sin_grabar(cub, obj_id=obj, obj_bus=0)
    elm._objs.append(obj)
    return obj


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_migracion_barras_lineas_y_sed_a_la_tension_nueva(semilla):
    """011:RF-81, 011:RF-82, 011:RF-83, 011:RF-85, 011:RF-86, 011:RF-99, 011:RF-103 — en el
    caso de la obra, todas las barras de media del alimentador, la de la cabecera incluida,
    pasan a la tensión nueva; cada línea lleva una copia de su tipo a esa tensión; las SED,
    un solo tipo nuevo por tipo original en el que solo cambia la alta. «Sin proyecto» no
    cambia."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    f = rng.choice(alims)
    destino = rng.choice([13.2, 22.9, 33.0])
    sufijo = f'{destino:g}kV'.replace('.', '_')
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(f, destino)]))
    assert codigo == 0, informe
    o = informe['obras'][0]
    assert (o['kv_origen'], o['kv_destino']) == (10.0, destino)
    elm = _elm(app, f)
    cabecera = guion.cabecera_de(elm)

    _activas(app, CON)
    assert cabecera.uknom == destino
    assert {b.uknom for b in elm.GetObjs('ElmTerm')} == {destino}
    for ln in elm.GetObjs('ElmLne'):
        assert ln.typ_id.loc_name == f'AAAC_{f}_{sufijo}' and ln.typ_id.uline == destino
    tipos_sed = {id(tr.typ_id): tr.typ_id for tr in elm.GetObjs('ElmTr2')}
    assert len(tipos_sed) == 1                                   # RF-99
    (nuevo,) = tipos_sed.values()
    assert nuevo.loc_name == f'TR100_{f}_{sufijo}'
    assert (nuevo.utrn_h, nuevo.utrn_l, nuevo.strn) == (destino, 0.38, 0.1)   # RF-103

    _activas(app, SIN)
    assert cabecera.uknom == 10.0 and {b.uknom for b in elm.GetObjs('ElmTerm')} == {10.0}
    assert {tr.typ_id.loc_name for tr in elm.GetObjs('ElmTr2')} == {f'TR100_{f}'}
    original = next(t for t in app.carpetas['equip'].GetContents('*.TypTr2')
                    if t.loc_name == f'TR100_{f}')
    assert original.utrn_h == 10.0                                # RF-59
    assert informe['comprobacion']['diferencias'] == []


def test_migracion_con_un_tipo_compartido_no_toca_al_otro_alimentador():
    """011:RF-97, 011:RF-59 — si otro alimentador usa el mismo tipo de línea, sigue con él a
    la tensión de antes, y sus barras no cambian."""
    app, alims = _calibrada(random.Random(41))
    f, otro = alims[0], alims[1]
    compartido = next(t for t in app.carpetas['equip'].GetContents('*.TypLne')
                      if t.loc_name == f'AAAC_{f}')
    for ln in _elm(app, otro).GetObjs('ElmLne'):
        _sin_grabar(ln, typ_id=compartido)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(f, 22.9, (SIN, CON))]))
    assert codigo == 0, informe
    for caso in (SIN, CON):
        _activas(app, caso)
        assert {ln.typ_id for ln in _elm(app, otro).GetObjs('ElmLne')} == {compartido}
        assert {b.uknom for b in _elm(app, otro).GetObjs('ElmTerm')} == {10.0}
        assert {ln.typ_id.loc_name for ln in _elm(app, f).GetObjs('ElmLne')} == {f'AAAC_{f}_22_9kV'}
    assert getattr(compartido, 'uline', None) is None


def test_migracion_condensadores_y_reguladores_de_media():
    """011:RF-84 — los condensadores de media pasan a la tensión nueva y los de baja se
    quedan; cada regulador lleva una copia de su tipo a esa tensión."""
    app, alims = _calibrada(random.Random(42))
    f = alims[0]
    elm = _elm(app, f)
    b1 = _barra(app, f'{f}_B1')
    _colgar(app, elm, b1, 'ElmShnt', 'BANCO_MT', ushnm=10.0)
    _colgar(app, elm, b1, 'ElmShnt', 'BANCO_BT', ushnm=0.38)
    vr = _tipo(app.carpetas['equip'], 'TypVoltreg', 'VR_10', Un=10.0, pcReg=10.0, ntapmin=-16,
               ntapmax=16, nntap0=0)
    _colgar(app, elm, b1, 'ElmVoltreg', 'VR_EXISTENTE', typ_id=vr)
    _limpio(app)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(f, 22.9)]))
    assert codigo == 0, informe
    _activas(app, CON)
    bancos = {b.loc_name: b.ushnm for b in elm.GetObjs('ElmShnt')}
    assert bancos == {'BANCO_MT': 22.9, 'BANCO_BT': 0.38}
    (reg,) = elm.GetObjs('ElmVoltreg')
    assert reg.typ_id.loc_name == 'VR_10_22_9kV' and reg.typ_id.Un == 22.9 and vr.Un == 10.0


def test_migracion_la_fuente_conserva_su_consigna():
    """011:RF-100, 011:RF-101 — la red externa sigue en la barra de cabecera, ahora a la
    tensión nueva, con su consigna en p.u.; el informe da su valor en kV."""
    app, alims = _calibrada(random.Random(43))
    f = alims[0]
    elm = _elm(app, f)
    cabecera = guion.cabecera_de(elm)
    fuente = _colgar(app, elm, cabecera, 'ElmXnet', f'Red_{f}', usetp=1.02)
    _limpio(app)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(f, 22.9)]))
    assert codigo == 0, informe
    _activas(app, CON)
    assert guion._fuentes_en(cabecera) == [fuente] and fuente.usetp == 1.02
    assert cabecera.uknom == 22.9
    assert any('1.02 p.u.' in a and '23.358 kV' in a for a in informe['obras'][0]['avisos'])


def test_migracion_no_anade_barras_ni_transformadores():
    """011:RF-96 — migrar no crea barras ni transformadores: solo la variación y los tipos."""
    app, alims = _calibrada(random.Random(44))
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(alims[0], 33.0)]))
    assert codigo == 0, informe
    creados = {o.GetClassName() for o in app.creados}
    assert creados <= {'IntScheme', 'IntSstage', 'TypLne', 'TypTr2'}, creados


def test_migracion_con_la_cabecera_compartida_se_rechaza():
    """011:RF-102 — si otro alimentador sale de la misma barra de cabecera, no se migra y se
    nombra ese alimentador."""
    app, alims = _calibrada(random.Random(45))
    f, otro = alims[0], alims[1]
    _sin_grabar(_elm(app, otro), obj_id=_elm(app, f).obj_id)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(f, 22.9)]))
    assert codigo == 2
    assert otro in informe['obras'][0]['error'] and 'no se migra' in informe['obras'][0]['error']
    assert not any(n.startswith('Obra_') for n in _variaciones(app))


def test_la_cabecera_compartida_se_reconoce_con_otro_envoltorio(monkeypatch):
    """011:RF-102 — DIgSILENT da un objeto Python nuevo en cada acceso: dos alimentadores que
    salen de la misma barra de SET por cubículos distintos la comparten aunque la barra no sea
    el mismo objeto (Nasca por sistema, 2026-10-24: la migración de NA203 a 10 kV iba a pasar
    también la barra de la SET 51, de la que salen NA205 y los demás)."""
    app, alims = _calibrada(random.Random(47))
    f, otro = alims[0], alims[1]
    barra = guion.cabecera_de(_elm(app, f))

    class Envoltorio:
        def __init__(self, obj):
            self._obj = obj

        def __getattr__(self, nombre):
            return getattr(self._obj, nombre)

    original = guion.cabecera_de
    monkeypatch.setattr(guion, 'cabecera_de', lambda elm: (
        Envoltorio(barra) if elm.loc_name == otro else original(elm)))
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(f, 22.9)]))
    assert codigo == 2
    assert otro in informe['obras'][0]['error'] and 'no se migra' in informe['obras'][0]['error']


def test_migracion_cambia_la_cabecera_aunque_el_alimentador_no_la_liste():
    """011:RF-86 — la barra de cabecera pasa a la tensión nueva aunque ``ElmFeeder.GetObjs``
    no la devuelva entre sus barras: se toma del cubículo que define el alimentador."""
    app, alims = _calibrada(random.Random(46))
    f = alims[0]
    elm = _elm(app, f)
    cabecera = guion.cabecera_de(elm)
    elm._objs.remove(cabecera)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion(f, 22.9)]))
    assert codigo == 0, informe
    assert cabecera.loc_name in {e['elemento'] for e in informe['obras'][0]['elementos']}
    _activas(app, CON)
    assert cabecera.uknom == 22.9


def test_consigna_de_cabecera_en_su_variacion_de_con_proyecto():
    """019:RF-12 — la red externa de la cabecera queda con la consigna pedida en «Con
    proyecto», en su variación; el flujo converge."""
    app, alims = _calibrada(random.Random(31))
    f = alims[0]
    cabecera = guion.cabecera_de(_elm(app, f))
    fuente = cabecera.GetParent().CreateObject('ElmXnet', f'Red externa {f}')
    cub = cabecera.CreateObject('StaCubic', f'Cub_red_{f}')
    cub.obj_id, cub.obj_bus, fuente.usetp = fuente, 0, 1.0
    obra = {'clase': 'consigna', 'alimentador': f, 'casos': [CON], 'consigna_pu': 1.05}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    fila = informe['obras'][0]
    assert fila['variacion'] and not fila['error'] and fila['casos_activos'] == [CON]
    _activas(app, CON)
    fuentes = guion._fuentes_en(guion.cabecera_de(_elm(app, f)))
    assert fuentes and all(x.usetp == pytest.approx(1.05) for x in fuentes)


# =========================================================================== 025, T19: evaluar
PERFIL_ESCALERA = {
    'escalera': {'cumplimiento': 0.95, 'sorteos': 5, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0},
    'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
    'estudios': {'tension_min_pu': 0.5, 'tension_max_pu': 1.5, 'cargabilidad_max_pct': 1000},
}


def _calibrada_con_escenario(rng):
    alims = tuple(f'F{i}' for i in range(1, rng.randint(2, 3) + 1))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=3, bt=True, flujo=True, escenario=True)
    base = {'variaciones': [], 'feeders': list(alims), 'excluidos': [],
            'ajustes': [{'feeder': f, 'cuadrado': True} for f in alims]}
    informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': list(alims), 'base': base,
                                              'caso_base_sin_verificar': {}})
    assert codigo == 0, informe
    return app, list(alims)


def _actual_no_cumple(monkeypatch):
    """«Con proyecto» tal como está no cumple (en la red real lo impiden las cargas nuevas):
    la primera comparación, la del estado actual (025:RF-74), sale que no."""
    from igea_dgs import escalera_optima

    original = escalera_optima.cumple
    llamadas = []

    def cumple(sin, con, barras, p):
        llamadas.append(1)
        return (False, ['sin obra']) if len(llamadas) == 1 else original(sin, con, barras, p)

    monkeypatch.setattr(escalera_optima, 'cumple', cumple)


def test_si_con_proyecto_ya_cumple_no_se_prueba_ninguna_variante(monkeypatch):
    """025:RF-74 — con «Con proyecto» cumpliendo tal como está (la obra de una escalera anterior),
    no se crea ninguna variante y se dice que ya cumple."""
    app, alims = _calibrada_con_escenario(random.Random(41))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    f = alims[0]
    antes = (_activas(app, SIN), _activas(app, CON), _variaciones(app))
    creadas = []
    aplicar = guion.aplicar
    monkeypatch.setattr(guion, 'aplicar', lambda *a, **k: (creadas.append(1), aplicar(*a, **k))[1])
    sorteos = [{'factores': {a: 0.9 for a in alims}} for _ in range(3)]
    plan = _plan(alims, variantes=[{'nombre': 'terna', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0}],
                 sorteos=sorteos, barras_cargas=[], parametros=PERFIL_ESCALERA)
    informe, codigo = guion.evaluar(app, plan)
    assert codigo == 0, informe
    assert informe['ya_cumple']['fraccion'] == 1.0 and informe['variantes'] == [] and creadas == []
    assert (_activas(app, SIN), _activas(app, CON), _variaciones(app)) == antes


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_evaluar_variantes_sin_dejar_nada(semilla, monkeypatch):
    """025:RF-50, 025:RF-52b, 025:RF-44b — cada variante en «Con proyecto»: con la máxima y, si
    cumple, en los sorteos; la que no converge no se sortea. Al terminar no queda ninguna obra,
    ni el escenario temporal, y «Sin proyecto» y «Con proyecto» siguen como estaban."""
    rng = random.Random(semilla)
    app, alims = _calibrada_con_escenario(rng)
    _actual_no_cumple(monkeypatch)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'condensador', _sobrecarga)
    f = alims[0]
    antes = (_activas(app, SIN), _activas(app, CON), _variaciones(app))
    escenarios = {e.loc_name for e in app.GetProjectFolder('scen', 1).GetContents('*.IntScenario')}
    sorteos = [{'factores': {a: rng.uniform(0.5, 1.0) for a in alims}} for _ in range(5)]
    plan = _plan(alims, variantes=[{'nombre': 'terna', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0},
                                   {'nombre': 'no converge', 'obras': [_banco(f, [CON])], 'costo_base': 1.0}],
                 sorteos=sorteos, barras_cargas=[], parametros=PERFIL_ESCALERA)
    informe, codigo = guion.evaluar(app, plan)
    assert codigo == 0, informe
    filas = {v['nombre']: v for v in informe['variantes']}
    assert filas['terna']['maxima'] and filas['terna']['fraccion'] == 1.0, filas['terna']
    assert not filas['no converge']['maxima'] and filas['no converge']['fraccion'] is None
    assert (_activas(app, SIN), _activas(app, CON), _variaciones(app)) == antes
    assert {e.loc_name for e in app.GetProjectFolder('scen', 1).GetContents('*.IntScenario')} == escenarios


def test_los_sorteos_escalan_solo_las_cargas_existentes_y_se_restituyen(monkeypatch):
    """025:RF-51, 025:RF-52 — en cada sorteo, la demanda de cada carga existente por el factor
    de su alimentador, en un escenario temporal; al terminar, la de siempre."""
    app, alims = _calibrada_con_escenario(random.Random(9))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    f = alims[0]
    carga = next(c for c in app.proyecto.GetContents('*.ElmLod', 1) if c.loc_name.startswith(f))
    p0 = float(carga.plini)
    vistos = []
    medir = guion.medida_para_criterio

    def registrar(app_, alims_, feeders):
        vistos.append((getattr(app_.GetActiveScenario(), 'loc_name', ''), float(carga.plini)))
        return medir(app_, alims_, feeders)

    monkeypatch.setattr(guion, 'medida_para_criterio', registrar)
    sorteos = [{'factores': {a: 0.5 for a in alims}}, {'factores': {a: 0.8 for a in alims}}]
    plan = _plan(alims, variantes=[{'nombre': 'terna', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0}],
                 sorteos=sorteos, barras_cargas=[], parametros=PERFIL_ESCALERA)
    informe, codigo = guion.evaluar(app, plan)
    assert codigo == 0, informe
    en_sorteo = [(e, p) for e, p in vistos if e.startswith('IGEA_sorteo_escalera')]
    assert [round(p / p0, 6) for _, p in en_sorteo] == [0.5, 0.8, 0.5, 0.8]
    assert float(carga.plini) == p0

def test_datos_de_la_escalera_troncal_corriente_y_tramo_de_cada_carga():
    """025:RF-49, 025:RF-60 — en «Con proyecto», la troncal de cada alimentador desde la
    cabecera, como la lee la obra, con su largo y una corriente por tramo, y el tramo de la
    troncal donde cae cada barra pedida; las cargas nuevas vuelven a quedar activas."""
    app, alims = _calibrada_con_escenario(random.Random(12))
    f = alims[0]
    antes = _activas(app, CON)
    elm = next(e for e in app.proyecto.GetContents('*.ElmFeeder', 1) if e.loc_name == f)
    esperada = guion.leer_troncal(elm, f)[0]
    con_gps = [b.loc_name for b in elm.GetObjs('ElmTerm') if guion.gps_de(b)]
    informe, codigo = guion.datos_escalera(app, _plan(alims, barras={f: con_gps[-1:]}, tension_min_pu=0.95))
    assert codigo == 0, informe
    d = informe['alimentadores'][f]
    assert [t['nombre'] for t in d['troncal']] == list(esperada)
    assert all(t['largo_m'] >= 0 and 'corriente_a' in t for t in d['troncal'])
    if con_gps:
        assert set(d['indices']) == set(con_gps[-1:]) and 0 <= d['indices'][con_gps[-1]] < len(esperada)
    assert _activas(app, CON) == antes
    assert informe['variaciones_activas'] == sorted(antes)                    # 025:RF-73

def test_al_evaluar_un_alimentador_se_apartan_las_cargas_de_los_otros(monkeypatch):
    """025:RF-69 — mientras se evalúa F1, las cargas nuevas de F2 (sin resolver) están apartadas
    en «Con proyecto»; al terminar vuelven a estar activas."""
    from test_casos_pf import cargas_guion
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas

    app, alims = _calibrada_con_escenario(random.Random(21))
    f1, f2 = alims[0], alims[1]
    nuevas = [_nueva('N1', barra=f'{f1}_B2', tension_bt_kv=0.38), _nueva('N2', barra=f'{f2}_B2', tension_bt_kv=0.38)]
    base = {'variaciones': [], 'feeders': list(alims), 'excluidos': [],
            'ajustes': [{'feeder': f, 'cuadrado': True} for f in alims]}
    informe, rc = cargas_guion.ejecutar(app, {**_plan_cargas(list(alims), nuevas=nuevas), 'base': base}, simular=False)
    assert rc == 0, informe
    de_f2 = next(c['variacion'] for c in informe['cargas'] if c['sed'] == 'N2')
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    vistas = []
    medir = guion.medida_para_criterio

    def registrar(app_, alims_, feeders):
        vistas.append({v.loc_name for v in app_.GetActiveNetworkVariations() or []})
        return medir(app_, alims_, feeders)

    monkeypatch.setattr(guion, 'medida_para_criterio', registrar)
    plan = _plan([f1], variantes=[{'nombre': 'terna', 'obras': [_obra_terna(f1, [CON])]}], sorteos=[],
                 barras_cargas=[], parametros=PERFIL_ESCALERA, apartar_cargas_de=[f2])
    resultado, codigo = guion.evaluar(app, plan)
    assert codigo == 0, resultado
    assert vistas and all(de_f2 not in v for v in vistas)
    assert de_f2 in _activas(app, CON)


@pytest.mark.parametrize('apartar', [True, False])
def test_la_elegida_se_comprueba_con_las_cargas_de_los_otros_apartadas(monkeypatch, apartar):
    """025:RF-69 — al aplicar la elegida de F1 su flujo se comprueba con las cargas nuevas de F2
    apartadas, y la obra queda activa en «Con proyecto» aunque con las de F2 no converja; al
    terminar, las de F2 vuelven a estar activas. Sin apartarlas, la obra queda inactiva."""
    from test_casos_pf import cargas_guion
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas

    app, alims = _calibrada_con_escenario(random.Random(22))
    f1, f2 = alims[0], alims[1]
    nuevas = [_nueva('N1', barra=f'{f1}_B2', tension_bt_kv=0.38), _nueva('N2', barra=f'{f2}_B2', tension_bt_kv=0.38)]
    base = {'variaciones': [], 'feeders': list(alims), 'excluidos': [],
            'ajustes': [{'feeder': f, 'cuadrado': True} for f in alims]}
    informe, rc = cargas_guion.ejecutar(app, {**_plan_cargas(list(alims), nuevas=nuevas), 'base': base}, simular=False)
    assert rc == 0, informe
    de_f2 = next(c['variacion'] for c in informe['cargas'] if c['sed'] == 'N2')
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    flujo = guion.flujo_de_carga

    def sin_converger_con_f2(app_):
        activas = {v.loc_name for v in app_.GetActiveNetworkVariations() or []}
        return {**flujo(app_), 'converged': False} if de_f2 in activas else flujo(app_)

    monkeypatch.setattr(guion, 'flujo_de_carga', sin_converger_con_f2)
    plan = _plan([f1], obras=[_obra_terna(f1, [CON])], **({'apartar_cargas_de': [f2]} if apartar else {}))
    informe, _codigo = guion.aplicar(app, plan)
    (obra,) = informe['obras']
    assert (CON in obra['casos_activos']) is apartar
    assert de_f2 in _activas(app, CON)


def test_perdidas_con_lo_que_consumen_las_cargas_en_el_flujo(monkeypatch):
    """025:RF-70 — pérdidas = lo que entra por la cabecera − lo que consumen las cargas en el
    flujo (``m:Psum:bus1``), no su potencia nominal."""
    from types import SimpleNamespace

    from igea_dgs.ajuste_cabecera import Medida

    cargas = [SimpleNamespace(outserv=0, plini=9.0, GetAttribute=lambda a, p=p: p) for p in (0.4, 0.5)]
    elm = SimpleNamespace(GetObjs=lambda clase: cargas if clase == 'ElmLod' else [])
    alims = SimpleNamespace(elm={'F1': elm}, objetos=lambda f, clase: [])
    monkeypatch.setattr(guion, 'flujo_de_carga', lambda app: {'converged': True})
    monkeypatch.setattr(guion, 'leer_cabecera', lambda e: Medida(True, 950.0, 300.0))
    m = guion.medida_para_criterio(None, alims, ['F1'])
    assert m['perdidas_kw'] == pytest.approx(950.0 - 900.0)

def test_sorteos_de_la_mas_barata_a_la_mas_cara_hasta_la_primera_que_cumple(monkeypatch):
    """025:RF-71, 025:RF-72 — se sortean solo las que cumplen con la máxima y tienen costo, de la
    más barata a la más cara; la que no llega deja de sortearse en cuanto ya no puede, y tras la
    primera que cumple las más caras no se sortean; la que no tiene costo tampoco."""
    import contextlib

    from igea_dgs import escalera_optima

    app, alims = _calibrada_con_escenario(random.Random(31))
    actual, sorteadas, medidas = {}, [], {'n': 0}

    def aplicar(app_, sub):
        actual['v'] = sub['obras'][0]['tramos'][0]
        return {'obras': [{'variacion': None}]}, 0

    def medir(app_, alims_, feeders):
        medidas['n'] += 1
        return {'converge': True, 'u': {}, 'carga': {}, 'perdidas_kw': 10.0}

    def cumple(sin, con, barras, p):
        if 'v' not in actual:                          # «Con proyecto» sin obra (025:RF-74)
            return (False, ['sin obra'])
        return (actual.get('en_sorteo') != 'barata', [])

    class Sorteo:
        def __init__(self, *a):
            pass

        def __enter__(self):
            actual['en_sorteo'] = actual.get('v', 'sin proyecto')
            sorteadas.append(actual['en_sorteo'])
            return self

        def escalar(self, factores):
            pass

        def __exit__(self, *e):
            actual['en_sorteo'] = None
            return False

    monkeypatch.setattr(guion, 'aplicar', aplicar)
    monkeypatch.setattr(guion, 'medida_para_criterio', medir)
    monkeypatch.setattr(guion, '_Sorteo', Sorteo)
    monkeypatch.setattr(escalera_optima, 'cumple', cumple)
    f = alims[0]
    variantes = [{'nombre': n, 'obras': [{'clase': 'terna', 'alimentador': f, 'casos': [CON], 'tramos': [n]}],
                  'costo_base': c} for n, c in (('cara', 300.0), ('barata', 100.0), ('media', 200.0), ('sin', None))]
    sorteos = [{'factores': {a: 1.0 for a in alims}} for _ in range(40)]
    informe, codigo = guion.evaluar(app, _plan(alims, variantes=variantes, sorteos=sorteos, barras_cargas=[],
                                               parametros=PERFIL_ESCALERA, costo_por_kw_perdido=1.0))
    assert codigo == 0, informe
    assert sorteadas[1:] == ['barata', 'media']             # el primero es el de «Sin proyecto»
    filas = {v['nombre']: v for v in informe['variantes']}
    assert filas['media']['fraccion'] == 1.0 and filas['barata']['fraccion'] < 0.95
    # RF-72: la barata dejó de sortearse al pasar los 2 fallos que admite el 95 % de 40.
    assert medidas['n'] < 1 + 40 + 4 + 40 + 40
    assert 'cuesta menos' in filas['cara']['sin_sortear'] and filas['cara']['fraccion'] is None
    assert 'sin costo' in filas['sin']['sin_sortear']

def test_tipo_de_otro_proyecto_que_no_se_deja_pegar_se_copia_igual():
    """025:RF-59 — si DIgSILENT no deja pegar el tipo del proyecto biblioteca (``PasteCopy``
    con código 1, Pisco 2026-10-24), se copia de otra forma, con los mismos datos."""
    app, alims = _calibrada(random.Random(5))
    _prj, equip_otro = _otro_proyecto(app, 'IGEA_Biblioteca_tipos')
    original = _tipo(equip_otro, 'TypVoltreg', 'VR32_22_9kV_300A', Un=13.2213, In=300.0, pcReg=10.0,
                     ntapmin=-16, ntapmax=16, nntap0=0)
    local = app.GetLocalLibrary('TypVoltreg')
    object.__setattr__(local, 'PasteCopy', lambda _o: (1, None))
    copia, reutiliza, _aviso = guion.copiar_tipo(app, original, 'VR32_22_9kV_300A')
    assert not reutiliza and copia.GetParent() is local
    assert (copia.Un, copia.In, copia.ntapmax) == (13.2213, 300.0, 16)