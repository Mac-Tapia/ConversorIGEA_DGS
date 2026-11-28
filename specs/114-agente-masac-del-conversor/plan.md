# Plan 114 — Agente MASAC que aprende a operar el conversor

## Módulos

- `src/convertersmartgrid/adaptadores/masac_entorno.py` (RF-1, RF-4, RF-10, RF-13, RF-15 a RF-18, RF-20; T1): el
  `ParallelEnv` de obras con un agente por alimentador, por SET y por sistema, su observación parcial con la consigna del
  nivel superior, sus acciones (banco, terna, escalera, toma, transferencia y consigna de la fuente) y la recompensa común;
  los pasos los evalúa el motor abierto (`digital_twin/motores_flujo.py`, 083), el barrido del oráculo o el oráculo PINN.
  Va en `adaptadores/` y no en `aplicacion/agente/`: usa el oráculo, que es un adaptador, y la capa de aplicación no puede
  importarlo (`tests/test_capas.py`). Reutiliza de la 074 (`madrl_obras.py`) las zonas por alimentador, los candidatos,
  las obras, la medida de violaciones y las penalidades.
- `src/convertersmartgrid/aplicacion/agente/escenarios.py` (RF-5): escenarios desde VNR-GIS (080) con demanda generada.
- `src/convertersmartgrid/adaptadores/masac_politica.py` (RF-2, RF-3, RF-14; T3): MASAC propio en PyTorch con CTDE,
  entrenamiento en CPU para el juguete (Colab, 113, para lo grande) e inferencia local sin GPU; guarda y carga el modelo
  con su manifiesto. `tools/masac_agente.py juguete` lo compara con el azar y con la PPO GATv2 de la 074 en la misma red.
- `tools/agente_comparar_marllib.py` (RF-3): la comparación con MARLlib en su entorno aparte, por ficheros.
- `src/convertersmartgrid/adaptadores/masac_sombra.py` (RF-7, RF-9, RF-11, RF-19; T4): registro de experiencia en JSONL
  (decisiones y sus confirmaciones o deshechas, que vuelven a la recompensa por RF-10), modo sombra frente a la escalera
  de la 074 con la explicación de cada propuesta, y la guarda de dónde se puede escribir. Las puertas (RF-8) son de la T5.
- Web (RF-7, RF-9, RF-11, RF-21 a RF-23; T4): `presentacion/web/agente_sombra.py` y `agente_sombra_api.py` (la red del
  gemelo del proyecto, la primera política en CPU si no hay, la propuesta en el carril del asistente, su lectura con el
  marcador y la decisión del operador en el registro), y en `frontend/` el bloque `PropuestaAgente.tsx` junto a las obras
  automáticas, con sus textos en `textosAgente.ts`.
- La 074 se reescribe como fase 1 (obras) de este plan; su código PPO queda como base de comparación.

## Decisiones

- BenchMARL/TorchRL para MASAC (lo trae nativo con CTDE y corre en Python 3.12). MARLlib solo para comparar: fija Ray 1.8
  y Python ≤ 3.9 y no trae MASAC de serie.
- 2026-11-27 (RF-14): BenchMARL no se instala. Su 1.5.2 fija `torchrl<0.12` y no importa con la TorchRL 0.14.1 que pide
  torch 2.14.1 (falta `torchrl.collectors.SyncDataCollector`; evidencia en `D:/csg/PM_IMPL/114/deps_benchmarl.log`).
  Alternativa descartada: bajar TorchRL, que obliga a otro PyTorch. MASAC se escribe en PyTorch con la misma formulación,
  y así entrena e infiere también sin `madrl_deps`. PettingZoo 1.27.0 sí se instala aparte (`requirements-madrl.txt`):
  con él la herramienta pasa `parallel_api_test`; sin él, el entorno cumple la misma API (RF-15).
- Cada nivel tiene un número fijo de huecos de acción (los candidatos de la 074, las tomas, las transferencias y las
  consignas declarados), para que un actor valga para todos los agentes de su nivel; el crítico central ve el estado global
  agregado por nivel (media y máximo), así su tamaño no depende del número de alimentadores (RF-13).
- DIgSILENT fuera del bucle (caro y con licencia única); el oráculo y el motor abierto dan los pasos.
- Currículo y modo sombra antes de actuar: el riesgo de una política mal recompensada es alto.

## Pruebas

- Entornos: espacios de observación y acción, recompensa con casos sintéticos sorteados, determinismo con semilla.
- Política: aprende un caso de juguete (un alimentador sintético) mejor que el azar; MASAC frente a PPO en el mismo caso.
- Modo sombra: registra y no aplica; las puertas impiden actuar sin superar al método actual.
- Real: fase 1 con redes VNR-GIS públicas y validación con un sistema real medido.
