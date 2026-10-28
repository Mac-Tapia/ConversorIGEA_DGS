# Tareas — Spec 027

Estado: aprobadas el 2026-10-28; se empieza por T0 y T19. Una tarea cada vez, pruebas primero.

- [x] T0. Auditoría del dataset de cada modelo antes de entrenar (`tools/digital_twin_auditar.py`
      e informe en el registro del modelo): estructura, validez, rangos, impedancias mínimas,
      tensiones implausibles, parámetros frente a etiquetas; corregir el comentario de
      `Muestra.x` (5 columnas, no 4). (RF-29 a RF-34)
      Hecho cuando: `pytest -q tests/test_digital_twin_auditoria.py` en verde con datos
      sorteados que traen cada defecto, y el informe del búfer real reproduce las cifras del
      2026-10-28 (24 muestras, 1 red de 2470 nodos, 928 518 parámetros).
      Hecho el 2026-10-28: 6 pruebas en verde; `tools/digital_twin_auditar.py` sobre el búfer real da
      24 muestras, 1 red de 2470 nodos, 58 707 etiquetas, 928 518 parámetros, 11 episodios con
      tensiones fuera de 0,8–1,2 p.u. y 5 órdenes reales del asistente (1 en la prueba).
- [x] T1. Episodio tras cada calibración, obra y estudio de cualquier sistema desde la web, con
      sistema, SET, caso y huella. (RF-1)
      Hecho cuando: `pytest -q tests/test_digital_twin_capture.py` en verde y, tras calibrar
      Nasca y Chincha desde la web, el búfer tiene episodios de las dos familias.
      Hecho el 2026-10-28: la lectura nativa trae el grafo eléctrico (antes solo tensiones) y el
      episodio de la calibración de Nasca en DIgSILENT es entrenable (4067 nodos con tensión).
      Pendiente (2026-10-28): Nasca dejó de cuadrar en DIgSILENT. NA203 se arregló con 004:RF-67
      (de +6,18 % a −0,18 %), pero la cabecera de NA205 se queda en 8631 kW con el factor de 1,11
      a 1,46 en 30 flujos (en la corrida buena respondía: 9510 → 8634 → 8732). Igual antes y
      después de RF-67, así que cambió el proyecto: revisar con una sonda los 6 bancos de
      450 kvar de la calibración fallida, las maniobras y la central de Nasca (¿fuente?).
      Sonda del 2026-10-28 (solo lectura): las 109 cargas de NA205 tienen tensión y consumen
      7,877 MW, sin fuentes dentro; las escaladas están en scale0 0,014 y 0,037 (el factor que
      dejaron corridas con las fijas por su POT) y con 004:RF-67 deben subir ~19 veces: el ajuste
      parte del factor anterior y avanza ~1 % por flujo. Además los bancos BC_CAL_* se acumulan
      entre corridas (NA205 tiene 8: _1, _1_2, _1_3, _2 a _6). Corregir en tools/ajuste_cabecera_pf.py:
      partir de la base de las escaladas (kVA × FP, 015:RF-44) y no repetir bancos ya puestos
      (021:RF-64); después recalibrar Nasca y Chincha y cerrar T1.
      Decisión del usuario (2026-10-28): las centrales y los bancos de NA205 los pone él a mano en
      DIgSILENT (cambio manual, que se respeta). `tools/sistema_web.py` pasa al plan la central del
      perfil solo si trae su `nodo`; el perfil local ya no lo trae.
- [x] T2. Particiones «un sistema fuera» y mínimo de episodios de prueba por familia. (RF-2, RF-3)
      Hecho cuando: `pytest -q tests/test_digital_twin_evaluacion.py` en verde con familias
      sorteadas; ningún sistema en entrenamiento y prueba a la vez.
      Hecho el 2026-10-28: `particionar` por red (huella de sus nodos) y `fallos_de_particion`
      (sin red de prueba o con menos de 10 episodios no se promueve); `entrenar` y `evaluar` lo usan.
