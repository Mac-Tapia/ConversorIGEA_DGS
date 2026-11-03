# Tareas 066

- [x] T1. Precio de compra del libro. (RF-3)
      Hecho cuando: `pytest -q tests/test_libro_perdidas_por_sistema.py -k precio` en verde.
- [x] T2. Plan de celdas desde el perfil. (RF-1, RF-2, RF-4, RF-5, RF-6, RF-8)
      Hecho cuando: `pytest -q tests/test_libro_informe.py` en verde.
- [x] T3. Excel aplica el plan y se comprueba el libro. (RF-7, RF-9, RF-10)
      Hecho cuando: `pytest -q tests/test_libro_informe.py` en verde.
- [x] T4. La web lo genera y lo ofrece en los dos informes. (RF-11, RF-12)
      Hecho cuando: `pytest -q tests/test_libro_informe.py -k web` en verde.
- [x] T8. Los datos de equipos que traiga el informe llenan su grupo y dejan de ser hueco. (RF-13)
      Hecho cuando: `pytest -q tests/test_libro_informe.py -k fichas` en verde.
      Hecho el 2026-11-02: lo usa el libro de Santa María, con cable y troncal de fichas y TC normalizado.
- [x] T7. [DIgSILENT] INKA'S BERRIES en SM218 desde el botón con su libro. (Todos)
      Hecho cuando: el libro sale sin avisos y sus importes son los del Word, con el precio del libro.
      Hecho el 2026-11-02, trabajo `659a33fbf842`: sin avisos; 0,2307 S/./kWh, 0,55 % y 0,30 % del libro; 314 994 y 368 209 S/.
      en el libro y en el Word. Quedan vacíos el transformador y la capacidad de los equipos, que no se calculan.
