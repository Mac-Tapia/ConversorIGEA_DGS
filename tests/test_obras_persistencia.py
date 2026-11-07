"""Spec 048, T4a: las obras elegidas persisten en sus variaciones sin tocar el caso de referencia (RF-9).

``tools/obras_pf.py`` aplica las obras como siempre (spec 011) y, al terminar, reabre el proyecto y relee: cada
obra sigue en su variación, con lo que grabó y activa solo en los casos donde quedó, y el «Caso base» (y «Sin
proyecto», si ninguna obra es de allí) tienen la misma foto que antes. Aquí, con el DIgSILENT simulado
``fake_pf``; la reapertura nativa con el motor real es la T4 [DIgSILENT] (``test_optimizacion_mixta_nativa.py``).
"""
from __future__ import annotations

import random

import pytest
from test_obras_pf_guion import (
    BASE, CON, SIN, SEMILLAS, _activas, _banco, _calibrada, _obra_terna, _plan, _terna, _tipo,
    _toca_a_otro, _variaciones, guion,
)

from convertersmartgrid.obras_pf import foto_de_referencia, veredicto_persistencia


def _seccion(ctx):
    (copia,) = ctx.tipos.values()
    for e in ctx.fila['elementos']:
        ctx.objeto('ElmLne', e['elemento']).typ_id = copia


def _con_seccion(app, f):
    _tipo(app.GetGlobalLibrary(), 'TypLne', 'AAAC_120', uline=22.9, sline=0.36, qurs=120.0)
    return {'clase': 'seccion', 'alimentador': f, 'casos': [CON], 'tramos': [f'{f}_L1'],
            'tipo': {'nombre': 'AAAC_120', 'clase': 'TypLne', 'origen': 'global'}}


# --------------------------------------------------------------------------- con el guion
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_obras_persisten_sin_tocar_referencia(semilla, monkeypatch):
    """048:RF-9 — tras aplicar, el proyecto se reabre y se relee: cada obra está en su variación, con lo que
    grabó, activa solo en «Con proyecto»; el «Caso base» y «Sin proyecto» tienen la misma foto que antes."""
    rng = random.Random(semilla)
    app, alims = _calibrada(rng)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    monkeypatch.setitem(guion.CONSTRUCTORES, 'seccion', _seccion)
    elegidos = sorted(rng.sample(alims, rng.randint(1, len(alims))))
    obras = [_obra_terna(f, [CON]) for f in elegidos] + [_con_seccion(app, elegidos[0])]
    reaperturas = []
    original = guion.activar_proyecto
    monkeypatch.setattr(guion, 'activar_proyecto',
                        lambda a, r, c=None: reaperturas.append(a.GetActiveProject()) or original(a, r, c))
    inicial = app.GetActiveStudyCase()

    informe, codigo = guion.aplicar(app, _plan(alims, obras=obras))
    assert codigo == 0, informe
    persistencia = informe['persistencia']
    assert persistencia['ok'] is True, persistencia
    assert persistencia['reabierto'] is True
    assert None in reaperturas[1:], 'el proyecto no se desactivó antes de releer'
    assert app.GetActiveProject() is app.proyecto and app.GetActiveStudyCase() is inicial
    assert sorted(persistencia['referencias']) == [BASE, SIN]
    for ref in persistencia['referencias'].values():
        assert ref['igual'] is True and ref['antes'] == ref['despues'] and ref['cambios'] == []
    assert [o['variacion'] for o in persistencia['obras']] == [o['variacion'] for o in informe['obras']]
    for o in persistencia['obras']:
        assert o['ok'] and o['existe'] and o['objetos'] > 0 and o['activa_en'] == [CON], o
        assert o['variacion'] in _variaciones(app)
    # Lo que se releyó es lo que hay: con «Con proyecto», las obras; con «Sin proyecto», la red de antes.
    _activas(app, CON)
    lineas = {ln.loc_name: ln for ln in app.proyecto.GetContents('*.ElmLne', 1)}
    assert all(lineas[f'{f}_L1'].nlnum == 2 for f in elegidos)
    assert lineas[f'{elegidos[0]}_L1'].typ_id.loc_name == 'AAAC_120_10kV'
    _activas(app, SIN)
    assert all(lineas[f'{f}_L1'].nlnum == 1 for f in elegidos)


