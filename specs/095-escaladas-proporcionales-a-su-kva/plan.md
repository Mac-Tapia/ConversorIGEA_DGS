# Plan 095 — Escaladas proporcionales a su kVA

## Dónde

- `src/convertersmartgrid/ajuste_cabecera.py`: `probabilistico_de_fijas` devuelve pendiente 0 y la dispersión como la
  desviación típica de log(kW/kVA) de las fijas alrededor de su media (RF-1, RF-2); `probabilistico_del_perfil`
  devuelve pendiente 0 y anota si el perfil traía otra (RF-3).
- `tools/ajuste_cabecera_pf.py`, `preparar_probabilistico`: el perfil, con pendiente 0 (RF-3).
- `muestra_de_reparto` no cambia: con pendiente 0, el multiplicador es solo el ruido de media 1.

## Decisión

- Pendiente 0 en el origen de los parámetros, no en el muestreo: así el muestreo sigue probado como estaba y la
  decisión queda en un solo sitio. Descartado: quitar el término de la potencia de `muestra_de_reparto`.

## Pruebas

- `tests/test_reparto_probabilistico.py`: de fijas con pendiente real, la pendiente sale 0 y la dispersión es la de su
  utilización; una muestra con pendiente 0 da a cada escalada la misma utilización esperada; el perfil con pendiente
  la ignora y lo dice.
