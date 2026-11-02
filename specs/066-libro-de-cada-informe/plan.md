# Plan 066

- `src/convertersmartgrid/libro_informe.py`: del JSON del informe a un plan de celdas (RF-1, RF-4, RF-5, RF-6, RF-8);
  Excel por COM aplica el plan, porque el modelo tiene imágenes, gráfico, vínculos y comentarios que openpyxl pierde al
  guardar (RF-9). Después se relee el libro y se comprueba (RF-7, RF-10).
- `config/perfiles/electro_dunas.json`: el plano del libro. El código no lleva celdas ni nombres de la empresa (RF-2, RF-4).
- `libros_informe.py`: precio por `hoja_precio` y `celda_precio` (RF-3).
- `web/services.py` y `InformesPF.tsx`: lo llaman los dos informes y lo ofrece la web (RF-11, RF-12).

Pruebas: un modelo pequeño creado con openpyxl y un sustituto de Excel que aplica el plan; la prueba real con Excel es T7.
Descartado: openpyxl para guardar, porque pierde las imágenes del libro y sus comentarios encadenados.
