# Cierre integral para producción — Plan de implementación

> **Para ejecución:** aplicar `superpowers:executing-plans` tarea por tarea. Este documento no crea subagentes, no implementa código y no publica. Los pasos pendientes usan casillas. Cualquier trabajo delegado futuro debe leer `C:/Users/Lenovo Legion/.agents/COORDINATION.md` y `C:/Users/Lenovo Legion/.agents/skills/team-agent-orchestration/SKILL.md`.

**Goal:** cerrar los fallos y vacíos del diagnóstico con código, datos y aceptación verificables, conservando todo el trabajo existente.

**Architecture:** conservar motor Python/FastAPI, frontend React/TypeScript y arnés nativo de PowerFactory. Integrar productores, contratos y consumidores antes de las campañas reales; completar arquitectura al estabilizar los módulos y repetir validación sobre la revisión final.

**Tech Stack:** Windows, CPython 3.12, PowerFactory con API compatible, Access/SQL Server según la fuente, React/TypeScript/Vite, PyTorch/CUDA y registros locales de modelos.

**Spec:** `docs/constitution.md`; specs activas 002–099 enumeradas en la matriz adjunta, particularmente 065 y 086. El plan `docs/PLAN_CIERRE_SPECS_2026-11-06.md` conserva su historia; este documento precisa el trabajo pendiente según el corte verificado y no reescribe decisiones ya resueltas.

**Corte verificado:** 7 de noviembre de 2026, America/Lima; `D:/converter/ConversorIGEA_DGS`, `main`, `5617251012f39193297e19b299d8a179a8fe1f61`, con diff preexistente en `src/convertersmartgrid/web/services.py` y `.agents/` sin seguimiento. 99 specs, 97 listas de tareas, 115 casillas abiertas en 47 specs. El inventario se releyó al preparar este plan.

**Base de evidencia:** `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/`. El diagnóstico obtuvo 81 pases Python enfocados, frontend 42 pases/1 fallo, tipos/contrato correctos y npm audit sin avisos. Esos resultados describen el corte auditado; no se reejecutaron para redactar este plan ni sustituyen validación final.

## Decisión de implementación y alcance

Se propone cierre incremental por subsistema y caso real. Un arreglo único masivo aumentaría la dificultad de atribuir fallos y proteger trabajo concurrente. Cerrar solo el empaquetado dejaría sin resolver los vacíos de IA/planeamiento solicitados como proyecto completo.

Se mantienen dos hitos verificables: **núcleo comercial local aceptado**, según el alcance explícito de 086, y **proyecto completo**, que además exige módulos activos, campañas y datos pendientes. El asistente beta y los módulos opcionales pueden quedar fuera de una edición comercial conforme a sus decisiones vigentes; eso no cierra sus specs ni permite declarar completo el proyecto. El plan cubre ambos hitos, sin eliminar funcionalidades web existentes.

## Global Constraints

- CPython `>=3.12,<3.13`; frontend respeta Node `>=22.14.0 <25` y npm `>=10.9.0 <12`. Revalidar matrices de API nativa antes de cambiar motores.
- Una responsabilidad y un sitio: no duplicar conversión, reglas, lectura/escritura ni arnés de PowerFactory.
- Mismas entradas/perfil/alias producen mismo DGS byte a byte; validar layouts reducido/completo y workers serie/paralelo.
- TXT, MDB y VNR mantienen procedencia independiente, empresa/SET/sistema/periodo/CRS y hashes. Datos privados nunca en git ni servicios de terceros.
- Conservar rutas, pestañas, botones y campos existentes de la web. No resolver un fallo retirando la función afectada.
- Trabajo pesado único en esta máquina: GPU, suite completa y DIgSILENT se reservan por turno. No reiniciar webs ni terminar procesos ajenos. El worktree no aísla licencias/puertos/memoria.
- Copias, modelos, informes, originales, output, historia y cambios ajenos se conservan. No git clean/reset/stash para esconder diferencias; no actualizar baselines para aceptar resultados nuevos sin justificación.
- Evidencia/temporales externos al checkout. Publicación atómica, cancelación y recuperación verificadas. No promover datos o modelos de etapas incompletas.
- Implementado, prueba enfocada, regresión completa, datos reales, persistencia nativa, aceptación eléctrica, científica y operativa son estados distintos.
- Cada comportamiento nuevo requiere RF en spec activa, plan, tarea y prueba. La tarea 072 T14 aún carece de RF: P17 resuelve ese contrato antes de código.
- Los commits futuros, una vez autorizados, usan rutas explícitas y resultados verificados. Este pedido entrega un plan; no autoriza por sí mismo publicación, renombrado real ni ejecución de campañas nativas.
- Preservar D1–D7 ya decididas de 086. D7 no exige asesoría legal: cada usuario aporta sus licencias.

## Review Focus

1. **Identidad/contexto equivocados:** P04/P19 prueban que otro source_run, proyecto o caso no se acepta ni comparte partición/puntero por parecido.
2. **Convergencia engañosa o fuera de dominio:** P05/P21 prueban flujo desequilibrado, carga no servida e inventario incompleto; éxito numérico no da aceptación eléctrica.
3. **Corte entre escribir y publicar:** P19/P21/P22 prueban caída, cancelación y rollback con estados/modelos/variaciones conservados y sin reaplicar transferencias.
4. **Evaluación contaminada:** P14/P15/P16/P18 separan selección, calibración y test; ni maestro ni predicción del propio modelo sirven de verdad eléctrica.
5. **Entorno diferente al entregado:** P01/P22/P25 verifican Python embebido, drivers, lock, versión de seguridad, máquinas sin desarrollo y evidencia del mismo candidato.

## Fases, dependencias y recursos

| Fase | Paquetes | Entregable y puerta de salida |
| --- | --- | --- |
| F0. Preparación | P00 | Corte, fuentes, responsables y superficies web preservadas. |
| F1. Seguridad y regresión | P01–P04 | Entorno candidato, frontend corregido y puerta integral probada. |
| F2. Corridas universales | P07–P13 | R1–R5, regresiones recientes e informes por caso, sin mezcla. |
| F3. Física y protecciones | P05–P06 | Dominio/variaciones comprobados; datos y bloqueos de protecciones explícitos. |
| F4. Modelos y planeamiento | P14–P20 | Campañas por familia, PIDE anual, MADRL, ciclo conjunto y consola. |
| F5. Robustez e instalación | P21–P22 | Recuperación/sin red, instalador, complemento y tercero. |
| F6. Estructura y rutas | P23–P24 | Capas/frontend reorganizados y renombrado ensayado conservando identidad. |
| F7. Aceptación final | P25 | Mismo candidato con pruebas completas y aceptación de cada dominio. |
| F8. Publicación | P26 | Artefacto revisable y publicación únicamente con orden expresa. |

El orden dentro de una fase lo determina la dependencia de cada paquete. Se permite adelantar preparación de datos/documentación de P06/P17 mientras otro paquete usa el motor. Las campañas pesadas se serializan. Para trabajo independiente no se crean agentes en este plan; se deja definida la propiedad de archivos por si el usuario autoriza colaboración después.

Una dependencia exige su interfaz/artefacto válido: un modelo rechazado no es la dependencia válida de una etapa que exige modelo aprobado. Mientras ese bloqueo exista solo avanzan paquetes independientes; no se fuerza la cadena para completar un cronograma.

No se fija una fecha de fin sin medir disponibilidad. P00 debe registrar duración de R1 y R3, entrenamiento de una familia y suite completa; con esas medidas se estima el resto por número real de casos/modelos y turnos disponibles. Los tiempos del diagnóstico son de pruebas enfocadas y no permiten estimar las campañas enteras.

## Procedimiento común por unidad de implementación

- [ ] Releer RF, criterios originales de la matriz y consumidores actuales; confirmar dueño y base.
- [ ] Para cambios de comportamiento, añadir primero una regresión que represente el fallo y conservar su salida roja. Para una aceptación ya implementada, ejecutar el caso real sin fabricar un cambio de código.
- [ ] Aplicar cambio mínimo e integrar productores/consumidores; mantener compatibilidad prevista.
- [ ] Ejecutar pruebas indicadas y negativas del Review Focus. El resultado debe tener salida 0, cero fallos/errores/skips requeridos y artefactos completos; un timeout no pasa.
- [ ] Revisar diff propio, ejecutar puertas apropiadas y registrar evidencia. Commit de rutas propias cuando esté autorizado; no incluir el diff ajeno por conveniencia.
- [ ] Marcar la tarea original solo si cumple su criterio completo; actualizar matriz, Estado y documentación con la revisión exacta. Resultado rechazado/bloqueado conserva esa condición.

Cada paquete se descompone en subunidades revisables; no se funde como un bloque indivisible. P19 sigue T1b→T2b→T3b→T4b→T5b. P23 sigue capas de abajo arriba y luego cada movimiento frontend. R1–R5 se revisan por proyecto/caso. La matriz conserva todas las tareas originales para que una tanda no cierre tareas que no ejecutó.


