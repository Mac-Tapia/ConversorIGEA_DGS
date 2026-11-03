# Spec 044 — Evaluación causal y verificación completa

Estado: implementada · Fecha: 2026-10-31

## Contexto y objetivo

La validación del PINN se reutiliza para calibración y el auxiliar top-k trata algunas métricas ausentes como diferencias cero. Ambas decisiones impiden sostener una validación independiente completa.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 043; solo T0 puede adelantarse porque corrige el auxiliar existente sin contratos nuevos.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se evalúe un modelo, EL SISTEMA separará entrenamiento, selección, calibración y prueba mediante grupos de custodia sin solapamiento.
- Aclaración de RF-1: los grupos de custodia de un episodio son su red y su familia topológica. Con un sistema entero (027:RF-68) el reparto se hace por la huella de la familia, no por la de cada episodio: por episodio, las variantes de demanda de una maniobra caían a los dos lados y 060:RF-2 lo rechazaba siempre. Las cuotas 30/10/10 de ese modo son de grupos.
- RF-2: SI falta una partición o su mínimo predeclarado, ENTONCES EL SISTEMA bloqueará la promoción sin sustituirla por datos de entrenamiento.
- RF-3: EL SISTEMA ajustará transformaciones e hiperparámetros sin utilizar la partición de prueba sellada.
- RF-4: CUANDO se calibre incertidumbre, EL SISTEMA utilizará únicamente la partición de calibración no usada para selección.
- RF-5: CUANDO se compare un candidato, EL SISTEMA aplicará puertas predeclaradas por familia además de los resultados agregados.
- Aclaración de RF-5: en la PINN, cada familia de la prueba pasa los topes 0,005 p.u. y 0,05 y no puede superar 1,05 veces el error del flujo físico ni el del modelo en uso. La comparación global con el flujo físico sigue siendo estricta (071:RF-3).
- RF-6: SI faltan métricas nativas obligatorias o contienen valores no finitos, ENTONCES EL SISTEMA rechazará la verificación de la alternativa.
- RF-7: CUANDO se acepte una alternativa, EL SISTEMA exigirá la evaluación nativa completa del caso y de su referencia vinculada.
- RF-8: CUANDO se publique una evaluación, EL SISTEMA conservará denominadores, unidades, particiones y política suficientes para reproducirla.
- Aclaración de RF-8: la cobertura de un intervalo solo se afirma si las familias de calibración alcanzan para ella (⌈(g+1)·cobertura⌉ ≤ g, nueve para un 90 %); con menos, se publica la empírica con sus denominadores y la cobertura queda vacía. Nunca se promete garantía de datos intercambiables.
- RF-9: CUANDO se confirme un diseño en PowerFactory, EL SISTEMA verificará su persistencia después de reabrirlo.

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- Copias de un episodio en splits distintos: T1, test_cuatro_particiones_sin_solape.
- Calibración vacía o umbral elegido tras ver prueba: T1–T2, test_sin_calibracion_bloquea.
- Familia pequeña que empeora con mejor media global: T2, test_regresion_familia_rechaza.
- NaN/None o pérdidas cero: T3, test_top_k_sin_metricas_rechaza y test_perdida_cero_no_oculta_error.
- Medición de otro año o caso: T3–T4, test_top_k_contexto_distinto_rechaza.

## Fuera de alcance

No cambiar límites normativos para aprobar candidatos; no prometer cobertura fuera del dominio o bajo dependencia temporal no evaluada.

## Criterios de finalización

Cada RF tiene una prueba con cita `044:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

La calibración independiente es una condición del protocolo propuesto; las tesis y PowerFlowNet justifican contraste fuera de entrenamiento, no una cobertura garantizada con datos correlacionados.

## Clarificaciones de diseño

El alcance y las políticas anteriores son propuesta en borrador. No se declara
aprobada esta spec ni se cambia el estado de specs anteriores por crear el plan.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

