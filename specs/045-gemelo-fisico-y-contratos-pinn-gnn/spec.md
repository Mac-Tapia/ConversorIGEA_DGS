# Spec 045 — Gemelo físico y contratos PINN/GNN

Estado: aprobada (2026-11-22: T3 cerrada con la ablación real en CUDA; RF-15 a RF-18 nuevos de MEJ30 con la T6 [GPU] abierta) · cumplida el 2026-11-21 · Fecha: 2026-10-31

## Contexto y objetivo

El PINN existente tiene balance AC, base física y magnitud de fuente impuesta, pero su contrato no cubre todos los controles ni el cuarto caso de la web. La publicación general exige explicitar dominio, restricciones, entrenamiento y contraste.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 043 y 044; preservar reglas y casos de 025, 032 y 037–042.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se capture un episodio nuevo, EL SISTEMA distinguirá los cuatro roles de caso con su identidad nativa.
- RF-2: CUANDO se lea un episodio histórico, EL SISTEMA preservará su contenido y huella originales.
- RF-3: CUANDO se construya el grafo, EL SISTEMA registrará equipos, unidades, controles efectivos y alcance físico representado.
- RF-4: SI un equipo o condición no está soportado por la física, ENTONCES EL SISTEMA rechazará su uso predictivo con un motivo trazable.
- RF-5: EL SISTEMA fijará la referencia de magnitud y ángulo correspondiente a cada componente energizada del modelo.
- RF-6: CUANDO se calcule la pérdida, EL SISTEMA conservará por separado error de datos, residuo físico y error de fronteras.
- RF-7: CUANDO se compruebe el residuo diferenciable, EL SISTEMA contrastará sus gradientes con diferencias finitas en una red pequeña.
- RF-8: CUANDO se evalúe una arquitectura, EL SISTEMA comparará física pura, red sin término físico e híbrido sobre las mismas particiones.
- RF-9: SI una predicción queda fuera del dominio validado, ENTONCES EL SISTEMA impedirá su uso como diseño aceptado.
- RF-10: CUANDO se capture la red real, EL SISTEMA conservará la central y los bancos existentes con sus estados medidos.
- RF-11: CUANDO se acepte un modelo para un alcance, EL SISTEMA aportará contraste nativo de ese mismo alcance.
- RF-12: CUANDO se pida aprender con flujo equilibrado, EL SISTEMA calculará los escenarios de la copia con flujo equilibrado, aunque la red tenga ramales monofásicos, para que esos episodios enseñen a la PINN; el proyecto del operador no cambia.
- RF-13: DONDE el perfil declare un proyecto como red de prueba (`gemelo.proyectos_de_prueba`), EL SISTEMA dejará esa red entera en la prueba y fuera del entrenamiento, en lugar del reparto por huella; si no está entre las muestras, seguirá el reparto por huella.
- RF-14: SI el flujo mallado de la física base no converge, ENTONCES EL SISTEMA intentará Newton-Raphson y, si tampoco,
  usará el barrido radial y lo dirá; nunca dará 0 p.u. como física base. Ciclo del 2026-11-08: la red 9f53b98… del búfer (dos
  fuentes, 0,54 p.u. en DIgSILENT) no convergía, la base salía a 0 p.u. y la PINN, que aprendía de ceros, quedó a 0,354 p.u.
- RF-15: CUANDO se entrene un miembro del híbrido, EL SISTEMA empezará con la corrección nula (la física exacta), la
  contará como la época que hay que mejorar en validación y solo elegirá una época con menor error de tensión cuyo residuo
  físico medio no pase del tope de la puerta de 044; si ninguna lo hace, el miembro quedará en la física. Ablación del
  2026-11-21 en GPU (`045_T3/ablaciones.json`): la física pasaba las puertas en global y en las 5 familias y el híbrido no
  (5,25·10⁻⁴ p.u. frente a 2,07·10⁻⁴, residuo 0,073 sobre 0,05 en 4 familias), con la mejor época de validación en la 0.
