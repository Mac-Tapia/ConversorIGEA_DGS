# Plan 114 — Agente MASAC que aprende a operar el conversor

## Módulos

- `src/convertersmartgrid/aplicacion/agente/entornos/` (RF-1, RF-4, RF-5): un `ParallelEnv` de PettingZoo por módulo
  (obras primero), con observación por agente, espacio de acciones y recompensa; pasos con el oráculo y el motor abierto
  (`motores_flujo.py`, 083).
- `src/convertersmartgrid/aplicacion/agente/escenarios.py` (RF-5): escenarios desde VNR-GIS (080) con demanda generada.
- `src/convertersmartgrid/adaptadores/agente_masac.py` (RF-2, RF-3, RF-12): entrenamiento MASAC con BenchMARL, en Colab
  (113); inferencia local sin GPU.
- `tools/agente_comparar_marllib.py` (RF-3): la comparación con MARLlib en su entorno aparte, por ficheros.
- `src/convertersmartgrid/aplicacion/agente/sombra.py` (RF-7, RF-8, RF-11): modo sombra, registro de experiencia y puertas.
- Web (RF-7, RF-9): las propuestas del agente junto a las del método actual, con su explicación y la confirmación.
- La 074 se reescribe como fase 1 (obras) de este plan; su código PPO queda como base de comparación.

## Decisiones

- BenchMARL/TorchRL para MASAC (lo trae nativo con CTDE y corre en Python 3.12). MARLlib solo para comparar: fija Ray 1.8
  y Python ≤ 3.9 y no trae MASAC de serie.
- DIgSILENT fuera del bucle (caro y con licencia única); el oráculo y el motor abierto dan los pasos.
- Currículo y modo sombra antes de actuar: el riesgo de una política mal recompensada es alto.

## Pruebas

- Entornos: espacios de observación y acción, recompensa con casos sintéticos sorteados, determinismo con semilla.
- Política: aprende un caso de juguete (un alimentador sintético) mejor que el azar; MASAC frente a PPO en el mismo caso.
- Modo sombra: registra y no aplica; las puertas impiden actuar sin superar al método actual.
- Real: fase 1 con redes VNR-GIS públicas y validación con un sistema real medido.
