# Tareas — Spec 024, primera entrega: búfer de episodios

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [ ] T1. Contrato del episodio: clases (`accepted`, `converged_with_violations`, `rejected`,
      `counterfactual`, `quarantine`), caso (`caso_base`, `sin_proyecto`, `con_proyecto`),
      bloque de resultados del flujo (balance, pérdidas, cargabilidad, tensiones, confiabilidad
      con ausentes explícitos), campos del PIDE de cada obra, JSON canónico, SHA-256 y validación
      con la ruta del campo que falla; esquema JSON. (RF-1, RF-2, RF-7, RF-28, RF-32)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_digital_twin_episode.py`
      en verde.
- [ ] T2. Búfer inmutable: objeto atómico por huella, idempotente, colisión detectada, índice
      SQLite con consultas por proyecto, alimentador, caso, clase, acción y versión de
      PowerFactory, reconstrucción del índice y cuarentena de manifiestos corruptos.
      (RF-6, RF-7, RF-8, RF-9, RF-10)
      Hecho cuando: `pytest -q tests/test_digital_twin_buffer.py` en verde.
- [ ] T3. Evaluación por caso: «Caso base» y «Sin proyecto» con violaciones como diagnóstico;
      «Sin proyecto» aceptado solo si la calibración cuadra; «Con proyecto» contra la norma de su
      sistema (NTCSE/NTCSER del perfil), pérdidas y confiabilidad frente a «Sin proyecto»;
      cuarentena sin tolerancia NTCSER o sin «Sin proyecto» de referencia; revertido o sin
      reapertura nunca `accepted`. (RF-4, RF-5, RF-29, RF-30, RF-31)
      Hecho cuando: `pytest -q tests/test_digital_twin_evaluacion.py` en verde.
- [ ] T4. Ensamblaje del episodio desde el contexto firmado, el resultado nativo y la lectura;
      evidencia incompleta a cuarentena con sus causas. (RF-1, RF-3, RF-4, RF-9)
      Hecho cuando: `pytest -q tests/test_digital_twin_capture.py tests/test_native_project_gate.py`
      en verde.
- [ ] T5. Lectura nativa de solo lectura tras la reapertura: identidades estables, componentes
      conexas, frontera y orientación de cada red, huella GPS del enlace, resultados con unidades;
      `reopen_verified` solo en una sesión nueva. (RF-2, RF-3, RF-27, RF-28)
      Hecho cuando: `pytest -q tests/test_digital_twin_snapshot_pf.py` en verde con `fake_pf`.
- [ ] T6. Enganche web tras cada acción nativa (flujo, cargas, ajuste, verificación, obras,
      estudios, transferencia, guiones) con un solo punto de integración; fallo de captura a
      cuarentena sin tocar la acción; cancelación y tiempo agotado. (RF-1)
      Hecho cuando: `pytest -q tests/test_digital_twin_integration.py tests/test_pf_arnes.py
      tests/test_pf_servidor.py` en verde.
- [ ] T7. Consulta: rutas de la API (lista y detalle, con la autorización de vínculos de la spec
      018) y herramienta `tools/digital_twin_buffer.py` (`list`, `show`, `validate`,
      `rebuild-index`, `register`). (RF-8)
      Hecho cuando: `pytest -q tests/test_digital_twin_web.py tests/test_digital_twin_buffer_cli.py
      tests/test_inventario.py` en verde.
- [ ] T8. Caso dorado IN111–TA225: fixture saneado, prueba sin licencia y aceptación nativa de
      solo lectura en dos procesos; clase `converged_with_violations` por ser «Con proyecto»;
      comandos en `docs/MANUAL_COMANDOS.md`. (RF-24, RF-25, RF-26, RF-27)
      Hecho cuando: `pytest -q tests/test_digital_twin_in111_ta225.py` en verde y la aceptación
      en DIgSILENT sale con código 0 y `reopen_verified=true`.
- [ ] T9. Validación de esta entrega: RF-1 a RF-10 y RF-24 a RF-32 citados por pruebas en
      verde; RF-11 a RF-23 y RF-33 a RF-38 quedan para sus planes; suite completa con las siete
      variables y ninguna omitida; inventario de episodios por clase y caso. (Todos los de esta
      entrega)
      Hecho cuando: `grep -rnoE "024:RF-[0-9]+" tests | sort -u` lista los RF de esta entrega.
