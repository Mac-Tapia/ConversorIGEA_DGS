# Tareas — Spec 023

- [x] T1. Explorar la copia real: restaurar `ELDU_VNR_24_APR.bak` en `.\SQLEXPRESS` y listar
      su esquema (sin valores). (duda abierta)
      Hecho cuando: el esquema está en el plan. 2026-10-18: 75 tablas, ver plan.
- [x] T2. `sqlserver_vnr.py` (restauración): huella, cabecera, restauración con `WITH MOVE`, reutilizar, error
      sin motor, `ConfigBD.config`. (RF-2 a RF-6)
      Hecho cuando: pruebas con el doble del motor en verde.
      Ampliación 2026-11-13 (aclaración de RF-4, auditoría c7): solo se reutiliza la base `ONLINE`; en otro estado se
      retira, se restaura con `REPLACE` y se anota. Hecho cuando:
      `tests/test_vnr_sqlserver.py::test_una_base_que_no_esta_en_linea_se_restaura_otra_vez` (023:RF-4) en verde.
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
      Hecho cuando: RF-1 a RF-10 citados y la suite con las siete variables, sin omitidas, en verde.
- [x] T7. Segunda concesionaria: la copia VNR-GIS 2025 de Electro Oriente. (RF-1, RF-9)
      Hecho cuando: `pytest -q tests/test_vnr_sqlserver.py` en verde y la copia se lee entera.
      Hecho el 2026-11-01: `referencia/PIDEELOR/ELOR25_V2/ELOR25_V2` (sin extensión, cabecera
      `TAPE`) vino sin su base de parámetros, y su vista `norEquipoMT` nombra `VNRGISGART`, que no
      existe aquí: tumbaba la lectura. Ahora una tabla o vista ilegible se anota
      (`TABLA_ILEGIBLE`) y se sigue. Resultado con el mismo lector, sin código de la empresa:
      ELOR, 168 salidas, 83 353 tramos, 8 729 cargas, 160 tipos de conductor; anotados
      1 233 huecos con su padre, 282 tramos sin padre unidos, 167 islas unidas, 95 SED sin enlace.
