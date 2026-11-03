# Tareas — Spec 079

- [x] T1 La prueba `sellada_079`, escrita de una vez y antes del currículo, y la sellada anterior sin decidir. (RF-38 a RF-48, RF-60, RF-64)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k sellada` y `tests/test_asistente_maestro.py` en verde.
- [x] T2 Codificador partido, afinado con parada por selección y artefacto. (RF-1 a RF-24)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k "afinado or artefacto"` en verde.
- [x] T3 Pérdida contrastiva, grupos, lotes y confusiones. (RF-25 a RF-30)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k contrastiva` en verde.
- [x] T4 Currículo de las tareas flojas. (RF-31 a RF-37)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k curriculo` en verde.
- [x] T5 Validación cruzada con afinado y regla de Ollama elegida en desarrollo. (RF-49 a RF-57)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k "cruzada or regla"` en verde.
- [x] T6 Herramienta, protocolo y caché local. (RF-58, RF-59, RF-61 a RF-63)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k "herramienta or cache"` en verde.
- [ ] T7 [DIgSILENT] El integrador lanza el afinado en la GPU y mide; no usa DIgSILENT, pero es la tarea de la ejecución real.
  Hecho cuando: el registro deja la decisión con las dos selladas, la medida fuera de grupo y la rejilla de la regla de Ollama.
