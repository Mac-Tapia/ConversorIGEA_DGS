# Una SED de una fase que no llega a su ramal: barra de baja a 0 p.u. con el flujo «convergido»

## Síntoma
El flujo decía que convergió. La barra de baja de la SED estaba a 0 p.u. y su carga no consumía: faltaba demanda sin ningún aviso.

## Causa
La SED ocupa una fase que su ramal no lleva. DIgSILENT no da error: la deja sin alimentar. Corrige el modelo en TXT y MDB la rama `fix/acopladores-con-fases` (054:RF-9), sin integrar cuando se escribe esto.

## Comprobación permanente
Dos, y ninguna depende de ese arreglo. Antes de importar, `comprobacion_fases.comprobar_modelo` calcula lo que llega a cada nodo y dice cada elemento que pide lo que no le llega. Tras el flujo, `comprobacion_flujo.comprobar_tras_flujo` cuenta las barras de baja con carga a 0 p.u. y las cargas que no consumen; con alguna, el flujo no sale limpio: `CONVERGE_SIN_SERVIR`, que calibra pero no es `VERIFICADO`, e `IMPORTADO_CON_CARGAS_SIN_SERVIR` en vez de «OK». La lectura real es la T11 de la spec 081.

## Prueba
- `tests/test_comprobacion_fases.py::test_fases_que_no_llegan_desde_la_cabecera`
- `tests/test_comprobacion_flujo.py::test_barra_de_baja_con_carga_a_cero`
- `tests/test_comprobacion_flujo.py::test_carga_que_no_consume`
- `tests/test_comprobacion_flujo.py::test_flujo_sin_servir_no_sale_limpio`
- `tests/test_comprobacion_flujo.py::test_importacion_limpio_no_dice_ok`
