"""Spec 021, RF-25 a RF-27 y RF-34: la central térmica de un alimentador en la web.

El front no se ejecuta en la suite (no hay pruebas de navegador): se comprueba en la
fuente que cada pieza existe y que llama a la ruta que la API define, como en
``test_curva_cabecera_front.py``. Lo demás se ve en el navegador.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP_PY = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
DEMANDA = (SRC / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
AJUSTE = (SRC / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
API = (SRC / 'api.ts').read_text(encoding='utf-8')
TIPOS = (SRC / 'types.ts').read_text(encoding='utf-8')


def test_campo_central_con_tres_medidores_y_su_nodo():
    """021:RF-25 — por alimentador, «Declarar central»: generación, llegada, salida y la
    barra del troncal; sus tres medidores van en el mismo trabajo de la máxima."""
    assert 'Declarar central</button>' in DEMANDA
    for campo in ("'generacion', 'Generación'", "'llegada', 'Llegada (lado SET)'",
                  "'salida', 'Salida (lado carga)'", 'Barra de la central en DIgSILENT'):
        assert campo in DEMANDA
    assert 'api.demandaCabecera(ws.id, aBuscar, { periodo, instante, por_barra: porBarra && !instante })' in DEMANDA
    assert 'alimentador: alimentadorDeCentral(f), medidor' in DEMANDA
    assert 'nodo: string;' in TIPOS


def test_medidores_que_no_son_de_la_red_en_el_desplegable():
    """021:RF-26 — el desplegable ofrece los medidores de la ruta de la API que no son de
    un alimentador de la red."""
    assert "@app.get('/api/workspaces/{wid}/demanda/medidores-externos')" in APP_PY
    assert '/demanda/medidores-externos?${q}' in API
    assert 'api.demandaMedidoresExternos(ws.id, feeders)' in DEMANDA
    assert 'opcionesExternas.map((m) => (' in DEMANDA


def test_la_central_del_perfil_se_propone_rellena():
    """021:RF-27 — la central del perfil de cada alimentador marcado sale ya rellena, y el
    operador puede cambiarla o quitarla."""
    assert 'ext.centrales_perfil[f]' in DEMANDA
    assert 'onClick={() => quitarCentral(f)}' in DEMANDA


def test_resumen_de_la_maxima_con_central():
    """021:RF-34 — el ajuste muestra, por alimentador con central, la máxima de demanda,
    cada zona, la generación, la cabecera y la máxima de cabecera que no es la de la
    demanda, de la ruta de la API."""
    assert "@app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/central')" in APP_PY
    assert '/demanda/cabecera/${enc(jobId)}/central?' in API
    assert 'api.demandaCentral(ws.id, maxima.id, g.alimentador, medidor, centrales[g.alimentador])' in AJUSTE
    for texto in ('máxima de demanda', 'aguas arriba', 'aguas abajo', 'generaba',
                  'por la cabecera entraban', 'no es la de la demanda'):
        assert texto in AJUSTE
    assert 'centrales={Object.fromEntries(' in DEMANDA


def test_el_plan_del_ajuste_lleva_las_centrales():
    """021:RF-35 — el ajuste manda en su plan la central de cada alimentador."""
    assert 'centrales?: Record<string, CentralTermica>' in API
    plan = AJUSTE[AJUSTE.index('api.ajustePlan(ws.id, {'):]
    assert 'centrales,' in plan[:400]
    assert 'centrales: dict[str, CentralIn]' in APP_PY


CURVA = (SRC / 'components' / 'CurvaCabecera.tsx').read_text(encoding='utf-8')


def test_curvas_de_la_central_en_la_grafica():
    """021:RF-47 — con central, además de la cabecera: generación, llegada, salida y la
    demanda calculada (pedida a su ruta de la API)."""
    assert "@app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/central/curva')" in APP_PY
    assert '/central/curva?${q}' in API
    assert 'api.demandaCurvaCentral(wsId, jobId, s.demanda.alimentador, s.medidor' in CURVA
    for serie in ('·demanda', '·generacion', '·llegada', '·salida'):
        assert serie in AJUSTE


def test_las_dos_maximas_marcadas():
    """021:RF-48 — la máxima de demanda (el objetivo) y la de cabecera, cada una con su
    punto y su fecha en la leyenda."""
    assert 'demanda (objetivo)' in AJUSTE
    assert 'className="curva-pico-serie"' in CURVA
    assert '· máx. ${fmtNum(datos[s.clave].maxima.kw, 1)} kW el ${diaHora(new Date(datos[s.clave].maxima.fecha))}' in CURVA


def test_las_curvas_de_la_central_con_el_mismo_tramo_y_leyenda():
    """021:RF-49 — las curvas de la central son series más: el mismo tramo ampliado y la
    misma leyenda para ocultarlas."""
    assert 'pedidas.map((s) => (s.demanda' in CURVA and 'tramo?.desde, tramo?.hasta)' in CURVA
    assert 'aria-pressed={!ocultas.has(s.clave)}' in CURVA


def test_mes_de_analisis_antes_de_buscar_la_maxima():
    """013:RF-11 — la búsqueda de la máxima lleva el mes elegido. Usuario, 2026-10-22: el
    selector va una sola vez, en 2.3, junto al cruce de clientes; 2.2 dice qué mes usa."""
    seccion_clientes = DEMANDA.index('<h4>2.3 · Clientes importantes')
    assert DEMANDA.count('{selectorMes}') == 1
    assert seccion_clientes < DEMANDA.index('{selectorMes}') < DEMANDA.index('`Cruzar clientes de ${cuales}`')
    assert 'La máxima se busca en {nombreMes(periodo)}, el mes elegido en 2.3.' in DEMANDA
    assert 'api.demandaCabecera(ws.id, aBuscar, { periodo, instante, por_barra: porBarra && !instante })' in DEMANDA
    assert "periodo: criterio.periodo || null, instante: criterio.instante || null" in API


def test_instante_coincidente_de_la_maxima_de_un_alimentador():
    """021:RF-50, 021:RF-52 — tras la búsqueda, se puede calibrar a todos en la máxima de uno:
    se vuelve a buscar con ese instante y se avisa de que es coincidente."""
    assert 'Instante de la calibración' in DEMANDA
    assert 'Coincidente: la máxima de {x.alimentador} · {x.fecha}' in DEMANDA
    assert "onChange={(e) => maxima(e.target.value ? e.target.value.replace(' ', 'T') : '')}" in DEMANDA
    assert 'se calibra a la vez, no en la máxima de cada uno' in DEMANDA


def test_cambios_en_la_red_y_nombre_del_cliente():
    """020:RF-62, 004:RF-57 — el resultado del ajuste muestra cada cambio en la red con lo
    original existente y lo nuevo, con su SED; la tabla del cruce, el nombre del cliente."""
    ajuste = AJUSTE
    assert '<CambiosEnLaRed filas={inf.cambios_en_la_red!} />' in ajuste
    for th in ('<th>SED</th>', '<th>Original existente</th>', '<th>Potencia instalada</th>',
               '<th>Nuevo</th>', '<th>Potencia nueva</th>'):
        assert th in ajuste
    assert 'cambios_en_la_red?: CambioEnLaRed[];' in TIPOS
    assert '<th>Nis / Suministro</th><th>Cliente</th>' in DEMANDA
    assert "{c.nombre || '—'}" in DEMANDA and 'nombre: string;' in TIPOS


def test_tension_en_la_fuente_en_el_ajuste():
    """021:RF-61, 021:RF-63 — campo «Tensión en la fuente (pu)» en 2.4; vacío, la fuente
    queda como está; va en el plan."""
    assert '<span>Tensión en la fuente (pu)</span>' in AJUSTE
    assert 'centrales, tension_fuente_pu: uFuente,' in AJUSTE
    assert "'La tensión en la fuente va de 0,90 a 1,10 pu.'" in AJUSTE
    assert 'tension_fuente_pu?: number | null' in API


def test_casilla_de_los_bancos_que_falten():
    """021:RF-64 — casilla «Poner los bancos que falten» en 2.4, que va en el plan."""
    assert 'Poner los bancos que falten' in AJUSTE
    assert 'completar_bancos: completarBancos,' in AJUSTE
    assert 'completar_bancos?: boolean' in API


def test_maxima_por_barra_de_set_en_la_web():
    """022:RF-39, 022:RF-41, 022:RF-44 — casilla «Máxima por barra de SET» en 2.2, que va en
    la búsqueda; la tabla de cada barra con su máxima, su central y sus alimentadores en esa
    fecha."""
    assert 'Máxima por barra de SET' in DEMANDA and 'por_barra: porBarra && !instante' in DEMANDA
    assert '<BarrasDeSet barras={barrasSet} />' in DEMANDA
    assert '<th>Alimentadores (en esa fecha)</th>' in DEMANDA
    assert 'por_barra: Boolean(criterio.por_barra),' in API
    assert 'export interface BarraDeSet' in TIPOS


def test_conversion_por_sistema_electrico_aparte_de_unir():
    """022:RF-4, 022:RF-47, 022:RF-48, 022:RF-50, 022:RF-51 — botón propio «Convertir por
    sistema eléctrico» con el zonal (o todos), aparte de «Unir», que ya no lleva la
    estructura; la lista de DGS unidos dice el tipo; ranura para la tabla de la estructura."""
    panel = (SRC / 'components' / 'FeedersPanel.tsx').read_text(encoding='utf-8')
    assert 'Convertir por sistema eléctrico' in panel and 'api.convertSistema(ws.id, zonal ? [zonal] : [])' in panel
    assert 'Todos los sistemas (SISTEMA_ELECTRICO)' in panel
    assert 'api.convertGroup(ws.id, selected, nombre.trim() || sugerido))' in panel
    assert 'por_set' not in API and '/convert/sistema' in API
    assert "g.tipo === 'sistema'" in panel
    assert "tipo: 'estructura', titulo: 'Estructura zonal → SET (opcional)'" in DEMANDA


def test_proyecto_por_sistema_en_la_calibracion():
    """022:RF-54 — con un proyecto por sistema eléctrico, la web lee su sistema, marca la
    máxima por barra de SET y dice qué alimentadores quedan sin medidor (022:RF-53)."""
    assert 'api.demandaSistema(ws.id, project)' in DEMANDA
    assert 'if (r.sistema) setPorBarra(true);' in DEMANDA
    assert 'Sin medidor (quedan con la demanda del archivo, en los mismos flujos)' in DEMANDA
    assert '/demanda/sistema?project=' in API and 'export interface SistemaDelProyecto' in TIPOS
