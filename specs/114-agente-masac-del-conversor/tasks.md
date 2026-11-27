# Tareas 114 — Agente MASAC que aprende a operar el conversor

- [ ] T1. Entorno PettingZoo de obras (Dec-POMDP: agentes por alimentador y SET, observación parcial, acciones de banco,
      tap, transferencia y escalera, recompensa CNE + costo + pérdidas), con el oráculo y el motor abierto. (RF-1, RF-4, RF-10)
      Hecho cuando: pruebas 114:RF-1, RF-4, RF-10 en verde con redes sintéticas sorteadas.
- [ ] T2. Escenarios desde VNR-GIS públicos con demanda generada desde las curvas propias. (RF-5)
      Hecho cuando: prueba 114:RF-5 en verde con un paquete sintético; ensayo con dos distribuidoras reales.
- [ ] T3. MASAC con BenchMARL y CTDE; inferencia local sin GPU. (RF-2, RF-3)
      Hecho cuando: en un caso de juguete la política supera al azar y se compara con PPO (074), con semilla fija.
- [ ] T4. Registro de experiencia y modo sombra en la web, con explicación. (RF-7, RF-9, RF-11)
      Hecho cuando: pruebas 114:RF-7, RF-9, RF-11 en verde; la web propone sin aplicar.
- [ ] T5. Puertas de la fase 1 frente a NSGA-II con el oráculo y confirmación con DIgSILENT. (RF-8, RF-12)
      Hecho cuando: prueba 114:RF-8 en verde y una corrida real en un proyecto de prueba.
- [ ] T6. Comparación con MARLlib (MAPPO, MADDPG) en su entorno aparte. (RF-3)
      Hecho cuando: informe de la comparación en los mismos casos, con sus semillas.
- [ ] T7. [Colab] Entrenamiento de la fase 1 por el circuito de la 113. (RF-6, RF-12)
      Hecho cuando: candidato traído y examinado por sus puertas, con su evidencia aquí.
- [ ] T8. Fases siguientes (calibración, cargas nuevas, estudios, modelos, RAG, director): cada una con su ampliación de
      esta spec antes de implementarla. (RF-6)
      Hecho cuando: cada fase tiene sus RF y sus tareas en esta spec, aprobados por el usuario, y su puerta superada.