## P00. Fijar candidato, responsables y línea base

**Dependencias:** ninguna. **Responsable propuesto:** Integrador. **Recurso:** Lectura; sin motores.

**Archivos existentes a revisar o modificar:** `.agents/coordination/ACTIVE.md`, `docs/PLAN_CIERRE_SPECS_2026-11-06.md`.

**Tareas abiertas que administra:** actividad transversal necesaria para el cierre de hallazgos.

- [ ] **Paso 1.** Identificar dueño y propósito del diff preexistente de services.py; decidir su incorporación con evidencia, sin atribuir autoría por apariencia.
- [ ] **Paso 2.** Registrar HEAD, rama, worktrees, estado Git y hashes de fuentes/perfiles/modelos; guardar manifiesto y copia verificable fuera del checkout.
- [ ] **Paso 3.** Inventariar rutas, pestañas, botones y campos existentes de la web; conservar esa línea base en todo el plan.
- [ ] **Paso 4.** Asignar responsable y worktree por paquete; un integrador incorpora cambios y cada archivo compartido tiene un único escritor.
- [ ] **Paso 5.** Leer D1–D7 actuales de 086. Mantener decisiones resueltas, incluido D7: cada usuario aporta sus licencias. Identificar operador y tercero de T41.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_trazabilidad_specs.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Corte reproducible y dueños registrados; cambios ajenos conservados. Produce candidato_id y manifiesto de fuentes. No cerrar por un tablero sin evidencia.

**Evidencia esperada:** `evidencia/P00/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P01. Alinear entorno, locks y seguridad

**Dependencias:** P00. **Responsable propuesto:** Entorno y empaquetado. **Recurso:** CPU; venv externo.

**Archivos existentes a revisar o modificar:** `constraints-python312-win.txt`, `requirements.txt`, `requirements-nucleo.lock`, `config/entrega.json`, `tools/fijar_entorno.py`, `tools/construir_candidato.py`.

**Tareas abiertas que administra:** actividad transversal necesaria para el cierre de hallazgos.

- [ ] **Paso 1.** Comparar installed/constraints/lock con candidato.versiones_de_seguridad. Base auditada: Pillow 12.3.0 frente a 13.0.0; pypdf 6.21.2 frente a 6.21.4; certifi 2026.7.22 frente a 2026.10.18. Consultar avisos actuales antes de fijar versiones definitivas.
- [ ] **Paso 2.** Añadir a test_fijar_entorno la negativa test_entorno_bajo_minimo_de_seguridad_no_es_apto: un paquete bajo el mínimo impide declarar entorno apto aunque pip check pase. Guardar el fallo antes del arreglo.
- [ ] **Paso 3.** Preparar entorno candidato externo CPython 3.12 con dependencias y ruedas verificadas; no reinstalar Torch ni modificar el .venv de las sesiones activas.
- [ ] **Paso 4.** Corregir constraints/locks que permitan regresar a versiones antiguas; conservar hashes, procedencia y separación del complemento IA.
- [ ] **Paso 5.** Ejecutar pip check, escaneo actual de Python y pruebas de instalación/capacidades con el intérprete candidato; ensayar reversión antes de cambiar el lanzador compartido.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_fijar_entorno.py tests/test_instalacion_programa.py tests/test_web_runtime_dependencies.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Versiones coherentes con política y auditoría sin vulnerabilidades graves no resueltas; ejecutable y dependencias registrados. pip check verde no acredita seguridad.

**Evidencia esperada:** `evidencia/P01/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P02. Resolver regresión de alcance temporal del frontend

**Dependencias:** P00. **Responsable propuesto:** Frontend e informes. **Recurso:** CPU ligera.

**Archivos existentes a revisar o modificar:** `frontend/src/alternativas.ts`, `frontend/test/alternativas.test.mjs`, `src/convertersmartgrid/informes.py`.

**Tareas abiertas que administra:** actividad transversal necesaria para el cierre de hallazgos.

**Interfaz/decisión:** Conservar alcanceDe(a: Alternativa): string y el contrato JSON actual.

- [ ] **Paso 1.** Reproducir node --test frontend/test/alternativas.test.mjs y conservar la diferencia: temporal frente a temporal, no llega al horizonte más corto.
- [ ] **Paso 2.** Contrastar 042:RF-77, ampliación 098 y filas del informe. Conservar la distinción entre sin medir, horizonte insuficiente, temporal y definitiva.
- [ ] **Paso 3.** Cubrir en alcanceDe definitiva=true, años positivos, cero, nulo y mas_corto presente/ausente. Si el comportamiento actual cumple el RF, actualizar la expectativa obsoleta; no quitar el aviso para poner verde la prueba.
- [ ] **Paso 4.** Ejecutar npm test y npm run typecheck completos; verificar el mismo significado en tabla real y Word/Excel durante P13.

**Verificación enfocada prevista:**

```powershell
node --test frontend/test/alternativas.test.mjs
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Frontend sin fallos/omitidas y alcance coherente con el informe. No fijar el número de pruebas como contrato.

**Evidencia esperada:** `evidencia/P02/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P03. Crear puerta integral de entrega con ámbitos explícitos

**Dependencias:** P01, P02. **Responsable propuesto:** Integrador de validación. **Recurso:** CPU; suites por turno.

**Archivos existentes a revisar o modificar:** `tools/verificar_candidato.py`, `tools/trazabilidad_candidato.py`, `CODIGO_FUENTE.md`.

**Tareas abiertas que administra:** actividad transversal necesaria para el cierre de hallazgos.

**Interfaz/decisión:** Firmas propuestas; no existen aún. Mantener compatible tools/verificar_candidato.py. Nuevos archivos enumerados en esta tarea.

- [ ] **Paso 1.** Crear tools/verificar_entrega_integral.py y tests/test_verificar_entrega_integral.py. Vincularlos a 065:RF-24 y 086:RF-46 en sus planes activos e inventario; reutilizar el runner Python existente.
- [ ] **Paso 2.** Escribir primero negativas: frontend fallido, JUnit ausente, timeout, skip/xfail requerido, datos sin huella, candidato modificado y módulo exigido sin dependencia impiden aceptación.
- [ ] **Paso 3.** Implementar plan_comprobaciones(raiz: Path, python: Path, edicion: str, evidencia: Path) -> list[dict] y evaluar_entrega(resultados: list[dict], obligatorias: set[str]) -> dict. Comprobación: id, comando como lista, cwd, artefacto, ámbito y obligatoriedad.
- [ ] **Paso 4.** CLI nueva propuesta: --root, --python, --output-dir y --edicion nucleo|completa. Backend tests/, frontend test/typecheck/build y auditorías son puertas separadas; completa incorpora tests_ml y campañas requeridas. No cambiar el significado de flags históricos en silencio.
- [ ] **Paso 5.** Consolidar en resultado_entrega.json revisión, datos, modelos, salida y estados de implementación/pruebas/aceptación. Núcleo aceptado y proyecto completo son campos diferentes.
- [ ] **Paso 6.** Probar el orquestador con procesos mínimos reales aislados, incluidos fallos, antes de ejecutar el gate verdadero de P25.

**Crear:** `tools/verificar_entrega_integral.py` y `tests/test_verificar_entrega_integral.py`; sus nombres e interfaz son propuestas de este plan.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_verificar_candidato.py tests/test_trazabilidad_candidato.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Ningún pase parcial o proceso incompleto produce entrega aceptada; la edición completa no salta módulos sin dependencias.

**Evidencia esperada:** `evidencia/P03/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P04. Congelar contratos de fuentes y conservación de la web

**Dependencias:** P01, P02. **Responsable propuesto:** Backend y custodia. **Recurso:** CPU; datos reales en lectura.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/batch.py`, `src/convertersmartgrid/web/readiness.py`, `src/convertersmartgrid/web/source_runs.py`, `src/convertersmartgrid/web/workspace.py`.

**Tareas abiertas que administra:** actividad transversal necesaria para el cierre de hallazgos.

**Interfaz/decisión:** Produce source_run_id/source_fingerprint por modalidad y baseline de superficies web.

- [ ] **Paso 1.** Preparar manifiestos separados TXT/MDB/VNR con empresa, periodo, CRS, hashes y selección; no completar una modalidad con datos de otra.
- [ ] **Paso 2.** Verificar negativas de fuente ausente, pertenencia a otro sistema, catálogo incompatible y reconstrucción con supuestos. El inventario sigue visible; preparación ambigua bloquea conversión.
- [ ] **Paso 3.** Probar layouts reducido/completo, uno/varios/todos, red unida y DGS byte a byte con workers=1/4, usando las referencias de entrada correspondientes.
- [ ] **Paso 4.** Si cambió la huella de entrada/catálogo, bloquear la comparación de entrega y explicar la diferencia; nunca regenerar la línea base automáticamente.
- [ ] **Paso 5.** Conservar inventario de UI de P00 y comprobar que ningún botón, ruta, campo o pestaña existente desaparece. Añadir una guarda solo si la existente no demuestra esa conservación.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_export_layouts.py tests/test_readiness.py tests/test_source_runs.py tests/test_reconstruction_contract.py tests/test_reconstruction_topology.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Cada modalidad mantiene contrato, procedencia, determinismo y baseline. La conservación de interfaz es criterio de todos los paquetes.

