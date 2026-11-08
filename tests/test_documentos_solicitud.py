"""Spec 017, RF-136 a RF-141: los datos de la solicitud desde los PDF del solicitante.

Las pruebas sintéticas usan cartas inventadas con la redacción de las reales. Las de datos
reales leen los PDF de ``referencia/`` por variables (nunca se copian al repositorio):
``CSG_SOLICITUD_PDF`` (la carta de un solicitante) e ``CSG_SOLICITUD_DIR`` (una carpeta
con los PDF de un expediente, como «ampliaciondecarga»).
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from convertersmartgrid import documentos_solicitud as ds
from convertersmartgrid.documentos_solicitud import (
    Documento, antecedentes_de, clase_de, datos_de_texto, leer_documento, propuesta_factibilidad, texto_pdf,
)

CARTA = """Información Pública
Lima, 3 de marzo de 2027

Señores:
Distribuidora Ejemplo S.A.
Av. Siempre Viva 123.

Asunto : Solicito Ampliación de Carga de 250 a 600 kW para el Sistema de Utilización
en Media Tensión 10 kV de la S.E. 12345, con NIS 999000111, propiedad de
la Agrícola Prueba S.A.C., ubicado en distrito de San Juan, Provincia de Norte y
Departamento de Sur.

Referencia : a) CARTA GT -SU-12-2027/PO (recibido el 01/02/2027)
b) EXP-2027-000042

