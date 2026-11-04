# Tareas — Spec 042

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. `set_nueva.py`: potencia de diseño, módulos PIT del libro CAPEX y el que cubre, ubicación
      óptima con sorteos de crecimiento por zona; claves del perfil. (RF-5, RF-7 a RF-9)
      Hecho cuando: `pytest -q tests/test_set_nueva.py` en verde.
      Hecho el 2026-10-31: `potencia_de_diseno`, `leer_modulos_pit`, `elegir_modulo` y
      `ubicacion_optima` (Weber con las potencias esperadas; los sorteos dan la dispersión);
      `factor_seguridad_set` y `modulos_pit` en el perfil. Con el libro real: hasta 25 MVA la Nueva
      SET Copara (5,75 M USD), hasta 40 MVA el transformador de 40 MVA; 7 pruebas, 10 semillas.
- [x] T2. Ramas que pasan a la SET nueva y su punto de corte. (RF-6)
      Hecho cuando: `pytest -q tests/test_set_nueva.py -k rama` en verde.
- [x] T3. Carga a carga: orden, cargas apartadas en la escalera y bisección de cuántas caben. (RF-1 a RF-4)
      Hecho cuando: `pytest -q tests/test_set_nueva_web.py -k escalera` en verde.
- [x] T4. Obra «SET nueva» en DIgSILENT, con su comprobación de tensiones. (RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion_042.py` en verde.
      Hecho el 2026-10-31: clase de obra `set_nueva` (validación, plan y `construir_set_nueva`: barras,
      red externa copiada de la de cabecera, trafo con la uk de IEC 60076-5 del perfil, una línea y un
      `ElmFeeder` por rama, tramo de entrada abierto, y hasta 6 acercamientos a la barra que peor
      queda); modo `--set-nueva-datos`; 8 pruebas con el doble.
- [x] T5. Informe y botón en el paso de obras. (RF-12, RF-13)
      Hecho cuando: `pytest -q tests/test_set_nueva_web.py` en verde y `npm run build` sin errores.
      Hecho el 2026-10-31: `set_nueva_proponer` y `con_proyecto_optimizar`, ruta
      `/pf/obras/con-proyecto`; botón «Optimizar «Con proyecto» con SET nueva» y su informe en el paso 3
      (el de la escalera de la 025); `tsc` y `npm run build` sin errores.
- [x] T7. Transformadores en paralelo y cargas apartadas en la SET nueva. (RF-6, RF-14)
      Hecho cuando: `pytest -q tests/test_set_nueva.py tests/test_obras_pf_guion_042.py
      tests/test_set_nueva_web.py` en verde.
      Hecho el 2026-10-31: `elegir_modulo(max_unidades=)`, campo `unidades` de la obra y
      `ElmTr2.ntnum`; la barra de cada carga apartada se lleva a media desde la que dio la escalera
      (antes 29 de 32 quedaban fuera con «no está activa»). La primera corrida en DIgSILENT
      (trabajo aaaccc63b7e1): caben 3 cargas con bancos 2×450 kvar y terna de 11,13 km en NA203;
      32 a la SET nueva, 45,5 MVA de diseño, sin módulo de 40 MVA que los cubra.
- [x] T8. Ramas abiertas en barras de la red sin las cargas nuevas. (RF-15)
      Hecho cuando: `pytest -q tests/test_set_nueva.py tests/test_set_nueva_web.py` en verde, con la
      lectura de DIgSILENT dando las barras que existen con las cargas nuevas apartadas.
- [x] T9. Toma y consigna de la SET nueva; el mejor punto probado. (RF-10, RF-16)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion_042.py` en verde, con el transformador
      regulando a la consigna de la cabecera y el informe con la toma y el punto elegidos.
- [x] T11. La escalera primero, cuando el operador la pide. (RF-17)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py` en verde.
- [x] T12. La carga que parte un tramo también entra en la SET nueva. (RF-18)
      Hecho cuando: `pytest -q tests/test_set_nueva_web.py` en verde.
- [x] T13. La obra inactiva o fallida devuelve lo que abrió. (RF-19)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion.py` en verde.
- [x] T14. Barra por tensión, zonas geográficas y alimentador expreso. (RF-20, RF-21, RF-22)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion_042.py tests/test_set_nueva.py tests/test_set_nueva_web.py` en verde.
- [x] T15. «Con proyecto» medido con el plan completo de las zonas. (RF-23)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion_042.py` en verde.
- [x] T16. La escalera por alimentador. (RF-24)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py` en verde.
- [x] T17. Cada etapa nueva con su segundo propio. (RF-25)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py` en verde.
- [x] T18. La fila cercana que no cabe en el transformador de la SED es SED nueva. (RF-26)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py` en verde.
- [x] T19. Secciones normalizadas y 80 % de planeamiento. (RF-27, RF-28)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T20. Al aplicar, solo la obra elegida de cada alimentador. (RF-29)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py` en verde.
- [x] T21. Conductores normalizados desde su ficha y doble terna en el mismo camino. (RF-30)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T22. «Con proyecto» desde `tools/sistema_web.py`, sin vigilancia. (RF-31)
      Hecho cuando: `pytest -q tests/test_sistema_web.py` en verde.
- [x] T23. Las cargas nuevas se reponen antes de la escalera. (RF-32)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py tests/test_obras_pf_guion_042.py` en verde.
- [x] T24. La SET sin módulo se dimensiona igual y los tipos de regulador se crean. (RF-33, RF-34)
      Hecho cuando: `pytest -q tests/test_set_nueva.py tests/test_set_nueva_web.py tests/test_obras_pf_guion_042.py` en verde.
- [x] T25. En línea larga, el regulador por delante del tope de variantes. (RF-35)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T26. Obras georreferenciadas y bancos a 2/3 en línea larga. (RF-36, RF-37)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_obras_pf_guion_042.py` en verde.
- [x] T27. Todas las obras integradas en las variantes. (RF-38)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T28. «Con proyecto» de cualquier empresa siempre propone obras. (RF-39, RF-40, RF-41, RF-42)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_set_nueva.py` en verde.
- [ ] T29. [DIgSILENT] «Con proyecto» de un sistema de otra empresa y otra tensión, sin perfil, desde la web. (RF-39, RF-40)
      Hecho cuando: cada alimentador con cargas nuevas termina con obra medida o «ya cumple».
- [x] T30. Cada variante refuerza los tramos sobrecargados de cualquier ramal. (RF-43)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T31. El camino eléctrico pasa por acopladores y equipos en serie. (RF-44, RF-45)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_obras_pf_guion_042.py` en verde.
- [x] T32. Tipos de la biblioteca por su nombre pedido y regulador en puntos óptimos. (RF-46, RF-47)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_obras_pf_guion_042.py` en verde.
- [x] T33. La obra de cada alimentador se aplica al terminarlo. (RF-48)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py` en verde.
- [x] T34. El regulador solo por encima de 15 km. (RF-49)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T35. Escalón de 10 a 22,9 kV en la escalera, con su costo. (RF-50, RF-53, RF-54)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T36. Celda nueva en la barra de 22,9 kV de la SET, o cambio con su fuente. (RF-51, RF-52)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion_016.py` en verde.
- [x] T40. Rehacer las obras de los alimentadores marcados. (RF-60)
      Hecho cuando: `pytest -q tests/test_obras_pf_guion_042.py tests/test_informe_factibilidad_un_paso.py` en verde.
- [x] T41. Elevador dedicado en cabecera compartida, con su costo y su límite. (RF-61, RF-62, RF-63)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_obras_pf_guion_016.py` en verde.
- [ ] T42. [DIgSILENT] Un alimentador de 10 kV sin barra de 22,9 kV en su SET converge con el elevador. (RF-61)
      Hecho cuando: el flujo converge con el elevador sobre un proyecto de prueba, y su medida queda en la tarea.
- [x] T43. Obra aparte para el déficit previo, con su costo. (RF-64, RF-65, RF-66)
      Hecho cuando: `pytest -q tests/test_informe_factibilidad_un_paso.py tests/test_valle.py` en verde.
- [x] T45. Rótulos, nota del informe, valle y factor del elevador. (RF-67, RF-68, RF-69, RF-70)
      Hecho cuando: `pytest -q tests/test_informes_planeamiento.py tests/test_valle.py tests/test_escalera_optima.py` en verde.
- [x] T46. El factor en el regulador, con una sola regla, y su valor en el informe. (RF-71, RF-72)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_set_nueva.py tests/test_informes_planeamiento.py` en verde.
- [ ] T44. [DIgSILENT] La obra del déficit previo de SI112, medida en el proyecto de prueba de Pisco. (RF-64)
      Hecho cuando: su mínima de media y su costo quedan anotados en esta tarea.
- [ ] T37. [DIgSILENT] Un alimentador de 10 kV de Pisco pasa a 22,9 kV y converge. (RF-50, RF-51)
      Hecho cuando: el flujo de «Con proyecto» converge con la celda nueva y sus cargas en límites.
- [x] T38. Hasta 3 alternativas, elegida por costo anual y sin repetir sorteos. (RF-55, RF-56, RF-57, RF-59)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_informe_factibilidad_un_paso.py` en verde.
- [x] T39. Las alternativas en el informe de estudio, el plan y el PIDE. (RF-58)
      Hecho cuando: `pytest -q tests/test_informes_planeamiento.py tests/test_informe_alternativas.py` en verde.
- [ ] T6. [DIgSILENT] NA203 + NA205 optimizado desde la web. (Todos)
      Hecho cuando: cada carga nueva con su destino, la red existente con obras que cumplen y la SET
      Copara con su punto, su módulo PIT y «Con proyecto» dentro de 0,94–1,06 pu.
