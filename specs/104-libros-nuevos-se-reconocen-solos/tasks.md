# Tareas — Spec 104

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Mes de los libros con la carpeta del año elegida, el año de sus fechas y el aviso sin mes. (RF-27, RF-28, RF-29)
      Hecho cuando: `tests/test_libros_nuevos.py -k "mes or carpeta"` falla sin el arreglo y pasa con él.
- [x] T2. Foto, cambios y verificación de un libro de clientes y de cabecera, con su aviso. (RF-1, RF-3, RF-7 a RF-15,
      RF-17, RF-18, RF-20)
      Hecho cuando: `tests/test_libros_nuevos.py` en verde.
- [x] T3. Vigilancia en la web: arranque, apertura, intervalo, motor ocupado, reindexado, aviso, visto y libro repetido
      inactivo. (RF-1 a RF-6, RF-16, RF-19 a RF-21)
      Hecho cuando: `tests/test_libros_nuevos_web.py` en verde.
- [x] T4. Dataset desactualizado, regenerado sin entrenar, con su perfil; el libro repetido, apartado también fuera de la
      web. (RF-22 a RF-26)
      Hecho cuando: `tests/test_libros_nuevos.py -k "dataset or perfil"` y `tests/test_libros_nuevos_web.py -k dataset`
      en verde.
- [x] T5. Aviso en la web, contrato de la API e índices del repositorio. (RF-20, RF-21)
      Hecho cuando: `npm run lint`, `npx tsc --noEmit -p .`, `npm test`, `npm run build`,
      `tools/generar_contrato_api.py --check` y `tests/test_inventario.py` en verde.
- [x] T6. Con la web real arrancada por el operador, el libro nuevo aparece reconocido en el aviso del espacio sin pulsar
      nada, y el dataset del espacio se regenera con los libros reales. (RF-1, RF-20, RF-23)
      Hecho cuando: se ve en el navegador real. La comprobación con los libros reales por la vía de la web, sin navegador
      ni servidor, se hizo el 2026-11-12 (cifras en el informe de la tarea, fuera de git).
      Hecho en la fila 104-T6 (f7, 17-11): `frontend/test/e2e/f10_libros_nuevos.e2e.mjs` en Edge, con su web con la vigilancia
      encendida (CSG_LIBROS_NUEVOS=1 e intervalo corto): el libro de octubre que llega a la carpeta del espacio sale
      reconocido en «Novedades de los libros» sin pulsar nada, y el dataset del espacio se regenera solo (al_dia, con el
      libro nuevo). Libros sintéticos de tests/e2e_libros_sinteticos.py; la vía de la web con los libros reales, el 2026-11-12.
- [x] T7. Carril de fondo que cede al operador: sin la cola del motor, proceso de prioridad baja que se termina al ceder,
      foto base sin abrir libros, «Verificar todos ahora», dataset solo en reposo y aviso que se relee. (RF-30 a RF-39)
      Hecho cuando: `tests/test_libros_nuevos_web.py -k "fondo or base or ceder or reposo or verificar_todos"` y
      `npm test` (`frontend/test/librosFondo.test.mjs`) en verde, y en el navegador «Cargar / listar alimentadores»
      arranca enseguida con una revisión de fondo en marcha.
- [x] T8. Solo los espacios recientes, y sin leer libros de los que el operador no tiene abiertos. (RF-40, RF-41)
      Hecho cuando: `tests/test_libros_nuevos_web.py -k "recientes or abierto"` en verde.
- [x] T9. El dataset «regenerando» sin proceso vivo, pasado de plazo o cortado al apagar la web pasa a interrumpido, se
      avisa y se retoma; los libros apartados salen como aviso. (RF-42 a RF-47)
      Hecho cuando: `tests/test_libros_nuevos_web.py -k "interrumpido or vivo_no_se_toca or plazo or cerrar_la_web or
      apartado_y_formato"` falla sin el arreglo y pasa con él (registros `D:/csg/D_todo_rojo_9063b8af.log` y
      `D:/csg/D_todo_verde.log`).