def test_una_obra_que_toca_la_referencia_no_persiste_limpia(monkeypatch):
    """048:RF-9 — si una obra cambia algo fuera de su variación, la foto de «Sin proyecto» lo dice con el
    elemento y el valor, y la aplicación no se da por buena."""
    app, alims = _calibrada(random.Random(41))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _toca_a_otro)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [CON])]))
    assert codigo == 2
    persistencia = informe['persistencia']
    assert persistencia['ok'] is False
    sin = persistencia['referencias'][SIN]
    assert sin['igual'] is False and sin['antes'] != sin['despues']
    otro = next(a for a in alims if a != alims[0])
    assert any(otro in c and 'plini' in c for c in sin['cambios']), sin['cambios']
    assert any('«Sin proyecto»' in a and '048:RF-9' in a for a in informe['avisos'])


def test_la_variacion_que_no_vuelve_al_reabrir_se_dice(monkeypatch):
    """048:RF-9 — una variación que no está al reabrir (DIgSILENT no la guardó) no persiste: la obra lo dice."""
    app, alims = _calibrada(random.Random(43))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    original = guion.activar_proyecto
    llamadas = []

    def reabrir_sin_guardar(a, r, c=None):
        llamadas.append(r)
        prj = original(a, r, c)
        if len(llamadas) > 1:                    # la reapertura, no la primera activación
            for v in a.carpetas['scheme'].GetContents('*.IntScheme'):
                if v.loc_name.startswith('Obra_terna'):
                    v.Delete()
        return prj

    monkeypatch.setattr(guion, 'activar_proyecto', reabrir_sin_guardar)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [CON])]))
    assert codigo == 2
    (o,) = informe['persistencia']['obras']
    assert o['ok'] is False and o['existe'] is False and 'no está' in o['motivo']


def test_la_obra_inactiva_por_no_converger_persiste_inactiva(monkeypatch):
    """048:RF-9, 011:RF-66 — la obra que no converge se conserva inactiva: persiste, sin estar activa en ningún caso."""
    from test_obras_pf_guion import _sobrecarga

    app, alims = _calibrada(random.Random(47))
    app.ldf.limite = 5.0
    monkeypatch.setitem(guion.CONSTRUCTORES, 'condensador', _sobrecarga)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_banco(alims[0], [CON])]))
    assert codigo == 2                                   # por el flujo, no por la persistencia
    (o,) = informe['persistencia']['obras']
    assert o['ok'] and o['existe'] and o['objetos'] > 0 and o['activa_en'] == []
    assert informe['persistencia']['ok'] is True


def test_con_obras_en_sin_proyecto_la_referencia_es_el_caso_base(monkeypatch):
    """048:RF-9, 011:RF-58 — una obra también de «Sin proyecto» lo cambia a propósito: la referencia es el «Caso
    base», donde ninguna obra se activa nunca."""
    app, alims = _calibrada(random.Random(53))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [SIN, CON])]))
    assert codigo == 0, informe
    persistencia = informe['persistencia']
    assert list(persistencia['referencias']) == [BASE] and persistencia['ok']
    (o,) = persistencia['obras']
    assert o['activa_en'] == [SIN, CON]


def test_simular_y_evaluar_no_releen(monkeypatch):
    """048:RF-9, 011:RF-69, 025:RF-49 — simular no escribe y las variantes de la escalera se borran: nada que releer."""
    app, alims = _calibrada(random.Random(59))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    informe, _ = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [CON])]), simular=True)
    assert 'persistencia' not in informe
    informe, _ = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [CON])], evaluando=True))
    assert 'persistencia' not in informe


def test_si_releer_falla_lo_dice_y_conserva_las_obras(monkeypatch):
    """048:RF-9 — un fallo al releer no pierde lo aplicado: el informe trae las obras y el motivo."""
    app, alims = _calibrada(random.Random(61))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)

    def falla(*_a, **_k):
        raise RuntimeError('sin lectura')

    monkeypatch.setattr(guion, 'releer_obras', falla)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [CON])]))
    assert codigo == 2
    assert informe['obras'][0]['variacion'] in _variaciones(app)
    assert informe['persistencia']['ok'] is False and 'sin lectura' in informe['persistencia']['error']


# --------------------------------------------------------------------------- sin DIgSILENT
def _filas(n=3, desorden=False):
    filas = [{'nombre': f'Red\\L{i}.ElmLne', 'clase': 'ElmLne', 'datos': {'nlnum': 1, 'typ_id': 'AAAC'}}
             for i in range(n)]
    return list(reversed(filas)) if desorden else filas


