# Plan — Spec 007

## Resumen

La base es la variación que dejó el ajuste (spec 006), junto con la variación de las
demandas si el envío trae demandas: es el estado **sin proyecto**. El guion de cargas
deja de crear una variación para todo y pasa a crear una variación de demandas y una por
carga nueva. Cada carga se conecta con solo la base y su variación activas, se mide
(con proyecto) y se desactiva antes de la siguiente.

## Módulos

| Fichero | Cambio | RF |
| --- | --- | --- |
| `src/igea_dgs/cargas_pf.py` | `armar_plan(..., base=None)`: el plan lleva `base` (variación, alimentador, cuadró, desvío, cabecera, SED calibradas), `variacion_demandas` y, por carga, el nombre base de su variación `Carga_<SED>_<alim>_<stamp>`. Las SED calibradas que cambia el libro de demandas van en `calibradas_cambiadas`. | RF-1, RF-10, RF-19, RF-21, RF-34 |
| `src/igea_dgs/web/services.py` | `cargas_plan(..., ajuste_job=None)`: toma la base del trabajo `ajuste_aplicar` (como `ajuste_plan` toma la máxima de su trabajo) y comprueba que es del mismo proyecto; sin trabajo, sin base. | RF-1, RF-4, RF-5, RF-34 |
| `src/igea_dgs/web/app.py` | El endpoint del plan de cargas acepta `ajuste_job_id`. | RF-1 |
| `tools/cargas_pf.py` | `activar_base` (busca el `IntScheme` por nombre en la carpeta `scheme`, lo activa; RF-7 si no está), `variaciones_activas` para el informe, `resolver_nuevas(..., activo=)` para buscar solo en el alimentador activo, y un `ejecutar` por fases: demandas → flujo sin proyecto → una variación por carga → base al final. | RF-6 a RF-18, RF-24 a RF-33, RF-35 |
| `tools/ajuste_cabecera_pf.py` → `tools/cargas_pf.py` | `medir_cabecera` y `potencia` pasan a `cargas_pf.py` (el ajuste ya importa de allí) para medir la cabecera con y sin proyecto sin importar en círculo. | RF-13, RF-32, RF-33 |
| `tests/fake_pf.py` | Variaciones con `Activate`/`Deactivate` y `GetActiveNetworkVariations`; los objetos creados con una etapa grabando quedan fuera de la red cuando su variación se desactiva, para que el flujo de la carga *i* no vea la *i−1*. | apoyo RF-11, RF-12, RF-17 |
| `frontend/src/components/CargasTab.tsx`, `DemandaMedida.tsx`, `AjusteCabecera.tsx` | Orden de pasos (proyecto → alimentador → máxima y clientes → ajuste → cargas); recuadro «Base: sin proyecto» con la variación, la máxima, si cuadró y «Quitar base»; con base, el alimentador queda fijado al del ajuste. Informe por carga: variación, barra, distancia, Δ cabecera, Δ pérdidas, Δ tensión mínima, VAN. | RF-1 a RF-5, RF-18, RF-21, RF-23, RF-30, RF-33, RF-34 |
| `frontend/src/types.ts`, `api.ts` | Tipos de la base y del informe por carga; `ajuste_job_id` en el plan. | — |

## Decisiones

- **La base sale del trabajo del ajuste, no de lo que haya activo en DIgSILENT.** El
  front manda el id del último `ajuste_aplicar` terminado para el proyecto; la web lee de
  él la variación, el alimentador, `cuadrado` y `desvio`. *Descartado:* adivinar la base
  por el prefijo `Ajuste_` entre las variaciones del proyecto: con dos ajustes del mismo
  alimentador no se sabe cuál, y un ajuste hecho a mano no tendría informe.
- **Una carga, una variación, desactivada al terminar.** Por carga: `crear_variacion`
  (activa y graba), `crear_carga`, flujo, `ComTececo` si se pide, datos económicos en su
  etapa, `Deactivate()` de su variación. Así RF-12 y RF-17 se cumplen sin un paso aparte.
  *Descartado:* crear todas y activarlas de una en una al final: cada carga se dibuja y se
  mide con las demás ya creadas, y un fallo a mitad deja el proyecto con todas activas.
