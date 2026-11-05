# Spec 092 — El «Caso base» de una red reconstruida se verifica con lo que hay en disco

Estado: implementada · Fecha: 2026-11-05 · Origen: usuario, 2026-11-05, Pisco: «debe revisar el porqué; si ya está
hecho, si tiene un antecedente, debe corregir; no puede obviar lo que dice; ve al fondo».

## Contexto y objetivo

Al recalibrar AL209 y PA217 de `20261103-013907_CSG_SISTEMA_PISCO` desde la web, la verificación del «Caso base»
falló dos veces con «SOURCE_RUN_MISMATCH: SISTEMA_PISCO sale de una reconstrucción y la red no está cargada en esta
sesión de la web. Pulse «Cargar / listar alimentadores»», también después de pulsarlo. La causa es un círculo:

1. «Cargar / listar alimentadores» crea una ejecución nueva y la red en memoria es la de esa ejecución.
2. La verificación usa la ejecución con la que se aceptó el proyecto (018:RF-15); como la red en memoria es de otra,
   la deja de dar por cargada (`invalidate`), para no hacer creer que lo está.
3. Después, un DGS de reconstrucción exigía la red cargada (018:RF-12): nunca puede estarlo, porque la cargada es
   siempre otra ejecución.

Lo que se valida de una reconstrucción es su informe en disco: el SHA-256 del informe, el del sidecar y los recuentos
de reparaciones, coincidencias y supuestos (`verify_reconstruction_contract`). Con el informe de Pisco da
`VERIFIED_BEFORE_MUTATION` sin la red en memoria. Cambia 018:RF-12 (spec cumplida, que no crece).

## Requisitos funcionales (EARS)

- RF-1: CUANDO se verifica el «Caso base» de un proyecto ya importado cuyo DGS sale de una reconstrucción, EL SISTEMA
  validará la reconstrucción con su informe y su sidecar en disco, sin exigir la red cargada en la sesión.
- RF-2: SI el informe de la reconstrucción no está en disco o su SHA-256 o sus recuentos no son los del sidecar,
  ENTONCES EL SISTEMA no verificará y dirá el motivo con el código `POWERFACTORY_RECONSTRUCTION_MISMATCH`.
- RF-3: DONDE la sesión de la web tenga una reconstrucción propia, EL SISTEMA exigirá además que sea la del DGS, como
  hasta ahora.
- RF-4: EL SISTEMA seguirá exigiendo la red cargada para importar un DGS de reconstrucción.

## Fuera de alcance

- Cambiar cómo se reconstruye la red (022:RF-57 a RF-61) o el vínculo de los proyectos (spec 018).

## Criterios de finalización

- `grep -rnoE "092:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-4.
- La verificación del «Caso base» de Pisco desde la web, sin «SOURCE_RUN_MISMATCH».
