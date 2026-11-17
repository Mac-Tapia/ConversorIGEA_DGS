# ADR-011 · Los vínculos entre módulos son una matriz declarada y citada en la norma

- Estado: vigente
- Fecha: 2026-11-17
- Specs: 109:RF-25
- Elementos C4: vnr, vad, pit, planning, regulador, fuentes
- Tareas: 109 T20

## Contexto

El VNR, el VAD, el PIT, el PIDE y el planeamiento de corto y largo plazo comparten unas entradas, tienen las suyas
y dan sus propios entregables, y unos consumen lo que otro produce: el VNR entra en la TIR del VAD (LCE, arts. 70, 71
y 77); las inversiones del PIDE se incorporan en la anualidad del VAD y el PIDE descuenta lo que el VAD ya reconoce
(TdR del PIDE de una distribuidora estatal, con su huella); el PIT se planifica por área de demanda (Norma Tarifas,
RCD 217-2013-OS/CD). El usuario pidió que esa articulación se sostenga en la norma y en evidencia real, no en el
diseño.

## Decisión

`config/modulos/vinculos.json` declara, por módulo, las entradas compartidas (con su origen: el espacio o las fuentes
de la empresa), las propias, los entregables y lo que consume de otro módulo, cada uno con su cita: norma y clave del
registro normativo, artículo, documento de práctica con su huella, o «decisión de producto» con su motivo. Una prueba
comprueba que cada cita existe y que cada compartida está declarada. Lo que la norma aún no aprueba (los criterios del
PIDE, RM 428-2017, prepublicada) va con su estado.

## Alternativa descartada

Dejar los vínculos implícitos en el código de cada módulo. Nadie podría comprobar si una pestaña pide lo que no le
toca o si un entregable sale de la norma.

## Consecuencias

Un módulo nuevo o un cambio de norma empieza por la matriz. Las pantallas y los endpoints se comprueban contra ella.

## Contratos afectados

`config/modulos/vinculos.json` (esquema `vinculos_modulos_v1`).

## Vuelta atrás

Es una declaración: quitarla no cambia el cálculo, solo deja sin comprobar los vínculos.
