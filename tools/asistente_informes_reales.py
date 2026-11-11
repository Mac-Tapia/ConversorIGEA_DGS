"""Registra informes reales etiquetados para el clasificador de informes (spec 026, RF-34).

Uso: python tools/asistente_informes_reales.py --manifiesto etiquetas.json [--origen maestro] [--simular]

El manifiesto es una lista de ``{"ruta" o "texto", "tipo", "subtipo", "grupo"}``; ``texto`` es un informe que redacta el
maestro para un subtipo sin informes reales (refuerzo de red y transferencia no tenían ninguno el 2026-11-11).
Lee el texto de cada documento (Word, o PDF con OCR en las páginas sin texto), no repite uno ya anotado (por su texto)
y lo anota con su grupo (026:RF-33).
El 2026-11-11 el clasificador tenía 9 informes reales y una prueba de 2: un fallo bastaba para rechazar un candidato.
Los documentos son de la distribuidora: se leen donde están y su texto queda en el almacén local, fuera de git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from convertersmartgrid.asistente import almacen, clasificador
from convertersmartgrid.contratos_aprendizaje import TIPOS_INFORME


def texto_de(ruta: Path) -> str:
    if ruta.suffix.lower() == '.docx':
        return clasificador.texto_de_docx(ruta)
    if ruta.suffix.lower() == '.pdf':
        from convertersmartgrid.documentos_solicitud import texto_pdf
        return texto_pdf(ruta)[0]
    raise ValueError(f'{ruta.name}: solo se leen .docx y .pdf')


def _huella(texto: str) -> str:
    # Los primeros anotados guardan tabuladores y saltos tal cual: se compara el texto con los blancos unificados.
    # Y solo el comienzo: lo guardado está recortado antes de unificar, y el resto no distingue un informe de otro.
    return hashlib.sha256(' '.join(texto.split())[:400].encode('utf-8')).hexdigest()


def registrar_manifiesto(filas: list[dict], origen: str, *, simular: bool = False) -> dict:
    """026:RF-34: cada documento una vez, con su tipo, subtipo y grupo; lo que no se pudo leer se dice."""
    ya = {_huella(f.get('texto', '')) for f in almacen.leer('informes')}
    hechos, repetidos, errores = [], [], []
    for f in filas:
        ruta = Path(f.get('ruta') or f"{f.get('grupo', 'sin_grupo')}.texto")
        if f.get('tipo') not in TIPOS_INFORME or not f.get('subtipo') or not f.get('grupo'):
            errores.append(f'{ruta.name}: falta tipo válido, subtipo o grupo')
            continue
        try:
            texto = ' '.join((f['texto'] if f.get('texto') else texto_de(ruta)).split())
        except (OSError, ValueError) as exc:
            errores.append(f'{ruta.name}: {exc}')
            continue
        if not texto:
            errores.append(f'{ruta.name}: sin texto legible')
            continue
        huella = _huella(texto)
        if huella in ya:
            repetidos.append(ruta.name)
            continue
        ya.add(huella)
        if not simular:
            clasificador.registrar(texto, f['tipo'], f['subtipo'], origen, grupo=f['grupo'])
        hechos.append(ruta.name)
    return {'anotados': hechos, 'repetidos': repetidos, 'errores': errores}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--manifiesto', required=True, help='JSON con ruta, tipo, subtipo y grupo de cada informe')
    p.add_argument('--origen', default='maestro', help='Quién etiquetó: maestro, operador… (085:RF-25)')
    p.add_argument('--simular', action='store_true', help='Lee y cuenta sin anotar nada')
    args = p.parse_args(argv)
    filas = json.loads(Path(args.manifiesto).read_text(encoding='utf-8'))
    resultado = registrar_manifiesto(filas, args.origen, simular=args.simular)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 1 if resultado['errores'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
