# Tareas 113 — Entrenamiento remoto en Colab con evaluación local

Aprobada por el usuario el 2026-11-26 («Aprobada, impléméntala»), con dos órdenes del mismo día: Colab es una opción que
nunca limita lo local (RF-16) y debe aprovechar Colab Pro («si no, de nada serviría usar Colab»).

- [x] T1. Manifiesto de paquetes y de candidatos, con huellas, revisión y origen. (RF-9, RF-10)
      Hecho cuando: lo de abajo; evidencia: `aplicacion/entrenamiento_remoto.py`; `tests/test_entrenamiento_remoto.py` (113:RF-9, RF-10) en verde.
- [x] T2. Empaquetado con anonimización por familia; los sellados y los crudos nunca entran. (RF-5, RF-6)
      Hecho cuando: lo de abajo; evidencia: modos «texto», «en_origen» (el corpus de redacción, que ya llega anonimizado y lleva sus huellas) y
      «tal_cual»; pruebas con nombres sintéticos de RF-5 y RF-6 en verde.
- [x] T3. `notebooks/ConverterSmartGrid.ipynb`: revisión del paquete, versiones fijadas, Drive, paquete verificado,
      perfil de Colab Pro por GPU, puntos de control y un candidato por semilla. Sin salidas en git.
      (RF-1, RF-2, RF-3, RF-7, RF-8, RF-9, RF-14) Hecho cuando: pruebas del cuaderno; evidencia: pruebas del cuaderno en verde.
- [x] T4. Web: panel «Entrenar en Colab Pro» (previa, confirmación de un solo uso, subida a Drive, enlace de Colab) y
      «Traer los candidatos». (RF-4, RF-10, RF-11, RF-16) Hecho cuando: API y frontend en verde; evidencia: pruebas de API, `typecheck`, `lint`, `npm test` y
      `npm run build` en verde.
- [x] T5. `tools/entrenamiento_remoto.py` para VS Code, con su fila en MANUAL_COMANDOS. (RF-10, RF-14)
      Hecho cuando: lo de abajo; evidencia: `--help` y `opciones` probados; índices al día.
- [x] T6. Aviso de datos nuevos en la web para reentrenar. (RF-13) Hecho cuando: la web lo avisa al crecer el dataset
      preparado; evidencia: `registrar_preparado` anota en el almacén del asistente (`colab/preparados.json`) la carpeta
      y los ejemplos de cada paquete (web y `tools/entrenamiento_remoto.py preparar`), `avisos_de_reentreno` los vuelve
      a contar y `GET /api/entrenamiento/colab` los da en `reentrenar`; el panel «Entrenar en Colab Pro» lo enseña;
      `test_el_registro_avisa_cuando_el_dataset_crecio` y `test_la_web_prepara_solo_con_la_confirmacion_del_operador`.
      Límite: cuenta la carpeta que se empaquetó; un corpus reconstruido en otra carpeta se prepara como paquete nuevo.
- [ ] T7. [Colab] Ensayo real: el corpus de redacción de la 072 en una A100, tiempos medidos y candidato traído por su
      puerta local (`asistente_qlora.py evaluar`). (RF-4 a RF-12) Hecho cuando: la evidencia consta aquí.