- [ ] T3. Escenarios por hipercubo latino del rango de carga medido, en copias del proyecto. (RF-4)
      Hecho cuando: pruebas de `escenarios.py` en verde y una corrida en DIgSILENT con Nasca.
      Hecho el 2026-10-28 (código): `rango_medido` (total coincidente de las cabeceras de la última
      máxima, del valle a la punta + 10 %) y `factores_hipercubo` (una franja por factor, sorteado
      dentro); `gemelo_aprender` los usa y, sin curvas, sigue con los fijos. Falta la corrida en
      DIgSILENT con Nasca, tras su recalibración.
- [x] T4. `Entrenamiento` con paciencia, coseno, recorte de gradiente y mejor época; GRU con
      validación temporal y sin caída a CPU. (RF-5, RF-6, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_digital_twin_oraculo.py tests/test_digital_twin_temporal.py`
      en verde; sin CUDA, error claro.
      Hecho el 2026-10-28: paciencia, `cada`, coseno (`lr_min`) y recorte en `Entrenamiento`; cada
      miembro se valida con la partición de validación y vuelve a su mejor época, que queda con su
      curva en `modelo.json`; la GRU valida con el último 20 % de la serie y `temporal.elegido` usa
      el estacional si no lo mejora (la web también). Sin CUDA, `SinGPU` (sin caída a CPU).
- [x] T5. Manifiesto con commit, huellas, configuración, semilla y dispositivo; reproducción con
      diferencia < 10⁻⁵ p.u. (RF-8, RF-9)
      Hecho cuando: prueba de reproducibilidad en GPU en verde.
      Hecho el 2026-10-28: `manifiesto` en `modelo.json` (episodios por su huella, commit, cfg,
      semillas, GPU, torch y CUDA, modelo del que parte, MAE por familia); entrenamiento con
      algoritmos deterministas (`CUBLAS_WORKSPACE_CONFIG`); `reproducir` y
      `tools/digital_twin_entrenar.py --reproducir VERSION`; reproducido en la GPU con diferencia
      < 10⁻⁵ p.u.
- [x] T6. Búsqueda de hiperparámetros con presupuesto (Optuna, TPE y poda), solo en validación,
      y `tools/digital_twin_entrenar.py --buscar`. (RF-7)
      Hecho cuando: prueba sintética en verde; `--help` sin GPU; informe de ensayos guardado.
      Hecho el 2026-10-28: `digital_twin/hiperparametros.py` (lr, ocultas, pasos, peso físico y
      recorte; TPE con semilla y `MedianPruner` sobre la curva de validación por `al_validar`);
      `--buscar --ensayos --limite-s` guarda los ensayos en `modelos/busquedas/` y entrena con la
      elegida. Optuna en el extra `ml`.
- [x] T7. Intervalo conforme por barra y marca de no confiable. (RF-12, RF-13)
      Hecho cuando: cobertura empírica ≥ la pedida − 2 % en datos sorteados.
      Hecho el 2026-10-28: predicción conforme partida normalizada por la dispersión del conjunto
      (|error|/(σ + 10⁻⁴), cuantil ⌈(n+1)·c⌉), calibrada con la validación y guardada en
      `modelo.json` (`conforme`); `predecir` da `intervalo_pu` por barra y `estado_electrico`
      pide DIgSILENT si es más ancho que la banda de la norma (`confiable`).
- [ ] T8. Top-k verificado en DIgSILENT con `pf_arnes`; descarte, episodio y siguiente;
      gemelo y DIgSILENT en la propuesta. (RF-14 a RF-16)
      Hecho cuando: prueba con `fake_pf` en verde y una propuesta de bancos verificada en
      DIgSILENT con Chincha.
      Avance del 2026-10-28 (código): `optimizar_bancos` devuelve las 3 mejores alternativas que
      cumplen (distintas) y `evolutivo.verificar_top_k` las prueba en orden con la medida de
      DIgSILENT, descarta la que se aparta de la tolerancia (tensión mínima o pérdidas), guarda su
      episodio y da la propuesta con el gemelo y DIgSILENT; las alternativas viajan con las obras
      del PIDE. Falta conectar la medida a `obras_pf.py --evaluar` y la prueba con Chincha.
- [x] T9. Conjunto de órdenes reales del operador, versionado y separado; puertas de tarea y
      datos; confirmación obligatoria mientras sea pequeño. (RF-17 a RF-19)
      Hecho cuando: pruebas del asistente en verde; la web muestra el tamaño del conjunto.
      Hecho el 2026-10-28: puertas de 0,98 y 0,95 en las órdenes reales de la prueba fija, medidas
      aparte de las sintéticas (`Puertas.acierto_real`, `f1_real`); el registro y la pestaña dicen
      cuántas hay de las 200 y que toda escritura pide confirmación hasta entonces.
- [x] T10. Realimentación del error con un único reintento en el ejecutor. (RF-20)
      Hecho cuando: prueba con un error forzado: un reintento y luego vuelta al operador.
      Hecho el 2026-10-28: `ejecutor.revisar_tras_error` da el error al modelo; con la misma tarea y
      datos (fallo pasajero) se reintenta una vez, con otros vuelve al operador con la propuesta
      para confirmar (RF-19); cada decisión queda en el registro `reintentos`.
- [x] T11. (Condicional) LoRA/QLoRA local si T9 no pasa las puertas. (RF-21)
      Hecho cuando: el modelo ajustado pasa RF-18 con el conjunto real, o la tarea se cierra
      con la medida de que no hace falta.
      Cerrada el 2026-10-28 con la medida: el Transformer en uso (20261024-150042-37ce) acierta 1,0
      la tarea y 1,0 el F1 de los datos en las 5 órdenes reales (1 en la prueba fija), sobre las
      puertas de RF-18; LoRA/QLoRA no hace falta. Con 5 órdenes la medida es débil: se repite al
      llegar a las 200 (RF-19), y los pares de preferencia de T15 quedan para un DPO si entonces
      no pasa.
- [x] T12. Deriva, propuesta de reentrenamiento y vuelta atrás desde la web. (RF-22 a RF-24)
      Hecho cuando: pruebas de API en verde y botón en la web compilada.
      Hecho el 2026-10-28: `oraculo.deriva_por_familia` (nuevos y fuera de dominio por familia;
      propone con fuera de dominio, ≥ 10 nuevos o un 20 % más), `--deriva` en la herramienta, ruta
      `POST …/digital-twin/deriva` y `POST /api/modelos/{gemelo|asistente}/volver`; botones «Revisar
      deriva» y «Volver al modelo anterior» en 5.2.
- [x] T13. Carril `engine` en un proceso trabajador con límite de memoria. (RF-25 a RF-27)
      Hecho cuando: `/api/health` < 1 s durante la búsqueda de la máxima de Chincha y un
      trabajo que supera el límite se detiene sin tumbar la API.
      Hecho el 2026-10-28: `JobContext.en_proceso` (proceso `spawn` con Registro, avance y
      cancelación; límite `IGEA_LIMITE_MEMORIA_MB`, 6000 por defecto, vigilado con psutil) y la
      máxima por barra en `demanda_medida.maximas_por_barra`. En la web con Chincha (28 medidores,
      13 barras, 15 s), `/api/health` respondió en 0,031 s como máximo.
- [x] T15. Señal de cada orden (confirmada, corregida, rechazada, fallida) y pares de
      preferencia. (RF-35, RF-36)
      Hecho cuando: pruebas del almacén en verde; la web muestra recompensas y penalizaciones
      acumuladas por tarea.
      Hecho el 2026-10-28: `asistente/senales.py` (confirmada +1; corregida, rechazada y fallida −1;
      pares de preferencia por corrección); botón «Rechazar» y tabla por tarea en el registro.
- [x] T16. Memoria de reflexiones y ejemplos parecidos para Ollama. (RF-37, RF-39)
      Hecho cuando: una orden que falló una vez lleva su nota la siguiente vez (prueba con un
      fallo forzado).
      Hecho el 2026-10-28: nota por fallo o corrección y `contexto_para` (trigramas) con las 5
      confirmadas más parecidas y las notas, que Ollama recibe antes de la orden.
- [x] T17. Umbrales por tarea calibrados con órdenes reales y decisión por impacto. (RF-38, RF-40)
      Hecho cuando: tasa de error empírica ≤ la fijada en el conjunto real de prueba.
      Hecho el 2026-10-28 (código): `senales.calibrar_umbrales` (menor umbral con error ≤ 2 % y al
      menos 10 órdenes de la tarea), calibrado en cada reentrenamiento y usado por el intérprete;
      la decisión por impacto (RF-40) ya la daba el plan. Con 5 órdenes reales aún ninguna tarea
      tiene 10: se calibra cuando el conjunto crezca (RF-17).
- [x] T18. Citas comprobadas y medición de consultas. (RF-41, RF-42)
      Hecho cuando: prueba con una cita falsa sustituida; informe con preguntas reales.
      Hecho el 2026-10-28 (código): `indice.citas_que_no_apoyan` cambia la redacción por los trozos
      si una cita no existe o no comparte términos con su frase; `indice.medir` da la fracción con
      cita correcta y la de «No lo sé» acertados. Falta el informe: no hay aún preguntas reales del
      operador con su fuente esperada.
- [x] T19. Corpus PIDE desde `referencia/PIDEELOR` con `pide_dataset` (texto completo) y su
      auditoría con T0: ficheros, formatos no leídos y fragmentos por artículo. (RF-46, RF-47, RF-51)
      Hecho cuando: el manifiesto cubre los 1397 ficheros con su huella, cada no leído
      (MPP, DWG, RAR) dicho, y `test_pide_dataset` en verde.
      Hecho el 2026-10-28: 1397 ficheros con huella (26 GB, 1015 contenidos distintos, 382
      duplicados), 724 extraídos, 194 que piden lector nativo (107 MPP, 32 PFD, 12 DWG, 19 MSG…)
      y 92 solo metadatos, dichos; 18 620 fragmentos y 2603 de 2625 hojas de Excel con su
      cabecera (antes solo nombre y tamaño); los .xls con calamine y el .docx antiguo con «\»
      leído de su XML. Quedan 2 PDF truncados en el propio expediente (mapas SR0020 y SR0021).
      El 87 % de los fragmentos no tiene artículo por su ruta: lo asigna T20 por contenido.
- [x] T20. Ejemplos del agente desde el corpus: artículo → evidencias y entregables; formato →
      hojas y columnas entregadas; estructura de los informes 4.1 y 4.2. (RF-48, RF-50)
      Hecho cuando: prueba con un corpus sintético; informe del real con los 20 artículos y
      los 15 formatos cubiertos o dichos como ausentes.
      Hecho el 2026-10-28: `asistente/ejemplos_pide.py` y `construir_dataset_pide.py --solo-ejemplos`.
      En PIDEELOR: 20 de 20 artículos con ejemplos de 2021 y 2026 (fragmentos con artículo de 6 758
      a 9 035: el artículo sale también del texto, y «diagnóstico»/«pérdida» con tilde no
      coincidían nunca en `clasificar_ruta`), 15 de 15 formatos con sus hojas y columnas, y las
      secciones del 4.1 (82) y del 4.2 (65); en `output/pide_dataset/PIDEELOR/ejemplos_agente.json`.
- [x] T21. Orquestador del proyecto desde cero, etapa por etapa, con puntos de control y
      reanudación, por las rutas de la web. (RF-43, RF-44)
      Hecho cuando: prueba con `fake_pf` cortada a mitad y reanudada sin repetir etapas.
      Hecho el 2026-10-28 (código): `asistente/orquestador.py`, `POST …/agente/proyecto` (carril
      `asistente`) y «Proyecto desde cero» en la pestaña Asistente; punto de control en
      `agente_proyecto.json` del espacio; prueba cortada en los estudios y retomada sin repetir la
      fuente, el sistema ni el «Caso base». La corrida real desde cero con VNR-GIS es la de T14
      (RF-55).
- [ ] T22. PIDE completo con lo implementado y comparación de cada formato con el entregado.
      (RF-45, RF-49)
      Hecho cuando: F01 a F15 producidos para un sistema, con la fracción de campos coincidentes.
      Avance del 2026-10-28 (código): `ejemplos_pide.comparar_formatos` (palabras y unidades de
      cada campo frente a las celdas de encabezado entregadas) en el resultado del PIDE de la web
      (`comparacion_formatos`) y en `--solo-ejemplos`; los encabezados del conversor coinciden en
      63 de 122 campos con los entregados de PIDEELOR (F10 7/9, F13 9/15; F15 1/4). Falta producir
      F01 a F15 de un sistema en DIgSILENT (con T14).
- [ ] T14. Aceptación: todos los sistemas desde la web con el asistente, gemelo con dos o más
      familias de prueba y asistente con RF-18. (RF-28)
      Hecho cuando: informe con Nasca, Chincha, Pisco e Ica válidos en DIgSILENT y las métricas
      de las puertas, y el agente ejecutó el proyecto desde un espacio vacío hasta el PIDE y
      sus informes (RF-43).
- [ ] T23. El nodo de cabecera con la sigla canónica (`NODE_…_CN101` → `NODE_…_CHN101`) en el DGS,
      sus metadatos y lo que los guiones buscan por él. (022:RF-90)
      Hecho cuando: Chincha reconvertido e importado sin `CN` en sus nombres y calibrado válido
      en DIgSILENT.
      Avance del 2026-10-28 (código): `naming.nombre_canonico` cambia la sigla de cada trozo
      «sigla + número» (`NODE_2030_1192582_CN101` → `…_CHN101`, también `NET_` y `SRC_`) y el DGS
      lo aplica a todos los `loc_name` con las siglas leídas una vez por fichero. Falta reconvertir
      e importar Chincha en DIgSILENT.
- [ ] T24. Episodios por sistema según RF-53 y curva de aprendizaje por familia. (RF-53, RF-54)
      Hecho cuando: informe por sistema con sus 30/10/10 episodios y la curva que dice si ha
      convergido.
      Avance del 2026-10-28 (código): `digital_twin/curva.py` y `digital_twin_entrenar.py --curva`.
      En el búfer real hay una red (IN111–TA225, 2470 nodos) con 14/4/6 episodios: faltan 16/6/4
      para la curva, que se piden con «Aprender» (T3) en cada sistema; el episodio de la
      calibración de Nasca no sale como red entrenable y hay que revisarlo.
- [x] T25. Destilación del modelo local de Ollama al Transformer de órdenes: votos con
      temperatura, filtro por acuerdo, pérdida α·CE + (1 − α)·T²·KL, promoción solo si no empeora
      al alumno sin destilar y registro del maestro. (RF-56 a RF-62)
      Hecho cuando: `pytest -q tests/test_asistente_destilacion.py` en verde con un maestro falso
      sorteado (también uno que no responde) y una corrida real con Ollama en esta máquina.
      Hecho el 2026-10-28: `asistente/destilacion.py`, pérdida en `transformer.entrenar` y
      `tools/asistente_entrenar.py --destilar`; 5 pruebas en verde. Corrida real con llama3.1:8b en
      la GPU: 12 órdenes sin etiqueta, 11 etiquetadas y 1 descartada por acuerdo; el destilado
      acierta 0,982 frente a 0,983 sin destilar en la prueba fija de 541, así que se queda sin
      destilar (RF-60) y el modelo en uso (0,987) sigue. Con 11 órdenes frente a 4070 sintéticas la
      destilación aún no aporta: hará falta con las 200 órdenes reales de RF-17.
- [ ] T26. Claude y Codex como maestros de la destilación: etiquetas de Claude en
      `etiquetas_maestro`, Codex por su CLI con los nombres de la red enmascarados y anotado, y
      `tools/asistente_entrenar.py --destilar --maestro claude|codex|ollama`. (RF-56, RF-63, RF-64)
      Hecho cuando: pruebas en verde (enmascarado y restitución, etiquetas de archivo) y una
      corrida real con las etiquetas de Claude y otra con Codex.
      Avance del 2026-10-28: `MaestroArchivo`, `MaestroCodex` (con `enmascarar` y `reponer`) y
      `--maestro claude|codex|ollama`, `--modelo-codex`; 9 pruebas en verde. Claude etiquetó las 13
      órdenes sin confirmar (5 votos cada una) y, con él de maestro, el alumno acierta 0,985 frente a
      0,980 sin destilar (se usa el destilado); no se promueve porque el modelo en uso acierta 0,987.
      Codex, pendiente: su cuenta de ChatGPT rechaza el modelo configurado (`gpt-5.6-sol`) y también
      gpt-5.5, gpt-5 y gpt-5-codex; falta configurar un modelo que la cuenta admita.
