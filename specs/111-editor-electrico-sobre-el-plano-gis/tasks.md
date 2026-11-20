# Tareas — Spec 111

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.
Cada fichero nuevo entra en `CODIGO_FUENTE.md` y en `docs/architecture/subsistemas.json` en la tarea que lo crea
(`tests/test_inventario.py`). Ninguna tarea toca `web/services.py`, `pide_economia.py`, `adaptadores/entrada/vnr/**` ni
`catalog_resolution.py`. Las órdenes de `npm` y `npx` se ejecutan en `frontend/`.

- [x] T1. Arnés e2e: `@playwright/test` y `@axe-core/playwright` como dependencias de desarrollo, `playwright.config.ts`
      y `e2e/preparar.mjs`, que arranca la web con un espacio sintético sorteado; primera prueba: las pestañas y
      acciones de hoy siguen ahí. (RF-16)
      Hecho cuando: `npx playwright test -c e2e/playwright.config.ts linea_base.spec.ts` (111:RF-16) en verde y
      `npm run build` correcto. Código del arnés hecho (`frontend/e2e/`, aclaración T1 del plan, y
      `tests/test_e2e_arnes.py`).
      Corrida (2026-11-16, 4d): en Chrome real, claro y oscuro, «2 passed» (semilla 1869780053, 3 alimentadores) y
      `npm run build` rc=0. Antes, `web_de_prueba.py` arrancaba a nivel de módulo: los hijos «spawn» de la
      conversión creaban otra sesión (401) y la conversión fallaba; ahora todo va en `main()`, con su prueba
      permanente en `tests/test_e2e_arnes.py`.
- [x] T2. Medición de la línea base: peso de la página y tiempo hasta el primer dibujo de la vista previa Leaflet de la
      red unida con todos los alimentadores de una entrega sorteada grande; fija el presupuesto y decide si basta
      Leaflet con lienzo o hace falta deck.gl en la página. (RF-1)
      Hecho cuando: `npx playwright test -c e2e/playwright.config.ts medicion_plano.spec.ts` deja la medición con la semilla y el número de
      alimentadores, y `plan.md` anota la cifra, el presupuesto y la decisión.
      Medición (2026-11-16, 4d): 40 alimentadores, semilla 20261116: 316 594 bytes y 6,0 a 8,6 s; presupuesto 2 MB y
      12 s; Leaflet con lienzo basta (plan.md, «Medición de la línea base»).
