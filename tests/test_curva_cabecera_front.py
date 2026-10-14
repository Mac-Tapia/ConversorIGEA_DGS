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
    assert 'tramo?.desde ?? datos.inicio' in CURVA and 'tramo?.hasta ?? datos.fin' in CURVA


def test_franja_del_mes_de_la_maxima():
    """006:RF-33 — franja del mes natural de la máxima, del día 1 al 1 del mes siguiente."""
    assert 'new Date(fm.getFullYear(), fm.getMonth(), 1)' in CURVA
    assert 'new Date(fm.getFullYear(), fm.getMonth() + 1, 1)' in CURVA
    assert 'className="curva-franja"' in CURVA and '.curva-franja { fill: var(--warn-soft); }' in CSS


def test_punto_de_la_maxima_con_fecha_y_kw():
    """006:RF-34 — el punto de la máxima, marcado con su kW, fecha y hora."""
    assert 'className="curva-pico"' in CURVA
    assert '{fmtNum(datos.maxima.kw, 1)} kW · {diaHora(g.fm)}' in CURVA


def test_zoom_por_arrastre_y_ver_todo():
    """006:RF-35 — arrastrar pide el tramo al servidor; «Ver todo» vuelve al registro entero.
    Sin rueda: la página hace scroll con ella."""
    assert 'onPointerDown=' in CURVA and 'onPointerUp={soltar}' in CURVA
    assert 'setTramo({ desde: isoLocal(' in CURVA
    assert 'api.demandaCurva(wsId, jobId, medidor, tramo?.desde, tramo?.hasta)' in CURVA
    assert "onClick={() => setTramo(null)}>Ver todo</button>" in CURVA
    assert 'onWheel' not in CURVA


def test_kvar_opcional():
    """006:RF-36 — el kVAR se añade a la gráfica solo si se pide."""
    assert 'checked={kvar}' in CURVA and 'className="curva-kvar"' in CURVA
    assert 'const q = kvar ?' in CURVA


def test_registros_fuera_de_la_curva_se_dicen():
    """006:RF-37 — si hay registros fuera de la curva, se dice cuántos."""
    assert 'datos.fuera_de_curva > 0' in CURVA and 'fuera de la curva' in CURVA


def test_selector_de_medidor_con_el_del_objetivo_por_defecto():
    """006:RF-38 — con varios medidores, selector; por defecto, el que da el objetivo."""
    assert 'inicial={medidores[0] || grupos[0].filas[0].medidor}' in AJUSTE
    assert 'opciones.length > 1 &&' in CURVA and 'aria-label="Medidor de la curva"' in CURVA
