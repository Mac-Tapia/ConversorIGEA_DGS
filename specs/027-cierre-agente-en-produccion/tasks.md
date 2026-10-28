# Tareas — Spec 027

Estado: borrador del 2026-10-28, pendiente de aprobación. Una tarea cada vez, pruebas primero.

- [ ] T0. Auditoría del dataset de cada modelo antes de entrenar (`tools/digital_twin_auditar.py`
      e informe en el registro del modelo): estructura, validez, rangos, impedancias mínimas,
      tensiones implausibles, parámetros frente a etiquetas; corregir el comentario de
      `Muestra.x` (5 columnas, no 4). (RF-29 a RF-34)
      Hecho cuando: `pytest -q tests/test_digital_twin_auditoria.py` en verde con datos
      sorteados que traen cada defecto, y el informe del búfer real reproduce las cifras del
      2026-10-28 (24 muestras, 1 red de 2470 nodos, 928 518 parámetros).
- [ ] T1. Episodio tras cada calibración, obra y estudio de cualquier sistema desde la web, con
      sistema, SET, caso y huella. (RF-1)
      Hecho cuando: `pytest -q tests/test_digital_twin_capture.py` en verde y, tras calibrar
      Nasca y Chincha desde la web, el búfer tiene episodios de las dos familias.
- [ ] T2. Particiones «un sistema fuera» y mínimo de episodios de prueba por familia. (RF-2, RF-3)
      Hecho cuando: `pytest -q tests/test_digital_twin_evaluacion.py` en verde con familias
      sorteadas; ningún sistema en entrenamiento y prueba a la vez.
- [ ] T3. Escenarios por hipercubo latino del rango de carga medido, en copias del proyecto. (RF-4)
      Hecho cuando: pruebas de `escenarios.py` en verde y una corrida en DIgSILENT con Nasca.
- [ ] T4. `Entrenamiento` con paciencia, coseno, recorte de gradiente y mejor época; GRU con
      validación temporal y sin caída a CPU. (RF-5, RF-6, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_digital_twin_oraculo.py tests/test_digital_twin_temporal.py`
      en verde; sin CUDA, error claro.
- [ ] T5. Manifiesto con commit, huellas, configuración, semilla y dispositivo; reproducción con
      diferencia < 10⁻⁵ p.u. (RF-8, RF-9)
      Hecho cuando: prueba de reproducibilidad en GPU en verde.
- [ ] T6. Búsqueda de hiperparámetros con presupuesto (Optuna, TPE y poda), solo en validación,
      y `tools/digital_twin_entrenar.py --buscar`. (RF-7)
      Hecho cuando: prueba sintética en verde; `--help` sin GPU; informe de ensayos guardado.
- [ ] T7. Intervalo conforme por barra y marca de no confiable. (RF-12, RF-13)
      Hecho cuando: cobertura empírica ≥ la pedida − 2 % en datos sorteados.
- [ ] T8. Top-k verificado en DIgSILENT con `pf_arnes`; descarte, episodio y siguiente;
      gemelo y DIgSILENT en la propuesta. (RF-14 a RF-16)
      Hecho cuando: prueba con `fake_pf` en verde y una propuesta de bancos verificada en
      DIgSILENT con Chincha.
- [ ] T9. Conjunto de órdenes reales del operador, versionado y separado; puertas de tarea y
      datos; confirmación obligatoria mientras sea pequeño. (RF-17 a RF-19)
      Hecho cuando: pruebas del asistente en verde; la web muestra el tamaño del conjunto.
- [ ] T10. Realimentación del error con un único reintento en el ejecutor. (RF-20)
      Hecho cuando: prueba con un error forzado: un reintento y luego vuelta al operador.
- [ ] T11. (Condicional) LoRA/QLoRA local si T9 no pasa las puertas. (RF-21)
      Hecho cuando: el modelo ajustado pasa RF-18 con el conjunto real, o la tarea se cierra
      con la medida de que no hace falta.
- [ ] T12. Deriva, propuesta de reentrenamiento y vuelta atrás desde la web. (RF-22 a RF-24)
      Hecho cuando: pruebas de API en verde y botón en la web compilada.
- [ ] T13. Carril `engine` en un proceso trabajador con límite de memoria. (RF-25 a RF-27)
      Hecho cuando: `/api/health` < 1 s durante la búsqueda de la máxima de Chincha y un
      trabajo que supera el límite se detiene sin tumbar la API.
- [ ] T14. Aceptación: todos los sistemas desde la web con el asistente, gemelo con dos o más
      familias de prueba y asistente con RF-18. (RF-28)
      Hecho cuando: informe con Nasca, Chincha, Pisco e Ica válidos en DIgSILENT y las métricas
      de las puertas.
