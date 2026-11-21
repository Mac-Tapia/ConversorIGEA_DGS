# Tareas — Spec 026, asistente de órdenes

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Catálogo de tareas: cada tarea de RF-11 con su función de `services`, sus datos, si
      escribe y su carril. (RF-8, RF-9, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_asistente_tareas.py` en verde (cada tarea apunta a una
      función que existe y cada dato obligatorio tiene tipo).
      Hecho el 2026-10-24.
- [x] T2. Ejemplos sintéticos con los nombres reales del espacio. (RF-21)
      Hecho cuando: `pytest -q tests/test_asistente_sinteticos.py` en verde.
      Hecho el 2026-10-24.
- [x] T3. Transformer (tokenizador, codificador, tarea y BIO), entrenamiento en GPU, registro y
      promoción por puertas; `tools/asistente_entrenar.py`. (RF-2, RF-19, RF-20)
      Hecho cuando: `pytest -q tests/test_asistente_transformer.py` en verde, con acierto de tarea
      en frases no vistas por encima del umbral del perfil.
      Hecho el 2026-10-24: por caracteres, con los datos decididos por palabra (carácter a carácter
      el F1 de los datos era 0,13); con los 98 alimentadores, 61 proyectos y 4 zonales reales,
      acierto de tarea 98,1 % y F1 de los datos 0,87 en la prueba fija; el segundo reentrenamiento
      ya incluyó una orden confirmada en la web.
- [x] T4. Cliente de Ollama local y medida de qwen2.5:3b frente a llama3.1:8b
      (`tools/asistente_medir_ollama.py`). (RF-3, RF-5)
      Hecho cuando: `pytest -q tests/test_asistente_ollama.py` en verde y la medida elige modelo.
      Hecho el 2026-10-24: llama3.1:8b (76 %) frente a qwen2.5:3b (74 %), los dos en 1,5 s de
      mediana; Ollama suelta la GPU antes de cada entrenamiento (con su modelo cargado, entrenar dio
      «CUDA error: out of memory») y no retiene el modelo más de 60 s.
- [x] T5. Intérprete híbrido y plan con datos contrastados y razonamiento. (RF-2 a RF-7)
      Hecho cuando: `pytest -q tests/test_asistente_interprete.py` en verde.
      Hecho el 2026-10-24; los requisitos de cada tarea (entradas del espacio) se comprueban en el
      plan con la misma validación de la web: «carga la fuente» sin entradas se ofrecía para
      confirmar y fallaba después en la ruta.
      Corregido el 2026-11-14 (prueba del auditor con órdenes reales, F1): el vocabulario de alimentadores era el
      NetworkID de la fuente y «convierte el PA217» decía que faltaban alimentadores. Ahora es el código del
      alimentador, como en la tabla de la web, y una orden con el NetworkID resuelve al mismo
      (`services.asistente_vocabulario`, `plan._alimentadores`). Evidencia: `pytest -q tests/test_asistente_vocabulario.py`,
      con las dos disposiciones del TXT, cuatro convenciones de NetworkID y filas de .mdb y VNR-GIS, sorteadas.
      Un código que llevan dos redes (dos SET o repetido en la fuente) no se resuelve con la primera: el vocabulario
      da sus NetworkID y el plan pregunta cuál. De punta a punta por la web, la ruta real convierte el alimentador
      sorteado; con CSG_MDB y CSG_VNR_BAK, el vocabulario de la fuente real reconoce sus códigos.
- [x] T6. Web: rutas de orden, confirmación y corrección, ejecución por los trabajos de la web;
      consola en el front. (RF-1, RF-8, RF-9, RF-10, RF-12, RF-15, RF-19)
      Hecho cuando: `pytest -q tests/test_asistente_web.py` en verde y `npm run build` sin errores.
      Hecho el 2026-10-24: pestaña «Asistente»; carril `asistente`, que solo espera.
- [x] T7. Informes desde la consola y clasificador de dos niveles con los subtipos del perfil.
      (RF-13 a RF-16)
      Hecho cuando: `pytest -q tests/test_asistente_clasificador.py` en verde.
      Hecho el 2026-10-24: acierto de tipo 100 % y de subtipo 98,7 % en la prueba fija.
- [x] T8. Índice del proyecto con embeddings locales o BM25 y respuestas con cita. (RF-17, RF-18)
      Hecho cuando: `pytest -q tests/test_asistente_indice.py` en verde.
      Hecho el 2026-10-24: con BM25; los embeddings se usan si `nomic-embed-text` está instalado
      en Ollama (aún no se ha descargado).
- [x] T9. Vigilancia de trabajos, modelos, calidad y suite nocturna. (RF-22 a RF-25)
      Hecho cuando: `pytest -q tests/test_asistente_vigilancia.py` en verde.
      Hecho el 2026-10-24.
- [x] T10. Mejoras en rama aparte (`git worktree`), sin fusionar, y registro de decisiones.
      (RF-26 a RF-28)
      Hecho cuando: `pytest -q tests/test_asistente_mejoras.py` en verde.
      Hecho el 2026-10-24.
- [x] T11. Internet con filtro de identificadores, registro y propuestas de librerías.
      (RF-29 a RF-32)
      Hecho cuando: `pytest -q tests/test_asistente_internet.py` en verde.
      Hecho el 2026-10-24: probado contra GitHub y arXiv reales (8 repositorios y 5 artículos);
      «busca en github caída de tensión en IN111» se bloquea sin salir de la máquina.
- [x] T12. [DIgSILENT] Aceptación: una orden real de cada tarea de RF-11 desde la consola, en DIgSILENT;
      validación RF por RF; suite completa con las siete variables y ninguna omitida.
      (Todos)
      Hecho cuando: `grep -rnoE "026:RF-[0-9]+" tests | sort -u` lista los 32 RF y la suite pasa.
      En curso el 2026-10-24: los 32 RF citados por pruebas en verde; en la web real, consultas
      (estado, proyectos, PIDE, episodios, preguntas con cita, clasificación, búsqueda y bloqueo),
      evaluación del gemelo lanzada sola, reentrenar la PINN confirmado y planes de las órdenes que
      escriben (sistema Pisco con 2026-07, verificar el «Caso base» de IN111–TA225). Falta
      confirmar en DIgSILENT las tareas que lo usan (sistema completo, cargas, obras, estudios,
      transferencia, PIDE e informes): el 2026-10-24 otra sesión tenía DIgSILENT ocupado y el espacio
      no tenía entradas.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T13. Informes reales por grupo y estratificados; herramienta para anotarlos desde un manifiesto. (RF-33, RF-34)
      Hecho cuando: `tests/test_asistente_clasificador.py` (026:RF-33, RF-34) en verde.
- [x] T14. Puerta propia de los informes reales en las dos vías de entrenamiento. (RF-35)
      Hecho cuando: `tests/test_asistente_clasificador.py` (026:RF-35) en verde.
- [x] T15. Clasificador de informes por vectores como arquitectura elegible, guardado sin pickle, con las mismas puertas,
      elección con un grupo fuera solo en entrenamiento y carga según la arquitectura en uso. (RF-36 a RF-41)
      Hecho cuando: `tests/test_asistente_clasificador_vectores.py` (026:RF-36 a RF-41) en verde y el ensayo corto con los
      informes reales (entrenar, guardar y reabrir en un proceso nuevo) da las mismas predicciones.
- [x] T16. Órdenes de las entradas: asignar un fichero (de la máquina o de la nube) a cada casilla del espacio y subir los
      libros de las fuentes de la empresa a su carpeta y año, por las rutas de la web, con confirmación. (RF-42)
      Hecho cuando: la orden no existe con el código de antes (rojo por aserción) y existe después, con su prueba del
      ejecutor contra la API de prueba y la e2e F04 ampliada; `test_asistente_*` y la sellada 107-112 en verde.
      Implementada el 2026-11-19 (ce, ASISTENTE-B): `asignar_entrada` sube el fichero de la máquina a su casilla por
      `POST /inputs/{casilla}` (la casilla, por las palabras de la orden o por la extensión; lo que la casilla rechaza no
      entra y la vigente se queda) y `subir_fuente_empresa` registra el libro en `POST /fuentes` con su clase y su año
      (sin año, el plan lo pregunta, salvo perfil, catálogo, TdR y .pfd); de la nube, el plan remite al selector del
      operador (`importar_nube`, 070:RF-81). Las dos y `repetir_trabajo` (T17) van en `TAREAS_026_CONTROL`, fuera de las
      selladas de la 070 y la 079 y con su conjunto sellado propio (`prueba_sellada_026.selladas_control`, huella
      54a19b36009d381b), en el currículo y en las propuestas. Prueba: `tests/test_asistente_026_entradas.py`
      (026:RF-42). Rojo VALIDO: `D:/csg/PM_IMPL/ASISTENTE_B/b_T16/r2/rojo.log` (5 failed por aserción); verde:
      `D:/csg/PM_IMPL/ASISTENTE_B/b_T16/r2/verde.log` (390 passed, 0 omitidas, rc=0).
      Hecho el 2026-11-21 (d8, MEJ19b): la e2e F04 ampliada asigna y sube cada casilla desde el asistente, acepta
      antes el diálogo de error del trabajo fallido (081:RF-24) y lo comprueba en la API: dos veces seguidas sobre el
      índice final, «3 passed», rc=0 (D:/csg/PM_IMPL/MEJ19_ENTRADAS/e2e_mej19b_f04_1_20261121_082946.log,
      e2e_mej19b_f04_2_20261121_083026.log), y el arnés e2e entero, «19 passed»
      (e2e_mej19b_arnes_20261121_082707.log); rojo y verde de la estructural nueva en
      rojo_verde_mej19b_20261121_082604.log (sin el arreglo FALLA, con él PASA). `test_asistente_*` y la sellada
      107-112, en el verde del hueco FIN (D:/csg/PM_IMPL/FIN/estado.txt), que también repite la e2e sobre la punta que
      se integra.
- [x] T17. Control de los trabajos: carril, avance y resultado de cada uno, cancelar y repetir el último que falló con sus
      mismos datos. (RF-43)
      Hecho cuando: rojo por aserción (las órdenes de estado y de repetir no existen) y verde con la prueba del ejecutor.
      Hecho el 2026-11-18 (ce, ASISTENTE-B): la consulta `estado` da el carril, el avance y el error de cada trabajo en
      curso y el último que falló; `repetir_trabajo` rehace con `asistente_plan_repetido` el último plan que falló (no el
      cancelado) como plan nuevo, con su tarea, sus datos, el sello de ahora y su confirmación; cancelar ya estaba
      (`cancelar_trabajo`, 070:RF-32). Prueba: `tests/test_asistente_026_trabajos.py` (026:RF-43).
- [x] T18. Órdenes `vnr_estudio` (108) y `clientes_fijos_evolucion` (105), con las entradas del espacio por defecto;
      sus frases en el corpus de entrenamiento del intérprete (079), nunca en el sellado; se miden en su propia prueba
      sellada (`prueba_sellada_026`, con el criterio de la 070:RF-85) y las selladas de la 070, la 079 y la 107-112
      conservan su huella. (RF-44)
      Hecho cuando: rojo por aserción (las órdenes no existen) y verde con `tests/test_asistente_026_modulos.py`,
      `tests/test_prueba_sellada_026.py` (incluida la fuga sembrada en el currículo, que tiene que delatarse),
      `tests/test_prueba_sellada_107_112.py` y las que restan las tareas sin sellada de la 070 y la 079
      (`test_afinado_ordenes`, `test_asistente_maestro`, `test_destilacion_integral`).
- [x] T19. Entregar los entregables de cada módulo: descargarlos, publicarlos en la nube o enviarlos por correo, con
      confirmación. (RF-45)
      Hecho cuando: rojo por aserción y verde con la prueba del ejecutor por módulo (PIDE, PIT, VAD, VNR e informes).
      Hecho el 2026-11-19 (ce, ASISTENTE-B), por las rutas que ya tiene la web: `descargar_resultados` con el módulo que
      nombra la orden baja el PIDE, el VNR y los informes en el ZIP de la salida con su selección (`/outputs/archive`), y
      el PIT (de su último expediente o diagnóstico terminado, `GET /api/jobs/{id}`) y el VAD (de su estudio,
      `GET /vad/{estudio}`) fichero a fichero, enlazados por `/files`; «descarga el expediente del PIT» ya no lo vuelve a
      armar. `publicar_nube` deja la tarjeta con la selección del PIDE, el VNR o el informe; `enviar_informe` prepara el
      borrador de un informe y nunca adjunta otro libro en lugar del módulo pedido. Publicar y enviar siguen siendo el clic
      del operador (070:RF-81). Lo que la web no hace, el plan lo dice y no se ofrece: publicar el PIT o el VAD (están
      fuera de la salida, que es lo único que publica la nube, 109:RF-24) y mandar por correo un módulo que no es un
      informe (el correo solo lleva un informe cerrado, 110:RF-3). Prueba: `tests/test_asistente_026_entregas.py`
      (026:RF-45). Rojo VALIDO: `D:/csg/PM_IMPL/ASISTENTE_B/b_T19/rojo.log` (6 failed por aserción); verde:
      `D:/csg/PM_IMPL/ASISTENTE_B/b_T16/r2/verde.log` (390 passed, 0 omitidas, rc=0).
- [x] T20. Órdenes `normativa_comprobar` (lectura), `normativa_agregar` y `normativa_regenerar` (con el resumen del cambio
      y confirmación; 107:RF-22). (RF-46)
      Hecho cuando: rojo por aserción por cada orden y verde con `tests/test_asistente_026_normativa.py` (comprobar solo
      lee; agregar sube el .json; regenerar con vista previa que no escribe y aplicar con su ficha; fuente alterada o
      sin carpeta, sin regenerar y con su motivo sin rutas de la máquina), `test_biblioteca_normativa`,
      `test_pit_sombreadas` y `tests/test_prueba_sellada_026.py`.
- [x] T21. Dictamen del equipo (fuentes, física, coste y riesgo) antes de escribir un entregable, enseñado con la
      confirmación. (RF-47)
      Hecho cuando: rojo por aserción (sin dictamen) y verde con la prueba del gobierno del equipo (065).
      Hecho el 2026-11-19 (ASISTENTE-C, wt_ce_c sobre 1797b486): `equipo.dictamen_del_equipo` y
      `GobiernoEquipo.dictaminar` leen las corridas custodiadas del mismo proyecto y fuente (la más reciente de cada
      clase), sin calcular nada; con «riesgo», `_validar` no deja escribir y su motivo es la pregunta; el dictamen va en
      el sello del plan guardado, en `publico()`, en el razonamiento del plan (y la pregunta en sus avisos) y en cada
      etapa de entregable del proyecto entero; la custodia guarda el estado del trabajo. Rojo VALIDO (9 failed) en
      D:/csg/PM_IMPL/ASISTENTE_C/026_T21/rojo.log; verde D:/csg/PM_IMPL/ASISTENTE_C/verde/verde_c.log (461 passed, rc=0), con
      `tests/test_asistente_026_dictamen.py`, `test_asistente_equipo.py` y `test_asistente_equipo_web.py`.
- [x] T22. El asistente decide el camino: siguiente etapa, entradas del espacio y parámetros según la norma y el perfil,
      propuesto entero con su motivo; el operador confirma lo que escribe o envía. (RF-48)
      Hecho cuando: rojo por aserción (sin propuesta de camino con su motivo) y verde con la prueba del planificador y la
      e2e F04 ampliada.
      Implementada el 2026-11-19 (ASISTENTE-C, wt_ce_c): `orquestador.camino_de` sobre la lista que confirma el
      operador (siguiente etapa, entradas, parámetros de la norma vigente con su acto y del perfil, motivo, qué confirma
      el operador y qué hace solo), en el plan del proyecto entero (`publico['camino']`). Rojo VALIDO (7 failed) en
      D:/csg/PM_IMPL/ASISTENTE_C/026_T22/rojo.log; verde D:/csg/PM_IMPL/ASISTENTE_C/verde/verde_c.log (461 passed, rc=0) con
      `tests/test_asistente_026_camino.py`.
      Comprobado el 2026-11-19 (d8) en navegador real: e2e F04 ampliada (proyecto entero, módulos saltados con su motivo
      y camino propuesto), con CSG_E2E_SIN_MODELO=1, en verde; registro `D:/csg/PM_IMPL/BC_d8/e2e_test_e2e.log`.
      Bloqueada por la e2e F04 ampliada (el camino propuesto), que corre en el FIN2 de esta fila. Siguiente acción:
      ampliar `frontend/test/e2e/f04_asistente.e2e.mjs` y correrla con los dos arneses.
- [x] T23. Aprender del operador y del programa: cada acción del operador con su contexto y su resultado al corpus de
      entrenamiento (nunca al sellado), evaluado antes de usarse y sin promoción automática. (RF-49)
      Hecho cuando: rojo por aserción (la acción no llega al corpus) y verde con las pruebas del diario de operaciones
      (061), del corpus y de la evaluación (027).
      Hecho el 2026-11-19 (ASISTENTE-C, wt_ce_c2): `RegistroOperaciones.terminadas` da las operaciones acabadas de cada
      espacio; `dataset_entrenamiento.importar_diarios_operaciones` (en `construir_dataset(raiz_web=…)` y en
      `tools/construir_dataset_entrenamiento.py`) las lleva al corpus como `accion_operador`, anonimizadas (clase del
      trabajo, resultado, fuente y lo de antes; espacio, trabajo y huella por su huella con sal; sin título, error,
      proyectos ni rutas), del operador (`gold_human`) o del programa (`silver_deterministic`), con tarea
      `proponer_accion` para que el intérprete no las tome por órdenes; la que coincide con una sellada va a cuarentena
      (`fuga_evaluacion.frases_selladas`, `fugas_de_lo_aprendido`). `evaluar_acciones_aprendidas` aprende de train y mide
      con validation+test (sin compartir registro ni grupo; 5 casos y acierto 0,8), y sale sin promover; solo
      `promover_acciones_aprendidas` con el operador, y `propuesta_aprendida` no propone nada sin promover, sin puertas o
      tocado. Rojo VALIDO (5 failed) en D:/csg/PM_IMPL/ASISTENTE_C/026_T23/rojo.log; verde en
      D:/csg/PM_IMPL/ASISTENTE_C/026_T23/verde.log, con `tests/test_asistente_026_aprender.py`.
      Ampliada el 2026-11-19 (ASISTENTE-C, wt_ce_c2) para que lo aprendido LLEGUE al operador, de punta a punta:
      `tools/construir_dataset_entrenamiento.py` guarda el candidato entero (tabla, evaluación, puertas, huella,
      `promovido=false`) en el almacén del asistente, fuera de git (`acciones_aprendidas/candidato.json`, con
      `publicar_duradero`; nunca encima de uno promovido); la web da `GET /api/asistente/aprendido` (candidato, lo que
      está en uso y si se puede promover) y la promoción con previa y confirmación de un solo uso
      (`POST /api/asistente/aprendido/previa` y `/promover`, solo desde el navegador; lo promovido va aparte, a
      `en_uso.json`, y falla con su motivo si no pasó las puertas, si se tocó tras medirse o sin confirmación);
      `services.agente_proyecto_lista` añade `aprendido` (`propuesta_aprendida` con la fuente del espacio y lo último
      acabado en su diario de la 061, `anterior_del_espacio`) solo si hay algo promovido e intacto, y nunca ejecuta; el
      panel del asistente enseña «Lo aprendido del operador» (evaluación, puertas y el botón solo con ellas pasadas) y
      «Proyecto desde cero», la propuesta aprendida con su motivo. Rojo VALIDO en
      D:/csg/PM_IMPL/ASISTENTE_C/026_RF49_web/rojo.log y rojo_node.log; verde en la misma carpeta, con
      `tests/test_asistente_026_aprender.py` y `frontend/test/asistenteAprendido.test.mjs`.
- [x] T24. Navegar por internet para buscar información: búsqueda y lectura de páginas web generales con las salvaguardas
      de RF-29 a RF-32 (consulta sin datos de la distribuidora, registro con destino, fecha y huella, salidas de red),
      lo leído citado como fuente y nunca obedecido, sin credenciales ni pagos. (RF-50)
      Hecho cuando: rojo por aserción (sin búsqueda ni lectura general) y verde con las pruebas del buscador: un dominio
      fuera de la lista no se consulta, añadir uno pide confirmación y queda registrado, una consulta con un código de
      alimentador o con un término del perfil se rechaza antes de salir, la página se cita con su huella y con las
      salidas apagadas no se envía nada (`tests/test_asistente_026_internet.py` y `tests/test_asistente_internet.py`;
      la lista base en `internet.DOMINIOS_BASE`, la del operador en `config/internet_dominios.json` de la carpeta local,
      fuera de git, y `GET`/`POST /api/asistente/internet/dominios`).
- [x] T25. Matriz de operaciones del asistente derivada del código, con sus pruebas y los huecos de las specs del
      asistente con su responsable. (RF-51)
      Hecho cuando: rojo por aserción (sin matriz) y verde con `tests/test_matriz_operaciones.py` (026:RF-51): todas las
      tareas, vías directas y lecturas están, los huecos salen de `estado_specs` y `--comprobar` falla con una operación
      sin prueba, un hueco sin dueño o un dueño de una tarea cerrada.
      Hecho el 2026-11-18: `tools/matriz_operaciones.py` (A0 del plan de control integral de Codex); al corte, 75
      operaciones con prueba que las cita y 12 huecos con dueño; aceptación del dominio, no medida.