- [x] T3. Identidad y revisión de la red en `plano_red.py`: código de la fuente por elemento, cruce con el nombre en
      DIgSILENT por `dgs.nombre_en_pf`. Esa función **no existe en 51895566**: esta tarea la CREA en `dgs.py` como alias
      público de `_loc_name`, igual a él y sin cambiar ningún DGS; ningún módulo importa el nombre privado. Aviso de
      colisiones y huella de revisión. (RF-2, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_plano_red.py -k "identidad or revision or nombre_en_pf" tests/test_capas.py`
      en verde. Una prueba comprueba que `dgs.nombre_en_pf(x) == dgs._loc_name(x)` sobre identificadores sorteados (con
      tildes, espacios y longitud por encima del límite), y que el DGS de referencia sintético sale idéntico byte a byte.
- [x] T4. Vista del plano: todos los vértices de la fuente por alimentador, sin simplificar; dato original, lo deducido
      con su motivo y el estado de calidad de cada elemento; doble terna y alimentador sin coordenadas. (RF-1, RF-2,
      RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_plano_red.py` en verde con las dos disposiciones y
      dos perfiles sintéticos.
- [x] T5. Variación del plano en `variacion_plano.py`: maniobra y tramo nuevo (vértices tal como se dibujaron, longitud
      GIS y eléctrica por separado), guardada con versión y su revisión de partida en el espacio, nunca en el caso
      base; la geografía y el DGS quedan con la misma huella. (RF-4, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_variacion_plano.py -k "maniobra or tramo"` en
      verde.
- [x] T6. Reglas de topología de la edición: dos tramos que se cruzan sin nodo ni equipo no se conectan; el ajuste de un
      extremo a un nodo cercano es una propuesta con su distancia, aplicada solo al confirmarla; radio
      `editor_ajuste_m` del perfil. (RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_variacion_plano.py -k "cruce or ajuste"` en verde.
- [x] T7. Inserción de equipos con validación de tensión, fases y conexión, y la lista de lo que falta; un equipo sin
      parámetros no se acepta. (RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_variacion_plano.py -k equipo` en verde.
- [x] T8. Deshacer y rehacer las ediciones de una variación sin confirmar; al confirmarla, el diario queda cerrado.
      (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_variacion_plano.py -k "deshacer or rehacer"` en
      verde.
- [x] T9. Resultado por elemento con el motor abierto: `oraculo.resultados_por_elemento` y `resultados_plano.py`, que
      aplica la variación a una copia del modelo; si no converge, no hay resultado que pintar y se dan los mensajes del
      motor; el resultado guarda el motor, el caso y la revisión. (RF-10, RF-11, RF-17, RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_resultados_plano.py -k "abierto or converge"` y
      `tests/test_oraculo.py` en verde.
- [x] T10. Capas de resultados: tensión por barra, corriente y cargabilidad por tramo y estado de cada equipo, con
      unidad, banda, umbral del perfil (o el de por defecto, dicho), caso y motor; un incumplimiento lleva texto,
      icono, valor y umbral; los resultados de DIgSILENT se traducen por la identidad y solo se pintan si coinciden el
      caso y la revisión. (RF-10, RF-11, RF-13, RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_resultados_plano.py -k "capa or umbral or revision"`
      en verde.
- [x] T11. Comparación de dos casos por elemento sobre el mismo plano, con aviso cuando los motores son distintos.
      (RF-12, RF-19)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_resultados_plano.py -k comparar` en verde.
- [x] T12. Guion `tools/variacion_plano_pf.py`: la variación, en una variación temporal del conversor dentro de una
      copia del caso (y del escenario de operación si lo hay), `ComLdf`, lectura con `geografia`, borrado y
      restitución comprobada con `pf_estado`; elección del motor por licencia y vínculo del proyecto. (RF-4, RF-10,
      RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_variacion_plano_pf_guion.py` en verde con
      `tests/fake_pf.py` y `.venv/Scripts/python.exe tools/variacion_plano_pf.py --help` responde sin DIgSILENT.
- [x] T13. API en `web/plano_api.py` (`registrar_rutas_plano`) y contratos en `web/api_contract.py`; cableado mínimo
      en `web/app.py`, pactado con el integrador; versión con `409` si cambió la versión o la revisión de la red;
      estudiar como trabajo en su carril; las rutas de antes siguen. (RF-4, RF-9, RF-15, RF-16, RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_plano_api.py tests/test_contrato_api.py` en verde y
      `.venv/Scripts/python.exe tools/generar_contrato_api.py --check` sin deriva. Código hecho (`web/plano_api.py`,
      sus contratos y `tests/test_plano_api.py`); falta el cableado de `web/app.py` con su contrato regenerado, que
      monta el integrador con el parche aparte de la entrega.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_contrato_api.py tests/test_plano_api.py.
- [x] T14. Página del plano en `pagina_plano.py`: Leaflet propio con lienzo, capas por vista, nivel de detalle solo
      gráfico y reversible, leyenda con unidad, umbral, caso y motor, tokens claro y oscuro, sin fondo si las teselas
      están apagadas, CSP aislada y mensajes `postMessage` con esquema cerrado. (RF-1, RF-2, RF-10, RF-13, RF-14,
      RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pagina_plano.py` en verde.
- [x] T15. Pestaña «Plano de la red»: `api/plano.ts` y `features/plano/` (plano, buscador por código, inspector,
      ediciones con deshacer y rehacer, tabla enlazada y virtualizada, capas, caso y comparación), montada en
      `app/App.tsx` sin quitar nada; anuncios `aria-live`; todo con teclado; ninguna regla eléctrica ni umbral en el
      navegador; textos sin RF ni jerga. (RF-2, RF-3, RF-9, RF-12, RF-13, RF-14, RF-15, RF-16, RF-18, RF-19)
      Hecho cuando: `npm run lint`, `npm run typecheck`, `npm test` (`test/plano.test.mjs`) y `npm run build` en verde.
      Hecho (`api/plano.ts`, `features/plano/`, la pestaña en `App.tsx` y su paso en `pasoDeTrabajo.ts`): lint,
      typecheck, `test/plano.test.mjs` y `npm run build` en verde (evidencia en la entrega T15 v2, fuera de git).
- [x] T16. Recorridos e2e en navegador real: maniobra → flujo con el motor abierto → resultados sobre el plano, y
      comparación de dos casos, los dos también solo con teclado; axe sin fallos serios en claro y en oscuro; huellas de
      los vértices de la fuente iguales antes y después. (RF-1, RF-2, RF-3, RF-4, RF-10, RF-11, RF-12, RF-13, RF-14,
      RF-16, RF-17, RF-18, RF-19)
      Hecho cuando: `npx playwright test -c e2e/playwright.config.ts plano.spec.ts` en verde, con la semilla en el registro.
      Hecho en la fila 111-T16 (f7, 17-11): `frontend/e2e/plano.spec.ts`, en claro y oscuro y solo con el teclado: buscar
      una maniobra, abrir una variación, cambiar su estado y estudiar con el motor abierto (resultados sobre el plano con
      el motor dicho), un segundo caso estudiado y la comparación del A con el B; axe sin infracciones graves y las huellas
      de los vértices de la fuente iguales antes y después. Sustituye al F02 vacío de 086 T79 (086:RF-107).
- [ ] T17. Revisión a mano en navegador real: solo teclado, lector de pantalla, contraste en claro y oscuro, foco
      visible y microcopia sin exceso de texto. (RF-13, RF-14)
      Hecho cuando: la nota de la revisión, con capturas, está en la evidencia de la entrega (fuera de git) sin
      hallazgos abiertos.
- [ ] T18. [DIgSILENT] Recorrido real por la web sobre una copia de un proyecto de prueba: una maniobra y un tramo nuevo
      estudiados en DIgSILENT, resultados sobre el plano con el motor dicho, y el caso base y los casos del operador
      como estaban. (RF-4, RF-10, RF-11, RF-17, RF-18)
      Hecho cuando: la evidencia de la corrida (informe del guion, foto de `pf_estado` antes y después y capturas del
      plano) está fuera de git y la relectura no da ninguna diferencia en los casos del operador.
- [x] T19. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "111:RF-[0-9]+" tests frontend/test frontend/e2e | sort -u` lista de RF-1 a RF-19.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: las del criterio.
- [x] T20. Selección enlazada plano ↔ tabla ↔ inspector con encuadre y zoom al elemento. (RF-20)
      Hecho cuando: un recorrido e2e en navegador real selecciona en cada vista y comprueba las otras dos y el encuadre,
      y `npm test` cubre la sincronización sin navegador.
      Hecho en la fila 111-T20 (f7, 17-11): `seleccionEnlazada` en logicaPlano.ts (una regla para toda selección; la que viene del
      plano también encuadra con margen), Escape y «Quitar la selección» la quitan en todas las vistas, y el mensaje
      «deseleccionar» en pagina_plano.py; pruebas: frontend/test/planoEspacio.test.mjs, tests/test_pagina_plano.py y
      frontend/e2e/plano_espacio.spec.ts.
- [x] T21. Del hallazgo al elemento: cada fila de hallazgos del informe y de las tablas lleva al plano y al inspector con
      valor, umbral, norma citada, caso y motor. (RF-21)
      Hecho cuando: e2e en navegador real desde un hallazgo de cada tipo y prueba del servidor de que la norma citada sale
      de la biblioteca (ninguna cita escrita en el frontend).
      Hecho en la fila 111-T21 (f7, 17-11): `resultados_plano.normas_de_las_capas` lee la norma de cada hallazgo de la biblioteca
      (tensión: calidad.tension.tolerancia_ntcse) y da la cargabilidad de distribución como criterio de la empresa
      (perfil: estudios.cargabilidad_max_pct, con su origen); el inspector enseña valor, umbral, norma, caso y motor;
      pruebas: tests/test_resultados_plano.py, frontend/test/planoEspacio.test.mjs y frontend/e2e/plano_espacio.spec.ts.
- [x] T22. El espacio de trabajo de ingeniería en una pantalla (plano, tabla e inspector redimensionables y recordados).
      (RF-22)
      Hecho cuando: e2e en navegador real a 1366×900 y a 1920×1080, en claro y oscuro, y la matriz de la web sin ninguna
      vista retirada.
      Hecho en la fila 111-T22 (f7, 17-11): la pestaña es una sola pantalla con el plano, la tabla y el inspector, con dos
      separadores accesibles (flechas, Inicio y Fin) y el reparto recordado por espacio; estrecha, se apilan sin quitar
      ninguna vista; pruebas: frontend/test/planoEspacio.test.mjs y frontend/e2e/plano_espacio.spec.ts a 1366×900 y 1920×1080.
- [x] T23. Unifilar automático sincronizado con el plano (selección y resultados), sin tocar geometrías ni impedancias. (RF-23)
      Hecho cuando: rojo por aserción (sin unifilar) y verde con sus pruebas de render y su e2e en navegador real.
      Hecho en la fila PLANO-A (4d, 18-11): dominio/disposicion_unifilar.py da la disposición por anchura desde la
      cabecera, común con el unifilar del PIT (107:RF-15, mismas hojas); la vista del plano trae su unifilar y la
      pestaña lo enseña con los mismos códigos, la misma selección y las mismas bandas; pruebas:
      tests/test_plano_unifilar.py, frontend/test/unifilar.test.mjs y frontend/e2e/unifilar.spec.ts (claro y oscuro).
- [x] T24. Varios alimentadores a la vez, cada uno con su color y su capa. (RF-24)
      Hecho cuando: rojo por aserción (un solo alimentador y un solo color) y verde con sus pruebas del servidor y de la
      pestaña, y comprobado en navegador real.
      Hecho en la fila PLANO-VARIOS (ce, 19-11): «Ver también» en PlanoRed.tsx (casillas con filtro; el principal sigue en
      su desplegable) pide el plano y su página con todos; pagina_plano.py da un color por alimentador
      (COLORES_ALIMENTADOR, claro y oscuro), su capa en el selector y la leyenda; el resalte vuelve a su color; pruebas:
      tests/test_plano_varios_alimentadores.py y frontend/test/planoVariosAlimentadores.test.mjs.
- [x] T25. Los puntos de transferencia entre los alimentadores del plano. (RF-25)
      Hecho cuando: rojo por aserción y verde con una barra común, un trecho común, una vista combinada y el contrato.
      Hecho en la fila PLANO-VARIOS (ce, 19-11): plano_red.transferencias (barras de frontera con el mismo código; medido
      en una entrega real: una barra común entre vecinos), en el resumen del plano, su contrato
      (TransferenciaPlanoRespuesta) y la página (rombo con los alimentadores, la barra y sus maniobras); la pestaña los
      lista y cada uno lleva a su barra; pruebas: tests/test_plano_varios_alimentadores.py y
      frontend/test/planoVariosAlimentadores.test.mjs.
- [x] T26. Etiquetas del código y la potencia de la SED y de la sección del conductor. (RF-26)
      Hecho cuando: rojo por aserción y verde con las tres capas apagadas al abrir y la sección de cada tramo.
      Hecho en la fila PLANO-VARIOS (ce, 19-11): la vista da `seccion_mm2` de cada tramo (catalog.seccion_de_codigo); la
      página tiene tres capas de etiquetas desde ZOOM_ETIQUETAS y el aviso para acercarse; prueba:
      tests/test_plano_varios_alimentadores.py.
- [x] T27. El fondo de calles llega: las teselas piden con el origen como «Referer». (RF-27)
      Hecho cuando: el «403 Access blocked» reproducido (sin «Referer», la imagen de bloqueo de 6,7 kB; con el origen, la
      tesela de 19,7 kB), rojo por aserción y verde, y comprobado en navegador real.
      Hecho en la fila PLANO-VARIOS (ce, 19-11): preview.REFERER_TESELAS en el `L.tileLayer` común (plano, vista previa y
      mapa de las cargas nuevas); prueba: tests/test_plano_varios_alimentadores.py.
      Comprobado en navegador real el 19-11 (claro y oscuro): frontend/e2e/plano_varios.spec.ts en verde, registro en
      `D:/csg/PM_IMPL/GWEB2/hueco/e2e_plano.log`.
