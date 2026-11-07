# Spec 049 — Protecciones nativas y coordinación

Estado: implementada · Fecha: 2026-10-31

## Contexto y objetivo

La publicación DIgSILENT enlaza funciones de protecciones. Hoy el catálogo menciona ComProtgraphic, pero faltan curvas reales y la lista ejecutable no incluye este estudio; presencia en catálogo no es cumplimiento.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 043–045; catálogo de estudios y datos de empresa existentes; 048 solo si se optimizan ajustes.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se solicite protecciones, EL SISTEMA comprobará disponibilidad de funciones en la versión y licencia nativas conectadas.
- RF-2: SI faltan curvas, ajustes, relaciones de medida o datos de fuente requeridos, ENTONCES EL SISTEMA bloqueará el estudio con la lista concreta de ausencias.
- RF-3: CUANDO se importe un ajuste, EL SISTEMA conservará modelo de dispositivo, unidades y procedencia de sus parámetros.
- RF-4: CUANDO se construya un escenario de falla, EL SISTEMA incluirá los aportes de generación y estados de equipos del caso vinculado.
- RF-5: CUANDO se evalúe coordinación, EL SISTEMA comparará primaria y respaldo con el intervalo requerido por el perfil para cada falla aplicable.
- RF-6: CUANDO se evalúe un dispositivo, EL SISTEMA comprobará sensibilidad y poder de corte con datos nominales trazables.
- RF-7: CUANDO se publique el estudio, EL SISTEMA distinguirá fallas evaluadas, fallas no cubiertas y criterios incumplidos.
- RF-8: CUANDO se propongan ajustes, EL SISTEMA los mantendrá en una variación separada hasta su validación.
- RF-9: CUANDO se acepten ajustes en el modelo, EL SISTEMA verificará su persistencia mediante reapertura y relectura nativa.
- RF-10: CUANDO la web ofrezca el estudio, EL SISTEMA mostrará disponibilidad y resultados sin presentar un flujo convergente como selectividad validada.

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- Comando presente sin módulo licenciado: T1, test_sin_curvas_o_licencia_bloquea.
- Fila DEFAULT con poder de corte cero: T1, test_default_no_es_ficha_real.
- CT/VT o tiempos en unidades incompatibles: T2, test_unidades_y_relaciones_requeridas.
- Central térmica existente no incluida en falla: T2–T4, test_generacion_existente_aporta.
- Solo una falla da apariencia de coordinación global: T3, test_falla_no_evaluada_no_aprueba.

## Fuera de alcance

Configurar relés de campo o StationWare; automatización de disparos reales; prometer funciones PF2026 en otra versión; distancia/diferencial/RMS/EMT sin equipo, modelo y licencia apropiados.

## Criterios de finalización

Cada RF tiene una prueba con cita `049:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

La [tesis doctoral de Wan (PolyU, 2007)](https://ira.lib.polyu.edu.hk/handle/10397/84834) sustenta aportes de generación y coordinación. [Aminian et al., Journal of Cloud Computing (2024)](https://doi.org/10.1186/s13677-024-00672-2) estudia coordinación y heurísticas. [DIgSILENT oficial](https://www.digsilent.de/en/protection-functions.html) documenta capacidades, sin acreditar la licencia instalada.

## Clarificaciones de diseño

El alcance y las políticas anteriores son propuesta en borrador. No se declara
aprobada esta spec ni se cambia el estado de specs anteriores por crear el plan.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

