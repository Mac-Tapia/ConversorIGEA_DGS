# Tareas — Spec 004

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde y `- [x]`.

- [x] T1. `convertersmartgrid/cargas_pf.py`: lee los libros de demandas y de cargas nuevas sin
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
- [x] T9. `convertersmartgrid/demanda_medida.py`, cabecera: medidores por alimentador, índice de
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
      Hecho cuando: pruebas sintéticas en verde y, con `CSG_DEMANDA_DIR`, con los reales.
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
- [x] T13. Cabecera de un medidor partido en canales: completar kVAR y kVA por la fecha
      del kW máximo desde las hojas de una magnitud del medidor o de sus hermanas, y unir
      el canal sin hoja con el medidor que ya lo da. (RF-44, RF-45)
      Hecho cuando: `pytest tests/test_demanda_medida.py` en verde y, con
      `CSG_DEMANDA_DIR`, IN191 de Ica sale con kW y kVAR en una sola fila.
- [x] T8. Validación: RF-1 a RF-41 citados, suite completa en verde, RF-14 de la 001
      igual; prueba real en DIgSILENT a cargo del usuario.
      2026-10-09: RF-1 a RF-41 citados; suite completa con las cinco variables `CSG_*` y
      `CSG_DEMANDA_DIR` en verde (948 correctas, 18 omitidas). Falta la prueba real en
      DIgSILENT.
      Hecho cuando: `grep -rnoE "004:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-41 y la suite completa, en verde.
- [x] T14. Demandas también en el escenario de operación: en el del caso en que se escriben
      y, con los tres casos de la 011, en los de «Sin proyecto» y «Con proyecto», no en el
      del «Caso base». El doble imita que el escenario manda (`app.escenario_manda`).
      (RF-54, RF-55)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion.py tests/test_casos_pf.py` en verde.
      Hecho el 2026-10-12. Falta comprobarlo en DIgSILENT: una demanda en bloque se ve en la
      cabecera con el escenario activo.
- [x] T15. Descubrimiento universal del libro de suministros por contenido, con selección
      automática no bloqueante entre varios candidatos, opción explícita y una sola regla
      compartida por núcleo, API, interfaz y `tools/sistema_web.py`. (RF-58 a RF-61)
      Hecho cuando: las pruebas sintéticas con nombres arbitrarios y múltiples candidatos,
      las pruebas de API, el front, Ruff y la suite completa con datos reales están en verde.
      Hecho el 2026-10-21: suite con las siete variables, 2469 pasan, ninguna omitida.
- [x] T16. Cada libro en su hueco: los de clientes importantes (hoja «resumen» con código
      de cliente) fuera de los candidatos de suministros, con aviso en el hueco; sin ningún
      libro de suministros el hueco se guarda sin elección, sin rechazar; en el índice de
      clientes, un libro sin «resumen» no se activa. (RF-62 a RF-65)
      Hecho cuando: pruebas sintéticas y de API en verde, `tsc` y `build` correctos, y con
      `CSG_DEMANDA_DIR` la carpeta de clientes no da candidatos de suministros.
      Hecho el 2026-10-22: `referencia/4.-clientesimportantes` da 0 candidatos (5 libros de
      clientes avisados) y `3.-suministrocliente` elige «0926 Clientes_spl.xlsx».
- [x] T17. Reactiva de las fijas en el registro de su POT: `registros_de_maxima` (hoja
      «maestro_lib» → hoja de 15 minutos del cliente), `q_registro_kvar` y `fecha_registro`
      en el cruce, `fijas_de` con el ERI × 4 de ese registro y sin el FP mínimo, columnas en
      la web y en el Excel. (RF-66)
      Hecho cuando: `pytest -q tests/test_demanda_medida.py tests/test_central_termica_front.py`
      en verde y, con el libro real de julio de 2026, cada cliente cruzado con su registro.
      Hecho el 2026-10-28: 12 de 12 clientes del libro de julio con su registro (0,2 s); FP del
      registro frente al del mes, de 0,769 a 0,956 en 700096086.
