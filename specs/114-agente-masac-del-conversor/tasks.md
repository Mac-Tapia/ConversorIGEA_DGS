# Tareas 114 — Agente MASAC que aprende a operar el conversor

- [x] T1. Entorno PettingZoo de obras (Dec-POMDP: un agente en cada alimentador, en cada SET y en el sistema eléctrico (RF-13),
      observación parcial, acciones de banco,
      tap, transferencia y escalera, recompensa CNE + costo + pérdidas), con el oráculo y el motor abierto. (RF-1, RF-4, RF-10, RF-13,
      RF-15, RF-16, RF-17, RF-18, RF-20)
      Hecho cuando: pruebas 114:RF-1, RF-4, RF-10, RF-13, RF-15 a RF-18 y RF-20 en verde con redes sintéticas sorteadas.
      Hecho el 2026-11-27: `masac_entorno.py` (agentes formados de la red o de la estructura de la 055, pasos con el
      motor abierto, el barrido o una PINN, recompensa en máxima y valle) y `tests/test_masac_agente.py` en verde en CPU
      (D:/csg/PM_IMPL/114/verde_masac_y_074.log, con las de la 074); rojo por aserción de cada RF con una mutación
      (D:/csg/PM_IMPL/114/rojo_mutaciones_1.log); con PettingZoo 1.27.0 aparte pasa `parallel_api_test`
      (D:/csg/PM_IMPL/114/comprobar_api.log).
- [ ] T2. Escenarios desde VNR-GIS públicos con demanda generada desde las curvas propias. (RF-5)
      Hecho cuando: prueba 114:RF-5 en verde con un paquete sintético; ensayo con dos distribuidoras reales.
- [x] T3. MASAC con BenchMARL y CTDE; inferencia local sin GPU. (RF-2, RF-3, RF-14)
      Hecho cuando: en un caso de juguete la política supera al azar y se compara con PPO (074), con semilla fija.
      Hecho el 2026-11-27 sin BenchMARL (RF-14: no importa con torchrl 0.14.1; D:/csg/PM_IMPL/114/deps_benchmarl.log),
      con `masac_politica.py` en PyTorch y en CPU. `tools/masac_agente.py juguete --semilla 1 --episodios 80`
      (D:/csg/PM_IMPL/114/juguete_semilla1.json): MASAC queda en norma con un banco, una toma y la consigna (obras 10,
      maniobras 2, retorno −1,19) frente al azar (−4,08, en norma el 74 % de los episodios); con solo obras, MASAC usa
      dos bancos (20), como la escalera y NSGA-II, y la PPO GATv2 de la 074 tres (30), todos en norma y medidos igual.
- [x] T4. Registro de experiencia y modo sombra en la web, con explicación. (RF-7, RF-9, RF-11, RF-19, RF-21, RF-22,
      RF-23)
      Hecho cuando: pruebas 114:RF-7, RF-9, RF-11, RF-19, RF-21 a RF-23 en verde; la web propone sin aplicar.
      Hecho el 2026-11-27: `masac_sombra.py` (registro JSONL de decisiones con confirmaciones y deshechas, que vuelven
      como castigo; propuesta en sombra junto a la escalera con su explicación; guarda de dónde se escribe),
      `tools/masac_agente.py sombra` y la web: `POST …/agente/sombra` (trabajo en CPU con la red del gemelo y el motor
      abierto, sin DIgSILENT), `GET …/agente/sombra?project=` (propuestas y marcador) y `POST
      …/agente/sombra/decisiones/{id}` (confirmar o deshacer, solo al registro), con el bloque «Propuesta del agente (en
      sombra, no se aplica)» junto a las obras automáticas. Pruebas: `tests/test_masac_agente.py`,
      `tests/test_agente_sombra_web.py` y `frontend/test/agenteSombra.test.mjs` en verde; `npm test`, `tsc` y
      `npm run build` en verde (registros en D:/csg/PM_IMPL/114/).
- [ ] T5. Puertas de la fase 1 frente a NSGA-II con el oráculo y confirmación con DIgSILENT. (RF-8, RF-12)
      Hecho cuando: prueba 114:RF-8 en verde y una corrida real en un proyecto de prueba.
- [ ] T6. Comparación con MARLlib (MAPPO, MADDPG) en su entorno aparte. (RF-3)
      Hecho cuando: informe de la comparación en los mismos casos, con sus semillas.
- [ ] T7. [Colab] Entrenamiento de la fase 1 por el circuito de la 113. (RF-6, RF-12)
      Hecho cuando: candidato traído y examinado por sus puertas, con su evidencia aquí.
- [ ] T8. Fases siguientes (calibración, cargas nuevas, estudios, modelos, RAG, director): cada una con su ampliación de
      esta spec antes de implementarla. (RF-6)
      Hecho cuando: cada fase tiene sus RF y sus tareas en esta spec, aprobados por el usuario, y su puerta superada.