**Evidencia esperada:** `evidencia/P04/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P05. Física, dominio, optimización y episodios nativos

**Dependencias:** P04, P07. **Responsable propuesto:** Gemelo y responsable eléctrico. **Recurso:** DIgSILENT exclusivo; GPU en otro turno.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/digital_twin/contratos_fisicos.py`, `src/convertersmartgrid/digital_twin/benchmark_fisico.py`, `src/convertersmartgrid/digital_twin/oraculo.py`, `src/convertersmartgrid/digital_twin/flujo.py`, `tools/aceptacion_nativa.py`.

**Tareas abiertas que administra:** 027:T29, 027:T30, 027:T31, 045:T3, 045:T4, 048:T4.

**Interfaz/decisión:** Consume ContextoExperimento y manifiestos de fuente. Produce predicción/contraste/veredicto por caso.

- [ ] **Paso 1.** Releer casos tras reapertura: iopt_net, fases, transformadores, controles, bancos, centrales y perfil. La evidencia PE10 de otro commit se conserva como antecedente.
- [ ] **Paso 2.** Fijar la negativa física equilibrada frente a flujo desequilibrado: fuera_de_dominio y top-k no autorizado. Comparar tensiones, pérdidas e inventario con tolerancias definidas antes del test.
- [ ] **Paso 3.** Ejecutar ablaciones/candidato PyG de 045 T3. Si hace falta dominio físico nuevo, completar sus RF y plan antes de implementarlo; no ajustar tolerancias mirando el test.
- [ ] **Paso 4.** Aplicar/retirar variantes de 048 en copias nuevas; verificar variaciones, persistencia, Caso base y Sin proyecto tras reabrir.
- [ ] **Paso 5.** Completar hipercubo latino, top-k y episodios 30/10/10 por sistema de 027 T29–T31 con semillas/contextos/curva; conservar candidatos rechazados.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_gemelo_contratos_v2.py tests/test_gemelo_fisico_nativo.py tests/test_optimizacion_mixta_nativa.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 045/048 y campañas tienen dominio y persistencia verificables. cerrable=true por evaluar un rechazo no significa red aceptada.

**Evidencia esperada:** `evidencia/P05/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P06. Datos y aceptación real de protecciones

**Dependencias:** P04. **Responsable propuesto:** Ingeniero de protecciones y custodio. **Recurso:** Datos externos; DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/protecciones.py`, `src/convertersmartgrid/datos_empresa.py`, `tools/protecciones_pf.py`, `tools/aceptacion_nativa.py`.

**Tareas abiertas que administra:** 049:T4.

- [ ] **Paso 1.** Inventariar y obtener curvas, ajustes, poder de corte, potencia/impedancia real de cortocircuito, CTI, sensibilidad y márgenes; identificar custodio de cada faltante.
- [ ] **Paso 2.** Validar unidades/procedencia; DEFAULT y ceros de plantilla no son fichas. Conservar pruebas negativas por cada dato ausente.
- [ ] **Paso 3.** Completar lectura de fichas y escenarios de falla según 049, manteniendo el bloqueo hasta disponer de datos suficientes.
- [ ] **Paso 4.** Ejecutar coordinación nativa, persistir ajustes, reabrir y releer. Entregar reporte al ingeniero, con fallos de coordinación y capacidad de corte visibles.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_protecciones_datos.py tests/test_protecciones_coordinacion.py tests/test_protecciones_pf_guion.py tests/test_protecciones_nativas.py tests/test_protecciones_web.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 049 T4 cierra solo con datos reales, coordinación y persistencia; sin fichas/licencia queda bloqueada, no aprobada por return_code=0.

**Evidencia esperada:** `evidencia/P06/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P07. R1: TXT y operación de dos alimentadores

**Dependencias:** P04. **Responsable propuesto:** Operador de pruebas PF. **Recurso:** DIgSILENT exclusivo y navegador.

**Archivos existentes a revisar o modificar:** `tools/sistema_web.py`, `src/convertersmartgrid/web/services.py`, `tools/ajuste_cabecera_pf.py`, `tools/estudios_pf.py`, `tools/transferencia_pf.py`.

**Tareas abiertas que administra:** 008:T7, 011:T19, 012:T13, 013:T7, 028:T11, 037:T4, 086:T24.

- [ ] **Paso 1.** Crear espacio/proyecto de prueba nuevo CA101+PE104 por la web con TXT custodiados; registrar comando, espacio y selección.
- [ ] **Paso 2.** Convertir/importar/calibrar/recalibrar; cabecera al mismo instante, tolerancia R1 de 086 del 1 %, pertenencia de cargas y lecturas m:Psum.
- [ ] **Paso 3.** Aplicar carga nueva, obras, transferencia y estudios; confiabilidad usa libros reales exigidos por 012.
- [ ] **Paso 4.** Verificar idempotencia, invariantes de Caso base/Sin proyecto y restitución de estado. Conservar resultados parciales y motivos.
- [ ] **Paso 5.** Entregar resultados a P13 para informe y P05 para física; registrar cierre específico de cada tarea 008/011/012/013/028/037 y 086 T24.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_sistema_web.py tests/test_cargas_pf_web.py tests/test_obras_pf_web.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** R1 completo con fuente/caso/periodo, cabecera válida e invariantes; ningún resultado de otro alimentador acredita esta corrida.

**Evidencia esperada:** `evidencia/P07/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P08. R2: MDB, cargas y fases de ramales

**Dependencias:** P04. **Responsable propuesto:** Operador de pruebas PF. **Recurso:** Access real y DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/access.py`, `src/convertersmartgrid/cargas_pf.py`, `tools/cargas_pf.py`, `tools/sistema_web.py`.

**Tareas abiertas que administra:** 016:T18, 081:T20, 086:T25.

- [ ] **Paso 1.** Verificar driver Access y bases de red/equipos declaradas; sus funciones y hashes son independientes del TXT.
- [ ] **Paso 2.** Importar SI213 y PN107 de prueba por web; aplicar cargas con/sin cable según distancia real al nodo.
- [ ] **Paso 3.** Probar ramal monofásico, fase servida, barra de baja y aviso cuantificado; no confundir convergencia con servicio de la carga.
- [ ] **Paso 4.** Repetir aplicación, reabrir y comprobar variación por carga, idempotencia y caso base activo al terminar.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_access_input.py tests/test_cargas_pf_guion_016.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 086 T25, 016 T18 y 081 T20 con conexión/fases/persistencia verificadas sin mezcla de fuentes.

**Evidencia esperada:** `evidencia/P08/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P09. R3: Pisco, SET, valle y mejora medida

**Dependencias:** P04, P07. **Responsable propuesto:** Ingeniería y optimización. **Recurso:** DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/escalera_optima.py`, `src/convertersmartgrid/valle.py`, `src/convertersmartgrid/set_nueva.py`, `src/convertersmartgrid/optimizacion_oraculo.py`, `tools/sistema_web.py`, `tools/estadistica_ordenes.py`.

**Tareas abiertas que administra:** 042:T50, 042:T48, 042:T44, 042:T37, 071:T5, 081:T24, 084:T8, 084:T9, 086:T26, 087:T27, 087:T12, 087:T13, 092:T2.

- [ ] **Paso 1.** Importar Pisco nuevo, calibrar sistema y SET con periodo común; verificar huella del caso base y lista de alimentadores sin medidor.
- [ ] **Paso 2.** Medir referencia y método con oráculo sobre mismo estado, casos, revisión y semillas; registrar tiempos y obra elegida para 071 T5 y 087 T12/T13.
- [ ] **Paso 3.** Medir migración 10→22,9 kV, obras de déficit previo y alcance por alimentador. Separar máxima, valle, costos de déficit y costos de la carga.
- [ ] **Paso 4.** Validar SET fuera del trazado, iopt_net restituido y fline/c:loading del tramo con ficha del fabricante para la terna.
- [ ] **Paso 5.** Confirmar sistema completo y tabla de Pisco. Para 081 T24 fijar población/contraste antes del análisis; informar efecto, muestra y p. Si no cumple p<0,05, no cerrar ni recortar la muestra a posteriori.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_escalera_optima.py tests/test_set_nueva.py tests/test_obras_pf_guion_042.py tests/test_puertas_modelos.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** R3 y tareas 042/071/084/087 con medidas comparables y veredicto por alimentador, sin convertir una reducción descriptiva en eficacia demostrada.

**Evidencia esperada:** `evidencia/P09/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P10. R4: Nasca, fijas, centrales y valle

