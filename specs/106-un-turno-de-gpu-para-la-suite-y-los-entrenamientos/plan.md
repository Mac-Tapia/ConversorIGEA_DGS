# Plan — Spec 106

- `src/convertersmartgrid/trabajadores_ml.py`: `turno_gpu_con_plazo` (espera, aviso cada minuto y error con el dueño) y
  `quien_tiene_la_gpu` (lee el JSON del turno). Reloj y espera inyectables para probar sin dormir. RF-2, RF-3.
- `tests/conftest.py`: al importarse, calcula la guardia de la máquina y redirige `CSG_ML_GPU_LOCK` a una de la sesión,
  antes que cualquier fixture de módulo; `pytest_collection_modifyitems` marca `gpu` por el texto del módulo (RF-6);
  `pytest_collection_finish` toma el turno solo si hay ítems `gpu` (RF-7), con plazo, y sale con
  `pytest.exit(..., returncode=SALIDA_SIN_TURNO_GPU)` si vence; `pytest_sessionfinish` lo suelta. Se mantiene el fixture
  por prueba de 102:RF-22. RF-1, RF-4.
- `tools/puerta_calidad.py`: el código 6 es un fallo con el dueño del turno (RF-8).
- Alternativa descartada: tomar el turno en `pytest_sessionstart`, para toda sesión con CUDA. La puerta de un commit
  sin pruebas de GPU esperaba hasta 2 h a cada clase de la T7 (auditoría del 2026-11-12).
- `pyproject.toml`: `faulthandler_timeout = 1800`. RF-5.
- Alternativa descartada: comprobar la memoria libre con `torch.cuda.mem_get_info` antes de cada prueba. No reserva
  nada: otro proceso puede llenarla justo después, y el asignador con caché de PyTorch no la devuelve (ver la spec).
- Pruebas: `tests/test_turno_gpu_de_la_suite.py`, con un proceso doble que tiene el turno
  (`test_experimentos_runner._guardia_en_otro_proceso`) y tiempo simulado.
