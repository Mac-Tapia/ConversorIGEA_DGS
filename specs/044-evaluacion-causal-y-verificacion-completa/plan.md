# Evaluación causal y verificación completa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Impedir aceptación por particiones contaminadas, métricas ausentes o una media que oculta regresiones.

**Architecture:** Centralizar política, particiones y comparación de candidatos. Adaptar las funciones existentes de entrenamiento y verificación para consumir el mismo contexto y la evaluación eléctrica existente.

**Tech Stack:** Python 3.12, NumPy, PyTorch y arnés PowerFactory existente.

**Spec:** [spec.md](spec.md). Dependencias: 043; solo T0 puede adelantarse sin contratos nuevos.

## Global Constraints

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `044:RF-n`; no cerrar tareas nativas con mocks.

## Review Focus

- Copias de un episodio en splits distintos: T1, test_cuatro_particiones_sin_solape.
- Calibración vacía o umbral elegido tras ver prueba: T1–T2, test_sin_calibracion_bloquea.
- Familia pequeña que empeora con mejor media global: T2, test_regresion_familia_rechaza.
- NaN/None o pérdidas cero: T3, test_top_k_sin_metricas_rechaza y test_perdida_cero_no_oculta_error.
- Medición de otro año o caso: T3–T4, test_top_k_contexto_distinto_rechaza.

---

### T0: Rechazar inmediatamente métricas ausentes en el auxiliar actual

**Cubre:** RF-6 en el auxiliar; T3 completa su aplicación a todos los consumidores.

**Files:** modificar únicamente `digital_twin/evolutivo.py:verificar_top_k` y crear
`tests/test_verificacion_top_k_completa.py` con citas `044:RF-6`.

**Interfaces:** conservar la firma pública actual de `verificar_top_k`; validar
predicción y medición antes de calcular diferencias, sin depender de clases de 043.
La falta de `v_min` o `perdidas_kw`, un valor no finito o una pérdida negativa
descarta esa alternativa con motivo explícito; no fabricar ceros.

- [x] Escribir primero `test_top_k_sin_metricas_rechaza` con el reproductor:

  ```python
  resultado = verificar_top_k(
      [{'id': 'x'}], lambda _: {'converge': True}, tolerancia_v_pu=0.01)
  assert resultado['verificada'] is False
  assert resultado['elegida'] is None
  assert resultado['descartadas'][0]['motivo']
  ```

  Parametrizar ausencia y NaN/Inf en cada métrica, y pérdida negativa; una medición
  completa válida conserva el comportamiento anterior hasta la integración T3.
- [x] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_completa.py`
  y observar el fallo actual `True is False`.
- [x] Añadir el rechazo local de incompletitud/no finitud sin cambiar firma ni
  introducir puertas eléctricas parciales como sustituto de T3.
- [x] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_completa.py tests/test_digital_twin_evolutivo.py`
  hasta PASS y comprobar sus consumidores por posibles dependencias del comportamiento defectuoso.
- [x] Registrar evidencia y commit propio que cite `spec 044 T0`; no marcar T3 ni
  la spec completa por esta corrección puntual.

### T1: Particiones independientes y política previa

**Cubre:** RF-1, RF-2, RF-3.

**Files:** Crear `src/convertersmartgrid/evaluacion_modelos.py`, `tests/test_evaluacion_modelos.py`; modificar `digital_twin/oraculo.py:particionar`, `_grupos` y consumidores del donante.

**Interfaces:** `Particiones` contiene `entrenamiento`, `seleccion`, `calibracion`, `prueba` como tuplas de IDs; `PoliticaEvaluacion` contiene `schema_version`, `modo` (por_sistema/generalizacion), `min_calibracion_grupos`, `cobertura_objetivo`, `puertas_por_familia`, `semillas` y hash sellado. `particionar_registros(registros: Sequence[Mapping], politica: PoliticaEvaluacion) -> Particiones`. Requerir mínimos existentes 30/10/10 por sistema y mínimo de calibración positivo declarado; el modo generalizacion además retiene sistemas enteros fuera.

Para el currículo del agente (047 T5), se admite modo `agente` con mínimos de grupos
explícitos por partición, sin atribuir generalización a otros sistemas eléctricos.
La asignación de familias de plantillas se declara antes de generar ejemplos y el
particionador la valida; no divide filas hermanas al azar. No altera las cuotas
eléctricas del modo por_sistema ni cierra su integración pendiente en el PINN.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_cuatro_particiones_sin_solape`: intersecciones de IDs y grupos vacías; `test_sin_calibracion_bloquea`: mínimo no declarado o grupo insuficiente da BLOQUEADO_POR_DATOS; `test_modo_por_sistema_no_finge_generalizacion`: informar alcance sin exigir sistema externo en el modo autorizado por 027:RF-68. Usar cortes temporales para series y grupos hermanos para episodios.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_evaluacion_modelos.py tests/test_digital_twin_particiones.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 044 T1`.

