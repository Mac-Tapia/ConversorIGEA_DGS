# Harness integral de modelos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans para ejecutar en esta sesión; revisión independiente final. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Medir y comparar LLM, recuperación y modelos eléctricos mediante suites selladas, resultados individuales y decisiones conservadoras.

**Architecture:** Paquete nuevo con contratos, métricas, adaptadores, ejecución e informes. Consume evaluadores/registro existentes mediante interfaces explícitas de solo lectura y devuelve evidencia; no altera sus políticas. Los paquetes de GitHub son adaptadores opcionales con revisiones fijadas.

**Tech Stack:** Python 3.12, stdlib, unittest; NumPy solo en el adaptador temporal existente. Sin instalar dependencias ni cargar modelos para probar contratos.

**Spec:** `docs/superpowers/specs/2026-11-08-harness-integral-modelos-design.md`, aprobada por el usuario el 2026-11-08.

## Global Constraints

- Worktree propio `.worktrees/harness-integral-20261108`, rama `codex/harness-integral-20261108`, base `5617251012f39193297e19b299d8a179a8fe1f61`.
- Acuse de la sesión de producción en `.agents/coordination/ACTIVE.md`: superficies nuevas aceptadas; compartidos en solo lectura. Consultar contratos `c6ec7fb8` y posteriores antes de integrar.
- Sin GPU/PF/instalaciones/suite completa ni entorno compartido durante su turno G2. Pruebas propias ligeras mediante Python 3.12 del sistema, `-I -B`, stdlib y fuentes del worktree.
- No reemplazar pesos, corpus, modelos activos, políticas, lock eléctrico, referencias reales ni cambios ajenos.
- `contract` y `replay` nunca promueven; solamente `runtime` completo puede solicitar la promoción por la vía existente y con sus puertas conservadas.
- Cero denominador produce `null` con soporte. Una suite obligatoria incompleta bloquea esa familia; una auxiliar no desaparece del informe.
- Publicar por reemplazo atómico y relectura. No afirmar mejora ni aceptación nativa a partir de contratos o replay.

## Review Focus

1. JSON mal formado, booleanos como conteos y NaN: rechazo antes de medir (T1/T2).
2. Omisiones, ids duplicados y casos extra: cobertura programada conservada y promoción bloqueada (T3).
3. Abstenciones, clases raras y consultas sin respuesta: denominadores explícitos, ninguna precisión artificial (T1).
4. Cambio de modelo, datos, política o partición entre referencia y candidato: bloqueo antes de comparar (T2/T3).
5. Fallo al escribir/releer y salida upstream incompatible: conservar informe anterior y no promover (T4/T5).

## Superficies e interfaces

Solo se crean `src/convertersmartgrid/evaluacion_harness/{__init__,metricas,contratos,ejecucion,adaptadores,publicacion,cli}.py`, `tools/evaluar_harness.py`, `tests/test_harness_*.py` y documentación con prefijo propio. No se escribe en `aceptacion.py`, `model_registry.py` ni `training_coordinator.py`.

### Task 1: Métricas auditables

**Files:** Create `evaluacion_harness/metricas.py`; Test `tests/test_harness_metricas.py`.

**Interfaces:** Produce `conteos(vp:int, fp:int, fn:int)->dict`, `clasificacion(casos:list[dict], clases:list[str])->dict`, `entidades(casos:list[dict])->dict`, `recuperacion(casos:list[dict], *, k:int)->dict`, `comparar_pareado(casos:list[dict], *, metrica:str, margen:float, semilla:int, remuestras:int, confianza:float, min_grupos:int)->dict`.

- [x] Escribir y ejecutar pruebas rojas con VP=2/FP=1/FN=2: precision=2/3, recall=1/2, F1=4/7; conteos vacíos→null; rechazo de negativos/bool/NaN.
- [x] Añadir clasificación con abstención, clases ausentes y macro/micro; recuperación con k=3, dos positivos y un acierto→P@3=1/3, R@3=1/2; gold parcial→recall null; duplicados rechazados.
- [x] Implementar métricas y remuestreo pareado por grupo con semilla explícita; insuficiencia de grupos no demuestra mejora.
- [x] Ejecutar `tests/test_harness_metricas.py` con unittest. Expected: todos los casos pasan; sin modelos/campañas.

### Task 2: Política, particiones y matriz de suites selladas

**Files:** Create `evaluacion_harness/contratos.py`; Test `tests/test_harness_contratos.py`.

