# Spec 039 — Fijas del máximo del mes o coincidentes con la cabecera, elegidas y comparadas en la web

Estado: implementada · Fecha: 2026-10-31 · Origen: petición del usuario, 2026-10-31, tras auditar a
mano NA203 («implementa que exista opción para hacer análisis y estudios desde la web estas dos
opciones … los valores máximos de fijos del mes y coincidente en la misma fecha»)

## Contexto y objetivo

En la recalibración de NA203 (2026-10-31) la Q de cabecera no cuadraba. La auditoría a mano dio:
las 15 fijas suman 7 707,5 kW y 3 725,5 kvar, cada una la POT máxima de su hoja de 15 minutos (EA ×
4) con el ERI × 4 de ese registro y ERC = 0; el registro de cabecera del 03/10 11:00 (9 889 kW,
1 711 kvar) es coherente con su kVA; y en un mismo instante (26/09/2026 11:00) las fijas suman
6 681 kW y 3 061 kvar frente a 9 669 kW y 1 717 kvar en toda la cabecera. Cada criterio cambia lo que
pesan las fijas, y el operador quiere elegirlo y compararlo desde la web.

Amplía 035:RF-1, RF-17 y 022:RF-84: hoy el plan toma el registro del instante de la máxima si el
libro de clientes lo tiene y, si no, la POT del mes, sin que el operador lo elija ni lo vea.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA dejará elegir en la tabla cruzada de la web, al cruzar los clientes, el
  criterio de todas las fijas, «máximo del mes» o «coincidente con la cabecera», y el mismo
  criterio pasará al plan de la calibración y de la recalibración.
- Aclaración de RF-1 (usuario, 2026-10-31): por defecto, «coincidente con la cabecera».
- RF-2: CON «máximo del mes», EL SISTEMA dará a cada fija la POT máxima de su hoja de 15 minutos
  (EA × 4) y la Q del ERI × 4 de ese mismo registro.
- RF-3: CON «coincidente con la cabecera», EL SISTEMA dará a cada fija la EA × 4 y el ERI × 4 de
  su registro en el instante de la máxima de cabecera del alimentador.
- RF-4: SI el libro de clientes no tiene ese instante, ENTONCES EL SISTEMA no tomará otro para esa
  fija: lo dirá, con el periodo que daría la misma fecha, y no aplicará la calibración hasta que el
  operador elija otro periodo o el «máximo del mes».
- RF-5: EL SISTEMA ofrecerá en la web «Comparar los criterios de las fijas», como trabajo que no
  abre DIgSILENT: por fija, los dos valores de P y Q con su registro; sus sumas; la cabecera medida
  en el instante de la máxima; y la Q de la red y de los bancos de la última simulación en
  DIgSILENT, con la Q que quedaría para las escaladas con cada criterio.
- RF-6: EL SISTEMA dirá en el informe de la calibración el criterio de las fijas que usó.
- RF-7: EL SISTEMA tendrá en la tabla cruzada un desplegable con los alimentadores de la máxima buscada, para marcar
  cuáles toman sus fijas con «máximo del mes»; los no marcados toman el criterio general del selector. Usuario,
  2026-11-05, Pisco: «¿podría hacerse un desplegable para seleccionar qué alimentadores se van a considerar en las
  máximas del mes en la tabla cruzada?», con el criterio por alimentador y todos calibrados juntos.
- RF-8: EL SISTEMA llevará el criterio de cada alimentador a la tabla, al plan de la calibración y de la recalibración,
  y al informe (RF-6), y dirá en la tabla el criterio de cada fila.

## Relación con otras specs

- Con «coincidente», RF-4 cambia 035:RF-19 y 004:RF-67: un libro de otro mes, o una hoja sin el
  registro del instante, ya no deja tomar el de la POT sin decirlo; el plan no se prepara. Con
  «máximo del mes», 035:RF-19 sigue igual: no bloquea.
- Un cliente sin hoja de 15 minutos va con su EA/ERI del mes con los dos criterios (004:RF-66) y
  no bloquea: ningún criterio le daría otro valor.

## Fuera de alcance

- Cambiar los valores de las hojas o de la red: la comparación solo lee.
- Alimentadores con central (021): su cabecera es por zonas; se comparan sus fijas, no la cabecera.

## Criterios de finalización

- `grep -rnoE "039:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-6.
- NA203 desde la web: «máximo del mes» da 7 707,5 kW y 3 725,5 kvar; «coincidente» con el periodo
  2026-09 da el registro de cada fija en el instante de su máxima de cabecera.
