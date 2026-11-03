# Tareas — Spec 073

- [ ] T1 Ventana de valle desde la medición, por alcance. (RF-1, RF-2, RF-3, RF-4, RF-5, RF-6, RF-7, RF-8, RF-9, RF-10, RF-11, RF-34)
      Hecho cuando: `pytest -q tests/test_valle.py -k ventana` en verde, con curvas sorteadas.
- [ ] T2 Contrato de la calibración a valle en su propio caso. (RF-13, RF-14, RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_valle.py -k calibracion` en verde, con el doble de DIgSILENT.
- [ ] T3 Escalera y oráculo: valle en la elección y número de módulos. (RF-17, RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-27)
      Hecho cuando: `pytest -q tests/test_valle.py -k escalera` en verde, con el caso «la máxima cumple con bancos y el valle no».
- [ ] T4 El guion de la evaluación mide en valle sin dejar nada. (RF-25, RF-26)
      Hecho cuando: `pytest -q tests/test_valle.py -k guion` en verde, con el doble de DIgSILENT.
- [ ] T5 PIDE: el banco que el valle no admite no se propone. (RF-28, RF-29)
      Hecho cuando: `pytest -q tests/test_valle.py -k pide` en verde.
- [ ] T6 Informe y compatibilidad. (RF-12, RF-30, RF-31, RF-32)
      Hecho cuando: `pytest -q tests/test_valle.py -k informe` en verde.
- [ ] T7 Entrada para el pronóstico, sin sustituir a la medición. (RF-33)
      Hecho cuando: `pytest -q tests/test_valle.py -k pronostico` en verde.
- [ ] T8 [DIgSILENT] Calibrar a valle en «Valle <año>» y correr la escalera con esos puntos, sobre un proyecto de prueba de la sesión.
      Hecho cuando: el flujo a valle cuadra con la cabecera medida (`m:Psum`, memoria iopt-lev), la máxima sigue idéntica, y la tensión del oráculo y la de DIgSILENT quedan comparadas con una variante de bancos.
- [ ] T9 Alimentador con central: el valle con su curva de demanda, `curva_de_demanda`, en vez de dejarlo sin comprobar.
      Hecho cuando: una prueba con una central da su valle por la demanda, no por la cabecera.
