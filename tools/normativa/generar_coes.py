"""T28 (107, paso 3b): registro de datos del COES y de las horas punta, generado desde las fuentes descargadas.

Escribe config/normativa/coes_maxima_demanda_sein.json (esquema registro_normativo_v1). Todo número y toda fecha se
lee de la fuente; nada se teclea:
  - máxima ANUAL del SEIN por año (fuente primaria): Estadística Anual del COES, cap. 05, hoja BD, «COMPARATIVO DE
    MÁXIMA DEMANDA» (filas 45-47);
  - 12 máximas MENSUALES ejecutadas (contraste): cap. 01, hoja BD, filas 16-27;
  - la definición del intervalo (15 min, potencia media, horas punta): Glosario de los procedimientos del COES;
  - las horas punta: RM 153-2021-MINEM/DM (17:00-23:00, del 2021-06-01 al 2025-05-31) y RM 189-2025-MINEM/DM
    (18:00-23:00, del 2025-06-01 al 2029-05-31), las dos de El Peruano.
La fecha anual de 2024 viene con año 2023 en las dos estadísticas; el contraste mensual (la mayor de 2024 es la de
noviembre de 2024, con la misma potencia) la sitúa en 2024: se guarda lo publicado y lo corregido, con la marca.

Uso: python -I -X utf8 tools/normativa/generar_coes.py --fuentes <carpeta de fuentes> --destino <repo>
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from python_calamine import CalamineWorkbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fuentes import comprobar_carpeta, sin_rutas  # noqa: E402  comprobación de fuentes y del registro (28)

COES = Path('COES_SEIN')        # lo fija main() desde --fuentes
CAP05 = 'Capítulo 05_DEMANDA DE ENERGÍA ELÉCTRICA.xlsx'
CAP01 = 'Capítulo 01_PRINCIPALES INDICADORES DE OPERACIÓN DEL SEIN.xlsx'
URL_EA = 'https://www.coes.org.pe/Portal/browser/download?url=Publicaciones/Estadisticas Anuales/{a}/Excel/{c}'
MESES = ('ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SET', 'OCT', 'NOV', 'DIC')
CONSULTA = '2026-11-14'
URL_GLOSARIO = ('https://www.coes.org.pe/Portal/browser/download?url=Marco+Normativo%2FProcedimientos%2FGlosario+de+'
                'Terminos%2FGlosario+de+T%C3%A9rminos.pdf')
# Páginas del PDF (38 páginas) donde están las definiciones, comprobadas con pdftotext página a página.
PAG_PUNTA, PAG_MAXIMA = '17', '19'


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hoja(p: Path):
    return CalamineWorkbook.from_path(str(p)).get_sheet_by_name('BD').to_python()


def lineas(texto: Path, *trozos: str) -> tuple[str, str]:
    """Líneas (1-based) del texto donde empieza el primer trozo y acaba el último, y la cita literal unida."""
    # errors='replace': el texto del PR-30 trae símbolos matemáticos del PDF que no son UTF-8 válido; las líneas que
    # se citan no los tienen, y el sha256_texto es el del fichero tal cual.
    L = texto.read_bytes().decode('utf-8', errors='replace').split('\n')
    ini = next(i for i, x in enumerate(L) if trozos[0] in x)
    fin = next(i for i in range(ini, len(L)) if trozos[-1] in L[i])
    return f'{ini + 1}-{fin + 1}', ' '.join(x.strip() for x in L[ini:fin + 1])


def _hojas_absolutas(p: Path):
    """Cada hoja con sus filas en coordenadas de Excel: la fila i de la lista es la fila i+1 de la hoja."""
    wb = CalamineWorkbook.from_path(str(p))
    for nombre in wb.sheet_names:
        yield nombre, wb.get_sheet_by_name(nombre).to_python(skip_empty_area=False)


def _letra(i: int) -> str:
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def maxima_anual(anio: int):
    """La tabla «COMPARATIVO DE MÁXIMA DEMANDA» del cap. 05, en la hoja que la traiga: la fila «Potencia (MW)», la
    siguiente «Fecha / hora» y, encima, la cabecera con la columna del año."""
    p = COES / str(anio) / CAP05
    for hoja_n, f in _hojas_absolutas(p):
        for i, fila in enumerate(f):
            for j, c in enumerate(fila):
                if str(c).strip().startswith('Potencia (MW)') and i + 1 < len(f) and \
                        str(f[i + 1][j]).replace(' ', '').startswith('Fecha/hora'):
                    cab = next(k for k in range(i - 1, max(i - 4, -1), -1) if any(str(anio) in str(x) for x in f[k]))
                    col = next(k for k, x in enumerate(f[cab]) if str(anio) in str(x))
                    titulo = next((k for k in range(cab, max(cab - 4, -1), -1)
                                   if any('COMPARATIVO DE MÁXIMA DEMANDA' in str(x) for x in f[k])), None)
                    assert titulo is not None, (anio, hoja_n, i)
                    potencia, instante = float(f[i][col]), f[i + 1][col]
                    assert isinstance(instante, dt.datetime), (anio, instante)
                    nota = next(str(x) for r in f[i + 2:i + 6] for x in r if str(x).startswith('(*)'))
                    rotulo = str(f[cab][col]).replace('\n', ' ')
                    donde = (f'hoja {hoja_n}, título en la fila {titulo + 1}, cabecera {_letra(col)}{cab + 1}, '
                             f'cifras {_letra(col)}{i + 1} y {_letra(col)}{i + 2}')
                    return p, rotulo, potencia, instante, nota, donde
    raise SystemExit(f'{p.name}: sin la tabla de máxima demanda anual')


def mensuales(anio: int):
    """Las 12 máximas mensuales ejecutadas: en 2024-2025, cap. 01, hoja BD, filas «MÁXIMA DEMANDA (MW)» con el mes;
    en 2022, cap. 05, la hoja con la fila «TOTAL MÁXIMA DEMANDA MENSUAL» bajo la cabecera ENE..DIC."""
    p1 = COES / str(anio) / CAP01
    for hoja_n, f in _hojas_absolutas(p1):
        filas = [(i, r) for i, r in enumerate(f) if len(r) > 2 and str(r[1]).startswith('MÁXIMA DEMANDA')
                 and str(r[2]) in MESES]   # después de los 12 meses vienen filas por tecnología (SOLAR, BESS…)
        if len(filas) == 12:
            assert [str(r[2]) for _i, r in filas] == list(MESES), (anio, hoja_n)
            meses = {str(r[2]): float(r[4]) for _i, r in filas}
            return p1, meses, f'{CAP01}, hoja {hoja_n}, filas {filas[0][0] + 1}-{filas[-1][0] + 1} (columna E, lo ejecutado)'
    p5 = COES / str(anio) / CAP05
    for hoja_n, f in _hojas_absolutas(p5):
        for i, r in enumerate(f):
            if any(str(x).strip() == 'TOTAL MÁXIMA DEMANDA MENSUAL' for x in r):
                cab = next(k for k in range(i - 1, max(i - 8, -1), -1) if 'ENE' in [str(x) for x in f[k]])
                c0 = [str(x) for x in f[cab]].index('ENE')
                assert [str(x) for x in f[cab][c0:c0 + 12]] == list(MESES), (anio, hoja_n)
                meses = {m: float(f[i][c0 + k]) for k, m in enumerate(MESES)}
                return p5, meses, (f'{CAP05}, hoja {hoja_n}, fila {i + 1} «TOTAL MÁXIMA DEMANDA MENSUAL», '
                                   f'{_letra(c0)}{i + 1}:{_letra(c0 + 11)}{i + 1}')
    raise SystemExit(f'{anio}: sin las 12 máximas mensuales')


def norma_anual(anio: int) -> dict:
    p, rotulo, potencia, instante, nota, donde = maxima_anual(anio)
    pm, meses, donde_m = mensuales(anio)
    mes_max = max(meses, key=meses.get)
    publicado = {'fecha': instante.strftime('%Y-%m-%d'), 'hora': instante.strftime('%H:%M')}
    valor = {'anio': anio, 'potencia_mw': potencia, **publicado, 'intervalo_min': 15,
             'fuente': 'estadistica_anual', 'contraste_mensual': {'mes_de_la_mayor': mes_max,
                                                                  'potencia_mw': meses[mes_max],
                                                                  'coincide_potencia': abs(meses[mes_max] - potencia) < 1e-6}}
    interpretacion = 'Se toma tal como la publica el COES.'
    if instante.year != anio:
        mes_num = MESES.index(mes_max) + 1
        assert valor['contraste_mensual']['coincide_potencia'] and instante.month == mes_num, (anio, instante, mes_max)
        corregido = instante.replace(year=anio)
        valor.update({'fecha': corregido.strftime('%Y-%m-%d'), 'publicado': publicado,
                      'marca': 'corregido por el contraste mensual'})
        interpretacion = (f'La estadística de {anio} publica la máxima anual con fecha {publicado["fecha"]}, fuera de su '
                          f'año. El contraste mensual de la misma estadística da la mayor de {anio} en '
                          f'{mes_max} de {anio} con la misma potencia ({meses[mes_max]:.3f} MW), así que se usa '
                          f'{valor["fecha"]} {publicado["hora"]} con la marca «corregido por el contraste mensual» y '
                          'se conserva lo publicado. Decisión del auditor ca (2026-11-14 05:25).')
    cita = (f'COMPARATIVO DE MÁXIMA DEMANDA · {rotulo} · Potencia (MW) {potencia} · Fecha / hora '
            f'{instante.strftime("%Y-%m-%d %H:%M")} · {nota}')
    return {
        'acto': f'COES Estadística Anual {anio}, cap. 05',
        'titulo': f'Estadística Anual {anio} del COES, capítulo 05 «Demanda de energía eléctrica» (máxima demanda del SEIN)',
        'estado_juridico': 'vigente_comprobada', 'url': URL_EA.format(a=anio, c=CAP05), 'fecha_consulta': CONSULTA,
        'sha256': sha(p), 'fichero_local': str(p).replace('\\', '/'), 'vigencia_desde': f'{anio}-01-01',
        'nota': (f'Publicación oficial de datos del COES, no una norma: dato común a todas las empresas. Contraste: '
                 f'{pm.name} (sha256 {sha(pm)}), {donde_m}.'),
        'reglas': [
            {'clave': f'coes.sein.maxima_anual.{anio}', 'valor': valor, 'unidad': 'MW', 'pagina': donde,
             'articulo_o_anexo': 'Capítulo 05, «COMPARATIVO DE MÁXIMA DEMANDA»',
             'cita_literal': cita, 'interpretacion': interpretacion},
            {'clave': f'coes.sein.maximas_mensuales.{anio}', 'valor': meses, 'unidad': 'MW',
             'articulo_o_anexo': 'Máxima demanda ejecutada por mes', 'pagina': donde_m,
             'cita_literal': ' · '.join(f'{m} {v}' for m, v in meses.items()),
             'interpretacion': 'Contraste de la anual: la mayor de las 12 tiene que coincidir con la anual; si no, se '
                               'nombra la diferencia.'}]}


def main(destino: str, fuentes: str) -> None:
    global COES, REPORTES, MEDICION
    COES, MEDICION = Path(fuentes) / 'COES_SEIN', Path(fuentes) / 'MEDICION'
    REPORTES = COES / 'reporte_maxima_demanda'
    # Antes de leer nada, cada fuente oficial contra su SHA256SUMS.txt (orden de 28, 2026-11-15).
    for d in ('2022', '2024', '2025', 'reporte_maxima_demanda', 'procedimientos', 'procedimientos/rm_153_2021_minem',
              'procedimientos/rm_189_2025_minem', 'procedimientos/pr30_vigente', 'procedimientos/rcd_173_2026',
              'procedimientos/serie_demanda_30min'):
        comprobar_carpeta(COES / d)
    for d in ('rm_496_2005', 'inacal_guia_tupa_2019'):
        comprobar_carpeta(MEDICION / d)
    rm = COES / 'procedimientos/rm_153_2021_minem'
    html, texto = rm / 'dispositivo_1956880-1.html', rm / 'texto.txt'
    l1, c1 = lineas(texto, 'Artículo 1.-', 'inciso e) del artículo 110 del Reglamento de la Ley de Concesiones Eléctricas.')
    l2, c2 = lineas(texto, 'Artículo 2.-', 'entrará en vigencia el 1 de junio de 2021')
    rm189 = COES / 'procedimientos/rm_189_2025_minem'
    html189, texto189 = rm189 / 'dispositivo_EX_2405081-1.html', rm189 / 'texto.txt'
    l189_1, c189_1 = lineas(texto189, 'Artículo 1.-', 'aprobado por Decreto Supremo Nº 009-93-EM.')
    l189_2, c189_2 = lineas(texto189, 'Artículo 2.-', 'hasta el 31 de mayo de 2029.')
    glos_txt = COES / 'procedimientos/glosario.txt'
    lg, cg = lineas(glos_txt, 'Máxima demanda mensual a nivel de generación:', 'en el mes. Este intervalo es el Intervalo de Punta del mes.')
    lp, cp = lineas(glos_txt, 'Intervalo de Punta del mes:', 'la Ley de Concesiones Eléctricas.')
    registro = {
        'esquema': 'registro_normativo_v1',
        'nota': ('Generado por tools/normativa/generar_coes.py desde las fuentes descargadas. Registro '
                 'de datos del COES (máxima demanda anual del SEIN por año, reemplazable por año) y horas punta del MINEM.'),
        'normas': [
            {'acto': 'RM 153-2021-MINEM/DM', 'titulo': 'Fijan Horas de Punta del Sistema Eléctrico Interconectado Nacional',
             'estado_juridico': 'vigente_comprobada', 'url': 'https://busquedas.elperuano.pe/dispositivo/NL/1956880-1',
             'fecha_publicacion': '2021-05-27', 'fecha_consulta': '2026-11-15', 'sha256': sha(html),
             'sha256_texto': sha(texto), 'fichero_local': str(html).replace('\\', '/'),
             'vigencia_desde': '2021-06-01', 'vigencia_hasta': '2025-05-31',
             'vigencia_hasta_motivo': ('fin deducido: inicio de la RM 189-2025-MINEM/DM (2025-06-01), sin derogación '
                                       'expresa (la 189-2025 no tiene artículo derogatorio y solo la cita en un considerando '
                                       'como «vigente a la fecha»); su Artículo 2 fija el periodo «2021 al 2025» y el ciclo '
                                       'de cuatro años es el del RLCE, art. 110 e) (apoyo (cc), frente «z13_rm189_2025_horas_punta»)'),
             'nota': ('Art. 2: vigente desde el 1 de junio de 2021 para 2021-2025. La sustituye desde el 2025-06-01 la RM '
                      '189-2025-MINEM/DM (su considerando la cita como «vigente a la fecha» el 31-05-2025), así que rige '
                      'hasta el 2025-05-31. Fecha de publicación (27/05/2021): la de la página de El Peruano, línea 9 de '
                      'texto.txt.'),
             'reglas': [
                 {'clave': 'sein.horas_punta', 'valor': {'desde': '17:00', 'hasta': '23:00'}, 'articulo_o_anexo': 'Artículo 1',
                  'pagina': 'única (edición web de El Peruano, dispositivo 1956880-1)',
                  'lineas': l1, 'cita_literal': c1},
                 {'clave': 'sein.horas_punta.periodo', 'valor': {'desde': '2021-06-01', 'anios': [2021, 2025]},
                  'articulo_o_anexo': 'Artículo 2', 'pagina': 'única (edición web de El Peruano, dispositivo 1956880-1)',
                  'lineas': l2, 'cita_literal': c2}]},
            {'acto': 'RM 189-2025-MINEM/DM', 'titulo': 'Definen Horas de Punta del Sistema Eléctrico Interconectado Nacional',
             'estado_juridico': 'vigente_comprobada', 'url': 'https://busquedas.elperuano.pe/dispositivo/EX/2405081-1',
             'fecha_publicacion': '2025-05-31', 'fecha_consulta': '2026-11-15', 'sha256': sha(html189),
             'sha256_texto': sha(texto189), 'fichero_local': str(html189).replace('\\', '/'),
             'vigencia_desde': '2025-06-01', 'vigencia_hasta': '2029-05-31',
             'nota': ('Edición extraordinaria de El Peruano (la ruta NL da 404). La localizó cc (apoyo de f4) el '
                      '2026-11-15, en apoyo (cc), frente «a_horas_punta_y_convencion;» f4 comprobó las líneas 17-18 y '
                      'las huellas. PDF oficial de la edición extraordinaria N.º 18622 del 31-05-2025, pág. 1 (firmado '
                      'por Editora Perú el 31/05/2025 19:13), sha256 '
                      '9bc3db86689fd43505975d764c57804cc65f28288c7c97601a479f887eecd627: contiene literales las líneas '
                      '6, 11, 17 y 18 del texto (apoyo (cc), frente «z13_rm189_2025_horas_punta»).'),
             'reglas': [
                 {'clave': 'sein.horas_punta', 'valor': {'desde': '18:00', 'hasta': '23:00'}, 'articulo_o_anexo': 'Artículo 1',
                  'pagina': 'única (edición web de El Peruano, dispositivo EX 2405081-1)', 'lineas': l189_1,
                  'cita_literal': c189_1},
                 {'clave': 'sein.horas_punta.periodo', 'valor': {'desde': '2025-06-01', 'hasta': '2029-05-31'},
                  'articulo_o_anexo': 'Artículo 2', 'pagina': 'única (edición web de El Peruano, dispositivo EX 2405081-1)',
                  'lineas': l189_2, 'cita_literal': c189_2}]},
            {'acto': 'COES Glosario de los Procedimientos Técnicos',
             'titulo': 'Glosario de abreviaturas y definiciones utilizadas en los procedimientos técnicos del COES SINAC',
             'estado_juridico': 'vigente_comprobada', 'sha256': sha(COES / 'procedimientos/glosario.pdf'),
             'url': URL_GLOSARIO, 'fecha_consulta': CONSULTA,
             'sha256_texto': sha(glos_txt), 'fichero_local': str(COES / 'procedimientos/glosario.pdf').replace('\\', '/'),
             'reglas': [
                 {'clave': 'coes.sein.intervalo_maxima', 'valor': {'minutos': 15, 'magnitud': 'potencia_media'},
                  'articulo_o_anexo': 'Definiciones: «Máxima demanda mensual a nivel de generación»',
                  'pagina': PAG_MAXIMA, 'lineas': lg, 'cita_literal': cg},
                 {'clave': 'coes.sein.intervalo_punta', 'valor': 'intervalo de 15 minutos de la máxima mensual en horas punta',
                  'articulo_o_anexo': 'Definiciones: «Intervalo de Punta del mes»', 'pagina': PAG_PUNTA,
                  'lineas': lp, 'cita_literal': cp},
                 {'clave': 'coes.sein.convencion_marca_tiempo', 'valor': 'no_declarada',
                  'articulo_o_anexo': 'Definiciones: «Máxima demanda mensual a nivel de generación»',
                  'pagina': PAG_MAXIMA, 'lineas': lg, 'cita_literal': cg,
                  'interpretacion': ('El glosario define el intervalo de 15 minutos, pero no dice si la hora publicada '
                                     'rotula su inicio o su fin. Decisión de ca (05:40), confirmada por 28 (23:31): se '
                                     'calculan las dos alineaciones, [h, h+15) y [h−15, h); si dan lo mismo dentro de la '
                                     'tolerancia, se usa con la marca «convención no declarada; resultado igual en las '
                                     'dos»; si difieren, hueco con las dos cifras.')}]},
            norma_anual(2022), norma_anual(2024), norma_anual(2025), norma_reporte(2022), norma_reporte(2024),
            norma_reporte(2025),
            *normas_convencion_y_pr30()]}
    salida = Path(destino) / 'config/normativa/coes_maxima_demanda_sein.json'
    salida.write_text(json.dumps(sin_rutas(registro, COES.parent), ensure_ascii=False, indent=1) + '\n',
                      encoding='utf-8', newline='\n')
    print(salida, sha(salida)[:16])
    medida = Path(destino) / 'config/normativa/medida_clase_precision.json'
    medida.write_text(json.dumps(sin_rutas(registro_medida(), COES.parent), ensure_ascii=False, indent=1) + '\n',
                      encoding='utf-8', newline='\n')
    print(medida, sha(medida)[:16])


REPORTES = COES / 'reporte_maxima_demanda'   # ídem
URL_REPORTE = 'https://www.coes.org.pe/Portal/Medidores/maximademanda/ReporteMaximaDemanda'


def norma_reporte(anio: int) -> dict:
    """Tercera fuente (contraste): el reporte público de Máxima Demanda del COES, uno por mes, con tipoCentral=0
    (todos). Sus MW son de medidores, no consolidados: para los MW manda la Estadística Anual."""
    import html as _html
    import re
    meses, citas, huellas = {}, [], []
    for m in range(1, 13):
        f = REPORTES / f'md_{anio}-{m:02d}_central0.html'
        s = re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', f.read_text(encoding='utf-8', errors='replace'))))
        g = re.search(r'SEIN MW (\d\d/\d\d/\d{4}) (\d\d:\d\d) [\d.,]+ [\d.,]+ ((?:\d{1,3} )*\d{1,3},\d+) Nota: (.*? h\.)', s)
        assert g, f
        d, mth, a = g.group(1).split('/')
        assert int(a) == anio and int(mth) == m, (f, g.group(1))
        meses[MESES[m - 1]] = {'fecha': f'{a}-{mth}-{d}', 'hora': g.group(2),
                               'potencia_mw': float(g.group(3).replace(' ', '').replace(',', '.')),
                               'nota_horas_punta': g.group(4), 'sha256': sha(f), 'fichero': f.name}
        citas.append(f'{MESES[m - 1]}: «SEIN MW {g.group(1)} {g.group(2)} … {g.group(3)}»')
        huellas.append(f'{sha(f)}  {f.name}')
    manifiesto = hashlib.sha256(chr(10).join(huellas).encode('utf-8')).hexdigest()
    return {
        'acto': f'COES Reporte de Máxima Demanda {anio}',
        'titulo': f'Reporte público de máxima demanda del SEIN, por mes, {anio} (COES, Portal de medidores)',
        'estado_juridico': 'vigente_comprobada', 'url': URL_REPORTE, 'fecha_consulta': '2026-11-15',
        'sha256': manifiesto, 'fichero_local': REPORTES.as_posix(), 'vigencia_desde': f'{anio}-01-01',
        'nota': ('POST con tipoCentral=0&tipoGeneracion=-1&idEmpresa=-1&mes=AAAA-MM; 12 HTML. El sha256 de la norma es el '
                 'del manifiesto «sha256  fichero» de los 12, en orden de mes. Localizado por cc '
                 '(apoyo (cc), frente «b_maximas_mensuales_2024»).'),
        'reglas': [{'clave': f'coes.sein.reporte_mensual.{anio}', 'valor': meses, 'unidad': 'MW',
                    'articulo_o_anexo': 'Máxima demanda en hora punta, fila «SEIN MW»', 'pagina': 'una por mes (HTML)',
                    'cita_literal': ' · '.join(citas),
                    'interpretacion': ('Contraste de fecha y hora de la máxima anual. Sus MW salen de medidores y no '
                                       'coinciden con la estadística; si su mayor mes no es el de la anual, se nombra.')}]}


def normas_convencion_y_pr30() -> list[dict]:
    """Decisiones de 28 (2026-11-15): la alineación por defecto del instante del SEIN es la de FIN de intervalo,
    [h-15, h), como práctica observada del COES (no norma); y el PR-30 vigente hasta el 2026-12-31, al que sustituye
    desde el 2027-01-01 el aprobado por la RCD 95-2026-OS/CD (RCD 173-2026-OS/CD)."""
    import json as _json
    proc = COES / 'procedimientos'
    serie = proc / 'serie_demanda_30min/demanda_2025-03-26.json'
    datos = next(s['Data'] for s in _json.loads(serie.read_text(encoding='utf-8'))['Chart']['Series']
                 if s['Name'] == 'Ejecutado')
    primero, ultimo = datos[0]['Nombre'], datos[-1]['Nombre']
    assert primero.endswith('00:30:00') and ultimo.endswith('00:00:00') and len(datos) == 48, (primero, ultimo)
    pr30, pr30t = proc / 'pr30_vigente/PR-30_vigente.pdf', proc / 'pr30_vigente/PR-30_vigente.utf8.txt'
    l30, c30 = lineas(pr30t, 'El presente Procedimiento Técnico estará vigente hasta el 31 de diciembre de 2026',
                      'nuevo PR-30, aprobado mediante la Resolución OSINERGMIN N° 95-2026-OS/CD')
    r173 = proc / 'rcd_173_2026/Osinergmin-173-2026-OS-CD.pdf'
    r173t = proc / 'rcd_173_2026/Osinergmin-173-2026-OS-CD.txt'
    l173, c173 = lineas(r173t, 'Artículo 2.- Aprobar el Procedimiento Técnico del COES N° 30',
                        'aprobado con Resolución N° 200-2017-OS/CD.')
    marca = 'práctica observada del COES (serie de 30 min, sha c315beba), no norma'
    return [
        {'acto': 'COES Portal, serie pública de demanda (30 min)',
         'titulo': 'Serie de demanda ejecutada del SEIN del 2025-03-26, portal de información del COES',
         'estado_juridico': 'vigente_comprobada', 'url': 'https://www.coes.org.pe/Portal/portalinformacion/Demanda',
         'fecha_consulta': '2026-11-15', 'sha256': sha(serie), 'fichero_local': serie.as_posix(),
         'nota': ('POST público con fechaInicial=fechaFinal=26/03/2025 (frente i de cc, '
                  'apoyo (cc), frente «i_convencion_datos_coes»). Es práctica observada, no norma.'),
         'reglas': [{'clave': 'coes.sein.convencion_por_defecto', 'valor': {'alineacion': 'fin', 'marca': marca},
                     'articulo_o_anexo': 'Chart.Series «Ejecutado», 48 registros', 'pagina': 'JSON (única)',
                     'cita_literal': f'«{primero}» … «{ultimo}» (48 registros; ninguno a las 00:00 del día)',
                     'interpretacion': ('La serie pública rotula el FIN de su intervalo. Si se muestra una sola '
                                        'alineación del instante del SEIN es [h-15, h), con esta marca; las dos se '
                                        'siguen calculando y si difieren más que la tolerancia hay hueco (28).')}]},
        {'acto': 'PR-30 (RCD 200-2017-OS/CD)', 'titulo': 'Procedimiento Técnico del COES N° 30, vigente',
         'estado_juridico': 'vigente_comprobada',
         'url': ('https://www.coes.org.pe/Portal/browser/download?url=Marco%20Normativo%2FProcedimientos%2FTecnicos%2F'
                 '30%20Valorizaci%C3%B3n%20de%20Transferencias%20de%20Potencia%20y%20Compensaciones%20al%20Sistema'
                 '%20Principal%20y%20Sistema%20Garantizado%20de%20Transmisi%C3%B3n.pdf'),
         'fecha_consulta': '2026-11-15', 'sha256': sha(pr30), 'sha256_texto': sha(pr30t),
         'fichero_local': pr30.as_posix(), 'vigencia_hasta': '2026-12-31',
         'reglas': [{'clave': 'coes.procedimiento.pr30',
                     'valor': {'aprobado_por': 'RCD 200-2017-OS/CD', 'hasta': '2026-12-31'},
                     'articulo_o_anexo': 'Nota de vigencia', 'pagina': pagina_de(pr30, c30), 'lineas': l30,
                     'cita_literal': c30}]},
        {'acto': 'RCD 173-2026-OS/CD',
         'titulo': 'Modifica la entrada en vigencia del PR-10 y del PR-30 aprobados por la RCD 95-2026-OS/CD',
         'estado_juridico': 'vigente_comprobada',
         'url': 'https://www.osinergmin.gob.pe/Resoluciones/pdf/2026/Osinergmin-173-2026-OS-CD.pdf',
         'fecha_consulta': '2026-11-15', 'sha256': sha(r173), 'sha256_texto': sha(r173t),
         'fichero_local': r173.as_posix(), 'vigencia_desde': '2027-01-01',
         'nota': ('Lima, 29 de setiembre de 2026; El Peruano NL/2559474-1 (frente h de cc). La integra el IT '
                  '577-2026-GRT, sin descargar.'),
         'reglas': [{'clave': 'coes.procedimiento.pr30',
                     'valor': {'aprobado_por': 'RCD 95-2026-OS/CD', 'desde': '2027-01-01'},
                     'articulo_o_anexo': 'Artículo 1 (nueva redacción del art. 2 de la RCD 95-2026-OS/CD)',
                     'pagina': pagina_de(r173, c173), 'lineas': l173, 'cita_literal': c173}]}]


def pagina_de(pdf: Path, cita: str) -> str:
    import subprocess
    clave = ' '.join(cita.split()[:8])
    for pag in range(1, 200):
        r = subprocess.run(['pdftotext', '-f', str(pag), '-l', str(pag), '-enc', 'UTF-8', str(pdf), '-'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode:
            break
        if clave in ' '.join(r.stdout.split()):
            return str(pag)
    raise SystemExit(f'{pdf.name}: no se halla «{clave}»')


MEDICION = Path('MEDICION')     # ídem
#: Ficha del SPIJ de la RM 496-2005-MEM/DM y sha256 de su innerText, calculado en la página (cc, z19, RN-VIG2).
SPIJ_496 = ('H905941', '73ee1c5b7b6b0abc1b948a8a4bce1e23cc83fc7c671fffca082da36174e28493')


def registro_medida() -> dict:
    """Error admisible por clase de precisión (RM 496-2005-MEM/DM, Tabla N° 01) y clase por defecto en MT (Guía TUPA
    del INACAL), aprobados por el auditor 28 (2026-11-15) como tolerancia por defecto de las dos alineaciones."""
    rm = MEDICION / 'rm_496_2005'
    pdf, txt = rm / 'rm496-2005.pdf', rm / 'rm496-2005.txt'
    lt, ct = lineas(txt, 'Tabla N° 01: Contador', '3          Imáx              1      ± 0,3 ± 0,7')
    # Las tres condiciones (0,05 In, In e Imáx, cos φ = 1): los dos primeros errores son los de 0,2S y 0,5S estáticos.
    import re
    filas = [ln for ln in txt.read_text(encoding='utf-8').split('\n')[int(lt.split('-')[0]) - 1:int(lt.split('-')[1])]
             if re.match(r'\s*[123]\s{3,}', ln)]
    errores = {tuple(re.findall(r'± (\d+(?:,\d+)?)', ln)[:2]) for ln in filas}
    assert len(filas) == 3 and len(errores) == 1, (filas, errores)
    e02, e05 = (float(x.replace(',', '.')) for x in errores.pop())
    tupa = MEDICION / 'inacal_guia_tupa_2019'
    tpdf, ttxt = tupa / 'Guia_TUPA.pdf', tupa / 'Guia_TUPA.txt'
    lu, cu = lineas(ttxt, 'Medidor Clase 0,2 S y 0,5 S', '(Media Tensión, Alta Tensión y Muy Alta Tensión)')
    return {
        'esquema': 'registro_normativo_v1',
        'nota': ('Generado por tools/normativa/generar_coes.py. Fuentes localizadas por cc (apoyo de f4), '
                 'apoyo (cc), frente «f_clase_precision_mt» ninguna norma peruana abierta asigna la clase por '
                 'nivel de tensión.'),
        'normas': [
            {'acto': 'RM 496-2005-MEM/DM', 'titulo': 'Norma DGE «Contraste del Sistema de Medición de Energía Eléctrica»',
             'estado_juridico': 'modificada', 'url': 'http://www.osinerg.gob.pe/newweb/uploads/Publico/rm496-2005.pdf',
             'fecha_publicacion': '2005-12-14', 'fecha_consulta': '2026-11-15', 'sha256': sha(pdf),
             'sha256_texto': sha(txt), 'fichero_local': pdf.as_posix(),
             'version': f'texto de 2005; ficha del SPIJ {SPIJ_496[0]} (sha256 del innerText {SPIJ_496[1]})',
             'vigencia_desde': '2006-01-01', 'modificada_por': ['RM 102-2010-MEM-DM'],
             'nota': ('Texto de noviembre de 2005, publicado el 14-12-2005. Vigencia comprobada en el SPIJ por cc '
                      '(RN-VIG2, 2026-11-15): su única modificatoria es la RM 102-2010-MEM-DM, que no toca la Tabla N° 01; '
                      'el «(*)» de esa tabla es la nota original sobre los contadores de inducción. Vigencia por SU propia '
                      'cláusula (orden de 28): «Artículo 3º.- La presente Resolución Ministerial entrará en vigencia a '
                      'partir del 1 de enero de 2006.» (El Peruano, pág. 3; copia del apoyo (cc), frente '
                      '«f_clase_precision_mt», PDF sha 41104942, texto sha bdc9f648); no se aplica la regla general del art. '
                      '109 de la Constitución porque la norma fija su propia fecha.'),
             'reglas': [
                 {'clave': 'medida.error_admisible_por_clase', 'valor': {'0.2S': e02, '0.5S': e05}, 'unidad': '%',
                  'articulo_o_anexo': 'Tabla N° 01 «Contador: Error Admisible (%) según la clase de precisión»',
                  'pagina': '7', 'lineas': lt, 'cita_literal': ct,
                  'interpretacion': ('Contadores estáticos, cos φ = 1, igual en 0,05 In, In e Imáx. Es la tolerancia por '
                                     'defecto de las dos alineaciones del instante del SEIN cuando el perfil no da la '
                                     'resolución del medidor (decisión del auditor 28, 2026-11-15).')}]},
            {'acto': 'RM 102-2010-MEM-DM',
             'titulo': 'Modifica la Norma DGE «Contraste del Sistema de Medición de Energía Eléctrica» (RM 496-2005-MEM/DM)',
             'estado_juridico': 'no_verificada', 'fecha_publicacion': '2010-03-05', 'fecha_consulta': '2026-11-15',
             'version': f'conocida por la nota del SPIJ en la ficha {SPIJ_496[0]} de la RM 496-2005-MEM/DM',
             'modifica': ['RM 496-2005-MEM/DM'],
             'nota': ('Modificatoria que NO toca la Tabla 01 (error del contador por clase): su art. 2 cambia el num. '
                      '6.5.3 y su art. 1 precisa un párrafo junto a la Tabla 02 (el párrafo cuarto del literal ii), '
                      'transformadores de corriente). Su texto propio no se ha leído: lo que se sabe de ella es la nota '
                      'del SPIJ en la 496-2005 (RN-VIG2, 2026-11-15); por eso «no_verificada» y sin reglas.')},
            {'acto': 'INACAL Guía TUPA de Metrología Legal',
             'titulo': 'Guía para la atención de los procedimientos TUPA de metrología legal (INACAL)',
             'estado_juridico': 'vigente_comprobada', 'url': 'https://cdn.www.gob.pe/uploads/document/file/1119004/Guia_TUPA.pdf',
             'fecha_consulta': '2026-11-15', 'sha256': sha(tpdf), 'sha256_texto': sha(ttxt),
             'fichero_local': tpdf.as_posix(),
             'nota': 'Guía de homologación, no una obligación: se usa como práctica para la clase por defecto en MT.',
             'reglas': [
                 {'clave': 'medida.clase_por_defecto_mt', 'valor': '0.5S',
                  'articulo_o_anexo': 'Tabla de ítems de la NMP, columna de medidores de media tensión', 'pagina': '4',
                  'lineas': lu, 'cita_literal': cu,
                  'interpretacion': ('La guía asocia las clases 0,2S y 0,5S a la MT, la AT y la MAT. Sin la clase en el '
                                     'perfil se toma 0,5S, la de mayor error admisible (decisión del auditor 28).')}]}]}


# Auditoría D.2 (2026-11-24): una sola copia, en tools/normativa/fuentes.py.
def _argumentos(descripcion: str):
    from fuentes import argumentos_de_generador
    return argumentos_de_generador(descripcion)


if __name__ == '__main__':
    a = _argumentos('Registro de datos del COES (máxima demanda del SEIN), horas punta y clase de precisión de la medida, desde las fuentes oficiales descargadas.')
    main(a.destino, a.fuentes)
