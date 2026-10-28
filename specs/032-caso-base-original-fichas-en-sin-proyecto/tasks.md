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
- [ ] T9. Prueba en DIgSILENT desde la web con un sistema entero (conversión nueva):
      «Caso base» con los kVA y conductores del archivo y verificación sin diferencias;
      «Sin proyecto» con `Fichas_` y `SED_NTP_` grabadas, informe de conductores y propuesta.
      (Todos)
      Hecho cuando: `tools/sistema_web.py` termina válido y el escaneo muestra las dos
      variaciones solo fuera del «Caso base».
- [ ] T10. Validación: cada RF citado por al menos una prueba y en verde; suite con las
      siete variables, `-rs`, ninguna omitida; `CODIGO_FUENTE.md`, tabla de `CLAUDE.md` y
      nota en la 020. (Todos)
      Hecho cuando: `grep -rnoE "032:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-28.