**Interfaces:** Produce `huella(valor)->str`, `sellar(config:dict)->dict`, `validar(config:dict)->None`, `MINIMAS:dict[str,tuple[str,...]]`.

- [x] Probar rojo: sello alterado; familia desconocida; suite obligatoria omitida; grupos/textos cruzados; ids repetidos; mínimos no declarados.
- [x] Definir configuración JSON versionada con familia, modelos/digests/config hashes, suites/tipos/casos, cuatro particiones, política/puertas e identidad de datos. Preservar campos de custodia y distinguir humano/sintético.
- [x] Sellar contenido canónico completo antes de inferencia y rechazar cambios. No inventar umbrales de campaña: sin política declarada solo diagnóstico.
- [x] Ejecutar pruebas T1/T2. Expected: pasan; cada entrada rechazada tiene motivo explícito.

### Task 3: Ejecución pareada y control de promoción

**Files:** Create `evaluacion_harness/ejecucion.py`; Test `tests/test_harness_ejecucion.py`.

**Interfaces:** Consume T1/T2. Produce `ejecutar(config:dict, proveedor:Callable, *, modo:str, cancelar:Callable|None=None)->dict`, `validar_promocion(informe:dict, config:dict)->None`.

- [x] Probar rojo: callback recibe exclusivamente entrada pública, no gold; fallo/timeout/cancelación no elimina ids; casos de prueba idénticos para ambos modelos.
- [x] Ejecutar secuencialmente cada caso y modelo; registrar salidas/errores, backend y dispositivo efectivos del proveedor. No inferir CUDA de la configuración.
- [x] Aplicar mínimos y puertas globales/por familia contra métricas recalculadas; exigir todas las suites obligatorias. Evidencia nativa/dominio y recarga serán obligatorias para promoción según la matriz, nunca un bypass del registro existente.
- [x] Probar rechazo de `contract`/`replay`, hashes distintos, informe editado e incompleto y lectura de políticas ajenas. Expected: no cambia ningún activo.

### Task 4: Adaptadores existentes y GitHub

**Files:** Create `evaluacion_harness/adaptadores.py`; Test `tests/test_harness_adaptadores.py`.

**Interfaces:** Produce `desde_ordenes(informe:dict)->list[dict]`, `evaluar_temporal(real, predicciones, *, politica)->dict`, `evaluar_electrico(metricas:dict, *, politica)->dict`, `importar_upstream(payload:dict, *, herramienta:str, commit:str, lock:dict)->dict`.

- [x] Probar rojo: conteos contradictorios en órdenes; referencia de otro contexto; commit distinto; esquema upstream inesperado y resultado parcial.
- [x] Conectar por imports diferidos a los evaluadores temporal y eléctrico vigentes sin duplicar sus puertas. Normalizar órdenes desde sus casos, conservando F1 histórico y convención nueva separadas.
- [x] Importar resultados de EleutherAI/Promptfoo/Ragas con salida original y digest, commit fijado y alcance auxiliar explícito; no convertir salida importada en runtime local ni verdad física.
- [x] Ejecutar pruebas ligeras de adaptadores; pruebas que requieren entorno opcional solo cuando exista y se autorice turno. Expected: sin instalaciones ni promociones.

### Task 5: CLI, publicación y reapertura

**Files:** Create `evaluacion_harness/publicacion.py`, `evaluacion_harness/cli.py`, `tools/evaluar_harness.py`; Test `tests/test_harness_cli.py`.

**Interfaces:** Consume T2–T4. Produce `publicar(ruta:Path, informe:dict)->str`, `leer_informe(ruta:Path)->dict`, `main(argv:list[str]|None=None)->int`.

- [x] Probar rojo: JSON/NaN inválido, salida truncada, fallo de reemplazo conserva archivo anterior, referencia/candidato ausentes y replay marcado explícitamente.
- [x] CLI `sellar --config ... --salida ...`, `replay --config ... --predicciones ... --salida ...`, `verificar --informe ...`. Runtime se ofrece mediante API Python de proveedor local integrado por el coordinador, nunca ejecutando comandos/imports arbitrarios desde JSON.
- [x] Publicar informe firmado por contenido y releer antes de retornar; devolver códigos no cero ante fallo/cancelación/bloqueo y no aceptar meramente un resumen favorable.
- [x] Ejecutar prueba CLI real en proceso hijo con archivos temporales y `-I -B`; Expected: informe reabrible y sin datos de negocio/estado activo alterados.

### Task 6: Puente al coordinador y registro existentes

**Files:** Create `src/convertersmartgrid/evaluacion_harness/integracion.py`; Test `tests/test_harness_integracion.py`.

