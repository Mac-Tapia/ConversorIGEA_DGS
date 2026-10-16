"""Spec 004, T6: contrato entre el front y la API del módulo de cargas en DIgSILENT.

El front no se ejecuta en las pruebas; se comprueba su fuente: que no queden llamadas a
las rutas retiradas (que hoy darían 404 sin que nada lo delate hasta pulsar el botón) y
que cada ruta que llama exista en la API.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')


def _fuente() -> str:
    return '\n'.join(p.read_text(encoding='utf-8') for p in sorted(SRC.rglob('*.ts*')))


def _rutas_api() -> set[str]:
    """Rutas de la API con los parámetros como ``{}``: ``/api/workspaces/{}/lote/{}/apply``."""
    return {re.sub(r'\{[^}]+\}', '{}', r)
            for r in re.findall(r"@app\.(?:get|post|put|delete)\('([^']+)'", APP)}


def test_no_quedan_rutas_retiradas():
    """004:RF-1 — el front ya no llama a las rutas por alimentador que exigían entradas cargadas."""
    fuente = _fuente()
    for retirada in ('load-template', 'load-plan', 'create-template', 'create-plan', '/plans/'):
        assert retirada not in fuente, retirada
    for retirado in ('LoadsTab', 'NewSedTab', 'LoteTab'):
        assert retirado not in fuente, retirado


def test_una_sola_pestana_de_cargas():
    """004:RF-2 — una pestaña «Cargas en DIgSILENT» que lee los proyectos y sus alimentadores."""
    app_tsx = (SRC / 'App.tsx').read_text(encoding='utf-8')
    assert app_tsx.count("label: 'Cargas en DIgSILENT'") == 1
    assert '<CargasTab />' in app_tsx
    tab = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
    assert 'api.pfProjects' in tab and 'p.feeders' in tab


def test_simular_y_aplicar_son_trabajos():
    """004:RF-17 — simular y aplicar se lanzan como trabajos, nunca esperando dentro del clic."""
    tab = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
    assert 'startJob(() => (simular ? api.cargasSimular : api.cargasAplicar)' in tab


def test_el_informe_se_muestra_por_alimentador():
    """004:RF-20 — el informe del guion se muestra por alimentador, con omitidas y ambiguas."""
    tab = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
    for clave in ('inf.feeders', 'inf.sin_alimentador', 'inf.ambiguas', 'inf.no_creadas',
                  'actualizadas', 'creadas', 'fallos'):
        assert clave in tab, clave


def test_cada_ruta_del_cliente_existe_en_la_api():
    """004:RF-5, 018:RF-13 — el cliente del módulo llama a rutas que la API define, las mismas
    para uno o varios; la lista de proyectos se lee (POST) y se recupera guardada (GET)."""
    api_ts = (SRC / 'api.ts').read_text(encoding='utf-8')
    rutas = _rutas_api()
    llamadas = [ll for ll in re.findall(r'`\$\{ws\(id\)\}(/[^`?]*)', api_ts)
                if ll.startswith(('/lote', '/cargas', '/powerfactory/projects'))]
    assert len(llamadas) == 6, llamadas
    for llamada in llamadas:
        ruta = '/api/workspaces/{}' + re.sub(r'\$\{[^}]+\}', '{}', llamada)
        assert ruta in rutas, f'{ruta} no existe en la API'


# ----------------------------------------------------------------- spec 007
def _tab():
    return (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')


def test_base_propuesta_desde_el_ultimo_ajuste():
    """007:RF-1 / 007:RF-2 — la base es el último ajuste aplicado del proyecto, se manda al
    plan y se muestra con su variación, su máxima y si cuadró."""
    tab = _tab()
    # 020:RF-28: el ajuste que recalibró tras los transformadores nuevos también vale.
    assert ("(j.kind === 'ajuste_aplicar' || j.kind === 'ajuste_transformadores')\n"
            "    && j.result?.project === project") in tab
    assert 'conBase ? baseJob!.id : null' in tab
    assert "fd.append('ajuste_job_id', ajusteJobId)" in (SRC / 'api.ts').read_text(encoding='utf-8')
    for pieza in ('function Base(', 'i.variacion', 'i.objetivo', 'i.cuadrado'):
        assert pieza in tab, pieza


def test_orden_de_los_pasos_del_trabajo():
    """007:RF-3 — proyecto, alimentador, máxima y clientes, ajuste, y por último las cargas."""
    tab = _tab()
    demanda = (SRC / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    assert tab.index('1 · Proyecto') < tab.index('<DemandaMedida') < tab.index('3 · Integración de nuevas')
    assert demanda.index('2.2 · Máxima') < demanda.index('2.3 · Clientes') < demanda.index('<AjusteCabecera')


def test_quitar_la_base():
    """007:RF-4 / 007:RF-5 — se puede quitar la base; sin ella se dice que se aplica sobre lo activo."""
    tab = _tab()
    assert 'Quitar base' in tab and 'setSinBase(true)' in tab
    assert 'se aplica sobre las variaciones que' in tab and 'plan.avisos.map' in tab


def test_base_que_no_cuadro_y_calibradas_cambiadas_a_la_vista():
    """007:RF-34 / 007:RF-21 — el plan muestra si la base no cuadró y qué SED calibradas cambia el libro."""
    tab = _tab()
    assert 'se usa igual' in tab
    assert '<Calibradas xs={plan.calibradas_cambiadas} />' in tab
    assert 'inf.calibradas_cambiadas' in tab


def test_informe_por_carga():
    """007:RF-18 / 007:RF-23 / 007:RF-30 / 007:RF-33 — por carga su variación, barra y distancia,
    las diferencias con y sin proyecto y su evaluación técnico-económica."""
    tab = _tab()
    for pieza in ('function PorCarga(', 'c.variacion', 'c.distancia_m', 'c.delta?.kw', 'c.delta?.perdidas_kw',
                  'c.delta?.vm_min', 'c.tecnico_economico', 'variación ${c.variacion}'):
        assert pieza in tab, pieza
