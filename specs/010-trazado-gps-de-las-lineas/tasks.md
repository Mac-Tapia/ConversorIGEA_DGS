# Tareas — Spec 010

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Tabla `Matrix` en el perfil y trazado de cada línea en `write_dgs`. (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_trazado_gps.py` en verde.
- [x] T2. El validador acepta el FID repetido de `Matrix` y compara el trazado releído con la geografía. (RF-5)
      Hecho cuando: `pytest -q tests/test_trazado_gps.py tests/test_validate*.py` en verde.
- [x] T3. La aceptación en PowerFactory compara el trazado de las líneas con el manifiesto. (RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_powerfactory_gate.py` en verde.
- [x] T4. 001:RF-14 anota la excepción y se regenera `output/linea_base_001.json`.
      Hecho cuando: `pytest -q tests/test_linea_base_001.py` en verde con las tres `CSG_*`.
- [x] T5. Prueba real: red unida NA293 + NA295 importada en PowerFactory con `--manifest`. (RF-6, RF-7)
      Hecho cuando: el informe da 0 líneas con trazado distinto del manifiesto.
- [x] T6. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "010:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-8.
      Ampliada el 2026-11-14 con RF-8 (H14): `tests/test_geography_v21.py` en rojo con el `_seq` anterior.
      Abierta hasta el verde integrado de RF-8: `tests/test_geography_v21.py` entero, con los TXT reales
      y sin pruebas omitidas, en la puerta de integración (auditor 3e, 2026-11-14).
      RF y sus pruebas (una por RF; todas en el mapa `D:/csg/PM_IMPL/PISTA3/MARCAS-PISTA3/mapa_T_RF_pruebas.tsv`):
      RF-1: `tests/test_geography_v21.py::test_seqnumber_entero_escrito_con_decimal_se_ordena_por_su_numero` (línea 98).
      RF-2: `tests/test_trazado_gps.py::test_los_extremos_son_el_gps_de_las_barras` (línea 86).
      RF-3: `tests/test_trazado_gps.py::test_sin_georreferenciacion_no_hay_trazado` (línea 113).
      RF-4: `tests/test_trazado_gps.py::test_la_red_unida_lleva_el_trazado_de_todas_sus_lineas` (línea 123).
      RF-5: `tests/test_trazado_gps.py::test_el_validador_detecta_un_trazado_alterado` (línea 137).
      RF-6: `tests/test_powerfactory_gate.py::test_la_aceptacion_compara_el_trazado_de_cada_linea_con_el_manifiesto` (línea 573).
      RF-7: `tests/test_hoja_y_coordenadas.py::test_cabecera_de_conectores_ensanchada_es_valida` (línea 226).
      RF-8: `tests/test_geography_v21.py::test_el_aviso_del_seqnumber_llega_a_la_validacion_de_la_geografia` (línea 107).
      Hecho el 2026-11-15 (MARCAS-PISTA3): `git grep -hoE "010:RF-[0-9]+" e182c823 -- tests` lista RF-1 a RF-8; rojo de RF-8 en
      `D:/csg/INTEGRA_F9/h14_rojo.log`; verde integrado: suite entera sobre el árbol de e182c823 con las 14 variables CSG_*: `D:/csg/INTEGRA_54/g107/integra_g12f13_82_183656.log` (línea 1202) «Puerta de calidad: 9582 pruebas, 0 fallidas, 0 omitidas.» con CSG_RED (los TXT reales).
