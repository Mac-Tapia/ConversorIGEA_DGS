"""107 T19 y T26: los formatos F-001 a F-523 de la Norma Tarifas (RCD 217-2013-OS/CD), transcritos de sus libros Excel
oficiales («NormaTarifas2013.rar», publicado por Osinergmin junto a la norma), hoja por hoja y fila por fila.

Nada se interpreta: cada formato guarda su título y las celdas no vacías de cada fila de la plantilla, con la letra de
su columna, tal como están en el libro. Se lee con el lector común calamine (memoria leer-todos-los-formatos-y-hojas).
Sale un fichero del registro que AMPLÍA la norma 217-2013 con una regla por formato (registro_normativo_v1).

Celdas sombreadas (delta20): cada formato lleva ``no_llenar`` (``sombreadas_217.py``), con los rellenos leídos con
xlrd de los libros oficiales y cotejados con el mapa derivado ``<fuentes>/PIT_NORMA/rcd_217-2013_formatos/sombreadas/``
(SHA256SUMS); los rellenos de color, como observación (``colores``) sin efecto.

Uso: python -I -X utf8 tools/normativa/generar_formatos_217.py --fuentes <carpeta de fuentes> --destino <repo>
"""
import hashlib
import json
import sys
from pathlib import Path

import python_calamine as pc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fuentes import comprobar, comprobar_carpeta  # noqa: E402  comprobación permanente de las fuentes (28)
from sombreadas_217 import (GRISES_SHA, MapaSombreadasError, cargar_grises, colores_del_formato, cotejar,  # noqa: E402
                            leer_rellenos, no_llenar)

# Auditoría D.2 (2026-11-24): una sola copia, en tools/normativa/fuentes.py.
def _argumentos(descripcion: str):
    from fuentes import argumentos_de_generador
    return argumentos_de_generador(descripcion)


_a = _argumentos('Formatos de la Norma Tarifas (RCD 217-2013-OS/CD) transcritos de sus libros Excel oficiales, con las llamadas a nota separadas del rótulo.')
BASE = Path(_a.fuentes) / 'PIT_NORMA' / 'rcd_217-2013_formatos'
OUT = Path(_a.destino) / 'config' / 'normativa'
RAR = BASE / 'rar' / 'NormaTarifas2013.rar'
URL_RAR = ('https://www.osinergmin.gob.pe/seccion/centro_documental/gart/procesosregulatorios/electricidad/Infotec/'
           'NormaTarifas2013.rar')
PAGINA = 'https://prie.osinergmin.gob.pe/propuesta-tarifaria'


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def letra(j: int) -> str:
    s = ''
    j += 1
    while j:
        j, r = divmod(j - 1, 26)
        s = chr(65 + r) + s
    return s


