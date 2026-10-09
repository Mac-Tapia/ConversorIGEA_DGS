# Tareas — Spec 006

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. `src/igea_dgs/ajuste_cabecera.py`: objetivo, demandas fijas de los clientes y
      reparto inicial por kVA, con los modos «todo escala» y «solo kW». (RF-1, RF-3, RF-5,
      RF-6, RF-7, RF-8, RF-13, RF-14, RF-24)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_ajuste_cabecera.py` en verde.
- [x] T2. Cuadre: secante sobre `kp` y `kq`, tolerancia, último reparto que convergió y
      escalera de remedios, contra la red de juguete con pérdidas. (RF-11, RF-12, RF-16,
      RF-17, RF-18)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera.py` en verde, con un caso que
      cuadra en menos de 30 flujos y otro que agota los remedios.
- [x] T3. Doble de PowerFactory: `ElmTr2` con tipo, cubículo de cabecera del `ElmFeeder`,
      `ComLdf` que calcula la cabecera con pérdidas y falla por encima de un umbral, en
      `tests/fake_pf.py`. (apoyo de RF-4, RF-11, RF-15)
      Hecho cuando: `tests/test_cargas_pf_guion.py` sigue en verde con el doble ampliado.
- [x] T4. `tools/ajuste_cabecera_pf.py`: cargas y kVA del alimentador, simular, aplicar en
      variación nueva, medir la cabecera, diagnóstico, remedios con los ajustes del `ComLdf`
      restituidos, cancelación e informe. (RF-4, RF-9, RF-10, RF-15, RF-17 a RF-22, RF-24)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T5. Web: `services.ajuste_plan` (objetivo comprobado contra el trabajo de la máxima,
      clientes del alimentador, kVA de la entrada original) y `ajuste_ejecutar` como trabajo
      del carril `powerfactory`; endpoints y tolerancia validada entre 0,1 % y 10 %.
      (RF-1, RF-2, RF-3, RF-10, RF-19, RF-20, RF-24)
      Hecho cuando: `pytest -q tests/test_demanda_medida_web.py` en verde.
- [x] T6. Interfaz: elegir el medidor de la cabecera, tolerancia, «Simular» y «Ajustar en
      DIgSILENT» con el proyecto de la pestaña, y el informe por SED y del alimentador.
      (RF-2, RF-3, RF-20, RF-21, RF-23)
      Hecho cuando: `npx tsc --noEmit -p .` y `npm run build` en `frontend/` correctos.
- [x] T7. Validación: cada RF citado por al menos una prueba y en verde; suite completa. (Todos)
      Hecho cuando: `grep -rnoE "006:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-24.
- [ ] T8. Prueba real en DIgSILENT con un alimentador, a cargo del usuario: comprobar el
      signo y el lado de lo medido en la cabecera y que cuadra al 1 %.
