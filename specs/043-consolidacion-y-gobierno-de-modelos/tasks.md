# Tareas — Spec 043

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Integrar registro y exclusión de GPU. (RF-1, RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_model_registry.py tests/test_training_coordinator.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [x] T2. Contrato común y custodia de datos. (RF-2, RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos.py tests/test_asistente_dataset_entrenamiento.py tests/test_asistente_calidad_datos.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Runner, reanudación y promoción con reapertura. (RF-5, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos_runner.py tests/test_reentrenamiento_integral.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4. Visibilidad y aceptación de integración. (RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_modelos_web.py tests/test_model_registry.py tests/test_training_coordinator.py tests/test_experimentos.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan.

- [x] T5. Preparar repositorios GitHub con URL, commit y licencia fijados, sin sobrescribir copias modificadas ni imponer dependencias al núcleo. (RF-9, RF-10, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_upstream_ia.py` pasa y `tools/preparar_upstream_ia.py --verificar` valida las copias reales del catálogo.

## Evidencia de ejecución

- [x] T7. Completar los cuatro trabajadores ausentes y sus contratos con el runner. (RF-5, RF-6, RF-7, RF-13)
      Hecho cuando: existen y pasan ayuda/validación los CLI temporal, evolutivo, embeddings y QLoRA; el runner solo envía opciones aceptadas; se prueban informes reales de bloqueo y operaciones disponibles, exclusión GPU heredada y preservación del activo. Crear archivos no acredita ajustes completos ni aceptación integral.

T7, 2026-11-01: cuatro entrypoints implementados, `--dataset-v2` funcional en el
trabajador del asistente, corpus generativo separado mediante `--llm-dataset`,
guardia padre/hijo verificada en procesos reales y reportes atómicos con motivos.
Regresión final de código: 94 aprobadas, cero fallos/errores/omisiones.
Benchmark real GA/NSGA-II/DE: 30 semillas por algoritmo. Con fuentes reales, QLoRA
rechaza la huella antigua, GRU detecta fecha/potencia ausente y embeddings encontró
memoria insuficiente; ningún bloqueo se presenta como entrenamiento completado.
Se corrigieron cuatro hallazgos de revisión con pruebas RED/GREEN. Detalles y
límites en [trabajadores](../../docs/TRABAJADORES_COORDINADOR_2026-11-01.md).
Este cierre solo acredita los trabajadores/contratos de T7, no T3, 047 T7 ni 050.

- [x] T6. Instalar y verificar bibliotecas y pesos faltantes del catálogo local. (RF-12)
      Hecho cuando: el catálogo fijado, las pruebas de preparación, las descargas completas y las operaciones reales de bibliotecas/modelos tienen informes; `pip check` pasa sin cambiar las versiones previas del núcleo. Descargar no cierra entrenamiento, integración o aceptación eléctrica.
- [x] T8. Orden que construye el dataset y dice si está completo. (RF-14, RF-15)
      Hecho cuando: `pytest -q tests/test_construir_dataset_entrenamiento.py` en verde.

T5: siete pruebas con Git y subprocesos reales pasaron; se verificaron las nueve
copias públicas. Catálogo y reproducción en [reutilización GitHub](../../docs/REUSO_GITHUB_IA_2026-10-31.md).
La implementación de adaptadores y su aceptación permanecen en 045–048.

T6: 33 paquetes instalados, cero versiones previas del núcleo cambiadas,
`pip check` correcto; nueve ensayos de entorno/GPU y un ensayo real Ipopt pasaron.
Catálogos fijados y descargas reanudables implementados; cinco modelos completos
verificados por segunda auditoría. [Informe](../../docs/ACEPTACION_INTEGRAL_AGENTE_2026-10-31.md).

Continuación local: BGE completó descarga y verificación de archivos/hashes;
E5 y nomic están disponibles. Se fijó la base Instruct-2507 NF4 para PEFT y se
preservó la variante FP16 como experimento archivado. Las pruebas nuevas de carga
están en `tests_ml/test_pesos_ia.py`; E5/CUDA encontró error Windows 1455 y el control
previo de RAM informó el bloqueo sin omitirlo; se conservan esos informes históricos.

Descargas terminadas: el catálogo canónico completo pasó una segunda auditoría
con cinco modelos verificados y cero activaciones; informe
`output/aceptacion_200_20261031/catalogo_completo_verificado.json`.
Con los pesos completos, los tres ensayos E5/BGE/NF4 terminaron con error previo
de recursos (1,54 GiB libres; requieren 3/4/6 GiB), sin cargar pesos ni omitirlos;
evidencia histórica `pesos_completos_precondiciones.xml`.

Corrección y cierre: el control ahora distingue RAM física y memoria comprometible
Windows, y los trabajadores CUDA salen antes de arrancar el siguiente. La ejecución
conjunta `tests_ml/test_pesos_ia.py` terminó con **3 aprobadas, cero omisiones** en
146,80 s (`pesos_cuda_integrales.xml`): codificación E5, pares BGE y un paso LoRA
NF4 con reapertura real en otro proceso. Pico NF4 4.209.276.928 bytes; diferencia
máxima de logits tras recarga 0,0. Adaptador y JSON conservados en
`output/aceptacion_200_20261031/nf4_adaptador_verificado/`, sin activación.
Qwen3:8b completó selección real de 27 órdenes, totalmente en GPU, con digest
fijado; nomic produjo dos vectores locales. Se cierra preparación/operaciones,
sin cerrar entrenamiento del agente, calidad ni aceptación eléctrica por arrastre.

Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.


Ejecución 2026-10-31: ver [registro y pendientes](../../docs/EJECUCION_IA_2026-10-31.md).

Las tareas abiertas pueden contener código parcial: el registro distingue implementación, datos reales, verificación y aceptación pendiente.