**Dependencias:** P04. **Responsable propuesto:** Ingeniero eléctrico. **Recurso:** DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/escaneo.py`, `src/convertersmartgrid/ajuste_cabecera.py`, `src/convertersmartgrid/valle.py`, `tools/ajuste_cabecera_pf.py`, `tools/escanear_alimentador_pf.py`.

**Tareas abiertas que administra:** 028:T6, 039:T4, 042:T6, 052:T4, 073:T8, 086:T27.

- [ ] **Paso 1.** Crear NA203+NA205 de prueba; registrar central/maniobras antes del escaneo sin deducir pertenencia por nombre.
- [ ] **Paso 2.** Recalibrar coincidente y máximo del mes con libros y periodo de cada tarea; cifras históricas solo se comparan si las huellas corresponden.
- [ ] **Paso 3.** Ejecutar destinos por carga y obras de Con proyecto. Medir 052 T4: menos de 20 minutos en hardware y condiciones documentados.
- [ ] **Paso 4.** Construir Valle <año> con medición real, m:Psum y máxima inalterada; comparar variante de bancos con el oráculo.
- [ ] **Paso 5.** Reabrir, releer centrales, casos, variaciones y ubicación final de SET; guardar evidencia propia de cada criterio.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_cargas_pf.py tests/test_escalera_optima.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 086 T27 y tareas asociadas con fijas/valle/rendimiento diferenciados; si excede tiempo, 052 T4 sigue pendiente.

**Evidencia esperada:** `evidencia/P10/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P11. R5: VNR-GIS y otra empresa

**Dependencias:** P04. **Responsable propuesto:** VNR-GIS y operador PF. **Recurso:** SQL Server/Access y DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `src/vnr_etl/connectors/sqlserver_vnr.py`, `src/vnr_etl/discovery/official.py`, `src/convertersmartgrid/web/services.py`, `frontend/src/components/InputsPanel.tsx`.

**Tareas abiertas que administra:** 042:T29, 051:T3, 055:T2, 056:T3, 058:T7, 081:T16, 086:T28, 087:T14.

- [ ] **Paso 1.** Custodiar paquete oficial y perfil propio: moneda, periodo, CRS, sistemas/SET y carpeta provenientes de la empresa real de prueba.
- [ ] **Paso 2.** Convertir/importar NJA202 y R205 solo si pertenecen al paquete; no equiparar R205/0205 por parecido.
- [ ] **Paso 3.** Completar campo de empresa faltante de 081 T16 en frontend, con contrato y negativa de empresa no declarada; conservar opciones previas.
- [ ] **Paso 4.** Calibrar/estudiar en la tensión real; cada carga nueva con solución medida o ya cumple. Verificar vocabulario/carpeta sin mover proyectos existentes.
- [ ] **Paso 5.** Medir 087 T14 en segundo dominio; conservar evidencia R5 para instalarla en P22.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_vnr_etl.py tests/test_entrega_universal.py tests/test_web_reconstruction.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 086 T28 y 042/051/055/056/058/081/087 con otra empresa real y sin convenciones incrustadas en lógica.

**Evidencia esperada:** `evidencia/P11/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P12. Calibraciones y regresiones operativas recientes

**Dependencias:** P04. **Responsable propuesto:** Calibración y cargas. **Recurso:** DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/ajuste_cabecera.py`, `src/convertersmartgrid/transferencia_operador.py`, `src/convertersmartgrid/cargas_pf.py`, `src/convertersmartgrid/web/services.py`, `tools/transferencia_operador_pf.py`, `tools/cargas_pf.py`.

**Tareas abiertas que administra:** 004:T20, 025:T21, 039:T8, 042:T42, 091:T7, 094:T5, 098:T6, 099:T3.

- [ ] **Paso 1.** Crear copias nuevas de PE102, PA217/TM105, TM102, AL209 y CA101+CHN102; proteger proyectos originales y trabajo manual del operador.
- [ ] **Paso 2.** Las copias son ensayo. Si el criterio original exige un proyecto nominal concreto (098/099), no cerrar con una copia distinta: coordinar la ejecución autorizada sobre ese proyecto o aprobar antes la aclaración del criterio, conservando trazabilidad entre original y copia.
- [ ] **Paso 3.** 004 T20: dimensionado de transformadores CH_13/CH_22; 025 T21: calibración por año; 042 T42: elevador de 10 kV donde no hay barra de 22,9 kV.
- [ ] **Paso 4.** 039 T8/091 T7: máximo de cliente, secuencia calibración→recalibración→estudio y mensajes fieles con DIgSILENT abierto.
- [ ] **Paso 5.** 094 T5: perfiles antes/después y bancos propuestos desde el perfil, con comparación y límites.
- [ ] **Paso 6.** 098 T6: transferencia del operador, alternativa seleccionada, retorno a base y no reaplicación de una deshecha.
- [ ] **Paso 7.** 099 T3: identidad única del cliente; CH_23 creada y CH_20 descartada según libro. Retirar duplicada solo en copia de prueba con inventario antes/después.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_cargas_pf_guion.py tests/test_cargas_pf_guion_007.py tests/test_cargas_pf_web.py tests/test_sistema_web.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Evidencia particular por tarea y caso; una corrida de otro alimentador no cierra estas regresiones.

**Evidencia esperada:** `evidencia/P12/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P13. Informes, tablas y navegador real

**Dependencias:** P07, P09, P10. **Responsable propuesto:** Informes, frontend e ingeniero. **Recurso:** Navegador y render Word/Excel.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/informes.py`, `src/convertersmartgrid/informe_docx.py`, `src/convertersmartgrid/libros_informe.py`, `frontend/src/components/CargasTab.tsx`, `frontend/src/components/InformesPF.tsx`.

**Tareas abiertas que administra:** 017:T13, 017:T14, 017:T19, 073:T12, 081:T22, 086:T29.

- [ ] **Paso 1.** Generar Word/Excel de 017 T13/T14/T19 desde corridas verificadas, con job_id/fuente/caso; no heredar resultados de un intento fallido sin aviso.
- [ ] **Paso 2.** Comparar cifras del JSON, Word y Excel; revisar unidades, moneda, alcance y separación de déficit previo/carga.
- [ ] **Paso 3.** Renderizar y revisar visualmente tablas, figuras y paginación; el ingeniero registra aceptación o correcciones.
- [ ] **Paso 4.** Comprobar navegador real claro/oscuro y pantalla estrecha, tabla Pisco, En valle y aviso/retirada de catálogo de 081 T22.
- [ ] **Paso 5.** Conservar toda la UI de P00; texto y decisión del backend deben coincidir, incluido el alcance temporal de P02.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_informe_docx.py tests/test_contrato_api.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Correspondencia JSON→Word→Excel→web y acta del ingeniero; revisión textual automatizada no equivale a aceptación visual.

**Evidencia esperada:** `evidencia/P13/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P14. Entrenar y gobernar modelos del asistente

**Dependencias:** P01, P03. **Responsable propuesto:** ML y evaluación. **Recurso:** GPU exclusiva; memoria verificada.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/asistente/ajuste_condicionado.py`, `src/convertersmartgrid/asistente/modelos_en_uso.py`, `src/convertersmartgrid/asistente/llm_destilacion.py`, `src/convertersmartgrid/model_registry.py`, `src/convertersmartgrid/training_coordinator.py`, `tools/asistente_entrenar.py`, `tools/asistente_qlora.py`, `tools/asistente_comparar_revision.py`.

**Tareas abiertas que administra:** 027:T11, 027:T26, 043:T9, 047:T4, 047:T8, 047:T7, 069:T7, 070:T11.

- [ ] **Paso 1.** Releer decisiones y campaña concurrente antes de repetir entrenamientos; respetar el provisional ya autorizado y distinguirlo de un aprobado.
- [ ] **Paso 2.** Congelar dataset humano/maestro, particiones, puertas, semillas y presupuesto; prueba sellada apartada de selección y ajuste.
- [ ] **Paso 3.** Completar maestros 027 T26 con redacción de nombres; si la cuenta no permite el servicio, registrar bloqueo. No enviar datos reales a terceros.
- [ ] **Paso 4.** Ejecutar integral/validación cruzada con guardia existente y memoria suficiente. La campaña concurrente anotó mínimo 10 GiB libres: verificar configuración y disponibilidad actuales antes de lanzarla.
- [ ] **Paso 5.** Completar 047 T4/T8 y QLoRA de T7 cuando corresponda a 027 T11: pérdida solo de respuesta, comparación de checkpoints, exportación y reapertura exactas.
- [ ] **Paso 6.** Reabrir cada familia en CUDA (043 T9); medir candidato de 070 T11 y 069 T7 con prueba nueva. Registrar PROMOVIDO/RECHAZADO/BLOQUEADO_POR_DATOS/ERROR_ENTORNO sin promover para cerrar casillas.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_modelo_provisional.py tests/test_asistente_ajuste_condicionado.py tests/test_asistente_qlora.py tests/test_llm_destilacion.py tests_ml/test_destilacion_cuda.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** Puertas, calidad fuera de muestra y relectura por familia verificadas; una campaña terminada sin pasar puertas no cierra las tareas que exigen aprobar.

