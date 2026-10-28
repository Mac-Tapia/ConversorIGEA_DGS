#!/usr/bin/env python
"""Entrena el Transformer de órdenes y el clasificador de informes del asistente (spec 026, T3 y T7).

En su propio proceso, como la PINN: si la GPU falla, cae este proceso y no la web. Cada
modelo se promueve solo si pasa sus puertas en un conjunto de prueba fijo y no acierta
menos que el que está en uso (RF-20); el anterior queda para volver a él.

    python tools/asistente_entrenar.py --output-json entrenamiento.json [--vocabulario vocab.json]
    python tools/asistente_entrenar.py --output-json evaluacion.json --evaluar
    python tools/asistente_entrenar.py --output-json entrenamiento.json --destilar

``--destilar`` (spec 027, RF-56 a RF-62): el modelo local de Ollama interpreta k veces las
órdenes que el operador no confirmó y el Transformer aprende de sus votos; se usa solo si
acierta al menos lo mismo que sin destilar.

``--vocabulario`` es un JSON ``{"alimentadores": [...], "proyecto": [...], "sistema": [...]}``
con los nombres reales del espacio; sin él se usan los que guardó la web la última vez.

Códigos de salida: 0 hecho, 2 sin PyTorch o sin GPU, 1 error.
"""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path


def _log(mensaje: str) -> None:
    """El avance a quien escuche; si la web que lo lanzó ya no está, se entrena igual
    (con la salida rota, ``print`` daba «OSError 22» y se perdía el entrenamiento)."""
    try:
        print(mensaje, flush=True)
    except OSError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Entrena el Transformer de órdenes y el clasificador de informes '
                                            'del asistente (spec 026)')
    p.add_argument('--output-json', required=True)
    p.add_argument('--vocabulario', type=Path, help='Nombres reales del espacio (JSON)')
    p.add_argument('--solo', choices=('ordenes', 'informes'), help='Entrenar solo uno de los dos modelos')
    p.add_argument('--destilar', action='store_true',
                   help='Destilar del modelo local de Ollama (maestro) al Transformer (spec 027, RF-56)')
    p.add_argument('--maestro', choices=('claude', 'codex', 'ollama'), default='claude',
                   help='Maestro de la destilación: las etiquetas de Claude, Codex o Ollama (027:RF-56)')
    p.add_argument('--modelo-codex', help='Modelo de Codex como maestro (por defecto, el de su configuración)')
    p.add_argument('--evaluar', action='store_true', help='No entrenar: medir los modelos en uso con la prueba fija')
    args = p.parse_args(argv)
    salida = Path(args.output_json)

    try:
        from igea_dgs.asistente import almacen, clasificador, transformer
        from igea_dgs.digital_twin.oraculo import dispositivo

        dispositivo()
    except (ImportError, RuntimeError) as exc:
        salida.write_text(json.dumps({'entrenado': False, 'motivo': str(exc)}, ensure_ascii=False), encoding='utf-8')
        print(f'ERROR: {exc}')
        return 2
    if args.vocabulario:
        vocab = json.loads(args.vocabulario.read_text(encoding='utf-8'))
    else:
        vocab = almacen.leer_json('vocabulario') or {}
    out: dict = {}
    try:
        if args.evaluar:
            from igea_dgs.asistente.sinteticos import generar

            m = transformer.cargar()
            prueba = generar(vocab, por_tarea=20, semilla=transformer.SEMILLA_PRUEBA) + transformer.ejemplos_reales()[1]
            out['ordenes'] = transformer.evaluar(m, prueba) if m is not None else None
            c = clasificador.cargar()
            if c is not None:
                prueba_c = clasificador.generar(c.subtipos, por_subtipo=25, semilla=clasificador.SEMILLA_PRUEBA)
                out['informes'] = clasificador.evaluar(c, prueba_c)
            print(json.dumps(out, ensure_ascii=False))
        else:
            if args.solo in (None, 'ordenes'):
                kw = {}
                if args.destilar:
                    from igea_dgs.asistente.destilacion import Destilacion
                    from igea_dgs.asistente.ollama import cliente_configurado

                    from igea_dgs.asistente.destilacion import MaestroArchivo, MaestroCodex

                    maestro = {'claude': lambda: MaestroArchivo(), 'codex': lambda: MaestroCodex(vocab, modelo=args.modelo_codex),
                               'ollama': lambda: cliente_configurado(tiempo_max_s=60.0)}[args.maestro]()
                    # Codex fuera de la máquina: menos votos, cada uno es una llamada (RF-63).
                    kw = {'destilar': Destilacion(k=3 if args.maestro == 'codex' else 5), 'maestro': maestro}
                out['ordenes'] = transformer.entrenar_y_promover(vocab, log=_log, **kw)
            if args.solo in (None, 'informes'):
                out['informes'] = clasificador.entrenar_y_promover(log=_log)
        codigo = 0
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito
        out, codigo = {'error': repr(exc), 'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(out, ensure_ascii=False, default=str), encoding='utf-8')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
