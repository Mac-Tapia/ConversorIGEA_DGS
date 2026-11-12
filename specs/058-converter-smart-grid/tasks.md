# Tareas — Spec 058

- [x] T1. Paquete `convertersmartgrid` y comandos nuevos. (RF-2)
      Hecho cuando: la suite sintética pasa importando `convertersmartgrid`.
- [x] T2. Variables `CSG_*`. (RF-3)
      Hecho cuando: las pruebas que citan 058:RF-3 pasan.
- [x] T3. Textos visibles, sigla de proyecto, carpeta por defecto y skills. (RF-1, RF-4, RF-5, RF-7)
      Hecho cuando: las pruebas que citan sus RF pasan.
- [x] T4. Prueba de que nada menciona IGEA fuera de las excepciones. (RF-8, RF-9)
      Hecho cuando: `tests/test_nombre_converter_smart_grid.py` pasa.
- [x] T5. Líneas base regeneradas solo por la cabecera y suite completa sin omitidas. (RF-10)
      Hecho cuando: la suite completa con las nueve variables pasa con `-rs` sin omitidas.
      Evidencia: suite completa del 2026-11-12 sobre 6306cc65 con las doce variables de datos reales y `-rs`: 8 682 aprobadas, 0 fallidas, 0 omitidas (59 min; `.git/puerta_calidad/6306cc65….json`).
- [ ] T6. Carpeta principal `ConverterSmartGrid`, `.venv`, acceso directo y espacios. (RF-6)
      Hecho cuando: la web abre desde el acceso directo nuevo con los espacios de antes.
- [x] T7. [DIgSILENT] Un alimentador importado por la web con el nombre nuevo. (RF-4, RF-5)
      Hecho cuando: se cumple su criterio de finalización.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