**Interfaces:** `crear_etapa(*, nombre, config, proveedor, evaluadores, registro, declaracion, informe_path, uses_gpu, modo='runtime', cancelar=None, activar=False, revalidar=None)` devuelve un `TrainingStage` existente. `registrar_resultado(informe, config, *, registro, modelo, model_manifest, dataset_manifest, decision_dominio, smoke_reload, artifacts, activar=False, revalidar=None)` registra evidencia y activa solo con todas las guardas.

- [x] Probar conexión real en temporales a `TrainingCoordinator` y `RegistroModelo`, con publicación/relectura y reanudación; sin GPU, modelos ni registros reales.
- [x] Sellar destino absoluto, slot, etapa, recursos y activo esperado; bloquear LLM→PINN, otro registro o referencia cambiada.
- [x] Sellar artefactos antes de evaluar y contrastarlos en proveedor, manifiesto, recarga, snapshot y revalidación.
- [x] Exigir identidad de candidato y referencia, puertas heredadas y recibo `decision_original` de la suite dominio de esta campaña; una aprobación antigua de la misma política no basta.
- [x] Preservar activo ante rechazo/cancelación, registrar rechazados para auditoría y activar únicamente por decisión booleana explícita con relectura.

### Task 7: Evidencia, revisión e integración coordinada

**Files:** Create documentación `2026-11-08-harness-integral-modelos-uso.md` y evidencia de la misma tarea; todos los tests nuevos.

- [x] Ejecutar batería completa propia y comprobación de whitespace/compilación sin bytecode; registrar intérprete, comando, resultado y hashes.
- [x] Revisión independiente del diff completo, solo lectura; corregir hallazgos demostrados con prueba roja y verde.
- [ ] Entregar diff/commit de rutas propias al integrador comercial con alcance, contratos de su revisión contrastados y pendientes de runtime. No mezclar ni subir ramas ajenas.
- [ ] Campañas LLM/GPU/PF: pendientes hasta FIN/turno confirmado y datos/política de campaña válidos. No declarar aumento de precision/recall con ensayos de contrato.

## Fundamento y procedencia

Reutiliza las fuentes verificadas del diseño: [maestría de König](https://publications.ait.ac.at/de/publications/automated-evaluation-and-parameter-optimisation-for-retrieval-aug/), [doctorado de Stiasny](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/), [RAGAs, EACL 2024](https://aclanthology.org/2024.eacl-demo.16/) y artículos JMLR/PowerFlowNet allí citados. Consulta web reiterada el 2026-11-08; justifican evaluación separada y contraste físico, no acreditan rendimiento de este código.

## Registro de ejecución

- Diseño aprobado; acuse de coordinación confirmado en ACTIVE.md. Implementación nativa en esta sesión con revisión final; no se repite la aprobación ya otorgada para implementar.
- Ruling: pruebas stdlib ligeras con Python 3.12 del sistema, sin usar el entorno compartido reservado por G2; no baseline completo por exclusión expresa del integrador.
- T1–T6 implementadas en superficies nuevas. T7: verificación final, revisión y entrega de commit en curso; campañas reales pendientes por turno/datos/política, fuera de la evidencia de contratos.
- El integrador autorizó explícitamente el catálogo generado por hook090 en este worktree. No se modifican los módulos heredados ni la rama comercial; se entrega commit para integración única de la otra sesión.
- Ruling: el coordinador usa `qlora` para la etapa LLM; no existe una etapa `llm` en `ORDEN_MODELOS`. El slot de registro y la etapa están vinculados en configuración, preservando el contrato vigente.
- Ruling: los contrastes admiten `mayor_mejor` y `menor_mejor`; para métricas de dominio se requieren valores por grupo del evaluador independiente. No se duplican fórmulas temporales ni físicas.
- Ruling: conexión automática disponible como `TrainingStage` ejecutable, no modificación unilateral de los jobs/productores heredados reservados. La admisión exclusiva por slot y el turno PF siguen siendo responsabilidad de la aplicación integradora.
- Revisión final propia y revisión provisional de producción atendidas: el formato escalar por grupo fue eliminado y los seis tests recibieron citas semánticas de spec. Ocho módulos nuevos quedan propuestos al integrador para el mapa de capas, sin modificar su pyproject reservado.
- Verificación del corte final de fuentes: 42 unittest stdlib correctas; regresión enfocada 127 correctas y17subtests, sin skips; Ruff correcto. No suite completa, entrenamiento, promoción de modelos del usuario ni aceptación eléctrica.
