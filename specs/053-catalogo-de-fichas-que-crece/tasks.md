# Tareas — Spec 053

- [x] T1. Deducción y crecimiento del catálogo. (RF-1 a RF-8)
      Hecho cuando: `pytest -q tests/test_catalogo_crece.py` en verde.
      Hecho el 2026-11-01: 6 pruebas. Sobre una copia del catálogo real, los seis códigos de
      Electro Oriente: AS035/AS050/AS070 de N2XSY de su sección con ρAl/ρCu (AS050: 0,634 Ω/km
      frente a 0,641 de la IEC 60228), CS035 del N2XSY 3-1×35, AA240 de la ficha universal del
      AAAC (0,1414 Ω/km) y N2300 del N2XSY 3-1×120 por la relación de secciones.
- [x] T2. [DIgSILENT] NJA202 y R205 de Electro Oriente reconvertidos por la web sin ningún tramo
      de impedancia nula. (Todos)
      Hecho cuando: el oráculo previo no da «impedancia_nula» y el flujo converge sin rebajar
      la demanda del «Caso base».
      Hecho el 2026-11-01: NJA202 y 0205 reconvertidos por la web; Caso base VERIFICADO con flujo y
      calibración VÁLIDA sin rebajar la demanda.

- [x] T3. La carga reconstruye los conductores sin impedancia y lo dice por alimentador. (RF-9)
      Hecho cuando: las pruebas que citan 053:RF-9 pasan y los 22 alimentadores de Electro Oriente
      salen listos al cargar en la web.
      Hecho el 2026-11-01: familias AP, CP, NA, EC, NY e YC por equivalencia y filas pendientes
      rellenadas; los 168 alimentadores de Electro Oriente, listos al cargar en la web.