**Evidencia esperada:** `evidencia/P14/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P15. Medir RAG multilingüe con corpus real

**Dependencias:** P01. **Responsable propuesto:** RAG y evaluación. **Recurso:** GPU exclusiva.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/asistente/embeddings.py`, `src/convertersmartgrid/asistente/reranker.py`, `src/convertersmartgrid/asistente/evaluacion_rag.py`, `tools/asistente_evaluar_rag.py`.

**Tareas abiertas que administra:** 097:T3.

- [ ] **Paso 1.** Congelar corpus/consultas humanas de 047/077 y particiones de calibración/prueba antes de comparar candidatos.
- [ ] **Paso 2.** Comparar los embeddings de 097, incluido bge-m3 y referencia aplicable, sobre los mismos documentos/preguntas.
- [ ] **Paso 3.** Medir recuperación, reranking, latencia y memoria; calibrar solo sobre selección y sellar una vez al elegido.
- [ ] **Paso 4.** Reabrir índice publicado, comprobar versión/fuentes y respuesta en español desde la web.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_asistente_equipo.py tests/test_asistente_equipo_web.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 097 T3 con protocolo, métricas y decisión; existencia del índice no demuestra calidad de recuperación.

**Evidencia esperada:** `evidencia/P15/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P16. Backtest y campaña completa de pronóstico

**Dependencias:** P01, P03. **Responsable propuesto:** Pronóstico y datos. **Recurso:** CPU/GPU por turno; libros en lectura.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/pronostico_demanda.py`, `src/convertersmartgrid/digital_twin/series_causales.py`, `src/convertersmartgrid/digital_twin/temporal_entrenamiento.py`, `tools/pronostico_demanda.py`.

**Tareas abiertas que administra:** 089:T5, 089:T7.

- [ ] **Paso 1.** Custodiar cabecera, equivalencias, clientes, suministros y exógenas con disponibilidad temporal; fijar limpieza/cortes antes de evaluar.
- [ ] **Paso 2.** Persistir dataset con huella; probar que apoyo e imputaciones no usan datos posteriores al corte.
- [ ] **Paso 3.** Enumerar clase cabecera/cliente/escaladas × kW/kVAR × horizontes y modelos exigidos por 089; ningún alias de GRU sustituye a otro algoritmo.
- [ ] **Paso 4.** Ejecutar backtest real 2026 y corrida larga con orígenes, semillas y referencias comparables; guardar error, cobertura y latencia por objetivo.
- [ ] **Paso 5.** Seleccionar/reabrir con política causal y emitir perfiles por año a P17; falta de cobertura queda como objetivo bloqueado.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_pronostico_demanda.py tests/test_pronostico_integracion.py tests/test_pronostico_competicion.py tests/test_pronostico_multihorizonte.py tests/test_pronostico_gpu.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 089 T5/T7 con informe y decisión por combinación requerida, sin convertir un ganador global en cobertura de todos los objetivos.

**Evidencia esperada:** `evidencia/P16/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P17. PIDE anual y costos de fuentes reales

**Dependencias:** P12, P16. **Responsable propuesto:** Planeamiento y revisor humano. **Recurso:** DIgSILENT exclusivo; datos externos.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/pide.py`, `src/convertersmartgrid/pide_economia.py`, `src/convertersmartgrid/costos_fuentes.py`, `src/convertersmartgrid/formatos_pide.py`, `tools/pide_pf.py`, `specs/072-pide-y-planeamiento-de-largo-plazo/spec.md`, `specs/072-pide-y-planeamiento-de-largo-plazo/plan.md`, `specs/072-pide-y-planeamiento-de-largo-plazo/tasks.md`.

**Tareas abiertas que administra:** 027:T22, 072:T9b, 072:T11, 072:T13, 072:T14.

- [ ] **Paso 1.** Antes de T14, redactar RF EARS faltantes en spec 072 activa: flujo PIDE propio universal, copias con obra de corto plazo, años siguientes a cuatro, demanda 089, obras acumulativas y restitución. Asignar números libres tras releer el documento y obtener la aprobación requerida para los RF nuevos.
- [ ] **Paso 2.** Completar revisión humana del corpus T9b y usar solo lo aprobado para entrenar; conservar fuente/faltantes en redacción.
- [ ] **Paso 3.** Obtener base oficial exigida por T13 con URL, fecha, hash, moneda/unidad; verificar disponibilidad actual con el custodio. No sustituir otra resolución sin decisión metodológica expresa.
- [ ] **Paso 4.** En cada año, partir del caso previo y sus obras, aplicar proyección de P16, medir cuándo vuelve a fallar y la obra necesaria de ese año.
- [ ] **Paso 5.** Valorar obras reales; terreno/unidad/precio faltante se declara. Comparar formatos con los entregados de 027 T22.
- [ ] **Paso 6.** Presentar los dos entregables de 072 T11 al usuario/ingeniero; faltas de archivos oficiales o revisión mantienen bloqueo explícito.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_pide.py tests/test_pide_economia.py tests/test_formatos_pide.py tests/test_pide_pf.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** PIDE por años conserva demanda/obras/costos/fuentes; T14 no se implementa sin RF. T9b/T11/T13/T14 y 027 T22 tienen evidencia individual.

**Evidencia esperada:** `evidencia/P17/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P18. Piloto MADRL con fidelidad y prueba nativa

**Dependencias:** P05. **Responsable propuesto:** ML de obras e ingeniero. **Recurso:** Captura DIgSILENT; GPU en otro turno.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/madrl_obras.py`, `src/convertersmartgrid/madrl_politica.py`, `tools/madrl_entrenar.py`, `tools/madrl_obras.py`.

**Tareas abiertas que administra:** 074:T5, 074:T7, 074:T8.

- [ ] **Paso 1.** Recapturar redes reales y confirmar ntnum/fases/controles; al menos una red problemática debe superar fidelidad antes de entrenar.
- [ ] **Paso 2.** Fijar particiones por alimentador, referencia, semillas y presupuesto. No mezclar topologías ni ajustar con redes de prueba.
- [ ] **Paso 3.** Entrenar con controles reales, conservar curva/modelo; una prueba CPU sintética no acredita entrenamiento real.
- [ ] **Paso 4.** Evaluar alimentadores no vistos y confirmar obras en DIgSILENT, con reapertura y persistencia. Rechazo de política conserva su estado y límites.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_madrl_obras.py tests/test_madrl_politica.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 074 T5/T7/T8 con fidelidad, entrenamiento y prueba fuera de muestra; convergencia no sustituye eficacia ni aceptación eléctrica.

**Evidencia esperada:** `evidencia/P18/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P19. Conectar el ciclo único de aprendizaje continuo

**Dependencias:** P14, P15, P16, P18. **Responsable propuesto:** Coordinador ML, backend y frontend. **Recurso:** CPU de integración; GPU exclusiva en campaña.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/aprendizaje_continuo.py`, `src/convertersmartgrid/experimentos.py`, `src/convertersmartgrid/asistente/dataset_entrenamiento.py`, `src/convertersmartgrid/asistente/vigilancia.py`, `src/convertersmartgrid/asistente/modelos_en_uso.py`, `src/convertersmartgrid/digital_twin/buffer.py`, `src/convertersmartgrid/digital_twin/oraculo.py`, `src/convertersmartgrid/digital_twin/temporal.py`, `src/convertersmartgrid/digital_twin/temporal_entrenamiento.py`, `src/convertersmartgrid/web/app.py`, `src/convertersmartgrid/web/services.py`, `src/convertersmartgrid/web/api_contract.py`, `tools/aprendizaje_continuo.py`.

**Tareas abiertas que administra:** 050:T1b, 050:T2b, 050:T3b, 050:T4b, 050:T5b.

**Interfaz/decisión:** Reusar Muestra(observacion_id, familia, snapshot_id, origen, etiqueta, particion, contexto, record_id), ejecutar_ciclo, publicar_conjunto, revertir_conjunto y version_del_conjunto. Revisar todos los llamadores al extender firmas.

- [ ] **Paso 1.** T1b: fijar contexto de ciclo sin fingir un único proyecto. Propuesta: mapa ordenado proyecto→contexto_hash y huella agregada; mantener ContextoExperimento individual de 043. Aclarar esta decisión en spec/plan 050 antes de código.
- [ ] **Paso 2.** T2b: contrato propuesto crear_observacion_id(contexto_hash: str, fuente_hash: str, registro_id: str, instante: str) -> str en aprendizaje_continuo.py; usarlo en todos los productores de Muestra sin incluir familia en la identidad. Fijar pruebas de observación común, duplicación, partición cruzada y fuga.
- [ ] **Paso 3.** T3b: añadir publicar_individual: bool = True a entradas de entrenamiento PINN/temporal; coordinador pasa False. Las etapas registran candidatos sin cambiar punteros. Conectar Vigilante.ciclo a ejecutar_ciclo mediante cola cancelable.
- [ ] **Paso 4.** T4b: publicar_conjunto después de puertas individuales/conjuntas/retención. Con conjunto configurado, consumidores resuelven version_del_conjunto; si está corrupto bloquean. Compatibilidad heredada solo cuando no hay conjunto configurado.
- [ ] **Paso 5.** T5b: API y vista web de las siete fases reutilizando estado_aprendizaje y contratos de jobs; regenerar tipos y mantener controles existentes.
- [ ] **Paso 6.** Ejecutar primero integración mínima con archivos/modelos ligeros auténticos; luego dos capturas reales y ciclo completo: deduplicación, cancelación, cuarentena, no autorrecompensa, publicación atómica y reversión por relectura.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_aprendizaje_continuo.py tests/test_modelos_web.py tests/test_contrato_api.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 050 T1b–T5b con fuentes y modelos reales, identidad común, ciclo único y consumidores del conjunto. Dobles de control no cierran la campaña.

