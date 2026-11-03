# Tareas — Spec 078

- [x] T1 Lectura única del flujo y clasificación. (RF-1 a RF-12)
  Hecho cuando: `pytest -q tests/test_senales_de_convergencia.py -k "lectura or clasifica"` en verde.
- [x] T2 «Caso base», vínculo y gemelo. (RF-13 a RF-18)
  Hecho cuando: `pytest -q tests/test_senales_de_convergencia.py -k caso_base` y `tests/test_caso_base_verificado.py` en verde.
- [x] T3 La línea de la importación y sus recuentos. (RF-19 a RF-24)
  Hecho cuando: `pytest -q tests/test_senales_de_convergencia.py -k importacion` en verde.
- [x] T4 Interfaz e informe de texto. (RF-25 a RF-28)
  Hecho cuando: `pytest -q tests/test_senales_de_convergencia.py -k "interfaz or informe"` en verde y `npm run typecheck` sin errores.
- [x] T5 Grupos al importar y dudas del plan. (RF-29 a RF-35)
  Hecho cuando: `pytest -q tests/test_plan_grupos_al_importar.py` en verde.
- [ ] T6 [DIgSILENT] Un proyecto importado cuyo flujo no calcula y otro bueno, por la web.
  Hecho cuando: el primero sale `IMPORTADO_SIN_CONVERGENCIA` con su `return_code` y `NO_CONVERGE`; el segundo, `OK`, `VERIFICADO` y `CONVERGED_*`.
- [ ] T7 [DIgSILENT] Vuelve a verificar el primero y la orden «importa <grupo> en digsilent» en el navegador.
  Hecho cuando: sigue `NO_CONVERGE` con el flujo registrado; la tabla lo muestra; la orden propone el grupo sin pedir alimentadores.
