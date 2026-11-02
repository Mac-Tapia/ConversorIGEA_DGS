# Plan — Spec 063

## 1. Un solo trabajo de DIgSILENT (RF-1, RF-2, RF-12)

`web/services.informe_factibilidad` pasa a hacer, en este orden y en el mismo trabajo:

1. La base de la calibración con `ajuste_aplicado_en_disco(ws, project)`, la misma de 4.2.
2. El plan de estudios con `estudios_plan(…, estudios=['flujo', 'flujo_desequilibrado'],
   feeders=[alimentador])` y `estudios_ejecutar`. Reutiliza 4.2 entero: casos, flujos, CSV y
   el JSON de cada caso. No hay un segundo camino hacia DIgSILENT.
3. El informe con lo que acaba de guardar ese estudio (`_ultimo_estudio`), como hoy.

`web/app.py`: el endpoint `/informes/factibilidad` pasa al carril `powerfactory` (hoy `engine`).
El botón de 4.4 es el mismo; el aviso «Ejecute antes el estudio de flujo… en 4.2» se retira.

Descartado: un botón «Preparar y generar» aparte. Duplicaría el de 4.4, como dijo el usuario.

## 2. Casos desde la recalibración (RF-3, RF-4, RF-5)

- `tools/casos_pf.preparar_con` ya renueva «Con proyecto» sin obras desde «Sin proyecto»
  (037:RF-8), y «Cargas nuevas» es copia de «Sin proyecto» con su escenario renovado
  (025:RF-62). Las dos se copian con las cargas nuevas desactivadas y las activan después
  (`_dejar_activas`, `cargas_nuevas`). RF-4 se cumple con eso; aquí se prueba.
- RF-5: `estudios_pf` llama a `cargas_pf.etapas_al_dia(app)` al activar cada caso, antes del
  flujo, y añade la lista de variaciones adelantadas a los avisos del informe.
- La hora de estudio que movía `_optimizador` ya se restituye (011:RF-26, 2026-11-01).

## 3. Tres casos en el informe (RF-6 a RF-11, RF-13)

- `informes.py`: `Caso.desde_medida` ya existe para «Sin» y «Con»; se añade el de
  «Cargas nuevas» (`_ultimo_estudio(ws, 'cargas', project)`).
- La conclusión deja de depender solo de «Con proyecto». Pasa por una función pura,
  `conclusion_factibilidad(actual, cargas, con, obras)`, que devuelve `factible`, `motivo`
  y `elementos`, con las reglas de RF-8 a RF-11.
- `informe_docx.escribir_informe_factibilidad`:
  - Sección del estado actual («Sin proyecto»), del estado proyectado sin obras («Cargas
    nuevas») y de «Con proyecto» si tiene obras.
  - Si no hay problemas, la frase de RF-8. Si los hay, la lista de RF-9 y RF-10.
- RF-13: los límites salen ya de `ConfigInforme` con su origen; el informe dice «por defecto»
  cuando no hay perfil.

## 4. Campos de los PDF (RF-14 a RF-20)

- `web/services.informe_documentos` ya da `propuesta` y `datos` por documento. Se añade:
  - una prioridad de `expediente` (EXP-… sobre el código de la ficha), con `codigo_ficha`
    aparte (RF-15);
  - `fecha` con su documento de origen (RF-20);
  - la lista `alimentadores_leidos` (RF-19).
- `frontend/src/components/InformesPF.tsx`:
  - nuevos campos en `SOLICITUD`: `potencia_actual_kw` y `nis`; el incremento se calcula y se
    muestra (RF-14, RF-18);
  - `leidoDelSolicitante` rellena `codigo` con la estructura (RF-16), y `pcc_mva`, `utm_x` y
    `utm_y` en un bloque «Punto de diseño (ficha)» (RF-17);
  - aviso si el alimentador leído no es el de la carga (RF-19).
- El cuerpo de `InformeFactibilidadIn` gana `potencia_actual_kw`, `nis`, `pcc_mva`, `utm_x`
  y `utm_y` (opcionales), que llegan al informe.

## Pruebas

La continuación de RF-36 a RF-38 añade una operación de SET existente en el carril nativo:
`/pf/obras/set-nueva/operacion`, `services.set_nueva_operacion` y el adaptador
`tools/set_nueva_operacion_pf.py`. El diagnóstico lee cubículos, conexiones y parámetros
por ruta completa dentro del proyecto vinculado. Evaluar copia el escenario y graba cada
refuerzo estructural en una variación propia; no aparta cargas que crean tramos partidos.
Los cambios admitidos se restringen a capacidades, referencias de tipos existentes y
operación; no se permite bajar plini, qlini o scale0. Se conserva posición y potencia de
COPARA. Las maniobras y la salida de la central térmica quedan registradas en sus
propias etapas, con el escenario propio de operación coherente con ellas. La
aplicación debe revertir nuevas variaciones si falta cobertura, demanda o aceptación, y
releer tras reabrir para acreditar persistencia. El caso original conserva su escenario.

La evaluación guarda además `red_proyecto` y `geo_proyecto` en los flujos: las ramas que pasan
a una SET nueva dejan de pertenecer al ElmFeeder original, pero siguen dentro del proyecto
evaluado. Se conserva el resumen por medidor y se añade el completo, con fuentes, generación,
consumos efectivos y tensiones por nivel; una cobertura o balance incompletos no se aceptan.
`tools/informe_casos_guardados.py` reproduce el Word con esos informes ya guardados por la web,
sin una ejecución nativa alternativa. El generador existente incorpora el caso sin obras,
potencia previa, NIS, datos de ficha y un dictamen coherente con los tres casos; los balances
instantáneos se pueden informar sin inventar una anualización ni un precio de energía.

