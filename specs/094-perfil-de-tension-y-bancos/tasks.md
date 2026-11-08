# Tareas 094

Lee: `specs/094-perfil-de-tension-y-bancos/spec.md` y `plan.md`.

- [x] T1. `perfil_tension.py`: perfil, ubicaciones por reglas, separación y bancos hasta el objetivo. (RF-1, RF-4, RF-6, RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_perfil_tension.py` en verde.
- [x] T2. El perfil en el informe de la calibración y guardado con ella. (RF-1, RF-2, RF-10, RF-11, RF-12)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_perfil_tension.py` en verde.
- [x] T3. La escalera, el déficit previo y el sistema usan las ubicaciones del perfil. (RF-4, RF-5, RF-7)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py tests/test_seleccion_por_oraculo.py` en verde.
- [x] T4. El perfil en la web y en el informe del estudio. (RF-2, RF-3)
      Hecho cuando: `npm --prefix frontend run build` sin errores y `pytest -q tests/test_informe_docx.py tests/test_ajuste_cabecera_web.py tests/test_informe_web.py` en verde. Verlo en el navegador real pasa a la T5, que es la que deja un perfil real.
- [x] T8. Bancos solo en la troncal y en las troncales de los ramales largos; camino sin ciclos. (RF-16, RF-17)
      Hecho cuando: `pytest -q tests/test_perfil_tension.py tests/test_optimizacion_oraculo.py tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T9. La variante de bancos según el perfil manda si cumple en DIgSILENT. (RF-18)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [x] T6. El perfil completo antes y después de cada propuesta, con su comparación. (RF-13, RF-14)
      Hecho cuando: `pytest -q tests/test_perfil_tension.py tests/test_optimizacion_oraculo.py` en verde.
- [x] T7. El gráfico de perfil de tensión de DIgSILENT en «Sin proyecto» y «Con proyecto». (RF-15)
      Hecho cuando: una prueba con el doble de DIgSILENT crea el gráfico del alimentador en cada caso.
      Hecho: `casos_pf.grafico_perfil`, en «Sin proyecto» y «Con proyecto»; `pytest -q tests/test_casos_pf.py -k grafico`.
      Antes (2026-11-06): la referencia de Python de PowerFactory 2024 da la clase `VisPath` y sus escalas, pero no el
      atributo con que se liga al alimentador; se averigua con una sonda en un proyecto de prueba (T10) antes de escribir
      el doble.
- [x] T10. [DIgSILENT] Sonda en un proyecto de prueba de la sesión: crear con `GrpPage.GetOrInsertPlot(…, 'VisPath', 1)`
      el perfil de un alimentador y leer qué atributo lo liga a su `ElmFeeder`. (RF-15)
      Hecho cuando: el atributo y su valor quedan anotados en esta tarea, y el proyecto de prueba, sin la página.
      Hecho el 2026-11-06 en `20261106-065905_CSG_TXT_PRUEBA_007` («Sin proyecto», TM105): en modo motor
      `GetGraphicsBoard()` da None; el escritorio es el `SetDesktop` «Desktop» del caso. `SetVipage.GetOrInsertPlot(…,
      'VisPath', 1)` da None y en un `GrpPage` falla («method call failed»); `CreateObject('VisPath', nombre)` en una
      `SetVipage` sí lo crea. Se liga con `feeder = [ElmFeeder]` (lista vacía al crear; leído de vuelta, TM105.ElmFeeder);
      `iopt_x` es 0 (distancia). Las páginas de la sonda se borraron; el proyecto quedó con su única página PRUEBA_007.
- [x] T5. [DIgSILENT] AL209 recalibrado desde la web, con su perfil y los bancos propuestos desde él. (Todos)
      Hecho cuando: la recalibración guarda el perfil, la web lo dibuja en el navegador real con su límite y «Con proyecto»
      aplica los bancos del perfil, confirmados en DIgSILENT.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
