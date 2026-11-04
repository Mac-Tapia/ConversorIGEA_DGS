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
- [ ] T6. [DIgSILENT] NA203 + NA205 optimizado desde la web. (Todos)
      Hecho cuando: cada carga nueva con su destino, la red existente con obras que cumplen y la SET
      Copara con su punto, su módulo PIT y «Con proyecto» dentro de 0,94–1,06 pu.
