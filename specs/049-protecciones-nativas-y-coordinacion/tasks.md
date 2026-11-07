# Tareas — Spec 049

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Disponibilidad real e inventario de entradas. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_datos.py tests/test_estudios_pf.py tests/test_datos_empresa.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Escenarios de falla y captura nativa. (RF-4, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_pf_guion.py tests/test_protecciones_datos.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Coordinación, reporte y web. (RF-5, RF-6, RF-7, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_coordinacion.py tests/test_protecciones_web.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4 [DIgSILENT]. Validación y persistencia de protecciones en PowerFactory. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_nativas.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando, resultado, informe y
limitaciones; no marcar casillas por existir código o por una simulación que solo converge.

T1 (RF-1 a RF-3), 2026-11-06, rama del worktree `agent-aeb4c1fac69ae0f98` sobre `1c22f85b`. Sin
DIgSILENT ni GPU; sintéticas sorteadas.

- `src/convertersmartgrid/protecciones.py`: `disponibilidad_protecciones` (disponible, faltan, bloqueos,
  alcance, criterios), `validar_dispositivo`, `es_fila_por_defecto`, `inventario_protecciones`,
  `criterios_de_perfil`. Contrato en `schemas/protecciones_v1.schema.json`.
- La referencia de Python de PF 2024 (`PythonReference_en.pdf`, 5.4.33) documenta `ComProtgraphic` solo
  para refrescar páginas de gráficos: no se toma como prueba de coordinación. Las órdenes exigidas son
  `ComShc` y `ComShctrace` (5.4.43, 5.4.44), con sus métodos documentados.
- Libro de la empresa: hoja «Protecciones» (`datos_empresa.py`) con procedencia por fila; perfil:
  `protecciones.cti_s`, `factor_sensibilidad`, `margen_poder_corte` (esquema, plantilla, guía), sin valor
  de referencia. El catálogo de estudios lista las protecciones con la lista concreta de lo que falta.
- `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_datos.py tests/test_estudios_pf.py
  tests/test_datos_empresa.py`: 56 aprobadas, 0 omitidas. Regresiones de los módulos tocados:
  `tests/test_entrega_universal.py tests/test_asistente_maestro.py` (282 aprobadas con las anteriores),
  `tests/test_inventario.py tests/test_arquitectura_generada.py tests/test_perfil_empresa.py` en verde.
- Limitación: hoy ninguna fuente trae dispositivos ni impedancia real de cabecera, así que el resultado en
  cualquier proyecto es «bloqueado» con la lista; eso es lo esperado (RF-2), no un fallo.