- [x] T10. En la web real, el aviso del dataset interrumpido y el de un libro apartado se ven en el paso de la demanda, y
      la confirmación de un formato (089:RF-110) se hace con su botón. (RF-44, RF-47)
      Hecho cuando: se ve en el navegador real, tras `npm run lint`, `npx tsc --noEmit -p .`, `npm test`, `npm run build`
      y `tools/generar_contrato_api.py --check` en verde.
      RF y sus pruebas: RF-44 y RF-47 `frontend/test/librosFondo.test.mjs` («104:RF-44, 104:RF-47 cada aviso dice de qué es
      y el interrumpido o el apartado se ven como alerta», línea 91); en el servidor, `tests/test_libros_nuevos_web.py`
      (líneas 501, 609, 645, 778, 800, 814 y 829).
      Hecho el 2026-11-15 (tarjeta 104_T10 de la PISTA 3; el auditor 0d la pasa de REAL a HACER con los cinco comandos,
      sin el navegador). Sobre el árbol de PASO-PIT-DIAG (267d698d), en `D:/csg/PM_IMPL/PISTA3/104_T10/`: lint y tsc
      rc=0 (`verde_lint_tsc.log`), `npm test` 178 de 178 (`verde_npm_test.log`), build rc=0 (`verde_build.log`) y
      «Contrato API sin deriva.» (`verde_contrato.log`).
- [x] T11. El estado del reconocimiento se guarda aunque Windows niegue un instante su sustitución, y un
      bloqueo que persiste sube sin dañar el estado anterior. (RF-48)
      Hecho cuando: `tests/test_libros_nuevos.py -k "windows_niegue or niega_siempre"` falla sin el arreglo
      (`D:/csg/PM_IMPL/104_REINTENTO/rojo_192946.log`) y pasa con él, y `tests/test_libros_nuevos.py`,
      `tests/test_libros_nuevos_web.py` y `tests/test_datos_duraderos.py` siguen en verde.
      RF y sus pruebas (una por RF; todas en el mapa `D:/csg/PM_IMPL/PISTA3/MARCAS-PISTA3/mapa_T_RF_pruebas.tsv`):
      RF-48: `tests/test_libros_nuevos.py::test_el_estado_no_se_da_por_guardado_si_windows_lo_niega_siempre` (línea 229).
      Hecho el 2026-11-15 (MARCAS-PISTA3; arreglo de ccceb4c8): rojo `D:/csg/PM_IMPL/104_REINTENTO/rojo_192946.log`
      (la F es el PermissionError que la prueba reproduce); verde: suite entera sobre el árbol de e182c823 con las 14 variables CSG_*: `D:/csg/INTEGRA_54/g107/integra_g12f13_82_183656.log` (línea 1202) «Puerta de calidad: 9582 pruebas, 0 fallidas, 0 omitidas.»
- [x] T12. Al terminar la regeneración, el estado final se guarda antes de soltar el proceso propio, y el paso a
      interrumpido se decide en el mismo guardado: ningún dataset «al día» queda sin sus libros incluidos. (RF-43, RF-45)
      Hecho cuando: `pytest -q tests/test_libros_nuevos_web.py -k "terminar_bien or no_pisa"` falla sobre 98dbffc9 con
      solo las pruebas y pasa con el arreglo, `tests/test_libros_nuevos_web.py` y `tests/test_libros_nuevos.py` siguen en
      verde, y la e2e `frontend/test/e2e/f10_libros_nuevos.e2e.mjs` pasa cinco veces seguidas.
      Hecha el 2026-11-22 (tarjeta E2E-F10): rojo `D:/csg/PM_IMPL/E2E_F10/rojo.log` (2 F por aserción, rojo=VALIDO),
      verde `D:/csg/PM_IMPL/E2E_F10/verde.log` y e2e `D:/csg/PM_IMPL/E2E_F10/e2e_f10_x5.log`.

