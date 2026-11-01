# Tareas — Spec 051

- [x] T1. Lectura del libro ancho y de las máximas mensuales, y escritura. (RF-1 a RF-7, RF-9 a RF-11)
      Hecho cuando: `pytest -q tests/test_cabecera_ancha.py` en verde.
      Hecho el 2026-11-01: 7 pruebas con libros sintéticos de la forma de los de Electro Oriente.
- [x] T2. Herramienta `tools/cabecera_ancha.py`. (RF-8)
      Hecho cuando: responde a `--help` y escribe los libros de un perfil sintético.
      Hecho el 2026-11-01. Con los reales: NJA202, 35 136 registros de 2024, máxima 6 512 kW y
      2 136 kVAR el 2024-11-08 15:30; R5, 7 máximas mensuales (2021-04 a 2022-01), la mayor
      5 040 kW. El lector de la calibración los lee sin cambios (NJA202 6 512 kW en 2024; R205,
      por R5, 4 920 kW en 2022-01).
- [ ] T3. [DIgSILENT] NJA202 y R205 de Electro Oriente convertidos, importados y calibrados por
      la web, en un espacio propio. (Todos)
      Hecho cuando: cada uno con su cabecera dentro del 1 % (R205 solo en activa).
