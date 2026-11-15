# ADR-004 · Todo fichero de estado se publica con el escritor duradero común

- Estado: vigente
- Fecha: 2026-11-14
- Specs: 086:RF-1, 086:RF-2, 086:RF-54
- Elementos C4: workspaceStore, custody, operationStore, api
- Evidencia: `src/convertersmartgrid/util.py::publicar_duradero`, `src/convertersmartgrid/util.py::_sustituir`, `src/convertersmartgrid/util.py::ESPERAS_SUSTITUIR_S`, `src/convertersmartgrid/util.py::sincronizar_carpeta`, `src/convertersmartgrid/util.py::write_json_atomic`, `src/convertersmartgrid/util.py::ruta_copia_anterior`
- Consumidores: `src/convertersmartgrid/web/workspace.py::publicar_duradero`, `src/convertersmartgrid/web/source_runs.py::publicar_duradero`, `src/convertersmartgrid/web/copia_datos.py::publicar_duradero`, `src/convertersmartgrid/asistente/almacen.py::publicar_duradero`, `src/convertersmartgrid/powerfactory_binding.py::publicar_duradero`

## Contexto

Un `replace` sin `fsync` es atómico frente a un proceso que muere, pero no frente a un corte de luz: el sistema puede
grabar el cambio de nombre antes que los datos y dejar un `workspace.json` vacío donde había uno bueno. En Windows,
además, `replace` falla con `PermissionError` si otro proceso (el antivirus) tiene abierto el destino en ese
instante: con la suite completa del 2026-11-10, un trabajo de la web no se encoló una vez de 8 613 pruebas. El
2026-11-14 la spec 104 volvió a encontrarlo al guardar su estado (104:RF-48, en la pila de integración), y la
decisión del día fue reutilizar el escritor común en vez de un arreglo local.

## Decisión

Cada fichero de estado (espacio de trabajo, ejecución fuente, vínculo con DIgSILENT, almacén del asistente, copia
de datos y estados nuevos como el de la 104) se publica con `util.publicar_duradero`: temporal fuera del checkout,
`fsync`, sustitución con reintentos acotados (menos de dos segundos, solo ante `PermissionError` en Windows) y
sincronización de la carpeta. `write_json_atomic(copia=True)` conserva la versión buena anterior en `<nombre>.bak`.
Nadie copia esta lógica: `tests/test_util.py` falla si reaparece en otro módulo.

## Alternativa descartada

Una base SQLite única para todo el estado. Daría transacciones, pero obliga a migrar ficheros que otras
herramientas y el operador leen como JSON, y añade un escritor exclusivo que hoy no hace falta. Tampoco se acepta
un `try/except` local que reintente a su manera: es la copia que esta decisión prohíbe.

## Consecuencias

- Un corte de luz deja el fichero anterior o el nuevo, nunca uno a medias.
- Un bloqueo pasajero de Windows ya no tumba un trabajo; uno que dura más de dos segundos sube como error, con su
  causa, y no se calla.
- Un módulo nuevo con estado propio tiene que figurar en «Consumidores» de este ADR.

## Contratos afectados

Los ficheros `workspace.json` y su `.bak`, los manifiestos de las ejecuciones fuente, el vínculo con DIgSILENT y
los estados del asistente. Su formato no cambia; cambia cómo se escriben.

## Vuelta atrás

Sustituir `publicar_duradero` por un `replace` simple en un único sitio: un solo cambio en `util.py`. No se
recomienda: devuelve los dos fallos medidos.
