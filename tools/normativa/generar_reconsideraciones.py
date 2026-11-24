"""Delta13 (107 T27): la causa del cambio de los factores de expansión de pérdidas entre la fijación (IT 716-2023) y
las reconsideraciones (RCD 223-2023), empresa por empresa, desde los informes técnicos de cada reconsideración.

Escribe config/normativa/vad_2023_2027_reconsideraciones.json (esquema registro_normativo_v1). Nada se teclea: cada cita
literal y su página se leen del texto y del PDF de cada informe (pdftotext página a página). Las fuentes las localizó
cc (apoyo (cc), frente «c_reconsideraciones_216_217_218» y j_reconsideraciones_restantes) y están copiadas en
<fuentes>/PIT_NORMA/vad_2023_2027_perdidas/informes_reconsideracion.

Uso: python -I -X utf8 tools/normativa/generar_reconsideraciones.py --fuentes <carpeta de fuentes> --destino <repo>
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SUBCARPETA = Path('PIT_NORMA/vad_2023_2027_perdidas/informes_reconsideracion')
BASE = SUBCARPETA                # lo fija main() desde --fuentes
URL = 'https://www.osinergmin.gob.pe/Resoluciones/pdf/2023/Informe-Tecnico-{n}-2023-GRT.pdf'
#: Qué reconsideración es de qué empresa, su RCD, su informe, su carpeta en las fuentes y lo que se lee de él: datos,
#: no código (FIX-PUNTA, orden del auditor c3), en la entrada versionada junto al registro que se genera.
ENTRADA = Path('config/normativa/entradas/vad_2023_2027_reconsideraciones.entrada.json')
COMPONENTES = ['aisladores_mt', 'cable_enlace_bt_transformador_tablero', 'circuito_amperimetrico_medidores']


def leer_entrada(destino: str) -> dict:
    """La entrada del guion: ``con_causa`` (los informes que aceptan los tres componentes de pérdidas técnicas, con los
    trozos o las líneas que lo citan; frente c de cc), ``sin_causa`` (los que no aceptan nada de pérdidas técnicas, con
    lo leído; frente j de cc) y ``nota_registro``."""
    ruta = Path(destino) / ENTRADA
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SystemExit(f'no se puede leer la entrada {ruta}: {exc}') from None
    for lista, claves in (('con_causa', ('empresa', 'rcd', 'informe', 'carpeta', 'trozos')),
                          ('sin_causa', ('empresa', 'rcd', 'informe', 'carpeta', 'leido'))):
        for i, e in enumerate(datos.get(lista) or ()):
            falta = [k for k in claves if e.get(k) in (None, '', [])]
            if falta:
                raise SystemExit(f'{ruta.name}: {lista}[{i}] sin {falta}')
    if not datos.get('con_causa') or not datos.get('sin_causa') or not datos.get('nota_registro'):
        raise SystemExit(f'{ruta.name}: faltan con_causa, sin_causa o nota_registro')
    return datos


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pagina_de(pdf: Path, trozo: str) -> str:
    n = int(next(ln.split()[-1] for ln in subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True,
                                                         encoding='utf-8', errors='replace').stdout.splitlines()
                 if ln.startswith('Pages:')))
    clave = ' '.join(trozo.split()[:6])
    for p in range(1, n + 1):
        t = subprocess.run(['pdftotext', '-f', str(p), '-l', str(p), '-enc', 'UTF-8', str(pdf), '-'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        if clave in ' '.join(t.split()):
            return str(p)
    raise SystemExit(f'{pdf.name}: no se halla «{clave}» en ninguna página')


def linea(txt: Path, trozo) -> tuple[int, str]:
    """La línea (1-based) donde empieza el trozo (o la línea dada, comprobada con «acepta»), y su texto literal con la
    línea siguiente, porque las frases del PDF se cortan en dos."""
    L = txt.read_text(encoding='utf-8').split('\n')
    if isinstance(trozo, int):
        i = trozo - 1
        assert 'acepta' in L[i], (txt.name, trozo, L[i])
    else:
        i = next(i for i, x in enumerate(L) if trozo in x)
    return i + 1, ' '.join(' '.join(L[i:i + 2]).split())


def ficheros(carpeta: str) -> tuple[Path, Path]:
    """El PDF del informe y su texto (no el .fuente.txt)."""
    d = BASE / carpeta
    pdf = next(d.glob('*.pdf'))
    return pdf, d / f'{pdf.stem}.txt'


def norma(n: str, carpeta: str, empresa: str, rcd: str, reglas: list[dict]) -> dict:
    d = BASE / carpeta
    pdf, txt = ficheros(carpeta)
    fuente = (d / f'{pdf.name}.fuente.txt').read_text(encoding='utf-8')
    assert sha(pdf) in fuente, pdf
    consulta = next(x.split(':', 1)[1].strip()[:10] for x in fuente.splitlines() if x.startswith('Fecha de consulta'))
    return {'acto': f'IT {n}-2023-GRT', 'titulo': f'Informe técnico del recurso de reconsideración de {empresa} '
                                                  f'contra la RCD 187-2023-OS/CD (resuelto por la RCD {rcd}-2023-OS/CD)',
            'estado_juridico': 'vigente_comprobada', 'url': URL.format(n=n), 'fecha_consulta': consulta,
            'sha256': sha(pdf), 'sha256_texto': sha(txt), 'fichero_local': pdf.as_posix(), 'reglas': reglas}


def main(destino: str, fuentes: str) -> None:
    global BASE
    BASE = Path(fuentes) / SUBCARPETA
    entrada = leer_entrada(destino)
    normas = []
    for e in entrada['con_causa']:
        empresa, rcd, n, carpeta, trozos = e['empresa'], e['rcd'], e['informe'], e['carpeta'], e['trozos']
        pdf, txt = ficheros(carpeta)
        lns = [linea(txt, t) for t in trozos]
        normas.append(norma(n, carpeta, empresa, rcd, [{
            'clave': f'vad.perdidas.causa_del_cambio.{empresa}',
            'valor': {'resolucion': f'RCD {rcd}-2023-OS/CD', 'componentes': COMPONENTES, 'veredicto': 'fundado en parte'},
            'articulo_o_anexo': 'Análisis de las pérdidas técnicas de MT y BT',
            'pagina': ', '.join(sorted({pagina_de(pdf, t) for _, t in lns}, key=int)),
            'lineas': ', '.join(str(i) for i, _ in lns), 'cita_literal': ' · '.join(t for _, t in lns),
            'interpretacion': ('Causa citada del cambio de sus FE entre el IT 716 y la RCD 223-2023: se incorporaron las '
                               'pérdidas en aisladores de MT, el cable de enlace BT transformador-tablero y el circuito '
                               'amperimétrico de los medidores. El informe no trae la tabla final de FE: los vigentes '
                               'son los de la 223-2023, art. 4.')}]))
    for e in entrada['sin_causa']:
        empresa, rcd, n, carpeta, leido = e['empresa'], e['rcd'], e['informe'], e['carpeta'], e['leido']
        pdf, txt = ficheros(carpeta)
        i, cita = linea(txt, 'Reconsideración interpuesto')
        normas.append(norma(n, carpeta, empresa, rcd, [{
            'clave': f'vad.perdidas.sin_causa_localizada.{empresa}',
            'valor': {'resolucion': f'RCD {rcd}-2023-OS/CD', 'acepta_perdidas_tecnicas': False, 'leido': leido},
            'articulo_o_anexo': 'Portada y objeto del informe', 'pagina': pagina_de(pdf, cita), 'lineas': str(i),
            'cita_literal': cita,
            'interpretacion': ('Sus FE cambian entre el IT 716 y la RCD 223-2023, pero su informe no acepta nada de '
                               'pérdidas técnicas: la causa NO está localizada y no se supone. La RCD 223-2023-OS/CD '
                               'remite el detalle al IT 819-2023-GRT, que solo tabula los FE finales '
                               '(nota j de cc).')}]))
    out = {'esquema': 'registro_normativo_v1',
           'nota': entrada['nota_registro'],
           'normas': normas}
    salida = Path(destino) / 'config/normativa/vad_2023_2027_reconsideraciones.json'
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fuentes import sin_rutas
    # El registro va al repositorio: sin rutas de la máquina (delta19, orden de 28).
    salida.write_text(json.dumps(sin_rutas(out, BASE.parents[2]), ensure_ascii=False, indent=1) + '\n',
                      encoding='utf-8', newline='\n')
    print(salida, sha(salida)[:16])


# Auditoría D.2 (2026-11-24): una sola copia, en tools/normativa/fuentes.py.
def _argumentos(descripcion: str):
    sys.path.insert(0, str(Path(__file__).resolve().parent))   # se lanza con -I: su carpeta no está en sys.path
    from fuentes import argumentos_de_generador
    return argumentos_de_generador(descripcion)


if __name__ == '__main__':
    a = _argumentos('Causa del cambio de los factores de expansión de pérdidas del VAD 2023-2027, por empresa, desde los informes técnicos de las reconsideraciones.')
    main(a.destino, a.fuentes)
