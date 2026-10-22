# Plan — Spec 024, primera entrega: búfer de episodios

Lee: `docs/constitution.md` y `specs/024-pinn-gemelo-digital/spec.md`.

Alcance de este plan: los puntos 1 y 2 del «Orden de entrega» de la spec (contrato, búfer,
captura y caso dorado). Generador de escenarios, PINN/GNN, RNN, ordenamiento de
alternativas del PIDE y confiabilidad tienen cada uno su plan después de este, cuando el
búfer tenga episodios completos. Este plan no entrena ningún modelo ni añade PyTorch.

Parte del borrador de Codex `docs/superpowers/plans/2026-10-21-digital-twin-episode-buffer.md`
(histórico), corregido con la evaluación por caso (RF-28 a RF-31) y el registro de las
alternativas del PIDE (RF-32) que entraron en la spec al aprobarla.

## Contexto técnico

- Paquete nuevo `src/igea_dgs/digital_twin/`, puro (biblioteca estándar y `sqlite3`), sin
  importar PowerFactory: `episode.py` (contrato), `buffer.py` (almacén), `evaluacion.py`
  (clasificación por caso y norma), `capture.py` (ensamblaje), `native_snapshot.py`
  (identidades y lectura nativa) e `integration.py` (enganche con la web).
- Esquema `src/igea_dgs/schemas/digital_twin_episode_v1.schema.json`.
- Lectura nativa en `tools/digital_twin_snapshot_pf.py`, por `pf_arnes.conectar` y el servidor
  de DIgSILENT (spec 019), en el carril `powerfactory`, después de que la acción que escribe
  haya terminado; solo lectura (sin `CreateObject`, `Delete`, `SetAttribute`,
  `WriteChangesToDb`).
- Enganche en `src/igea_dgs/web/services.py` tras cada salida nativa (flujo, cargas, ajuste,
  verificación del «Caso base», obras, estudios, transferencia, guiones) y consulta en
  `src/igea_dgs/web/app.py`.
- Norma por sistema: `norma` de `config/perfiles/<empresa>.estructura.json` (NTCSE/NTCSER) y
  límites de `estudios` del perfil; transformadores con la máxima de la NTP 370.400 del perfil
  (spec 020).
- Búfer en `IGEA_TWIN_DATA` o `data_root() / '_digital_twin'` (`web/workspace.py`), local.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Contrato | `digital_twin/episode.py`, esquema JSON | RF-1, RF-2, RF-7, RF-28, RF-32 (campos) |
| B. Búfer | `digital_twin/buffer.py` | RF-6, RF-7, RF-8, RF-9, RF-10 (sin borrar evidencia) |
| C. Evaluación por caso | `digital_twin/evaluacion.py` | RF-4, RF-5, RF-29, RF-30, RF-31 |
| D. Ensamblaje | `digital_twin/capture.py`, `native_action.py` (solo helpers) | RF-1, RF-3, RF-4, RF-9 |
| E. Lectura nativa | `tools/digital_twin_snapshot_pf.py`, `digital_twin/native_snapshot.py`, `tests/fake_pf.py` | RF-2, RF-3, RF-27, RF-28 |
| F. Enganche web | `digital_twin/integration.py`, `web/services.py`, `web/jobs.py` | RF-1 |
| G. Consulta | `web/app.py`, `web/services.py`, `tools/digital_twin_buffer.py` | RF-8 |
| H. Caso dorado | `tools/accept_digital_twin_in111_ta225.py`, fixture saneado | RF-24 a RF-27 |

## Decisiones

- Clasificación por caso, no por convergencia. En «Caso base» y «Sin proyecto» una violación de
  norma es `diagnostico` del episodio `accepted` (RF-29); solo en «Con proyecto» da
  `converged_with_violations` (RF-5, RF-31). Descartado: el clasificador del borrador, que
  marcaba toda subtensión como violación y habría rechazado la red real tal como está.
- «Sin proyecto» exige que la calibración cuadre con la medida (RF-30): se toma el resultado del
  ajuste (spec 006/015/022) ya guardado, no se recalcula. Sin medidor, el episodio lo dice y no
  se acepta por cuadre. Descartado: comparar aquí con la medida, porque duplicaría el ajuste.
- «Con proyecto» compara pérdidas y confiabilidad con el último episodio aceptado de «Sin
  proyecto» del mismo proyecto; si no existe, cuarentena con la causa. Los índices de
  confiabilidad solo entran si la spec 012 ya los calculó; si no, quedan ausentes explícitos y el
  criterio de confiabilidad no se evalúa (se anota), sin bloquear.
- Límites de la norma solo desde el perfil (P13). Un sistema NTCSER sin tolerancia en el perfil
  deja el episodio de «Con proyecto» en cuarentena con «falta la tolerancia NTCSER en el perfil».
  Descartado: suponer un valor.
- Identidad estable por ruta completa del objeto en el proyecto y su clase, no por `loc_name`.
- JSON canónico con SHA-256 como objeto inmutable; SQLite solo como índice reconstruible.
  Descartado: SQLite como única evidencia (se corrompe y no se audita a mano).
