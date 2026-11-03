# Tareas — Spec 071

- [x] T1 Redes en el dominio y fuera de dominio por red. (RF-1, RF-2)
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k red` en verde.
- [x] T2 Puertas contra la física y el modelo en uso. (RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k comparacion` en verde, y `tests/test_digital_twin_oraculo.py` y `tests/test_optimizacion_oraculo.py` en verde con GPU.
- [x] T3 Monitor y vigilancia. (RF-5, RF-6)
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k "monitor or vigilancia"` en verde.
- [x] T4 Turno de GPU común. (RF-7, RF-8)
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k turno` en verde.
- [ ] T5 Medir antes y después en una red de prueba: tiempo de `optimizar_con_proyecto` y si cambia la obra elegida. (RF-2)
      Hecho cuando: la medida está anotada aquí, sin tocar proyectos ya trabajados.
      Avance del 2026-11-02, sin DIgSILENT, con los grafos guardados en los episodios: con la regla anterior, la PINN
      `20261028-114528-e6f5` (Chincha, 4 944 nodos) entraba en dominio en 7 de 19 proyectos (Chincha, Nasca, W12882, NJA202);
      con esta spec, en ninguno. Sin medir: tiempo y obra elegida. En el grafo guardado de Chincha el flujo del oráculo no
      converge sin obras (`medir([], 0)`), así que la PINN no llega a usarse y antes y después dan lo mismo.
