# Tareas — Spec 052

- [ ] T1. Lectura única del grafo y de las cargas nuevas por variación en «Con proyecto». (RF-1)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py -k lectura` en verde con el doble.
- [ ] T2. Variantes aplicadas al grafo y flujo del oráculo con k cargas, máxima y sorteos. (RF-2, RF-3, RF-9)
      Hecho cuando: en una red sintética, cada obra mueve la tensión como su flujo exacto.
- [ ] T3. Búsqueda de k y elección con el oráculo; confirmación y discrepancias en DIgSILENT. (RF-4 a RF-8, RF-10)
      Hecho cuando: con un DIgSILENT doble que discrepa, se corrige hacia lo confirmado.
- [ ] T4. [DIgSILENT] NA203 + NA205 optimizado por la web en menos de 20 min. (Todos)
      Hecho cuando: elegida y límite confirmados y la comparación oráculo–DIgSILENT en el informe.
