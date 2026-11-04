# Tareas — Spec 002

Pendientes de aprobar el plan. Una tarea cada vez; cada una deja la suite en verde con
las tres variables `CSG_*` y la línea base de DGS idéntica (RF-20).

T1 y T5 se adelantaron el 2026-10-12 a petición del usuario («siempre debe ser universal;
Electro Dunas es un ejemplo de aplicación para pruebas»): no dependen de las capas. La
línea base con el perfil `electro_dunas` es idéntica a la de antes en TXT, red unida y
Access.

- [x] T1. Línea base de DGS con `tools/linea_base_dgs.py`, que guarda los SHA-256 en
      `output/linea_base_001.json` (fuera de git); añadirle la vía MDB y `workers=4`. (RF-20)
      Del 2026-10-28: la vía MDB en su propia línea base, `output/linea_base_001_mdb.json`,
      generada con `--mdb` sola; la herramienta rechaza TXT y MDB en una misma orden.
      Hecho cuando: `pytest -q tests/test_linea_base_001.py`, con las variables `CSG_*`, en verde.
- [x] T2. `tests/test_capas.py` y la tabla módulo → capa en `pyproject.toml`, con las
      excepciones medidas del plan. (RF-2 a RF-5)
      Hecho cuando: `pytest -q tests/test_capas.py` en verde y una violación nueva lo pone en rojo.
      Del 2026-11-03: lo cumplió la 065 con `tools/arquitectura.py` y el registro `docs/implementacion065/deuda_arquitectura.json`;
      `test_violacion_deliberada_en_modulos_arbitrarios` es la violación nueva que pone la prueba en rojo.
- [x] T3. Romper los 5 ciclos. (RF-4)
      Hecho cuando: la lista de ciclos permitidos de `test_capas.py` está vacía.
      Del 2026-11-03: eran 24 aristas en 8 grupos al medir de nuevo; `test_no_quedan_ciclos_entre_modulos` lo fija.
- [x] T4. Quitar las 12 importaciones de nombres privados. (RF-5)
      Hecho cuando: la lista de privados permitidos está vacía.
      Del 2026-11-03: eran 36 al medir de nuevo, no 12; pasan a nombres públicos y `test_no_quedan_nombres_privados_entre_modulos` lo fija.
- [x] T5. Perfil de empresa: CRS, patrón de SED de medición, escala y forma del
      alimentador; perfil de Electro Dunas; pedir el CRS si falta; manifiesto. (RF-31 a RF-37)
      Hecho cuando: `pytest -q tests/test_perfil_empresa.py` en verde y `git grep EPSG:32718 -- src tools`
      solo encuentra el perfil.
- [x] T6. Puertos, registro de módulos por entry points y lista de permitidos. (RF-7 a RF-15, RF-23 a RF-30)
      Hecho cuando: `pytest -q tests/test_modulos.py` en verde.
      Del 2026-11-03: `puertos.py`, `registro_modulos.py` y `escritores.py`. Tras integrar hay que ejecutar
      `pip install -e .`: hasta entonces la prueba de RF-28 falla y pide esa orden, como manda el requisito.
      La conversión aún crea sus lectores con `sources.adapter_for` y su DGS con `write_dgs`; el registro los declara
      y los carga, y el paso de la conversión al registro se hace con T7, cuando se muevan esos módulos.
Plan de lo abierto (2026-11-03): T7 a T9 mueven 250 módulos y tocan casi todas las pruebas, `tools/` y los
guiones de PowerFactory; van por capas, de abajo arriba, una por commit y con la línea base en cada una. T8 y T9
van después de T7. T11 reordena `frontend/src` y pide probar la web en el navegador real. T12 es el cierre.

- [ ] T7. Mover los módulos a `dominio`, `puertos`, `aplicacion`, `adaptadores` y
      `presentacion`, con reexportaciones temporales. (RF-1)
      Hecho cuando: la tabla de `pyproject.toml` es la del plan y `test_capas.py` en verde sin excepciones de capa.
- [ ] T8. `vnr_etl` dentro de `convertersmartgrid.adaptadores.entrada.vnr`; `vnr-etl` sigue igual. (RF-6, RF-22)
      Hecho cuando: no queda `src/vnr_etl/` y `pytest -q tests/test_vnr_etl.py` en verde.
- [ ] T9. Retirar las reexportaciones; `tools/` y las pruebas usan las rutas nuevas. (RF-21)
      Hecho cuando: `test_capas.py` no encuentra ningún módulo que solo reexporte.
- [x] T10. Modelos Pydantic en las respuestas de la API y tipos del front generados. (RF-16, RF-17)
      Hecho cuando: `pytest -q tests/test_contrato_api.py` en verde.
      Del 2026-11-03: lo cumplió la 065. Quedan 7 de 133 rutas de `/api` sin modelo de respuesta; salen como tipo abierto.
- [ ] T11. `frontend/src` en `api/`, `shared/`, `features/` y `app/`, con la regla de fronteras. (RF-18, RF-19)
      Hecho cuando: `npm run lint`, `npx tsc --noEmit -p .` y `npm run build` correctos.
- [ ] T12. Validación: `grep -rnoE "002:RF-[0-9]+" tests frontend | sort -u` lista RF-1 a RF-37;
      línea base idéntica; `CODIGO_FUENTE.md` con las rutas nuevas.
      Hecho cuando: `grep -rnoE "002:RF-[0-9]+" tests frontend | sort -u` lista RF-1 a RF-37 y la línea base de la 001 sigue idéntica.