**Evidencia esperada:** `evidencia/P19/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P20. Asistente por consola y estados fieles de convergencia

**Dependencias:** P07, P10, P14, P15. **Responsable propuesto:** Operador, asistente y frontend. **Recurso:** Navegador y DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/asistente/interprete.py`, `src/convertersmartgrid/asistente/ejecutor.py`, `src/convertersmartgrid/web/services.py`, `src/convertersmartgrid/web/app.py`.

**Tareas abiertas que administra:** 026:T12, 027:T14, 067:T9, 070:T9, 070:T10, 078:T6, 078:T7, 086:T30.

- [ ] **Paso 1.** Ejecutar una orden real de cada tarea RF-11 de 026 en proyectos de prueba: interpretación, plan, confirmación y resultado.
- [ ] **Paso 2.** Completar alimentador, SET y carga nueva desde consola; informes/escalera salen de órdenes, no de atajos de API.
- [ ] **Paso 3.** Ver en navegador etapas, faltantes y consultas; sin datos no se inventa éxito.
- [ ] **Paso 4.** Proyecto bueno y otro no convergido: registrar IMPORTADO_SIN_CONVERGENCIA, NO_CONVERGE y return_code; repetir verificación y ordenar importar grupo ya convertido sin pedir alimentadores.
- [ ] **Paso 5.** Cerrar 027 T14 solo cuando sus criterios multisistema/gemelo/asistente estén medidos. Aplicar 086 T30 según beta vigente, sin llamar aprobado al provisional.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_asistente_web.py tests/test_asistente_equipo_web.py tests/test_aceptacion_agente.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 026/027/067/070/078 y beta de 086 con confirmaciones y resultado nativo rastreable.

**Evidencia esperada:** `evidencia/P20/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P21. Interrupciones, suspensión, fallos y operación sin red

**Dependencias:** P07, P09, P12. **Responsable propuesto:** QA operativo e integrador. **Recurso:** Ventana exclusiva con procesos propios identificados.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/web/jobs.py`, `src/convertersmartgrid/web/suspension.py`, `src/convertersmartgrid/web/workspace.py`, `src/convertersmartgrid/salidas_red.py`, `tools/sistema_web.py`, `tools/suite_por_tandas.py`.

**Tareas abiertas que administra:** 081:T10, 081:T11, 081:T12, 081:T13, 081:T14, 081:T31, 086:T36, 086:T33, 096:T3.

- [ ] **Paso 1.** Preparar copias, PID/espacio/raíz de procesos propios y ventana sin trabajos ajenos; no terminar procesos ni desconectar sesiones de otros.
- [ ] **Paso 2.** Ensayar acoplador/banco incompatible, SED sin fase servida y sistema parcial; comprobar CONVERGE_SIN_SERVIR y continuidad del resto.
- [ ] **Paso 3.** Medir huella real de Caso base antes/después; deriva conserva diferencias y bloquea, no reescribe baseline.
- [ ] **Paso 4.** Cortar escalera con transferencia, importación y calibración propias; verificar retirada de aperturas propias, estado interrumpido, siguiente orden y reanudación idempotente.
- [ ] **Paso 5.** Suspender/despertar a mitad de recalibración propia (096 T3); suite nocturna separada sobrevive a cierre de su web y registra interrupción si termina su proceso.
- [ ] **Paso 6.** Ensayar red realmente cortada en equipo/entorno de prueba, importar/calibrar/informe y avisos de cada salida apagada. Restaurar servicio tras la prueba.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_trabajos_interrumpidos.py tests/test_workspace_runtime.py tests/test_huella_caso_base.py tests/test_seguridad_web.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 081/086 T33/T36 y 096 T3 con conservación y recuperación reales; no se sustituyen por sembrar un estado sintético en el diario.

**Evidencia esperada:** `evidencia/P21/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P22. Instalador, complemento IA, update/rollback y tercero

**Dependencias:** P01, P11, P13, P21. **Responsable propuesto:** Empaquetado y operador externo. **Recurso:** Equipo de prueba; DIgSILENT exclusivo.

**Archivos existentes a revisar o modificar:** `tools/construir_candidato.py`, `tools/instalar_candidato.py`, `tools/comprobar_entrega.py`, `docs/MANUAL_INSTALACION.md`, `docs/MANUAL_OPERADOR.md`, `docs/SEGURIDAD_Y_PRIVACIDAD.md`.

**Tareas abiertas que administra:** 086:T40, 086:T41, 086:T32.

- [ ] **Paso 1.** Construir wheel/candidato desde revisión elegida, Python embebido 3.12 y ruedas con huella; neutralizar comentarios D5 y comprobar con --candidato.
- [ ] **Paso 2.** Generar SBOM/avisos y auditorías actuales de núcleo/complemento; no inferir licencias por lista automática.
- [ ] **Paso 3.** Instalar setup.exe sin Node ni herramientas de desarrollo en entorno; convertir desde la web instalada y ejecutar importación nativa con el Python entregado.
- [ ] **Paso 4.** Actualizar y revertir conservando hashes de datos/espacios/modelos; candidato alterado se rechaza antes de tocar la instalación válida.
- [ ] **Paso 5.** Construir/instalar complemento IA y reabrir modelos; su ausencia no rompe núcleo. Ejecutar otra empresa hasta Word/Excel y revisión del ingeniero.
- [ ] **Paso 6.** Una persona ajena instala y convierte solo con manual; registrar dificultades y corregir manuales antes de repetir.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_instalacion_programa.py tests/test_entrega_universal.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 086 T32/T40/T41 acreditadas con setup.exe y Python entregado; import powerfactory sin abrir motor no equivale a cadena completa.

**Evidencia esperada:** `evidencia/P22/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P23. Migración final de arquitectura y frontend

**Dependencias:** P04, P19, P20. **Responsable propuesto:** Arquitectura e integrador. **Recurso:** CPU; validaciones reales por turno.

**Archivos existentes a revisar o modificar:** `pyproject.toml`, `docs/implementacion065/deuda_arquitectura.json`, `src/convertersmartgrid`, `src/vnr_etl`, `tools`, `frontend/src`, `CODIGO_FUENTE.md`.

**Tareas abiertas que administra:** 002:T7, 002:T8, 002:T9, 002:T11, 002:T12.

- [ ] **Paso 1.** Congelar grafo capa/módulo, consumidores dinámicos/entry points y 37 excepciones; dueño y lista exacta de archivos por movimiento.
- [ ] **Paso 2.** T7: mover dominio→puertos→aplicación→adaptadores→presentación, con reexportaciones temporales y pruebas/DGS en cada bloque.
- [ ] **Paso 3.** T8: mover vnr_etl a convertersmartgrid.adaptadores.entrada.vnr conservando comando vnr-etl y contratos de entrada.
- [ ] **Paso 4.** T9: actualizar todos los consumidores/scripts/tests/entry points antes de retirar reexportaciones; recorrer imports dinámicos.
- [ ] **Paso 5.** T11: frontend api/shared/features/app con regla de fronteras. package.json actual carece de lint: añadir script/dependencias adecuados, preservar todas las superficies UI y ejecutar lint/typecheck/build.
- [ ] **Paso 6.** T12: actualizar índices/tipos/arquitectura, reducir deuda a cero exigido por spec, comparar DGS sin regeneración automática.
- [ ] **Paso 7.** Planificar revalidación nativa tras los movimientos: cadena por cada fuente y módulos nativos afectados; evidencia previa al refactor no valida automáticamente el final.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_capas.py tests/test_modulos.py tests/test_contrato_api.py tests/test_linea_base_001.py tests/test_inventario.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 002 completa con entry points/imports y DGS preservados, ninguna excepción residual exigida por el contrato y ninguna función UI eliminada.

**Evidencia esperada:** `evidencia/P23/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P24. Renombrar conservando identidad, entornos y worktrees

**Dependencias:** P22, P23. **Responsable propuesto:** Integrador y responsable del puesto. **Recurso:** Ventana exclusiva; ensayo previo en copia.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/runtime_paths.py`, `tools/copia_datos.py`, `run_gui.bat`, `docs/MANUAL_INSTALACION.md`, `.agents/coordination/ACTIVE.md`.

**Tareas abiertas que administra:** 058:T6, 086:T9.

