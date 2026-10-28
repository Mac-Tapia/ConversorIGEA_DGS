# Tareas — Spec 028

Estado: pedida por el usuario el 2026-10-28; T1 a T5 hechas el mismo día (`tests/test_escaneo.py`,
`test_ajuste_proyecto_guion.py -k segunda`, `test_sistema_web.py -k escanea`); falta T6 en DIgSILENT,
cuando el usuario ponga a mano la central de NA205.

- [x] T1. `escaneo.py`: origen por los prefijos del conversor, resumen y barra de la central.
      (RF-3, RF-4, RF-5, RF-7, RF-11, RF-12)
      Hecho cuando: `pytest -q tests/test_escaneo.py -k reglas` en verde con nombres sorteados.
- [x] T2. `tools/escanear_alimentador_pf.py`, de solo lectura, con `--help` sin DIgSILENT.
      (RF-1, RF-2, RF-4, RF-5, RF-6, RF-8)
      Hecho cuando: prueba con `fake_pf` en verde: generadores, bancos, variaciones y un
      alimentador que no está.
- [x] T3. Servicio, ruta y botón en la web; la central sin barra toma la del escaneo.
      (RF-9 a RF-12)
      Hecho cuando: prueba de la API y del front compilado en verde.
- [x] T4. Generador del operador en la barra de la central y sin bancos repetidos. (RF-13, RF-14)
      Hecho cuando: pruebas con `fake_pf` en verde.
- [x] T5. `tools/sistema_web.py` escanea antes de calibrar. (RF-15)
      Hecho cuando: prueba de `sistema_web` en verde.
- [ ] T6. Prueba en DIgSILENT: escanear Nasca con la central de NA205 puesta a mano por el
      usuario y recalibrar.
      Hecho cuando: el escaneo nombra el generador de NA205 y su barra, y la calibración lo usa.
