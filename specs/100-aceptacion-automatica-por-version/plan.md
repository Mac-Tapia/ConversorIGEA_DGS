# Plan 100 — Aceptación automática por versión

## Dónde

- `config/aceptacion/matriz.json`: los casos, sin datos de la distribuidora (RF-1, RF-5).
- `tools/aceptacion_version.py`, nueva: recorre la matriz reutilizando `tools/sistema_web.py` y `tools/aceptacion_nativa.py`, sin repetir la API (RF-2, RF-3, RF-5, RF-7).
- Reutiliza el retomar de `sistema_web.py` y el diario de trabajos (086:RF-9) para relanzar (RF-5).

## Decisión

Una herramienta sobre lo que ya existe, y no pruebas de pytest con DIgSILENT, porque 084:RF-21 las separa.

## Pruebas

Sintéticas con una web falsa: orden de la matriz, relanzado, informe, veredicto y que ninguna fuente se mezcle.

## Matriz estudio × motor (RF-8 a RF-12)

- `src/convertersmartgrid/dominio/matriz_estudios.py`, nuevo y puro: la tabla de evidencias y motivos, y `matriz(estado_de)` (RF-8, RF-9, RF-11).
- `src/convertersmartgrid/presentacion/web/matriz_estudios_api.py`, nuevo: `GET /api/estudios/matriz`, con el lector de la línea `Estado:` de `lectura_proyecto.estado_de_spec`; el contrato `MatrizEstudiosRespuesta` en `api_contract.py` (RF-10).
- Frontend: `api/matrizEstudios.ts`, `shared/matrizEstudios.ts` y `shared/MarcaValidacion.tsx`; la marca en los estudios de «4.2», en los pasos de calibración y obras, en el PIDE y el gemelo, y en las pestañas del VNR, PIT, VAD, PIDE y largo plazo (RF-12). No se quita nada de la web: se añade la marca y el apagado.

Decisión: el estado sale de las specs y no de una lista escrita a mano, para que reabrir una spec quite el «validado» sin tocar el código. La entrega excluye `specs/` (`config/entrega.json`), así que `tools/estado_specs.py --escribir` escribe también `src/convertersmartgrid/recursos/estado_specs.json` (`{spec: estado}` y la huella del README), que entra en la entrega y en la rueda (`recursos/*.json` en package-data); la ruta lo lee cuando no hay `specs/` (RF-13). Sin ninguno de los dos, nada sale validado. Las specs cuya tarea de DIgSILENT se cerró sin corrida propia, con su comprobación pasada a esta spec (011, 042, 049, 052, 087, y la 012 y la 045), llevan la 100 en la evidencia de sus celdas: no validan nada hasta que se cumpla la T4.


## Dos corridas sobre el mismo espacio (RF-14 a RF-17)

- `tools/aceptacion_version.py`: `tomar_candado`/`soltar_candado` con `<salida>/.aceptacion_en_curso.json` (PID e inicio); un candado de un proceso muerto se toma de nuevo; código de salida 3 (RF-14).
- `tools/sistema_web.py`: `otro_guion_del_espacio` mira los procesos de la máquina con psutil, sin contar el propio, sus antecesores (el lanzador del `.venv` repite la línea) ni sus hijos; sale con 1, que la matriz da por fallo y no relanza (RF-15).
- `presentacion/web/jobs.py`: `JobContext.pendientes`, los demás trabajos sin terminar; `services.proyectos_con_trabajos_pendientes` saca de sus títulos (y de la petición con que se relanzan) los proyectos con sello, y la importación los pasa con `--conservar` a `tools/powerfactory_acceptance.py`, que se los da a `carpeta_pf.eliminar_versiones_anteriores` (RF-16).
- `carpeta_pf.proyecto_ausente`: el mensaje común; `tools/ajuste_cabecera_pf.py` lo usa en sus tres activaciones y ya no sigue con `None` tras la primera pasada de los bancos que faltan (RF-17).

Decisión: tres defensas en capas y no una. El candado y la guarda del espacio evitan la causa del 25-11; la protección de los proyectos con trabajos cubre dos espacios distintos con el mismo alimentador, que ninguna de las dos ve. Se descarta que la importación deje de retirar versiones (005:RF-22 sigue valiendo) y que el nombre del proyecto se busque en el registro de la web: el título de cada trabajo de DIgSILENT ya lo lleva.


## La aceptación valida la web (RF-18 a RF-24, 2026-11-28)

- `aplicacion/sello_aceptacion.py`, nuevo: `carpeta_aceptacion` (`CSG_ACEPTACION_DATA` o `_aceptacion/` junto a los
  espacios de la web, `raiz_datos_web`, como el agente MASAC); `sellar` recalcula el veredicto con los casos de la matriz
  y escribe `sello_<revisión>.json` con `write_json_atomic` (RF-18 a RF-20); `version_en_uso` da `git rev-parse HEAD`
  en un árbol con `.git` y, si no, `__version__` del paquete (RF-21); `sello_vigente` solo devuelve el de esa versión
  (RF-22); `registrar_espacios` y `espacios_de_aceptacion` (RF-24, y los `CSG_ACEPTACION_*_ESPACIO` del entorno).
- `tools/aceptacion_version.py`: aceptada, sella (RF-18); `--sellar <informe.json>` sella un informe ya corrido, con
  `--variables` para anotar sus espacios y `--sellos` para otra carpeta (RF-19, RF-20, RF-24); los espacios se anotan
  antes del primer caso.
- `dominio/matriz_estudios.matriz(..., aceptacion=)`: la 100 vale por cumplida con el sello; el motivo de la celda
  validada por él lo dice (RF-21, RF-23). `presentacion/web/matriz_estudios_api.py` busca el sello de su versión en cada
  petición; `MatrizEstudiosRespuesta.aceptacion` en el contrato.

Decisión: el sello vive en los datos del programa y no en `specs/`: cerrar la T4 a mano seguiría siendo un paso humano y
la entrega instalada no trae `specs/`. Se descarta comparar el árbol (`git write-tree`) en la web: con un fichero sin
seguimiento cambiaría y una versión aceptada dejaría de valer; la revisión basta para «otra versión no vale». La web no
reconoce la revisión de un programa instalado, que no trae git: allí vale el sello cuya versión pedida es la del paquete.
