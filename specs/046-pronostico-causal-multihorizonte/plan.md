# Pronóstico causal multihorizonte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Corregir la fuga de normalización de GRU y comparar pronósticos temporales con un contrato causal común.

**Architecture:** Preparación temporal común y adaptadores de modelos bajo demanda. El modelo estacional y GRU son referencias obligatorias frente a NHITS, TFT y PatchTST; los resultados se separan por horizonte y contexto.

**Tech Stack:** Python 3.12, PyTorch/CUDA, NeuralForecast opcional, JSON de experimento.

**Spec:** [spec.md](spec.md). Dependencias: 043 y 044; lectura de medición existente y crecimiento de 029 conservados.

## Global Constraints

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `046:RF-n`; no cerrar tareas nativas con mocks.

## Review Focus

- Pico posterior cambia la escala pasada: T1, test_escala_usa_solo_entrenamiento.
- Hueco de medición contado como 0: T1, test_hueco_no_es_cero.
- Clima futuro medido filtrado como conocido: T1, test_covariable_sin_asof_se_excluye.
- Horizonte 96 con cadencia horaria: T2, test_horizonte_exige_cadencia.
- Intervalos q10/q90 etiquetados 90%: T3, test_cuantiles_y_cobertura_coherentes.

---

### T1: Preparación causal y corrección de GRU

**Cubre:** RF-1, RF-2, RF-3.

**Files:** Modificar `digital_twin/temporal.py:GemeloGRU.entrenar`; crear `digital_twin/series_causales.py` y `tests/test_series_causales.py`; conservar lectores de medición.

**Interfaces:** `preparar_serie(registros: Sequence[Mapping], *, corte: str, cadencia_min: int, zona_horaria: str, covariables: Mapping) -> dict` devuelve filas, máscaras, disponibilidad_asof y transformaciones ajustadas solo con entrenamiento. Definir cortes sobre objetivos antes de ventanas para evitar targets compartidos entre splits; purgar solapes conforme al horizonte. GemeloGRU mantiene su interfaz pública.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_escala_usa_solo_entrenamiento`: añadir un pico en validación no cambia escala de train; `test_hueco_no_es_cero`: ausencia conserva máscara; `test_covariable_sin_asof_se_excluye`: valor publicado después de emisión nunca entra. Verificar timestamps duplicados, cambios de zona y unidades kW/MW.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_series_causales.py tests/test_digital_twin_temporal.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 046 T1`.

### T2: Adaptadores y salida multihorizonte

**Cubre:** RF-4, RF-5.

**Files:** Crear `digital_twin/pronostico.py`, `digital_twin/adaptador_neuralforecast.py` y `tests/test_pronostico_multihorizonte.py`; ampliar `tools/digital_twin_temporal_entrenar.py` con config compartida.

**Interfaces:** `pronosticar(contexto: Mapping, *, horizontes: tuple[int, ...], algoritmo: str) -> list[dict]` devuelve target, emission_time, forecast_time, horizon_steps, cadence_min, q05, q50, q95. Horizontes iniciales (1,4,96) solo para cadencia confirmada de 15 minutos; exigir otra configuración explícita si cambia. Adaptadores gru/nhits/tft/patchtst usan la misma estructura y etapa histórica gru con algorithm diferenciado.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_horizonte_exige_cadencia`: 96 pasos no se rotulan un día con cadencia horaria; `test_ventanas_identicas_por_modelo`: los targets de prueba son iguales; `test_adaptador_opcional_no_rompe_gru`: ausencia NeuralForecast bloquea solo ese candidato. Entrenar con CUDA, sin fallback CPU.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_multihorizonte.py tests/test_digital_twin_temporal.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 046 T2`.

### T3: Benchmark, calibración y promoción temporal

**Cubre:** RF-6, RF-7, RF-8.

**Files:** Crear `digital_twin/evaluacion_temporal.py` y `tests/test_evaluacion_temporal.py`; integrar RegistroModelo, PoliticaEvaluacion y reportes existentes.

