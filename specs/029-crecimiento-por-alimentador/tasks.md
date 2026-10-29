# Tareas — Spec 029

Estado: pedida por el usuario el 2026-10-28; plan corto en la propia tarea.

Plan: `src/igea_dgs/crecimiento.py` (máximas mensuales de cada curva, tasa compuesta entre los
meses comunes del primer y el último año, mediana para los demás; lectura de los libros por año
con `demanda_medida.maximas`, de nivel superior para `JobContext.en_proceso`); `pide_ejecutar`
la calcula si el perfil no trae tasa y la pasa a `tools/pide_pf.py` por alimentador, que escala el
`scale0` de las cargas de cada uno y lo devuelve al terminar.

- [x] T1. `crecimiento.py` y sus pruebas con curvas sorteadas. (RF-1 a RF-3, RF-5, RF-7)
      Hecho cuando: `pytest -q tests/test_crecimiento.py` en verde.
- [x] T2. Tasa por alimentador en `pide_ejecutar` y en `tools/pide_pf.py`. (RF-1, RF-4 a RF-6)
      Hecho cuando: prueba con `fake_pf` en verde (factor por alimentador y cargas restituidas).
- [x] T3. PIDE de Chincha en DIgSILENT con la tasa de cada alimentador.
      Hecho cuando: informe con la tasa y los años del horizonte diagnosticados.
      Hecho el 2026-10-28 en DIgSILENT desde la web (proyecto 20261028-103442_IGEA_SISTEMA_CHINCHA,
      pide_726af9acfd9c.json): tasa medida de PN107 +4,75 % y TM105 −2,86 %, mediana +0,94 % para
      los demás; años 0, 4, 8, 12, 16 y 20 diagnosticados. Cerrada el 2026-10-29 con esa evidencia.
