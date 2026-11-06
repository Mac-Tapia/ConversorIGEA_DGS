# Spec 093 — La sigla de la carga nombra la carga nueva y su variación

Estado: implementada · Fecha: 2026-11-06 · Origen: usuario, 2026-11-06, AL209: «en las cargas y sus variaciones solo
debe poner con la columna de SIGLAS DE CARGA».

## Contexto y objetivo

El libro de cargas nuevas en bloque de la distribuidora trae, por fila, «SIGLAS DE CARGA» (PI_15), «DESCRIPCION»
(«SU_CementoINKA-Pisco») y la demanda. El lector solo reconoce «DESCRIPCION» como nombre (004:RF-53), así que la
carga, su SED y su variación se llamaban con el texto largo del cliente
(`Carga_EMPRESA_INVE_AL209_…`, `EMPRESA_INVERSIONES_DE_CEMENTO_S_A(2)`) y no por su sigla, que es como la
distribuidora la identifica. Con nombres largos se confundieron dos clientes de cemento de AL209 (PI_11 y PI_15).
Cambia 004:RF-53 (spec cumplida, que no crece).

## Requisitos funcionales (EARS)

- RF-1: DONDE el libro de cargas nuevas tenga una columna «SIGLAS DE CARGA» (o «SIGLAS», «SIGLA»), EL SISTEMA
  nombrará cada carga nueva con su sigla, y con ella su SED, su carga y su variación (007:RF-10).
- RF-2: SI una fila no trae sigla, ENTONCES EL SISTEMA la nombrará por su descripción como hasta ahora (004:RF-53).
- RF-3: EL SISTEMA conservará la descripción de la fila junto a la carga, para que el informe y los avisos digan
  de qué cliente se trata.

## Fuera de alcance

Renombrar las cargas nuevas ya creadas en proyectos de DIgSILENT con su descripción.

## Criterios de finalización

`grep -rnoE "093:RF-[0-9]+" tests | sort -u` cita los tres RF, suite enfocada en verde y la carga de un libro real
creada en DIgSILENT con su sigla.
