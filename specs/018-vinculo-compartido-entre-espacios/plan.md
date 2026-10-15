# Plan - Spec 018

## Archivos

- `src/igea_dgs/powerfactory_binding.py`: registro compartido (`vinculo_guardado`,
  `alimentadores_vinculados`, `sembrar_registro`, lectura y escritura atómica con bloqueo),
  causas nuevas (`NO_ACTIVE_SOURCE`, `FOLDER_MISMATCH`, `REGISTRY_UNREADABLE`) y
  `caso_base_verificado` sobre el registro.
- `src/igea_dgs/web/workspace.py`: `REGISTRO_VINCULOS_FILE` y el campo
  `vinculos_compartidos`, fijado por `WorkspaceStore` (crear y cargar); la siembra al arrancar.
- `src/igea_dgs/web/services.py`: `comprobar_dgs_vinculados` (RF-6), exigencia en
  `pf_verificar_base` (RF-5), `native_action_context`, `pf_projects` y `_registrar_vinculo`
  leen a través de `vinculo_guardado`. El import que deja proyectos sin vínculo escribe un
  AVISO en el Registro.
- `frontend/src/components/CargasTab.tsx`: el paso 1.1 se muestra solo sin bloqueo; el paso 2
  explica la causa del bloqueo con su código.
- Pruebas: `tests/test_powerfactory_binding.py` (RF-1 a RF-7) y `tests/test_caso_base_web.py`
  (la verificación exige un vínculo aceptado previo).

## Orden

1. Registro y lectura compartida (RF-1, RF-2, RF-7).
2. Causas de carpeta y fuente sin activa (RF-3, RF-4).
3. Exigencia en el servidor (RF-5), con las pruebas de la 015 que verificaban sin vínculo.
4. Comprobación del DGS (RF-6).
5. Interfaz.

## Riesgos y comportamiento nuevo

- Un proyecto aceptado no se puede verificar ni calibrar si su DGS cambió desde la
  aceptación (p. ej. reconversión con otras opciones). Es intencionado: el modelo de
  DIgSILENT ya no corresponde a la conversión. El mensaje dice qué hacer.
- Un proyecto sin vínculo deja de verificarse desde la web. Antes, la verificación creaba el
  vínculo. Para tener un vínculo hay que aceptar el proyecto desde la ejecución fuente activa.
- Si `vinculos_pf.json` se corrompe, todos los proyectos quedan bloqueados (fail-closed). No
  se borra ni se reconstruye en silencio; el mensaje indica el fichero.

## Reversión

Quitar el campo `vinculos_compartidos` vuelve al vínculo por espacio. Los vínculos que solo
existían en el registro se pierden hasta volver a aceptar.
