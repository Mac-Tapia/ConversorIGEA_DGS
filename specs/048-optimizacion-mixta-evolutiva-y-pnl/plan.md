# Optimización mixta evolutiva y PNL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Comparar y mejorar búsqueda de obras y consignas con variables físicas admisibles y aceptación nativa completa.

**Architecture:** Adaptadores del optimizador actual, pymoo y PNL continua sobre un contrato de problema común. La búsqueda propone; el top-k verificado mediante el arnés decide viabilidad y el registro conserva todo el contexto.

**Tech Stack:** Python 3.12, algoritmos actuales, pymoo opcional, Pyomo/Ipopt opcionales y PowerFactory.

**Spec:** [spec.md](spec.md). Dependencias: 043, 044 y 045; 046 opcional para escenarios; consumir escalera/SET nueva de 042 sin duplicarla.

## Global Constraints

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `048:RF-n`; no cerrar tareas nativas con mocks.

## Review Focus

- Banco 1.4 o interruptor entre estados: T1, test_variables_discretas_no_fraccionan.
- Caché entre años/criterios/modelos: T1, test_cache_incluye_contexto_y_modelo.
- Optimización mejora objetivo por desconectar cargas: T1, test_isla_invalida_no_es_factible.
- Presupuesto por generaciones diferente entre algoritmos: T2, test_presupuesto_es_evaluaciones.
- Salida local sin convergencia KKT o aceptación nativa: T3–T4, test_pnl_no_declara_optimo_global.

---

### T1: Problema mixto y caché con contexto

**Cubre:** RF-1, RF-2, RF-5.

**Files:** Crear `digital_twin/problema_optimizacion.py`, `tests/test_problema_optimizacion.py`; adaptar llamadas de `digital_twin/evolutivo.py`.

**Interfaces:** `ProblemaOptimizacion` contiene variables tipadas, cotas, unidades, restricciones, objetivos, ContextoExperimento y modelo_id. `evaluar_vector(problema: ProblemaOptimizacion, vector: Mapping) -> dict` retorna factible/objetivos/violaciones con flujo de referencia y cargas atendidas. `clave_evaluacion(problema, vector: Mapping, politica_hash: str) -> str` incluye todos los hashes del experimento. Catálogos y coste salen de perfiles/fuentes trazables, no de nombres fijos.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_variables_discretas_no_fraccionan`: rechaza etapas no enteras o equipo inexistente; `test_cache_incluye_contexto_y_modelo`: año/criterio/modelo distinto invalida; `test_isla_invalida_no_es_factible`: desconectar demanda no mejora factibilidad; `test_sin_coste_no_inventa_cero`.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_problema_optimizacion.py tests/test_digital_twin_evolutivo.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 048 T1`.

### T2: Benchmark de algoritmos actuales y pymoo

**Cubre:** RF-3, RF-6, RF-8.

**Files:** Crear `digital_twin/adaptador_pymoo.py`, `digital_twin/benchmark_optimizacion.py` y `tests/test_benchmark_optimizacion.py`; conectar runner etapa evolutivos.

**Interfaces:** `comparar_optimizadores(problemas: Sequence[ProblemaOptimizacion], *, semillas: tuple[int, ...], presupuesto: int, cancelado: Callable[[], bool]) -> dict` usa >=20 semillas, presupuesto en evaluaciones reales/consultas cacheadas informadas aparte y mismo criterio de reparación. Comparar genético, NSGA-II, DE vigentes y candidatos compatibles con el dominio; hypervolumen con objetivos normalizados y punto de referencia predeclarados.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_presupuesto_es_evaluaciones`: poblaciones distintas gastan igual máximo de evaluaciones; `test_cancelacion_no_publica_optimo`: guarda estado parcial; `test_semillas_comunes`: misma lista y problemas; ejecutar benchmark real local con métricas por problema y CI por semilla, sin inferir resultado de pruebas pequeñas.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_optimizacion.py tests/test_digital_twin_evolutivo.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 048 T2`.

### T3: PNL continua y selección top-k

**Cubre:** RF-4, RF-7.

**Files:** Crear `digital_twin/adaptador_pnl.py`, `tests/test_adaptador_pnl.py`; conectar `verificar_top_k` corregido y servicios actuales.

**Interfaces:** `resolver_continuo(problema: ProblemaOptimizacion, *, discretas_fijas: Mapping, opciones_solver: Mapping) -> dict` construye Pyomo/Ipopt solo con variables continuas restantes, informa estado/tolerancias/residuos/iniciales. Enumerar un caso discreto diminuto con óptimo conocido para probar el adaptador, sin extrapolar a redes reales. Usar top-k configurable (valor inicial 3), secuencial y verificación 044 completa.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_pnl_no_declara_optimo_global`: resultado rotulado local_continuo; `test_discretas_se_fijan`: nunca relaja equipos; `test_solver_ausente_no_rompe_algoritmos`: ERROR_ENTORNO solo candidato PNL; ejecutar prueba con solver real y caso conocido, sin mock que cierre compatibilidad.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_adaptador_pnl.py tests/test_verificacion_top_k_completa.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 048 T3`.

### T4 [DIgSILENT]: Aplicación en variaciones y reapertura nativa

**Cubre:** RF-9.

**Files:** Reutilizar `obras_pf.py`, `tools/obras_pf.py`, servicios y arnés existentes; crear `tests/test_optimizacion_mixta_nativa.py`.

**Interfaces:** Las propuestas usan las variaciones y validadores vigentes de 025/042; solo aplicar candidato tras 044. Guardar referencia inmutable, manifiesto de obras, costes con custodia y readback. Ejecutar en carril único; el LLM no escribe ajustes ni aprueba diseños.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_obras_persisten_sin_tocar_referencia`: comparar snapshot Sin proyecto antes/después y Con proyecto reabierto; `test_demanda_no_cae_artificialmente`: controles efectivos y cargas atendidas corresponden al diseño. Convergencia sin tensión/cargabilidad admisible no cierra tarea.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_optimizacion_mixta_nativa.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 048 T4`.

## Cierre y evidencia

Al ejecutar, actualizar [tasks.md](tasks.md) con comandos, resultado, hashes y rutas
de informe; mantener abiertas las condiciones sin evidencia. El estado se escribe
solo en spec.md y se refleja mediante `tools/estado_specs.py --escribir`. Validar
trazabilidad además de las pruebas de cada tarea; no cerrar otras specs por arrastre.

