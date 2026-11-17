"""108 T23 (RF-20): la «Guía de Elaboración del Valor Nuevo de Reemplazo de las Instalaciones de Distribución Eléctrica»
(RCD 232-2017-OS/CD), del PDF oficial al registro normativo, sin transcribir nada a mano.

- Comprueba el PDF contra el SHA256SUMS.txt de su carpeta (``fuentes.comprobar_carpeta``) antes de leerlo.
- Extrae el texto con pypdf (versión anotada en la salida), página a página separadas por «\\f», y lo guarda junto al PDF
  como ``rcd_232-2017.txt``: es el ``fichero_local`` del registro y cada regla cita sus líneas y su página.
- Cada regla lleva su cita literal: el tramo del texto oficial entre dos marcas, con los espacios normalizados.
- Las tablas de equivalencia del Anexo 6 (MT, BT y AP) salen a ``config/vnr/anexo6_equivalencias.json``. Una fila que no
  trae tantos valores como columnas declara su cabecera detiene el generador: nada se rellena.

Uso: python -I -X utf8 tools/normativa/generar_guia_vnr_232.py --fuentes <carpeta de fuentes> --destino <repo>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fuentes import comprobar_carpeta, sin_rutas

SUBCARPETA = 'VNR_GUIA_232_2017'
PDF = 'OSINERGMIN No.232-2017-OS-CD.pdf'
TXT = 'rcd_232-2017.txt'
ACTO = 'RCD 232-2017-OS/CD'
URL = 'https://www.osinergmin.gob.pe/Resoluciones/pdf/2017/OSINERGMIN%20No.232-2017-OS-CD.pdf'


class GuiaError(SystemExit):
    """El texto oficial no trae lo que el generador espera: se para sin escribir."""


def extraer_texto(pdf: Path) -> tuple[str, str]:
    import pypdf
    lector = pypdf.PdfReader(str(pdf))
    paginas = [(p.extract_text() or '') for p in lector.pages]
    return '\n\f'.join(paginas), pypdf.__version__


class Texto:
    """El texto oficial con sus líneas y sus páginas, para citar."""

    def __init__(self, texto: str):
        self.texto = texto
        self.lineas = texto.split('\n')
        self.pagina_de = []
        pagina = 1
        for linea in self.lineas:
            if linea.startswith('\f'):
                pagina += 1
            self.pagina_de.append(pagina)

    def _linea(self, desde: int) -> int:
        return self.texto.count('\n', 0, desde)

    def cita(self, inicio: str, fin: str, *, despues: str = '') -> dict:
        """El tramo literal desde ``inicio`` hasta antes de ``fin`` (la primera aparición tras ``despues``)."""
        base = self.texto.find(despues) if despues else 0
        if base < 0:
            raise GuiaError(f'{ACTO}: no está la marca «{despues}» en el texto oficial')
        i = self.texto.find(inicio, base)
        if i < 0:
            raise GuiaError(f'{ACTO}: no está «{inicio}» en el texto oficial')
        j = self.texto.find(fin, i + len(inicio))
        if j < 0:
            raise GuiaError(f'{ACTO}: no está el final «{fin}» tras «{inicio}»')
        a, b = self._linea(i), self._linea(j)
        literal = re.sub(r'\s+', ' ', self.texto[i:j].replace('\f', ' ')).strip()
        paginas = sorted({self.pagina_de[k] for k in range(a, b + 1)})
        return {'cita_literal': literal, 'lineas': f'{a + 1}-{b + 1}',
                'pagina': str(paginas[0]) if len(paginas) == 1 else f'{paginas[0]}-{paginas[-1]}'}


# ---------------------------------------------------------------- reglas

ZONAS = [  # Tabla N° 1 del art. 22.1; se comprueba que cada fila esté literal en la cita.
    {'zona': 'Muy Alta', 'desde_mw_km2': 4.0, 'hasta_mw_km2': None,
     'literal': 'Muy Alta Densidad Mayor o igual a 4 MW/km2 Rojo'},
    {'zona': 'Alta 1', 'desde_mw_km2': 2.5, 'hasta_mw_km2': 4.0,
     'literal': 'Alta Densidad 1 Mayor o igual a 2,5 MW/km2 y menor a 4 MW/km2 Anaranjado'},
    {'zona': 'Alta 2', 'desde_mw_km2': 1.5, 'hasta_mw_km2': 2.5,
     'literal': 'Alta Densidad 2 Mayor o igual a 1,50 MW/km2 y menor a 2,5 MW/km2 Azul'},
    {'zona': 'Media', 'desde_mw_km2': 0.25, 'hasta_mw_km2': 1.5,
     'literal': 'Media Densidad Mayor o igual a 0,25 MW/km2 y menor a 1,5 MW/km2 Verde'},
    {'zona': 'Baja', 'desde_mw_km2': None, 'hasta_mw_km2': 0.25,
     'literal': 'Baja Densidad Menor a 0,25 MW/km2 Amarillo'},
]

INSTALACIONES_16_4 = {
    'Media Tensión': ['Red Aérea Media Tensión', 'Red Subterránea Media Tensión',
                      'Equipos de Protección y Seccionamiento'],
    'Subestaciones': ['Subestación Aérea Monoposte', 'Subestación Aérea Biposte', 'Subestación Convencional',
                      'Subestación Compacta Pedestal', 'Subestación Compacta Bóveda'],
}


def _exigir(cita: dict, *literales: str) -> dict:
    for lit in literales:
        if lit not in cita['cita_literal']:
            raise GuiaError(f'{ACTO}: la cita {cita["lineas"]} no contiene «{lit}»')
    return cita


def reglas(t: Texto) -> list[dict]:
    g = 'Artículo 1.- Objetivo'  # el cuerpo de la Guía empieza tras su índice; las citas se buscan desde su texto.
    cuerpo = t.texto.find(g, t.texto.find(g) + 1)
    if cuerpo < 0:
        raise GuiaError(f'{ACTO}: no está el cuerpo de la Guía tras su índice')
    marca = t.texto[cuerpo:cuerpo + 80]
    r = []

    def regla(clave, valor, art, inicio, fin, *literales, unidad='', caracter='obligatoria', despues=marca):
        c = _exigir(t.cita(inicio, fin, despues=despues), *literales)
        d = {'clave': clave, 'valor': valor, 'articulo_o_anexo': art, **c, 'caracter': caracter}
        if unidad:
            d['unidad'] = unidad
        r.append(d)

    regla('vnr.guia.vigencia', 'dia_siguiente_publicacion', 'art. 2 de la resolución',
          'Artículo 2.- La presente resolución', 'Daniel', 'día siguiente de su publicación', despues='')
    regla('vnr.valorizacion.costos_ie', 'costos_estandar_ultima_fijacion', 'art. 12.1',
          '12.1 Para efectos de la entrega', '12.2', 'última fijación del VNR')
    regla('vnr.valorizacion.metrado_adaptado', 'capitulos_sexto_a_decimo_primero', 'art. 12.3',
          '12.3 La valorización de las instalaciones adaptadas', 'Artículo 13', 'Sexto al Décimo Primero')
    regla('vnr.costos_estandar.componentes', ['materiales', 'recursos', 'ingenieria', 'gastos_generales',
                                              'interes_intercalario'], 'art. 16.2',
          '16.2 Dichos costos', '16.3', 'ingeniería, gastos generales e interés')
    regla('vnr.costos_estandar.instalaciones', INSTALACIONES_16_4, 'art. 16.4',
          '16.4 Los costos estándar de inversión por sector típico', '16.5',
          *[i for v in INSTALACIONES_16_4.values() for i in v])
    regla('vnr.formula', 'VNR = MIE * CEIE + MINE * CINE', 'art. 17.2',
          '17.2 El VNR de las instalaciones', '17.3', 'VNR = MIE * CEIE + MINE * CINE')
    regla('vnr.zonas.densidad', [{k: v for k, v in z.items() if k != 'literal'} for z in ZONAS], 'art. 22.1',
          '22.1 El proceso de adaptación', '22.2', *[z['literal'] for z in ZONAS], unidad='MW/km2')
    regla('vnr.corrosivo.ancho_km', 7, 'art. 22.1', '22.1 El proceso de adaptación', '22.2',
          'costa de 7 km de ancho', unidad='km')
    regla('vnr.cuadricula.lados_m', [1000, 500, 250], 'art. 22.2', '22.2 Para determinar', '22.3',
          '1000, 500 y 250 m', 'múltiplos de mil', unidad='m')
    regla('vnr.ap.factor_carga', 0.5, 'art. 22.3', '22.3 Para elaborar', '22.4', 'factor de carga igual a 0,5')
    regla('vnr.ap.factor_coincidencia', 1.0, 'art. 22.3', '22.3 Para elaborar', '22.4',
          'factor de coincidencia igual a 1,0')
    regla('vnr.md.anio', 'previo_a_la_fijacion', 'art. 22.4', '22.4 Para calcular', '22.5',
          'año previo al proceso de fijación')
    regla('vnr.zonificacion.proceso', ['1000_muy_alta', '500_muy_alta', '250_todas', 'aislada_predominante',
                                       'cero_eliminada'], 'art. 22.6', '22.6 El proceso de zonificación', '22.7',
          'adoptan la densidad de carga predominante', 'densidad de carga igual a cero debe ser eliminada')
    regla('vnr.zonificacion.mapas', {'MT': 'todas_las_sed', 'BT': 'sed_uso_no_industrial'}, 'art. 22.8',
          '22.8 Se deben construir', 'Artículo 23', 'totalidad de las subestaciones',
          'cuyo uso no sea industrial')
    r.extend(reglas_adaptacion(t, marca))
    return r


# ---------------------------------------------------------------- criterios de adaptación (capítulos 6 a 10)
# Cada criterio es el artículo entero como cita literal y su valor estructurado. El generador para si la cita no trae las
# frases que justifican cada valor (``exige``): así un cambio del texto oficial no pasa desapercibido.

SECTORES = {
    'urbano_alta': ('CAPÍTULO SEXTO', 23),
    'urbano_media_baja': ('CAPÍTULO SÉPTIMO', 28),
    'urbano_rural': ('CAPÍTULO OCTAVO', 33),
    'rural_ser': ('CAPÍTULO NOVENO', 38),
}
_DESNUDO = {'corrosivo': 'CU Desnudo', 'no_corrosivo': 'AA Desnudo'}
_PROT_AEREA = {'Reconectador': 'Reconectador SF6', 'Seccionador bajo carga': 'Seccionador bajo carga SF6',
               'Seccionador fusible (cut-out)': None, 'Seccionador Unipolar (x1, x2, x3)': None,
               'Seccionalizador': 'Seccionalizador electrónico'}
_PROT_SUBT = {'Interruptor': 'Interruptor SF6', 'Seccionador bajo carga': 'Seccionador bajo carga SF6',
              'Seccionador Unipolar (x1, x2, x3)': None}
_SED_ALTA_OTRAS = [  # Tabla N° 5 (art. 25.5) = Tabla N° 9 (art. 30.4)
    {'fases': 3, 'mayor_que': 640, 'existentes': ['Compacta', 'Convencional'], 'adaptada': 'Convencional 3ø'},
    {'fases': 3, 'mayor_que': 250, 'hasta': 640, 'adaptada': 'Compacta Pedestal 3ø'},
    {'fases': 3, 'mayor_que': 75, 'hasta': 250, 'adaptada': 'Biposte 3ø'},
    {'fases': 3, 'hasta': 75, 'adaptada': 'Monoposte 3ø'},
    {'fases': 1, 'hasta': 37.5, 'adaptada': 'Monoposte 1ø'},
    {'fases': 1, 'mayor_que': 37.5, 'adaptada': 'Monoposte 3ø'}]
_SED_RURAL = [  # Tabla N° 13 (art. 35.4) y la del art. 40.4
    {'fases': 3, 'mayor_que': 75, 'adaptada': 'Biposte 3ø'},
    {'fases': 3, 'hasta': 75, 'adaptada': 'Monoposte 3ø'},
    {'fases': 1, 'hasta': 37.5, 'adaptada': 'Monoposte 1ø'},
    {'fases': 1, 'mayor_que': 37.5, 'adaptada': 'Monoposte 3ø'}]

CRITERIOS = {
    ('urbano_alta', 'mt'): ({
        'tensiones_kv': [10.0, 22.9], 'postes': 'concreto',
        'aerea': {'Muy Alta': {'todos': 'NA2XSY'},
                  'otras': {'desnudo_por_ambiente': _DESNUDO,
                            'cambian': ['AA Protegido', 'AA Desnudo', 'CU Protegido'],
                            'autoportante': {'zonas': ['Alta 1', 'Alta 2'], 'se_mantiene': True,
                                             'CU Autoportante': 'AL Autoportante'}}},
        'subterranea': {'NA2XSY_en': ['Muy Alta', 'Alta 1', 'Alta 2'],
                        'media_baja': {'NA2XSY_desde_mm2': 95, 'menor': 'aerea_desnudo_por_ambiente'}}},
        ['10 kV y 22,9 kV', 'por cables NA2XSY', 'equivalente en cobre desnudo', 'equivalente en aluminio desnudo',
         'autoportantes de aluminio', 'iguales o mayores a 95 mm2']),
    ('urbano_media_baja', 'mt'): ({
        'tensiones_kv': [10.0, 13.2, 22.9], 'postes': 'concreto',
        'aerea': {'todas': {'desnudo_por_ambiente': _DESNUDO,
                            'autoportante': {'se_mantiene': True, 'CU Autoportante': 'AL Autoportante'}}},
        'subterranea': {'tipo': 'NA2XSY', 'tope_porcentaje_sistema': 14, 'exceso': 'aerea_desnudo_por_ambiente',
                        'orden_exceso': 'seccion_ascendente'}},
        ['equivalente en cobre desnudo', 'equivalente en aluminio desnudo', 'autoportantes de aluminio',
         'no supere el 14%', 'secciones más delgadas', 'del tipo NA2XSY', 'postes de concreto']),
    ('urbano_rural', 'mt'): ({
        'tensiones_kv': [10.0, 13.2, 22.9], 'postes': 'concreto',
        'aerea_y_subterranea': {'desnudo_por_ambiente': _DESNUDO}},
        ['aéreas o subterráneas ubicadas en Zonas de Ambiente Corrosivo', 'equivalente en aluminio desnudo',
         'postes de concreto']),
    ('rural_ser', 'mt'): ({
        'tensiones_kv': [10.0, 13.2, 22.9], 'postes': 'madera',
        'aerea_y_subterranea': {'desnudo_por_ambiente': _DESNUDO}},
        ['aéreas o subterráneas ubicadas en Zonas de Ambiente Corrosivo', 'equivalente en aluminio desnudo',
         'postes de madera']),
    ('urbano_alta', 'proteccion'): ({'aerea': _PROT_AEREA, 'subterranea': _PROT_SUBT, 'se_mantienen': [
        'Pararrayos', 'Fusible Limitador', 'Fusible expulsión', 'Conectores aislados separables',
        'Banco de Condensadores', 'Banco de Regulación de Tensión']},
        ['Reconectador SF6', 'Seccionalizador electrónico', 'Interruptor SF6', 'se mantiene el equipo reportado']),
    ('urbano_media_baja', 'proteccion'): ({'aerea': _PROT_AEREA, 'subterranea': _PROT_SUBT, 'se_mantienen': [
        'Banco de Condensadores', 'Banco de Regulación de Tensión'], 'pararrayos': 'sierra_selva_isoceraunico'},
        ['Reconectador SF6', 'Interruptor SF6', 'altos niveles isoceraúnicos']),
    ('urbano_rural', 'proteccion'): ({'aerea': {k: v for k, v in _PROT_AEREA.items() if k != 'Seccionador bajo carga'},
                                      'se_mantienen': ['Banco de Condensadores', 'Banco de Regulación de Tensión'],
                                      'pararrayos': 'sierra_selva_isoceraunico'},
                                     ['Reconectador SF6', 'Seccionalizador electrónico', 'altos niveles isoceraúnicos']),
    ('rural_ser', 'proteccion'): ({'aerea': {k: v for k, v in _PROT_AEREA.items() if k != 'Seccionador bajo carga'},
                                   'se_mantienen': ['Banco de Condensadores', 'Banco de Regulación de Tensión'],
                                   'pararrayos': 'sierra_selva_isoceraunico'},
                                  ['Reconectador SF6', 'Seccionalizador electrónico', 'altos niveles isoceraúnicos']),
    ('urbano_alta', 'sed'): ({'fp': 0.9, 'fu': 0.75, 'sin_bancos_monofasicos': True, 'tabla': {
        'Muy Alta': [
            {'fases': 3, 'mayor_que': 640, 'existentes': ['Compacta', 'Convencional'], 'adaptada': 'Convencional 3ø'},
            {'fases': 3, 'hasta': 640, 'existentes': ['Compacta Pedestal'], 'adaptada': 'Compacta Pedestal 3ø'},
            {'fases': 3, 'hasta': 640, 'existentes': ['Compacta Bóveda'], 'adaptada': 'Compacta Bóveda 3ø'},
            {'fases': 3, 'hasta': 640, 'existentes': ['Convencional'], 'adaptada': 'Compacta Pedestal 3ø'},
            {'fases': 3, 'hasta': 640, 'existentes': ['SAM', 'SAB'], 'adaptada': 'Compacta Pedestal 3ø'}],
        'otras': _SED_ALTA_OTRAS}},
        ['factor de utilización (f.u.) es igual a 0,75', 'Compacta Pedestal 3ø', 'Monoposte 1ø']),
    ('urbano_media_baja', 'sed'): ({'fp': 0.9, 'fu': 0.85, 'sin_bancos_monofasicos': True,
                                    'tabla': {'todas': _SED_ALTA_OTRAS}},
                                   ['factor de utilización (f.u.) es igual a 0,85', 'Biposte 3ø']),
    ('urbano_rural', 'sed'): ({'fp': 0.9, 'fu': 0.9, 'sin_bancos_monofasicos': True, 'tabla': {'todas': _SED_RURAL}},
                              ['factor de utilización (f.u.) es igual a 0,9', 'Biposte 3ø']),
    ('rural_ser', 'sed'): ({'fp': 0.9, 'fu': 0.9, 'sin_bancos_monofasicos': True, 'tabla': {'todas': _SED_RURAL}},
                           ['factor de utilización (f.u.) es igual a 0,9', 'Biposte 3ø']),
    ('urbano_alta', 'bt'): ({
        'tension_v': 220, 'postes': 'concreto',
        'Muy Alta': 'NA2XY', 'aerea_otras': 'AL Autoportante',
        'subterranea_otras': {'sed_aerea': 'AL Autoportante', 'sed_no_aerea': 'NA2XY',
                              'reparto_aereo': {'A.1.1': 71, 'A.1.3': 29}, 'orden_29': 'bifasicas_luego_trifasicas'}},
        ['equivalente en cables NA2XY unipolar', 'autoportante de aluminio', 'Monoposte o Biposte', '71%', '29%',
         '220 V']),
    ('urbano_media_baja', 'bt'): ({'tensiones_v': [220, 380], 'postes': 'concreto', 'aerea': 'AL Autoportante',
                                   'subterranea': {'tipo': 'NA2XY', 'tope_porcentaje_sistema': 2,
                                                   'exceso': 'AL Autoportante',
                                                   'orden_exceso': 'bifasicas_luego_trifasicas'}},
                                  ['autoportante de aluminio', 'no supere el 2%', 'NA2XY unipolar']),
    ('urbano_rural', 'bt'): ({'tensiones_v': [220, 380], 'postes': 'concreto', 'aerea_y_subterranea': 'AL Autoportante'},
                             ['aéreas y subterráneas', 'autoportante de aluminio', 'postes de concreto']),
    ('rural_ser', 'bt'): ({'tensiones_v': [220, 380], 'postes': 'madera', 'aerea_y_subterranea': 'AL Autoportante'},
                          ['aéreas y subterráneas', 'autoportante de aluminio', 'postes de madera']),
    ('urbano_alta', 'ap'): ({'tecnologias': ['Sodio', 'LED'], 'tabla_anexo6': 10, 'pastorales': 'metalicos',
                             'vano_postes_ap_m': 33.33, 'poste_ap_m': 9},
                            ['vapor de sodio y LEDs', 'pastorales metálicos', '33,33 m']),
    ('urbano_media_baja', 'ap'): ({'tecnologias': ['Sodio', 'LED'], 'tabla_anexo6': 11, 'pastorales': 'metalicos',
                                   'vano_postes_ap_m': 33.33, 'poste_ap_m': 9},
                                  ['vapor de sodio y LEDs', 'pastorales metálicos', '33,33 m']),
    ('urbano_rural', 'ap'): ({'tecnologias': ['Sodio', 'LED'], 'tabla_anexo6': 12, 'sodio_max_w': 70,
                              'led_max_w': 40, 'pastorales': 'reportados'},
                             ['sodio de hasta 70 W', 'potencia máxima 40 W', 'pastorales reportados']),
    ('rural_ser', 'ap'): ({'tecnologias': ['Sodio', 'LED'], 'tabla_anexo6': 13, 'sodio_max_w': 50, 'led_max_w': 40,
                           'pastorales': 'reportados'},
                          ['sodio de hasta 50 W', 'potencia máxima 40 W', 'pastorales reportados']),
}
_RUBRO_ARTICULO = {'mt': 0, 'proteccion': 1, 'sed': 2, 'bt': 3, 'ap': 4}


def reglas_adaptacion(t: Texto, marca: str) -> list[dict]:
    r = []
    for (sector, rubro), (valor, exige) in CRITERIOS.items():
        n = SECTORES[sector][1] + _RUBRO_ARTICULO[rubro]
        fin = f'Artículo {n + 1}.-' if not (sector == 'rural_ser' and rubro == 'ap') else 'CAPÍTULO DÉCIMO'
        c = _exigir(t.cita(f'Artículo {n}.-', fin, despues=marca), *exige)
        r.append({'clave': f'vnr.adaptacion.{sector}.{rubro}', 'valor': valor, 'articulo_o_anexo': f'art. {n}', **c,
                  'caracter': 'obligatoria'})
    especiales = {
        'vnr.adaptacion.zonas_historicas': ('Artículo 43.-', 'Artículo 44.-', 'art. 43',
                                            {'subterranea_solo_si_instalada': True, 'mt': 'NA2XSY', 'bt': 'NA2XY',
                                             'sed_subterraneas': ['Compacta Pedestal', 'Compacta Bóveda']},
                                            ['sólo es efectivo', 'NA2XSY', 'NA2XY']),
        'vnr.adaptacion.calles_angostas': ('Artículo 44.-', 'CAPÍTULO DECIMO PRIMERO', 'art. 44',
                                           {'ancho_calle_max_m': 12, 'subterranea_o_autoportante_solo_si_instalada': True,
                                            'sed_subterraneas': ['Compacta Pedestal', 'Compacta Bóveda']},
                                           ['menores o iguales a 12 metros', 'sólo es efectivo']),
        'vnr.adaptacion.ine': ('Artículo 45.-', 'Artículo 46.-', 'art. 45',
                               {'nivel': 'unidad_de_gestion', 'tope': 'metrado_reportado'},
                               ['Unidades de Gestión', 'En ningún caso, este dimensionamiento debe exceder los metrados de las INE reportadas']),
    }
    for clave, (ini, fin, art, valor, exige) in especiales.items():
        c = _exigir(t.cita(ini, fin, despues=marca), *exige)
        r.append({'clave': clave, 'valor': valor, 'articulo_o_anexo': art, **c, 'caracter': 'obligatoria'})
    return r


# ---------------------------------------------------------------- Anexo 6

_FILA = re.compile(r'^(\d+(?:,\d+)?) ?mm2 ((?:\S+ ?)+?)\s*$')


def _num(v: str):
    if v in ('-', '—'):
        return None
    try:
        return int(v)
    except ValueError:
        return float(v.replace(',', '.'))


def anexo6(t: Texto) -> dict:
    inicio = t.texto.rfind('TABLAS DE EQUIVALENCIA')
    if inicio < 0:
        raise GuiaError(f'{ACTO}: no está el Anexo 6 (TABLAS DE EQUIVALENCIA)')
    linea0 = t._linea(inicio)
    tablas, actual, grupo, nivel = {}, None, None, None
    niveles = {'1. Tablas de Equivalencia de Media Tensión': 'MT', '2. Tablas de Equivalencia de Baja Tensión': 'BT',
               '3. Tablas de Equivalencia de Alumbrado Público': 'AP',
               '4. Zonas Geográficas de Tipo de Ambiente Corrosivo': 'corrosivo'}
    for k in range(linea0, len(t.lineas)):
        s = t.lineas[k].replace('\f', '').strip()
        nivel = niveles.get(s, nivel)  # el numeral del Anexo 6 donde está cada tabla
        m = re.match(r'^Tabla N° (\d+)$', s)
        if m:
            actual = {'tabla': int(m.group(1)), 'nivel': nivel, 'pagina': t.pagina_de[k], 'linea': k + 1,
                      'columnas': None, 'filas': []}
            tablas[actual['tabla']] = actual
            grupo = None
            continue
        if actual is None or not s or s.startswith(('Anexo 6', 'División de Distribución')):
            continue
        if s.startswith('Origen ') and actual['columnas'] is None:
            if 'Equivalencia en' in s:
                actual['columnas'] = [c.strip() for c in s.split('Equivalencia en')[1:]]
                actual['tipo'] = 'tecnologia'
            elif s.startswith('Origen Origen 2,3 kV'):
                actual['columnas'] = ['2,3 kV a 10 kV', '5,8 kV a 10 kV']
                actual['tipo'] = 'tension'
            else:
                raise GuiaError(f'{ACTO}: cabecera desconocida en la tabla {actual["tabla"]}: «{s}»')
            continue
        if s.startswith('Origen '):
            continue  # la cabecera repetida al cambiar de página
        if s == 'Existente Adaptado':
            actual['columnas'], actual['tipo'] = ['Adaptado'], 'alumbrado'
            continue
        if actual.get('tipo') == 'alumbrado':
            partes = s.split()
            if len(partes) >= 2 and partes[-1] in ('Sodio', 'LED'):
                actual['filas'].append({'origen': ' '.join(partes[:-1]), 'valores': [partes[-1]]})
                continue
        m = _FILA.match(s)
        if m and actual['columnas']:
            # Una celda es una sección («185») o un material con su sección («CU Desnudo 185»): la equivalencia
            # conserva otro material cuando la columna no tiene uno equivalente (Anexo 6, tablas 4 a 9).
            valores, previo = [], []
            for tok in m.group(2).split():
                if re.fullmatch(r'\d+(?:,\d+)?|-', tok):
                    valores.append({'material': ' '.join(previo), 'seccion_mm2': _num(tok)} if previo else _num(tok))
                    previo = []
                else:
                    previo.append(tok)
            if previo:
                raise GuiaError(f'{ACTO}: la tabla {actual["tabla"]}, fila «{s}» (línea {k + 1}) acaba en un material '
                                'sin sección')
            if len(valores) != len(actual['columnas']):
                raise GuiaError(f'{ACTO}: la tabla {actual["tabla"]}, fila «{s}» (línea {k + 1}) trae {len(valores)} '
                                f'valores y su cabecera {len(actual["columnas"])} columnas')
            if grupo is None:
                raise GuiaError(f'{ACTO}: la tabla {actual["tabla"]} tiene la fila «{s}» sin material de origen')
            actual['filas'].append({'origen': grupo, 'seccion_mm2': _num(m.group(1)),
                                    'valores': valores})
            continue
        if (actual['columnas'] and actual.get('tipo') in ('tension', 'tecnologia') and not re.search(r'\d', s[:1])
                and len(s) <= 40 and not s.endswith('.')):
            grupo = s
    vacias = [n for n, tb in tablas.items() if not tb['filas']]
    return {'tablas': [tablas[n] for n in sorted(tablas)], 'sin_filas_en_el_texto': vacias}


PAGINA_TABLA_14 = 180  # Anexo 6, numeral 4: la tabla de provincias exceptuadas está como imagen en el PDF
PPP_OCR = 400
TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
_TRAMO = re.compile(r'(\d+)\s*-\s*(\d+)\s*km|(\d+)\s*km')


def _grupos(valores) -> list[tuple[int, int]]:
    g: list[list[int]] = []
    for v in valores:
        if g and v - g[-1][-1] <= 3:
            g[-1].append(int(v))
        else:
            g.append([int(v)])
    return [(x[0], x[-1]) for x in g]


def _tramos(texto: str) -> list[list[int]]:
    """«0 - 3 km, 5 - 7 km y 10 - 16 km» → [[0, 3], [5, 7], [10, 16]]; «0 km» → [] (sin zona corrosiva)."""
    t = texto.replace('O', '0').replace('o', '0')
    tramos = []
    for m in _TRAMO.finditer(t):
        if m.group(3) is not None:
            if int(m.group(3)) != 0:
                raise GuiaError(f'{ACTO}: Tabla N° 14, franja «{texto}» sin tramo')
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if not a < b:
            raise GuiaError(f'{ACTO}: Tabla N° 14, tramo {a}-{b} km no creciente en «{texto}»')
        tramos.append([a, b])
    if not _TRAMO.search(t):
        raise GuiaError(f'{ACTO}: Tabla N° 14, la franja «{texto}» no se lee')
    return tramos


def tabla14_por_ocr(pdf: Path) -> dict:
    """La Tabla N° 14 del Anexo 6 (imagen): líneas de la cuadrícula por proyección, cada celda leída aparte con
    Tesseract (--psm 7). Se exige su forma: 3 columnas y cada franja en km; si no, se para."""
    import subprocess
    import tempfile
    from collections import Counter

    import numpy as np
    import pypdfium2
    from PIL import Image

    exe = Path(__import__('os').environ.get('CSG_TESSERACT', TESSERACT))
    if not exe.is_file():
        raise GuiaError(f'{ACTO}: la Tabla N° 14 es una imagen y hace falta Tesseract ({exe}); defina CSG_TESSERACT')
    version = subprocess.run([str(exe), '--version'], capture_output=True, text=True, check=False).stdout.split('\n')[0].strip()
    im = pypdfium2.PdfDocument(str(pdf))[PAGINA_TABLA_14 - 1].render(scale=PPP_OCR / 72).to_pil().convert('L')
    a = np.array(im) < 128
    alto, ancho = a.shape
    candidatas = _grupos([y for y in range(alto) if a[y].mean() > 0.45])
    extension = {}
    for g in candidatas:
        xs = np.where(a[g[0]])[0]
        extension[g] = (round(int(xs.min()), -1), round(int(xs.max()), -1))
    x_a, x_b = Counter(extension.values()).most_common(1)[0][0]
    propias = [g for g, e in extension.items() if e == (x_a, x_b)]
    lo, hi = propias[0][0], propias[-1][1]
    hs = [g for g in _grupos([y for y in range(alto) if a[y, x_a + 5:x_b - 5].mean() > 0.9]) if lo - 5 <= g[0] <= hi + 5]
    vs = _grupos([x for x in range(ancho) if a[hs[0][0]:hs[-1][1], x].mean() > 0.9])
    if len(vs) != 4:
        raise GuiaError(f'{ACTO}: Tabla N° 14 con {len(vs) - 1} columnas en la imagen; se esperan 3')
    filas = []
    with tempfile.TemporaryDirectory() as tmp:
        celda_png = Path(tmp) / 'celda.png'
        for i in range(len(hs) - 1):
            celdas = []
            for j in range(3):
                c = im.crop((vs[j][1] + 8, hs[i][1] + 8, vs[j + 1][0] - 8, hs[i + 1][0] - 8))
                c = c.resize((c.width * 2, c.height * 2), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
                lienzo = Image.new('L', (c.width + 80, c.height + 80), 255)
                lienzo.paste(c, (40, 40))
                lienzo.save(celda_png)
                r = subprocess.run([str(exe), str(celda_png), 'stdout', '-l', 'eng', '--psm', '7'],
                                   capture_output=True, text=True, check=True)
                celdas.append(re.sub(r'\s+', ' ', r.stdout).strip())
            if not any(celdas):
                continue
            dep, prov, franja = celdas
            if not dep or not prov:
                raise GuiaError(f'{ACTO}: Tabla N° 14, fila {i + 1} incompleta: {celdas}')
            filas.append({'departamento': dep, 'provincia': prov, 'literal_ocr': franja,
                          'tramos_corrosivos_km': _tramos(franja)})
    return {'tabla': 14, 'nivel': 'corrosivo', 'tipo': 'corrosivo_excepciones', 'pagina': PAGINA_TABLA_14,
            'columnas': ['Departamento', 'Provincia', 'Zona de Ambiente Corrosivo'],
            'origen_lectura': f'OCR celda a celda, {version}, página {PAGINA_TABLA_14} a {PPP_OCR} ppp',
            'filas': filas}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--fuentes', required=True, help='carpeta raíz de las fuentes oficiales (fuera de git)')
    ap.add_argument('--destino', required=True, help='raíz del repositorio')
    a = ap.parse_args()
    carpeta = Path(a.fuentes) / SUBCARPETA
    comprobar_carpeta(carpeta, '*.pdf')
    pdf = carpeta / PDF
    texto, version = extraer_texto(pdf)
    (carpeta / TXT).write_text(texto, encoding='utf-8', newline='\n')
    t = Texto(texto)
    sha_pdf = hashlib.sha256(pdf.read_bytes()).hexdigest()
    sha_txt = hashlib.sha256(texto.encode('utf-8')).hexdigest()
    a6 = anexo6(t)
    if a6['sin_filas_en_el_texto'] == [14]:  # la tabla 14 es una imagen: se lee por OCR (orden del usuario, 16-11)
        a6['tablas'] = [x for x in a6['tablas'] if x['tabla'] != 14] + [tabla14_por_ocr(pdf)]
        a6['sin_filas_en_el_texto'] = []
    # El esquema del registro no admite claves propias por norma: lo que no se pudo leer va en la nota, nunca a mano.
    pendientes = ''.join(f' Pendiente: Anexo 6, tabla N° {n}, sin filas en el texto extraído (probablemente imagen); '
                         'no se rellena a mano.' for n in a6['sin_filas_en_el_texto'])
    norma = {
        'acto': ACTO,
        'titulo': 'Guía de Elaboración del Valor Nuevo de Reemplazo de las Instalaciones de Distribución Eléctrica',
        'estado_juridico': 'vigente_comprobada',
        'fecha_emision': '2017-12-27',
        'fecha_publicacion': '2017-12-29',
        'vigencia_desde': '2017-12-30',
        'fecha_consulta': '2026-11-16',
        'fichero_local': (carpeta / TXT).as_posix(),
        'sha256': sha_pdf,
        'sha256_texto': sha_txt,
        'url': URL,
        'version': f'texto original (Lima, 27 de diciembre de 2017); texto extraído con pypdf {version}',
        'modifica': ['RCD 329-2004-OS/CD'],  # la sustituye entera (art. 1 y considerandos)
        'nota': ('Publicación comprobada en la separata especial de El Peruano del viernes 29 de diciembre de 2017, '
                 'pág. 4 (copia del regulador: https://www.osinergmin.gob.pe/Resoluciones/pdf/2017/'
                 'R_OSINERGMIN_No.231-2017-OS-CD.pdf, sha256 24a7856025dd1e539c1a9a66980ece26abea4d29913f943e72fde45eb6d41f81). '
                 'Vigencia por su art. 2: «a partir del día siguiente de su publicación en el diario oficial El '
                 'Peruano», es decir, el 2017-12-30. Sustituye a la guía de 2004 (RCD 329-2004-OS/CD y sus '
                 'modificatorias 336-2006 y 167-2012). Sin modificatorias de esta guía halladas al 2026-11-16: las '
                 'resoluciones posteriores fijan el VNR, no cambian la guía.') + pendientes,
        'reglas': reglas(t),
    }
    # El esquema registro_normativo_v1 no admite claves propias en la raíz (additionalProperties: false): quién lo
    # genera lo dice la nota de cada fichero de config/vnr y este mismo generador.
    registro = {'esquema': 'registro_normativo_v1', 'normas': [norma]}
    destino = Path(a.destino)
    (destino / 'config' / 'normativa').mkdir(parents=True, exist_ok=True)
    (destino / 'config' / 'vnr').mkdir(parents=True, exist_ok=True)
    salida = sin_rutas(registro, a.fuentes)
    (destino / 'config' / 'normativa' / 'rcd_232_2017.json').write_text(
        json.dumps(salida, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    equivalencias = {'esquema': 'vnr_anexo6_v1', 'acto': ACTO, 'anexo': 'Anexo 6, Tablas de Equivalencia',
                     'sha256_pdf': sha_pdf, 'sha256_texto': sha_txt,
                     'generado_por': 'tools/normativa/generar_guia_vnr_232.py', **a6}
    (destino / 'config' / 'vnr' / 'anexo6_equivalencias.json').write_text(
        json.dumps(equivalencias, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    a5 = {'esquema': 'vnr_anexo5_v1', 'acto': ACTO, 'anexo': 'Anexo 5, Formatos de Valorización y Metrados',
          'sha256_pdf': sha_pdf, 'sha256_texto': sha_txt, 'generado_por': 'tools/normativa/generar_guia_vnr_232.py',
          **anexo5(t)}
    (destino / 'config' / 'vnr' / 'anexo5_formatos.json').write_text(
        json.dumps(a5, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    a2 = anexo2(t)
    codigos = {'esquema': 'vnr_anexo2_v1', 'acto': ACTO, 'anexo': 'Anexo 2, Lista de Códigos VNR',
               'sha256_pdf': sha_pdf, 'sha256_texto': sha_txt, 'generado_por': 'tools/normativa/generar_guia_vnr_232.py',
               'codigos': a2, **anexo3(t)}
    (destino / 'config' / 'vnr' / 'anexo2_codigos.json').write_text(
        json.dumps(codigos, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(f'{ACTO}: {len(norma["reglas"])} reglas; Anexo 6: {len(a6["tablas"])} tablas, '
          f'{sum(len(x["filas"]) for x in a6["tablas"])} filas; sin filas: {a6["sin_filas_en_el_texto"]}; '
          f'Anexo 2: {len(a2)} códigos')
    return 0


def anexo3(t: Texto) -> dict:
    """Anexo 3, tablas 9 (tensiones nominales) y 11 (material de estructura): las claves de tensión y de secundario con
    las que el SICODI guarda cada costo estándar."""
    ini = t.texto.find('LISTA DE CÓDIGOS COMPLEMENTARIOS')
    salida = {}
    for n, clave, patron in ((9, 'tensiones', r'^(?:[A-ZÁÉÍÓÚ ]+ )?([A-Z]) (\d[\d,/]* k?V)$'),
                             (11, 'estructuras', r'^([A-Z]) ([A-ZÁÉÍÓÚ ().*]+?)\s*$')):
        i = t.texto.find(f'Tabla N° {n}', ini)
        j = t.texto.find(f'Tabla N° {n + 1}', i)
        if i < 0 or j < 0:
            raise GuiaError(f'{ACTO}: no está la tabla {n} del Anexo 3')
        filas = {}
        for linea in t.texto[i:j].split('\n')[1:]:
            m = re.match(patron, linea.replace('\f', '').strip())
            if m and not linea.strip().startswith(('CÓDIGO', 'NIVEL')):
                filas[m.group(1)] = m.group(2).replace(' (*)', '').strip()
        salida[clave] = filas
    if salida['tensiones'].get('D') != '10 kV' or salida['tensiones'].get('G') != '22,9 kV' \
            or salida['estructuras'].get('C') != 'CONCRETO' or salida['estructuras'].get('A') != 'MADERA':
        raise GuiaError(f'{ACTO}: tablas 9 y 11 del Anexo 3 leídas con forma inesperada: {salida}')
    return salida


def _unir_trozos(s: str, palabras: set[str]) -> str:
    """Une dos trozos de una palabra que el PDF separó con un espacio solo si la palabra unida existe en el propio texto
    oficial y el segundo trozo empieza en minúscula («Se rvicio» → «Servicio», «de l» → «del»; «En zanja» queda)."""
    def unir(m):
        a, b = m.group(1), m.group(2)
        if (a + b) in palabras and b[0].islower():
            return a + b
        return m.group(0)
    return re.sub(r'\b([^\W\d_]\w{0,2}) ([^\W\d_]\w*)\b', unir, s)


def anexo5(t: Texto) -> dict:
    """Anexo 5, Formatos de valorización y metrados: las filas del Formato N° 1 (A1) con su grupo, su ítem y su unidad,
    y el título de los cuatro formatos. B1, C1 y D1 repiten las filas de A1 a nivel de sector típico, sistema eléctrico
    y unidad de gestión (INE)."""
    ini = t.texto.find('Formato N°  1')
    fin = t.texto.find('Notas:', ini)
    if ini < 0 or fin < 0:
        raise GuiaError(f'{ACTO}: no está el Formato N° 1 del Anexo 5')
    filas, grupo, componente = [], '', ''
    en_tabla = False
    palabras = set(re.findall(r'\w+', t.texto))
    for linea in t.texto[ini:fin].split('\n'):
        s = re.sub(r'\s+', ' ', linea.replace('\f', '')).strip()
        s = _unir_trozos(s, palabras)  # «Se rvicio» → «Servicio»: espacios que mete el PDF
        if s.startswith('Item Descripción'):
            en_tabla = True
            continue
        if not en_tabla or not s or s.startswith(('US$', 'Total')):
            continue
        m = re.match(r'^(\d)\. (.+)$', s)
        if m:
            grupo = m.group(1)
            continue
        m = re.match(r'^([A-Z](?:\d(?:\.\d)?)?)\.? +(.+?)(?: (km|unidad|m2))?$', s)
        if not m:
            raise GuiaError(f'{ACTO}: Formato N° 1, fila no reconocida: «{s}»')
        item, desc, unidad = m.group(1), re.sub(' +', ' ', m.group(2)).strip(), m.group(3) or ''
        if len(item) == 1:
            componente = item
        if unidad:
            filas.append({'grupo': grupo, 'componente': componente, 'item': item, 'descripcion': desc,
                          'unidad': unidad})
    titulos = {}
    for n, codigo in ((1, 'A1'), (2, 'B1'), (3, 'C1'), (4, 'D1')):
        i = t.texto.find(f'Formato N°  {n}')
        m = re.search(r'Formato Resumen del Valor Nuevo de Reemplazo a Nivel de ([^\n]+)', t.texto[i:i + 400])
        if i < 0 or not m:
            raise GuiaError(f'{ACTO}: no está el título del Formato N° {n}')
        titulos[codigo] = 'Resumen del VNR a nivel de ' + re.sub(r'\s+', ' ', m.group(1)).strip()
    if len(filas) < 30 or {f['unidad'] for f in filas} != {'km', 'unidad', 'm2'}:
        raise GuiaError(f'{ACTO}: Formato N° 1 con forma inesperada ({len(filas)} filas)')
    return {'formatos': titulos, 'filas': filas,
            'notas': ['(1) Cantidad total de cada item',
                      '(2) Se calcula dividiendo el costo total de cada item entre la cantidad total correspondiente'],
            'unidad_costo': 'US$/unidad', 'unidad_subtotal': 'miles de US$'}


_CODIGO = re.compile(r'^((?=[A-Z0-9]*\d)[A-Z0-9]{5,9})\s+(\S.*?)\s*$')  # un código lleva al menos una cifra


def anexo2(t: Texto) -> list[dict]:
    """Anexo 2, Lista de Códigos VNR: cada código con su grupo, componente, subcomponente y descripción literal."""
    marca = 'LISTA DE CÓDIGOS VNR'
    ini = t.texto.find(marca)
    fin = t.texto.find('LISTA DE CÓDIGOS COMPLEMENTARIOS', ini)
    if ini < 0 or fin < 0:
        raise GuiaError(f'{ACTO}: no están los límites del Anexo 2')
    grupo = componente = sub = ''
    salida, vistos = [], {}
    for k in range(t._linea(ini), t._linea(fin)):
        s = t.lineas[k].replace('\f', '').strip()
        m = re.match(r'^Grupo (\d+) (.+)$', s)
        if m:
            grupo = f'{m.group(1)} {m.group(2).strip()}'
            continue
        m = re.match(r'^Componente ([A-Z]) (.+)$', s)
        if m:
            componente = f'{m.group(1)} {m.group(2).strip()}'
            continue
        m = re.match(r'^Subcomponente (\S+) (.+)$', s)
        if m:
            sub = f'{m.group(1)} {re.sub(" +", " ", m.group(2)).strip()}'
            continue
        m = _CODIGO.match(s)
        if m and grupo and not s.startswith(('Código', 'Anexo', 'Tabla')):
            codigo, desc = m.group(1), re.sub(r'\s+', ' ', m.group(2))
            clave = (grupo, sub, codigo)
            if clave in vistos:
                raise GuiaError(f'{ACTO}: Anexo 2, código {codigo} repetido en {grupo} › {sub} (líneas {vistos[clave]} y {k + 1})')
            vistos[clave] = k + 1
            salida.append({'codigo': codigo, 'descripcion': desc, 'grupo': grupo, 'componente': componente,
                           'subcomponente': sub, 'linea': k + 1, 'pagina': t.pagina_de[k]})
    if not salida:
        raise GuiaError(f'{ACTO}: Anexo 2 sin códigos')
    return salida


if __name__ == '__main__':
    raise SystemExit(main())
