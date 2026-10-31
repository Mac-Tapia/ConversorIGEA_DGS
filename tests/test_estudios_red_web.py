"""Spec 012, T9: la API del libro de la empresa y de los estudios de confiabilidad y capacidad.

Los guiones son el falso de ``apoyo_pf_web``; los libros, sorteados con los ayudantes de
``test_datos_empresa``. Lo que se prueba es qué manda la web y qué hace con la respuesta.
"""
from __future__ import annotations

import json
import random

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from apoyo import esperar_trabajo  # noqa: E402
from apoyo_pf_web import guion_falso  # noqa: E402,F401
from test_datos_empresa import _datos, _escribir  # noqa: E402
from test_estudios_pf_web import _ajuste, _ejecutar, _espacio, _plan, client  # noqa: E402,F401

SIN, CON = 'Sin proyecto', 'Con proyecto'


def _libro(tmp_path, semilla=1, **kw):
    datos, _ = _datos(random.Random(semilla))
    return _escribir(tmp_path / f'libro_{semilla}.xlsx', datos, **kw)


def _subir(client, wid, ruta, project='P'):
    with open(ruta, 'rb') as fh:
        return client.post(f'/api/workspaces/{wid}/pf/datos-empresa', data={'project': project},
                           files={'file': (ruta.name, fh, 'application/octet-stream')})


def _catalogo(client, wid, project='P'):
    r = client.get(f'/api/workspaces/{wid}/pf/estudios', params={'project': project}).json()
    return {e['clave'] for e in r['ofrecidos']}, {o['clave']: o for o in r['no_ofrecidos']}, r


def test_sin_libro_los_tres_estudios_dicen_que_les_falta(client):
    """012:RF-19, 012:RF-1 — sin libro del proyecto, confiabilidad, reconectadores y
    condensadores se listan con el dato que les falta; los que no lo necesitan se ofrecen."""
    wid = _espacio(client)
    ofrecidos, no, r = _catalogo(client, wid)
    assert {'alojamiento', 'curvas_pv', 'flujo'} <= ofrecidos
    for clave in ('fiabilidad', 'reconectadores', 'condensadores'):
        assert 'libro de la empresa' in no[clave]['motivo']
    assert r['datos_empresa'] is None


def test_subir_el_libro_lo_valida_y_lo_guarda_con_el_proyecto(client, tmp_path):
    """012:RF-6, 012:RF-20, 012:RF-62 — el libro se valida al subirlo; queda con el proyecto,
    con su nombre y fecha, y desbloquea los estudios; sobrevive a recargar el espacio."""
    wid = _espacio(client)
    r = _subir(client, wid, _libro(tmp_path))
    assert r.status_code == 200, r.text
    libro = r.json()['libro']
    assert libro['nombre'] == 'libro_1.xlsx' and libro['cargado'] and libro['bancos']
    ofrecidos, _no, cat = _catalogo(client, wid)
    assert {'fiabilidad', 'reconectadores', 'condensadores'} <= ofrecidos
    assert cat['datos_empresa']['nombre'] == 'libro_1.xlsx'
    assert _catalogo(client, wid, 'OTRO')[2]['datos_empresa'] is None
    ws = client.app.state.store.get(wid)
    from igea_dgs.web.workspace import Workspace
    assert Workspace.load(ws.root).datos_empresa['P']['nombre'] == 'libro_1.xlsx'


def test_un_libro_con_errores_se_rechaza_y_no_reemplaza_al_anterior(client, tmp_path):
    """012:RF-16, 012:RF-63 — un libro con una unidad cambiada se rechaza nombrando hoja,
    fila y columna, y el anterior sigue; uno sin una hoja se acepta y lo dice."""
    wid = _espacio(client)
    assert _subir(client, wid, _libro(tmp_path)).status_code == 200
    malo = _libro(tmp_path, 2, unidades={'tiempos': ['-', 'h']})
    r = _subir(client, wid, malo)
    assert r.status_code == 400 and 'Hoja «Tiempos», fila 2, columna «Valor»' in r.json()['detail']
    assert client.get(f'/api/workspaces/{wid}/pf/datos-empresa', params={'project': 'P'}).json()['libro'][
        'nombre'] == 'libro_1.xlsx'
    sin_bancos = _libro(tmp_path, 3, sin=('bancos',))
    r = _subir(client, wid, sin_bancos)
    assert r.status_code == 200 and any('Bancos' in a for a in r.json()['libro']['avisos'])
    ofrecidos, no, _ = _catalogo(client, wid)
    assert 'condensadores' not in ofrecidos and 'Bancos' in no['condensadores']['motivo']
    assert 'fiabilidad' in ofrecidos


def test_plantilla_descargable(client):
    """012:RF-7 — la plantilla del libro se descarga como Excel."""
    wid = _espacio(client)
    r = client.get(f'/api/workspaces/{wid}/pf/datos-empresa/plantilla')
    assert r.status_code == 200 and r.content[:2] == b'PK'


def test_aplicar_el_libro_es_un_trabajo_de_digsilent(client, tmp_path):
    """012:RF-21, 012:RF-20 — aplicar el libro va por el carril de DIgSILENT con el libro y los
    alimentadores; queda la fecha en que se aplicó. Sin libro, no empieza."""
    wid = _espacio(client)
    r = client.post(f'/api/workspaces/{wid}/pf/datos-empresa/aplicar', json={'project': 'P', 'feeders': ['A1']})
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'failed' and 'súbalo primero' in estado['error']
    assert _subir(client, wid, _libro(tmp_path)).status_code == 200
    r = client.post(f'/api/workspaces/{wid}/pf/datos-empresa/aplicar', json={'project': 'P', 'feeders': ['A1']})
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done' and estado['lane'] == 'powerfactory', estado
    recibido = estado['result']['informe']['recibido']
    assert recibido['libro']['nombre'] == 'libro_1.xlsx' and recibido['feeders'] == ['A1']
    assert client.app.state.store.get(wid).datos_empresa['P']['aplicado']


