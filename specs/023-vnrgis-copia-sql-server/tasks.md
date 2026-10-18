# Tareas — Spec 023

- [x] T1. Explorar la copia real: restaurar `ELDU_VNR_24_APR.bak` en `.\SQLEXPRESS` y listar
      su esquema (sin valores). (duda abierta)
      Hecho cuando: el esquema está en el plan. 2026-10-18: 75 tablas, ver plan.
- [x] T2. `sqlserver.py`: huella, cabecera, restauración con `WITH MOVE`, reutilizar, error
      sin motor, `ConfigBD.config`. (RF-2 a RF-6)
      Hecho cuando: pruebas con el doble del motor en verde.
- [x] T3. `sqlserver_vnr.py`: tablas por campos y modelo canónico de un alimentador con su
      geometría y su CRS. (RF-7, RF-8, RF-10)
      Hecho cuando: pruebas sintéticas en verde.
- [x] T4. Fuente VNR con `.bak` en el adaptador, la web y el CLI. (RF-1, RF-9)
      Hecho cuando: pruebas de la API y del CLI en verde; `CODIGO_FUENTE.md` al día.
- [ ] T5. Real: un alimentador de la copia de Electro Dunas convertido, validado e importado
      en DIgSILENT. (todos)
      Hecho cuando: el DGS pasa validación e inventario y el flujo converge.
- [ ] T6. Validación RF por RF y suite completa sin omitidas. (todos)
