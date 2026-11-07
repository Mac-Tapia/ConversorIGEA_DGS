"""Spec 049, T2: plan de fallas y ``tools/protecciones_pf.py`` contra ``fake_pf``.

Proyectos, dispositivos, tiempos y generación sorteados; ninguna curva ni ajuste de una empresa.
Estas pruebas no cierran la evidencia nativa: esa es la T4, con DIgSILENT real.
"""

from __future__ import annotations

import hashlib
import json
import random

import pytest

import fake_pf
from apoyo import cargar_herramienta, contexto_nativo
from convertersmartgrid import protecciones as pr
from convertersmartgrid.experimentos import ContextoExperimento

guion = cargar_herramienta('protecciones_pf.py', 'protecciones_049', tools_en_path=True)

SEMILLAS = (5, 31, 77, 140)


def _h(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _contexto(feeders, rol='sin_proyecto', caso='Caso'):
    return ContextoExperimento(
        source_run_id='run-1', source_mode='txt', source_fingerprint=_h('fuente'), project='P',
        feeders=tuple(feeders), case_id=caso, case_role=rol, year=2026, period='2026-07',
        criterio_fijas='coincidente', profile_hash=_h('perfil'), topology_hash=_h('red'),
        controls_hash=_h('controles'), scenario_hash=_h('escenario'))


def _red(rng):
    """Proyecto con un relé de cabecera y fusibles aguas abajo en cada alimentador, la red
    externa y una central térmica; cada dispositivo con lo que vería en cada falla."""
    alims = tuple(f'F{i}' for i in range(1, rng.randint(1, 3) + 1))
    n = rng.randint(2, 4)
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=n)
    red = next(o for o in app.proyecto.GetContents('*.ElmNet'))
    red.CreateObject('ElmXnet', 'Externa')
    termica = red.CreateObject('ElmSym', f'Termica_{rng.randrange(99)}')
    termica.outserv = 0
    dispositivos, fallas = [], []
    for f in alims:
        rele = red.CreateObject('ElmRelay', f'R_{f}')
        dispositivos.append({'id': rele.loc_name, 'cubiculo': f'c_{f}_L1', 'clase': 'rele', 'fabricante': 'X',
                             'modelo': 'Y', 'curva': 'IEC NI', 'arranque': round(rng.uniform(50, 300), 1),
                             'unidad_arranque': 'A', 'dial': round(rng.uniform(0.05, 0.5), 2), 'unidad_dial': 'dial',
                             'poder_corte_ka': 20.0, 'fuente': 'ficha'})
        for i in range(1, n + 1):
            fus = red.CreateObject('RelFuse', f'FU_{f}_{i}')
            dispositivos.append({'id': fus.loc_name, 'cubiculo': f'c_{f}_L{i}', 'clase': 'fusible', 'fabricante': 'X',
                                 'modelo': 'K', 'curva': 'K', 'arranque': rng.choice([10, 25, 40]),
                                 'unidad_arranque': 'A', 'poder_corte_ka': 8.0, 'fuente': 'ficha',
                                 'respalda_a': []})
            dispositivos[-1 - i]['respalda_a'] = dispositivos[-1 - i].get('respalda_a', []) + [fus.loc_name]
            barra = f'{f}_B{i}'
            for tipo in ('3psc', '2psc'):
                t_fus = round(rng.uniform(0.01, 0.2), 3)
                fus.tiempos[(barra, tipo)] = t_fus
                fus.corrientes[(barra, tipo)] = rng.uniform(500, 3000)
                rele.tiempos[(barra, tipo)] = round(t_fus + rng.uniform(0.1, 0.6), 3)
                rele.corrientes[(barra, tipo)] = rng.uniform(500, 3000)
            fallas.append({'id': f'{barra}_3f', 'tipo': 'trifasica', 'ubicacion': barra, 'r_ohm': 0, 'x_ohm': 0,
                           'protegen': [fus.loc_name]})
    app.ordenes['ComShc'] = fake_pf.Cortocircuito(app)
    app.ordenes['ComShctrace'] = fake_pf.TrazaCortocircuito(app)
    app.escrituras.clear()
    return app, list(alims), dispositivos, fallas


def _plan_capacidades(feeders, **extra):
    return {'project': 'P', 'feeders': list(feeders), 'ejecutar_ordenes': True,
            'native_action_context': contexto_nativo('P', feeders, 'protecciones'), **extra}


