# Tareas — Spec 105

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Detección del mes copiado e indicadores mensuales en el dominio. (RF-4 a RF-11, RF-13, RF-14, RF-37)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_evolucion_clientes_fijos.py` en verde.
- [x] T2. Lectura con los lectores del pronóstico, clientes por radial, renumeración, calidad y cabecera. (RF-1 a RF-4,
      RF-12, RF-15, RF-16)
      Hecho cuando: `tests/test_evolucion_clientes_fijos.py` en verde.
- [x] T3. Conciliación de fuentes, cadenas de renumeración, propuestas y fijos sobre la cabecera. (RF-34 a RF-38)
      Hecho cuando: `tests/test_evolucion_clientes_fijos.py` (105:RF-34 a RF-38) en verde.
- [x] T4. Libro Excel con sus hojas y gráficos. (RF-27)
      Hecho cuando: `tests/test_evolucion_clientes_fijos.py::test_libro_excel_con_sus_hojas_y_graficos` en verde.
- [x] T5. Archivo de informes: configuración, copia por temporal con reintentos, sin pisar. (RF-28 a RF-33)
      Hecho cuando: las pruebas de archivo de `tests/test_evolucion_clientes_fijos.py` y `tests/test_evolucion_fijas_web.py`
      en verde.
- [x] T6. Trabajo, rutas y contrato de la API. (RF-17 a RF-20)
      Hecho cuando: `tests/test_evolucion_fijas_web.py` en verde y `python tools/generar_contrato_api.py --check` sin
      deriva.
- [x] T7. Pestaña, tablero, buscador y tarjeta de archivo en la web. (RF-21 a RF-26, RF-29, RF-39)
      Hecho cuando: `npm run lint`, `npx tsc --noEmit -p .`, `npm test` y `npm run build` en verde en `frontend/`.
- [x] T8. Comprobación real y navegador: AL209 de enero a octubre de 2026 da las cifras del libro hecho a mano, otro
      alimentador con clientes fijos funciona y la pestaña se recorre en la web propia. (RF-1 a RF-39)
      Hecho cuando: el informe de la entrega trae las cifras y el recorrido, sin datos de la distribuidora en git.
      Hecho el 2026-11-12: AL209 sin ninguna diferencia frente al libro hecho a mano (404 231 celdas), NA205 y CA101
      calculados, y la pestaña recorrida en la web propia del puerto 8790 (cifras en el informe de la entrega).
- [x] T9. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "105:RF-[0-9]+" tests frontend/test | sort -u` lista los 39 RF.
- [x] T10. El archivo reemplaza el mismo fichero por su versión vigente y no toca los demás. (RF-40)
      Hecho cuando: `pytest -q tests/test_evolucion_clientes_fijos.py -k archivar` (105:RF-40) en verde.
