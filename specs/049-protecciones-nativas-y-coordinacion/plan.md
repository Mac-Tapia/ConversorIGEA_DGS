# Protecciones nativas y coordinación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Implementar un estudio verificable de protecciones donde existan datos y licencia, con bloqueo explícito en los demás casos.

**Architecture:** Ampliar el catálogo y el trabajo nativo existentes con disponibilidad real y un contrato de ajustes/fallas. Comparar tiempos de primaria y respaldo con reglas del perfil; producir reportes vinculados al caso, sin inferir selectividad a partir del flujo.

**Tech Stack:** Python 3.12, PowerFactory por arnés, curvas y fichas empresariales/fabricante, React y reportes tabulares.

**Spec:** [spec.md](spec.md). Dependencias: 043–045; catálogo de estudios y datos de empresa existentes; 048 solo si se optimizan ajustes.

## Global Constraints

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `049:RF-n`; no cerrar tareas nativas con mocks.

## Review Focus

- Comando presente sin módulo licenciado: T1, test_sin_curvas_o_licencia_bloquea.
- Fila DEFAULT con poder de corte cero: T1, test_default_no_es_ficha_real.
- CT/VT o tiempos en unidades incompatibles: T2, test_unidades_y_relaciones_requeridas.
- Central térmica existente no incluida en falla: T2–T4, test_generacion_existente_aporta.
- Solo una falla da apariencia de coordinación global: T3, test_falla_no_evaluada_no_aprueba.

---

### T1: Disponibilidad real e inventario de entradas

**Cubre:** RF-1, RF-2, RF-3.

**Files:** Crear `src/convertersmartgrid/protecciones.py`, `schemas/protecciones_v1.schema.json`, `tests/test_protecciones_datos.py`; modificar `studies.py`, `datos_empresa.py` y disponibilidad en `estudios_pf.py`.

**Interfaces:** `disponibilidad_protecciones(inventario: Mapping, capacidades: Mapping, perfil: Mapping) -> dict` informa disponible/faltan/bloqueos/alcance. Contrato: ID estable dispositivo/cubículo, fabricante/modelo, curva, pickup y unidad, dial/retardo y unidad, CT/VT cuando aplique, dirección, capacidad de interrupción y fuente documental. Datos de secuencia/cortocircuito y conexión a tierra obligatorios según fallas pedidas. No adoptar ComProtgraphic como prueba universal de auditoría: verificar API/documentación de la versión conectada.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_sin_curvas_o_licencia_bloquea`: ausencias concretas visibles; `test_default_no_es_ficha_real`: DEFAULT/InterruptingRating=0 no habilita; `test_capacidad_por_version`: función anunciada en PF2026 no se supone en PF2024/2025. Preservar comportamiento de estudios actuales.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_datos.py tests/test_estudios_pf.py tests/test_datos_empresa.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 049 T1`.

### T2: Escenarios de falla y captura nativa

**Cubre:** RF-4, RF-8.

**Files:** Crear `tools/protecciones_pf.py`, adaptar `pf_arnes.py`, servicios y despachador existentes; crear `tests/test_protecciones_pf_guion.py` con datos de contrato y pruebas de construcción.

**Interfaces:** `plan_protecciones(contexto: ContextoExperimento, inventario: Mapping, fallas: Sequence[Mapping]) -> dict` usa identidad nativa, ubicación/fase/impedancia de falla, caso/año, escenarios de generación y perfiles. El guion usa el arnés existente y comandos documentados/verificados; una primera tarea de capacidades genera inventario de métodos/atributos soportados antes de programar ejecución. Capturar tiempos, dispositivo que opera, secuencia y estado; ajustes candidatos solo en copia/variación.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_generacion_existente_aporta`: el plan conserva central/generadores y estados, no los reemplaza por demanda negativa sin modelo de falla; `test_unidades_y_relaciones_requeridas`: rechaza relación o unidad ausente; `test_ajuste_no_toca_base`: plan de escritura restringido a variación. Las pruebas del guion no cierran la evidencia nativa T4.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_pf_guion.py tests/test_protecciones_datos.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 049 T2`.

### T3: Coordinación, reporte y web

**Cubre:** RF-5, RF-6, RF-7, RF-10.

**Files:** Ampliar `protecciones.py`; modificar trabajos de `web/services.py` y `web/app.py`, `frontend/src/components/EstudiosPF.tsx`, tipos/API; crear `tests/test_protecciones_coordinacion.py` y `tests/test_protecciones_web.py`.

**Interfaces:** `evaluar_coordinacion(resultados: Sequence[Mapping], inventario: Mapping, perfil: Mapping) -> dict` evalúa t_respaldo-t_primaria>=CTI requerido por pareja/falla, sensibilidad y capacidad de interrupción; CTI y márgenes no tienen valor empresarial fijo en código. Salida lista dispositivos, fallas, tiempos, márgenes, violaciones y no_evaluados con razones. Reporte JSON/CSV y curvas tiempo-corriente cuando disponibles; comparación Sin/Con proyecto solo entre contextos compatibles.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_falla_no_evaluada_no_aprueba`: cobertura parcial se declara parcial; `test_cti_incumplido_rechaza`: un tiempo primario/respaldo fuera de margen no pasa aunque fluya; `test_poder_corte_insuficiente_rechaza`; `test_web_muestra_dato_faltante`: estudio bloqueado explica el motivo. Build frontend y revisión de la interfaz con datos completos/incompletos.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_coordinacion.py tests/test_protecciones_web.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 049 T3`.

### T4 [DIgSILENT]: Validación y persistencia de protecciones en PowerFactory

**Cubre:** RF-9.

**Files:** Usar trabajo nativo de T2 y crear `tests/test_protecciones_nativas.py`; conservar informes, gráficas y readback con custodia.

**Interfaces:** Consumir planes generados por el servicio y licencia comprobada. Ejecutar caso de coordinación conocido con parámetros trazables; aplicar en variación, guardar, reabrir y repetir las fallas previstas. Fuente, central existente y bancos permanecen según el caso; no habilitar estudios de tierra sin modelo de secuencia/puesta a tierra válido.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_protecciones_nativas_reabre`: tiempos/ajustes y topología tras reapertura coinciden dentro de tolerancias predeclaradas; `test_generacion_existente_aporta`: validar aportes reales por escenario. Si faltan fichas o licencia, guardar lista de bloqueo y mantener T4 abierta; dobles, gráficos inventados o mero ComShc ejecutado no la cierran.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_nativas.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 049 T4`.

## Cierre y evidencia

Al ejecutar, actualizar [tasks.md](tasks.md) con comandos, resultado, hashes y rutas
de informe; mantener abiertas las condiciones sin evidencia. El estado se escribe
solo en spec.md y se refleja mediante `tools/estado_specs.py --escribir`. Validar
trazabilidad además de las pruebas de cada tarea; no cerrar otras specs por arrastre.

