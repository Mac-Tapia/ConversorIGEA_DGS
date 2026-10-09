# Tareas — Spec 004

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde y `- [x]`.

- [x] T1. `igea_dgs/cargas_pf.py`: lee los libros de demandas y de cargas nuevas sin
      modelo, valida cada fila, pasa coordenadas a WGS84 y arma el plan. (RF-1, RF-5)
      Hecho cuando: pruebas con libros sorteados de varios alimentadores, sin dataset.
      Hecho el 2026-10-08 (`tests/test_cargas_pf.py`). Una fila con error se informa y no
      impide las demás. Carga nueva: `barra`, `Lat`/`Lon` o `CoordX`/`CoordY` con el CRS
      del perfil; columnas nuevas `alimentador`, `tipo_linea` y `tension_bt_kv`.
- [x] T2. `tools/cargas_pf.py`, actualización de demandas: variación nueva con nombre
      libre, coincidencia en el alimentador, omitidas y ambiguas, escritura por modo
      con signo de Q y relectura. (RF-3, RF-4, RF-6 a RF-9, RF-21)
      Hecho cuando: pruebas con DIgSILENT simulado en verde.
      Hecho el 2026-10-09 (`tests/test_cargas_pf_guion.py`, con `tests/fake_pf.py`).
- [x] T3. `tools/cargas_pf.py`, carga nueva: barra por nombre o por GPS, tipo de línea,
      tensiones y frecuencia, carga escrita como demanda, dibujo, ya existente, no
      conectable. (RF-10 a RF-16)
      Hecho cuando: pruebas con DIgSILENT simulado en verde.
      Hecho el 2026-10-09 (`tests/test_cargas_pf_guion.py`).
- [x] T4. Simular, flujo final, informe y cancelación entre alimentadores
      (`run_process(cancel_file=)`). (RF-17 a RF-20)
      Hecho cuando: pruebas del guion y de `JobContext` en verde.
      Hecho el 2026-10-09 (`tests/test_cargas_pf_guion.py`, `tests/test_cargas_pf_web.py`).
- [x] T5. Web: servicios y rutas sin entradas cargadas; se retiran las rutas por
      alimentador. (RF-1, RF-2, RF-5, RF-17)
      Hecho cuando: pruebas de API con un espacio sin entradas en verde.
      Hecho el 2026-10-09 (`tests/test_cargas_pf_web.py`). Rutas `/lote/plan`,
      `/lote/{token}/simular`, `/lote/{token}/apply` y `/cargas/plantilla/{tipo}`.
- [x] T6. Front: una pestaña «Cargas en DIgSILENT» con simular y aplicar; fuera
      `LoadsTab` y `NewSedTab`. (RF-2, RF-17, RF-20)
      Hecho cuando: `tsc` y `build` correctos y prueba de contrato en verde.
      Hecho el 2026-10-09 (`CargasTab.tsx`, `tests/test_cargas_pf_front.py`). La carga del
      formulario va como texto y la valida el mismo lector que el libro.
- [x] T7. Limpieza: retirar los tres guiones viejos y lo que solo ellos usaban. (P5)
      Hecho cuando: ninguna referencia a ellos y suite en verde.
      Hecho el 2026-10-09: fuera los tres guiones, `loads_create.py`, `web/load_batch.py` y
      sus pruebas; `services.proyecto_pf_de` también (el proyecto lo elige el operador).
- [x] T9. `igea_dgs/demanda_medida.py`, cabecera: medidores por alimentador, índice de
      hojas, hoja del medidor (entera o partida), columnas por alias, kW máximo con su
      registro, kVA/FP calculados, medidor no hallado. (RF-22, RF-24 a RF-32)
      Hecho cuando: pruebas con libros sintéticos de columnas sorteadas en verde.
      Hecho el 2026-10-09 (`tests/test_demanda_medida.py`). Visto en los libros reales y
      cubierto: `PF lag/lead mean` en %, pasan a decimal con su signo; `PF sign tot us`
      con valores de más de ±100 no es un FP y se calcula; «Local Time» a veces sin hora
      (se usa «Timestamp»); hoja con el nombre del medidor sin kW y el kW en una parte;
      hojas completas con sufijo (`L-6613_PE`); celdas con dos medidores («A Y B»).
- [x] T10. `demanda_medida.py`, clientes: suministros, resumen en los dos formatos,
      cruce actual → anterior, no cruzados, Excel de salida. (RF-33 a RF-38)
      Hecho cuando: pruebas sintéticas en verde y, con `IGEA_DEMANDA_DIR`, con los reales.
      Hecho el 2026-10-09. Con los reales: 98 de 103 medidores con máxima (los otros 5,
      con motivo); clientes de enero a abril 257 cruzados (107 por el código anterior),
      de mayo a julio 253.
- [x] T11. Web de la demanda medida: libros por subida o ruta (carpeta), medidores,
      cabecera como trabajo cancelable, cruce y descarga. (RF-23, RF-38, RF-39)
      Hecho cuando: pruebas de API en verde.
      Hecho el 2026-10-09 (`tests/test_demanda_medida_web.py`). Rutas `/demanda/…`.
- [x] T12. Front: sección «Demanda medida» en la pestaña de cargas. (RF-40, RF-41)
      Hecho cuando: `tsc`, `build` y prueba de contrato en verde.
      Hecho el 2026-10-09 (`DemandaMedida.tsx`, `tests/test_demanda_medida_front.py`).
- [ ] T8. Validación: RF-1 a RF-41 citados, suite completa en verde, RF-14 de la 001
      igual; prueba real en DIgSILENT a cargo del usuario.
      2026-10-09: RF-1 a RF-41 citados; suite completa con las cinco variables `IGEA_*` y
      `IGEA_DEMANDA_DIR` en verde (948 correctas, 18 omitidas). Falta la prueba real en
      DIgSILENT.
