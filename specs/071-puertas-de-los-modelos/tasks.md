# Tareas — Spec 071

- [x] T1 Redes en el dominio y fuera de dominio por red. (RF-1, RF-2)
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k red` en verde.
- [x] T2 Puertas contra la física y el modelo en uso. (RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k comparacion` en verde, y `tests/test_digital_twin_oraculo.py` y `tests/test_optimizacion_oraculo.py` en verde con GPU.
- [x] T3 Monitor y vigilancia. (RF-5, RF-6)
  Cambio del 2026-11-13 (aclaración de RF-6): sin la variable la vigilancia cuenta los datos nuevos; solo `0` la para.
  Pruebas: `tests/test_puertas_modelos.py::test_vigilancia_entrena_salvo_la_orden_de_parar` y
  `test_un_candidato_que_no_pasa_sus_puertas_no_se_promueve`; rojo y verde en `D:/csg/EDICION/rojo2_ampliacion.log` y
  `verde2_ampliacion.log`.
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k "monitor or vigilancia"` en verde.
- [x] T4 Turno de GPU común. (RF-7, RF-8)
      Hecho cuando: `pytest -q tests/test_puertas_modelos.py -k turno` en verde.
- [x] T5 Medir antes y después en una red de prueba: tiempo de `optimizar_con_proyecto` y si cambia la obra elegida. (RF-2)
      Hecho cuando: la medida está anotada aquí, sin tocar proyectos ya trabajados.
      Avance del 2026-11-02, sin DIgSILENT, con los grafos guardados en los episodios: con la regla anterior, la PINN
      `20261028-114528-e6f5` (Chincha, 4 944 nodos) entraba en dominio en 7 de 19 proyectos (Chincha, Nasca, W19882, NJA292);
      con esta spec, en ninguno. Sin medir: tiempo y obra elegida. En el grafo guardado de Chincha el flujo del oráculo no
      converge sin obras (`medir([], 0)`), así que la PINN no llega a usarse y antes y después dan lo mismo.
      Avance del 2026-11-19 (59), medida «después» en DIgSILENT sobre el proyecto de prueba importado por la web
      el 2026-11-19 (código 37585807): «Con proyecto» con 3 cargas nuevas → obra sección
      AA24003D_22_9kV_FICHA en 63 tramos (15,88 km), definitiva, aplicada; obras_pf.py 24 órdenes, 0 % fallidas, 0,22 h
      (D:/csg/INTEGRA_54/cierre_tareas/digsilent/, corrida C2c). Falta la medida «antes» (regla anterior) sobre el mismo
      proyecto para comparar tiempo y obra: sigue abierta.
      Hecho el 2026-11-20 (MEJ18, wt_d8_obras): la medida «antes» (la regla sin 071:RF-2) y «después» (la vigente),
      con `tools/medir_mejora.py dominio`, sobre los grafos del gemelo capturados en esa misma corrida C2c del proyecto de
      prueba (7 episodios con grafo, de 1 344 y 1 355 nodos; el octavo no trae grafo y se dice) y la PINN promovida
      `20261028-114528-e6f5`: con las dos reglas decide el flujo físico en los 7, porque la regla anterior ya la dejaba
      fuera (flujo desequilibrado, grafo de otra versión y 1 355 nodos frente a los 4 944 aprendidos). «Con proyecto» corre
      el mismo camino con las dos: la obra elegida no cambia (la sección de la corrida C2c, 63 tramos, 15,88 km) y el
      tiempo de `optimizar_con_proyecto` tampoco (C2c: 16 min 42 s de trabajo; obras_pf.py 24 órdenes en 0,22 h), salvo la
      comprobación de dominio, de 0,08 a 0,25 ms por red. Una red donde la regla sí cambia la decisión la marca la
      herramienta («CAMBIA: medir en DIgSILENT»). Prueba: `tests/test_puertas_modelos.py::test_medida_de_la_regla_de_red_antes_y_despues`
      (rojo por aserción con la herramienta de la base; verde). Evidencia fuera de git:
      `D:/csg/PM_IMPL/MEJ18_OBRAS/T5_dominio_red_de_prueba.json` y `.log`, sin tocar proyectos ya trabajados.
