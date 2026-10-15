# Verificación de las specs — 2026-10-14

Recorrido de cada spec de `specs/`, RF por RF y tarea por tarea, según la fase 7 del skill
`igea-dgs-spec`: un RF sin prueba que lo cite es un RF no cumplido. Rama
`lectura-de-las-dos-disposiciones`, con los cambios sin confirmar del arranque acotado de
los guiones de PowerFactory (005:RF-21).

## Cómo se midió

- **RF definidos:** líneas `- RF-n` de cada `spec.md` (la misma regla que
  `tests/test_inventario.py`).
- **RF probados:** RF definidos que cita al menos una prueba (`NNN:RF-n` en `tests/` o
  `frontend/src/`).
- **Suite sintética:** `pytest -q` → 1713 correctas, 61 omitidas.
- **Suite con datos reales** (`IGEA_RED`, `IGEA_LOADS`, `IGEA_EQUIPMENT`, `IGEA_MDB`,
  `IGEA_EQUIPMENT_MDB`): 1753 correctas, 20 omitidas. 18 de las omitidas eran
  comparaciones tramo a tramo entre la vía TXT y la vía Access; se **retiraron** el mismo
  día, porque las fuentes son independientes (otra fecha, otra empresa) y cada una se
  valida por sí misma. Las otras dos son de la demanda medida y piden `IGEA_DEMANDA_DIR`. El único fallo de esa vuelta fue el índice
  nombrando este informe antes de existir.

## Resultado por spec

| Spec | RF probados | Tareas | Abiertas | Veredicto |
| --- | --- | --- | --- | --- |
| 001 reorganización | 27/27 | 24/24 | — | **Cumplida** |
| 002 arquitectura por capas | 8/37 | 2/12 | T2–T4, T6–T12 | **No cumplida**: sin empezar salvo T1 (línea base) y T5 (perfil de empresa, RF-31 a RF-37) |
| 004 cargas en PowerFactory | 55/55 | 14/14 | — | **Cumplida** (estado actualizado) |
| 005 carpeta de proyectos PF | 21/21 | 12/13 | T12 (DIgSILENT) | Implementada; falta la prueba del usuario |
| 006 ajuste a la máxima | 44/44 | 12/13 | T8 (DIgSILENT) | Implementada; falta la prueba del usuario |
| 007 cargas sobre el ajuste | 39/39 | 10/11 | T11 (DIgSILENT) | Implementada; falta la prueba del usuario |
| 008 pestaña por pasos | 24/24 | 6/7 | T7 (DIgSILENT) | Implementada; falta la prueba del usuario |
| 009 inventario | 15/15 | 5/5 | — | **Cumplida** (estado actualizado) |
| 010 trazado GPS | 7/7 | 6/6 | — | **Cumplida** |
| 011 estudios y obras | 126/129 | 23/24 | T19 (DIgSILENT) | Implementada; RF-2, RF-54 y RF-55 sustituidos (ver abajo) |
| 012 confiabilidad y capacidad | 12/72 | 2/13 | T3–T13 | **No cumplida**: en curso, sigue T3 |
| 013 mes de análisis y transferencia | 6/29 | sin `tasks.md` | — | **Borrador**: plan escrito, sin tareas ni aprobación; RF-1 a RF-6 ya tienen prueba |
| 014 calibración en «Sin proyecto» | 28/28 | 12/13 | T9 (DIgSILENT) | Implementada; falta la prueba con CA101 |
| 015 «Caso base» verificado | 46/46 | 17/18 | T12 (DIgSILENT) | Implementada; falta la prueba con CA101 |

## Huecos y qué hacer con ellos

1. **011:RF-2, RF-54 y RF-55 no los cita ninguna prueba** porque su comportamiento ya no
   existe: la 014 llevó la calibración a «Sin proyecto» (RF-2) y la 015 quitó la
   variación del ajuste y de las demandas (RF-54, RF-55). Ambas specs están anotadas al
   final de la 011. Cuando se cierre T19, `test_una_spec_implementada_tiene_cada_rf_probado`
   fallará por esos tres RF: hay que decidir si se reescriben en la 011 con el
   comportamiento vigente (y una prueba los cita) o se marcan como sustituidos de forma
   que la prueba del inventario los excluya. Es un cambio de spec: necesita aprobación.
2. **La spec 013 no figuraba en `CLAUDE.md`** y no tiene `tasks.md`. Su plan es de
   2026-10-13 y su estado, borrador. Falta aprobar spec y plan y escribir las tareas antes
   de seguir implementándola.
3. **Pruebas en DIgSILENT pendientes** (a cargo del usuario): 005 T12, 006 T8, 007 T11,
   008 T7, 011 T19, 012 T13, 014 T9 y 015 T12. La 014 T9 depende de la 015 T12, abierta
   porque el «Caso base» del proyecto CA101 existente no converge.
4. **Spec 002**: aprobada el 2026-10-08, con plan y tareas pendientes de aprobar desde el
   2026-10-10. Las capas de hoy están descritas en `docs/ARQUITECTURA.md`.

## Arreglado en esta verificación

- `tests/test_ajuste_cabecera_web.py::test_cancelar_no_empieza_otro_alimentador` fallaba
  con los cambios sin confirmar: el guion real ahora escribe «Conectado a DIgSILENT» al
  conectar, y la web no manda el fichero de cancelación a un guion que aún no ha escrito
  nada (lo corta). El guion falso de la prueba no imitaba esa primera línea, así que la
  cancelación lo cortaba antes de conectar y no había informe. Se añadió la línea al
  guion falso.
- Spec 014, T8c: notas «Cambios de la spec 014» en las specs 004, 006, 007 y 011. T8c-015
  ya estaba anotado al final de la 014. T10 cerrada con las dos suites.
- Specs 004 y 009 pasan a «cumplida»: todas sus tareas hechas y cada RF con prueba.
- Documentación: `docs/ARQUITECTURA.md` nuevo; README (pestaña en cuatro pasos, estado,
  enlace a la arquitectura), `docs/MANUAL_COMANDOS.md` 7.ter (los tres casos, calibración
  en el escenario de «Sin proyecto», paso 4; una ruta con un tabulador en lugar de `\t`),
  `CODIGO_FUENTE.md` y la tabla de estado de `CLAUDE.md`.
- Retiradas las 18 pruebas que comparaban TXT con Access (`TestAccessMatchesTxt`, la
  fase contra el TXT, y las clases «misma red» y «recuperación de conductores» de PA217
  y SL143) y la fixture `both`. Ninguna citaba un RF. Con ellas se retiraron
  `src/igea_dgs/huella.py` y `tools/emparejar_entradas.py`, que solo servían para
  emparejarlas.
