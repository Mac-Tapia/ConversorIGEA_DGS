# Spec 043 — Consolidación y gobierno de modelos

Estado: aprobada · Fecha: 2026-10-31

## Contexto y objetivo

El worktree de reentrenamiento contiene registro, coordinador, datasets y QLoRA que deben integrarse antes de añadir otro circuito de entrenamiento. Los informes históricos no prueban activación en la raíz.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 024, 026 y 027; integración selectiva del worktree de reentrenamiento.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA mantendrá un único registro de candidatos con los estados terminales PROMOVIDO, RECHAZADO, BLOQUEADO_POR_DATOS y ERROR_ENTORNO.
- RF-2: CUANDO se registre un experimento, EL SISTEMA conservará su contexto exacto de fuente, red, caso, año, periodo, criterio de fijas, perfil, controles y revisiones.
- RF-3: CUANDO se construya un dataset, EL SISTEMA distinguirá órdenes reales revisadas, datos sintéticos y contexto documental por su custodia.
- RF-4: SI dos registros comparten una misma observación o escenario de origen, ENTONCES EL SISTEMA los agrupará antes de particionar.
- RF-5: CUANDO se promueva un candidato, EL SISTEMA exigirá sus puertas aprobadas y una reapertura correcta de los artefactos en otro proceso.
- RF-6: MIENTRAS haya una etapa CUDA activa, EL SISTEMA impedirá que otra etapa de entrenamiento tome la misma GPU.
- RF-7: CUANDO se reanude una ejecución, EL SISTEMA preservará las etapas terminales compatibles con la configuración registrada.
- RF-8: CUANDO la web consulte los modelos, EL SISTEMA mostrará el estado respaldado por el informe vigente de cada familia.
- RF-9: CUANDO se prepare un proyecto de GitHub para reutilizarlo, EL SISTEMA registrará su URL de origen, revisión exacta y licencia verificable en un catálogo versionado.
- RF-10: SI una copia de terceros contiene cambios locales o una revisión distinta de la fijada, ENTONCES EL SISTEMA impedirá reemplazarla automáticamente.
- RF-11: EL SISTEMA mantendrá las copias de terceros fuera de la instalación y del arranque obligatorios del conversor.

## Requisitos no funcionales

- RF-13: CUANDO el coordinador invoque un trabajador de entrenamiento o evaluación, EL SISTEMA usará un entrypoint existente con argumentos compatibles, conservará informe atómico de éxito, bloqueo o error, y distinguirá operación ejecutada de promoción, sin descargar datos ni activar candidatos implícitamente.
- RF-14: EL SISTEMA construirá el dataset de entrenamiento con una orden propia, en una carpeta nueva, sin pisar el anterior.
- RF-15: CUANDO se construya el dataset, EL SISTEMA dirá si está completo, y qué falta, midiendo solo datos reales revisados frente a los umbrales de la spec 027.

- RF-12: CUANDO se preparen dependencias y pesos locales, EL SISTEMA conservará versiones, revisiones, licencias, tamaños y hashes de los modelos seleccionados; verificará archivos completos y disponibilidad local sin activar candidatos ni declarar aceptación por descargarlos. Los fallos se guardarán con salida no exitosa y sin eliminar descargas parciales. La instalación de paquetes conservará las versiones existentes del núcleo y acreditará imports y operaciones reales.

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- Contextos con igual nombre y fuente distinta: T2, test_contexto_distinto_no_reutiliza.
- Lock GPU ilegible o perteneciente a proceso vivo: T1, test_lock_ilegible_bloquea.
- Artefacto promovido que no reabre: T3, test_smoke_fallido_no_promueve.
- Órdenes sintéticas contadas como reales: T2, test_sintetico_no_es_gold_real.
- Informe reanudado con configuración distinta: T3, test_resume_config_distinta_rechaza.

## Fuera de alcance

No entrenar arquitecturas nuevas en este paquete; no copiar pesos ni todo el worktree; no cambiar las puertas eléctricas.

## Criterios de finalización

Cada RF tiene una prueba con cita `043:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

La evaluación reproducible y la separación de modelos/datos materializan las limitaciones de escalabilidad y confianza discutidas por Stiasny; reutilizar el donante reduce vías de promoción inconsistentes.

## Clarificaciones de diseño

El usuario autorizó implementar este alcance. El estado aprobada indica que quedan
tareas abiertas; crear el plan no cambia el estado de specs anteriores.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

