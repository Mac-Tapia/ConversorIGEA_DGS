"""Spec 017: el paso «4.4 · Informes» de la página (``InformesPF.tsx``).

Comprueba en la fuente lo que el operador ve; el recorrido se prueba además en el navegador
real con la web abierta (sin-duplicar-y-front-probado-de-verdad).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFORMES = (ROOT / 'frontend' / 'src' / 'components' / 'InformesPF.tsx').read_text(encoding='utf-8')
CARGAS = (ROOT / 'frontend' / 'src' / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')


def test_informes_en_4_4_con_sus_dos_apartados():
    """017:RF-73 / 017:RF-74 — «4.4 · Informes» va en el paso 4, tras los estudios, con el
    proyecto del paso 1 y los alimentadores marcados del paso 2, sin volver a pedirlos."""
    assert CARGAS.index('<h4>4.2 · Estudios</h4>') < CARGAS.index('<h4>4.4 · Informes</h4>')
    assert '<InformesPF project={project} feeders={order} />' in CARGAS
    assert INFORMES.index('4.4.1 · Análisis eléctrico') < INFORMES.index('4.4.2 · Conexión de un cliente nuevo')


def test_la_web_no_dice_factible_a_secas_con_barras_bajas():
    """086:RF-48, 086:RF-49, 086:RF-50 — el aviso verde solo sin déficit, y cada barra baja a la vista."""
    assert "r.factible && !r.queda_deficit ? 'alert-ok' : 'alert-warn'" in INFORMES
    assert 'Factible para la carga: el alimentador sigue con barras bajo el límite.' in INFORMES
    assert 'r.textos_bajo_limite!.map' in INFORMES
    assert 'g.queda_deficit' in INFORMES
    assert "barrasAjenas(v) > 0 ? 'cumple para las cargas' : 'cumple'" in CARGAS


def test_encabezado_en_los_dos_apartados():
    """017:RF-79 — fecha, asunto, destinatario y antecedentes en los dos informes; los de la
    factibilidad salen redactados con las frases del modelo (RF-107)."""
    cabecera = INFORMES[INFORMES.index('const CABECERA'):INFORMES.index('function Campos')]
    for campo in ("'fecha'", "'asunto'", "'destinatario'"):
        assert campo in cabecera, campo
    assert INFORMES.count('<Campos campos={CABECERA}') == 2
    assert '<span>Antecedentes</span>' in INFORMES


def test_al_elegir_la_carga_y_factor_de_carga_medido():
    """017:RF-91 / 017:RF-92 — elegir la carga rellena su potencia y su punto de conexión; el
    factor de carga se propone de la medición de cabecera con su mes, o se pide."""
    elegir = INFORMES[INFORMES.index('const elegir = '):INFORMES.index('const leidoDelSolicitante')]
    assert 'potencia_kw' in elegir and 'c.barra' in elegir and 'c?.barra' in elegir, '063:RF-48: también al cambiar de carga'
    assert 'De la medición de ${fcMedido.medidor} en ${fcMedido.mes}' in INFORMES
    assert 'escríbalo, o las pérdidas quedan señaladas' in INFORMES


def test_generar_se_desactiva_con_trabajos_y_cancelar_lo_dice():
    """017:RF-98 / 017:RF-99 — «Generar» se desactiva mientras corre el motor o DIgSILENT y dice
    por qué; al cancelar, la página dice que no se escribió ningún informe."""
    assert 'const engineBusy = Boolean(active.engine || active.powerfactory);' in INFORMES
    assert INFORMES.count('disabled={busy || Boolean(motivo)}') == 2
    assert INFORMES.count('Espere a que termine el trabajo en curso.') == 2
    assert 'Cancelado: no se escribió ningún informe.' in INFORMES