- Una captura fallida deja cuarentena y nunca repite ni deshace la acción nativa.
- Los campos del PIDE (alternativa, tramo o equipo, coste, VAN, TIR, retorno) se registran si la
  obra los trae; el ordenamiento (RF-33, RF-34) va en su propio plan.

## Comprobación contra la constitución

- P13 universal: norma y límites del perfil; ninguna tensión, empresa ni alimentador fijo; el
  caso dorado vive solo en su prueba y su guion de aceptación.
- Escala: el índice consulta por columnas indexadas; nada recorre todos los episodios por
  alimentador.
- Datos de la distribuidora: el fixture del caso dorado no lleva coordenadas ni clientes, solo
  identificadores sintéticos, huellas y las tensiones de la spec.
- Idioma: código y mensajes nuevos en español (el borrador estaba en inglés).

## Estrategia de pruebas

- Unitarias puras para A, B, C y D, sin licencia; casos sorteados de clase y caso.
- `fake_pf` con dos alimentadores, una frontera abierta y un enlace manual para E.
- Web con el cliente de pruebas de FastAPI para F y G.
- Caso dorado: prueba sin licencia con el fixture, y aceptación nativa aparte en DIgSILENT con
  el proyecto `20261015-170359_IGEA_IN111_TA225`, en dos procesos (escribir y releer).
- Cada prueba cita `024:RF-n`; ficheros nuevos en `CODIGO_FUENTE.md` (spec 009); las
  herramientas responden a `--help`.
- Suite completa con las siete variables y ninguna omitida al cerrar.

## Riesgos

- El enganche tras cada acción alarga el turno de DIgSILENT: la lectura usa el servidor abierto
  (019) y se mide en la prueba nativa; si pasa de 30 s en CA101 se anota y se decide.
- Un cambio en los estados de `native_action.py` rompería la puerta del proyecto nativo: solo se
  añaden helpers y `test_native_project_gate.py` corre en cada tarea que lo toque.
- El búfer crece sin límite: retención sin borrado decidida en la spec; se informa el tamaño.

---

# Plan — entregas siguientes (T10 a T14)

Usuario, 2026-10-22: «has lo que falta, nada debe quedar pendiente»; «seguir sin parar»,
PyTorch con GPU (RTX 4060, CUDA 12.6), datos buscados en la web y tasa del 12 %. Orden:
T13 → T14 → T10 → T11 → T12, porque el plan del PIDE y su economía no dependen de los
modelos y los modelos necesitan los escenarios.

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| T13. Metodología del PIDE | `src/igea_dgs/pide.py` (puro): mercado y densidad por cuadrículas, diagnóstico con causa, año de incumplimiento, plan por etapas, formatos 01 a 15 en Excel; `tools/pide_pf.py`: cada año del horizonte en DIgSILENT con el factor de escala de cargas del `ComLdf`, restituido al terminar | RF-49 a RF-53, RF-60 a RF-63 |
| T14. Economía y priorización | `src/igea_dgs/pide_economia.py` (puro): libro CAPEX por nombres del perfil, CI por componente, anualidad, costo anual, VAN y TIR regulados, flujo de caja privado con tarifas, indicadores, priorización del art. 15, sobredimensionadas, rubros; `services`: propuestas propias verificadas y aplicadas con las obras de la 011 | RF-23, RF-33 a RF-36, RF-38, RF-45 a RF-48, RF-54 a RF-59 |
| T10. Escenarios y aprendizaje activo | `src/igea_dgs/digital_twin/escenarios.py` (puro: matriz, partición por familia, elección por incertidumbre); `tools/escenarios_pf.py`: copia del proyecto, escala y tramos abiertos, lectura y episodio `counterfactual`, copia borrada | RF-11, RF-12, RF-40, RF-41 |
| T11. Oráculo PINN/GNN | `src/igea_dgs/digital_twin/oraculo.py` (PyTorch opcional): grafo con impedancias, GNN con pérdida física de balance nodal, conjunto de modelos para la incertidumbre, fuera de distribución, registro y promoción con puertas | RF-13 a RF-19, RF-39, RF-42 a RF-44 |
| T12. Gemelo temporal | `src/igea_dgs/digital_twin/temporal.py`: GRU sobre las curvas de cabecera del mes, pseudo-medidas de los alimentadores sin medidor con la barra de su SET | RF-20 a RF-22, RF-37 |

Decisiones:
- Los años se verifican escalando las cargas con el `ComLdf` y no con variaciones: no deja
  nada en el proyecto. Descartado: una variación por año, que el operador tendría que borrar.
- Los escenarios se simulan en una copia del proyecto que se borra al terminar (memoria
  «no probar con datos inventados»: nunca SED inventadas, solo escala y maniobras).
- Pesos del art. 15.3 iguales mientras el perfil no diga otros; la norma no los fija.
- COyM como fracción del CI del perfil; sin ella, el costo anual se da sin COyM y se avisa.
- PyTorch es el extra `ml`: sin él, el oráculo y el gemelo temporal dicen que falta y el
  resto funciona (RNF «Compatible»).
