# Tareas — Spec 024, primera entrega: búfer de episodios

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Contrato del episodio: clases (`accepted`, `converged_with_violations`, `rejected`,
      `counterfactual`, `quarantine`), caso (`caso_base`, `sin_proyecto`, `con_proyecto`),
      bloque de resultados del flujo (balance, pérdidas, cargabilidad, tensiones, confiabilidad
      con ausentes explícitos), campos del PIDE de cada obra, JSON canónico, SHA-256 y validación
      con la ruta del campo que falla; esquema JSON. (RF-1, RF-2, RF-7, RF-28, RF-32)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_digital_twin_episode.py`
      en verde.
      Hecho el 2026-10-21.
- [x] T2. Búfer inmutable: objeto atómico por huella, idempotente, colisión detectada, índice
      SQLite con consultas por proyecto, alimentador, caso, clase, acción y versión de
      PowerFactory, reconstrucción del índice y cuarentena de manifiestos corruptos.
      (RF-6, RF-7, RF-8, RF-9, RF-10)
      Hecho cuando: `pytest -q tests/test_digital_twin_buffer.py` en verde.
      Hecho el 2026-10-22.
- [x] T3. Evaluación por caso: «Caso base» y «Sin proyecto» con violaciones como diagnóstico;
      «Sin proyecto» aceptado solo si la calibración cuadra; «Con proyecto» contra la norma de su
      sistema (NTCSE/NTCSER del perfil), pérdidas y confiabilidad frente a «Sin proyecto»;
      cuarentena sin tolerancia NTCSER o sin «Sin proyecto» de referencia; revertido o sin
      reapertura nunca `accepted`. (RF-4, RF-5, RF-29, RF-30, RF-31)
      Hecho cuando: `pytest -q tests/test_digital_twin_evaluacion.py` en verde.
      Hecho el 2026-10-22; en «Con proyecto», si ya incumple la norma es violación aunque falte «Sin proyecto» (solo la aceptación lo necesita), y las barras a 0 p.u. son islas sin fuente, no subtensión (visto en DIgSILENT).
- [x] T4. Ensamblaje del episodio desde el contexto firmado, el resultado nativo y la lectura;
      evidencia incompleta a cuarentena con sus causas. (RF-1, RF-3, RF-4, RF-9)
      Hecho cuando: `pytest -q tests/test_digital_twin_capture.py tests/test_native_project_gate.py`
      en verde.
      Hecho el 2026-10-22.
- [x] T5. Lectura nativa de solo lectura tras la reapertura: identidades estables, componentes
      conexas, frontera y orientación de cada red, huella GPS del enlace, resultados con unidades;
      `reopen_verified` solo en una sesión nueva. (RF-2, RF-3, RF-27, RF-28)
      Hecho cuando: `pytest -q tests/test_digital_twin_snapshot_pf.py` en verde con `fake_pf`.
      Hecho el 2026-10-22: reabre el proyecto, nombre y kV por barra, estados pedidos (los seccionadores son StaSwitch o líneas), barras sin tensión aparte.
- [x] T6. Enganche web tras cada acción nativa (flujo, cargas, ajuste, verificación, obras,
      estudios, transferencia, guiones) con un solo punto de integración; fallo de captura a
      cuarentena sin tocar la acción; cancelación y tiempo agotado. (RF-1)
      Hecho cuando: `pytest -q tests/test_digital_twin_integration.py tests/test_pf_arnes.py
      tests/test_pf_servidor.py` en verde.
      Hecho el 2026-10-22: `_gemelo` en cargas, ajuste, verificación del «Caso base», obras, estudios (flujo), transferencia y guiones; solo lo aplicado; `IGEA_TWIN_CAPTURA=0` lo apaga en las pruebas.
- [x] T7. Consulta: rutas de la API (lista y detalle, con la autorización de vínculos de la spec
      018) y herramienta `tools/digital_twin_buffer.py` (`list`, `show`, `validate`,
      `rebuild-index`, `register`). (RF-8)
      Hecho cuando: `pytest -q tests/test_digital_twin_web.py
      tests/test_inventario.py` en verde.
      Hecho el 2026-10-22.
- [x] T8. Caso dorado IN111–TA225: fixture saneado, prueba sin licencia y aceptación nativa de
      solo lectura en dos procesos; clase `converged_with_violations` por ser «Con proyecto»;
      comandos en `docs/MANUAL_COMANDOS.md`. (RF-24, RF-25, RF-26, RF-27)
      Hecho cuando: `pytest -q tests/test_digital_twin_in111_ta225.py` en verde y la aceptación
      en DIgSILENT sale con código 0 y `reopen_verified=true`.
      Hecho el 2026-10-22: probado en DIgSILENT, 11 de 11 comprobaciones (3091 a 0,95227 p.u., 3092 a 0,96043, mínima 0,86833 en SE41154_BT, `converged_with_violations`). Antes hubo que reactivar en «Con proyecto» las 13 variaciones de la obra: la sesión de Codex había dejado activa solo DT_6a2ebb58_12758e88 (las cinco DT_* siguen en el proyecto, inactivas).
- [x] T9. Validación de esta entrega: RF-1 a RF-10 y RF-24 a RF-32 citados por pruebas en
      verde; RF-11 a RF-23 y RF-33 a RF-38 quedan para sus planes; suite completa con las siete
      variables y ninguna omitida; inventario de episodios por clase y caso. (Todos los de esta
      entrega)
      Hecho cuando: `grep -rnoE "024:RF-[0-9]+" tests | sort -u` lista los RF de esta entrega.
      Hecho el 2026-10-22: RF-1 a RF-10 y RF-24 a RF-32 citados por pruebas en verde.

## Entregas siguientes (plan en plan.md, 2026-10-22)

- [x] T10. Generador de escenarios y aprendizaje activo en copias del proyecto, con presupuesto
      de licencia. (RF-11, RF-12, RF-40, RF-41)
      Hecho cuando: `pytest -q tests/test_digital_twin_escenarios.py en verde`.
      Hecho el 2026-10-22: probado en DIgSILENT desde la web con IN111–TA225, 24 escenarios en una copia
      borrada al terminar; el grafo trae los acopladores (sin ellos solo 91 de 2470 nodos tenían fuente).
- [x] T11. Oráculo PINN/GNN del estado eléctrico con incertidumbre, entrenamiento, registro y
      promoción automática con puertas; ordenar y proponer con el oráculo. (RF-13 a RF-19, RF-23,
      RF-35, RF-36, RF-38, RF-39, RF-42 a RF-44)
      Hecho cuando: `pytest -q tests/test_digital_twin_oraculo.py en verde, en GPU si la hay`.
      Pendiente (el usuario, 2026-10-22: «déjalo como pendiente para después»): código y pruebas en verde,
      solo en la GPU, híbrido barrido físico + GNN y modelo de carga elegido con los datos (impedancia
      constante en IN111–TA225: el barrido se aparta 0,019 p.u. frente a 0,050 con potencia constante).
      Con los 24 escenarios reales el modelo aún no pasa las puertas (0,057 p.u. sobre 0,005), así
      que no se usa; falta reentrenar con el modelo de carga elegido y más escenarios.
      Cerrada el 2026-10-24 con T15: la causa era el barrido radial (descartaba los 3 lazos) y los
      acopladores en el residuo físico. Con la física mallada, la potencia constante y el peso
      físico 10⁻⁴, el candidato 20261024-112255-dd63 pasó las puertas y quedó promovido: en la
      partición de prueba se aparta 0,00045 p.u. de DIgSILENT (la física sola, 0,0032).
- [x] T12. Gemelo temporal (RNN) con las curvas del mes y pseudo-medidas. (RF-20 a RF-22, RF-37)
      Hecho cuando: `pytest -q tests/test_digital_twin_temporal.py en verde`.
      Hecho el 2026-10-22: GRU en la GPU; pruebas con curvas sintéticas y la ruta de la web.
- [x] T13. Diagnóstico, mercado y plan por etapas de la norma del PIDE. (RF-49 a RF-53, RF-60 a
      RF-63)
      Hecho cuando: `pytest -q tests/test_pide.py tests/test_pide_pf.py en verde`.
      Hecho el 2026-10-22: probado en DIgSILENT con IN111–TA225 («Sin proyecto», años 00, 04 y 08 al 3 %
      de prueba): la mínima baja de 0,765 a 0,632 p.u. y el factor del `ComLdf` se restituye.
- [x] T14. Evaluación económica (art. 14, tarifas, tasa privada), priorización del art. 15,
      libro CAPEX y propuestas e implementación propias. (RF-33, RF-34, RF-45 a RF-48, RF-54 a
      RF-59)
      Hecho cuando: `pytest -q tests/test_pide_economia.py tests/test_pide_web.py en verde`.
      Hecho el 2026-10-22: pliego de Electro Dunas del 2026-10-04 y NTCSER en el perfil; bancos y ternas
      se aplican solos tras simularlos; el resto queda propuesto con su motivo.       Faltan en el perfil
      `crecimiento_demanda_anual`, `factor_carga` y `precio_compra_kwh`: sin ellos se avisa (RF-58e).

## Del 2026-10-24: física mallada, evolutivos y evaluación (RF-64 a RF-74)

- [x] T15. Flujo físico por matriz de admitancias con lazos (`digital_twin/flujo.py`,
      `ModeloMallado`), acopladores como una barra y residuo por barra eléctrica; la PINN lo usa
      como base y elige con él el modelo de carga; peso físico 10⁻⁴ elegido con los datos.
      (RF-64, RF-65, RF-66)
      Hecho cuando: `pytest -q tests/test_digital_twin_flujo.py tests/test_digital_twin_oraculo.py` en verde.
      Hecho el 2026-10-24: coincide con pandapower en redes con lazos; en IN111–TA225 la física
      sola se aparta 0,0032 p.u. (el barrido, 0,019) y la potencia constante es el modelo de carga.
- [x] T16. Algoritmo genético, NSGA-II y jDE (`digital_twin/evolutivo.py`); bancos con frente
      y sobredimensionadas, reconfiguración radial y consigna; bancos del PIDE afinados en la web
      con la red del gemelo (`services._pide_optimizar`). (RF-67 a RF-73)
      Hecho cuando: `pytest -q tests/test_digital_twin_evolutivo.py` en verde.
      Hecho el 2026-10-24.
- [x] T17. Evaluación del aprendizaje (`oraculo.evaluar`, `tools/digital_twin_entrenar.py --evaluar`). (RF-74)
      Hecho cuando: `pytest -q tests/test_digital_twin_oraculo.py` en verde y la evaluación con los
      episodios reales de IN111–TA225 dice el error de la partición de prueba.
- [x] T18. Retro (033, 2026-10-29): RF-47b, RF-47c, RF-58b a RF-58d, añadidos a la spec como cambio después de
      escribir las tareas e implementados con su prueba sin tarea propia. (RF-47b, RF-47c, RF-58b a RF-58d)
      Hecho cuando: las pruebas que los citan pasan (pruebas de `tests/test_pide_economia.py` y `tests/test_pide_web.py`).
