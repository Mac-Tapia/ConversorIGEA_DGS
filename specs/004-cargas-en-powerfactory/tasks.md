# Tareas — Spec 004

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde y `- [x]`.

- [x] T1. `igea_dgs/cargas_pf.py`: lee los libros de demandas y de cargas nuevas sin
      modelo, valida cada fila, pasa coordenadas a WGS84 y arma el plan. (RF-1, RF-5)
      Hecho cuando: pruebas con libros sorteados de varios alimentadores, sin dataset.
      Hecho el 2026-10-08 (`tests/test_cargas_pf.py`). Una fila con error se informa y no
      impide las demás. Carga nueva: `barra`, `Lat`/`Lon` o `CoordX`/`CoordY` con el CRS
      del perfil; columnas nuevas `alimentador`, `tipo_linea` y `tension_bt_kv`.
- [ ] T2. `tools/cargas_pf.py`, actualización de demandas: variación nueva con nombre
      libre, coincidencia en el alimentador, omitidas y ambiguas, escritura por modo
      con signo de Q y relectura. (RF-3, RF-4, RF-6 a RF-9, RF-21)
      Hecho cuando: pruebas con DIgSILENT simulado en verde.
- [ ] T3. `tools/cargas_pf.py`, carga nueva: barra por nombre o por GPS, tipo de línea,
      tensiones y frecuencia, carga escrita como demanda, dibujo, ya existente, no
      conectable. (RF-10 a RF-16)
      Hecho cuando: pruebas con DIgSILENT simulado en verde.
- [ ] T4. Simular, flujo final, informe y cancelación entre alimentadores
      (`run_process(cancel_file=)`). (RF-17 a RF-20)
      Hecho cuando: pruebas del guion y de `JobContext` en verde.
- [ ] T5. Web: servicios y rutas sin entradas cargadas; se retiran las rutas por
      alimentador. (RF-1, RF-2, RF-5, RF-17)
      Hecho cuando: pruebas de API con un espacio sin entradas en verde.
- [ ] T6. Front: una pestaña «Cargas en DIgSILENT» con simular y aplicar; fuera
      `LoadsTab` y `NewSedTab`. (RF-2, RF-17, RF-20)
      Hecho cuando: `tsc` y `build` correctos y prueba de contrato en verde.
- [ ] T7. Limpieza: retirar los tres guiones viejos y lo que solo ellos usaban. (P5)
      Hecho cuando: ninguna referencia a ellos y suite en verde.
- [ ] T8. Validación: RF-1 a RF-21 citados, suite completa en verde, RF-14 de la 001
      igual; prueba real en DIgSILENT a cargo del usuario.