def _inventario(app, feeders, dispositivos, **extra):
    capacidades, codigo = guion.capacidades(app, _plan_capacidades(feeders), version='24.0.1')
    assert codigo == 0, capacidades
    return {'dispositivos': dispositivos, 'generacion': capacidades['generacion'], 'capacidades': capacidades,
            'impedancia_real': True, **extra}, capacidades


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_capacidades_inventaria_la_version_conectada(semilla):
    """049:RF-1 — el modo de capacidades dice qué órdenes, métodos, atributos y dispositivos
    hay en la versión conectada; con eso, y solo con eso, la disponibilidad deja de bloquear."""
    rng = random.Random(semilla)
    app, feeders, dispositivos, _ = _red(rng)
    inventario, cap = _inventario(app, feeders, dispositivos)
    assert cap['version'] == '24.0.1' and cap['caso'] == 'Caso'
    assert cap['comandos']['ComShc']['existe'] and cap['comandos']['ComShc']['ejecuta'] is True
    assert all(cap['comandos']['ComShc']['atributos'].values())
    assert all(cap['comandos']['ComShctrace']['metodos'][m] for m in pr.METODOS_REQUERIDOS['ComShctrace'])
    assert cap['comandos']['ComProtgraphic']['existe'] is False
    assert cap['clases']['ElmRelay']['cuantos'] == len(feeders)
    assert set(cap['clases']['RelFuse']['nombres']) == {d['id'] for d in dispositivos if d['clase'] == 'fusible'}
    assert {g['clase'] for g in cap['generacion']} == {'ElmXnet', 'ElmSym'}
    perfil = {'protecciones': {'cti_s': 0.3, 'factor_sensibilidad': 2.0, 'margen_poder_corte': 1.1}}
    assert pr.disponibilidad_protecciones(inventario, cap, perfil)['disponible']
    # Sin traza en la versión conectada, o con el cortocircuito rechazado por licencia: bloquea.
    del app.ordenes['ComShctrace']
    app.ordenes['ComShc'] = fake_pf.Cortocircuito(app, rc=1)
    cap, _ = guion.capacidades(app, _plan_capacidades(feeders), version='24.0.1')
    d = pr.disponibilidad_protecciones(inventario, cap, perfil)
    assert any('ComShctrace' in b for b in d['bloqueos'])
    assert any('licencia' in b and 'ComShc' in b for b in d['bloqueos'])
    assert app.escrituras == []                                   # inventariar no escribe nada


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_generacion_existente_aporta(semilla):
    """049:RF-4 — el plan conserva la red externa y la central con su estado; una central
    modelada como carga negativa se rechaza, y si la generación cambia el guion no estudia
    otra red."""
    rng = random.Random(semilla)
    app, feeders, dispositivos, fallas = _red(rng)
    inventario, _cap = _inventario(app, feeders, dispositivos)
    plan = pr.plan_protecciones(_contexto(feeders), inventario, fallas)
    assert {(a['clase'], a['en_servicio']) for a in plan['aportes']} == {('ElmXnet', True), ('ElmSym', True)}
    informe, codigo = guion.ejecutar(app, plan)
    assert codigo == 0, informe
    assert informe['aportes'] == plan['aportes']
    # La térmica sale de servicio después de preparar el plan: no se estudia otra red.
    next(o for o in app.proyecto.GetContents('*.ElmSym', 1)).outserv = 1
    informe, codigo = guion.ejecutar(app, plan)
    assert codigo == 2 and 'generación' in informe['error']
    # Una central como carga negativa no aporta corriente de falla.
    negativa = dict(inventario, generacion=inventario['generacion'] + [
        {'nombre': 'Central_negativa', 'clase': 'ElmLod', 'modelo': 'carga_negativa', 'en_servicio': True}])
    with pytest.raises(pr.ProteccionesError, match='carga negativa'):
        pr.plan_protecciones(_contexto(feeders), negativa, fallas)
    carga = next(o for o in app.proyecto.GetContents('*.ElmLod', 1))
    carga.plini = -abs(rng.uniform(0.1, 2))
    assert any(g.get('modelo') == 'carga_negativa' for g in guion.capacidades(
        app, _plan_capacidades(feeders), version='x')[0]['generacion'])


