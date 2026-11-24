# Tareas 031

- [x] T1. Competición, métricas y elección por magnitud y clase. (RF-2, RF-3, RF-4, RF-8, RF-13, RF-14)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k "competicion or eleccion"` en verde.
      Hecho el 2026-11-08: 10 pruebas en verde.
- [x] T6. Formato 01 construido con la medición de cabecera, con sus meses por año. (RF-15, RF-8)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k formato` en verde.
      Hecho el 2026-11-08: 8 pruebas en verde.
- [x] T2. Emisión de todos los años con banda, reparto por carga y evaluación que lee 072. (RF-5, RF-6, RF-7, RF-9, RF-12, RF-16)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k "emision or contrato"` en verde.
      Hecho el 2026-11-08: 16 pruebas en verde.
- [x] T3. El PIDE pronostica primero y las obras leen la proyección aceptada. (RF-1, RF-11)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k "pide or obras"` en verde.
      Hecho el 2026-11-08: 7 pruebas en verde. Residuo: con proyección aceptada el PIDE recibe una tasa equivalente por alimentador; el valor de cada año exige las identidades `.ElmLod` del modo anual.
- [x] T4. Los modelos neuronales compiten en el ciclo común y el ganador publicado ancla el año base. (RF-2, RF-10)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k ciclo` en verde.
      Desbloqueada el 2026-11-17: el integrador le dio dueño (f7) con el pronóstico de la 089 ya integrado.
      Hecho en esta entrega (LOTE-2); pruebas: tests/test_proyeccion_anual.py -k ciclo. RF-2: compiten en la etapa `gru` del
      ciclo (`orden_temporal`); RF-10: `proyeccion_anual.ganador_del_ciclo` lee el conjunto activo (`miembro_en_uso`) y su
      `pronostico.json`, y la evaluación anota `ciclo_comun`. La corrida real con GPU es la T5.
- [x] T5. Corrida real: proyección de un sistema con sus métricas por modelo y el ganador anotados aquí. (Todos)
      Hecho cuando: el informe está fuera de git y el resumen, sin datos de la distribuidora, anotado aquí.
      Bloqueada por datos y carril (2026-11-14, T0b de e6): la corrida real necesita los libros de la empresa, el registro de PBI y población del INEI y el BCRP de su región y el turno de GPU; el encargo prohíbe descargas, datos reales pesados y GPU (`D:/csg/PM_IMPL/ENCARGOS_E6.md`, «Prohibiciones»). Siguiente acción: el operador carga el registro y e6 la pone en el corredor.
      Hecho el 2026-11-23 (d8, corrida de la T11, informe `GPU_BLOQUE/031_T11_noche/corrida_p6`, fuera de git, con su
      espejo verificado por sha256 en Drive). Horizonte de 30 años, paso de 6 meses entre orígenes, 4 orígenes por modelo.
      WAPE de la demanda media mensual en los orígenes de elección (%), por grupo:
      cliente kW: sin crecimiento 31,0 · TiDE 31,5 · perfil calendario 31,8 · perfil anclado 31,9 · semanal 32,2 ·
      TFT 33,2 · N-HiTS 35,0 · PatchTST 35,7. Cliente kVAR: perfil calendario 35,5 · perfil anclado 35,9 · sin
      crecimiento, semanal y TiDE 36,4 · TFT 37,3 · N-HiTS 40,9 · PatchTST 41,5. Escaladas kW: perfil anclado y semanal
      18,6 · perfil calendario 18,7 · TiDE 18,9 · sin crecimiento 19,4 · N-HiTS 19,7 · PatchTST 20,0 · TFT 28,2.
      Escaladas kVAR: PatchTST 64,2 · N-HiTS 66,0 · perfil anclado 71,7 · semanal 72,2 · TiDE 75,5 · perfil calendario
      76,9 · sin crecimiento 79,4 · TFT 114,9. Las tasas anuales no aplican: con esta historia no alcanzan 3 orígenes.
      Ganador en los cuatro grupos: **sin crecimiento**, la referencia, porque ninguno pasa la regla (mejora de 2 % o más
      sin peor error en la máxima y con cobertura); en escaladas kVAR N-HiTS baja el WAPE de 79,4 a 66,0, pero su error en la máxima es 21,8 frente a 21,7.
      Estado `sin_aceptar`: 0 de 30 años validados (10 meses medidos); validarlos pide más historia o la orden expresa
      del operador (RF de aceptación), sin PBI ni población del INEI, que no se cargaron.
- [x] T9. Las redes del PIDE caben en la GPU de 8 GiB: lote de series por la memoria libre medida, reintento y causa escrita, y predicción con solo su contexto. (RF-24, RF-25, RF-26)
      Hecho cuando: `pytest -q tests/test_pronostico_memoria_gpu.py` en verde, con su rojo sobre la base sin el cambio. La corrida real con la GPU es la T5.
      Hecho el 2026-11-20 (MEJ14-GPU031): rojo con 8 fallos por aserción sobre la base y verde con 9; ensayo corto en la GPU con el dataset de la T12 (10 pasos): N-HiTS entrena en los cuatro grupos, donde antes los clientes daban «no disponible», y abrir el dataset baja de 3,07 a 1,72 GiB.
- [x] T10. Estrategia de horizonte largo: 15 minutos solo en el horizonte corto y resolución horaria o diaria (o la forma anual) para el largo, para que las cuatro redes quepan en la GPU sin recortar redes ni orígenes. (RF-2, RF-17, RF-24, RF-27, RF-28, RF-29)
      Hecho cuando: la corrida de la T5 hace competir N-HiTS, TFT, PatchTST y TiDE en todos sus orígenes sin ninguna `memoria_gpu`, con su prueba de que el horizonte corto sigue a 15 minutos.
      Medido el 2026-11-20 (MEJ14-GPU031) con un horizonte de un año a 15 minutos (35 040 a 38 016 registros) y un contexto de 2 688: al entrenar, con sus gradientes y Adam, N-HiTS pide 4,37 GiB (293,5 M de parámetros), TiDE 22,7 GiB (1 522,8 M) y PatchTST 24,4 GiB (1 635,5 M; su cabeza sola, 6,09 GiB); TFT tiene 1,7 M de parámetros, pero su atención sobre contexto + horizonte pidió 24,69 GiB con una sola serie. Las ventanas de una serie piden de 0,10 a 0,72 GiB. En una tarjeta de 8 GiB solo N-HiTS cabe; las otras tres salen `NO_DISPONIBLE` con su causa (RF-25).
      Hecho el 2026-11-20 (MEJ16-HORIZONTE): por encima de 31 días las redes aprenden la serie diaria del objetivo (media y máxima del resto sobre su perfil anclado, contexto de hasta 364 días) y la curva de 15 minutos sale de su perfil; en la competición del PIDE las cuatro redes usan la diaria en todos los orígenes. Con un año de horizonte diario: TiDE 0,26 GiB, N-HiTS 0,10, PatchTST 0,04 y NBEATSx 0,14 al entrenar; hasta 31 días siguen a 15 minutos. Pruebas: tests/test_pronostico_horizonte_largo.py (rojo por aserción sobre la base y verde). La corrida real con la GPU es la T5.
- [x] T7. Lanzador del PIDE en la GPU en un paso, sin ganador fijo ni series inventadas. (RF-17, RF-18)
      Hecho cuando: `tests/test_lanzar_pronostico_pide_gpu.py` en verde y `--help` responde.
- [x] T8. PBI y población como exógenas anuales, con su fuente, su huella y su fecha de publicación, en la competición y en la emisión. (RF-19, RF-20, RF-21, RF-22, RF-23)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual_exogenas.py` en verde, con la prueba de que una cifra publicada después del origen se rechaza.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_proyeccion_anual_exogenas.py.
- [x] T11. Un año de contexto para todas las series del PIDE, con relleno inicial. (RF-30)
      Hecho cuando: `pytest -q tests/test_pronostico_horizonte_largo.py` en verde con su rojo por aserción en la base, y
      la emisión de la T5 sale con las redes y sin «requires at least 364 training timestamp(s)».
      Hecho el 2026-11-23 (d8, N10): rojo por aserción sobre b5e0c45f (`N10_SINCODEX/T17/rojo_base_1825.log`) y verde
      (`N10_SINCODEX/T19/verde_2155.log`). Corrida real en la GPU, 2026-11-23 19:03–20:45 (cola de d8, paso
      `32_031T11_pide_n10`, informe en `GPU_BLOQUE/031_T11_noche/corrida_p6`, fuera de git): N-HiTS, TFT, PatchTST y
      TiDE entrenan y emiten en los cuatro grupos y en sus cuatro orígenes, con contexto de 364 días, sin ningún
      «requires at least 364 training timestamp(s)» y sin `memoria_gpu`.
