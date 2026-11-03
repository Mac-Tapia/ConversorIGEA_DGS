# Spec 046 — Pronóstico causal multihorizonte

Estado: cumplida · Fecha: 2026-10-31

## Contexto y objetivo

La GRU actual dispone de validación cronológica, pero su escala interna usa toda la serie recibida antes del corte. No hay un contrato multivariante/multihorizonte equivalente para comparar Transformers con trazabilidad.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD. Objetivos: la demanda de cabecera por alimentador y la de cada cliente fijo, en kW y kVAR, cada 15 minutos donde el dato lo sea (orden del usuario del 2026-11-02). El número de alimentadores y de clientes es variable.
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
- RF-9: CUANDO el operador pida el pronóstico de cabecera, EL SISTEMA tomará como objetivos el kW y el kVAR de cada alimentador pedido con los lectores de `demanda_medida.py`.
- RF-10: DONDE el operador declare los medidores de una central de un alimentador, EL SISTEMA pronosticará la demanda con la central descontada por `curva_de_demanda`.
- RF-11: CUANDO el operador pida el pronóstico de clientes fijos, EL SISTEMA tomará como objetivos el kW y el kVAR de cada cliente pedido desde su hoja de 15 minutos del libro de clientes libres.
- RF-12: SI un objetivo no cumple la cadencia declarada, ENTONCES EL SISTEMA lo apartará nombrando el objetivo y el motivo, sin rellenar valores.
- RF-13: EL SISTEMA hará competir, en las mismas ventanas de cada objetivo, al ingenuo, al estacional semanal, a la GRU y a los adaptadores N-HiTS, TFT y PatchTST.
- RF-14: SI un adaptador no carga, ENTONCES EL SISTEMA lo declarará no disponible con su motivo y seguirá con los demás modelos.
- RF-15: SI no hay GPU CUDA, ENTONCES EL SISTEMA dará un error que lo diga para cada modelo neuronal, sin entrenarlo en la CPU.
- RF-16: EL SISTEMA elegirá un ganador por objetivo, y decidirá por separado la clase cabecera y la clase cliente.
- RF-17: SI ningún modelo neuronal de un objetivo supera las puertas, ENTONCES EL SISTEMA declarará ganadora a su referencia y lo dirá en el resultado.
- RF-18: EL SISTEMA incluirá en las puertas el error en la máxima y el error en el instante de la máxima, frente a la referencia de cada objetivo.
- RF-19: CUANDO emita un pronóstico, EL SISTEMA escribirá un artefacto con fuente, emisión, horizonte, cuantiles, modelo y la marca `pronostico` en cada fila.
- RF-20: EL SISTEMA no usará un pronóstico como medición en la calibración, en el «Caso base» ni en los informes.
- RF-21: EL SISTEMA no escribirá un pronóstico en DIgSILENT.
- RF-22: EL SISTEMA conservará `crecimiento.py` como la tasa del PIDE, sin leer de él ningún pronóstico.
- RF-23: EL SISTEMA emitirá un pronóstico solo por una petición expresa desde la web o desde el asistente.
- RF-24: CUANDO la web o el asistente pidan un pronóstico, EL SISTEMA lo ejecutará como trabajo cancelable en otro proceso.
- RF-25: CUANDO se reproduzca el mes con `gemelo_temporal`, EL SISTEMA dirá en el resultado que es una reconstrucción a un paso y no un pronóstico.
- Aclaración de RF-8: las puertas son las de «Puertas predeclaradas»; no se cambian después de medir, y un cambio de valores abre otra versión de la política con su huella.
- Aclaración de RF-5: las ventanas de un objetivo se fijan por su emisión, con todo el contexto común y todos los objetivos futuros observados, antes de ajustar ningún modelo.

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Puertas predeclaradas

Fijadas el 2026-11-02, antes de la primera medición real; `POLITICA_TEMPORAL` de
`digital_twin/evaluacion_temporal.py` las lleva con su huella y una prueba comprueba que esta tabla
dice lo mismo. La referencia es, por objetivo y horizonte, la mejor de ingenuo y estacional semanal
en la partición de selección, nunca en la de prueba.

Particiones cronológicas por día local completo:

| Partición | Fracción de los días | Mínimo de días |
| --- | --- | --- |
| entrenamiento | 0.60 | 30 |
| seleccion | 0.15 | 7 |
| calibracion | 0.10 | 7 |
| prueba | 0.15 | 14 |

Cada objetivo y horizonte debe pasar todas (una media buena no compensa a otro horizonte):

| Puerta | Mínimo | Qué mide en la partición de prueba |
| --- | --- | --- |
| habilidad_pinball | 0.02 | 1 − pinball del modelo / pinball de la referencia |
| habilidad_mae | 0.00 | 1 − MAE del modelo / MAE de la referencia |
| maxima_no_peor | 1.00 | 1 si el IC 90 % por días de la mejora en el error de la máxima no queda entero por debajo de cero |
| instante_no_peor | 1.00 | 1 si el IC 90 % por días de la mejora en el error del instante de la máxima no queda entero por debajo de cero |
| cobertura_en_banda | 1.00 | 1 si la cobertura empírica q05–q95 está entre 0.85 y 0.95 |
| mejora_significativa | 1.00 | 1 si el IC 90 % por días (bootstrap de días) de la mejora en pinball excluye el cero |

Además: reapertura en otro proceso con la misma predicción, y frente a un modelo activo, una mejora
de pinball del 1 % en las mismas ventanas. Un empate no promueve. Los intervalos se calibran por
objetivo y horizonte en la partición de calibración, que no se usa para ajustar ni para evaluar.

La máxima prevista es la máxima de q50 en el primer día de la trayectoria más el sesgo mediano que
ese modelo mostró en la partición de calibración, igual para todos. Sin esa corrección, una mediana
lisa siempre se queda por debajo de un pico con ruido y la puerta favorecería a copiar la semana
anterior: se vio en la prueba de contrato del perfil medio, antes de medir datos reales. Las puertas de
máxima y de instante exigen no ser peor de forma significativa, y no una mejora puntual: con solo los
días de una partición hay un pico por día, y en sorteos de contrato el mismo perfil, siempre mejor en
pinball, variaba su error de máxima frente a la referencia entre −16 % y +48 %. Ninguna puerta se
cambió después de ver datos reales.

## Casos límite

- Pico posterior cambia la escala pasada: T1, test_escala_usa_solo_entrenamiento.
- Hueco de medición contado como 0: T1, test_hueco_no_es_cero.
- Clima futuro medido filtrado como conocido: T1, test_covariable_sin_asof_se_excluye.
- Horizonte 96 con cadencia horaria: T2, test_horizonte_exige_cadencia.
- Intervalos q10/q90 etiquetados 90%: T3, test_cuantiles_y_cobertura_coherentes.
- Medidor sin señal (todo ceros): T4, test_objetivo_sin_senal_se_aparta.
- Cliente repartido en libros mensuales con un registro contradictorio: T4, test_cliente_con_meses_contradictorios_se_aparta.
- El ingenuo o el estacional ganan: T5, test_si_gana_la_referencia_se_dice.
- Un adaptador que no carga: T2, test_adaptador_opcional_no_rompe_gru.

## Fuera de alcance

Proyección a años con variables exógenas (spec 031, reservada); clima u otras covariables sin dato real con su fecha de publicación (solo entra el calendario, conocido al emitir); sustituir 029 por una red sin comparación; escribir pronósticos en DIgSILENT; inferir dinámica electromecánica desde series de 15 minutos; introducir TimeXer sin licencia verificada.

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