- [ ] T8. Las demás familias (intérprete, PINN y gemelo, pronóstico, MADRL/MASAC), cada una con su orden comprobada
      con un ensayo corto antes de entrar en `FAMILIAS`, y los paquetes VNR-GIS públicos (RF-15). Hecho cuando: cada
      familia tiene su prueba y su ensayo corto.
      Avance del 2026-11-27: entran `pronostico_demanda` (089, `tools/pronostico_demanda.py --dataset`, tal cual) y
      `madrl_obras` (074, GATv2 de `tools/madrl_entrenar.py`, tal cual, puerta `tools/madrl_puerta.py aplicar`), cada
      una ensayada como en Colab: datos sintéticos empaquetados con `preparar_paquete`, la orden de `FAMILIAS` desde la
      carpeta `datos` del paquete, el paquete intacto tras entrenar y el candidato traído sin activarse (MADRL en CUDA
      con su turno, 252 s; pronóstico con `--pasos 10 --lote 16` añadidos solo al ensayo, los cinco modelos
      EVALUADO); el cuaderno añade `--experimento-autorizado` solo a la familia que lo declara (`autorizar`), porque los
      demás guiones lo rechazarían. Pruebas `test_cada_familia_entrena_con_una_orden_de_tools_y_su_puerta_local`,
      `test_la_orden_de_cada_familia_lleva_sus_datos_su_salida_y_su_semilla`, `test_las_ordenes_son_las_ensayadas` y
      `test_solo_el_qlora_pide_su_experimento_autorizado`. Falta, porque su guion no entrena desde un paquete: el
      intérprete (`asistente_entrenar.py` lee el almacén o un dataset v2 que exige `test.jsonl`, sellado por RF-6:
      necesita un modo «solo entrenar» y una puerta local sobre la prueba sellada); la PINN (`digital_twin_entrenar.py`
      escribe modelos e índice dentro del búfer y su partición de prueba viaja con él: necesita una salida de modelos
      aparte y la prueba fuera del paquete); la GRU temporal (`digital_twin_temporal_entrenar.py` lee libros crudos; la
      GRU ya compite dentro de `pronostico_demanda`); MASAC (114, en borrador, sin guion); y los paquetes VNR-GIS (RF-15).
      Avance del 2026-11-27 (noche, rama `agente/colab-113-t8b`): entra `interprete_ordenes` (069/079, RF-18 a RF-20,
      `en_origen`). `asistente_entrenar.py --preparar-colab` construye en el equipo el corpus integral de siempre y saca
      solo entrenamiento y selección, con proyectos, SED, SET, casos, estudios y rutas seudonimizados (misma forma,
      sal en el almacén) y el texto libre por `sin_nombres`; `--solo-entrenar` entrena y elige en Colab con
      `--afinar`; `--examinar-colab CANDIDATO --corpus CORPUS` es la puerta local. `entrenar_destilacion` se partió en
      `_entrenar_y_elegir` y `_examinar` sin cambiar lo que hace (138 pruebas vecinas en verde). Pruebas:
      `test_el_interprete_entrena_en_colab_y_se_examina_aqui`, `test_colab_no_entrena_con_la_prueba`,
      `test_el_seudonimo_guarda_la_forma_y_no_el_nombre`, `test_la_fila_sin_nombres_conserva_sus_datos`,
      `test_los_modos_de_colab_del_interprete_van_solos_y_su_puerta_decide_aqui` y
      `test_entran_en_colab_las_familias_ensayadas`. Ensayo corto, fase sin GPU, desde un almacén sintético: corpus
      completo de 67 048 filas, salen 60 434 (entrenamiento y selección), 20 204 proyectos seudonimizados, paquete
      verificado y releído por `leer_corpus`. Falta la fase con GPU del ensayo (`--solo-entrenar` desde `datos` y
      `--examinar-colab`), lista en `D:/csg/PM_IMPL/T8b_113/ensayo_interprete.py entrenar`, para cuando haya turno.
      Validación cruzada (RF-21, excepción a RF-6 autorizada por el usuario el 2026-11-27): entra
      `interprete_ordenes_cruzada`. `--preparar-colab --validacion-cruzada` añade `confirmadas.json` con las órdenes
      humanas sin nombres y lo que entrena de cada una ya filtrado aquí frente a lo que mide
      (`validacion_cruzada.preparar_confirmadas`); Colab hace las vueltas y el modelo final (`--solo-entrenar
      --validacion-cruzada`) y deja `validacion_colab.json`; `--examinar-colab` lee la medida fuera de grupo con la
      sal de aquí (`FueraDeGrupoColab`). Pruebas `test_la_validacion_cruzada_va_a_colab_solo_con_las_confirmadas_sin_nombres`
      y `test_sin_pedirla_ninguna_orden_humana_sale`. El primer ensayo sin GPU encontró dos fugas en el texto libre de
      las confirmadas: «Zafiro», palabra de un proyecto, fuera de los datos de su frase, y «Inventado SA», razón social
      sin puntos; ahora se ocultan con un catálogo local (`catalogo_colab`: vocabulario, datos de las humanas y sus
      palabras, guardado junto al corpus completo, que no sale) y con la razón social sin puntos
      (`test_la_razon_social_sin_puntos_no_sale`, rojo por aserción y verde). Ensayo sin GPU repetido
      (`D:/csg/PM_IMPL/T8b_113/ensayo_interprete_vc.log`): 7 confirmadas salen (4 entrenan, 64 variantes), ningún nombre
      inventado sale y ninguna de las 6 739 filas de calibración y prueba entra en el paquete. Falta su fase con GPU.
      Siguen fuera: la PINN (hace falta `--preparar-colab` con los episodios de entrenamiento, validación y
      calibración de `muestras_y_particiones`, `--solo-entrenar` con una carpeta de modelos aparte y `--examinar-colab`
      con las puertas de `oraculo.entrenar` sacadas a una función; no se hizo porque esas puertas solo se prueban en
      CUDA, y la GPU no estaba libre); la GRU temporal (su red es pequeña y cabe en el equipo, lee libros crudos, y la GRU
      de la 089 ya va a Colab dentro de `pronostico_demanda`): se queda fuera con ese motivo; y MASAC (114, borrador).
- [x] T9. Enlace directo a Colab en el cuaderno. (RF-17) Hecho cuando: el cuaderno lleva el enlace «Abrir en Colab» y
      `test_el_cuaderno_tiene_su_enlace_directo_a_colab` lo comprueba; evidencia: esa prueba en verde el 2026-11-27. El
      enlace abre el cuaderno de `main`: funciona en cuanto la rama esté integrada.
- [x] T10 LUGARES-SIN-NOMBRE (28-11). El nombre de un lugar tras su clase no sale a Colab. (RF-22)
      Hecho cuando: `tests/test_interprete_codificador.py` (113:RF-22) en verde con su rojo por aserción, y el paquete del
      intérprete preparado con las órdenes reales sin ningún nombre de lugar. Hecho el 2026-11-28 (evidencia en el commit
      que lo integra).
- [x] T11 GRAFOS-SIN-NOMBRES (28-11). El grafo de MADRL sale con seudónimos y la misma red. (RF-23)
      Hecho cuando: `tests/test_entrenamiento_remoto.py` (113:RF-23) en verde con su rojo por aserción, y el paquete
      `madrl_obras` de LL203 sin ningún nombre (comprobado: ni el cliente de la barra ni la estructura del proyecto) y con
      677 nodos, 680 ramas y 22 zonas como el original. Hecho el 2026-11-28.
