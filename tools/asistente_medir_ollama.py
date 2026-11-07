#!/usr/bin/env python
"""Mide los modelos locales de Ollama como intérpretes de órdenes y elige uno (spec 026, T4, RF-3).

Las mismas órdenes (sintéticas, con la semilla de la prueba fija) a cada modelo: acierto de
tarea, segundos por orden y cuántas no respondieron. Se elige el que más acierta entre los
que responden en menos del tiempo máximo, y queda guardado para la web (``ollama.json`` del
asistente). Todo es local: Ollama tiene que estar en esta máquina (P9).

    python tools/asistente_medir_ollama.py --output-json medida.json \\
        [--modelos qwen2.5:3b llama3.1:8b] [--por-tarea 3] [--tiempo-max 30]

Códigos de salida: 0 hecho, 2 Ollama no responde, 1 error.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Mide los modelos locales de Ollama como intérpretes de órdenes '
                                            '(spec 026)')
    p.add_argument('--output-json', required=True)
    p.add_argument('--modelos', nargs='+', default=['qwen2.5:3b', 'llama3.1:8b'])
    p.add_argument('--por-tarea', type=int, default=3, help='Órdenes por tarea')
    p.add_argument('--tiempo-max', type=float, default=30.0, help='Segundos máximos por orden')
    args = p.parse_args(argv)

    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.asistente.ollama import ClienteOllama
    from convertersmartgrid.asistente.sinteticos import generar
    from convertersmartgrid.asistente.transformer import SEMILLA_PRUEBA

    salida = Path(args.output_json)
    instalados = ClienteOllama(modelo=args.modelos[0]).modelos()
    if instalados is None:
        salida.write_text(json.dumps({'error': 'Ollama no responde en esta máquina'}, ensure_ascii=False),
                          encoding='utf-8')
        print('ERROR: Ollama no responde en esta máquina.')
        return 2
    ordenes = generar(almacen.leer_json('vocabulario') or {}, por_tarea=args.por_tarea, semilla=SEMILLA_PRUEBA,
                      ruido=0.1)
    medidas = {}
    for modelo in args.modelos:
        if not any(i == modelo or i.startswith(modelo + ':') for i in instalados):
            medidas[modelo] = {'instalado': False}
            continue
        # El intérprete pide JSON corto: sin razonamiento previo. qwen3:8b razonaba antes de cada orden y el 2026-11-07
        # dejó 48 de 144 sin respuesta, con 11 s de mediana: se medía el razonamiento, no el intérprete.
        cliente = ClienteOllama(modelo=modelo, tiempo_max_s=args.tiempo_max, pensar=False)
        aciertos, tiempos, sin_respuesta = 0, [], 0
        for e in ordenes:
            inicio = time.monotonic()
            r = cliente.interpretar(e.texto)
            tiempos.append(time.monotonic() - inicio)
            if r is None:
                sin_respuesta += 1
            elif r.get('tarea') == e.tarea:
                aciertos += 1
        medidas[modelo] = {'instalado': True, 'acierto': aciertos / len(ordenes), 'ordenes': len(ordenes),
                           'segundos_mediana': statistics.median(tiempos), 'segundos_max': max(tiempos),
                           'sin_respuesta': sin_respuesta}
        print(f"{modelo}: acierto {medidas[modelo]['acierto']:.0%}, mediana "
              f"{medidas[modelo]['segundos_mediana']:.1f} s, {sin_respuesta} sin respuesta", flush=True)
    validos = {m: d for m, d in medidas.items() if d.get('instalado') and d['segundos_mediana'] <= args.tiempo_max}
    elegido = max(validos, key=lambda m: (validos[m]['acierto'], -validos[m]['segundos_mediana'])) if validos else None
    resultado = {'elegido': elegido, 'medidas': medidas, 'tiempo_max_s': args.tiempo_max}
    if elegido:
        # Con lo que se midió: sin razonar, como lo usa la web.
        almacen.guardar_json('ollama', {'modelo': elegido, 'pensar': False, 'medidas': medidas, 'fecha': almacen.ahora()})
    salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Elegido: {elegido or "ninguno"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
