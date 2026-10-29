# Tareas — Spec 032

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. «Caso base» sin SED redimensionadas ni fichas al convertir: `REGLAS_PROYECTO`
      sin `redimensionar_sed`, `aplicar_fichas=False`; `batch`, web y CLI sin
      `catalog_corrections`; Registro sin «SED redimensionada». Pruebas existentes
      ajustadas. (RF-1, RF-2, RF-5, RF-6)
      Hecho cuando: `pytest -q tests/test_caso_base_original.py tests/test_catalog.py
      tests/test_puentes.py` en verde, con las dos disposiciones y `workers=1`/`>1`.
- [x] T2. Conductores completados con el catálogo, anotados con fuente y tramos en el
      manifiesto y el Registro. (RF-3, RF-4)
      Hecho cuando: prueba sintética con un código sin fila en el BD_Equipo en verde.
- [x] T3. Verificación del «Caso base» frente a la entrada sin corregir y escalado de la
      demanda si no converge. (RF-7, RF-26)
      Hecho cuando: pruebas de `capacidades` y de 015:RF-38 con un DGS de SED sobrecargada
      citan 032 y pasan.
- [x] T4. `fichas_para_pf` y `cambios_de_ficha` en `catalog.py`; `fichas_conductores` en
      el plan del ajuste. (RF-14, RF-16, RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_catalog.py tests/test_sistema_web.py` en verde.
- [x] T5. Variación `Fichas_<proyecto>` en el guion: tipos propios, `typ_id` reasignado,
      reutilización, operador grabando, informe. (RF-8 a RF-17)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T6. SED fijas y escaladas sobre el umbral, con nivel; `implementar_transformadores`
      en `SED_NTP_<proyecto>`. (RF-8, RF-12, RF-13, RF-20 a RF-25, RF-28)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_trafos_sed.py`
      en verde.
- [x] T7. Casos: las dos variaciones activas en «Sin/Con proyecto» y los del año,
      inactivas en «Caso base»; prefijos en `escaneo`. (RF-27)
      Hecho cuando: `pytest -q tests/test_casos_pf*.py tests/test_escaneo.py` en verde.
- [x] T8. Web: tabla de conductores con su ficha y nivel de cada SED en la propuesta;
      `npm run build`. (RF-17, RF-22, RF-28)
      Hecho cuando: el front compila y las pruebas de la API del ajuste pasan.
- [x] T9. Prueba en DIgSILENT desde la web con un sistema entero (conversión nueva):
      «Caso base» con los kVA y conductores del archivo y verificación sin diferencias;
      «Sin proyecto» con `Fichas_` y `SED_NTP_` grabadas, informe de conductores y propuesta.
      (Todos)
      Hecho cuando: `tools/sistema_web.py` termina válido y el escaneo muestra las dos
      variaciones solo fuera del «Caso base».
      Hecho el 2026-10-28 desde la web con la entrega 231026 (espacio 5f11283a33c94ea5), en
      dos alimentadores, porque ninguno trae las dos clases: SM218 (su único conductor,
      AA05001D, sin ficha) y CA101 convertido e importado de nuevo. Con «Implementar
      transformadores», SM218 válido a −0,29 % y CA101 a −0,01 % (sin ellos, CA101 solo
      convergía con iopt_lev: SE20701, 1 088 kW sobre 50 kVA, a 0,517 pu). Sonda de solo
      lectura en DIgSILENT: «Caso base» sin variaciones, TR_SE41054 1 × 85 kVA, TR_SE20701
      1 × 50 kVA y CU01603D con R 1,3488 Ω/km e In 112 A del archivo; «Sin proyecto» con
      `SED_NTP_` (2 × 630 y 3 × 630 kVA NTP 370.400) y, en CA101, `Fichas_` (48 cambios en
      15 conductores; CU01603D_FICHA, R 1,17 Ω/km, In 141 A). En la prueba salieron y se
      corrigieron las fijas tapadas por cambios a mano falsos (014:RF-10, commits 85f5efbc y 0e5ea1bd).
      El TXT de cargas trae demanda en 2 547 de sus 7 339 SED (154 541 kW) y 0 kW en el resto
      (SE41384: 0 kW, 125 kVA); el «Caso base» lleva la del archivo: SM218, 121 de 306 SED
      con demanda (6 788,5 kW) y 185 en cero; CA101, 67 de 171 (3 016,2 kW). Las que vienen en
      cero se quedan en cero (usuario, el mismo día: «dejarlo en cero»); la demanda de todas
      la pone la calibración en «Sin proyecto».
- [x] T11. Cambios a mano del operador sin bloqueo: con una variación suya grabando, las
      fichas y los transformadores se graban en su variación propia y la grabación vuelve a
      la del operador; los bancos que faltan apartan sus variaciones solo mientras se crean.
      (RF-12, RF-29)
      Hecho cuando: `pytest -q tests/test_caso_base_original.py tests/test_ajuste_proyecto_guion.py`
      en verde y en DIgSILENT SM218 calibra con una variación del operador grabando.
      Hecho el 2026-10-28 con CA101 (proyecto de la T9): con «Prueba_operador_032», vacía y
      grabando en «Sin proyecto», la recalibración por la web salió VÁLIDA (−0,01 %, 9 fijas)
      y la variación siguió activa y grabando; se borró al terminar.
- [ ] T10. Validación: cada RF citado por al menos una prueba y en verde; suite con las
      siete variables, `-rs`, ninguna omitida; `CODIGO_FUENTE.md`, tabla de `CLAUDE.md` y
      nota en la 020. (Todos)
      Hecho cuando: `grep -rnoE "032:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-29.