**Interfaces:** `evaluar_pronosticos(real: Sequence[Mapping], predicciones: Sequence[Mapping], *, politica: PoliticaEvaluacion) -> dict` informa MAE/RMSE/error de pico/pinball/cobertura por contexto y horizonte. Intervalo inicial 90% corresponde a q05/q95. Incertidumbre y comparaciones se agrupan por día/semana; no tratar nodos/ventanas solapadas como muestras independientes. Promover solo tras puertas y reapertura real del artefacto.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_cuantiles_y_cobertura_coherentes`: q05<=q50<=q95 y cobertura con n; `test_empate_conserva_activo`: empate sin ventaja predeclarada no promueve; `test_error_por_horizonte_no_se_oculta`: media buena no oculta pico u horizonte fuera de puerta. Ejecutar benchmark real de ventanas posteriores y dejar BLOQUEADO_POR_DATOS donde no alcance.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_evaluacion_temporal.py tests/test_pronostico_multihorizonte.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 046 T3`.

### T4: Objetivos de cabecera y de clientes fijos

**Cubre:** RF-9, RF-10, RF-11, RF-12.

**Files:** Ampliar `demanda_medida.py` con `curvas_de_clientes`, que comparte con `registros_de_maxima` la lectura de «maestro_lib» y de las columnas (`_hojas_de_maestro`), y `digital_twin/temporal_entrenamiento.py` con `objetivos_de_cabecera`, `objetivos_de_clientes` e `inventariar`. Cabecera: `maximas` y `curva_de_demanda`, sin otro lector. Pruebas en `tests/test_pronostico_objetivos.py`.

Un cliente se reparte en libros mensuales del mismo origen: se unen sus meses, y dos valores distintos del mismo instante apartan al objetivo. Decisión: unir aquí no mezcla fuentes (TXT/MDB/VNR son las fuentes; los libros son meses de una medición); descartada: leer un solo mes, que no llega a 30 días.

### T5: Competición y ganador por objetivo

**Cubre:** RF-13, RF-14, RF-15, RF-16, RF-17, RF-18.

**Files:** `digital_twin/pronostico.py` (referencias, ventanas, contrato), `digital_twin/adaptador_neuralforecast.py`, `GemeloGRUMultihorizonte` en `digital_twin/temporal.py`, `comparar_pronosticos` en `temporal_entrenamiento.py` y decisión en `evaluacion_temporal.py`. Reutiliza `particionar_registros`, `verificar_familias` y `RegistroModelo`. Pruebas en `tests/test_pronostico_competicion.py` y, con CUDA, `tests/test_pronostico_gpu.py`.

El ganador neuronal de un objetivo se elige en selección y solo él se juzga en prueba: elegirlo en prueba daría un error optimista. Descartada: un único ganador global, porque un cliente fijo y una cabecera no tienen la misma forma.

### T6: Artefacto e integración opcional

**Cubre:** RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-25.

**Files:** `pronostico.json` por trabajo; `tools/digital_twin_temporal_entrenar.py --comparar`, `tools/reentrenar_modelos.py`, `modo: pronostico` en la ruta `/digital-twin/temporal`, `services.gemelo_pronostico`, paso del asistente en `asistente/ejecutor.py`. Pruebas en `tests/test_pronostico_integracion.py`, con una guarda por importaciones: calibración, informes, crecimiento y guiones de DIgSILENT no importan el pronóstico.

### T7: Medición real en GPU

**Cubre:** RF-5, RF-6, RF-7, RF-8, RF-13, RF-16, RF-17, RF-18.

Ejecutar `--comparar` con medición real en el turno de GPU que asigne el integrador; guardar el informe fuera de git. Sin ese turno no se declara ni modelo ganador ni promoción.

## Cierre y evidencia

Al ejecutar, actualizar [tasks.md](tasks.md) con comandos, resultado, hashes y rutas
de informe; mantener abiertas las condiciones sin evidencia. El estado se escribe
solo en spec.md y se refleja mediante `tools/estado_specs.py --escribir`. Validar
trazabilidad además de las pruebas de cada tarea; no cerrar otras specs por arrastre.

