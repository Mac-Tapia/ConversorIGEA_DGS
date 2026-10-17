"""Spec 006, RF-32 a RF-38: la curva del registro del medidor en la caja del ajuste.

El front no se ejecuta en la suite (no hay pruebas de navegador): se comprueba en la
fuente que cada pieza existe y que llama a la ruta que la API define, como en
``test_cargas_tres_pasos_front.py``. Lo demás se ve en el navegador.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP_PY = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
CURVA = (SRC / 'components' / 'CurvaCabecera.tsx').read_text(encoding='utf-8')
AJUSTE = (SRC / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
API = (SRC / 'api.ts').read_text(encoding='utf-8')
CSS = (SRC / 'styles.css').read_text(encoding='utf-8')


def test_curva_en_la_caja_del_ajuste_con_la_ruta_de_la_api():
    """006:RF-32 — la caja del ajuste muestra la curva, pedida a la ruta que define la API,
    en orden cronológico del inicio al fin del registro."""
    assert '<CurvaCabecera wsId={ws.id} jobId={maxima.id}' in AJUSTE
    assert AJUSTE.index('<CurvaCabecera') < AJUSTE.index('<span>Tolerancia (%)</span>')
    assert "@app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/curva')" in APP_PY
    assert '/demanda/cabecera/${enc(jobId)}/curva?' in API
    assert 'tramo?.desde ?? visibles.map((s) => s.curva!.inicio)' in CURVA
    assert 'tramo?.hasta ?? visibles.map((s) => s.curva!.fin)' in CURVA


def test_franja_del_mes_de_la_maxima():
    """006:RF-33 — franja del mes natural de la máxima, del día 1 al 1 del mes siguiente."""
    assert 'new Date(fm.getFullYear(), fm.getMonth(), 1)' in CURVA
    assert 'new Date(fm.getFullYear(), fm.getMonth() + 1, 1)' in CURVA
    assert 'className="curva-franja"' in CURVA and '.curva-franja { fill: var(--warn-soft); }' in CSS


def test_punto_de_la_maxima_con_fecha_y_kw():
    """006:RF-34 — el punto de la máxima, marcado con su kW, fecha y hora."""
    assert 'className="curva-pico"' in CURVA
    assert '{fmtNum(s.kwMax, 1)} kW · {diaHora(s.fm)}' in CURVA


def test_zoom_por_arrastre_y_ver_todo():
    """006:RF-35 — arrastrar pide el tramo al servidor; «Ver todo» vuelve al registro entero.
    Sin rueda: la página hace scroll con ella."""
    assert 'onPointerDown=' in CURVA and 'onPointerUp={soltar}' in CURVA
    assert 'setTramo({ desde: isoLocal(' in CURVA
    assert 'api.demandaCurva(wsId, jobId, s.medidor, tramo?.desde, tramo?.hasta)' in CURVA
    assert "onClick={() => setTramo(null)}>Ver todo</button>" in CURVA
    assert 'onWheel' not in CURVA


def test_kvar_opcional():
    """006:RF-36 — el kVAR se añade a la gráfica solo si se pide."""
    assert 'checked={kvar}' in CURVA and 'className="curva-kvar"' in CURVA
    assert 'q: kvar ?' in CURVA


def test_registros_fuera_de_la_curva_se_dicen():
    """006:RF-37 — si hay registros fuera de la curva, se dice cuántos."""
    assert 'fuera > 0' in CURVA and 'fuera de la curva' in CURVA


def test_selector_de_medidor_con_el_del_objetivo_por_defecto():
    """006:RF-38 — con varios medidores, selector; por defecto, el que da el objetivo."""
    assert 'inicial={medidores[0] || grupos[0].filas[0].medidor}' in AJUSTE
    assert '!varias && opciones.length > 1 &&' in CURVA and 'aria-label="Medidor de la curva"' in CURVA


# ---------------------------------------------------------------- spec 021: varias curvas
def test_varios_alimentadores_en_una_grafica_con_el_mismo_eje():
    """021:RF-17 — con dos o más alimentadores, todas las curvas en una gráfica, con el
    mismo eje de tiempo (del primer al último registro de ellas)."""
    assert 'const varias = series.length > 1;' in CURVA
    assert 'series={grupos.flatMap((g, i) => {' in AJUSTE
    assert '.sort()[0]' in CURVA and '.sort().at(-1)' in CURVA


def test_un_color_y_una_leyenda_por_alimentador():
    """021:RF-18 — un color por alimentador (tokens con modo oscuro) y la leyenda con su
    nombre y su medidor."""
    assert 'const color = (i: number) => `var(--serie-${i % COLORES})`;' in CURVA
    assert CSS.count('--serie-0:') == 2, 'claro y oscuro'
    assert "etiqueta: `${g.alimentador || '—'} · ${m}`" in AJUSTE
    assert 'className="curva-serie-btn"' in CURVA


def test_la_maxima_de_cada_alimentador_con_su_color():
    """021:RF-19 — la máxima de cada uno, con un punto de su color."""
    assert 'className="curva-pico-serie"' in CURVA and 'fill={s.color}' in CURVA


def test_el_arrastre_amplia_todas_las_curvas():
    """021:RF-20 — el tramo arrastrado se pide para todas: un solo ``tramo`` para todas
    las peticiones."""
    assert 'api.demandaCurva(wsId, jobId, s.medidor, tramo?.desde, tramo?.hasta)' in CURVA
    assert 'Promise.allSettled(pedidas.map((s) => (s.demanda' in CURVA


def test_la_leyenda_oculta_sin_pedir_otra_vez():
    """021:RF-21 — ocultar o mostrar es estado del navegador: no cambia lo que se pide."""
    assert 'aria-pressed={!ocultas.has(s.clave)}' in CURVA
    assert 'onClick={() => conmutar(s.clave)}' in CURVA
    peticion = CURVA[CURVA.index('Promise.allSettled'):CURVA.index('}, [wsId, jobId, firma, tramo]);')]
    assert 'ocultas' not in peticion


def test_el_medidor_elegido_o_el_primero():
    """021:RF-22 — con varios medidores, el que eligió el operador o el primero."""
    assert 'const m = medidores[i] || g.filas[0].medidor;' in AJUSTE


def test_la_curva_que_falla_no_tumba_las_demas():
    """021:RF-23 — cada curva por su lado; la que falla queda en la leyenda con su motivo."""
    assert 'Promise.allSettled(' in CURVA
    assert 'className="curva-serie-falta"' in CURVA and 'sin curva (' in CURVA


def test_un_alimentador_como_hasta_ahora():
    """021:RF-24 — con uno solo, su selector de medidor, el mes sombreado y la máxima
    rotulada, como en la 006."""
    assert '{!varias && opciones.length > 1 && (' in CURVA
    assert 'if (!varias) {' in CURVA and 'className="curva-pico"' in CURVA
