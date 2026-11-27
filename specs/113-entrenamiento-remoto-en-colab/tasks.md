# Tareas 113 — Entrenamiento remoto en Colab con evaluación local

- [ ] T1. Manifiesto de datasets y de candidatos, con huellas, revisión y origen. (RF-9, RF-10)
      Hecho cuando: `tests/test_entrenamiento_remoto.py` (113:RF-9, RF-10) en verde con su rojo por aserción.
- [ ] T2. Empaquetado con anonimización por tipo; los sellados y los crudos nunca entran. (RF-5, RF-6, RF-15)
      Hecho cuando: pruebas 113:RF-5, RF-6, RF-15 en verde con nombres sintéticos y un paquete VNR-GIS sintético.
- [ ] T3. `notebooks/ConverterSmartGrid.ipynb`: clonar la revisión, instalar lo fijado, montar Drive, comprobar el
      manifiesto, entrenar con puntos de control y Optuna, dejar candidatos. Sin salidas en git. (RF-1, RF-2, RF-3, RF-7, RF-8, RF-9)
      Hecho cuando: prueba de que el cuaderno no tiene salidas ni credenciales y de que su primera celda fija la revisión.
- [ ] T4. Web: «Entrenar en Colab» (comprobar árbol, confirmar, subir a Drive, abrir Colab) y «Traer los candidatos».
      (RF-4, RF-10, RF-11, RF-12) Hecho cuando: pruebas de API con el doble de Drive, `tsc` y `npm run build`.
- [ ] T5. `tools/entrenamiento_remoto.py` para VS Code, con su fila en MANUAL_COMANDOS. (RF-10, RF-14)
      Hecho cuando: `--help` y su prueba en verde; test_inventario en verde.
- [ ] T6. Aviso de datos nuevos para reentrenar. (RF-13) Hecho cuando: prueba 113:RF-13 en verde.
- [ ] T7. [Colab] Ensayo real corto: una familia, un dataset pequeño, tiempos medidos y candidato traído por sus puertas.
      (RF-4 a RF-12) Hecho cuando: la evidencia (tiempos, manifiesto, veredicto de la puerta) consta aquí.
