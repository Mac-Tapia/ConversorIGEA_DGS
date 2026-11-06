# Tareas 094

Lee: `specs/094-perfil-de-tension-y-bancos/spec.md` y `plan.md`.

- [x] T1. `perfil_tension.py`: perfil, ubicaciones por reglas, separación y bancos hasta el objetivo. (RF-1, RF-4, RF-6, RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_perfil_tension.py` en verde.
- [x] T2. El perfil en el informe de la calibración y guardado con ella. (RF-1, RF-2, RF-10, RF-11, RF-12)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_perfil_tension.py` en verde.
- [x] T3. La escalera, el déficit previo y el sistema usan las ubicaciones del perfil. (RF-4, RF-5, RF-7)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py tests/test_seleccion_por_oraculo.py` en verde.
- [ ] T4. El perfil en la web y en el informe del estudio. (RF-3)
      Hecho cuando: `npm --prefix frontend run build` sin errores, la web probada en el navegador y `pytest -q tests/test_informe_web.py` en verde.
- [x] T8. Bancos solo en la troncal y en las troncales de los ramales largos; camino sin ciclos. (RF-16, RF-17)
      Hecho cuando: `pytest -q tests/test_perfil_tension.py tests/test_optimizacion_oraculo.py tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T9. La variante de bancos según el perfil manda si cumple en DIgSILENT. (RF-18)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py` en verde.
- [ ] T6. El perfil completo antes y después de cada propuesta, con su comparación. (RF-13, RF-14)
      Hecho cuando: `pytest -q tests/test_perfil_tension.py tests/test_optimizacion_oraculo.py` en verde.
- [ ] T7. El gráfico de perfil de tensión de DIgSILENT en «Sin proyecto» y «Con proyecto». (RF-15)
      Hecho cuando: una prueba con el doble de DIgSILENT crea el gráfico del alimentador en cada caso.
- [ ] T5. [DIgSILENT] AL209 recalibrado desde la web, con su perfil y los bancos propuestos desde él. (Todos)
      Hecho cuando: la recalibración guarda el perfil y «Con proyecto» aplica los bancos del perfil, confirmados en DIgSILENT.
