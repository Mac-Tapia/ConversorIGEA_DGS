"""Spec 008: la pestaña «Cargas en DIgSILENT» en tres pasos (contrato de la fuente del front).

El front no se ejecuta en la suite (no hay pruebas de navegador): se comprueba en la
fuente que cada pieza existe, está en su paso y llama a una ruta que la API define.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP_PY = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
APP = (SRC / 'App.tsx').read_text(encoding='utf-8')
CARGAS = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
DEMANDA = (SRC / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
AJUSTE = (SRC / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
API = (SRC / 'api.ts').read_text(encoding='utf-8')


def _pos(texto: str, *piezas: str) -> list[int]:
    pos = [texto.find(p) for p in piezas]
    assert all(p >= 0 for p in pos), [p for p, i in zip(piezas, pos) if i < 0]
    return pos


def test_la_pestana_se_ve_sin_entradas():
    """008:RF-1 / 008:RF-2 — las pestañas se muestran sin entradas cargadas; sin ellas, solo
    las que no las necesitan, y «Cargas en DIgSILENT» no las necesita."""
    assert "{ id: 'cargas', label: 'Cargas en DIgSILENT', el: <CargasTab />, entradas: false }" in APP
    for tab in ('results', 'catalog', 'system'):
        assert re.search(rf"id: '{tab}'.*entradas: true", APP), tab
    assert 'TABS.filter((t) => w.state!.loaded || !t.entradas)' in APP
    assert '{w.state.loaded && (\n                <section className="card">' not in APP


def test_tres_pasos_en_orden():
    """008:RF-3 — proyecto, alimentadores y calibración, integración de nuevas; ya no hay «Qué aplicar»."""
    uno, dos, tres = _pos(CARGAS, '<h3>1 · Proyecto de DIgSILENT</h3>',
                          '<h3>2 · Alimentadores y calibración', '<h3>3 · Integración de nuevas</h3>')
    assert uno < dos < tres
    assert 'Qué aplicar' not in CARGAS
    # La calibración va en el paso 2, antes de la integración.
    assert dos < CARGAS.index('<DemandaMedida project={project} feeders={order} />') < tres


def test_filtrar_proyectos():
    """008:RF-4 / 008:RF-5 — se filtra por parte de la ruta y se elige de la lista filtrada;
    sin coincidencias se dice."""
    assert 'ruta(p).toLowerCase().includes(q)' in CARGAS
    assert '{filtrados.map((p) => (' in CARGAS
    assert 'Ningún proyecto coincide con' in CARGAS


def test_alimentadores_marcados_al_elegir_y_compartidos():
    """008:RF-6 / 008:RF-7 — elegir un proyecto marca todos sus alimentadores, y los marcados
    sirven a la calibración y a la integración."""
    assert 'setOrder(projects.find((p) => ruta(p) === name)?.feeders ?? [])' in CARGAS
    assert 'api.cargasPlan(ws.id, project, order,' in CARGAS
    assert 'feeders={order}' in CARGAS


def test_medidores_por_alimentador_y_maxima_en_un_trabajo():
    """008:RF-8 / 008:RF-9 / 008:RF-10 — medidores del libro por cada marcado, aviso y medidor
    a mano si no está, y la máxima de todos en un trabajo."""
    assert 'feeders.map((f) => api.demandaMedidores(ws.id, f))' in DEMANDA
    assert 'no está en el libro de medidores' in DEMANDA and 'anadir(f)' in DEMANDA
    assert 'startJob(() => api.demandaCabecera(ws.id, elegidos))' in DEMANDA


def test_clientes_de_los_marcados():
    """008:RF-11 / 013:RF-8 — el cruce de clientes es el de los alimentadores marcados, con
    el mes elegido en «2.3» si lo hay."""
    assert 'api.demandaClientes(ws.id, feeders, periodo || undefined)' in DEMANDA


def test_ajuste_de_varios_y_su_informe():
    """008:RF-12 / 008:RF-13 / 008:RF-16 — un medidor por alimentador, elección si hay varios,
    un solo plan con todos e informe por alimentador."""
    assert 'medidores, tolerancia: tol' in AJUSTE
    assert 'Medidor de la cabecera de' in AJUSTE
    assert 'resultado.informes ?? [resultado.informe]' in AJUSTE
    assert 'inf.no_empezado' in AJUSTE and 'inf.error' in AJUSTE
    assert 'medidores?: string[]' in API


def test_el_informe_muestra_el_kvar_nativo_no_bloqueante():
    """006:RF-14 — el operador ve objetivo, resultado nativo y diferencia de kVAR aunque
    el criterio de aceptación sea solo el cuadre de kW."""
    for pieza in ('kvar_no_bloqueante', 'red_nativa_kvar', 'diferencia_kvar',
                  'Diferencia de kVAR (no bloqueante)'):
        assert pieza in AJUSTE or pieza in (SRC / 'types.ts').read_text(encoding='utf-8'), pieza


def test_verificar_y_aplicar_solo_con_convergencia():
    """008:RF-18 / 008:RF-20 / 008:RF-21 — verificar es un trabajo; aplicar se desactiva sin un
    flujo convergido, simular no."""
    assert 'startJob(() => api.pfVerificar(ws.id, project, order))' in CARGAS
    assert "`${ws(id)}/powerfactory/verificar`" in API
    assert "@app.post('/api/workspaces/{wid}/powerfactory/verificar'" in APP_PY
    aplicar = CARGAS[CARGAS.index('<button className="btn btn-pf"'):]
    assert 'Boolean(porQueNoAplicar)' in aplicar[:200]
    simular = CARGAS[CARGAS.rindex('<button className="btn"', 0, CARGAS.index('Simular en DIgSILENT')):]
    assert 'porQueNoAplicar' not in simular[:200]
    assert "j.kind === 'pf_verificar'" in CARGAS and "j.kind === 'ajuste_aplicar'" in CARGAS


def test_verificacion_muestra_cabecera_por_alimentador():
    """008:RF-19 — el resultado de la verificación: converge, tensiones y cabecera por alimentador."""
    assert 'function Verificacion(' in CARGAS
    for pieza in ('f?.converged', 'vm_min_bus', 'x.cabecera.kw', 'inf.variaciones_activas'):
        assert pieza in CARGAS, pieza


def test_tres_partes_optativas_en_orden():
    """008:RF-22 / 008:RF-23 — 3.1 demandas, 3.2 una carga, 3.3 cargas en bloque; basta una."""
    a, b, c = _pos(CARGAS, '3.1 · Demandas en bloque', '3.2 · Una carga nueva', '3.3 · Cargas nuevas en bloque')
    assert a < b < c
    assert 'disabled={!order.length || (!demandas && !hayNuevas)}' in CARGAS


def _campos_nueva() -> str:
    return CARGAS[CARGAS.index('const NUEVA_CAMPOS'):CARGAS.index('const TEXTO')]


def test_carga_nueva_con_kw_y_fp():
    """004:RF-46 — el formulario pide kW y FP; kVAR y kVA solo están en el libro."""
    campos = _campos_nueva()
    for clave in ('Kw', 'FP'):
        assert re.search(rf"key: '{clave}'[^}}]*required: true", campos), clave
    assert "key: 'Kvar'" not in campos and "key: '(kVA)'" not in campos


def test_carga_nueva_ubicada_por_coordenadas():
    """004:RF-47 — Lat/Lon a la vista; CoordX/CoordY, barra, alimentador, línea y BT plegados."""
    campos = _campos_nueva()
    for clave in ('Lat', 'Lon'):
        assert re.search(rf"key: '{clave}'(?![^}}]*mas: true)[^}}]*}}", campos), clave
    for clave in ('CoordX', 'CoordY', 'barra', 'alimentador', 'tipo_linea', 'tension_bt_kv'):
        assert re.search(rf"key: '{clave}'[^}}]*mas: true", campos), clave
    assert 'NUEVA_CAMPOS.filter((c) => !c.mas).map(campoNueva)' in CARGAS
    assert '<summary>Más opciones' in CARGAS
