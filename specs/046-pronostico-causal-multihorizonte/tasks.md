# Tareas — Spec 046

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Preparación causal y corrección de GRU. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_series_causales.py tests/test_digital_twin_temporal.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [x] T2. Adaptadores y salida multihorizonte. (RF-4, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_multihorizonte.py tests/test_digital_twin_temporal.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [x] T3. Benchmark, calibración y promoción temporal. (RF-6, RF-7, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_evaluacion_temporal.py tests/test_pronostico_multihorizonte.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [x] T4. Objetivos de cabecera y de clientes fijos. (RF-9, RF-10, RF-11, RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_objetivos.py` pasa.

- [x] T5. Competición y ganador por objetivo. (RF-13, RF-14, RF-15, RF-16, RF-17, RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_competicion.py tests/test_pronostico_gpu.py` pasa, la segunda con CUDA.

- [x] T6. Artefacto e integración opcional. (RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-25)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_integracion.py` pasa.

- [x] T7. Medición real en GPU. (RF-5, RF-6, RF-7, RF-8, RF-13, RF-16, RF-17, RF-18)
      Hecho cuando: el informe de `--comparar` sobre medición real está guardado fuera de git y sus métricas y decisión están anotadas aquí sin datos de la distribuidora.

## Evidencia de ejecución

Fase 1, 2026-11-02, sin GPU (ningún modelo neuronal se ha entrenado ni cargado todavía):

- Implementación: T1 a T6 escritas; lo que pedía CUDA o medición real se cerró en la Fase 2, abajo.
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

Fase 2, 2026-11-02, en la GPU, sobre la revisión del merge de `main` c8999826. Informes en `output/pronostico/`, fuera de git:

- Pruebas CUDA: `tests/test_pronostico_gpu.py tests/test_series_causales.py tests/test_digital_twin_temporal.py
  tests/test_correcciones_aprendizaje_gpu.py`: 16 passed, sin omitidas, en 17,5 s. GRU, N-HiTS, TFT y PatchTST cargan,
  entrenan, predicen y reabren en CUDA.
- Medición real corta (300 pasos, una semilla, contexto del modelo de 2 días, una emisión cada 2 horas), con
  las puertas tal como se declararon antes de medir: dos alimentadores de un sistema (4 objetivos; particiones de
  180/45/30/45 días) y tres clientes fijos (6 objetivos; 92/23/15/24 días). Los seis modelos se evaluaron en las
  mismas ventanas, con una huella por corrida.
- Decisión: **ningún modelo neuronal supera las puertas, gana la referencia en los 10 objetivos** (estacional
  semanal en 9, ingenuo en 1). `RECHAZADO` en las dos clases, sin promoción: el registro de la corrida queda sin
  activo. Reapertura en otro proceso correcta, error relativo 0 en los cuatro modelos.
- Puertas pasadas por familia (objetivo y horizonte), cabecera/clientes: habilidad_pinball 2/12 y 11/18,
  habilidad_mae 3/12 y 8/18, maxima_no_peor 12/12 y 15/18, instante_no_peor 12/12 y 6/18, cobertura_en_banda 12/12 y
  13/18, mejora_significativa 1/12 y 8/18. Habilidad de pinball mediana por horizonte 1/4/96: −0,52/−0,01/+0,12
  en cabecera y −0,21/+0,26/+0,13 en clientes.
- Recursos: cabecera 92,2 s, 1 743 MiB de GPU y 2 360 MiB de RAM; clientes 108,6 s, 1 867 MiB y 2 776 MiB. Con
  las demás sesiones, la RAM disponible bajó a 141 MiB en cabecera.
- Limitaciones: es una corrida corta, no un veredicto sobre esos modelos con más pasos, semillas o datos; solo cubre
  esos objetivos; clientes con 153 días, y 2026 sin un año entero. El artefacto emite con la referencia global del
  objetivo en todos los horizontes, aunque a 15 minutos sea mejor el ingenuo.
- Para la spec 070 (asistente): una tarea propia del pronóstico, con frases y datos propios, y quien rellene el
  formulario `pronostico` de `extras` (clase, libros, zona, cadencia, pares o clientes). Hoy solo lo dispara ese
  formulario, y «pronostica…» en el currículo cae en `gemelo_temporal`, que reconstruye.


Las tareas abiertas pueden contener código parcial: el registro distingue implementación, datos reales, verificación y aceptación pendiente.
