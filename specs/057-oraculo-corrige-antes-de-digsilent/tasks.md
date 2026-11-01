# Tareas — Spec 057

- [x] T1. Detección de la demanda de relleno o fuera de escala y su corrección por kVA. (RF-2, RF-3)
      Hecho cuando: las pruebas que citan 057:RF-2 y 057:RF-3 pasan.
- [x] T2. El oráculo busca el factor y `aplicar_reglas` lo aplica e informa. (RF-1, RF-4)
      Hecho cuando: las pruebas que citan 057:RF-1 y 057:RF-4 pasan y el DGS es el mismo con
      `workers=1` y `workers>1`.
- [x] T3. La importación deja fuera lo que el oráculo no logra converger. (RF-5, RF-6)
      Hecho cuando: las pruebas que citan 057:RF-5 y 057:RF-6 pasan.
- [x] T4. [DIgSILENT] NJA202 de Electro Oriente por la web con el «Caso base» convergido. (Todos)
      Hecho cuando: se cumple su criterio de finalización.
      Hecho el 2026-11-01: NJA202 por la web; el oráculo corrigió la demanda de relleno (33 111 →
      6 921 kW) y el «Caso base» quedó VERIFICADO con su flujo; también 0205.