- [ ] **Paso 1.** Ensayar 086 T9 completo en copia: freeze, worktrees/junctions/acceso directo, espacios y vínculos PF; fijar identidad con copia_datos.py antes de mover.
- [ ] **Paso 2.** Verificar rutas absolutas resueltas y ausencia de procesos activos en ellas; renombrar solo en ventana acordada, sin forzar ni borrar destinos.
- [ ] **Paso 3.** Reparar worktrees/junctions/entry points; preservar .venv/Torch según T9, sin rehacer modelos ni perder versiones.
- [ ] **Paso 4.** Antes de guardar por la web, comparar espacios/rutas expandidas y vínculo PF con la foto; probar CUDA en el entorno correspondiente.
- [ ] **Paso 5.** Ejecutar rollback del ensayo. Tras cambio real autorizado, validar rutas definitivas en P25; archivar worktrees solo con su autorización concreta.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_workspace_runtime.py tests/test_instalacion_programa.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 058 T6/086 T9: identidad, espacios, modelos y entorno conservados; rollback ensayado y sin borrado de trabajo ajeno.

**Evidencia esperada:** `evidencia/P24/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P25. Aceptación final de una sola revisión

**Dependencias:** P03, P05, P06, P07, P08, P09, P10, P11, P12, P13, P14, P15, P16, P17, P18, P19, P20, P21, P22, P23, P24. **Responsable propuesto:** Integrador y responsables de dominio. **Recurso:** Suite/GPU/DIgSILENT por turnos.

**Archivos existentes a revisar o modificar:** `tools/verificar_candidato.py`, `tools/trazabilidad_candidato.py`, `tools/estado_specs.py`, `docs/ARQUITECTURA.md`, `specs/README.md`, `CLAUDE.md`.

**Tareas abiertas que administra:** 025:T22, 058:T5, 065:T12, 065:T13, 086:T31.

- [ ] **Paso 1.** Congelar revisión/manifiesto final tras arquitectura/rutas. Verificar fuentes, modelos y entorno; ninguna referencia se regenera para ocultar diferencias.
- [ ] **Paso 2.** Preparar nueve entradas CSG, CSG_MCP_PYTHON, CSG_EVIDENCIA_NATIVA y artefactos tests_ml del alcance completo; validar existencia/huellas antes de arrancar.
- [ ] **Paso 3.** Ejecutar verificar_candidato.py --ejecutar --suite-completa --hash-datos hacia evidencia externa: cero fallos/errores/skips/xfail y cero deriva.
- [ ] **Paso 4.** Frontend test/typecheck/build aislado, auditorías, tests_ml reales y campañas requeridas se consolidan con P03. Ausencia de dependencia requerida bloquea completa.
- [ ] **Paso 5.** Revalidar nativamente escenarios afectados de la revisión final; no sumar corridas de commits distintos sin trazabilidad de impacto y reejecución necesaria.
- [ ] **Paso 6.** Generar matriz RF→archivo→prueba→ejecución→dominio y revisar semántica; confrontar los 115 pendientes y actualizar Estado/índice solo con cierres reales.
- [ ] **Paso 7.** Separar production_ready_core, scientific_acceptance por familia, operational_acceptance y project_complete. Si faltan datos o calidad exigida, conservar false en la condición correspondiente.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_linea_base_001.py tests/test_inventario.py tests/test_trazabilidad_specs.py tests/test_capas.py tests/test_contrato_api.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** T31/065 T12-T13 y relacionadas con evidencia final íntegra; completa solo con cada tarea activa exigida cerrada o condicional no aplicable documentada, sin omisión oculta.

**Evidencia esperada:** `evidencia/P25/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## P26. Entrega y publicación con autorización concreta

**Dependencias:** P25. **Responsable propuesto:** Integrador y usuario. **Recurso:** Sin motores; publicación autorizada.

**Archivos existentes a revisar o modificar:** `src/convertersmartgrid/__init__.py`, `frontend/package.json`, `src/convertersmartgrid/recursos/NOTAS_VERSION.md`, `LICENSE`, `config/entrega.json`.

**Tareas abiertas que administra:** 086:T34.

- [ ] **Paso 1.** Preparar versión única/notas, hashes, SBOM, manuales, respaldo y procedimiento de actualización/reversión según alcance realmente aceptado.
- [ ] **Paso 2.** Comprobar que repositorio/paquete no incorporan entradas, perfiles privados, tokens, pesos ajenos o evidencia confidencial.
- [ ] **Paso 3.** Respetar D3/D7 actuales; no imponer asesoría legal descartada ni suponer permisos de publicación por acabar pruebas.
- [ ] **Paso 4.** Presentar artefacto concreto y acta P25; etiqueta v1.0.0/push/publicación solo con orden explícita del usuario.
- [ ] **Paso 5.** Verificar versión y hash descargables e instalación de control después de publicar; entregar responsable de soporte.

**Verificación enfocada prevista:**

```powershell
.venv/Scripts/python.exe -B -m pytest -q -rs tests/test_instalacion_programa.py
```

Ejecutar desde el worktree/candidato dueño, con temporal y evidencia externos. Para pruebas nativas por relectura, establecer `CSG_EVIDENCIA_NATIVA` solo tras la corrida real correspondiente; pytest no abre el motor.

**Cierre:** 086 T34 solo cierra con orden y evidencia de publicación; en espera de orden el estado es listo para publicar, no publicado.

**Evidencia esperada:** `evidencia/P26/manifest.json`, comandos, revisión/hash, entradas, resultados, limitaciones, dueño y siguiente acción. Fundamento metodológico A/B/C; para dominio eléctrico y modelos, también D/E.

## Cobertura íntegra de hallazgos

| Hallazgo | Paquetes responsables |
| --- | --- |
| H01 | P01 |
| H02 | P02 |
| H03 | P03, P25 |
| H04 | P05, P07, P08, P09, P10, P11, P12, P25 |
| H05 | P21, P22, P24 |
| H06 | P14, P15, P20 |
| H07 | P19 |
| H08 | P06 |
| H09 | P23 |
| H10 | P00, P22, P24, P26 |
| H11 | P00, P01, P02, P03, P04, P05, P06, P07, P08, P09, P10, P11, P12, P13, P14, P15, P16, P17, P18, P19, P20, P21, P22, P23, P24, P25, P26 |

## Cobertura de las 115 tareas originales

La matriz `2026-11-07-cierre-produccion-integral-cobertura.csv` contiene una fila por tarea abierta con propietario, recurso, dependencia, ruta/línea, SHA-256 del tasks.md leído, criterio original y evidencia esperada. El anexo `2026-11-07-cierre-produccion-integral-tareas.json` conserva los bloques originales y los 27 paquetes. No hay tareas huérfanas ni dos paquetes que reclamen el cierre primario de una misma tarea.

| Paquete | Tareas originales |
| --- | --- |
| P00 | transversal |
| P01 | transversal |
| P02 | transversal |
| P03 | transversal |
| P04 | transversal |
| P05 | 027:T29, 027:T30, 027:T31, 045:T3, 045:T4, 048:T4 |
| P06 | 049:T4 |
| P07 | 008:T7, 011:T19, 012:T13, 013:T7, 028:T11, 037:T4, 086:T24 |
| P08 | 016:T18, 081:T20, 086:T25 |
| P09 | 042:T50, 042:T48, 042:T44, 042:T37, 071:T5, 081:T24, 084:T8, 084:T9, 086:T26, 087:T27, 087:T12, 087:T13, 092:T2 |
| P10 | 028:T6, 039:T4, 042:T6, 052:T4, 073:T8, 086:T27 |
| P11 | 042:T29, 051:T3, 055:T2, 056:T3, 058:T7, 081:T16, 086:T28, 087:T14 |
| P12 | 004:T20, 025:T21, 039:T8, 042:T42, 091:T7, 094:T5, 098:T6, 099:T3 |
| P13 | 017:T13, 017:T14, 017:T19, 073:T12, 081:T22, 086:T29 |
| P14 | 027:T11, 027:T26, 043:T9, 047:T4, 047:T8, 047:T7, 069:T7, 070:T11 |
| P15 | 097:T3 |
| P16 | 089:T5, 089:T7 |
| P17 | 027:T22, 072:T9b, 072:T11, 072:T13, 072:T14 |
| P18 | 074:T5, 074:T7, 074:T8 |
| P19 | 050:T1b, 050:T2b, 050:T3b, 050:T4b, 050:T5b |
| P20 | 026:T12, 027:T14, 067:T9, 070:T9, 070:T10, 078:T6, 078:T7, 086:T30 |
| P21 | 081:T10, 081:T11, 081:T12, 081:T13, 081:T14, 081:T31, 086:T36, 086:T33, 096:T3 |
| P22 | 086:T40, 086:T41, 086:T32 |
| P23 | 002:T7, 002:T8, 002:T9, 002:T11, 002:T12 |
| P24 | 058:T6, 086:T9 |
| P25 | 025:T22, 058:T5, 065:T12, 065:T13, 086:T31 |
| P26 | 086:T34 |

## Matriz de aceptación y condiciones de no avance

