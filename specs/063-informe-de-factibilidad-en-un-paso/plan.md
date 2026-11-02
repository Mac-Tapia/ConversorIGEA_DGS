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
COPARA. La salida de la central térmica queda en el escenario propio de operación. La
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
