# Spec 046 — Pronóstico causal multihorizonte

Estado: borrador · Fecha: 2026-10-31

## Contexto y objetivo

La GRU actual dispone de validación cronológica, pero su escala interna usa toda la serie recibida antes del corte. No hay un contrato multivariante/multihorizonte equivalente para comparar Transformers con trazabilidad.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 043 y 044; lectura de medición existente y crecimiento de 029 conservados.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se ajuste una transformación temporal, EL SISTEMA utilizará únicamente observaciones anteriores al corte de entrenamiento.
- RF-2: SI una covariable no era conocida al emitir el pronóstico, ENTONCES EL SISTEMA la excluirá de las entradas disponibles.
- RF-3: CUANDO se prepare una serie, EL SISTEMA validará cadencia, zona horaria, unidades y huecos antes de crear ventanas.
- RF-4: CUANDO se pronostique, EL SISTEMA identificará objetivo, instante de emisión, horizonte y cuantiles de cada salida.
- RF-5: CUANDO se compare un modelo, EL SISTEMA utilizará las mismas ventanas posteriores para estacional, GRU y candidatos.
- RF-6: CUANDO se evalúe incertidumbre, EL SISTEMA informará cobertura empírica y pinball por horizonte sobre datos no usados para calibrar.
- RF-7: CUANDO se registre el candidato temporal, EL SISTEMA conservará su contexto, artefactos y evidencia de reapertura.
- RF-8: SI el candidato no supera las puertas predeclaradas, ENTONCES EL SISTEMA conservará el modelo activo anterior.

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- Pico posterior cambia la escala pasada: T1, test_escala_usa_solo_entrenamiento.
- Hueco de medición contado como 0: T1, test_hueco_no_es_cero.
- Clima futuro medido filtrado como conocido: T1, test_covariable_sin_asof_se_excluye.
- Horizonte 96 con cadencia horaria: T2, test_horizonte_exige_cadencia.
- Intervalos q10/q90 etiquetados 90%: T3, test_cuantiles_y_cobertura_coherentes.

## Fuera de alcance

Sustituir 029 por una red sin comparación; inferir dinámica electromecánica desde series de 15 minutos; introducir TimeXer sin licencia verificada.

## Criterios de finalización

Cada RF tiene una prueba con cita `046:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

[Lim et al., International Journal of Forecasting (2021)](https://doi.org/10.1016/j.ijforecast.2021.03.012) justifica TFT multihorizonte. [NeuralForecast oficial](https://github.com/Nixtla/neuralforecast) permite comparar varios candidatos; no prueba que mejoren estas series.

## Clarificaciones de diseño

El alcance y las políticas anteriores son propuesta en borrador. No se declara
aprobada esta spec ni se cambia el estado de specs anteriores por crear el plan.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

