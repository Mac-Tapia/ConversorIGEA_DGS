"""Audita el dataset de los modelos del agente antes de entrenar (spec 027, T0, RF-29 a RF-34).

Gemelo (episodios del búfer): muestras, redes distintas, nodos, columnas, fracción
etiquetada, rangos, valores no finitos, tensiones fuera de rango, ramas en el tope de
acoplador y parámetros frente a etiquetas. Asistente: órdenes reales y si sus puertas se
pueden medir con órdenes reales. Solo lee; no necesita GPU ni DIgSILENT.

    .venv/Scripts/python.exe tools/digital_twin_auditar.py --output-json auditoria.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='Audita el dataset de los modelos del agente antes de entrenar '
                                            '(spec 027, T0)')
    p.add_argument('--raiz', type=Path, help='Carpeta del búfer de episodios (por defecto, la de la web)')
    p.add_argument('--output-json', type=Path, help='Dónde guardar el informe')
    args = p.parse_args(argv)

    from igea_dgs.asistente import almacen
    from igea_dgs.digital_twin import oraculo
    from igea_dgs.digital_twin.auditoria import auditar_muestras, auditar_ordenes
    from igea_dgs.digital_twin.buffer import BuferEpisodios, Consulta, raiz_buffer

    bufer = BuferEpisodios(args.raiz or raiz_buffer())
    muestras, ids = oraculo._muestras(bufer, Consulta())
    actual = oraculo.cargar(bufer)
    cfg = actual.cfg if actual else oraculo.Entrenamiento()
    gemelo = auditar_muestras(muestras, ids, parametros=oraculo.MIEMBROS * oraculo._parametros(cfg))
    reales = almacen.leer('ejemplos')
    # La prueba fija del asistente: una de cada cinco órdenes reales (026:RF-19).
    asistente = auditar_ordenes(reales=len(reales), sinteticas=0,
                                prueba_real=sum(1 for i in range(len(reales)) if i % 5 == 4))
    informe = {'gemelo': gemelo, 'asistente': asistente}
    for nombre, parte in informe.items():
        print(f'{nombre}:')
        for k in ('apto', 'muestras', 'redes', 'nodos', 'columnas_x', 'etiquetas', 'parametros',
                  'reales', 'prueba_real', 'puertas_con_reales'):
            if k in parte:
                print(f'  {k}: {parte[k]}')
        for aviso in parte['avisos']:
            print(f'  aviso: {aviso}')
    if args.output_json:
        args.output_json.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if gemelo.get('apto') or not muestras else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