def test_estudios_de_la_012_con_sus_ficheros_y_propuestas(client, tmp_path):
    """012:RF-2, 012:RF-5, 012:RF-20, 012:RF-31, 012:RF-37, 012:RF-49, 012:RF-59, 012:RF-67,
    012:RF-68 — el plan lleva las opciones y el libro; cada estudio en «Sin proyecto» y «Con
    proyecto»; una fila por caso, alimentador y estudio con la diferencia; la capacidad por
    nodo en su fichero; ENS total y diferencia; propuestas para aceptar como obra."""
    wid = _espacio(client)
    assert _subir(client, wid, _libro(tmp_path)).status_code == 200
    ajuste = _ajuste(client, wid)
    opciones = {'objetivo': 'saidi', 'max_total': 2, 'max_por_alimentador': 1, 'conjunto': True}
    r = _plan(client, wid, ajuste, estudios=['fiabilidad', 'reconectadores', 'alojamiento', 'condensadores'],
              opciones=opciones)
    assert r.status_code == 200, r.text
    estado = esperar_trabajo(client, _ejecutar(client, wid, r.json()['token']))
    assert estado['status'] == 'done', estado
    res = estado['result']
    assert res['libro']['nombre'] == 'libro_1.xlsx' and res['libro']['cargado']
    filas = {(f['caso'], f['alimentador'], f['estudio']) for f in res['red']}
    for caso in (SIN, CON, 'Diferencia (con − sin)'):
        assert (caso, 'A1', 'fiabilidad') in filas
    dif = next(f for f in res['red'] if f['caso'].startswith('Diferencia') and f['alimentador'] == 'A1')
    assert dif['ens_kwh'] == pytest.approx(100.0)
    assert res['comparacion_ens']['ens_total_diferencia_kwh'] == pytest.approx(100.0 * 2)
    assert any(n.startswith('estudios_red_') for n in res['ficheros'])
    assert any(n.startswith('estudios_capacidad_') for n in res['ficheros'])
    assert len(res['capacidad']) == 3 * 2 * 2              # caso × alimentador × nodo (037:RF-3)
    tipos = {p['tipo'] for p in res['propuestas']}
    assert tipos == {'reconectador', 'condensador'}
    rec = next(p for p in res['propuestas'] if p['tipo'] == 'reconectador')
    assert rec['tramo'] and rec['mejora_kwh'] == 30.0
    # 012:RF-40, 012:RF-58: cada propuesta, aceptada como lo hace el botón, es una obra válida de 4.1.
    for p in res['propuestas']:
        obra = ({'clase': 'reconectador', 'alimentador': p['alimentador'], 'casos': [CON], 'tramo': p['tramo']}
                if p['tipo'] == 'reconectador' else
                {'clase': 'condensador', 'alimentador': p['alimentador'], 'casos': [CON], 'barra': p['nodo'],
                 'q_kvar': p['kvar'], 'escalones': p['pasos']})
        r = client.post(f'/api/workspaces/{wid}/obras', json=obra)
        assert r.status_code == 201, r.text
    assert len(client.get(f'/api/workspaces/{wid}/obras').json()) == len(res['propuestas'])


def test_el_plan_manda_opciones_libro_y_clases(client, tmp_path):
    """012:RF-37, 012:RF-45, 012:RF-53, 012:RF-26 — el guion recibe las opciones del operador,
    el libro y la clase de los equipos de la entrada."""
    wid = _espacio(client)
    assert _subir(client, wid, _libro(tmp_path)).status_code == 200
    ajuste = _ajuste(client, wid)
    opciones = {'objetivo': 'ens', 'contingencias': True}
    r = _plan(client, wid, ajuste, estudios=['curvas_pv'], opciones=opciones)
    assert r.status_code == 200, r.text
    ws = client.app.state.store.get(wid)
    plan = json.loads((ws.plans_dir / f"estudios_{r.json()['token']}.json").read_text(encoding='utf-8'))
    assert plan['opciones'] == opciones and plan['libro']['nombre'] == 'libro_1.xlsx'
    assert plan['clases_equipo'] == {}


def test_un_estudio_pedido_sin_su_libro_no_se_planifica(client):
    """012:RF-19 — pedir la confiabilidad sin libro da el motivo y no se planifica."""
    wid = _espacio(client)
    ajuste = _ajuste(client, wid)
    r = _plan(client, wid, ajuste, estudios=['fiabilidad'])
    assert r.status_code == 400 and 'libro de la empresa' in r.json()['detail']


def test_modulo_sin_licencia_queda_no_disponible(client, tmp_path):
    """012:RF-4 — si DIgSILENT rechaza un módulo por licencia, el catálogo lo lista como no
    disponible con su nombre y no deja pedirlo."""
    wid = _espacio(client)
    ajuste = _ajuste(client, wid, 'LICENCIA')
    r = _plan(client, wid, ajuste, project='LICENCIA', estudios=['alojamiento'])
    assert r.status_code == 200, r.text
    estado = esperar_trabajo(client, _ejecutar(client, wid, r.json()['token']))
    assert estado['status'] == 'done', estado
    ofrecidos, no, _ = _catalogo(client, wid, 'LICENCIA')
    assert 'alojamiento' not in ofrecidos and 'ComHostcap' in no['alojamiento']['motivo']
    r = _plan(client, wid, ajuste, project='LICENCIA', estudios=['alojamiento'])
    assert r.status_code == 400 and 'ComHostcap' in r.json()['detail']
