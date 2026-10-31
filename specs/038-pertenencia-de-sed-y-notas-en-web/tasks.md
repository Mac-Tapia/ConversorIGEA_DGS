# Tareas — spec 038

- [x] T1. Reconciliar la pertenencia antes del filtro y conservar evidencias (RF-1 a RF-5, RF-8).
  Hecho cuando: pasan los casos único, ausente y ambiguo y la integración con máximas.
- [x] T2. Notas del libro, interfaz y exportación (RF-2, RF-6).
  Hecho cuando: las notas sobreviven al cruce y al Excel y la interfaz las muestra.
- [x] T3. Nota sobre la fuente exportada y el alcance de los planos de IGEA (RF-7).
  Hecho cuando: la nota explica el alcance indicado por el usuario y pasa el build.
- [x] T4. Verificar regresión, trazabilidad y entrega real (RF-1 a RF-8).
  Hecho cuando: pasan las suites afectadas y se comprueban las asignaciones de la fuente real sin modificar la red nativa por un cambio comercial.

## Evidencia del 2026-10-31

- Reproducción inicial: 9 fallos por falta de reconciliación, notas y aclaración del alcance.
- Dos regresiones adicionales reprodujeron la pérdida de ambigüedad por mayúsculas y la
  preparación de un plan que omitía una fija ambigua; quedaron corregidas.
- `pytest tests/test_pertenencia_sed.py tests/test_demanda_medida.py
  tests/test_demanda_medida_web.py tests/test_ajuste_cabecera_web.py
  tests/test_q_con_bancos.py -q` con `IGEA_DEMANDA_DIR` real: **203 passed**, sin skips.
- `npm --prefix frontend run build`: TypeScript y Vite correctos.
- Regresión final después de incorporar el índice reutilizable de la fuente:
  `test_pertenencia_sed`, `test_demanda_medida_web`, `test_ajuste_cabecera_web`,
  `test_q_con_bancos` y `test_trazabilidad_specs`: **140 passed**, sin omisiones.
- Las once pruebas propias de pertenencia y notas pasaron; junto con la trazabilidad
  final: **33 passed**. Los ocho RF tienen tarea y prueba.
- Comprobación de inventario y trazabilidad: **35 passed, 44 deselected** en 596,73 s;
  se excluyeron las ayudas CLI, que no forman parte de este cambio. No se afirma que
  haya corrido toda la suite del repositorio.
- Ruff completo del archivo nuevo de pruebas: correcto. Ruff de errores de ejecución
  (`E9,F63,F7,F82`) de los dos módulos afectados: correcto. La revisión completa de
  estilo de esos módulos conserva deuda anterior; no se declara limpia globalmente.
- Tabla y plan: pruebas de pertenencia antes del filtro y rechazo de ambigüedad.
- Entrega real por la API: 15 clientes de NA203 y 17 de NA205; las tres SED corregidas
  conservan la nota del libro compartido. Las dos discrepancias PE104/CHN102 observadas
  se asignan a la red exportada y muestran el radial comercial anterior.
- Fuente TXT cargada de nuevo por la API, sin reconversión ni importación nativa:
  `20261031T085543-af2dc31e9a8f`; huella
  `c3df248bfe29a734a1c34139cc1259d9962a223ca574f45c4cf45c152198c708`.
- Bundle servido `index-D8ObVfGu.js`: comprobadas la nota del alcance y las notas por fila.
  Verificación de API y compilación; no se afirma inspección visual del navegador.
- La recalibración nativa del 2026-10-29 incorporó las tres SED corregidas, sin omitidas,
  y conservó la central del operador y cuatro bancos por alimentador en su escaneo;
  terminó en `FALLO_VALIDACION_NATIVA`. El cierre de esta spec de pertenencia y notas
  no acredita aceptación eléctrica de NA203 ni NA205.
- Los planos previos de IGEA no se modificaron; el aviso añadido inicialmente a la vista
  previa se retiró al aclarar el usuario el alcance.