| Puerta | Evidencia requerida | Condición que conserva el bloqueo |
| --- | --- | --- |
| G0. Identidad | corte, dueños, entradas y hashes | revisión/fuente/caso ambiguos |
| G1. Entorno | lock, capabilities, auditoría y Python real | paquete bajo política, driver requerido ausente |
| G2. Regresión | frontend/backend completos del alcance y JUnit | fallo, skip/xfail requerido, timeout o candidato que deriva |
| G3. Dominio | casos nativos, persistencia, reapertura y umbrales de perfil | fuera de dominio, carga no servida, límites eléctricos incumplidos |
| G4. Modelos | particiones, política, métricas, relectura y decisión | fuga, rechazo de puerta o falta de modelo exigido |
| G5. Operación | instalador, rollback, cortes, sin red y tercero | pérdida/corrupción de datos o funcionamiento no reproducible |
| G6. Completitud | 115 criterios y RF revisados, alcance explícito | tarea activa requerida pendiente o dato externo ausente |
| G7. Publicación | artefacto y orden expresa del usuario | orden ausente o candidato distinto del aprobado |

`production_ready_core` exige G0–G5 del alcance comercial 086 y sus dependencias. `project_complete` exige además G6 de todos los módulos activos. `published` exige G7. Ninguna cantidad de tests por sí sola activa los tres estados.

## Comandos de cierre a parametrizar con datos comprobados

Los siguientes comandos son previstos para ejecución futura; no se ejecutaron al redactar el plan. Leer `--help` en el candidato vigente antes de mutaciones. Las variables se rellenan con el manifiesto de P00, nunca con rutas supuestas.

```powershell
# Lectura y contratos
.venv/Scripts/python.exe -B tools/estado_specs.py --comprobar
.venv/Scripts/python.exe -B tools/arquitectura.py --json
.venv/Scripts/python.exe -B tools/generar_contrato_api.py --check
.venv/Scripts/python.exe -B -m pip check

# Frontend: ejecutar desde frontend; build con runtime/destino aislados
npm test
npm run typecheck
npm run build
npm audit --json --package-lock-only --ignore-scripts

# Regresión real: desde raíz, con nueve entradas CSG, MCP y evidencia nativa
.venv/Scripts/python.exe -B tools/verificar_candidato.py --root $raizCandidata --output-dir $evidenciaCandidata --python $pythonCandidato --ejecutar --suite-completa --hash-datos

# Cobertura ML adicional del proyecto completo, tras preparar datos/modelos/GPU
& $pythonCandidato -B -m pytest -q -rs tests_ml --basetemp $temporalMl --junitxml $junitMl

# Nueva herramienta de P03; disponible solo después de implementarla
& $pythonCandidato -B tools/verificar_entrega_integral.py --root $raizCandidata --python $pythonCandidato --output-dir $evidenciaIntegral --edicion completa
```

Las nueve entradas del runner son `CSG_RED`, `CSG_LOADS`, `CSG_EQUIPMENT`, `CSG_MDB`, `CSG_EQUIPMENT_MDB`, `CSG_DEMANDA_DIR`, `CSG_VNR_BAK`, `CSG_SOLICITUD_PDF`, `CSG_SOLICITUD_DIR`. Además `CSG_MCP_PYTHON` y `CSG_EVIDENCIA_NATIVA` son requisitos de las pruebas correspondientes. Los artefactos de `tests_ml` y sus variables se validan según cada test; no se presupone que esas once variables basten para ML.

## Bloqueos externos y responsables

- **Protecciones:** custodio/ingeniero entrega curvas, ajustes, poder de corte e impedancias reales. P06 permanece bloqueado hasta entonces.
- **PIDE/costos:** custodio verifica publicación/versión de la base oficial de 072 T13; el plan no presenta la nota histórica de no disponibilidad como estado web actual. No hay sustitución silenciosa ni costos inventados.
- **Revisión humana:** responsable de corpus PIDE y operador/tercero reservan tiempo para T9b/T11/T41; no se autogenera una aprobación.
- **GPU y memoria:** dueño de la máquina reserva turno; las campañas comparten recursos con otros proyectos. No se libera memoria terminando procesos ajenos.
- **Cuenta/maestros:** P14 registra disponibilidad real y aplica redacción. Falta de servicio no se simula con etiquetas inventadas.
- **Publicación y renombrado real:** integrador presenta resultados concretos para la acción autorizada, sin reabrir decisiones previas de alcance. Este plan no ejecuta esas acciones.

## Gestión de archivos, evidencia y reversión

Cada manifiesto de paquete debe registrar `package_id`, responsable, estado, commit y hash del candidato, rutas/hash de entradas, perfil, contexto, caso, versión nativa, semillas/política si aplica, comandos y códigos de salida, archivos de evidencia, resultado y pendientes. La comparación final verifica que el manifiesto corresponde al artefacto entregado.

Los cambios de modelo se revierten al puntero anterior comprobado; los de instalación usan el rollback ensayado; los de PowerFactory se aplican a proyectos de prueba y retiran sus propias variaciones, con relectura. Los originales y respaldos se conservan. No se usa un reset global para revertir el trabajo de otra sesión.

Los directorios amplios de P23 se desglosan por el grafo real en archivos explícitos antes de moverlos; P00 registra su dueño. Los paths aquí indicados no otorgan exclusividad sobre archivos que ya posee otra sesión: primero se acuerda la cesión. En particular services.py es superficie compartida y conserva el diff actual.

## Fundamento académico consultado en la web

**A. Maestría.** Eriksson, E., y Mosaddegh, K. (2021). *Establishing Feedback in Continuous Delivery – Benefits and Approaches*, Lund University. [Índice institucional](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/index.html), [tesis](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf). Fundamenta resultados visibles y retroalimentación de producto/proceso. El índice se verificó en esta preparación; el PDF dio timeout al reabrir y su contenido había sido consultado en el diagnóstico.

**B. Doctorado.** Strandberg, P. E. (2021). *Automated System-Level Software Testing of Industrial Networked Embedded Systems*, Mälardalen University, Dissertation 349. [Fuente institucional](https://www.es.mdh.se/pdf_publications/6347.pdf). Fundamenta pruebas de sistema/configuración, recursos controlados y resultados accionables.

**C. Artículo indexado.** Shahin, M., Ali Babar, M., y Zhu, L. (2017). *Continuous Integration, Delivery and Deployment: A Systematic Review on Approaches, Tools, Challenges and Practices*. IEEE Access, 5, 3909–3943. DOI 10.1109/ACCESS.2017.2685629. [Ficha institucional con enlace a Scopus](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/). Sustenta puertas integradas de construcción/pruebas/seguridad y confiabilidad de entrega.

**D. Artículo científico.** Shen, Z., Arraño-Vargas, F., y Konstantinou, G. (2024). *Virtual testbed for development and evaluation of power system digital twins and their applications*. Sustainable Energy, Grids and Networks, 38, 101331. DOI 10.1016/j.segan.2024.101331. [Editorial](https://www.sciencedirect.com/science/article/pii/S2352467724000602). Sustenta evaluación del gemelo antes del despliegue, dominio explícito y entorno controlado. Se contrastaron resumen/metadatos de la editorial; acceso directo completo restringido.

**E. Revisión científica.** Aghazadeh Ardebili, A., Zappatore, M., Ramadan, A. I. H. A., Longo, A., y Ficarella, A. (2024). *Digital Twins of smart energy systems: a systematic literature review on enablers, design, management and computational challenges*. Energy Informatics, 7, 94. DOI 10.1186/s42162-024-00385-5. [Editorial](https://link.springer.com/article/10.1186/s42162-024-00385-5). Fundamenta arquitectura, datos/persistencia y evaluación de integración en sistemas energéticos.

Consulta web: 7 de noviembre de 2026. Estas fuentes justifican el método; no certifican este software, no fijan sus umbrales de ingeniería ni garantizan que un entrenamiento pase. Los criterios concretos proceden de las specs y perfiles auditados.

## Revisión del plan y estado de entrega

- [x] Revisado corte Git y preservado el diff preexistente.
- [x] Releídas constitución, coordinación, diagnóstico, specs y planes afectados.
- [x] Veintisiete paquetes con dependencias, responsable propuesto, archivos, pasos y cierre.
- [x] Ciento quince tareas abiertas asignadas exactamente una vez; criterios y hashes de origen conservados.
- [x] Todos los hallazgos H01–H11 tienen tratamiento y todos los Review Focus un paquete responsable.
- [x] Verificados paths existentes, dependencias sin ciclos y cobertura sin tareas huérfanas.
- [x] Separadas firmas actuales de interfaces propuestas; descrita compatibilidad de consumidores.
- [ ] Implementación, campañas, aceptación nativa/científica/operativa y publicación: **no ejecutadas por este pedido de planificación**.

La siguiente unidad ejecutable es P00 y luego P01/P02, respetando archivos y turnos. No se necesita volver a diagnosticar todo antes de empezar: refrescar identidad/cambios y ejecutar la tarea concreta con su prueba.
