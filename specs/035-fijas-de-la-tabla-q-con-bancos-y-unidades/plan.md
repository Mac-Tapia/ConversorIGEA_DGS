# Plan — Spec 035

Estado: implementada (2026-10-29) · Spec: [spec.md](spec.md)

| Parte | Ficheros | RF |
| --- | --- | --- |
| Derivación de cada cliente (P, Q, fecha y método) en una sola función que usan la tabla y el ajuste | `src/igea_dgs/ajuste_cabecera.py` (`derivacion_cliente`, `fijas_de`) | RF-2 a RF-4 |
| Cruce con la máxima de cada alimentador: la web manda `maximas` (fecha, kW y kvar por alimentador) y el cruce toma el registro de ese instante | `src/igea_dgs/web/app.py`, `src/igea_dgs/web/services.py`, `frontend/src/api.ts`, `frontend/src/components/DemandaMedida.tsx` | RF-1 a RF-3 |
| Cuadre de la Q: factor `b` por secante sobre la Q de cabecera, en `cuadrar` y `cuadrar_conjunto`, con su estado (cuadrada, sin margen, sin base) | `src/igea_dgs/ajuste_cabecera.py` | RF-5, RF-6, RF-8, RF-9 |
| Escritura de la Q base por `b/a`, bancos en servicio, validación con el FP resultante, informe y unidades | `tools/ajuste_cabecera_pf.py`, `tools/cargas_pf.py` | RF-7, RF-10 a RF-16 |

Decisiones:

- La palanca de la Q son las escaladas porque son lo único que no viene medido: las fijas traen
  su Q del registro y los bancos son la red. Descartado mover los escalones de los bancos:
  015:RF-66 los pone a su máxima capacidad por decisión del usuario.
- Un solo `scale0` para P y Q (015:RF-44): la Q se mueve en la base (`qlini`) y no con otro factor
  de DIgSILENT, que no existe por separado para la Q de una carga.
- Unidades: detenerse en vez de convertir. Convertir obligaría a cambiar cada `* 1000` del guion
  y de las sondas; un error ahí multiplica por mil sin que se note. Detenerse es seguro y dice
  dónde corregirlo.

Pruebas: `tests/test_q_con_bancos.py` (cuadre de la Q con un flujo sintético lineal, sin margen y
sin base), `tests/test_tabla_en_el_instante.py` (la tabla y el ajuste dan la misma P y Q) y
`tests/test_unidades_pf.py` (con `fake_pf`); SM218 en DIgSILENT desde la web (T6).
