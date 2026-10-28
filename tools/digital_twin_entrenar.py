#!/usr/bin/env python
"""Entrena el oráculo PINN/GNN del gemelo digital en su propio proceso (spec 024, T11).

La web lo lanza tras el aprendizaje activo: si el entrenamiento se queda sin memoria o
el driver de la GPU falla, cae este proceso y no la web (IN111–TA225, 2026-10-22: la web
se cayó entrenando dentro de su proceso). Reentrena solo si toca (RF-39) o, con
``--forzar``, siempre; promueve si pasa las puertas (RF-16, RF-42).

    python tools/digital_twin_entrenar.py --output-json entrenamiento.json [--raiz carpeta]

Con ``--evaluar`` no entrena: dice cuánto se apartan de DIgSILENT el modelo promovido y la
física sola en cada episodio, con la media de entrenamiento, validación y prueba (RF-74).
Con ``--reproducir VERSION`` vuelve a entrenar ese modelo con su manifiesto y dice si su error
difiere menos de 10⁻⁵ p.u. (spec 027, RF-9). Con ``--deriva`` no entrena: dice por familia los
episodios nuevos y fuera de dominio y si conviene reentrenar (spec 027, RF-22 y RF-23). Con ``--buscar`` busca antes los hiperparámetros
(TPE y poda, solo en validación, con ``--ensayos`` y ``--limite-s``), guarda los ensayos y entrena
con los elegidos (spec 027, RF-7).

Códigos de salida: 0 hecho (entrenado o no hacía falta), 2 sin PyTorch, 1 error.
"""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path


def _log(mensaje: str) -> None:
    """El avance a quien escuche; si la web que lo lanzó ya no está, se entrena igual.

    2026-10-24: con la web parada a mitad, el primer ``print`` dio «OSError 22» en la salida
    rota y el entrenamiento se perdió aunque la GPU seguía libre.
    """
    try:
        print(mensaje, flush=True)
    except OSError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Entrena el oráculo PINN/GNN del gemelo digital en su '
                                            'propio proceso (spec 024)')
    p.add_argument('--output-json', required=True)
    p.add_argument('--raiz', type=Path, help='Búfer del gemelo (por defecto, el de la web)')
    p.add_argument('--forzar', action='store_true', help='Entrenar aunque no haya episodios nuevos')
    p.add_argument('--minimo', type=int, default=10, help='Episodios nuevos para reentrenar')
    p.add_argument('--evaluar', action='store_true',
                   help='No entrenar: comparar el modelo promovido y la física con DIgSILENT')
    p.add_argument('--buscar', action='store_true',
                   help='Buscar hiperparámetros (Optuna, solo en validación) y entrenar con ellos (027:RF-7)')
    p.add_argument('--ensayos', type=int, default=20, help='Ensayos de la búsqueda')
    p.add_argument('--limite-s', type=float, default=1800.0, help='Segundos de la búsqueda')
    p.add_argument('--deriva', action='store_true',
                   help='No entrenar: deriva por familia y si conviene reentrenar (027:RF-22, RF-23)')
    p.add_argument('--reproducir', metavar='VERSION',
                   help='Reentrenar un modelo con su manifiesto y comparar su error (027:RF-9)')
    args = p.parse_args(argv)
    salida = Path(args.output_json)

    from igea_dgs.digital_twin.buffer import BuferEpisodios

    try:
        from igea_dgs.digital_twin import oraculo
        oraculo.dispositivo()
    except ImportError as exc:
        salida.write_text(json.dumps({'entrenado': False, 'motivo': str(exc)}, ensure_ascii=False),
                          encoding='utf-8')
        print(f'ERROR: {exc}')
        return 2
    bufer = BuferEpisodios(args.raiz)
    if not (args.evaluar or args.deriva):
        # 026: la GPU de 8 GB la comparte con Ollama, que retiene su modelo tras responder.
        from igea_dgs.asistente.ollama import liberar_gpu_para_entrenar

        liberar_gpu_para_entrenar()
    try:
        if args.deriva:
            r = oraculo.deriva_por_familia(bufer)
            for m in r['motivos'] or ['sin deriva: no hace falta reentrenar']:
                print(m)
            salida.write_text(json.dumps(r, ensure_ascii=False, default=str), encoding='utf-8')
            return 0
        if args.reproducir:
            r = oraculo.reproducir(bufer, args.reproducir, log=_log)
            print(f"{r['version']}: original {r['mae_original']}, reproducido {r['mae_reproducido']}, "
                  f"diferencia {r['diferencia']:.2e} ({'reproducible' if r['reproducible'] else 'NO reproducible'})")
            salida.write_text(json.dumps(r, ensure_ascii=False, default=str), encoding='utf-8')
            return 0 if r['reproducible'] else 1
        if args.evaluar:
            r = oraculo.evaluar(bufer)
            for parte, d in r['por_particion'].items():
                modelo = f", modelo {d['mae_modelo']:.5f}" if 'mae_modelo' in d else ''
                print(f"{parte}: {d['episodios']} episodio(s), física {d['mae_fisica']:.5f} p.u.{modelo}")
            salida.write_text(json.dumps(r, ensure_ascii=False, default=str), encoding='utf-8')
            return 0
        if args.buscar:
            from igea_dgs.digital_twin.buffer import Consulta
            from igea_dgs.digital_twin.hiperparametros import buscar

            muestras, _ids = oraculo._muestras(bufer, Consulta())
            b = buscar(muestras, ensayos=args.ensayos, limite_s=args.limite_s,
                       destino=bufer.raiz / 'modelos' / 'busquedas', log=_log)
            _log(f"Búsqueda: mejor ensayo {b['mejor']['numero']} con {b['mejor']['mae_validacion']:.3e} p.u. "
                 f"en validación; ensayos en {b.get('ruta')}")
            r = {**oraculo.entrenar(bufer, cfg=oraculo.Entrenamiento(**b['cfg']), log=_log), 'busqueda': b}
        elif args.forzar:
            r = oraculo.entrenar(bufer, log=_log)
        else:
            r = oraculo.entrenar_si_toca(bufer, minimo=args.minimo, log=_log)
        codigo = 0
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito
        r, codigo = {'entrenado': False, 'error': repr(exc), 'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(r, ensure_ascii=False, default=str), encoding='utf-8')
    _log(f"Entrenamiento: {r.get('motivo') or ('promovido' if r.get('promovido') else r.get('fallos') or r.get('error'))}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
