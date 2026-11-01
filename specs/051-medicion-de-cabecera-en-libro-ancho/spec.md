# Spec 051 — Medición de cabecera en libro ancho: una columna por alimentador

Estado: implementada · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01, al llevar a
DIgSILENT la copia VNR-GIS de Electro Oriente («si existe medición de cabeceras, está en la misma
carpeta de donde sacaste el VNR-GIS; debes trabajarlo aparte sin mezclarlo con Electro Dunas, es
para ver que el conversor es universal y funcional»).

## Contexto y objetivo

La calibración (specs 006, 025 y 035) lee la medición de cabecera como la entrega Electro Dunas:
un libro de medidores que dice el medidor de cada alimentador, y libros con una hoja por medidor
con fecha, kW y kVAR. Electro Oriente la entrega de otra forma, en los perfiles de carga del
PIDE 2026 (`PIDEELOR/…/PROYECCION DE DEMANDA/<sede>/INFORMACION BASE/PERFILES`): un libro por
mes, una hoja por sistema y magnitud («BJSI_ACTIVA», «BJSI_REACTIVA»), la fecha y la hora en dos
columnas, cada 15 minutos, y **una columna por alimentador** con su código (`NJA202`, `JAE102`…).
Sobre algunas columnas de reactiva, una fila dice «CAPACITIVA».

Esta spec lee ese libro ancho, de cualquier empresa, y lo deja en el formato que la calibración
ya lee, sin tocar la calibración: una hoja por alimentador con fecha, kW y kVAR, y el libro de
medidores. Así la misma calibración sirve para las dos formas de entrega.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se le den uno o varios libros (o carpetas) y los códigos de los alimentadores, EL
  SISTEMA buscará en cada hoja una fila de cabecera con una columna de fecha y alguno de esos
  códigos, y leerá de cada código su serie por fecha y hora.
- RF-2: EL SISTEMA sabrá la magnitud de cada hoja por su nombre o por sus primeras filas
  («activa» o «reactiva»); una hoja sin magnitud no se lee y se dice.
- RF-3: EL SISTEMA formará el instante con la fecha y la hora aunque vengan en dos columnas, en
  cualquier orden, como texto o como fecha; la hora «24:00» es la medianoche del día siguiente.
- RF-4: CUANDO una fila sobre la cabecera diga «capacitiva» en la columna de un código, EL
  SISTEMA tomará su reactiva con signo negativo y lo anotará.
- RF-5: SI un código aparece dos veces en una hoja, EL SISTEMA tomará la primera columna y
  anotará la otra; los códigos pedidos que no aparezcan en ningún libro se dicen.
- RF-6: EL SISTEMA escribirá un libro de cabecera por año con una hoja por código (Fecha, kW,
  kVAR) y un libro de medidores con la fila «Alimentador, Medidor» de cada uno, que la calibración
  lee sin cambios.
- RF-7: EL SISTEMA no supondrá convenciones de una empresa: los códigos, el nombre de cada
  alimentador en DIgSILENT y las carpetas los da quien lo usa; nada se escribe en `referencia/`.
- RF-8: EL SISTEMA ofrecerá esta lectura como herramienta de línea de órdenes con `--help`.
- RF-9: CUANDO la medición sea una tabla de máximas mensuales (una fila por salida y una columna
  por mes, como «MAX DEMANDAS POR ALIMENTADORES IQUITOS» de Electro Oriente, en MW), EL SISTEMA
  tomará de cada código pedido la máxima de cada mes como un registro del día 1 a las 00:00 en
  kW, sin reactiva, y anotará que no trae hora ni reactiva: no se supone ningún factor de
  potencia. La unidad (MW o kW) se toma de la tabla o la da quien la usa. (Usuario, 2026-11-01:
  «en las mediciones, R205 debería estar como salida R5».)
- RF-11: CUANDO quien la usa dé el factor de potencia de un código cuya medición no trae
  reactiva, EL SISTEMA lo escribirá en la columna FP de sus registros sin reactiva, y la
  calibración sacará de él la Q (usuario, 2026-11-01: «la calibración Q de R5 debe ser la real
  que sale de un factor de potencia de 0,98»); la reactiva medida, si la hay, manda.
- RF-10: EL SISTEMA aceptará que el código de la medición y el nombre del alimentador en
  DIgSILENT sean distintos (R5 mide el R205 de la copia VNR-GIS): el libro de medidores los une.

## Relación con otras specs

- Alimenta la calibración de las specs 006, 025 y 035 con el formato que ya leen.
- Universalidad de la spec 023 y de la constitución (P13): la fuente y su medición se trabajan
  solas, sin mezclarse con las de otra empresa.

## Fuera de alcance

- Cambiar el lector de cabecera de Electro Dunas.
- Las proyecciones anuales: no son medición.

## Criterios de finalización

- `grep -rnoE "051:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-11.
- NJA202 de Electro Oriente (2024) leído de sus doce perfiles, y R205 con las máximas de R5,
  escritos y calibrados por la web, cada uno solo.
