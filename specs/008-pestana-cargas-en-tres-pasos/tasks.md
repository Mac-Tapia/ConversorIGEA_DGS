# Tareas — Spec 008

- [x] T1. Guiones: error inesperado → informe con `error`. (RF-17)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_cargas_pf_guion.py` en verde.
- [x] T2. `tools/verificar_pf.py` y `services.pf_verificar` con su endpoint. (RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_verificar_pf.py tests/test_cargas_pf_web.py` en verde.
- [x] T3. Ajuste de varios alimentadores en un trabajo. (RF-10, RF-12 a RF-15)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_web.py` en verde.
- [x] T4. Carga del formulario delante de las del libro. (RF-24)
      Hecho cuando: `pytest -q tests/test_cargas_pf_web.py` en verde.
- [x] T5. Interfaz en tres pasos. (RF-1 a RF-9, RF-11, RF-16, RF-20 a RF-23)
      Hecho cuando: `pytest -q tests/test_cargas_tres_pasos_front.py tests/test_cargas_pf_front.py
      tests/test_demanda_medida_front.py`, `npx tsc --noEmit -p .` y `npm run build` correctos.
- [x] T6. Validación: `grep -rnoE "008:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-24; suite completa.
- [ ] T7. Prueba real en DIgSILENT con un proyecto de dos alimentadores, a cargo del usuario.