- `tests/test_informe_factibilidad_un_paso.py` (nueva), con el doble `fake_pf`:
  - alimentadores sorteados (`CSG_SCALE_SEED`), de tamaño y número variables;
  - el trabajo prepara los casos, corre los flujos de los tres casos y escribe el informe;
  - sin perfil, límites por defecto declarados;
  - ningún alimentador fijo.
- `conclusion_factibilidad`, pura: las cuatro ramas de RF-8 a RF-11, con medidas sorteadas.
- Documentos (RF-15, RF-20): textos de carta, ficha y respuesta sintéticos (sin datos de la
  distribuidora), con EXP y código de ficha, y con tres fechas.
- Front: `tsc` y `npm run build`; la web probada en el navegador real con un proyecto
  importado (constitución, «web probada de verdad»).
- [DIgSILENT]: INKA en SM218 desde la web con un clic.

## Fundamento y límites de la verificación física

La continuidad se comprueba por referencias nativas de cubículos y terminales, incluyendo
líneas, transformadores, acoples y estados de interruptores; los nombres de alimentadores
no demuestran la fuente que atiende una carga. Toda transferencia debe conservar las cargas
y evitar unir redes externas independientes. El análisis del grafo propone la maniobra;
los flujos equilibrado y desequilibrado, la demanda efectiva y la relectura deciden su
aceptación. Se comprueban ambos modos en el dictamen del informe.

El enfoque se apoya en estas fuentes primarias consultadas en la web:

- Duchesne, M. (2025). *Unbalanced Low Voltage Distribution Network Reinforcement*.
  Tesis de maestría, Université de Liège.
  <https://matheo.uliege.be/handle/2268.2/23284>: fundamento para estudiar el desequilibrio
  y los refuerzos de la red.
- Li, J. (2025). *Flexibility Integration and Pricing Strategy for Distribution Networks
  to Unlock Spare Capacity*. Tesis doctoral (EngD), University of Bath.
  <https://researchportal.bath.ac.uk/en/studentTheses/flexibility-integration-and-pricing-strategy-for-distribution-net/>:
  evaluación de capacidad disponible y planificación de la distribución.
- Georgilakis, P. S., y Hatziargyriou, N. D. (2015). *A review of power distribution
  planning in the modern power systems era: Models, methods and future research*.
  Electric Power Systems Research, 121, 89–100.
  <https://doi.org/10.1016/j.epsr.2014.12.010>: artículo de revista científica indexada
  sobre modelos y métodos de planificación de redes.

Estas referencias justifican el método; no certifican este modelo ni prescriben sus
ternas, ubicación, potencia, precios o límites. La ubicación y los 2×40 MVA de COPARA
son condiciones del usuario. Los límites proceden del perfil seleccionado y se registran
en cada evaluación. Una alternativa que cumple los límites no prueba por sí sola un
óptimo global económico o eléctrico. Al aplicar se capturan también los dos flujos
de Sin proyecto y de Cargas nuevas con las demandas sincronizadas, sin reconstruir
los casos ni sustituir el escenario de operación por una recalibración anterior.

Cuando la suma de entradas por fase de una carga histórica difiere de sus totales de
calibración, `conciliar_fases=true` corrige esa incoherencia en la copia del escenario:
conserva `plini`, `qlini`, `scale0`, modo, estado y proporciones relativas por fase. La
firma de demanda se fija después de registrar y verificar esa conciliación. La misma
demanda se copia a Cargas nuevas; los escenarios originales se conservan. La corrección
no autoriza reducir demanda nominal para conseguir convergencia.

`salidas` permite repartir la carga desde la SET existente hacia terminales existentes
mediante líneas, cubículos y alimentadores propios. Cada ruta se aporta explícitamente,
con su procedencia; el adaptador no consulta mapas. El enrutador habilitado por el perfil
puede preparar las polilíneas por vías antes de la ejecución nativa. Cortes y salidas se
validan antes de escribir y se releen después; se conservan ubicación y potencia de SET.

La toma fija `nntap` se admite únicamente en un transformador con cambiador real, paso
positivo y posición dentro de los límites nativos del tipo. No se combina con sustitución
del tipo en la misma obra. Se registra en una variación propia y en la copia del escenario;
se comprueba la posición efectiva después del flujo y de reabrir. La aplicación conserva
la fecha del candidato y verifica nuevamente el modelo después de la restitución final:
activar una etapa antigua puede cambiar la fecha del caso y dejar sin efecto obras nuevas.

La continuación del 2026-11-02 distingue el diagnóstico de la referencia sin obras y la
aceptación final solicitada por el usuario. Si la primera no tiene solución de flujo, el
informe conserva ese resultado y un esquema de sus conexiones y demandas nominales,
identificado expresamente sin resultados eléctricos. Únicamente la operación nativa final
aceptada, persistida, conforme en ambos modos y verificada después de la restitución permite
un dictamen condicionado a esas obras. No se alteran las reglas bloqueantes de otros informes
sin esa evidencia. Se evita representar ausencia de resultados como cero violaciones o
comparar pérdidas inexistentes.

Para la persistencia se usa además el manual primario instalado de PowerFactory 2024,
*Python Function Reference*, página impresa 529 (PDF 538): `IntScenario.Save()` devuelve
1 cuando el escenario no está modificado o no está activo. Ese retorno exige comprobar
identidad activa y datos guardados; no se interpreta automáticamente como éxito ni fallo
de persistencia. La posterior reactivación y lectura física siguen siendo obligatorias.
