# Spec 053 — El catálogo de fichas crece con cada código nuevo

Estado: implementada · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01, al convertir la
copia VNR-GIS de Electro Oriente («debes usar para recalibración el catálogo y completar según
fichas técnicas; las fichas técnicas de cada equipo son universales, no tienen un nombre de la
empresa»; «las fichas técnicas son de uso universal, se usan para cualquier empresa; el flujo es
lo mismo para cualquier empresa del conversor»; «añade; cada vez debe crecer el catálogo»).

## Contexto y objetivo

El catálogo de parámetros (`input/catalogo_parametros.xlsx`, sección 7.bis del manual) da la R,
la X, la B1 y la ampacidad de cada tipo de conductor por su código de norma, con la ficha técnica
del fabricante. Las fichas son universales: el mismo código vale para cualquier distribuidora.

Hoy el catálogo se escribe de una vez a partir de los tipos que usaba la red de la que se sacó, y
un código que no está en él queda sin parámetros. Al convertir NJA202 y R205 de Electro Oriente
(2026-11-01), seis códigos no estaban (`AS03503G`, `AS05003G`, `AS07003G`, `CS03503G`,
`AA24003G`, `N230003G`) y sus tramos salían con R = X = 0: el oráculo lo detectaba y el flujo de
NJA202 solo convergía con la demanda al 11,3 %.

Esta spec hace que el catálogo crezca: cada código nuevo que aparezca en una conversión, de
cualquier fuente y empresa, se añade con los parámetros que se puedan deducir de fichas que ya
están en él o de fichas universales del propio conversor, anotados como deducidos hasta tener la
ficha del fabricante.

## Requisitos funcionales (EARS)

- RF-1: CUANDO una conversión tenga tipos de conductor cuyo código no esté en el catálogo, EL
  SISTEMA añadirá una fila por código, sin tocar ninguna de las que ya tiene.
- RF-2: SI el código es de una familia con otra sección en el catálogo, ENTONCES EL SISTEMA
  tomará la sección más cercana como referencia: la R y la R0 por la relación de secciones
  (Rref · Sref / S), la X, la X0 y la B1 de la referencia, y la ampacidad por
  Aref · (S / Sref)^0,75.
- RF-3: SI el código es de aleación de aluminio (AAAC), ENTONCES EL SISTEMA tomará la R de la
  ficha universal del AAAC que ya tiene el conversor y el resto de su familia según RF-2.
- RF-4: SI el código es de una red autoportante (norma del regulador: cables con aislamiento
  XLPE trenzados con un portante; `CS` de cobre, `AS` de aluminio), ENTONCES EL SISTEMA tomará como
  referencia el cable XLPE de cobre del catálogo, con la R y la R0 por ρAl / ρCu = 1,639
  (IEC 60228) si es de aluminio y la ampacidad por √(ρCu / ρAl).
- RF-5: SI no se puede deducir, ENTONCES EL SISTEMA añadirá la fila sin valores, pendiente de
  ficha, y lo dirá: nunca un tramo con impedancia cero sin aviso.
- RF-6: Cada fila añadida dirá su estado («por_confirmar» o «derivado»), la referencia, la regla
  y la fuente de donde se dedujo, y la fecha y la fuente de datos en que apareció; con la ficha
  del fabricante se cambia a «ficha».
- RF-7: EL SISTEMA escribirá el catálogo de forma que nunca quede a medias (fichero temporal y
  reemplazo) y lo usará en la misma conversión.
- RF-8: EL SISTEMA no tendrá un catálogo por empresa: es uno y universal; el perfil de empresa no
  interviene.

## Relación con otras specs

- Amplía el catálogo de la sección 7.bis (spec 009) y su uso en la fuente VNR-GIS (023:RF-10).
- La recalibración (specs 006, 025, 035) usa las fichas del catálogo.

## Fuera de alcance

- Leer fichas en PDF: las escribe el ingeniero en el catálogo.

## Criterios de finalización

- `grep -rnoE "053:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-8.
- NJA202 y R205 de Electro Oriente reconvertidos sin ningún tramo de impedancia nula.
