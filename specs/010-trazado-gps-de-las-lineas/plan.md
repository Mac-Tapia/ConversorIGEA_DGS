# Plan — Spec 010, trazado GPS de las líneas

## Formato (comprobado en PowerFactory 2024 el 2026-10-10)
DGS 7.0, apartado 6.7 de `Dgs/DGS_Documentation.pdf`: con la cabecera
`GPScoords:MATRIX` (la que ya usa el perfil `pf21_dgs_1_8_4`), la celda de la línea lleva
el FID de una matriz, y la matriz va en la tabla auxiliar
`$$Matrix;FID(a:40);MatColumn(i);MatRow(i);Val(r)`, una fila por valor. PowerFactory la
importa como n filas (puntos) × 2 columnas: `MatColumn` 0 latitud, 1 longitud. En AL106
(172 líneas) el trazado importado coincidió punto a punto con el origen y ninguna
longitud cambió (diferencia máxima 0,017 mm).

Descartado: la forma desnormalizada (`GPScoords:SIZEROW`, `GPScoords:0:0`, …) necesita
una columna por cada coordenada posible, fijada en la cabecera para todas las líneas; el
número de puntos varía por línea y por entrega.

## Módulos

| Parte | Fichero | RF |
| --- | --- | --- |
| Tabla `Matrix` en el perfil, al final del orden de tablas | `src/igea_dgs/schemas/pf21_dgs_1_8_4.json` | RF-1 |
| Filas de la matriz al escribir `ElmLne`; tabla solo si hay filas | `src/igea_dgs/dgs.py` | RF-1, RF-2, RF-3, RF-4 |
| `Matrix` fuera de la regla de FID único (su clave es FID + columna + fila); trazado releído frente a la geografía | `src/igea_dgs/validate.py` | RF-5 |
| Trazado de las líneas en PowerFactory frente al manifiesto; cuenta en el informe; falla el diagrama si difiere | `tools/powerfactory_acceptance.py` | RF-6, RF-7 |
| Excepción de RF-14 y línea base regenerada | `specs/001-reorganizacion/spec.md`, `output/linea_base_001.json` | — |

## Decisiones
- **FID de la matriz:** `GPS_<FID de la línea>`. No usa el registro de FID: pedir FID nuevos
  en mitad de `ElmLne` renumeraría todo lo que viene después y el cambio del DGS sería
  mucho mayor que el trazado. Ningún otro FID empieza por `GPS_`.
- **Puntos:** `GeoLine.path` tal cual. La geografía ya garantiza que empieza y acaba en el
  `GeoPoint` de sus barras (`validate_geography`), y los dos se escriben con el mismo
  formato (`.12g`): primer y último punto idénticos al GPS de la barra (RF-2).
- **Red unida:** `convert_group` ya llama a `write_dgs` con la geografía del modelo unido;
  no necesita código propio (RF-4), solo prueba.
- **Sin georreferenciación:** `geography is None` → celda vacía y sin tabla (RF-3).

## Pruebas
- `tests/test_trazado_gps.py` (nuevo), con el export sintético sorteado en las dos
  disposiciones: trazado = geografía punto a punto, extremos = GPS de las barras, sin
  georreferenciación no hay tabla, red unida, validación que detecta un trazado alterado,
  DGS idéntico con `workers=1` y `workers=2`.
- `tests/test_powerfactory_gate.py`: comprobación del trazado en la aceptación con
  objetos falsos de PowerFactory.
- Datos reales: suite con las tres `IGEA_*`; red unida NA203 + NA205 importada en
  PowerFactory con `--manifest`.
