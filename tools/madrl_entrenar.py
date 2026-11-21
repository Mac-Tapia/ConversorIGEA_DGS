#!/usr/bin/env python
"""Entrena el control MaskablePPO del piloto MADRL sobre un grafo y lo mide contra sus referencias (spec 074).

No escribe en DIgSILENT ni promueve nada: deja un JSON para la puerta. Sus dependencias van aparte del
``.venv`` compartido (``requirements-madrl.txt``). La GPU va por su turno; ``cpu`` existe solo para comprobar
el montaje con pocos pasos, porque un resultado así no es una medida del piloto.

Con ``--politica gatv2 --modelo-salida <carpeta>`` deja los pesos y su manifiesto para ``tools/madrl_puerta.py``.

Uso:
    python tools/madrl_entrenar.py --grafo <json> --tension-min 0.95 --tension-max 1.05 --carga-max 100 \
        --banco-mvar 0.3 --costo-banco 1 --pasos 20000 --dispositivo cuda --salida <json>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
if str(Path(__file__).resolve().parent) not in sys.path:  # ``_plural``, también cargado suelto (086:RF-110)
    sys.path.append(str(Path(__file__).resolve().parent))
from _plural import cuenta  # noqa: E402


def _entorno_gym(plano):
    import gymnasium as gym
    import numpy as np

    class Adaptador(gym.Env):
        def __init__(self) -> None:
            self.action_space = gym.spaces.Discrete(plano.n_acciones)
            self.observation_space = gym.spaces.Box(-np.inf, np.inf, (plano.tam_observacion,), dtype=np.float32)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            return plano.reiniciar(), {}

        def step(self, action):
            obs, recompensa, fin = plano.paso(int(action))
            return obs, float(recompensa), fin, False, {}

        def action_masks(self):
            return plano.mascara()

    return Adaptador()


def guardar_modelo(carpeta: Path, politica, parametros, redes, **extra) -> dict:
    """Los pesos de la política y con qué redes, límites y costos se entrenó: lo que la puerta necesita (074:RF-13)."""
    import torch

    from convertersmartgrid.adaptadores.madrl_puerta import (
        huella_fichero,
        manifiesto_modelo,
        red_declarada,
    )

    carpeta.mkdir(parents=True, exist_ok=True)
    pesos = carpeta / 'politica.pt'
    torch.save({k: v.detach().cpu() for k, v in politica.state_dict().items()}, pesos)
    manifiesto = manifiesto_modelo(politica='gatv2', ocultas=politica.g1.out_channels, cabezas=politica.g1.heads,
                                   parametros=parametros, entrenamiento=[red_declarada(n, g) for n, g in redes],
                                   huella_pesos=huella_fichero(pesos), **extra)
    (carpeta / 'modelo.json').write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifiesto


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Entrena MaskablePPO en el entorno del piloto MADRL y lo compara (spec 074).')
    p.add_argument('--grafo', type=Path, required=True, help='JSON con el grafo del oráculo')
    p.add_argument('--tension-min', type=float, required=True)
    p.add_argument('--tension-max', type=float, required=True)
    p.add_argument('--carga-max', type=float, required=True, help='Cargabilidad máxima en %%')
    p.add_argument('--banco-mvar', type=float, required=True)
    p.add_argument('--costo-banco', type=float, required=True)
    p.add_argument('--costo-terna-km', type=float, help='Sin él, no se ofrecen ternas')
    p.add_argument('--candidatos', type=int, default=8)
    p.add_argument('--max-bancos', type=int, default=3)
    p.add_argument('--politica', choices=('maskable_ppo', 'gatv2'), default='maskable_ppo',
                   help='maskable_ppo: el control; gatv2: la política con atención y crítico central')
    p.add_argument('--iteraciones', type=int, default=40, help='Iteraciones de PPO, con gatv2')
    p.add_argument('--pasos', type=int, default=20000, help='Pasos de entrenamiento, con maskable_ppo')
    p.add_argument('--semilla', type=int, default=1)
    p.add_argument('--dispositivo', choices=('cuda', 'cpu'), required=True, help='cpu: solo para comprobar el montaje')
    p.add_argument('--deps', type=Path, default=Path(os.environ.get('CSG_MADRL_DEPS') or Path.home() / '.convertersmartgrid' / 'madrl_deps'),
                   help='Carpeta de las dependencias del piloto')
    p.add_argument('--salida', type=Path, help='JSON con el resultado')
    p.add_argument('--modelo-salida', type=Path,
                   help='Con gatv2, carpeta donde quedan los pesos y su manifiesto para tools/madrl_puerta.py')
    args = p.parse_args(argv)
    if args.modelo_salida and args.politica != 'gatv2':
        # 074:RF-13: MaskablePPO aprende un espacio de acciones fijo, el de su red: en otra no vale.
        print('ERROR: solo la política gatv2 se guarda para aplicarla en alimentadores no vistos')
        return 2

    from convertersmartgrid.adaptadores.madrl_obras import (
        EntornoObras,
        EntornoPlano,
        ParametrosObras,
        comparar_controles,
        resultado,
        zonas_por_alimentador,
    )

    sys.path.insert(0, str(args.deps))
    if args.politica == 'maskable_ppo':
        try:
            from sb3_contrib import MaskablePPO
        except ImportError as exc:
            print(f'ERROR: faltan las dependencias del piloto en {args.deps} ({exc.name}); vea requirements-madrl.txt')
            return 2
    grafo = json.loads(args.grafo.read_text(encoding='utf-8'))
    zonas = zonas_por_alimentador(grafo)                            # 074:RF-11: un agente por alimentador
    if not zonas:
        print('ERROR: el grafo no tiene ninguna fuente')
        return 2
    parametros = ParametrosObras(args.tension_min, args.tension_max, args.carga_max, args.banco_mvar, args.costo_banco,
                                 args.costo_terna_km, args.candidatos, args.max_bancos)
    plano = EntornoPlano(EntornoObras(grafo, zonas, parametros))

    def entrenar():
        if args.politica == 'gatv2':
            from convertersmartgrid.adaptadores.madrl_politica import Entrenamiento, entrenar_ppo

            return entrenar_ppo(plano, Entrenamiento(iteraciones=args.iteraciones, semilla=args.semilla),
                                dispositivo=args.dispositivo)[0]
        modelo = MaskablePPO('MlpPolicy', _entorno_gym(plano), n_steps=64, batch_size=32, seed=args.semilla,
                             device=args.dispositivo, verbose=0)
        modelo.learn(args.pasos)
        return modelo

    if args.dispositivo == 'cuda':
        from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu

        with turno_gpu('madrl_entrenar'):
            modelo = entrenar()
    else:
        print('Aviso: en cpu solo se comprueba el montaje; esto no es una medida del piloto.')
        modelo = entrenar()
    if args.politica == 'gatv2':
        from convertersmartgrid.adaptadores.madrl_politica import evaluar_politica

        aprendido = evaluar_politica(plano, modelo)
    else:
        obs, fin = plano.reiniciar(), False
        while not fin:
            accion, _ = modelo.predict(obs, action_masks=plano.mascara(), deterministic=True)
            obs, _r, fin = plano.paso(int(accion))
        aprendido = resultado(plano.e, 'maskable_ppo', args.pasos)
    salida = {**comparar_controles(grafo, zonas, parametros), args.politica: aprendido,
              'multiplicadores': plano.e.lagrange.multiplicadores, 'dispositivo': args.dispositivo}
    for clave in ('escalera', 'nsga2', args.politica):
        c = salida[clave]
        print(f"{clave}: en norma {c['en_norma']}, costo {c['costo']:.1f}, mínima {c['vm_min']:.4f} p.u., {cuenta(len(c['obras']), 'obra', 'obras')}")
    if args.modelo_salida:
        guardar_modelo(args.modelo_salida, modelo, parametros, [(args.grafo.name, grafo)], semilla=args.semilla,
                       iteraciones=args.iteraciones, dispositivo=args.dispositivo)
        print(f'Modelo para la puerta: {args.modelo_salida}')
    if args.salida:
        args.salida.write_text(json.dumps(salida, ensure_ascii=False, indent=2, default=float), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
