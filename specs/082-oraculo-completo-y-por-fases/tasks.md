# Tareas — Spec 082

- [x] T1. Nada fuera de la red: tramos imposibles, nodos sin definir, maniobras, bancos y recuento. (RF-1, RF-2, RF-3, RF-4, RF-12)
      Hecho cuando: `pytest tests/test_oraculo_por_fases.py tests/test_oraculo.py` pasa.
- [x] T2. Veredicto por fases, comparación y convergencia falsa, también en la red unida y la corrección. (RF-5, RF-6, RF-7, RF-8, RF-9, RF-10, RF-11)
      Hecho cuando: `pytest tests/test_oraculo_por_fases.py tests/test_oraculo_corrige.py` pasa.
- [x] T3. Comprobación permanente en `docs/regresiones/` al rebasar sobre `integracion/065`. (RF-13)
      Hecho cuando: `pytest tests/test_regresiones.py tests/test_oraculo_por_fases.py` pasa con la ficha.
- [x] T4. [DIgSILENT] Contraste con el flujo desequilibrado y Caso base de TI01 y C+æ02 reimportados. (RF-14)
      Hecho cuando: el error medio de tensión es de 0,5 puntos o menos en los dos, con evidencia en `D:/BaseDatosVNRGIS/evidencia`.
      Medido el 2026-11-03: TI01 cumple (+0,00 puntos; 6,472 frente a 6,473 MW). C+æ02 no: +0,92 puntos con su demanda nueva, Vmin 0,789 en DIgSILENT y 0,804 aquí. Causa medida en DIgSILENT: los 3 reguladores consumen 0,23 Mvar y 24 kW con la impedancia que DIgSILENT da por defecto a su `TypVoltreg`, y el oráculo los calcula sin impedancia (transformadores: 0,443 frente a 0,447 Mvar; cabecera: 1,44 frente a 1,13 Mvar). Corregido con la T6. Medida final, reimportado: C+æ02 −0,00 puntos de media (7,563 frente a 7,562 MW), máximo 4,8 puntos en la BT de una SED bifásica, Vmin 0,7987 en DIgSILENT y 0,8023 aquí. TI01, sin reguladores ni cambio de demanda, +0,00.
- [x] T6. Reguladores con su impedancia serie en el oráculo, sin cambiar el DGS. (RF-15)
      Hecho cuando: `pytest tests/test_oraculo_por_fases.py` pasa.
