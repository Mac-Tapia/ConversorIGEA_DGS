# Tareas — Auditoría y arranque fiable

- [x] T1. Declarar y comprobar `psutil`. (RF-1)
      Hecho cuando: pruebas de declaraciones y del comprobador de entorno en verde.
      Ya estaba hecho (`requirements.txt`, extras `web` y `all`, `web/runtime.py`). Añadida la prueba
      del batch real: si sigue faltando tras instalar, sale con 1 y no inicia el servidor.
- [x] T2. Declarar `pypdf` en la instalación y los extras correspondientes. (RF-2)
      Hecho cuando: pruebas de declaraciones y extractor PDF real en verde.
      Las declaraciones ya estaban; el extractor solo se probaba con una página en blanco.
      Añadida `test_el_extractor_del_corpus_saca_el_texto_de_un_pdf`. Medido el 2026-11-03 con dos
      PDF reales de la distribuidora: 1 y 2 páginas, 1 625 y 5 728 caracteres, sin avisos.
- [x] T3. Interrumpir el batch ante fallos de npm. (RF-3)
      Hecho cuando: ejecución real del batch aislado con fallo de instalación y de build en
      verde, más el control de arranque correcto.
      `run_gui.bat` ya cumplía. La prueba no comprobaba el motivo, la segunda mitad de RF-3: ahora
      lo comprueba, con el caso nuevo de npm ausente.
- [x] T4. Corregir documentos desfasados e integrar el verificador de arquitectura en el manual.
      Hecho cuando: informe por carpeta, enlaces locales e inventario comprobados.
      Informe rehecho en `docs/AUDITORIA_RAIZ_2026-11-03.md`, porque el del 2026-10-29 no existe.
      Corregidas las rutas a la carpeta de datos retirada en el manual, el skill de backend y la
      constitución. Lo comprueban las pruebas `036 T4` de `tests/test_auditoria_raiz.py`.
- T5. Retirada el 2026-11-03, sin hacer: era limpiar solo residuos demostrados y conservar el manifiesto.
      Motivo: su manifiesto de cachés seleccionadas no existe, así que «no quedan las seleccionadas» no
      se puede comprobar, y una limpieza de una vez no dura: `__pycache__`, `.pytest_cache` y
      `.ruff_cache` vuelven con la siguiente prueba (0,47 GiB y 3 591 carpetas contadas el 2026-11-02).
      Sustituida por 062 (ejecuciones y temporales de la web, cumplida) y 065 T6 (cachés fuera del
      checkout, 065:RF-10, abierta). No se borró nada. Detalle en `docs/AUDITORIA_RAIZ_2026-11-03.md`.
- [x] T6. Verificación de la entrega.
      Hecho cuando: regresión relacionada, dependencias, compilación y trazabilidad en verde;
      registrar por separado cualquier límite de la auditoría y la aceptación nativa pendiente.
      Hecho el 2026-11-03, cada fichero por separado y con la GPU oculta: `test_auditoria_raiz` 29,
      `test_web_runtime_dependencies` 9, `test_web_runtime_front` 18, `test_lanzador_exitcode` 4,
      `test_lanzador_web` 16, `test_pide_dataset` 9, `test_sin_gui` 5, `test_trazabilidad_specs`,
      `test_regresiones`, `test_capas`, `test_casos_de_prueba` y `test_inventario`, todas en verde. También
      `pip check`, `generar_contrato_api.py --check`, `npm ci`, `npm run typecheck` y `npm run build`.
      Los límites y la aceptación nativa pendiente están en «Pendientes conservados» de
      `docs/AUDITORIA_RAIZ_2026-11-03.md`. No es la suite completa.