def test_la_foto_es_determinista_y_ve_cada_cambio():
    """048:RF-9 — la foto no depende del orden de lectura; un valor distinto, un elemento de más o de menos sí la cambian."""
    a = foto_de_referencia(_filas())
    assert a == foto_de_referencia(_filas(desorden=True))
    cambiada = _filas()
    cambiada[1]['datos']['nlnum'] = 2
    assert foto_de_referencia(cambiada)['sha256'] != a['sha256']
    assert foto_de_referencia(_filas(4))['sha256'] != a['sha256']
    assert foto_de_referencia(_filas(2))['sha256'] != a['sha256']
    # Ruido de coma flotante por debajo de la sexta cifra decimal no es un cambio.
    ruido = [{'nombre': 'C.ElmLod', 'clase': 'ElmLod', 'datos': {'plini': 0.1 + 0.2}}]
    exacto = [{'nombre': 'C.ElmLod', 'clase': 'ElmLod', 'datos': {'plini': 0.3}}]
    assert foto_de_referencia(ruido)['sha256'] == foto_de_referencia(exacto)['sha256']


def _referencia(igual=True):
    antes = foto_de_referencia(_filas())
    despues = antes if igual else foto_de_referencia(_filas(4))
    return {BASE: {'antes': antes, 'despues': despues}}


def test_veredicto_activa_solo_donde_quedo_y_nunca_en_el_caso_base():
    """048:RF-9, 011:RF-58 — activa donde no quedó, o en el «Caso base», no es la obra elegida tal como se aplicó."""
    filas = [{'variacion': 'Obra_terna_F1', 'casos_activos': [CON], 'error': ''}]
    bien = veredicto_persistencia(filas, {'Obra_terna_F1': {'existe': True, 'objetos': 2, 'activa_en': [CON]}},
                                  _referencia())
    assert bien['ok'] and bien['obras'][0]['ok']
    for activa in ([CON, BASE], [SIN, CON], []):
        mal = veredicto_persistencia(filas, {'Obra_terna_F1': {'existe': True, 'objetos': 2, 'activa_en': activa}},
                                     _referencia())
        assert not mal['ok'] and 'activa' in mal['obras'][0]['motivo'], activa
    vacia = veredicto_persistencia(filas, {'Obra_terna_F1': {'existe': True, 'objetos': 0, 'activa_en': [CON]}},
                                   _referencia())
    assert not vacia['ok'] and 'no graba' in vacia['obras'][0]['motivo']
    tocada = veredicto_persistencia(filas, {'Obra_terna_F1': {'existe': True, 'objetos': 2, 'activa_en': [CON]}},
                                    _referencia(igual=False))
    assert not tocada['ok'] and tocada['referencias'][BASE]['igual'] is False
    assert any('L3' in c for c in tocada['referencias'][BASE]['cambios'])


def test_veredicto_sin_obras_aplicadas_no_inventa_persistencia():
    """048:RF-9 — una obra con error no tiene variación que releer; sin ninguna aplicada no hay nada que dar por persistido."""
    filas = [{'variacion': '', 'casos_activos': [], 'error': 'no se pudo crear la obra: x'}]
    v = veredicto_persistencia(filas, {}, _referencia())
    assert v['obras'] == [] and v['ok'] is False and 'ninguna obra' in v['motivo']


def test_veredicto_activa_sin_etapa_en_vigor_no_persiste():
    """048:RF-9, 081:RF-78 — activa en su caso pero con todas sus etapas después de la hora del caso: DIgSILENT no la
    aplica y no avisa. PE10 (2026-11-07): la obra salía «persistida» con el «Con proyecto» sin sus etapas aplicadas."""
    filas = [{'variacion': 'Obra_terna_F1', 'casos_activos': [CON], 'error': ''}]
    leida = {'Obra_terna_F1': {'existe': True, 'objetos': 2, 'activa_en': [CON], 'sin_vigor_en': [CON]}}
    v = veredicto_persistencia(filas, leida, _referencia())
    assert not v['ok'] and 'en vigor' in v['obras'][0]['motivo']


def test_la_relectura_ve_la_etapa_posterior_a_la_hora_del_caso(monkeypatch):
    """048:RF-9, 081:RF-78 — con el guion: una etapa fechada después de la hora de «Con proyecto» deja la obra sin
    vigor y la persistencia lo dice."""
    app, alims = _calibrada(random.Random(53))
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _terna)
    original = guion.releer_obras

    def con_etapa_tarde(a, filas, casos):
        for v in a.carpetas['scheme'].GetContents('*.IntScheme'):
            if v.loc_name.startswith('Obra_terna'):
                for s in v.GetContents('*.IntSstage'):
                    s.tAcTime = 4_000_000_000              # años después de cualquier hora de caso
        return original(a, filas, casos)

    monkeypatch.setattr(guion, 'releer_obras', con_etapa_tarde)
    informe, _codigo = guion.aplicar(app, _plan(alims, obras=[_obra_terna(alims[0], [CON])]))
    (o,) = informe['persistencia']['obras']
    assert o['ok'] is False and 'en vigor' in o['motivo'] and informe['persistencia']['ok'] is False
