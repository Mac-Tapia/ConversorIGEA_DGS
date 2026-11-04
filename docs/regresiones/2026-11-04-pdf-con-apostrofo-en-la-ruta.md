# Una carpeta con apóstrofo rompía la exportación a PDF del informe

## Síntoma
`exportar_pdf` escribía la ruta dentro de comillas simples de PowerShell sin escaparla. Con un apóstrofo en la ruta la orden sale mal formada y el PDF no se genera. Reproducido con el doble de `ejecutar`, leyendo la orden. No se ha ejecutado con Word.

## Causa
Dentro de comillas simples de PowerShell el apóstrofo se dobla, y la orden no lo doblaba.

## Comprobación permanente
`exportar_pdf` dobla el apóstrofo en las dos rutas de la orden.

## Prueba
- `tests/test_informe_corrida.py::test_pdf_con_un_apostrofo_en_la_ruta`
