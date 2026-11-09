# Plan 101

## Módulos

- `src/convertersmartgrid/web/services.py`
  - `cambios_automaticos(informes, hechos)` (RF-1, RF-4, RF-6, RF-12): función pura. De cada informe toma
    `fijas_sobre_su_transformador` y las de `sed_sobre_umbral` con nivel `sobre_100`, con propuesta y un solo
    transformador, y quita las ya aplicadas con la misma potencia y las mismas unidades.
  - `ajuste_ejecutar` (RF-2, RF-3, RF-5, RF-8 a RF-11, RF-13): al aplicar, si `veredicto_calibracion` deja pendientes y
    hay cambios, llama a `ajuste_transformadores_varios` (020), que escribe los transformadores y recalibra el proyecto
    entero, hasta 3 rondas. El resultado lleva `transformadores_automaticos` con las rondas.
  - RF-7: `motivo_de_informe` ya da el motivo físico; si hay SED sobre el 100 % sin propuesta, se añade su motivo
    (`propuesta.motivo`) al Registro.

## Decisiones

- Se reutiliza `ajuste_transformadores_varios` (la ruta del botón de la 020) en lugar de una segunda ruta de escritura:
  mismo guion, mismas reglas de tipos (020:RF-19 a RF-22) y la misma recalibración. Descartado: cambiar los
  transformadores dentro de `tools/ajuste_cabecera_pf.py` antes del primer flujo, porque se saltaría la detección
  sobre la calibración real y la recalibración registrada (020:RF-28).
- El tope es de 3 rondas: una basta cuando la sobrecarga es de las fijas, y otra cuando una escalada pasa del 100 % solo
  con el reparto nuevo. La tercera es margen.

## Pruebas

- `tests/test_transformadores_automaticos.py`: la selección con informes sintéticos (RF-1, RF-4, RF-6, RF-12), y el
  bucle con `_correr_guion_ajuste` sustituido (RF-2, RF-3, RF-5, RF-8 a RF-11, RF-13).
- En DIgSILENT, la calibración de CA101 + CHN102 desde la web.
