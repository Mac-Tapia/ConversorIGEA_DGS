# Tareas - Spec 018

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Registro compartido en `powerfactory_binding.py`: lectura y escritura atómica con
      bloqueo, `vinculo_guardado` (el registro prevalece sobre la copia) y
      `record_project_binding` que escribe primero el registro. (RF-1, RF-2, RF-7)
      Hecho cuando: `pytest -q tests/test_powerfactory_binding.py` en verde.
- [x] T2. Causas `PROJECT_BINDING_NO_ACTIVE_SOURCE` y `PROJECT_BINDING_FOLDER_MISMATCH` en
      `require_project_binding`. (RF-3, RF-4)
      Hecho cuando: las pruebas de RF-3 y RF-4 en verde.
- [x] T3. Exigencia del vínculo en el servidor para `pf_verificar_base`; el espacio recibe
      `vinculos_compartidos` en `WorkspaceStore`. (RF-5)
      Hecho cuando: la prueba de RF-5 en verde y `tests/test_caso_base_web.py` en verde.
- [x] T4. Comprobación del DGS aceptado (`comprobar_dgs_vinculados`) en `native_action_context`
      y en la verificación. (RF-6)
      Hecho cuando: la prueba de RF-6 en verde.
- [x] T5. Interfaz: el paso 1.1 y el paso 2 dependen del bloqueo real, con el mensaje de la
      causa. Hecho cuando: `npm run build` en `frontend/` sin errores.
- [x] T6. Revisión: literales con mojibake corregidos y suite de vínculo, API web, caso base y
      ajuste en verde.
      Hecho cuando: la suite de vínculo, API web, caso base y ajuste en verde y sin literales con mojibake.
- [x] T7. Siembra del registro al arrancar (`WorkspaceStore`, `sembrar_registro`): los vínculos
      de los espacios existentes pasan al registro, validados por su huella. (RF-8)
      Hecho cuando: `pytest -q tests/test_powerfactory_binding.py` en verde, con la prueba de RF-8.
- [x] T8. `estado_vinculos` y `adoptar_fuente_del_vinculo` en `web/services.py`, con la ruta
      `POST /powerfactory/adoptar-fuente` como trabajo del carril del motor. (RF-9, RF-10)
      Hecho cuando: las pruebas de RF-9 y RF-10 en `tests/test_powerfactory_binding.py` en verde.
- [x] T9. Verificación del «Caso base» con la ejecución activa en disco, sin la red en memoria.
      (RF-12) Hecho cuando: la prueba de RF-12 en `tests/test_powerfactory_binding.py` y
      `tests/test_caso_base_web.py` en verde.
- [x] T10. Interfaz: uso automático sin fuente activa, botón con otra fuente, y un texto para
      cada causa. (RF-11) Hecho cuando: `npm run build` sin errores y la prueba del front.
- [x] T11. `pf_proyectos_guardados` y `GET /powerfactory/projects`; la pestaña la usa cuando no
      hay lectura en la sesión. (RF-13) Hecho cuando: la prueba de RF-13 en
      `tests/test_caso_base_web.py` en verde y `npm run build` sin errores.
- [x] T12. Retro (033, 2026-10-29): RF-14, RF-15, añadidos a la spec como cambio después de
      escribir las tareas e implementados con su prueba sin tarea propia. (RF-14, RF-15)
      Hecho cuando: las pruebas que los citan pasan (pruebas de `tests/test_powerfactory_binding.py`).
