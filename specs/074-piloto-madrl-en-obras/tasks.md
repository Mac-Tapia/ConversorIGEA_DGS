# Tareas — Spec 074

- [x] T1 Entorno, máscara y penalidades. (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: pruebas de la máscara, del grafo intacto y de los multiplicadores.
- [x] T2 Controles y puerta. (RF-5, RF-6)
      Hecho cuando: NSGA-II iguala a la fuerza bruta en una red pequeña y la puerta rechaza lo barato fuera de norma.
- [x] T3 Fidelidad contra DIgSILENT. (RF-7)
      Hecho cuando: se mide en episodios reales.
      Medido el 2026-11-02 sobre 5 redes del búfer: ninguna con problemas pasa. NJA202 tiene 0,047 p.u. de error medio; CA101 y SM218
      pasan en tensión media, pero su peor rama falla (150 y 245 puntos); `0205` pasa, y no tiene problemas que resolver.
      En esas redes, solo con bancos, ni la escalera ni NSGA-II llegan a norma.
- [x] T4 Captura de transformadores en paralelo y largo de cada tramo. (RF-8)
      Hecho cuando: la prueba con el simulador los recoge.
      El error de carga estaba en los transformadores, casi siempre del doble en SM218: el grafo ignoraba `ntnum`.
- [ ] T5 Volver a capturar y a medir. (RF-5, RF-7)
      Hecho cuando: en DIgSILENT se confirma `ntnum` y al menos una red con problemas pasa la fidelidad. Requiere turno de DIgSILENT
      sobre proyectos de prueba. Los episodios ya guardados conservan el grafo antiguo.
- [x] T6 Dependencias del aprendizaje en un entorno aparte. (RF-9)
      Hecho cuando: TorchRL y `sb3_contrib` corren con la versión de PyTorch del proyecto sin cambiar el `.venv` compartido.
      Verificado el 2026-11-02 con `requirements-madrl.txt` en `~/.convertersmartgrid/madrl_deps`: importan con torch 2.14.1 y GATv2
      responde. MaskablePPO, en CPU, 8 192 pasos y 3 semillas, llega a los 5 bancos de NSGA-II en una red sintética. Es la misma red
      de entrenamiento y solo prueba el montaje. Antes aprendió a no hacer nada, porque rendirse salía más barato: de ahí RF-4.
- [ ] T7 Entrenar, con su control. (RF-4, RF-9)
      Escrita la política GATv2 con crítico central (`madrl_politica.py`), probada en CPU el 2026-11-02 con redes sintéticas: aprende
      (retorno de -9,3 a -4,9) pero, en 3 redes que no vio, paga un banco más que NSGA-II en dos y en la tercera nadie llega a
      norma; la puerta la rechaza (67 %). Falta entrenarla en GPU sobre redes reales que pasen T5.
      Hecho cuando: GATv2 con crítico central y MaskablePPO entrenan con turno de GPU sobre redes que pasen T5. Antes de los modelos
      sanos de la auditoría no se entrena.
- [ ] T8 Puerta y confirmación. (RF-6, RF-10)
      Hecho cuando: la puerta se aplica en alimentadores no vistos y lo elegido se confirma en DIgSILENT. Si no pasa, el piloto se
      archiva con su medida, sin integrarlo en el flujo.
