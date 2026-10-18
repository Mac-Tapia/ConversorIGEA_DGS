# Tareas — Spec 019

- [x] T1. `pf_arnes.turno_del_motor` y su prueba. (RF-1, RF-2, RF-4, RF-13)
      Hecho cuando: `pytest -q tests/test_pf_arnes.py` en verde.
- [x] T2. `pf_arnes.abrir` y `caso_restituido`; los 13 guiones lo usan; prueba de fuentes.
      (RF-3, RF-5, RF-6, RF-10)
      Hecho cuando: `pytest -q tests/test_pf_arnes.py tests/test_inventario.py` y las de los
      guiones en verde.
- [x] T3. Obra `consigna` y registro de validadores. (RF-11, RF-12)
      Hecho cuando: `pytest -q tests/test_obras_pf.py tests/test_obras_pf_guion.py` en verde.
- [x] T4. `tools/pf_servidor.py` y su uso desde la web. (RF-7, RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_pf_servidor.py` y las de la web en verde.
- [x] T5. Prueba en DIgSILENT real: dos guiones a la vez, tres órdenes con una activación,
      consigna de cabecera en CA101. (Todos)
- [x] T6. Validación: cada RF citado por al menos una prueba. (Todos)
- [ ] T7. El servidor ocioso cede el turno, salida sin búfer y la API de DIgSILENT buscada
      en su instalación. (RF-14, RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_pf_arnes.py tests/test_pf_servidor.py` en verde y
      una sonda suelta entra con el servidor ocioso sin esperar su inactividad.

Resultado de T5 (2026-10-15, DIgSILENT real con CA101): tres órdenes `verificar_pf.py`
por el servidor, 27 s la primera (conectar y activar) y 0 y 1 s las siguientes, sin volver
a activar; un `verificar_pf.py` directo a la vez esperó diciendo «ocupado por
pf_servidor.py» y entró cuando el servidor se cerró solo a los 120 s sin órdenes; la obra
`consigna` 1,05 p.u. quedó en `Obra_consigna_CA101`, solo en «Con proyecto», converge y
«Sin proyecto» sin diferencias.
