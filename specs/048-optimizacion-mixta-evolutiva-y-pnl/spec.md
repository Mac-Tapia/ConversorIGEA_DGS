# Spec 048 — Optimización mixta evolutiva y PNL

Estado: implementada · Fecha: 2026-10-31

## Contexto y objetivo

Ya hay genético, NSGA-II y evolución diferencial. Se necesita un benchmark justo y una codificación que impida fracciones de bancos, topologías imposibles y cachés que mezclan casos.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 043, 044 y 045; 046 opcional para escenarios; consumir escalera/SET nueva de 042 sin duplicarla.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se formule una búsqueda, EL SISTEMA declarará dominio, unidades y restricciones de cada variable.
- RF-2: CUANDO se evalúe una solución, EL SISTEMA respetará discreción de equipos y restricciones de conectividad de su red.
- RF-3: CUANDO se comparen algoritmos, EL SISTEMA utilizará al menos veinte semillas y el mismo presupuesto predeclarado.
- RF-4: CUANDO se use un solucionador continuo, EL SISTEMA identificará el alcance local continuo de su resultado.
- RF-5: CUANDO se reutilice una evaluación, EL SISTEMA exigirá coincidencia de contexto, modelo, política y vector de decisión.
- RF-6: CUANDO se proponga un frente, EL SISTEMA informará factibilidad, objetivos, tiempo y evaluaciones bajo el mismo método comparativo.
- RF-7: CUANDO se elija una alternativa, EL SISTEMA exigirá la verificación completa definida por 044.
- RF-8: SI se cancela la búsqueda, ENTONCES EL SISTEMA conservará evidencia de lo evaluado sin publicar un óptimo aceptado.
- RF-9: CUANDO se apliquen obras elegidas, EL SISTEMA verificará su persistencia nativa sin alterar el caso de referencia.

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- Banco 1.4 o interruptor entre estados: T1, test_variables_discretas_no_fraccionan.
- Caché entre años/criterios/modelos: T1, test_cache_incluye_contexto_y_modelo.
- Optimización mejora objetivo por desconectar cargas: T1, test_isla_invalida_no_es_factible.
- Presupuesto por generaciones diferente entre algoritmos: T2, test_presupuesto_es_evaluaciones.
- Salida local sin convergencia KKT o aceptación nativa: T3–T4, test_pnl_no_declara_optimo_global.

## Fuera de alcance

Afirmar óptimo global de un MINLP con Ipopt; reemplazar automáticamente la escalera 042; obras sobre Sin proyecto; usar costes web como presupuesto empresarial aprobado.

## Criterios de finalización

Cada RF tiene una prueba con cita `048:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

[Blank y Deb, IEEE Access (2020)](https://doi.org/10.1109/ACCESS.2020.2990567) justifica pymoo y comparación multiobjetivo. [Pyomo](https://github.com/Pyomo/pyomo) e [Ipopt](https://github.com/coin-or/Ipopt) documentan el solucionador continuo, no garantizan óptimo global mixto.

## Clarificaciones de diseño

El alcance y las políticas anteriores son propuesta en borrador. No se declara
aprobada esta spec ni se cambia el estado de specs anteriores por crear el plan.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