def texto(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


# Superíndices (delta17, frente w0 de cc, apoyo (cc), frente «w0_superindices_formatos»): por libro, las celdas cuyo
# texto lleva una llamada a nota en superíndice. Se guarda el texto literal y, aparte, el rótulo sin la llamada; los
# exponentes (r² de F-106/F-107) quedan literales con su motivo. Una celda «revisar» detiene la transcripción.
# El rar oficial, contra el sha que registró la primera transcripción (nota de rcd_217_2013_formatos.json).
RAR_SHA = '911c3712b0d44da1bdcd3ffef3019a9bcc5232c5aebb8d32a2a4f00c236f3448'
comprobar(RAR, RAR_SHA)
comprobar_carpeta(BASE / 'xls_del_rar', '*.xls')
DERIVADO = BASE / 'sombreadas'
comprobar_carpeta(DERIVADO)                     # el mapa derivado, contra su SHA256SUMS.txt
GRISES = cargar_grises(DERIVADO / 'GRISES_217.json')
COLORES = json.loads((DERIVADO / 'COLORES_217_mapa.json').read_text(encoding='utf-8'))
LEIDOS = {}
for _libro in sorted((BASE / 'xls_del_rar').glob('*.xls')):
    LEIDOS.update(leer_rellenos(_libro))
cotejar(LEIDOS, GRISES, COLORES)
PROCEDENCIA_SOMBREADAS = (f'rellenos leídos con xlrd (formatting_info) de los libros oficiales del rar (sha comprobado), '
                          f'cotejados con el mapa derivado <fuentes>/PIT_NORMA/rcd_217-2013_formatos/sombreadas/ '
                          f'(GRISES_217.json sha256 {GRISES_SHA}, del apoyo (cc), frente «z6_cotejo_resto»): mismas '
                          f'celdas')
SUPERINDICES = {}
for f in comprobar_carpeta(BASE / 'superindices', 'superindices_*.json'):
    d = json.loads(f.read_text(encoding='utf-8'))
    SUPERINDICES[Path(d['libro']).name] = d

reglas = []
libros_sin_revisar = []
for libro in sorted((BASE / 'xls_del_rar').glob('*.xls')):   # los ORIGINALES del rar: las copias de xls/ cambiaron de bytes (14-11)
    wb = pc.CalamineWorkbook.from_path(str(libro))
    huella = sha(libro)
    for hoja in wb.sheet_names:
        filas = wb.get_sheet_by_name(hoja).to_python()
        literales = []
        for i, fila in enumerate(filas, 1):
            celdas = {letra(j): texto(v) for j, v in enumerate(fila) if texto(v)}
            if celdas:
                literales.append({'fila': i, 'celdas': celdas})
        if not literales:
            raise SystemExit(f'{libro.name}:{hoja} está vacía: no se transcribe a ciegas')
        sup = SUPERINDICES.get(libro.name)
        if sup is None:
            if libro.name not in libros_sin_revisar:
                libros_sin_revisar.append(libro.name)
        else:
            if sup['sha256'] != huella:
                raise SystemExit(f'{libro.name}: los superíndices son de otro libro (sha {sup["sha256"][:12]})')
            por_fila = {f['fila']: f for f in literales}
            for c in sup['celdas']:
                if c['hoja'] != hoja or c['clase'] in ('sin_superindice', 'sin_llamada'):  # sin_llamada: solo formato
                    continue
                col = ''.join(ch for ch in c['celda'] if ch.isalpha())
                fil = int(''.join(ch for ch in c['celda'] if ch.isdigit()))
                fila = por_fila.get(fil)
                if fila is None or fila['celdas'].get(col, '') != texto(c['texto_xlrd']):
                    raise SystemExit(f'{libro.name}:{hoja}!{c["celda"]}: calamine no da el texto de xlrd '
                                     f'({(fila or {}).get("celdas", {}).get(col)!r} frente a {c["texto_xlrd"]!r})')
                if c['clase'] == 'llamada':
                    fila.setdefault('llamadas', {})[col] = {'rotulo': texto(c['rotulo_limpio']), 'llamada': c['llamada']}
                elif c['clase'] == 'exponente':
                    fila.setdefault('exponentes', {})[col] = c.get('motivo', '')
                else:
                    raise SystemExit(f'{libro.name}:{hoja}!{c["celda"]}: superíndice por revisar ({c["clase"]})')
        codigo = next((c for c in literales[0]['celdas'].values() if c.startswith('F-')), None)
        if codigo != hoja:
            raise SystemExit(f'{libro.name}:{hoja}: la fila 1 dice {codigo!r}, no el código de la hoja')
        titulo = ' '.join(literales[1]['celdas'].values()) if len(literales) > 1 else ''
        cabecera = ' | '.join(' '.join(f['celdas'].values()) for f in literales[:4])
        reglas.append({
            'clave': f'pit.formato.{hoja}',
            'valor': {'codigo': hoja, 'titulo': titulo, 'libro': libro.name, 'hoja': hoja, 'sha256_libro': huella,
                      'filas_en_hoja': len(filas), 'filas': literales,
                      'no_llenar': no_llenar(hoja, libro.name, literales, LEIDOS.get(hoja), PROCEDENCIA_SOMBREADAS),
                      **({'colores': colores_del_formato(LEIDOS.get(hoja))} if colores_del_formato(LEIDOS.get(hoja))
                         else {})},
            'unidad': '',
            'articulo_o_anexo': 'art. 30 (Título IV) y art. 4 de la resolución: archivos Excel de los formatos',
            'pagina': f'libro {libro.name}, hoja {hoja}',
            'lineas': f'filas 1-{len(filas)}',
            'cita_literal': cabecera,
            'interpretacion': ('plantilla transcrita literal: celdas no vacías por fila y columna; los «…» y «Línea '
                               'n» de la plantilla indican filas que se repiten, no un número fijo'),
        })

sobran = sorted(set(GRISES) - {r['valor']['hoja'] for r in reglas})
if sobran:
    raise MapaSombreadasError(f'el mapa de celdas sombreadas trae hojas que los libros no tienen: {sobran}')
OUT.mkdir(parents=True, exist_ok=True)
datos = {
    'esquema': 'registro_normativo_v1',
    'amplia': 'RCD 217-2013-OS/CD',
    'nota': (f'Formatos de la Norma Tarifas en sus libros oficiales: {URL_RAR} (enlazado en {PAGINA}, '
             f'«Formularios de norma Tarifas y Compensaciones de Sistemas Secundarios y Complementarios»), sha256 del '
             f'rar {sha(RAR)}, descargado el 2026-11-14. Seis libros con fecha 06-11-2013 y {len(reglas)} hojas, una por '
             'formato, como la tabla 1 del art. 30.1. Las modificatorias leídas (018-2018 y 242-2021) no cambian '
             'formatos; la 177-2021 no está leída. Superíndices: las llamadas a nota van aparte del rótulo («llamadas»), '
             f'según el análisis de formato del libro (xlrd); libros sin revisar: {", ".join(libros_sin_revisar) or "ninguno"}.'),
    'reglas': reglas,
}
(OUT / 'rcd_217_2013_formatos.json').write_text(
    json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
print('formatos', len(reglas), 'rar', sha(RAR)[:16], 'sombreadas',
      {r['valor']['codigo']: r['valor']['no_llenar']['celdas'] for r in reglas if r['valor']['no_llenar']['celdas']})
