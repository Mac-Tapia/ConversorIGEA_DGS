"""049:RF-2: los ajustes de un relé o un reconectador se leen de su fichero y se dice lo que falta."""

from __future__ import annotations

from convertersmartgrid.protecciones import leer_ajustes

SEL = """Relay ID: CA101-R1
Manufacturer: SEL
Model = SEL-751A
CT 600/5 A
51P1P := 2.50 A sec
51P1C := U3
51P1TD := 3.00
Interrupting rating: 25 kA
"""

RECONECTADOR = """Reconectador del alimentador CA101
Equipo: RC-CA101-04
Fabricante: NOJA Power
Modelo: OSM15
Curva: IEC muy inversa
Arranque: 280 A
Dial: 0,15
Poder de corte: 12,5 kA
Celda: SEC_1091_315216
"""


def test_un_rele_estilo_sel_queda_completo_con_su_tc():
    """049:RF-2 — SEL-751A: arranque en amperios secundarios con su TC, curva, dial y poder de corte."""
    r = leer_ajustes(SEL, 'CA101_R1.txt', cubiculo='CA101')
    d = r['dispositivo']
    assert (d['id'], d['fabricante'], d['modelo'], d['clase']) == ('CA101-R1', 'SEL', 'SEL-751A', 'rele')
    assert (d['arranque'], d['unidad_arranque'], d['curva'], d['dial'], d['unidad_dial']) == (2.5, 'A sec', 'U3', 3.0, 'dial')
    assert (d['ct_primario_a'], d['ct_secundario_a'], d['poder_corte_ka']) == (600.0, 5.0, 25.0)
    assert r['faltan'] == [] and r['errores'] == []


def test_un_reconectador_en_espanol_con_coma_decimal():
    """049:RF-2 — un reconectador NOJA con las etiquetas en español y la coma decimal."""
    r = leer_ajustes(RECONECTADOR, 'reconectador.pdf')
    d = r['dispositivo']
    assert d['clase'] == 'reconectador' and d['id'] == 'RC-CA101-04' and d['cubiculo'] == 'SEC_1091_315216'
    assert (d['arranque'], d['unidad_arranque'], d['dial'], d['poder_corte_ka']) == (280.0, 'A', 0.15, 12.5)
    assert d['curva'] == 'IEC muy inversa' and d['fuente'] == 'reconectador.pdf'
    assert r['faltan'] == []


def test_lo_que_no_trae_se_dice_y_no_se_adivina():
    """049:RF-2 — sin poder de corte ni curva, el dispositivo no entra al estudio y se dice qué falta."""
    r = leer_ajustes('Fabricante: ABB\nArranque: 300 A\n', 'parcial.txt')
    assert 'poder_corte_ka' not in r['dispositivo'] and 'curva' not in r['dispositivo']
    assert any('poder de corte' in f for f in r['faltan']) and any('curva' in f for f in r['faltan'])


def test_una_foto_de_los_ajustes_se_lee_por_ocr(tmp_path):
    """049:RF-2 — los datos que faltan se cargan también en imagen (JPG, PNG…): la foto de la pantalla de ajustes de un
    reconectador se lee por OCR con el mismo lector que el TXT (usuario, 2026-11-13)."""
    import pytest
    from PIL import Image, ImageDraw, ImageFont

    from convertersmartgrid.documentos_solicitud import tesseract, texto_de_fichero
    if not tesseract():
        pytest.skip('sin Tesseract')
    try:
        fuente = ImageFont.truetype('arial.ttf', 42)
    except OSError:
        pytest.skip('sin la fuente Arial para dibujar la imagen de prueba')
    imagen = Image.new('RGB', (1500, 700), 'white')
    dibujo = ImageDraw.Draw(imagen)
    for n, linea in enumerate(RECONECTADOR.strip().splitlines()):
        dibujo.text((40, 30 + 70 * n), linea, fill='black', font=fuente)
    ruta = tmp_path / 'ajustes.jpg'
    imagen.save(ruta, quality=92)
    texto, metodo, avisos = texto_de_fichero(ruta)
    assert metodo == 'ocr' and avisos == []
    d = leer_ajustes(texto, ruta.name)['dispositivo']
    assert (d['clase'], d['arranque'], d['dial'], d['poder_corte_ka']) == ('reconectador', 280.0, 0.15, 12.5)
