# Plan 113 — Entrenamiento remoto en Colab con evaluación local

## Módulos

- `notebooks/ConverterSmartGrid.ipynb` (RF-1, RF-2, RF-3, RF-7, RF-8, RF-9, RF-14): celdas por familia; la primera clona
  y comprueba la revisión; monta Drive, verifica el manifiesto, entrena con puntos de control y deja los candidatos.
- `src/convertersmartgrid/aplicacion/entrenamiento_remoto.py` (RF-4, RF-5, RF-6, RF-9, RF-10, RF-15): manifiestos,
  empaquetado y anonimización por tipo de dataset, comprobación de huellas a la vuelta. Sin red: recibe un cliente de Drive.
- `src/convertersmartgrid/presentacion/web/` (RF-4, RF-10, RF-11, RF-13): rutas «preparar y abrir Colab», «traer
  candidatos» y aviso de datos nuevos; usan la integración de Drive de la 109 y el registro de modelos de la 043.
- `tools/entrenamiento_remoto.py` (RF-10, RF-14): lo mismo desde la línea de órdenes, para VS Code.
- Puertas: las existentes de cada familia (047/070 asistente, 045/071 PINN y gemelo, 089 pronóstico, 074/114 MASAC).

## Decisiones

- El cuaderno se abre desde GitHub en la revisión exacta (`colab.research.google.com/github/…/blob/<commit>/…`) y no
  subiendo el fichero local: garantiza que el código de Colab es el instalado. Descartado: subir el `.ipynb` a mano.
- Los datos van por el Drive privado del operador y nunca por GitHub. Descartado: un almacén propio en la nube.
- La evaluación es siempre local, frente a conjuntos sellados que no salen. Descartado: evaluar en Colab.

## Pruebas

- Sintéticas: manifiesto con huellas; rechazo por huella o revisión distintas; los sellados nunca en el paquete; el
  cuaderno sin salidas; anonimización por tipo con nombres sintéticos.
- Doble de Drive (como 109) para subir y traer sin red.
- Real: un ensayo corto en Colab Pro con un dataset pequeño, medido, y un candidato traído que pasa o no sus puertas.
