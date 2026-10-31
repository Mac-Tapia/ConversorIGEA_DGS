# Gemelo físico y contratos PINN/GNN — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Hacer explícita y comprobable la física que el gemelo aprende sobre la red y sus controles reales.

**Architecture:** Versionar episodios y grafo conservando lectura histórica inmutable. Mantener el oráculo híbrido actual como referencia e incorporar representaciones/adaptadores solo donde describen los equipos capturados.

**Tech Stack:** Python 3.12, JSON Schema, NumPy, PyTorch/CUDA; PyG opcional tras benchmark.

**Spec:** [spec.md](spec.md). Dependencias: 043 y 044; preservar reglas y casos de 025, 032 y 037–042.

## Global Constraints

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `045:RF-n`; no cerrar tareas nativas con mocks.

## Review Focus

- Episodio v1 reescrito por migración: T1, test_v1_lectura_no_cambia_hash.
- Cargas nuevas confundido con obras aceptadas: T1, test_cargas_nuevas_es_diagnostico.
- Frontera angular flotante o isla desenergizada: T2, test_referencia_por_componente.
- Toma/shunt/adaptación automática no representados: T2, test_fisica_incompleta_bloquea.
- Red nueva con intervalo estrecho: T3, test_fuera_dominio_no_se_acepta.

---

### T1: Versionar episodios, contexto y grafo

**Cubre:** RF-1, RF-2, RF-3, RF-10.

**Files:** Modificar `digital_twin/episode.py`, `buffer.py`, `integration.py` y `native_snapshot.py`; crear `schemas/digital_twin_episode_v2.schema.json`, `digital_twin/contratos_fisicos.py` y `tests/test_gemelo_contratos_v2.py`; conservar schema v1.

**Interfaces:** Añadir `Caso.CARGAS_NUEVAS='cargas_nuevas'`; nuevos episodios usan `igea-dgs-digital-twin-episode-v2`. `validar_alcance_fisico(grafo: Mapping) -> tuple[str, ...]` y `contexto_fisico(snapshot: Mapping) -> dict` viven en contratos_fisicos.py. Grafo versión 3 separa inyección/carga, generadores, bancos, tomas, modelo de carga, fase, estado, fuentes y base de unidades; hashes enlazan ContextoExperimento. Guardar ComLdf/iopt_lev, consignas escritas y resultados efectivos sin sustituirlos entre sí.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_v1_lectura_no_cambia_hash`; `test_cargas_nuevas_es_diagnostico`: nunca aceptado como obra; `test_controles_y_casos_no_se_mezclan`: variar criterio_fijas, banco, central, toma o caso cambia contexto. No inventar valores de controles ausentes.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_contratos_v2.py tests/test_digital_twin_episode.py tests/test_digital_twin_buffer.py tests/test_digital_twin_snapshot_pf.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 045 T1`.

### T2: Física representada y fronteras comprobables

**Cubre:** RF-4, RF-5, RF-6, RF-7.

**Files:** Modificar `digital_twin/oraculo.py` y `digital_twin/flujo.py`; ampliar contratos_fisicos.py; crear `tests/test_pinn_fisica_y_fronteras.py`.

**Interfaces:** `perdidas_fisicas(prediccion: Mapping, muestra: Muestra, *, pesos: Mapping) -> dict` informa datos/fisica/fronteras/total con unidades normalizadas. Mantener predecir(grafo)->dict del oráculo. Representar ramas con admitancias/tomas/shunts cuando estén capturadas y contrastadas; bloquear otras. Fijar una referencia angular coherente por componente; conservar magnitudes impuestas de fuentes y relaciones de controles conocidas. Modelo equilibrado se declara como tal, sin extrapolar a secuencias o fases.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_referencia_por_componente`: magnitud fuente exacta y ángulo de referencia exacto; `test_gradiente_residuo_diferencias_finitas`: float64, red pequeña, rtol=1e-4 y atol=1e-6 lejos de singularidades; `test_fisica_incompleta_bloquea`: atributo de control faltante no se aproxima en silencio; `test_isla_desenergizada_no_recibe_gold_cero`. Añadir red radial, mallada y acopladores.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_pinn_fisica_y_fronteras.py tests/test_digital_twin_flujo.py tests/test_digital_twin_in111_ta225.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 045 T2`.

### T3: Ablaciones, dominio y candidato opcional PyG

**Cubre:** RF-8, RF-9.

**Files:** Crear `digital_twin/benchmark_fisico.py`, `digital_twin/adaptador_pyg.py` opcional y `tests/test_benchmark_pinn.py`; integrar informes en runner de 043.

**Interfaces:** `comparar_fisicas(experimento: ExperimentoSpec, particiones: Particiones) -> dict` evalúa física pura, red con peso_fisico=0, híbrido vigente y candidato PyG sobre IDs idénticos. `comprobar_dominio(grafo: Mapping, model_manifest: Mapping) -> dict` produce dentro/bloqueos antes de inferir para optimización. Registrar residuos y términos por época, error por familia, latencia y VRAM. Nuevo algoritmo sigue etapa pinn.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_ablaciones_comparten_ids`: particiones y presupuesto coinciden; `test_fuera_dominio_no_se_acepta`: cambio no soportado impide aceptar; `test_pyg_ausente_no_rompe_base`: referencia actual sigue disponible. Ejecutar ablación real CUDA con artefactos reabiertos y las puertas 044; no medir mejora con redes ficticias únicamente.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_pinn.py tests/test_digital_twin_oraculo.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 045 T3`.

### T4 [DIgSILENT]: Contraste del gemelo con la red nativa

**Cubre:** RF-11.

**Files:** Usar `tools/escenarios_pf.py --plan RUTA --output-json RUTA` por el carril/armazón actual; ampliar `tests/test_gemelo_fisico_nativo.py` y captura existente sin segunda conexión independiente.

**Interfaces:** El plan nativo lo genera el servicio actual desde el vínculo de fuente; comprobar que la copia aislada conserva centro de generación y bancos, roles de caso, año y criterio de fijas. Guardar etiquetas solo cuando existan resultados válidos; la convergencia con violaciones puede producir dato físico etiquetado como tal, nunca diseño aceptado.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_contraste_nativo_cuatro_casos`: todos los roles solicitados se releen explícitamente; `test_central_y_bancos_persisten`: inventario previo/posterior coincide salvo acciones declaradas. Para NA203–NA205 respetar el diagnóstico cliente-SED y la central existente; no dimensionar transformadores con la sola ficha normativa.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_fisico_nativo.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 045 T4`.

## Cierre y evidencia

Al ejecutar, actualizar [tasks.md](tasks.md) con comandos, resultado, hashes y rutas
de informe; mantener abiertas las condiciones sin evidencia. El estado se escribe
solo en spec.md y se refleja mediante `tools/estado_specs.py --escribir`. Validar
trazabilidad además de las pruebas de cada tarea; no cerrar otras specs por arrastre.

