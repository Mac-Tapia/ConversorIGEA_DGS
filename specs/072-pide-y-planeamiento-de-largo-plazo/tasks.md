# Tareas — Spec 072

- [x] T1 Estudio de planeamiento: año de presentación, año 00 y años calculados. (RF-1, RF-2, RF-3)
      Hecho cuando: prueba con dos años de presentación distintos, sin ningún año en el código.
- [x] T2 Contrato de costos y adaptador SICODI, con cruce por código, tensión, estructura y sector típico. (RF-5, RF-7, RF-8, RF-9)
      Hecho cuando: prueba con los TXT públicos y medida de cuántos tramos de una red real cruzan.
      Medido el 2026-11-02, SICODI de la Res. 184-2026-OS/CD contra los 25 códigos de línea que lista el inventario de una red de ELOR:
      22 con costo y 94,7 % de sus tramos. Los otros 3 terminan en `H`, tensión que el SICODI no trae, y quedan como hueco nombrado.
      Falta declarar la moneda (el TXT no la dice) y el sector típico de cada sistema.
- [ ] T3 Adaptador de módulos estándar de transmisión. (RF-5, RF-6)
      Hecho cuando: el fichero de la resolución está ubicado y una obra de transmisión se valora con él.
- [x] T4 Metrados desde la red. (RF-15)
      Hecho cuando: los metrados de un alimentador real cuadran con sus longitudes.
- [x] T5 Proyección de mercado y prueba contra lo ocurrido. (RF-10, RF-11)
      Hecho cuando: medida contra la tasa de 029 en una prueba sin mirar el futuro.
      Medido el 2026-11-02 con el Formato 01 de `PIDE 2026` de Electro Oriente (energía 2015-2025): 53 sistemas son 9 perfiles
      distintos. Mediana de error a 1, 4 y 8 años: tasa media 3,55/5,92/6,28 %; tendencia 4,58/6,24/6,41 %; tasa de un año
      (referencia) 4,93/7,98/9,40 %; sin crecimiento 4,70/9,30/12,21 %. Corte 2021 → 2025, sobre las 53 series: 12,5 % la tasa
      media y 15,8 % la referencia. Pocos perfiles y una sola empresa: orienta, no generaliza. Faltan variables exógenas (031)
      y la máxima por SET y alimentador.
- [x] T6 Obras acumuladas por año. (RF-12)
      Hecho cuando: en DIgSILENT, sobre un proyecto de prueba, cada año conserva las obras de los anteriores.
      La copia de «Con proyecto» traía todas las obras en todos los años; ahora cada año activa las suyas y las anteriores.
      Medido el 2026-11-02 en DIgSILENT, sobre una copia de L14243 borrada al terminar, con dos variaciones de prueba que acortan un
      tramo. Releído cada caso al final, con flujo convergido: año 00 sin obras, 04 con la A y 08 con las dos, y los largos coinciden.
      Pérdidas sin y con obras: 662,80 y 660,13 kW en el 04; 853,75 y 850,12 kW en el 08. «Con proyecto» original no cambió. No se
      probó con obras reales de la spec 011 ni por la web, que se prueba con el estudio completo (T11).
- [x] T7 Evaluación con y sin proyecto, y F01 a F15. (RF-13, RF-14, RF-16)
      Hecho cuando: pruebas de cada formato, con los huecos nombrados.
      F03 y F04 salen de la tensión de cada barra; F04 mide la barra de baja de cada SED, no el extremo de una red de baja que no está
      modelada, y lo dice. F06 lee el último estudio de confiabilidad guardado. La evaluación con y sin proyecto solo mide el ahorro
      de pérdidas: la energía no servida y la calidad no entran en el flujo.
- [x] T8 Generadores de los módulos del plan y del PIDE. (RF-4, RF-13, RF-14, RF-17, RF-21)
      Hecho cuando: los siete documentos se generan para una empresa de prueba.
      Hecho con una empresa de prueba sintética. Presentan lo medido y sus huecos; no redactan análisis, que es del asistente (T9).
      La revisión del contenido con el usuario sobre una empresa real es T11.
- [ ] T9 Herramientas y entrenamiento del asistente. (RF-18, RF-19)
      Hecho cuando: el asistente completa un estudio por las rutas de la web, y el corpus revisado queda registrado.
- [x] T10 Etiqueta de casos de prueba. (RF-20)
      Hecho cuando: consta en la arquitectura y una prueba lo comprueba.
- [x] T12 El COyM del perfil en la propuesta del PIDE y en F10 a F12. (RF-22)
      Hecho cuando: `pytest -q tests/test_formatos_pide.py -k coym` en verde.
- [ ] T11 Aceptación real de los dos entregables.
      Hecho cuando: el usuario los revisa en una empresa.
