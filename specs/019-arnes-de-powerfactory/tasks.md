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
- [x] T7. El servidor ocioso cede el turno, salida sin búfer y la API de DIgSILENT buscada
      en su instalación. (RF-14, RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_pf_arnes.py tests/test_pf_servidor.py` en verde y
      una sonda suelta entra con el servidor ocioso sin esperar su inactividad.
      2026-10-18, DIgSILENT real: tras una lectura de la web, la sonda pidió el cierre al
      servidor ocioso y entró a los 3 s (su inactividad es de 120 s), sin `PYTHONPATH`; la
      limpieza de Chincha conectó igual y escribió cada línea al momento.
- [x] T8. Órdenes huérfanas descartadas y reintento de «Leer proyectos». (RF-17, RF-18)
      Hecho cuando: `pytest -q tests/test_pf_servidor.py tests/test_carpeta_pf.py` en verde
      y «Leer proyectos» de la web lista los proyectos tras importar.
- [x] T9. Turno hasta la muerte del proceso, identidad por pid e inicio, corte dirigido,
      servidor fuera del árbol del cliente, registro con horas, cola limpia y relanzamiento.
      (RF-19 a RF-22)
      Hecho cuando: `pytest -q tests/test_pf_arnes.py tests/test_pf_servidor.py` en verde y,
      en DIgSILENT real, un proceso con DIgSILENT que sale y «Leer proyectos» seguidos
      desde la web sin error.
      2026-10-19, DIgSILENT real: una sonda activó CA101_PE104 y salió; «Leer proyectos»
      lanzado al instante esperó a que muriera, conectó en 27 s y listó los 17 proyectos
      (255 s la lectura), con cada paso y su hora en `servidor.log`.

Resultado de T5 (2026-10-15, DIgSILENT real con CA101): tres órdenes `verificar_pf.py`
por el servidor, 27 s la primera (conectar y activar) y 0 y 1 s las siguientes, sin volver
a activar; un `verificar_pf.py` directo a la vez esperó diciendo «ocupado por
pf_servidor.py» y entró cuando el servidor se cerró solo a los 120 s sin órdenes; la obra
`consigna` 1,05 p.u. quedó en `Obra_consigna_CA101`, solo en «Con proyecto», converge y
«Sin proyecto» sin diferencias.
