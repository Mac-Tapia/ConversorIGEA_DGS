# Spec 045 — Gemelo físico y contratos PINN/GNN

Estado: aprobada · Fecha: 2026-10-31

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

PINN dinámico RMS/EMT; aprendizaje de una PDE espacial inexistente en el flujo algebraico; sustituir el motor nativo; modificar planos IGEA; dar por soportada red desequilibrada sin representación por fase.

## Criterios de finalización

Cada RF tiene una prueba con cita `045:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

[PowerFlowNet, IJEPES (2024)](https://doi.org/10.1016/j.ijepes.2024.110112) fundamenta el candidato GNN. Raissi et al., JCP (2019), DOI 10.1016/j.jcp.2018.10.045, fundamenta incorporar restricciones; aplicar aquí balance algebraico, sin inventar una PDE.

## Clarificaciones de diseño

El alcance y las políticas anteriores son propuesta en borrador. No se declara
aprobada esta spec ni se cambia el estado de specs anteriores por crear el plan.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

