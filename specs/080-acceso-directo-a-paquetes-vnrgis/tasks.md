# Tareas — Spec 080

- [x] T1. Descubrimiento de ciclos, clasificación por sección y vigente por empresa. (RF-1, RF-2, RF-3, RF-4, RF-5, RF-6, RF-7, RF-8, RF-9, RF-10)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_vnr_etl.py` en verde y, contra el portal real, salen Electro Sur Este y Luz del Sur con su resolución vigente.
- [x] T2. Extraer la copia del paquete y asignarla; extractor de RAR fuera del PATH. (RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_vnr_official_web.py` en verde.
- [x] T3. La entrada VNR-GIS de la web, por distribuidora. (RF-11, RF-12, RF-13, RF-14, RF-15, RF-16, RF-17)
      Hecho cuando: `npx tsc --noEmit -p frontend` y `npm run build` correctos, y las pruebas de API en verde.
- [x] T5. El motor puede abrir la copia custodiada de una empresa nueva. (RF-25, RF-26)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_vnr_sqlserver.py` en verde y la carga real de Electro Sur Este, base nunca restaurada, pasa de RESTORE.
- [x] T6. Ninguna salida con red se pierde y cada alimentador conserva su nombre. (RF-27, RF-28, RF-32, RF-33)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_vnr_sqlserver.py` en verde y la suite completa sin nombres cambiados en la fuente TXT.
- [x] T8. El CRS que declara la propia fuente. (RF-34)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py` en verde y `TI01` convierte por la web sin pedir CRS.
- [x] T7. Herramienta de cruce de la totalidad. (RF-29, RF-30, RF-31)
      Hecho cuando: `tools/validar_totalidad_vnr.py` da OK con Electro Sur Este y con Luz del Sur cargadas por la web.
- [x] T9. Celdas, derivaciones, kvar de los bancos y aviso de lo no modelado. (RF-35, RF-36, RF-37)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_vnr_sqlserver.py` en verde.
- [x] T10. Reguladores hasta el DGS; pararrayos y seccionadores cerrados fuera. (RF-38, RF-39, RF-40, RF-41)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py` en verde y un alimentador con `BR` importa en DIgSILENT con su regulador.
- [x] T11. Demanda proporcional de relleno, factor sin tensiones imposibles, toda carga de `Sed` como SED y reducción por igual. (RF-42, RF-43, RF-44, RF-45)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py` en verde y `TI01` pasa la verificación previa.
- [x] T12. Códigos operativos de las SED y reguladores en el recuento esperado. (RF-46, RF-47, RF-48)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py` en verde y `TI01` y `C+æ02` en DIgSILENT con sus SED por código operativo y `equipment_pass` verdadero.
- [x] T13. Un catálogo por empresa, con semilla sin datos de ninguna, y reguladores a 60 Hz. (RF-49, RF-50, RF-51, RF-52)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_catalogo_crece.py` en verde y `TI01` y `C+æ02` en DIgSILENT sin filas de otra empresa en su catálogo.
- [x] T4. Prueba en el navegador real con el portal real. (Todos)
      Hecho cuando: en el navegador, Electro Sur Este queda con `ELSE_VNR_22_REC.bak` asignada y su carga lista sus alimentadores, y Luz del Sur muestra su paquete de la RCD 184-2026.