- **Alimentador activo.** Con base, el de la base: `resolver_nuevas` solo mira sus
  barras (RF-24, RF-25) y una fila con otro alimentador se conecta igual y se anota
  (RF-29). Sin base se conserva la regla de la spec 004 entre los alimentadores elegidos,
  que son «los que elige el operador» (RF-5).
- **Sin proyecto se mide una vez.** Flujo con la base (y las demandas) antes de la
  primera carga; las diferencias de cada carga se restan de ese (RF-32, RF-33). Pérdidas
  = kW de la cabecera − Σ kW de las cargas del alimentador activo; tensión mínima, entre
  las barras de ese alimentador. *Descartado:* tomar la cabecera del informe del ajuste:
  las demandas del envío o un cambio a mano en DIgSILENT la habrían movido.
- **Sin carga conectada, sin variación.** `resolver_nuevas` ya decide si una carga se
  puede conectar antes de crear nada: la variación solo se crea para las resueltas
  (RF-15). Si `crear_carga` falla a mitad, la variación se borra (`Delete`) y se lista.
- **Cancelar** se mira entre cargas: la en curso termina con su flujo y se desactiva
  (RF-16, RF-17).
- **Nombre de cada variación**: `Carga_<SED>_<alimentador>_<stamp>` pasado por
  `nombre_pf` y `nombre_libre` (RF-10). Las demandas, `Demandas_<alim>_<stamp>`.
- **Escala.** Una variación y uno o dos flujos por carga: el tiempo crece con el número de
  cargas, no con el tamaño de la red; las barras del alimentador activo se leen una vez.

## Riesgos para la prueba real (T10)

- Los gráficos de una carga van al diagrama, no a su variación: con la variación inactiva
  PF los pinta en amarillo. Es lo esperado; comprobar que no se pintan «sin red».
- `IntScheme.Deactivate()` con su etapa grabando: comprobar que PF no pregunta.
- La variación del ajuste y las de las cargas comparten la hora del caso: comprobar que
  el orden de las etapas no cambia el resultado (sus objetos no se cruzan).

## Pruebas

- `tests/test_cargas_pf.py`: plan con base, nombres de variación por carga, SED
  calibradas que el libro cambia. Sintéticas, sin datos reales.
- `tests/test_cargas_pf_guion.py` con el doble ampliado: una variación por carga; la
  carga *i* no ve la *i−1*; base que no existe; base que no cuadró; solo el alimentador
  activo; fila con otro alimentador; sin proyecto medido una vez y Δ por carga;
  cancelación; al terminar solo la base activa; `ComTececo` por carga.
  Número de cargas sorteado, no fijo.
- `tests/test_cargas_pf_web.py`: `ajuste_job_id` de otro proyecto o de una simulación se
  rechaza; sin él, sin base.
- `tests/test_cargas_pf_front.py`, `npx tsc --noEmit -p .` y `npm run build`.
- Las pruebas de la spec 004 que fijaban «una variación para todo» se actualizan y citan
  `007:RF-9`; las demás deben seguir en verde sin tocarlas.

## Al implementar (2026-10-10)

- La base sale de `services.base_del_ajuste(result, project)`: el endpoint del plan de
  cargas recibe `ajuste_job_id`, comprueba que es un `ajuste_aplicar` del espacio y pasa
  su `result`. Con la spec 008 un ajuste trae un informe por alimentador: cada uno aporta
  su variación y los que fallaron quedan en `excluidos` (RF-37).
- Varios alimentadores marcados (RF-36): `resolver_nuevas` busca en el de la columna si
  está marcado y, si no, en todos los marcados; la nota de RF-29 lo dice.
- Las pruebas del guion de esta spec están en `tests/test_cargas_pf_guion_007.py`; las
  de la 004 que fijaban una variación para todo citan ahora `007:RF-9` y `007:RF-19`.
- `informe['flujo']` es el flujo final, con la base y las demandas: el estado sin
  proyecto tras desactivar todas las cargas.
