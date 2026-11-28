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
- [x] T9. Enlace directo a Colab en el cuaderno. (RF-17) Hecho cuando: el cuaderno lleva el enlace «Abrir en Colab» y
      `test_el_cuaderno_tiene_su_enlace_directo_a_colab` lo comprueba; evidencia: esa prueba en verde el 2026-11-27. El
      enlace abre el cuaderno de `main`: funciona en cuanto la rama esté integrada.
