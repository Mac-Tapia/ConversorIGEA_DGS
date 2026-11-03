# Tareas — Spec 046

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Preparación causal y corrección de GRU. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_series_causales.py tests/test_digital_twin_temporal.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Adaptadores y salida multihorizonte. (RF-4, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_multihorizonte.py tests/test_digital_twin_temporal.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Benchmark, calibración y promoción temporal. (RF-6, RF-7, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_evaluacion_temporal.py tests/test_pronostico_multihorizonte.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [x] T4. Objetivos de cabecera y de clientes fijos. (RF-9, RF-10, RF-11, RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_objetivos.py` pasa.

- [ ] T5. Competición y ganador por objetivo. (RF-13, RF-14, RF-15, RF-16, RF-17, RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_competicion.py tests/test_pronostico_gpu.py` pasa, la segunda con CUDA.

- [x] T6. Artefacto e integración opcional. (RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-25)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_integracion.py` pasa.

- [ ] T7. Medición real en GPU. (RF-5, RF-6, RF-7, RF-8, RF-13, RF-16, RF-17, RF-18)
      Hecho cuando: el informe de `--comparar` sobre medición real está guardado fuera de git y sus métricas y decisión están anotadas aquí sin datos de la distribuidora.

## Evidencia de ejecución

Fase 1, 2026-11-02, sin GPU (ningún modelo neuronal se ha entrenado ni cargado todavía):

- Implementación: T1 a T6 escritas. T1, T2, T3 y T5 siguen abiertas porque su «Hecho cuando» incluye
  pruebas en CUDA (`test_escala_usa_solo_entrenamiento`, `test_gru_reproduce_el_mes` y
  `tests/test_pronostico_gpu.py`) o el benchmark real de T7, que no se han lanzado.
- La fuga de escala de `GemeloGRU.entrenar` ya estaba corregida en la base (corte `ventana + n_ent`,
  desde 7f56651a); no se tocó y su prueba necesita CUDA. `GemeloGRUMultihorizonte` ajusta la escala solo con
  `valores[:fin_entrenamiento]`.
- Pruebas sin GPU, en verde: `test_pronostico_objetivos`, `test_evaluacion_temporal`,
  `test_pronostico_multihorizonte`, `test_pronostico_competicion`, `test_pronostico_integracion`. Ciclo de
  fallo previo: antes de implementar, las cinco fallaban en la recogida con
  `ModuleNotFoundError: convertersmartgrid.digital_twin.pronostico`.
- Prueba de datos reales de T4 con `CSG_DEMANDA_DIR`: un libro mensual de clientes da curvas de 15 minutos.
- Inventario real de 2026 con `--inventario`, solo lectura, informes en `output/inventario` (fuera de git).
  Cabecera, cuatro libros de sistema: del 1 de enero al 27 de octubre, 299 días, cadencia de 15 minutos en todos los
  objetivos; 399 objetivos, de los que 35 se apartan por no tener señal; huecos por objetivo: mediana 0 a 2.
  Clientes: 556 objetivos de cinco libros mensuales (mayo a septiembre), 153 días, 15 minutos, sin huecos; 25
  se apartan sin señal. Los cuatro libros `.xlsb` de enero a abril no tienen maestro ni hojas con SUMINISTRO, FECHA,
  HORA y EA: se apartan con ese motivo, sin rellenar.
- Limitaciones de T6: no hay panel propio en el front (el resultado se ve en el trabajo) y el asistente lo pide
  con el formulario `pronostico` de `extras`: una orden en texto libre no lo dispara, porque el intérprete
  no se ha tocado.
- Sin medición real ni modelo ganador: la Fase 2 (T7) espera el turno de GPU.


Las tareas abiertas pueden contener código parcial: el registro distingue implementación, datos reales, verificación y aceptación pendiente.
