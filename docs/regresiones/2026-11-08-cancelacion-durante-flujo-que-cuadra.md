# Cancelación recibida durante el flujo que ya cuadra

## Síntoma

El ajuste individual o conjunto podía informar que había cuadrado y que no estaba
cancelado aunque el operador hubiera cancelado mientras se ejecutaba el flujo final.
El fallo dependía de si esa primera medida ya cumplía la tolerancia, por lo que un
ensayo aislado podía pasar y la misma prueba fallar durante la suite.

## Causa

`cuadrar` y `cuadrar_conjunto` consultaban la cancelación al empezar cada iteración.
Tras recibir la medida, podían retornar directamente por convergencia sin volver a
consultarla. No se iniciaba otra iteración que reconociera la solicitud.

## Comprobación permanente

Conservar primero el reparto y la medida del flujo que acaba de converger y después
consultar la cancelación, antes de aceptar el cuadre o calcular otro paso/remedio.
Si está solicitada, terminar como cancelado, sin declarar cuadrado. Cuando ese flujo
es el último reparto bueno, no ejecutarlo otra vez: las demandas y los resultados
ya corresponden al estado que debe conservarse (006:RF-22, 021:RF-58).

La consulta también cubre una solicitud que llegue al notificar el progreso del flujo.
Se mantienen la restauración del último reparto bueno cuando el flujo posterior no
converge, los remedios, el oráculo y todas las tolerancias y puertas físicas.

## Prueba

- `tests/test_ajuste_cabecera.py::test_cancelar_durante_el_flujo_que_cuadra_conserva_su_reparto`.
- `tests/test_ajuste_cabecera.py::test_cancelar_durante_flujo_conjunto_que_cuadra_conserva_todos`.
- `tests/test_ajuste_cabecera_guion.py::test_cancelar` conserva el recorrido completo del guion.

Las dos nuevas pruebas activan la cancelación dentro del flujo que devuelve la medida
en objetivo; cubren con y sin Q, incluso con presupuesto de un solo flujo. Exigen
cancelado, no cuadrado, la misma medida y repartos, un flujo y ningún remedio extra.
Evidencia externa `p25_ajuste_cancelacion_20261108`: cuatro fallos deterministas antes
del cambio, cuatro verdes focales y los dos módulos CPU completos en verde. Estos
datos son sintéticos; no se ejecutaron PowerFactory, GPU ni aceptación nativa.