- RF-16: CUANDO el híbrido prediga, EL SISTEMA aplicará la mayor fracción de la corrección (1, ½, ¼, ⅛, 1/16 o 0) cuyo
  residuo físico medio no pase del tope o, si la física ya lo pasa, del de la física, y dirá la fracción usada; fuera de
  su dominio devolverá la física (y la marca), y la incertidumbre del aprendizaje activo seguirá creciendo con lo que la
  guarda recorta y con la fracción de nodos fuera de lo aprendido. T6 del 2026-11-21: la red de prueba, de 30 nodos,
  estaba fuera del dominio de los cinco candidatos (169–5 147 nodos aprendidos) y se medía una corrección que nadie
  usaría; y al multiplicar la dispersión por la fracción usada, f(30) = 1,0 quedaba por debajo de f(1) = 1,00000002.
- RF-17: SI un candidato no se promueve y el modelo en uso, en las redes de prueba de su dominio, no mejora al flujo
  físico o deja el residuo sobre el tope, ENTONCES EL SISTEMA, en el ciclo continuo, lo retirará con su motivo en el
  historial y decidirá la física; y la ablación dirá qué brazo quedaría en uso con la misma regla.
- RF-18: DONDE el contrato de una ablación declare `politica.redes_de_prueba` (prefijos de la huella de red), EL SISTEMA
  dejará esas redes enteras en la prueba y fuera del ajuste, la validación y la calibración, sin tocar el perfil de la
  empresa, y rechazará con su motivo una declaración que no sea de ninguna red, sea de varias o deje todas a prueba. T6 del
  2026-11-21: la red de prueba del perfil (30 nodos) estaba fuera del dominio de todos los candidatos (169–5 147 nodos).

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- Episodio v1 reescrito por migración: T1, test_v1_lectura_no_cambia_hash.
- Cargas nuevas confundido con obras aceptadas: T1, test_cargas_nuevas_es_diagnostico.
- Frontera angular flotante o isla desenergizada: T2, test_referencia_por_componente.
- Toma/shunt/adaptación automática no representados: T2, test_fisica_incompleta_bloquea.
- Red nueva con intervalo estrecho: T3, test_fuera_dominio_no_se_acepta.

## Fuera de alcance

PINN dinámico RMS/EMT; aprendizaje de una PDE espacial inexistente en el flujo algebraico; sustituir el motor nativo; modificar planos de la distribuidora; dar por soportada red desequilibrada sin representación por fase.

## Criterios de finalización

Cada RF tiene una prueba con cita `045:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

[PowerFlowNet, IJEPES (2024)](https://doi.org/10.1016/j.ijepes.2024.110112) fundamenta el candidato GNN. Raissi et al., JCP (2019), DOI 10.1016/j.jcp.2018.10.045, fundamenta incorporar restricciones; aplicar aquí balance algebraico, sin inventar una PDE.

RF-15 a RF-17 (MEJ30, 2026-11-21): la corrección parte de cero como la rama residual de ReZero (Bachlechner et al., UAI
2021, PMLR 161, [arXiv:2003.04887](https://arxiv.org/abs/2003.04887)) y aprende solo lo que la física no explica, como el
aprendizaje residual guiado por la física del flujo probabilístico ([arXiv:2301.12062](https://arxiv.org/abs/2301.12062));
la búsqueda lineal sobre el desbalance al inferir es la de PIGNN-Attn-LS (Kim et al., 2025,
[arXiv:2509.22458](https://arxiv.org/abs/2509.22458)), que observa que el término físico blando no obliga en la predicción;
Donon et al. (EPSR 2020, [HAL 02372741](https://hal.archives-ouvertes.fr/hal-02372741)) entrenan el resolvedor con la
violación de Kirchhoff; y Wang, Teng y Perdikaris ([arXiv:2001.04536](https://arxiv.org/abs/2001.04536)) explican por qué
un peso fijo de 10⁻⁴ deja el término físico sin gradiente frente al de datos. El peso no se cambia sin medirlo en GPU (T6).

## Clarificaciones de diseño

El usuario autorizó implementar este alcance. El estado aprobada indica que quedan
tareas abiertas; crear el plan no cambia el estado de specs anteriores.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

