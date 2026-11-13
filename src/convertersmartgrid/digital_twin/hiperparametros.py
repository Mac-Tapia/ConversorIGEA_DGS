"""Búsqueda de hiperparámetros del gemelo (spec 027, T6; RF-7).

Los de la PINN/GNN se eligieron a mano en IN111–TA225 (64 ocultas, 8 pasos, peso físico
10⁻⁴; 2026-10-24) y no tenían por qué valer para otro sistema. La búsqueda es bayesiana (TPE
de Optuna, Bischl et al., *WIREs DMKD* 2023) con poda por mediana sobre la curva de
validación, con presupuesto de ensayos, y evalúa cada ensayo **solo en la partición de
validación**: la de prueba (otra red) queda para decidir la promoción. Todos los ensayos y la
configuración elegida se guardan junto a los modelos.

El presupuesto son ensayos, no segundos (027:RF-70). Con ``timeout`` de ``Study.optimize``, Optuna
deja de crear ensayos al vencer el plazo («the study continues to create trials until the number of
trials reaches n_trials, timeout period elapses…»): cuántos ensayos entraban, y así la configuración
elegida, dependía de lo cargada que estuviera la máquina. El reloj queda como tope de seguridad: si
vence antes de los ensayos pedidos, la búsqueda se para sin elegir nada.

Un ensayo que falla para la búsqueda con su error (027:RF-71). Con ``catch=(RuntimeError,)``, en la
suite del 2026-11-12 los tres ensayos fallaron en 0,2 s por «CUDA error: out of memory» con la GPU
compartida, y el mensaje decía «ningún ensayo terminó dentro del presupuesto»: la elección entre los
que quedaran dependería de la memoria libre, no de los datos.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .oraculo import Entrenamiento, Muestra, OraculoPINN, entrenar_miembro, mae, particionar, separar_calibracion


def _sugerir(trial, base: Entrenamiento) -> Entrenamiento:
    """El espacio de búsqueda alrededor de lo que ya se usa."""
    return Entrenamiento(**{**base.__dict__,
                            'lr': trial.suggest_float('lr', 1e-4, 1e-2, log=True),
                            'ocultas': trial.suggest_categorical('ocultas', [32, 64, 96]),
                            'pasos': trial.suggest_int('pasos', 4, 10),
                            'peso_fisico': trial.suggest_float('peso_fisico', 1e-5, 1e-2, log=True),
                            'recorte': trial.suggest_float('recorte', 0.5, 5.0)})


def buscar(muestras: Sequence[Muestra], *, base: Entrenamiento | None = None, ensayos: int = 20,
           limite_s: float = 1800.0, semilla: int = 0, destino: Path | None = None,
           log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Busca con TPE y poda, evaluando en validación; guarda los ensayos en ``destino``."""
    import optuna

    base = base or Entrenamiento()
    grupos = separar_calibracion(particionar(muestras))
    entrenamiento, validacion = grupos['entrenamiento'], grupos['validacion']
    if not entrenamiento or not validacion:
        raise ValueError('hacen falta episodios de entrenamiento y de validación para buscar (027:RF-7)')
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    x = np.concatenate([m.x for m in entrenamiento])
    # Con el dominio de lo que se entrena, como ``oraculo.entrenar``: amplio para no marcar
    # fuera de dominio la validación, que es de la misma red.
    dominio = {'x_min': x.min(axis=0).tolist(), 'x_max': x.max(axis=0).tolist(),
               'nodos': [min(len(m.ids) for m in entrenamiento), max(len(m.ids) for m in entrenamiento)]}

    def objetivo(trial) -> float:
        cfg = _sugerir(trial, base)

        def podar(epoca: int, err: float) -> None:
            trial.report(err, epoca)
            if trial.should_prune():
                raise optuna.TrialPruned()

        try:
            estado = entrenar_miembro(entrenamiento, cfg, None, validacion=validacion, al_validar=podar)
        except RuntimeError as exc:
            raise RuntimeError(f'el ensayo {trial.number} de la búsqueda falló: {exc}; no se elige entre los '
                               f'demás (027:RF-71)') from exc
        error = mae(OraculoPINN([estado], cfg, dominio), validacion)
        log(f'  ensayo {trial.number}: {trial.params} → {error:.3e} p.u. en validación')
        return float(error)

    estudio = optuna.create_study(direction='minimize',
                                  sampler=optuna.samplers.TPESampler(seed=semilla),
                                  pruner=optuna.pruners.MedianPruner(n_startup_trials=3, n_warmup_steps=10))
    inicio = time.monotonic()

    def tope_de_seguridad(estudio_, _trial) -> None:
        # Entre ensayos, como Optuna con ``timeout``; pero aquí el tope no da por buena una búsqueda corta.
        if time.monotonic() - inicio > limite_s and len(estudio_.trials) < ensayos:
            estudio_.stop()

    # Sin ``timeout`` ni ``catch``: deciden los ensayos (RF-70) y un fallo para la búsqueda (RF-71).
    estudio.optimize(objetivo, n_trials=ensayos, callbacks=[tope_de_seguridad])
    if len(estudio.trials) < ensayos:
        raise TimeoutError(f'la búsqueda superó el tope de seguridad de {limite_s:g} s tras {len(estudio.trials)} '
                           f'de {ensayos} ensayos; no se elige con una búsqueda incompleta (027:RF-70)')
    completos = [t for t in estudio.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if not completos:
        raise ValueError(f'los {ensayos} ensayos se podaron y ninguno terminó (027:RF-7)')
    mejor = estudio.best_trial
    elegida = _sugerir(optuna.trial.FixedTrial(mejor.params), base)
    informe = {'ensayos_pedidos': ensayos, 'limite_s': limite_s, 'segundos': time.monotonic() - inicio,
               'presupuesto': {'unidad': 'ensayos', 'ensayos': ensayos, 'tope_seguridad_s': limite_s},
               'semilla': semilla, 'evaluado_en': 'validacion', 'validacion': len(validacion),
               'entrenamiento': len(entrenamiento),
               'calibracion_reservada': len(grupos['calibracion']),
               'ensayos': [{'numero': t.number, 'params': t.params, 'mae_validacion': t.value,
                            'estado': t.state.name} for t in estudio.trials],
               'mejor': {'numero': mejor.number, 'params': mejor.params, 'mae_validacion': mejor.value},
               'cfg': elegida.__dict__}
    if destino is not None:
        destino.mkdir(parents=True, exist_ok=True)
        ruta = destino / f"busqueda_{time.strftime('%Y%m%d-%H%M%S')}.json"
        ruta.write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding='utf-8')
        informe['ruta'] = str(ruta)
    return informe
