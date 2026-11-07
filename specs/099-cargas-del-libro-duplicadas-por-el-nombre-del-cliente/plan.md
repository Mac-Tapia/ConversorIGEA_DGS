# Plan 099 — Cargas del libro duplicadas por el nombre del cliente

## Dónde

- `src/convertersmartgrid/cargas_pf.py`: `palabras_del_cliente`, `mismo_cliente` y `duplicadas_por_cliente`, puras,
  junto a la lectura del libro (RF-1 a RF-4, RF-6).
- `tools/cargas_pf.py`, `resolver_nuevas`: antes del bucle, `duplicadas_por_cliente` con `MISMO_PUNTO_M`; la fila que
  no cuenta va a `no_creadas` con `duplicada_de` y, si ya tiene variación, `eliminar` (RF-1, RF-5). El camino de
  040:RF-1 queda como respaldo y ya no se alcanza con filas del mismo punto, que resuelve RF-4.

## Decisiones

- La última fila del libro, no la de más potencia: es la versión vigente de la solicitud y es la que pidió el usuario
  para Tierra Larga (CH_23, 1 390 kW, frente a CH_20, 1 770 kW).
- Comparar por palabras y no por distancia de edición: «SU-1770KW-Tierra Larga - Distrito el Camen…» y
  «SU-1390KW-TierraLarga-Chincha» difieren en más de la mitad de sus letras y son el mismo cliente.
- Una pasada por alimentador del libro, con sus filas nada más (escala).
