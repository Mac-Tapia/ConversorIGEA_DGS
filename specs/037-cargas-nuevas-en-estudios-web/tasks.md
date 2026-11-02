# Tareas — spec 037

- [x] T1. Preparación y resolución del diagnóstico con el año y protección de casos ajenos (RF-2, RF-4, RF-7).
  Hecho cuando: pasan las pruebas de casos y del guion de estudios.
- [x] T2. Ejecutar el diagnóstico entre los otros casos y conservar sus resultados (RF-3, RF-6).
  Hecho cuando: pasan las pruebas web con y sin cargas, y las de CSV.
- [x] T3. Explicar los casos y mostrar las exclusiones del diagnóstico (RF-1, RF-5).
  Hecho cuando: pasan las pruebas de interfaz, trazabilidad, inventario y el build del frontend.
- [x] T5. «Con proyecto» sin obras renovado desde la recalibración de «Sin proyecto» (RF-8).
      Hecho cuando: `pytest -q tests/test_casos_pf.py` en verde, con el caso viejo renombrado y sin marca,
      y uno con obras conservado.
- [ ] T4. [DIgSILENT] Estudios de un proyecto real con cargas nuevas.
  Hecho cuando: el trabajo web y una relectura nativa acreditan los tres casos del año,
  sus escenarios, cargas activas y exclusiones, con los informes conservados.

## Evidencia del 2026-10-29

- Regresión inicial: 7 fallos que reproducían la falta del caso y del año.
- `pytest -q tests/test_casos_pf.py tests/test_casos_por_anio.py tests/test_estudios_pf_guion.py
  tests/test_estudios_pf_web.py tests/test_obras_estudios_front.py tests/test_estudios_pf.py
  tests/test_estudios_red_web.py`: 167 passed, sin omisiones.
- `npm --prefix frontend run build`: TypeScript y Vite correctos.
- `pytest -q tests/test_trazabilidad_specs.py`: 22 passed; los 7 RF de la 037 tienen
  tarea y prueba, y el índice generado coincide con las specs.
- Inventario: sus 57 comprobaciones pasaron en la ejecución conjunta. Los fallos de
  trazabilidad de esa ejecución correspondían a índices en actualización; la ejecución
  independiente posterior de las 22 comprobaciones quedó en verde.
- Servidor actualizado mediante el acceso directo: `/api/health` responde sin trabajos
  activos; el bundle servido contiene la explicación de los tres casos y las exclusiones.
  No se hizo inspección visual: el host de automatización del navegador no está disponible.
- T4 pendiente: las pruebas anteriores usan el doble del motor y no acreditan persistencia
  ni aceptación eléctrica de un proyecto real.
