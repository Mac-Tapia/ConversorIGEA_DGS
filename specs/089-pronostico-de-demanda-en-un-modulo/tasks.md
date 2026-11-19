# Tareas — Spec 089

- [x] T1. Datos vivos, equivalencia y lector de clientes. (RF-1 a RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_demanda.py` en verde.
- [x] T2. Limpieza y sentido de las series. (RF-18 a RF-28, RF-54)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde.
- [x] T3. Las tres clases y el apoyo. (RF-29 a RF-37, RF-55)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde.
- [x] T4. Métodos, backtest, exógenas y salida. (RF-38 a RF-53)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde.
- [x] T5. Backtest real de 2026 con la herramienta. (RF-38 a RF-43)
      Hecho cuando: el informe está fuera de git y sus cifras, sin datos de la distribuidora, anotadas aquí.
      Evidencia: 2026-11-12, sobre 6306cc65, `tools/pronostico_demanda.py` con cabecera, equivalencia, clientes, suministros y apoyo 2025 reales, sin exógenas; informe fuera de git (`D:/csg/pronostico_089_t5/backtest_t5.json`, dataset 003bf7b0ed34). 994 objetivos, 28 días, 3 orígenes. WAPE de prueba del método elegido, mediano/ponderado: cabecera kW 0,109/0,120, cabecera kVAR 0,234/0,258, cliente kW 0,265/0,259, cliente kVAR 0,328/0,317, escaladas kW 0,109/0,108, escaladas kVAR 0,285/0,248; el perfil semanal es el mejor en las seis. Historia insuficiente en 97 objetivos (91 clientes en cero) y 19 series apartadas. LightGBM en cabecera kW: WAPE 0,097, no pasa la puerta por el error en la máxima (0,115 frente a 0,098). Sin exógenas, `anclado_temperatura` no se evaluó; las redes en GPU son la T7.
- [x] T6. Modelos, conjunto y puerta. (RF-56 a RF-88)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde, en la GPU.
- [x] T8. Entrenamiento por alimentador en la GPU, sin rutas fijas. (RF-89, RF-90)
      Hecho cuando: `tests/test_entrenar_alimentadores_gpu.py` en verde y `--help` responde.
- [x] T9. Una ventana de entrenamiento por día en las redes, tope de lote de TFT e iTransformer sin escalado. (RF-91, RF-92, RF-93)
      Hecho cuando: `tests/test_pronostico_demanda.py::test_las_redes_toman_una_ventana_por_dia` y `::test_tope_de_lote_y_escalado_por_red` en verde, en la GPU.
- [x] T11. Lector de clientes adaptable: columnas por contenido y por sinónimos, aviso por formato, regla confirmada,
      mes por los datos y libro «día, hora» con más días que su mes. (RF-107 a RF-113)
      Hecho cuando: `tests/test_libros_formas.py` y `tests/test_libros_nuevos_web.py -k apartado_y_formato` fallan sin
      el arreglo y pasan con él (registros `D:/csg/D_todo_rojo_9063b8af.log` y `D:/csg/D_todo_verde.log`).
- [ ] T12. Regenerar el dataset con los libros reales y repetir su perfil: «0225 Pulso e» y «0625 Pulso» entran.
      (RF-107, RF-109)
      Hecho cuando: el perfil del dataset regenerado fuera de git ya no aparta esos dos libros y sus cifras, sin datos de
      la distribuidora, están anotadas aquí. Lo hace quien tiene la orden de regenerar (no esta tarea de código).
- [ ] T7. Corrida larga real de todos los modelos.
      Hecho cuando: cada clase, magnitud y horizonte tiene su informe fuera de git, con la decisión y sus cifras anotadas aquí.
- [x] T13. La lectura de cabecera del pronóstico libro a libro: un libro abierto a la vez, para todos los
      alimentadores y sus centrales, con el mismo resultado. (RF-114)
      Hecho cuando: `pytest -q tests/test_pronostico_demanda.py -k "memoria_de_la_cabecera or no_deja_abiertos or libro_a_libro"` (089:RF-114) en verde.
- [x] T14. La GRU no cuenta los objetivos ausentes en la pérdida (C10 del diagnóstico del 18-11, H17): huecos a cero
      solo en la entrada y máscara en el objetivo, sin reentrenar ni promover. (RF-115)
      Hecho cuando: `pytest -q tests/test_pronostico_gru_huecos.py` en verde en CPU, con su rojo por aserción en la base
      (la sonda H17 de D:/csg/INTEGRA_54/auditoria_c0 reproduce lo mismo).
