# Tareas — Spec 049

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Disponibilidad real e inventario de entradas. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_datos.py tests/test_estudios_pf.py tests/test_datos_empresa.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [x] T2. Escenarios de falla y captura nativa. (RF-4, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_pf_guion.py tests/test_protecciones_datos.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [x] T3. Coordinación, reporte y web. (RF-5, RF-6, RF-7, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_coordinacion.py tests/test_protecciones_web.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4 [DIgSILENT]. Validación y persistencia de protecciones en PowerFactory. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_nativas.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.
      Abierta el 2026-11-07, con la lista de bloqueo guardada. `tools/aceptacion_nativa.py protecciones` (por la web,
      `/pf/protecciones/capacidades` con `ejecutar_ordenes`) en `20261106-233549_CSG_TXT_8fc733e4_01_PE10`: DIgSILENT 24.0.2;
      `ComShc` existe y se ejecuta (licencia), con `GetFaultType`, `ExecuteRXSweep` y los atributos `shcobj`, `iopt_shc`, `Rf`,
      `Xf` e `iopt_allbus` (lo que la T2 dejó por confirmar); `ComShctrace` existe; 0 `ElmRelay`, 0 `RelFuse`, 0 `StaCt`;
      generación: las dos redes externas. Bloqueo: dispositivos con curva, ajustes y poder de corte (la fuente trae 4 filas
      DEFAULT con poder de corte 0); Scc e impedancia real de cabecera; `protecciones.cti_s`, `factor_sensibilidad` y
      `margen_poder_corte` del perfil. Evidencia `D:/converter/evidencia_nativa/20261107_PE10_t4c/` (manifiesto
      `e582c7c3a660f79b…`); `pytest -q -rs tests/test_protecciones_nativas.py`: 2 passed, 0 omitidas, sin cerrar la tarea.
      Siguiente acción (dueño: quien traiga el libro «Protecciones» de la empresa): con fichas reales, aplicar ajustes en
      `CSG049_ajustes`, reabrir y repetir las fallas.

## Evidencia de ejecución

Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando, resultado, informe y
limitaciones; no marcar casillas por existir código o por una simulación que solo converge.

T1 (RF-1 a RF-3), 2026-11-06, rama del worktree `agent-aeb4c1fac69ae0f98` sobre `1c22f85b`. Sin
DIgSILENT ni GPU; sintéticas sorteadas.

- `src/convertersmartgrid/protecciones.py`: `disponibilidad_protecciones` (disponible, faltan, bloqueos,
  alcance, criterios), `validar_dispositivo`, `es_fila_por_defecto`, `inventario_protecciones`,
  `criterios_de_perfil`. Contrato en `schemas/protecciones_v1.schema.json`.
- La referencia de Python de PF 2024 (`PythonReference_en.pdf`, 5.4.33) documenta `ComProtgraphic` solo
  para refrescar páginas de gráficos: no se toma como prueba de coordinación. Las órdenes exigidas son
  `ComShc` y `ComShctrace` (5.4.43, 5.4.44), con sus métodos documentados.
- Libro de la empresa: hoja «Protecciones» (`datos_empresa.py`) con procedencia por fila; perfil:
  `protecciones.cti_s`, `factor_sensibilidad`, `margen_poder_corte` (esquema, plantilla, guía), sin valor
  de referencia. El catálogo de estudios lista las protecciones con la lista concreta de lo que falta.
- `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_datos.py tests/test_estudios_pf.py
  tests/test_datos_empresa.py`: 56 aprobadas, 0 omitidas. Regresiones de los módulos tocados:
  `tests/test_entrega_universal.py tests/test_asistente_maestro.py` (282 aprobadas con las anteriores),
  `tests/test_inventario.py tests/test_arquitectura_generada.py tests/test_perfil_empresa.py` en verde.
- Limitación: hoy ninguna fuente trae dispositivos ni impedancia real de cabecera, así que el resultado en
  cualquier proyecto es «bloqueado» con la lista; eso es lo esperado (RF-2), no un fallo.

T2 (RF-4, RF-8), 2026-11-06, misma rama. Sin DIgSILENT: el guion se prueba contra `tests/fake_pf.py`,
que imita lo documentado en la referencia de PF 2024 (`ComShc.GetFaultType`, `ComShctrace`,
`ElmRelay.GetMaxFdetectCalcI`). Estas pruebas no cierran la evidencia nativa, que es la T4.

- `protecciones.plan_protecciones(contexto, inventario, fallas)`: identidad del caso
  (`ContextoExperimento` y su clave), fallas con barra, tipo, fase e impedancia, la generación del caso
  con su estado (una central como carga negativa se rechaza) y los ajustes solo en la variación
  `CSG049_ajustes`, nunca en el «Caso base».
- `tools/protecciones_pf.py`: `--capacidades` (órdenes, métodos documentados, atributos de `ComShc` con
  `HasAttribute`, licencia del cortocircuito ejecutándolo, dispositivos y generación) y la ejecución de
  fallas con la traza (`GetDeviceTime` al arrancar, disparos y secuencia paso a paso), `ComShc` y el caso
  restituidos, cada falla independiente y cancelable entre fallas.
- Por confirmar en la T4 con DIgSILENT real: los atributos de `ComShc` con que se define la falla
  (`shcobj`, `iopt_shc`, `Rf`, `Xf`, `iopt_allbus`) no están en la referencia; el guion no los escribe si el
  modo de capacidades no los comprobó, y relee el tipo con `GetFaultType`. La fase de una falla monofásica
  se lleva en el plan y el informe, pero no se escribe en `ComShc` hasta conocer su atributo.
- `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_pf_guion.py tests/test_protecciones_datos.py`:
  32 aprobadas, 0 omitidas. `tests/test_inventario.py` (con `--help` del guion nuevo) y
  `tests/test_arquitectura_generada.py` en verde.

T3 (RF-5 a RF-7, RF-10), 2026-11-06, misma rama. Sin DIgSILENT: la web se prueba con un guion falso.

- `protecciones.evaluar_coordinacion(resultados, inventario, perfil)`: por pareja primaria-respaldo
  (`respalda_a`) y falla, `t_respaldo − t_primaria ≥ protecciones.cti_s`; sensibilidad con el arranque en
  amperios primarios (relación del TC) frente a `factor_sensibilidad`; poder de corte frente a la mayor
  corriente vista por `margen_poder_corte`. Estados `cumple`, `no_cumple`, `parcial` (una falla o un
  criterio sin evaluar) y `bloqueado` (ninguna falla evaluada). `escribir_reporte` (JSON y tres CSV, iguales
  byte a byte) y `comparar_casos` (solo «Sin proyecto» con «Con proyecto» del mismo proyecto, alimentadores,
  fuente, año, periodo y perfil).
- Web: `GET /api/workspaces/{wid}/pf/protecciones` (disponibilidad con lo que falta, capacidades,
  evaluaciones, comparación y el aviso de que un flujo convergente no es selectividad),
  `POST …/protecciones/capacidades` y `POST …/protecciones/ejecutar` (trabajos del carril de DIgSILENT; con el
  estudio bloqueado, 400 con la lista y nada encolado). Apartado «Protecciones» en `EstudiosPF.tsx`.
- `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_coordinacion.py tests/test_protecciones_web.py`:
  25 aprobadas, 0 omitidas. `npx tsc --noEmit -p .` y `npm run build` en `frontend/` sin errores; contrato de la
  API regenerado (`tools/generar_contrato_api.py`).
- RF-9 queda para la T4: el guion marca los ajustes escritos como `persistencia: sin_verificar` y
  `test_ajuste_no_toca_base` comprueba que no se dan por persistidos sin reabrir y releer; esa prueba no
  acredita la persistencia.
- Pendiente fuera del código: revisar el apartado en el navegador real con datos completos e incompletos
  (no se reinició la web del 8765) y la T4 con DIgSILENT real. Las curvas tiempo-corriente gráficas no se
  dibujan: `ComProtgraphic` solo refresca páginas de PF y ninguna fuente trae curvas; el reporte da los
  tiempos y márgenes en tabla.