### T2: Calibración y puertas por familia

**Cubre:** RF-4, RF-5, RF-8.

**Files:** Modificar `digital_twin/oraculo.py:entrenar`, `calibrar_conforme`, informes y comparación del donante; ampliar `evaluacion_modelos.py`; crear `tests/test_calibracion_independiente.py`.

**Interfaces:** `evaluar_candidato(metricas: Mapping, politica: PoliticaEvaluacion) -> dict` produce `approved`, `gates`, `bloqueos`, métricas globales y por familia. Conservar 0.005 pu, 0.05 y 1.05 como puertas iniciales PINN; exigir comparación por familia contra física y activo según política sellada. Selección gobierna parada; calibración calcula cuantiles; prueba solo mide. Reportar cobertura objetivo inicial 0.90, cobertura empírica, tamaño y método de agrupamiento; no prometer garantía IID sobre nodos correlacionados.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_calibrador_no_ve_seleccion_ni_prueba`: recibe exactamente IDs de calibración; `test_regresion_familia_rechaza`: media mejor con una familia fuera de puerta conserva activo anterior; `test_intervalos_reportan_denominador`: cobertura lleva n y agrupación. Un informe sin intervalos justificables no publica falsa cobertura.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_calibracion_independiente.py tests/test_digital_twin_oraculo.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 044 T2`.

### T3: Cerrar la verificación parcial de alternativas

**Cubre:** RF-6, RF-7.

**Files:** Modificar `digital_twin/evolutivo.py:verificar_top_k` y sus llamadas; reutilizar `digital_twin/evaluacion.py:evaluar`; crear `tests/test_verificacion_top_k_completa.py` y ampliar regresiones evolutivas/web.

**Interfaces:** Crear `validar_medicion_nativa(prediccion: Mapping, medicion: Mapping, contexto: ContextoExperimento, *, politica: Mapping) -> dict` en `evaluacion_modelos.py`; valida esquema, contexto, unidades y completitud antes de comparar. `verificar_top_k` conserva las claves públicas y devuelve `verificada=False` con motivos cuando falte información. Los llamadores pasan flujo completo, referencia, límites, evidencia de reapertura y calibración a `evaluar`; no basta converge=True.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_top_k_sin_metricas_rechaza`: alternativas=[{'id':'x'}], medir=lambda _: {'converge': True} debe dar verificada=False (hoy da True); `test_top_k_nan_rechaza` para cada métrica; `test_perdida_cero_no_oculta_error`: usar diferencia absoluta predeclarada cuando referencia sea cero; `test_top_k_contexto_distinto_rechaza`: año/caso/fuente distintos bloquean. No convertir ausencias en 0.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_completa.py tests/test_digital_twin_evolutivo.py tests/test_digital_twin_evaluacion.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 044 T3`.

### T4 [DIgSILENT]: Persistencia y aceptación en el motor real

**Cubre:** RF-9.

**Files:** Usar rutas de trabajos actuales y `tools/powerfactory_acceptance.py`; añadir evidencia de integración real en `tests/test_verificacion_top_k_nativa.py`.

**Interfaces:** Consumir informes completos de T3 y `ContextoExperimento` de 043. Verificar candidata aplicada, guardada y reabierta mediante el arnés; guardar informe nativo y hashes de entrada/referencia antes y después. No escribir scripts paralelos de acceso PowerFactory.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  Con datos reales y dependencia nativa obligatoria, `test_top_k_nativo_reabre_y_relee` confirma controles y resultados tras nueva sesión; caso convergente con sobrecarga queda rechazado eléctricamente; sin licencia disponible el requisito permanece pendiente, sin skip que lo cierre.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_nativa.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 044 T4`.

## Cierre y evidencia

Al ejecutar, actualizar [tasks.md](tasks.md) con comandos, resultado, hashes y rutas
de informe; mantener abiertas las condiciones sin evidencia. El estado se escribe
solo en spec.md y se refleja mediante `tools/estado_specs.py --escribir`. Validar
trazabilidad además de las pruebas de cada tarea; no cerrar otras specs por arrastre.

