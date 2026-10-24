#!/usr/bin/env python
"""Entrena el oráculo PINN/GNN del gemelo digital en su propio proceso (spec 024, T11).

La web lo lanza tras el aprendizaje activo: si el entrenamiento se queda sin memoria o
el driver de la GPU falla, cae este proceso y no la web (IN111–TA225, 2026-10-22: la web
se cayó entrenando dentro de su proceso). Reentrena solo si toca (RF-39) o, con
``--forzar``, siempre; promueve si pasa las puertas (RF-16, RF-42).

    python tools/digital_twin_entrenar.py --output-json entrenamiento.json [--raiz carpeta]

Con ``--evaluar`` no entrena: dice cuánto se apartan de DIgSILENT el modelo promovido y la
física sola en cada episodio, con la media de entrenamiento, validación y prueba (RF-74).

Códigos de salida: 0 hecho (entrenado o no hacía falta), 2 sin PyTorch, 1 error.
"""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Entrena el oráculo PINN/GNN del gemelo digital en su '
                                            'propio proceso (spec 024)')
    p.add_argument('--output-json', required=True)
    p.add_argument('--raiz', type=Path, help='Búfer del gemelo (por defecto, el de la web)')
    p.add_argument('--forzar', action='store_true', help='Entrenar aunque no haya episodios nuevos')
    p.add_argument('--minimo', type=int, default=10, help='Episodios nuevos para reentrenar')
    p.add_argument('--evaluar', action='store_true',
                   help='No entrenar: comparar el modelo promovido y la física con DIgSILENT')
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
    try:
        if args.evaluar:
            r = oraculo.evaluar(bufer)
            for parte, d in r['por_particion'].items():
                modelo = f", modelo {d['mae_modelo']:.5f}" if 'mae_modelo' in d else ''
                print(f"{parte}: {d['episodios']} episodio(s), física {d['mae_fisica']:.5f} p.u.{modelo}")
            salida.write_text(json.dumps(r, ensure_ascii=False, default=str), encoding='utf-8')
            return 0
        if args.forzar:
            r = oraculo.entrenar(bufer, log=lambda m: print(m, flush=True))
        else:
            r = oraculo.entrenar_si_toca(bufer, minimo=args.minimo, log=lambda m: print(m, flush=True))
        codigo = 0
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito
        r, codigo = {'entrenado': False, 'error': repr(exc), 'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(r, ensure_ascii=False, default=str), encoding='utf-8')
    print(f"Entrenamiento: {r.get('motivo') or ('promovido' if r.get('promovido') else r.get('fallos') or r.get('error'))}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
