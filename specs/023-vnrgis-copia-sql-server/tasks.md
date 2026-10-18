# Tareas — Spec 023

- [x] T1. Explorar la copia real: restaurar `ELDU_VNR_24_APR.bak` en `.\SQLEXPRESS` y listar
      su esquema (sin valores). (duda abierta)
      Hecho cuando: el esquema está en el plan. 2026-10-18: 75 tablas, ver plan.
- [x] T2. `sqlserver_vnr.py` (restauración): huella, cabecera, restauración con `WITH MOVE`, reutilizar, error
      sin motor, `ConfigBD.config`. (RF-2 a RF-6)
      Hecho cuando: pruebas con el doble del motor en verde.
- [x] T3. `sqlserver_vnr.py`: tablas por campos y modelo canónico de un alimentador con su
      geometría y su CRS. (RF-7, RF-8, RF-10)
      Hecho cuando: pruebas sintéticas en verde.
- [x] T4. Fuente VNR con `.bak` en el adaptador, la web y el CLI. (RF-1, RF-9)
      Hecho cuando: pruebas de la API y del CLI en verde; `CODIGO_FUENTE.md` al día.
- [x] T5. Real: un alimentador de la copia de Electro Dunas convertido, validado e importado
      en DIgSILENT. (todos)
      Hecho cuando: el DGS pasa validación e inventario y el flujo converge.
      2026-10-18: IN111 desde ELDU_VNR_24_APR.bak importado en «VNR_BAK_IN111»: «Caso base»
      VERIFICADO (GPS, trazado, conectividad, diagrama, capacidades, flujo), flujo converge;
      699/699 tramos, 694 nodos, 364 cargas, 274 SED, 95 maniobras, 4 bancos y 1 483 puntos
      intermedios iguales en DIgSILENT; GPS en 968/968 barras y 699/699 tramos, curvas del
      diagrama iguales al mapa (máx. 0,96 m). Arreglado: tipos con la letra de tensión y sus
      fichas del catálogo, y la aceptación con la API buscada en la instalación (019:RF-16).
- [x] T6. Validación RF por RF y suite completa sin omitidas. (todos)
      2026-10-18: RF-1 a RF-10 citados por sus pruebas; suite con las siete variables y
      `-rs`: 2450 pasan, ninguna omitida (línea base 001 regenerada con el catálogo de fichas).
      Sistema Ica desde la copia: «Caso base» VERIFICADO tras corregir la aceptación.