- [x] T18. Retro (033, 2026-10-29): RF-42, RF-43, RF-46 a RF-53, RF-56, RF-57, RF-67, añadidos a la spec como cambio después de
      escribir las tareas e implementados con su prueba sin tarea propia. (RF-42, RF-43, RF-46 a RF-53, RF-56, RF-57, RF-67)
      Hecho cuando: las pruebas que los citan pasan (pruebas de `tests/test_demanda_medida*.py`, `tests/test_cargas_pf*.py`, `tests/test_cargas_tres_pasos_front.py` y `tests/test_central_termica_front.py`).
- [x] T19. Transformador de ficha para las cargas nuevas: `CargaNueva.kva_deducido`,
      `transformador_de_ficha` en `tools/cargas_pf.py` con `trafos_sed.proponer` y el tipo con la
      ficha del perfil, `ntnum` con las unidades. (RF-68, RF-69)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py tests/test_cargas_pf_guion.py` en verde.
- [x] T20. [DIgSILENT] PE192 con las cargas CH_13 y CH_22 aplicadas de nuevo por la web: sus
      transformadores con ficha y la máxima ≤ 80 % en «Con proyecto». (RF-68, RF-69)
      Hecho cuando: el estudio 4.2 de «Con proyecto» no tiene ningún transformador de carga
      nueva por encima del 80 %.
      Hecho el 2026-11-08 en `20261103-142909_CSG_TXT_PE192` (espacio 3c689e86ecbf4e49), sobre 743e4506: cargas
      del libro `NuevosclientesMayoresv3.xlsx` y «Con proyecto» por `tools/sistema_web.py` (trabajo 121a05dd0dc3,
      refuerzo de 2 tramos, 0,43 km; 19 órdenes, ninguna fallida) y 4.2 por la web (plan b876d84c4a11, trabajo
      05e7ff56127c, `estudios_resultados_b876d84c4a11.csv`). TR_CH_13, creado con la ficha y a la tensión mínima
      (T21): 64,2 %. TR_CH_22 al 81,07 %: no se creó, se reutilizó la variación del vivero del 2026-11-06
      (014:RF-24), con el trafo de 315 kVA de la regla anterior; el usuario lo acepta así (2026-11-08) y no se
      redimensiona.
- [x] T21. La demanda del transformador de una carga nueva, a la tensión mínima de los estudios. (RF-68)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion.py -k ficha` en verde.
- [x] T22. El FP del perfil para las cargas nuevas que solo traen kW, con su aviso. (RF-70)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py -k fp_del_perfil` en verde.
- [x] T23. El nombre del cliente de la tabla cruzada, del libro de suministros cuando el libro mensual no lo trae. (RF-71)
      Hecho cuando: `pytest -q tests/test_demanda_medida.py -k nombre` (004:RF-71) en verde.
- [x] T24. Ubicación de la carga nueva frente a su alimentador, en la web: `ZonaAlimentador` y `verificar_ubicaciones`
      en `cargas_pf.py` (radio del alimentador, tope del perfil, propuesta de un dígito, X/Y y Lat/Lon intercambiadas),
      la geografía del DGS aceptado en `services.cargas_plan` y la clave `cargas_nuevas.distancia_max_al_nodo_m` del
      perfil. (RF-72, RF-73, RF-74)
      Hecho cuando: `pytest -q tests/test_cargas_pf_ubicacion.py` en verde.
- [x] T25. La misma comprobación en el guion sin geografía, la carga reemplazada si cambió y la longitud de la línea
      de conexión con su aviso, con el doble de DIgSILENT. (RF-75, RF-76, RF-77, RF-78, RF-79)
      Hecho cuando: `pytest -q tests/test_cargas_pf_ubicacion.py tests/test_cargas_pf_guion.py` en verde.
- [x] T26. La web: el error con su propuesta junto a la fila y la distancia y la línea tras simular o aplicar. (RF-80)
      Hecho cuando: `npm test`, `npx tsc --noEmit -p .` y `npm run build` en `frontend/` en verde, y
      `pytest -q tests/test_cargas_pf_ubicacion.py -k web` en verde.
- [x] T27. `tools/pfd_diagnostico.py`: importa un `.pfd` con `ComPfdimport` en un proyecto nuevo de la carpeta, por su
      huella (reutilizar, avisar si cambió, reimportar con sufijo, versión nueva y qué cambió), y lo diagnostica en solo
      lectura: redes y alimentadores, casos con escenario, variaciones y hora, escenarios, variaciones y etapas con lo
      que dan de alta, de baja o cambian y dónde se estudian, cargas por caso con totales y diferencias, recuento por
      clase y tipos, aviso de exportación reducida, JSON e informe aunque reviente y restauración del proyecto y el
      caso activos; con el doble `tests/fake_pf.py`. (RF-81, RF-82, RF-83, RF-84, RF-85, RF-86, RF-87, RF-88,
      RF-89, RF-90, RF-91, RF-92, RF-93, RF-94, RF-95, RF-96, RF-97, RF-98, RF-99, RF-100, RF-101, RF-102)
      Hecho cuando: `pytest -q tests/test_pfd_diagnostico.py tests/test_pf_servidor.py tests/test_compat_python39.py`
      en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_compat_python39.py tests/test_pf_servidor.py tests/test_pfd_diagnostico.py.
- [x] T28. Vínculo del proyecto con los ficheros de su expediente por su contenido, con la evidencia de cada vínculo,
      reutilizando `pide_dataset.py` y el lector común de libros; sus RF entran con la tarea (texto acordado en
      `plan.md`). (RF-109, RF-110)
      Hecho cuando: las pruebas sintéticas de vínculos están en verde.
      Código (2026-11-16, f7): `src/convertersmartgrid/adaptadores/pfd_vinculos.py` y `tests/test_pfd_vinculos.py`.
      Hecho en 016498fc (LOTE-1); pruebas: tests/test_pfd_vinculos.py.
- [x] T29. La web: subir el `.pfd`, el trabajo en el carril `powerfactory` y el informe del diagnóstico; sus RF entran
      con la tarea (texto acordado en `plan.md`).
      Hecho cuando: `pytest -q tests/test_web_api.py`, `npx tsc --noEmit -p .` y `npm run build` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_web_api.py.
- [x] T30. [DIgSILENT] Prueba real con el usuario: importar desde la web dos `.pfd` reales de prueba y revisar el
      diagnóstico de sus casos, escenarios, cargas, proyectos nuevos y vínculos. (RF-81 a RF-107)
      Hecho cuando: el usuario lo acepta en DIgSILENT.
      Nota del 2026-11-20 (bloque DIgSILENT de d8): los dos `.pfd` de prueba se diagnosticaron con el guion (rc=0;
      evidencia en `D:/csg/PM_IMPL/DIG_BLOQUE/50_pfd_004T30/`); la web no tenía la ruta (la pone T36) y los avisos se
      repetían (T35). Falta repetirlo desde la web con T35 y T36 integradas.
      Hecho el 2026-11-22: repetido desde la web en navegador real (Chromium, `T30_pfd/pfd_web.mjs` del bloque
      D:/csg/PM_IMPL/DIG_BLOQUE2/) en un espacio de prueba nuevo con la carpeta de pruebas: los dos `.pfd` de prueba de
      transmisión, reconocidos por su sha256 y reutilizados (RF-101), dan 142 casos, 184 escenarios, 556 variaciones, 9
      redes y 0 alimentadores con 13 avisos, y 54 casos, 96 escenarios, 405 variaciones y 0 alimentadores con 12 avisos,
      cada uno con su informe descargable (`pantalla_1.txt`, `pantalla_2.txt`, `trabajos.json` y capturas). El usuario
      lo aceptó el mismo día.
- [x] T31. El proyecto de la versión anterior de un `.pfd` se renombra con «_anterior_<sha10>_<AAAAMMDD-HHMMSS>» y se
      conserva; el nuevo toma el nombre base; si el anterior está activo se desactiva antes y se dice; el informe nombra
      los dos; con el doble `tests/fake_pf.py`. (RF-101, RF-103, RF-104, RF-105, RF-106, RF-107)
      Hecho cuando: `pytest -q tests/test_pfd_diagnostico.py -k "version or anterior"` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_pfd_diagnostico.py -k version or anterior.
- [x] T32. La búsqueda de máximas con la memoria acotada: `Cabecera` guarda los nombres de las hojas y cierra el libro
      usado hace más tiempo cuando no cabe en `LIBROS_ABIERTOS_MAX_BYTES`, `maximas` lee los medidores agrupados por
      libro y devuelve el orden pedido, y la curva y las tensiones de cada resultado son `CurvaMedida` y
      `TensionesMedidas`. (RF-108)
      Hecho cuando: `pytest -q tests/test_demanda_medida.py -k "memoria or compactas or abiertos"` (004:RF-108) en verde.
- [x] T33. MEJ10-FIJAS (orden del usuario del 20-11): `factores_de_medidor` y `fm_cambiados` en `aplicacion/demanda_medida.py`; la web avisa `FM_CAMBIADO` en la fila del cliente de la tabla cruzada (`_fm_cambiados`, `_anotar_medidor`). (RF-111)
      Hecho cuando: rojo por aserción sobre 2f9de358 y verde con `tests/test_demanda_medida.py -k rf111`; la corrida en DIgSILENT la decide d8.
      Hecho el 2026-11-20 (d8, cierre de la fila gSIG por orden del usuario «nada abierto»): rojo D:/csg/PM_IMPL/MEJ10_FIJAS/rojo.log (16 F por aserción sobre 2f9de358, con test_004_rf111_fm_cambiado_con_el_salto_de_su_energia);
      verde D:/csg/PM_IMPL/MEJ10_FIJAS/verde_py.log (665 passed); verde integrado del hueco de MEJ567 sobre c4326366 (D:/csg/PM_IMPL/MEJ567/verde_20261120_163024.log, 2423 passed, rc=0;
      npm_test_20261120_163024.log y e2e_20261120_163024.log) y la puerta gSIG que integra esta casilla (0 fallidas, 0 omitidas).
- [x] T34. MEJ11-MAXIMA (orden del usuario del 20-11): `maxima_de_registros` con la máxima sostenida de una hora, el pico
      de 15 minutos, el promedio sin ceros ni vacíos y el factor de carga; las ventanas en `instante_coincidente`,
      `maxima_de_barra`, `valor_de_barra_en` e `instante_de_barras_de_alta`; la tabla de 2.2 con cada dato en su columna
      (`frontend/src/features/powerfactory/tablaMaxima.ts`). (RF-112, RF-113, RF-114, RF-115, RF-116)
      Hecho cuando: rojo por aserción sobre d6582a8e y verde con `pytest -q tests/test_maxima_sostenida.py` y
      `node --test test/tablaMaxima.test.mjs`; la revisión con datos reales en el navegador y en DIgSILENT la decide d8.
      Hecho el 2026-11-20 (d8, cierre de la fila gSIG por orden del usuario «nada abierto»): rojo D:/csg/PM_IMPL/MEJ11_MAXIMA/rojo_py.log (14 F) y rojo_front.log (5 F) sobre d6582a8e; verde
      D:/csg/PM_IMPL/MEJ11_MAXIMA/verde_npm_test.log (334 pass, 0 fail); verde integrado del hueco de MEJ567 sobre c4326366 (D:/csg/PM_IMPL/MEJ567/verde_20261120_163024.log, 2423 passed, rc=0;
      npm_test_20261120_163024.log y e2e_20261120_163024.log) y la puerta gSIG que integra esta casilla (0 fallidas, 0 omitidas).
- [x] T35. MEJ23 Avisos del `.pfd` agrupados (orden del 20-11): `agrupar_avisos`, `etiqueta_de_caso` y el empate de
      etapas por la ruta del caso en `_completar` de `tools/pfd_diagnostico.py`; `avisos_agrupados` y
      `etapas_empatadas` en el JSON y «(×n)» en el informe de texto. (RF-117)
      Hecho cuando: rojo por aserción sobre dac543a5 + MEJ20 y verde con `pytest -q tests/test_pfd_diagnostico.py`.
      Hecho el 2026-11-21 (MEJ23, código): rojo por aserción D:/csg/PM_IMPL/MEJ23_PFD/rojo.log y verde D:/csg/PM_IMPL/MEJ23_PFD/verde_nucleo.log,
      verde_vecinas.log, tsc.log, npm_test.log y build.log (ESTADO.txt: 0 F, 0 omitidas).
- [x] T36. MEJ23 Importar el `.pfd` desde la web (orden del 20-11; la ruta que T29 daba por hecha):
      `POST /api/workspaces/{wid}/pf/pfd`, `services.nombre_del_pfd`, `pfd_importar` y `pfd_resumen`, y
      `frontend/src/features/powerfactory/ImportarPfd.tsx` en el paso 1 de «Cargas en DIgSILENT». (RF-118)
      Hecho cuando: rojo por aserción y verde con `pytest -q tests/test_pfd_web.py tests/test_web_api.py`, `npm test`,
      `npx tsc --noEmit -p .` y `npm run build`; la prueba con dos `.pfd` desde la web es la T30.
      Hecho el 2026-11-21 (MEJ23, código): rojo por aserción D:/csg/PM_IMPL/MEJ23_PFD/rojo.log y verde D:/csg/PM_IMPL/MEJ23_PFD/verde_nucleo.log,
      verde_vecinas.log, tsc.log, npm_test.log y build.log (ESTADO.txt: 0 F, 0 omitidas);
      la prueba con los dos `.pfd` desde la web es la T30 [DIgSILENT].
- [x] T37. Los vínculos del expediente en la importación del `.pfd` desde la web (auditoría D.3: el módulo de la T28 no lo
      llamaba ningún flujo). (RF-109, RF-110)
      Hecho cuando: `tests/test_pfd_vinculos_web.py` (004:RF-109) en verde, `npx tsc --noEmit -p .` y el contrato de la API
      sin deriva (`tools/generar_contrato_api.py --check`).
      Código, 2026-11-24 (d8, N12): `pfd_vinculos_del_expediente` en `services.py`, el campo `expediente` de
      `POST …/pf/pfd` (solo en local, 400 si la carpeta no existe), `ImportarPfd.tsx` con la carpeta y los vínculos, y
      el contrato regenerado (`tsc` y `--check` en verde).
      Verde, 2026-11-24 12:10 (d8): D:/csg/PM_IMPL/N12/pytest.log, 236 passed con tests/test_pfd_vinculos_web.py,
      tests/test_adaptador_pnl.py, test_contrato_api, test_capas, test_inventario y test_matriz_operaciones (los dos
      fallos del registro son los de la spec cumplida con esta tarea abierta, que se cierra aquí).
- [x] T38. La demanda con su llamada de nota, y la cabecera sin demanda dicha una vez. (RF-51)
      Hecho cuando: «DEM PROY (KW)2» es la demanda y una hoja sin columna de demanda da un solo error con su cabecera.
      Cerrada el 2026-11-25: rojo válido por aserción (2 failed) y verde (113 passed) en `tests/test_cargas_pf.py`;
      el libro real de cargas nuevas pasa de 104 errores a 104 cargas leídas y ninguno.
