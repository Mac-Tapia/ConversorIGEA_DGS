# Spec 088 — Q negativa desde el factor de potencia

Estado: cumplida · Fecha: 2026-11-05

## Contexto y objetivo

El usuario, el 2026-11-05: si los kVAR son negativos, se usa el factor de potencia en cualquier alimentador; «el factor de potencia es inductivo y es positivo el Q y si el factor de potencia es capacitivo es negativo Q». La limpieza de signos para entrenar está en la 089. Cita la 006 y la 035, que están cumplidas y no crecen.

Medido en los cuatro libros de cabecera de 2026 (191 hojas, 5,25 millones de registros): el 23 % de los registros tiene kVAR negativo, y 29 hojas tienen kW negativo en más del 1 %. Seis hojas lo tienen en más del 98 % (medidores en sentido contrario, con `PF lag`), y las de centrales y baterías, en ambos sentidos.

Los signos se dan en el sentido de la carga: inductivo es Q con el signo de P, y capacitivo, Q con el signo contrario. Un medidor en sentido contrario da P y Q negativas con `PF lag`, y forzar ahí una Q positiva rompería el balance de las centrales y, al invertirlo para entrenar, dejaría la Q al revés.

## Requisitos funcionales (EARS)

- RF-1: CUANDO un registro de cabecera con kW distinto de cero traiga un kVAR negativo, EL SISTEMA calculará su Q con el factor de potencia como |kW| · tan(acos(FP)).
- RF-2: CUANDO el FP del registro sea capacitivo (`lead`), EL SISTEMA dará a Q el signo contrario al de su kW.
- RF-3: CUANDO el FP del registro sea inductivo (`lag`), EL SISTEMA dará a Q el signo de su kW.
- RF-4: SI el registro no trae un FP de adelanto o atraso, ENTONCES EL SISTEMA tomará FP = |kW| / kVA y conservará el signo negativo del kVAR.
- RF-5: SI el registro no permite calcular un FP mayor que 0, ENTONCES EL SISTEMA conservará el kVAR de su columna.
- RF-6: CUANDO un medidor conserve un kVAR negativo de su columna, EL SISTEMA lo dirá en sus avisos con el número de registros.
- RF-7: EL SISTEMA conservará el kVAR de la columna de los registros con kVAR positivo o cero.
- RF-8: EL SISTEMA no cambiará el kW de ningún registro de cabecera por esta regla.
- RF-9: EL SISTEMA usará la Q calculada en la máxima y en la curva del medidor.
- RF-10: CUANDO se calcule la Q de algún registro, EL SISTEMA dirá en las columnas del resultado que la Q es calculada.
- RF-12: SI la Q calculada supera el kVA del registro, ENTONCES EL SISTEMA conservará el kVAR de su columna.
- RF-11: EL SISTEMA no llevará en el código ningún medidor ni alimentador de una empresa para esta regla.

## Fuera de alcance

Los registros con kVAR positivo y `PF lead`, que siguen con su columna; depurar los registros en que la Q calculada se separa de la columna; separar la Q de los bancos; el reparto de la Q entre fijas y escaladas.

## Criterios de finalización

Cada RF citado por una prueba `088:RF-n` y en verde, con la comprobación real con `CSG_DEMANDA_DIR`.
