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
- [ ] T6. Con la web real arrancada por el operador, el libro nuevo aparece reconocido en el aviso del espacio sin pulsar
      nada, y el dataset del espacio se regenera con los libros reales. (RF-1, RF-20, RF-23)
      Hecho cuando: se ve en el navegador real. La comprobación con los libros reales por la vía de la web, sin navegador
      ni servidor, se hizo el 2026-11-12 (cifras en el informe de la tarea, fuera de git).
- [x] T7. Carril de fondo que cede al operador: sin la cola del motor, proceso de prioridad baja que se termina al ceder,
      foto base sin abrir libros, «Verificar todos ahora», dataset solo en reposo y aviso que se relee. (RF-30 a RF-39)
      Hecho cuando: `tests/test_libros_nuevos_web.py -k "fondo or base or ceder or reposo or verificar_todos"` y
      `npm test` (`frontend/test/librosFondo.test.mjs`) en verde, y en el navegador «Cargar / listar alimentadores»
      arranca enseguida con una revisión de fondo en marcha.
- [x] T8. Solo los espacios recientes, y sin leer libros de los que el operador no tiene abiertos. (RF-40, RF-41)
      Hecho cuando: `tests/test_libros_nuevos_web.py -k "recientes or abierto"` en verde.
