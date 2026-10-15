# Tareas — Spec 017

Estado: aprobadas (2026-10-15) · Fecha: 2026-10-15

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. `python-docx` en `requirements.txt` y `pyproject.toml`; `src/igea_dgs/informes.py`
      con `ConfigInforme` (clave `informes` del perfil) y la clave en
      `config/perfiles/electro_dunas.json` (bandas del modelo). (RF-4, RF-5, RF-13, RF-14,
      RF-115)
      Hecho cuando: `pytest -q tests/test_informes.py` en verde e índice al día.
- [x] T2. `informes.py`: `Caso`, `Etapa`, pérdidas anuales, factor de carga, etapa
      recomendada y veredicto de factibilidad. (RF-15 a RF-19, RF-31, RF-33, RF-34, RF-43,
      RF-54 a RF-60, RF-71, RF-72)
      Hecho cuando: las pérdidas de EMAPICA salen como en el modelo, en
      `tests/test_informes.py`.
- [x] T3. `informes.py`: redacción de análisis, conclusiones, antecedentes, descripción y
      transformador. (RF-20 a RF-22, RF-50, RF-107, RF-108, RF-121, RF-122)
      Hecho cuando: `pytest -q tests/test_informes.py` en verde.
- [ ] T4. Sonda en DIgSILENT (solo lectura, sobre un proyecto ya importado): exportar el
      diagrama geográfico de CA101 a PNG con el coloreado por tensión y restaurar el
      coloreado. Anotar en el plan qué llamadas sirven. (RF-10, RF-11, RF-116)
      Hecho cuando: hay un PNG legible a 150 ppp y el plan lo anota.
- [ ] T5. `src/igea_dgs/libros_informe.py`: libro de pérdidas y tabla de costes, y
      `config/costes_referenciales.example.json` con precios de la web y su fuente. (RF-39b a
      RF-39e, RF-40c, RF-61 a RF-64)
      Hecho cuando: `pytest -q tests/test_libros_informe.py` en verde.
      Estado 2026-10-15: libro de pérdidas hecho y probado; la tabla de costes queda para la
      evaluación económica (el usuario: en CA101 bancos fijos de 300 kvar en 10 kV y 450 kvar
      en 22,9 kV, sin costes).
- [x] T6. `src/igea_dgs/informe_docx.py`: los dos informes sobre un modelo base, con
      huecos, tablas y figuras, y escritura atómica. (RF-2, RF-3, RF-6 a RF-9, RF-23 a
      RF-25, RF-27, RF-44, RF-45, RF-106, RF-113, RF-114, RF-118, RF-120)
      Hecho cuando: `pytest -q tests/test_informe_docx.py` en verde.
- [ ] T7. `tools/informes_pf.py`: casos, medidas, imágenes y restauración, sobre `fake_pf`.
      (RF-1, RF-1b, RF-10 a RF-12, RF-24, RF-28 a RF-30, RF-46 a RF-49, RF-52, RF-53,
      RF-109 a RF-112, RF-116, RF-117)
      Hecho cuando: `pytest -q tests/test_informes_pf.py` en verde y `--help` responde.
- [ ] T8. Etapas 1 a 3: bancos existentes y del proyecto anterior, sonda y uso de `ComCapo`
      y `ComPlaceopt`. (RF-32, RF-35 a RF-40d)
      Hecho cuando: pruebas sobre `fake_pf` en verde y la sonda anotada en el plan.
- [ ] T9. Etapas 4 y 5 con la troncal de la 016 (necesita las T6 a T8 de la 016).
      (RF-41 a RF-42c)
      Hecho cuando: pruebas sobre `fake_pf` en verde.
- [ ] T10. Transformador de la SET en el proyecto de transmisión, sin guardar. (RF-65 a
      RF-70, RF-119)
      Hecho cuando: pruebas sobre `fake_pf` en verde.
      Sonda del 2026-10-15 (solo lectura, solo cargas, barras y trafos de AD08): las 859
      cargas de AD08 son por barra de SET y tensión (`LElCarmen10` en `CAR10A`, 7,53 MW;
      `LElCarmen23` en `CAR23A`), ninguna por alimentador; CA101 va dentro de `LElCarmen10`,
      bajo el `ElmTr3` `TR1 EL CARMEN_N` (60/23/10 kV). Decidido por el usuario: Δ de
      cabecera de 4.2 sumado a la carga de la barra, caso «{año}_D» (RF-67 cambiado).
      Estado 2026-10-15: `tools/transformador_set_pf.py` (con `--listar`), probado en
      `tests/test_transformador_set_pf.py` y en DIgSILENT real sobre AD08 con Δ = 0
      (no hay flujo de «Con proyecto» de CA101 guardado): 2026_D, `LElCarmen10`,
      devanado de 10 kV al 42,27 %, carga restituida; el listado da 525 cargas con
      transformador en 28 s. Botones en 4.4.2. Falta la imagen del unifilar (RF-69,
      RF-119) y la prueba con un Δ real (T14).
- [ ] T11. API, trabajo en el carril `powerfactory` y CLI con el mismo plan. (RF-26, RF-82,
      RF-96, RF-97, RF-99, RF-103 a RF-105)
      Hecho cuando: una prueba por endpoint en `tests/test_web_api.py`.
      Estado 2026-10-15: `GET informes` (contexto), `POST informes/estudio` y
      `POST informes/factibilidad` en el carril `engine`, con lo ya guardado, probados en
      `tests/test_informe_web.py`; RF-82 (formulario en el servidor) hecho el mismo día;
      faltan el carril `powerfactory` (con T7) y la CLI.
- [ ] T12. Paso «4.4 · Informes» en la web (antes «5 · Informes», cambiado por el usuario
      el 2026-10-15). (RF-73 a RF-95, RF-98, RF-100 a RF-102, RF-124, RF-125)
      Hecho cuando: `npx tsc --noEmit -p frontend`, `npm run build` y checklist del skill
      `igea-dgs-frontend`.
      Estado 2026-10-15: `InformesPF.tsx` con los dos formularios, botones «Generar»,
      huecos, descarga e informes generados; el libro de pérdidas se sube y se lee en 4.4.2
      (RF-93, RF-94); faltan las etapas de 5.2 (RF-83 a RF-88, con T8 y T9), el proyecto de
      transmisión (RF-95, con T10), la vista previa de ubicación (RF-124) y las miniaturas
      (RF-101, con T7).
- [ ] T13. Prueba en DIgSILENT: informe de estudio de CA101 desde cero, con los bancos de
      «CA101 13», revisado por el usuario.
      Hecho cuando: el usuario da por bueno el `.docx`.
- [ ] T14. Prueba en DIgSILENT: informe de factibilidad de una carga nueva del libro de
      cargas nuevas, con AD08 V4.
      Hecho cuando: el usuario da por bueno el `.docx`.
- [ ] T15. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "017:RF-[0-9]+" tests | sort -u` lista todos los RF.
