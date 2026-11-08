# Tareas 099

- [x] T1. Nombre del cliente y última fila del libro en las cargas nuevas, con el mismo punto. (RF-1, RF-2, RF-3, RF-4, RF-6)
      Hecho cuando: `pytest -q tests/test_cargas_duplicadas_cliente.py` en verde.
- [x] T2. La variación de una fila que deja de contar se elimina como 040:RF-6. (RF-5)
      Hecho cuando: `pytest -q tests/test_cargas_duplicadas_cliente.py` en verde.
- [x] T4. La web enseña las filas repetidas al cargar el libro, en el plan de «Cargas en DIgSILENT». (RF-7)
      Hecho cuando: `pytest -q tests/test_cargas_duplicadas_cliente.py` en verde y `npm run build` sin errores.
- [x] T5. Lo repetido sale del plan al cargar el libro y su variación antigua se borra por su nombre o su punto. (RF-8)
      Hecho cuando: `pytest -q tests/test_cargas_duplicadas_cliente.py` en verde.
- [x] T3. [DIgSILENT] Cargas nuevas de CA101 + CHN102 desde la web con `NuevosclientesMayoresv3.xlsx`: CH_23 se crea, CH_20
      no, y su variación del 2026-11-05 se elimina. (RF-1, RF-5)
      Hecho cuando: el informe de la aplicación lo dice y el proyecto lo muestra.
      Hecho el 2026-11-08 en `20261105-124711_CSG_TXT_CA101_CHN102` (espacio 2131c6bc8b924e63): la aplicación
      `cargas_pf_aplicacion_db6ccd406524.json` da CH_20 como duplicada de CH_23 y no la crea, y reutiliza CH_23
      (`Carga_CH_23_CA101_20261107_182645`, creada el 2026-11-07). Relectura del proyecto en DIgSILENT: tres variaciones
      de carga, CH_10, CH_18 y CH_23, ninguna de CH_20.
