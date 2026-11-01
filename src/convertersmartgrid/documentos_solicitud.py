"""Datos de la solicitud desde los PDF del solicitante (spec 017, RF-136 a RF-141).

El operador recibe la carta del proyectista, el oficio de la distribuidora o la ficha del
punto de diseño, y copiaba a mano en 4.4 el cliente, la potencia, el expediente… (usuario,
2026-10-31, con «Carta_Sol_Fact_AMPC_480A1000.pdf» y la carpeta «ampliaciondecarga»).

Cada página se lee primero por su capa de texto: los cuatro PDF de prueba la traen, y es
exacta. Solo una página sin texto (escaneada) va por OCR con Tesseract, con la imagen
binarizada con OpenCV si está instalado (si no, con Pillow). Sin Tesseract la página se
anota y el resto sigue (RF-137). Nada sale del equipo (RF-141).

Los datos se buscan por las frases de estas cartas, no por posiciones: la ficha técnica
sale del PDF con las celdas desordenadas («Demanda Solicitada : 900 a 2000» y el «kW»
varias líneas después), y el OCR en inglés pierde las tildes («Ampliacion»).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

#: Página con menos caracteres útiles que esto: se tiene por escaneada y va por OCR.
MIN_CARACTERES = 40

MESES = {m: i for i, m in enumerate(
    ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
     'septiembre', 'octubre', 'noviembre', 'diciembre'), start=1)}
MESES['setiembre'] = 9

#: Rutas habituales de Tesseract en Windows; ``CSG_TESSERACT`` manda sobre todas.
_TESSERACT_WINDOWS = (Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'),
                      Path(r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'))


@dataclass
class Documento:
    """Un PDF leído: cómo se leyó y lo que se encontró (RF-137, RF-138)."""

    fichero: str
    paginas: int
    #: «texto» (capa del PDF), «ocr» o «texto+ocr» si se mezclan por página.
    metodo: str
    clase: str
    datos: dict[str, object] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    #: Las primeras líneas, para que el operador vea qué se leyó.
    extracto: str = ''

    def a_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------------------ texto


def tesseract() -> str | None:
    """El ejecutable de Tesseract, o ``None``: variable, PATH o la carpeta de Windows."""
    propio = os.environ.get('CSG_TESSERACT', '').strip()
    if propio and Path(propio).is_file():
        return propio
    en_path = shutil.which('tesseract')
    if en_path:
        return en_path
    return next((str(p) for p in _TESSERACT_WINDOWS if p.is_file()), None)


def tessdata() -> list[str]:
    """``--tessdata-dir`` con los idiomas propios, o nada (la carpeta de Tesseract).

    En este equipo la carpeta de Tesseract solo trae «eng» y no se puede escribir sin
    administrador (2026-10-31): el «spa» va en ``CSG_TESSDATA`` o en ``~/.convertersmartgrid/tessdata``,
    con «eng» copiado al lado, porque ``--tessdata-dir`` sustituye a la carpeta, no la suma.
    """
    propia = os.environ.get('CSG_TESSDATA', '').strip()
    carpeta = Path(propia) if propia else Path.home() / '.convertersmartgrid' / 'tessdata'
    return ['--tessdata-dir', str(carpeta)] if any(carpeta.glob('*.traineddata')) else []


def idioma_ocr(exe: str) -> str:
    """«spa» si Tesseract lo tiene; si no, «eng» (lee las cifras igual; pierde tildes)."""
    try:
        salida = subprocess.run([exe, *tessdata(), '--list-langs'], capture_output=True, text=True,
                                timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return 'eng'
    idiomas = {x.strip() for x in salida.splitlines()[1:]}
    return 'spa' if 'spa' in idiomas else 'eng'


def _limpiar_imagen(imagen):
    """Gris y umbral de Otsu con OpenCV; sin OpenCV, el equivalente con Pillow."""
    try:
        import cv2  # type: ignore[import-not-found]  # opcional: requirements-drivers.txt
        import numpy as np
    except ImportError:
        from PIL import ImageOps
        gris = ImageOps.autocontrast(ImageOps.grayscale(imagen))
        return gris.point(lambda v: 255 if v > 160 else 0)
    from PIL import Image
    gris = cv2.cvtColor(np.array(imagen.convert('RGB')), cv2.COLOR_RGB2GRAY)
    gris = cv2.medianBlur(gris, 3)
    _umbral, binaria = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(binaria)


def ocr_pagina(pdf: Path, pagina: int, exe: str, idioma: str) -> str:
    """Texto de una página (1-based) por OCR, a 300 ppp."""
    from pdf2image import convert_from_path
    imagen = convert_from_path(str(pdf), dpi=300, first_page=pagina, last_page=pagina)[0]
    with tempfile.TemporaryDirectory() as carpeta:
        png = Path(carpeta) / 'pagina.png'
        _limpiar_imagen(imagen).save(png)
        r = subprocess.run([exe, *tessdata(), str(png), 'stdout', '-l', idioma, '--psm', '6'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=300)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or '').strip() or f'Tesseract terminó con {r.returncode}')
    return r.stdout


def texto_pdf(pdf: Path, *, forzar_ocr: bool = False,
              cancelado: Callable[[], None] | None = None) -> tuple[str, int, str, list[str]]:
    """(texto, páginas, método, avisos). OCR solo en las páginas sin capa de texto."""
    from pypdf import PdfReader
    lector = PdfReader(str(pdf))
    partes, metodos, avisos = [], set(), []
    exe: str | None = None
    idioma = ''
    for n, pagina in enumerate(lector.pages, start=1):
        if cancelado:
            cancelado()
        texto = '' if forzar_ocr else (pagina.extract_text() or '')
        if len(re.sub(r'\s', '', texto)) >= MIN_CARACTERES:
            partes.append(texto)
            metodos.add('texto')
            continue
        if exe is None:
            exe = tesseract() or ''
            idioma = idioma_ocr(exe) if exe else ''
        if not exe:
            avisos.append(f'página {n} sin texto y sin Tesseract instalado: no se pudo leer '
                          '(instálelo o indique su ruta en CSG_TESSERACT).')
            continue
        try:
            partes.append(ocr_pagina(pdf, n, exe, idioma))
            metodos.add('ocr')
            if idioma != 'spa':
                avisos.append(f'página {n} leída con OCR en «{idioma}»: sin el idioma «spa» de '
                              'Tesseract se pierden las tildes; revise los datos.')
        except Exception as exc:  # noqa: BLE001 — una página mala no tumba las demás
            avisos.append(f'página {n}: el OCR falló ({exc}).')
    metodo = '+'.join(sorted(metodos)) or 'ninguno'
    return '\n'.join(partes), len(lector.pages), metodo, avisos


# ------------------------------------------------------------------------------ datos


def _numero(s: str) -> float | None:
    s = s.strip().rstrip('.')
    if re.fullmatch(r'\d{1,3}(,\d{3})+', s):          # 1,000 → mil
        s = s.replace(',', '')
    try:
        return float(s.replace(',', '.'))
    except ValueError:
        return None


def _limpio(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip(' ,;:-')
    # «Minera Santa María S.A.C.» conserva el punto de su sigla; «Ica.» lo pierde.
    if s.endswith('.') and not re.search(r'(?:\b[A-Z]\.){2,}$', s):
        s = s[:-1]
    return s


def _cliente(plano: str) -> str | None:
    """El propietario del suministro. En la ficha, «Estructura N° propiedad de Electro Dunas»
    es la dueña del poste del punto de diseño, no el cliente: se salta lo que sigue a
    «estructura», y lo que no termina en una frase corta."""
    for m in re.finditer(r'propiedad de\s+(?:la empresa\s+|la\s+|el\s+)?(.+?)'
                         r'(?=,\s|\s+ubicad|\.\s+[A-ZÁÉÍÓÚ]|\s*$)', plano, re.IGNORECASE):
        antes = plano[max(0, m.start() - 25):m.start()]
        nombre = _limpio(m.group(1))
        if re.search(r'estructura', antes, re.IGNORECASE) or not 2 < len(nombre) <= 80:
            continue
        return nombre
    return None


def _buscar(patron: str, texto: str, grupo: int = 1) -> str | None:
    m = re.search(patron, texto, re.IGNORECASE)
    return _limpio(m.group(grupo)) if m and m.group(grupo) else None


def datos_de_texto(texto: str) -> dict[str, object]:
    """Los datos de la solicitud que trae el texto (RF-138); falta lo que no aparece."""
    texto = unicodedata.normalize('NFC', texto).replace('\u2013', '-').replace('\u2014', '-')
    lineas = [x.strip() for x in texto.splitlines() if x.strip()]
    plano = re.sub(r'\s+', ' ', texto)
    d: dict[str, object] = {}

    for linea in lineas:     # «Ica, 22 de octubre de 2026»
        m = re.match(r'^([A-Za-zÁÉÍÓÚÑáéíóúñ .]{2,40}),\s*(\d{1,2})\s+de\s+([A-Za-záéíóú]+)\s+'
                     r'(?:de|del)\s+(\d{4})', linea)
        if m and m.group(3).lower() in MESES:
            d['lugar'] = _limpio(m.group(1))
            d['fecha'] = date(int(m.group(4)), MESES[m.group(3).lower()], int(m.group(2))).isoformat()
            break
    if 'fecha' not in d:     # la ficha: «Fecha: 4/11/2025»
        m = re.search(r'fecha\s*:\s*(\d{1,2})/(\d{1,2})/(\d{4})', plano, re.IGNORECASE)
        if m:
            d['fecha'] = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()

    asunto = _buscar(r'asunto\s*:\s*(.+?)\s+(?:ref(?:erencia)?\s*\.?\s*:|de (?:nuestra|mi) especial)',
                     plano)
    if asunto:
        d['asunto'] = asunto
    cliente = _cliente(plano)
    if cliente:
        d['cliente'] = cliente
    m = re.search(r'distrito de\s+([^,]+?),\s*provincia de\s+(.+?)\s+y\s+departamento de\s+'
                  r'([A-Za-zÁÉÍÓÚÑáéíóúñ ]+?)(?=[.,]|\s+(?:en|para|con)\s|$)', plano, re.IGNORECASE)
    if m:
        d['ubicacion'] = (f'distrito de {_limpio(m.group(1))}, provincia de {_limpio(m.group(2))}, '
                          f'departamento de {_limpio(m.group(3))}')

    if re.search(r'ampliaci[oó]n de carga', plano, re.IGNORECASE):
        d['tipo_solicitud'] = 'ampliación de carga'
    elif re.search(r'nuevo suministro|suministro nuevo', plano, re.IGNORECASE):
        d['tipo_solicitud'] = 'nuevo suministro'
    elif re.search(r'factibilidad', plano, re.IGNORECASE):
        d['tipo_solicitud'] = 'factibilidad de suministro'

    m = (re.search(r'\bde\s+([\d.,]+)\s*(?:kw\s*)?a\s+([\d.,]+)\s*kw', plano, re.IGNORECASE)
         or re.search(r'demanda solicitada\s*:\s*([\d.,]+)\s*a\s*([\d.,]+)', plano, re.IGNORECASE))
    if m:
        d['potencia_actual_kw'], d['potencia_kw'] = _numero(m.group(1)), _numero(m.group(2))
    else:
        kw = _buscar(r'(?:demanda solicitada\s*:\s*|\b)([\d.,]+)\s*kw\b', plano)
        if kw:
            d['potencia_kw'] = _numero(kw)
    # La tensión otorgada manda: la ficha cita también «Línea de 220 kV tercero».
    kv = (_buscar(r'tensi[oó]n otorgada\s*:\s*(\d{1,3}(?:[.,]\d{1,2})?)', plano)
          or _buscar(r'\b(\d{1,3}(?:[.,]\d{1,2})?)\s*kv\b', plano))
    if kv:
        d['tension_kv'] = _numero(kv)

    for clave, patron in (
            ('nis', r'\bNIS\s*(?:N[°º]\s*)?(\d{6,})'),
            ('solicitud', r'\b(SOL-\s*\d{4}-\d+)'),
            ('estructura', r'estructura\s*N\s*[°º]?\s*(\d{3,})'),
            ('alimentador', r'troncal alimentadora\s*:\s*([A-Z]{1,3}\d{2,4})\b'),
            ('set_nombre', r'sub-?\s*estaci[oó]n base\s*:\s*(.+?)(?:\s+nivel de tensi|\s*$)'),
            ('pcc_mva', r'(?:potencia de corto\s*circuito\s*:\s*|cortocircuito[^.]{0,60}?es de\s*)([\d.,]+)')):
        valor = _buscar(patron, plano)
        if valor:
            d[clave] = _numero(valor) if clave == 'pcc_mva' else valor.replace(' ', '')
            if clave == 'set_nombre':
                d[clave] = valor
    if 'alimentador' not in d:
        alim = _buscar(r'alimentador\s+([A-Z]{1,3}\d{2,4})\b', plano)
        if alim:
            d['alimentador'] = alim
    exp = _buscar(r'\b(EXP-\s*\d{4}-\d+)', plano) or _buscar(r'c[oó]digo del expediente\s*:\s*([\w-]+)', plano)
    if exp:
        d['expediente'] = exp.replace(' ', '')
    refs = [re.sub(r'\s+', '', m.group(1)) for m in re.finditer(
        r'\b(G[TC]\s*-\s*SU\s*-\s*\d+\s*-\s*\d{4}\s*/\s*PO)', plano, re.IGNORECASE)]
    if refs:
        d['referencias'] = list(dict.fromkeys(refs))
    m = re.search(r'\(\s*([\d.]+)\s*m\s*E\s*;\s*([\d.]+)\s*m\s*[NS]', plano)
    if m:
        d['utm_x'], d['utm_y'] = _numero(m.group(1)), _numero(m.group(2))
    for i, linea in enumerate(lineas[:-1]):
        if re.match(r'^se[ñn]or(?:es|\s*\(a\)|a)?\s*:?\s*$', linea, re.IGNORECASE):
            d['destinatario'] = _limpio(lineas[i + 1])
            break
    return d


def clase_de(texto: str) -> str:
    """«ficha», «solicitud» (la escribe el interesado) o «respuesta» (la distribuidora)."""
    # Por su apartado de datos: el oficio de respuesta también cita la «ficha técnica» y la
    # «fijación del punto de diseño» (2101_1. Rpta. AMPC SU Incas Berries).
    if re.search(r'datos del punto de dise[ñn]o', texto, re.IGNORECASE):
        return 'ficha'
    if re.search(r'\bsolicit(?:o|ar)\b|tengo el agrado', texto, re.IGNORECASE):
        return 'solicitud'
    return 'respuesta'


def leer_documento(pdf: Path, *, forzar_ocr: bool = False,
                   cancelado: Callable[[], None] | None = None) -> Documento:
    """Un PDF leído y sus datos (RF-137, RF-138)."""
    texto, paginas, metodo, avisos = texto_pdf(pdf, forzar_ocr=forzar_ocr, cancelado=cancelado)
    extracto = '\n'.join(x.strip() for x in texto.splitlines() if x.strip())[:1500]
    datos = datos_de_texto(texto) if texto.strip() else {}
    if texto.strip() and not datos:
        avisos.append('no se reconoció ningún dato: revise el extracto.')
    return Documento(fichero=pdf.name, paginas=paginas, metodo=metodo, clase=clase_de(texto),
                     datos=datos, avisos=avisos, extracto=extracto)


# ------------------------------------------------------------------ uso en los informes

#: Datos de la solicitud de 4.4.2, en el orden en que se buscan en los documentos.
CAMPOS_SOLICITUD = ('cliente', 'ubicacion', 'tipo_solicitud', 'potencia_kw', 'fecha',
                    'expediente', 'set_nombre', 'tension_kv', 'lugar', 'asunto', 'alimentador',
                    'nis', 'solicitud', 'estructura', 'utm_x', 'utm_y', 'pcc_mva')


def propuesta_factibilidad(documentos: list[Documento]) -> dict[str, dict[str, object]]:
    """Cada dato con el fichero del que sale (RF-139): primero la solicitud del interesado,
    luego la ficha y por último las respuestas."""
    orden = {'solicitud': 0, 'ficha': 1, 'respuesta': 2}
    propuesta: dict[str, dict[str, object]] = {}
    for doc in sorted(documentos, key=lambda x: orden.get(x.clase, 3)):
        for clave in CAMPOS_SOLICITUD:
            valor = doc.datos.get(clave)
            if valor not in (None, '') and clave not in propuesta:
                propuesta[clave] = {'valor': valor, 'fichero': doc.fichero}
    return propuesta


def _fecha_larga(iso: str) -> str:
    f = date.fromisoformat(iso)
    nombre = next(m for m, i in MESES.items() if i == f.month and m != 'setiembre')
    return f'{f.day} de {nombre} de {f.year}'


def antecedente(doc: Documento) -> str:
    """Un párrafo de antecedentes por documento (RF-140)."""
    d = doc.datos
    cuando = f'Con fecha {_fecha_larga(str(d["fecha"]))}' if d.get('fecha') else 'Sin fecha'
    if doc.clase == 'ficha':
        partes = [f'punto de diseño en la estructura N.° {d["estructura"]}' if d.get('estructura') else 'punto de diseño',
                  f'alimentador {d["alimentador"]}' if d.get('alimentador') else '',
                  f'SET {d["set_nombre"]}' if d.get('set_nombre') else '',
                  f'{d["tension_kv"]:g} kV' if d.get('tension_kv') else '',
                  f'potencia de cortocircuito {d["pcc_mva"]:g} MVA' if d.get('pcc_mva') else '',
                  f'coordenadas UTM {d["utm_x"]:.2f} E, {d["utm_y"]:.2f} N' if d.get('utm_x') else '']
        exp = f' (expediente {d["expediente"]})' if d.get('expediente') else ''
        return f'{cuando}, la ficha técnica de fijación del punto de diseño{exp} indica: ' \
               f'{", ".join(p for p in partes if p)}.'
    asunto = str(d.get('asunto') or 'sin asunto legible')
    asunto = asunto[0].lower() + asunto[1:] if asunto[:2] != asunto[:2].upper() else asunto
    refs = [str(x) for x in (d.get('solicitud'), d.get('expediente')) if x]
    con = f', registrada con {" y ".join(refs)}' if refs else ''
    if doc.clase == 'solicitud':
        quien = f'el interesado ({d["cliente"]})' if d.get('cliente') else 'el interesado'
        return f'{cuando}, {quien} solicita: {asunto}{con}.'
    referencias = d.get('referencias')
    numero = referencias[0] if isinstance(referencias, list) and referencias else None
    por = f' con documento {numero}' if numero else ''
    return f'{cuando}, la distribuidora responde{por}: {asunto}{con}.'


def antecedentes_de(documentos: list[Documento]) -> list[str]:
    """Los antecedentes en orden de fecha; los documentos sin fecha, al final (RF-140)."""
    con_fecha = sorted((d for d in documentos if d.datos.get('fecha')), key=lambda d: str(d.datos['fecha']))
    return [antecedente(d) for d in con_fecha + [d for d in documentos if not d.datos.get('fecha')]]