def test_unidades_y_relaciones_requeridas():
    """049:RF-3, 049:RF-4 — un arranque en amperios secundarios sin la relación del TC, una
    unidad que no existe o una falla sin impedancia se rechazan con la lista entera."""
    rng = random.Random(8)
    app, feeders, dispositivos, fallas = _red(rng)
    inventario, _cap = _inventario(app, feeders, dispositivos)
    rele = next(d for d in inventario['dispositivos'] if d['clase'] == 'rele')
    rele['unidad_arranque'] = 'A sec'
    fusible = next(d for d in inventario['dispositivos'] if d['clase'] == 'fusible')
    fusible['unidad_arranque'] = 'kA'
    mal = dict(fallas[0])
    del mal['x_ohm']
    with pytest.raises(pr.ProteccionesError) as e:
        pr.plan_protecciones(_contexto(feeders), inventario, [mal, *fallas[1:]])
    texto = str(e.value)
    assert 'primario del TC' in texto and 'secundario del TC' in texto and rele['id'] in texto
    assert 'kA' in texto and fusible['id'] in texto
    assert 'x_ohm' in texto
    rele.update(ct_primario_a=200, ct_secundario_a=5)
    fusible['unidad_arranque'] = 'A'
    a_tierra = dict(fallas[0], tipo='monofasica', fase='a')
    with pytest.raises(pr.ProteccionesError, match='secuencia cero'):
        pr.plan_protecciones(_contexto(feeders), dict(inventario, impedancia_real=False), [a_tierra])
    with pytest.raises(pr.ProteccionesError, match='su fase'):
        pr.plan_protecciones(_contexto(feeders), inventario, [dict(a_tierra, fase=None)])
    # Atributos de ComShc sin comprobar en la versión conectada: no se escriben a ciegas.
    sin_atributos = json.loads(json.dumps(inventario))
    sin_atributos['capacidades']['comandos']['ComShc']['atributos']['shcobj'] = False
    with pytest.raises(pr.ProteccionesError, match='shcobj'):
        pr.plan_protecciones(_contexto(feeders), sin_atributos, fallas)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_fallas_capturan_tiempos_y_secuencia(semilla):
    """049:RF-4 — cada falla da el tiempo previsto de cada dispositivo, el que dispara y la
    secuencia; una falla que no se puede definir queda no evaluada sin tumbar las demás, y la
    configuración de ComShc vuelve a la de antes."""
    rng = random.Random(semilla)
    app, feeders, dispositivos, fallas = _red(rng)
    inventario, _cap = _inventario(app, feeders, dispositivos)
    fallas.append({'id': 'Z_inexistente', 'tipo': 'trifasica', 'ubicacion': 'NO_ESTA', 'r_ohm': 0, 'x_ohm': 0})
    shc = app.ordenes['ComShc']
    antes = {a: getattr(shc, a) for a in pr.ATRIBUTOS_COMSHC.values()}
    informe, codigo = guion.ejecutar(app, pr.plan_protecciones(_contexto(feeders), inventario, fallas))
    assert codigo == 0, informe
    por_id = {f['id']: f for f in informe['fallas']}
    assert por_id['Z_inexistente']['estado'] == 'no_evaluada' and 'NO_ESTA' in por_id['Z_inexistente']['motivo']
    for falla in fallas[:-1]:
        r = por_id[falla['id']]
        assert r['estado'] == 'evaluada', r
        tiempos = {d['id']: d for d in r['dispositivos']}
        fus, = falla['protegen']
        rele = f"R_{falla['ubicacion'].split('_')[0]}"
        assert tiempos[fus]['estado'] == 'disparo'
        assert tiempos[rele]['tiempo_s'] > tiempos[fus]['tiempo_s'] and tiempos[rele]['estado'] == 'arranco'
        assert r['secuencia'] and r['secuencia'][-1]['disparados'] == [fus]
    assert {a: getattr(shc, a) for a in pr.ATRIBUTOS_COMSHC.values()} == antes
    assert app.caso.loc_name == 'Caso'


def test_ajuste_no_toca_base():
    """049:RF-8, 049:RF-9 — los ajustes propuestos van solo a una variación nueva, que queda
    desactivada hasta validarlos; sobre el «Caso base» no se plantean, y el informe no los da por
    persistidos sin reabrir y releer en DIgSILENT (eso lo cierra la T4, con el motor real)."""
    rng = random.Random(12)
    app, feeders, dispositivos, fallas = _red(rng)
    ajustes = [{'dispositivo': dispositivos[0]['id'], 'atributo': 'Tpset', 'valor': 0.2, 'unidad': 's'}]
    inventario, _cap = _inventario(app, feeders, dispositivos, ajustes=ajustes)
    with pytest.raises(pr.ProteccionesError, match='Caso base'):
        pr.plan_protecciones(_contexto(feeders, rol='caso_base'), inventario, fallas)
    plan = pr.plan_protecciones(_contexto(feeders), inventario, fallas)
    assert plan['escritura']['solo_variacion'] and plan['escritura']['ajustes'] == ajustes
    app.atributos_en_variacion = True
    informe, codigo = guion.ejecutar(app, plan)
    assert codigo == 0, informe
    variacion = next(v for v in app.carpetas['scheme'].GetContents('*.IntScheme')
                     if v.loc_name == informe['variacion'])
    escritas = [(etapa, valor) for obj, attr, valor, etapa, _esc in app.escrituras
                if obj.loc_name == ajustes[0]['dispositivo'] and attr == 'Tpset']
    assert escritas and all(etapa is not None and etapa._padre is variacion for etapa, _v in escritas)
    assert variacion not in app.variaciones_activas
    rele = next(o for o in app.proyecto.GetContents('*.ElmRelay', 1) if o.loc_name == ajustes[0]['dispositivo'])
    assert getattr(rele, 'Tpset', None) is None                # fuera de la variación, como estaba
    assert informe['persistencia']['estado'] == 'sin_verificar'
    sin_ajustes, _ = guion.ejecutar(app, pr.plan_protecciones(_contexto(feeders), dict(inventario, ajustes=[]), fallas))
    assert 'persistencia' not in sin_ajustes and 'variacion' not in sin_ajustes


def test_main_sin_contexto_nativo_no_abre_digsilent(tmp_path):
    """049:RF-1 — un plan sin el contexto firmado de la acción «protecciones» se rechaza antes
    de conectar con DIgSILENT."""
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'project': 'P', 'feeders': ['F1']}), encoding='utf-8')
    salida = tmp_path / 'informe.json'
    assert guion.main(['--capacidades', '--plan', str(plan), '--output-json', str(salida)]) == 2
    assert json.loads(salida.read_text(encoding='utf-8'))['status'] == 'BLOQUEADO_DATOS'
