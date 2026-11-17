# Tareas — Spec 080

- [x] T1. Descubrimiento de ciclos, clasificación por sección y vigente por empresa. (RF-1, RF-2, RF-3, RF-4, RF-5, RF-6, RF-7, RF-8, RF-9, RF-10)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_vnr_etl.py` en verde y, contra el portal real, salen Electro Sur Este y Luz del Sur con su resolución vigente.
- [x] T2. Extraer la copia del paquete y asignarla; extractor de RAR fuera del PATH. (RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_vnr_official_web.py` en verde.
- [ ] T3. La entrada VNR-GIS de la web, por distribuidora, con las puertas A–H que informan sin bloquear. (RF-11, RF-12, RF-13, RF-14, RF-15, RF-16, RF-17, RF-56, RF-57)
      Hecho cuando: `npx tsc --noEmit -p frontend` y `npm run build` correctos, y las pruebas de API en verde. Y `pytest tests/test_vnr_web_adapter.py` en verde: la incidencia de G/H llega al resultado de la carga en la web.
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
- [ ] T13. Un catálogo por empresa, con semilla sin datos de ninguna, reguladores a 60 Hz, y cada tramo aéreo o cable, con su tipo, su estado y la capacitancia de los cables. (RF-49, RF-50, RF-51, RF-52, RF-53, RF-54, RF-55, RF-58)
      Hecho cuando: `pytest tests/test_vnr_accesos_directos.py tests/test_catalogo_crece.py` en verde y dos alimentadores reales de prueba en DIgSILENT sin filas de otra empresa en su catálogo. Y `pytest tests/test_vnr_cymdist_bridge.py tests/test_vnr_web_adapter.py tests/test_catalog_resolution.py tests/test_vnr_etl.py tests/test_vnr_sqlserver.py` en verde, con `comparar_red` vacío de SQL → GeoPackage → capas en tramos MT y BT, nodos, SED y equipos, y un alimentador real en una copia da su `vm_min` antes y después.
- [ ] T14. Índices por salida en la lectura de la copia de SQL Server: ninguna tabla se recorre una vez por salida. (RF-59)
      Hecho cuando: `pytest tests/test_vnr_sqlserver.py -k "no_recorre_las_tablas"` falla antes del cambio (las tablas crecen de 2 a 6 copias) y pasa después, y `pytest tests/test_vnr_sqlserver.py tests/test_vnr_web_adapter.py tests/test_vnr_cymdist_bridge.py` sigue en verde.
- [ ] T15. La red BT se lee por bloques y solo se guarda la de las salidas pedidas: `leer_datos(con_bt=True, salidas=…)` con `_leer_red_bt` y `_por_bloques` (`fetchmany` de `FILAS_POR_BLOQUE`), el resumen en `DatosVnr.resumen_bt` para `_tramos_bt`, la memoria estimada antes de leer (`_avisar_memoria_bt`, `MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE`), y `leer_base_restaurada` pasa las salidas a la lectura. (RF-60)
      Hecho cuando: `pytest tests/test_vnr_sqlserver.py -k "memoria_de_la_red_bt or no_se_lee_entera or avisa_si_su_memoria"` falla por aserción con el código de antes (rojo) y pasa después; `pytest tests/test_vnr_sqlserver.py -k "red_bt"` en verde, con la huella sha256 del modelo igual a la de las tablas enteras; `pytest tests/test_vnr_sqlserver.py tests/test_vnr_web_adapter.py tests/test_vnr_cymdist_bridge.py tests/test_vnr_accesos_directos.py` sigue en verde; y la lectura con `con_bt=True` de una sola empresa, por el carril, da un pico ≤ 2 GB.
- [ ] T16. La exportación a capas en flujo: `capas.exportar_base_a_capas_en_flujo` con la red MT una vez y la BT volcada a disco y escrita por lotes de salidas (`sqlserver_vnr.volcar_red_bt`, `RedBtEnDisco`, `pyogrio.write_arrow`), el CLI `bak-a-capas` y el guion de ensayo (`--flujo`) por ella, y la estimación de memoria y disco con su línea en el registro y en la pantalla. (RF-60)
      Hecho cuando: `pytest tests/test_vnr_sqlserver.py -k "cadena_entera or se_ve_en_el_registro or imprime_la_estimacion"` falla por aserción con el código de antes (rojo) y pasa después; `pytest tests/test_vnr_sqlserver.py -k "en_flujo"` en verde, con el GeoPackage igual tabla a tabla; los vecinos VNR, `test_capas`, `test_trazabilidad_specs` y `test_arquitectura_generada` siguen en verde; y el ensayo de 82 con `--flujo` da, con la empresa entera, ≤ 0,7 GiB en la distribuidora del ensayo y ≤ 2 GB en la base mayor.
- [ ] T17. La red MT en flujo en la exportación a capas: `sqlserver_vnr.volcar_red_mt` y `RedMtEnDisco` (las tablas MT por bloques al SQLite temporal, y el canónico por lotes de salidas con `_canonico_de_la_salida`, la misma función que `modelo_canonico`), y `capas._CapasMtEnDisco` (las capas MT guardadas lote a lote y escritas cada una de una vez). (RF-60)
      Hecho cuando: `pytest tests/test_vnr_sqlserver.py -k "red_mt_de_la_empresa or red_mt_en_flujo_se_lee"` falla por aserción con el código de antes (rojo) y pasa después; `pytest tests/test_vnr_sqlserver.py -k "en_flujo or capas_mt or indices_por_salida"` en verde, con el GeoPackage igual tabla a tabla; los vecinos VNR y las pruebas estructurales siguen en verde; y el ensayo de 82 con `--flujo --sin-via-de-capas` da, con la empresa entera, ≤ 0,7 GiB en la distribuidora del ensayo y ≤ 2 GB en la base mayor.
- [x] T4. Prueba en el navegador real con el portal real. (Todos)
      Hecho cuando: en el navegador, Electro Sur Este queda con `ELSE_VNR_22_REC.bak` asignada y su carga lista sus alimentadores, y Luz del Sur muestra su paquete de la RCD 184-2026.