De mi especial consideración,
Tengo el agrado de dirigirme a usted para solicitar la factibilidad.
"""

FICHA = """FICHA TÉCNICA
1 DATOS DEL PROYECTO
Codigo del Expediente : 00042-27 Codigo Tipo Proy.: AMPC
2 DATOS DEL PUNTO DE DISEÑO
Punto de Diseño : Estructura N° propiedad de Distribuidora Ejemplo S.A.
Coordenadas Pto Diseño : (E,N) UTM ( 410000.50  m E  ; 8400000.25  m S  )
Demanda Solicitada : 250 a 600
Potencia de Corto Circuito : 48
Troncal Alimentadora : AB123
Sub-estación Base : Pueblo Viejo
Nivel de Tensión Otorgada : 10
Fecha: 9/3/2027
Linea de 220 kV tercero
Ampliacion de carga de 250 kW a 600 kW, NIS 999000111, Propiedad de
la empresa Agrícola Prueba SAC ubicado en Pampa Larga
"""

RESPUESTA = """Lima, 20 de marzo de 2027
GT – SU – 77 – 2027/PO
Señor (a):
Ana Pérez Ruiz
Ingeniera Proyectista
ASUNTO : Conformidad del Proyecto Ampliación de Carga de 250 kW a 600 kW, Propiedad de la empresa AGRÍCOLA PRUEBA S.A.C., San Juan.
Ref. : Solicitud N° SOL-2027-000099, N° EXP-2027-000042
De nuestra especial consideración: se adjunta la ficha técnica de fijación del punto de diseño.
"""


def test_datos_de_la_carta_del_solicitante():
    """017:RF-138 — fecha y lugar, asunto, cliente, ubicación, tipo, potencias, tensión, NIS,
    expediente, documento citado y destinatario de una carta del interesado."""
    d = datos_de_texto(CARTA)
    assert d['fecha'] == '2027-03-03' and d['lugar'] == 'Lima'
    assert d['cliente'] == 'Agrícola Prueba S.A.C.'
    assert d['ubicacion'] == 'distrito de San Juan, provincia de Norte, departamento de Sur'
    assert d['tipo_solicitud'] == 'ampliación de carga'
    assert (d['potencia_actual_kw'], d['potencia_kw']) == (250, 600)
    assert d['tension_kv'] == 10 and d['nis'] == '999000111' and d['expediente'] == 'EXP-2027-000042'
    assert d['referencias'] == ['GT-SU-12-2027/PO']
    assert str(d['asunto']).startswith('Solicito Ampliación de Carga de 250 a 600 kW')
    assert d['destinatario'] == 'Distribuidora Ejemplo S.A.'
    assert clase_de(CARTA) == 'solicitud'


def test_ficha_desordenada_sin_confundir_la_duena_de_la_estructura():
    """017:RF-138 — la ficha trae las celdas desordenadas: el cliente no es la dueña del poste,
    la tensión es la otorgada (no la línea de 220 kV) y salen el punto de diseño, la SET, el
    alimentador y la potencia de cortocircuito."""
    d = datos_de_texto(FICHA)
    assert d['cliente'] == 'Agrícola Prueba SAC'
    assert d['tension_kv'] == 10
    assert (d['utm_x'], d['utm_y']) == (410000.50, 8400000.25)
    assert d['alimentador'] == 'AB123' and d['set_nombre'] == 'Pueblo Viejo' and d['pcc_mva'] == 48
    # 063:RF-15: el «código del expediente» de la ficha es interno: va aparte, no como expediente.
    assert d['fecha'] == '2027-03-09' and d['codigo_ficha'] == '00042-27' and 'expediente' not in d
    assert (d['potencia_actual_kw'], d['potencia_kw']) == (250, 600)
    assert clase_de(FICHA) == 'ficha'
    # Un oficio que solo cita la ficha no es una ficha.
    assert clase_de(RESPUESTA) == 'respuesta'


def _doc(nombre: str, texto: str) -> Documento:
    return Documento(fichero=nombre, paginas=1, metodo='texto', clase=clase_de(texto), datos=datos_de_texto(texto))


def test_propuesta_con_el_fichero_de_cada_dato():
    """017:RF-139 — cada dato dice de qué fichero sale; la carta del interesado manda sobre la
    ficha y la respuesta."""
    docs = [_doc('respuesta.pdf', RESPUESTA), _doc('ficha.pdf', FICHA), _doc('carta.pdf', CARTA)]
    p = propuesta_factibilidad(docs)
    assert p['cliente'] == {'valor': 'Agrícola Prueba S.A.C.', 'fichero': 'carta.pdf'}
    assert p['potencia_kw']['valor'] == 600
    assert p['set_nombre'] == {'valor': 'Pueblo Viejo', 'fichero': 'ficha.pdf'}
    assert p['solicitud'] == {'valor': 'SOL-2027-000099', 'fichero': 'respuesta.pdf'}


def test_antecedentes_uno_por_documento_en_orden_de_fecha():
    """017:RF-140 — un párrafo por documento, del más antiguo al más reciente; sin fecha, al final."""
    sin_fecha = Documento(fichero='nota.pdf', paginas=1, metodo='texto', clase='respuesta',
                          datos={'asunto': 'Nota sin fecha'})
    docs = [_doc('respuesta.pdf', RESPUESTA), sin_fecha, _doc('carta.pdf', CARTA), _doc('ficha.pdf', FICHA)]
    a = antecedentes_de(docs)
    assert len(a) == 4
    assert a[0].startswith('Con fecha 3 de marzo de 2027, el interesado (Agrícola Prueba S.A.C.) solicita')
    assert a[1].startswith('Con fecha 9 de marzo de 2027, la ficha técnica') and 'alimentador AB123' in a[1]
    assert a[2].startswith('Con fecha 20 de marzo de 2027, la distribuidora responde con documento GT-SU-77-2027/PO')
    assert 'SOL-2027-000099 y EXP-2027-000042' in a[2]
    assert a[3].startswith('Sin fecha')


def _pdf_en_blanco(ruta: Path) -> Path:
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    with ruta.open('wb') as fh:
        w.write(fh)
    return ruta


def test_pagina_escaneada_sin_tesseract_se_dice_y_no_falla(tmp_path, monkeypatch):
    """017:RF-137 — una página sin texto va al OCR; sin Tesseract se anota por página y la
    lectura termina."""
    monkeypatch.setattr(ds, 'tesseract', lambda: None)
    texto, paginas, metodo, avisos = texto_pdf(_pdf_en_blanco(tmp_path / 'escaneado.pdf'))
    assert (texto, paginas, metodo) == ('', 1, 'ninguno')
    assert len(avisos) == 1 and 'página 1' in avisos[0] and 'Tesseract' in avisos[0]
    doc = leer_documento(tmp_path / 'escaneado.pdf')
    assert doc.datos == {} and doc.avisos


def _pdf_con_texto(ruta: Path, texto: str) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(ruta), pagesize=A4)
    y = 800
    for linea in texto.splitlines():
        c.drawString(40, y, linea)
        y -= 14
    c.save()
    return ruta


def test_capa_de_texto_sin_ocr(tmp_path, monkeypatch):
    """017:RF-137 — una página con texto se lee por su capa, sin llamar al OCR."""
    pytest.importorskip('reportlab')
    monkeypatch.setattr(ds, 'ocr_pagina', lambda *a, **k: pytest.fail('no debía pasar por OCR'))
    doc = leer_documento(_pdf_con_texto(tmp_path / 'carta.pdf', CARTA))
    assert doc.metodo == 'texto' and doc.clase == 'solicitud'
    assert doc.datos['potencia_kw'] == 600 and doc.datos['nis'] == '999000111'


# ------------------------------------------------------------------ datos reales

PDF_REAL = os.environ.get('CSG_SOLICITUD_PDF', '')
DIR_REAL = os.environ.get('CSG_SOLICITUD_DIR', '')


@pytest.mark.skipif(not PDF_REAL, reason='CSG_SOLICITUD_PDF no definida')
def test_carta_real_por_texto_y_por_ocr():
    """017:RF-137 / 017:RF-138 — la carta real da cliente, potencia, fecha, NIS y expediente; leída
    a la fuerza con OCR (Tesseract y OpenCV o Pillow) da las mismas cifras."""
    pdf = Path(PDF_REAL)
    doc = leer_documento(pdf)
    assert doc.metodo == 'texto' and doc.clase == 'solicitud'
    for clave in ('cliente', 'ubicacion', 'potencia_kw', 'fecha', 'nis', 'expediente', 'tension_kv'):
        assert doc.datos.get(clave), clave
    if not ds.tesseract():
        pytest.skip('Tesseract no está instalado: la parte de OCR no se puede probar')
    ocr = leer_documento(pdf, forzar_ocr=True)
    assert ocr.metodo == 'ocr'
    for clave in ('potencia_kw', 'potencia_actual_kw', 'nis', 'expediente', 'tension_kv', 'fecha'):
        assert ocr.datos.get(clave) == doc.datos.get(clave), clave


@pytest.mark.skipif(not DIR_REAL, reason='CSG_SOLICITUD_DIR no definida')
def test_expediente_real_en_antecedentes():
    """017:RF-138 / 017:RF-140 — cada PDF del expediente real se lee y da un antecedente, en orden
    de fecha; la ficha trae el punto de diseño."""
    pdfs = sorted(Path(DIR_REAL).glob('*.pdf'))
    assert pdfs
    docs = [leer_documento(p) for p in pdfs]
    assert all(d.datos for d in docs)
    antecedentes = antecedentes_de(docs)
    assert len(antecedentes) == len(docs)
    fichas = [d for d in docs if d.clase == 'ficha']
    for f in fichas:
        assert f.datos.get('utm_x') and f.datos.get('alimentador')


# ------------------------------------------------------------------ web


@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient

    from convertersmartgrid.web.app import create_app
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def test_web_lee_los_pdf_en_un_trabajo_y_los_guarda_en_el_espacio(client, tmp_path):
    """017:RF-136 / 017:RF-137 / 017:RF-141 — la API recibe uno o varios PDF, los deja en la
    carpeta del espacio y los lee en un trabajo; lo que no es PDF se rechaza."""
    pytest.importorskip('reportlab')
    from apoyo import esperar_trabajo

    wid = client.post('/api/workspaces').json()['id']
    url = f'/api/workspaces/{wid}/informes/documentos'
    carta = _pdf_con_texto(tmp_path / 'carta.pdf', CARTA).read_bytes()
    ficha = _pdf_con_texto(tmp_path / 'ficha.pdf', FICHA).read_bytes()
    r = client.post(url, data={'tipo': 'estudio'},
                    files=[('files', ('carta.pdf', io.BytesIO(carta), 'application/pdf')),
                           ('files', ('ficha.pdf', io.BytesIO(ficha), 'application/pdf'))])
    assert r.status_code == 202, r.text
    job = esperar_trabajo(client, r.json())
    assert job['status'] == 'done', job
    res = job['result']
    assert [d['fichero'] for d in res['documentos']] == ['carta.pdf', 'ficha.pdf']
    assert res['propuesta']['cliente']['valor'] == 'Agrícola Prueba S.A.C.'
    assert len(res['antecedentes']) == 2
    carpeta = tmp_path / 'web' / wid / 'informes' / 'documentos' / 'estudio'
    assert sorted(p.name for p in carpeta.iterdir()) == ['carta.pdf', 'ficha.pdf']
    malo = client.post(url, data={'tipo': 'factibilidad'},
                       files=[('files', ('carta.docx', io.BytesIO(b'x'), 'application/octet-stream'))])
    assert malo.status_code == 400 and 'Solo se leen PDF' in malo.json()['detail']


def test_la_web_ofrece_los_pdf_en_los_dos_informes():
    """017:RF-136 / 017:RF-139 / 017:RF-140 — 4.4.2 sube un documento y rellena solo lo que está en
    blanco; 4.4.1 sube varios y añade antecedentes sin repetirlos."""
    fuente = (Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'features' / 'powerfactory' / 'InformesPF.tsx').read_text(
        encoding='utf-8')
    assert '<DocumentosSolicitante tipo="factibilidad" varios={false}' in fuente
    # También sin carga aplicada todavía: la carta llega antes que la carga.
    vacio = fuente[fuente.index('if (!ctx.cargas.length || !solas.length)'):]
    assert '{documento}' in vacio[:900]
    assert '<DocumentosSolicitante tipo="estudio" varios' in fuente
    assert "if (v && libre) nueva[k] = v;" in fuente
    assert '!hay.includes(p)' in fuente


def test_documentos_exp_codigo_de_ficha_fechas_y_alimentadores():
    """063:RF-15, 063:RF-19, 063:RF-20 — de la carta, la ficha y la respuesta (sintéticas): el
    EXP es el expediente propuesto y el código de la ficha va aparte; cada fecha y cada
    alimentador dicen de qué documento salen, y la fecha propuesta es la de la solicitud."""
    docs = [_doc('respuesta.pdf', RESPUESTA), _doc('ficha.pdf', FICHA), _doc('carta.pdf', CARTA)]
    propuesta = propuesta_factibilidad(docs)
    assert propuesta['expediente'] == {'valor': 'EXP-2027-000042', 'fichero': 'carta.pdf'}
    assert propuesta['codigo_ficha'] == {'valor': '00042-27', 'fichero': 'ficha.pdf'}
    assert propuesta['fecha']['fichero'] == 'carta.pdf'
    fechas = ds.de_cada_documento(docs, 'fecha')
    assert {f['fichero'] for f in fechas} == {'carta.pdf', 'ficha.pdf', 'respuesta.pdf'}
    assert all(f['clase'] in ('solicitud', 'ficha', 'respuesta') for f in fechas)
    alims = ds.de_cada_documento(docs, 'alimentador')
    assert alims and all(a['fichero'] and a['valor'] for a in alims)
