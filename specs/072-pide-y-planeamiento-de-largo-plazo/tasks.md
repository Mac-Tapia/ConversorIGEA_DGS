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
- [ ] T6 Obras acumuladas por año. (RF-12)
      Hecho cuando: en DIgSILENT, sobre un proyecto de prueba, cada año conserva las obras de los anteriores.
      Código y simulador hechos el 2026-11-02: la copia de «Con proyecto» traía todas las obras en todos los años, y ahora cada año
      activa las suyas y las anteriores. Falta la prueba real: el simulador comparte las variaciones entre casos y DIgSILENT las
      guarda por caso, así que el aislamiento entre años solo se comprueba allí, leyendo el efecto en el flujo.
- [x] T7 Evaluación con y sin proyecto, y F01 a F15. (RF-13, RF-14, RF-16)
      Hecho cuando: pruebas de cada formato, con los huecos nombrados.
      Hecho con pruebas sintéticas, sin DIgSILENT. F04 sigue vacío porque el modelo no lleva la baja de cada SED, y F06 hasta pasarle
      los índices de 012. La evaluación con y sin proyecto espera las pérdidas de «Con proyecto» por año, que da T6; hasta entonces
      devuelve su hueco. Solo mide el ahorro de pérdidas: la energía no servida y la calidad no entran en el flujo.
- [ ] T8 Generadores de los informes de largo plazo y PIDE. (RF-4, RF-13, RF-14, RF-17)
      Hecho cuando: los dos Word se generan para una empresa de prueba.
- [ ] T9 Herramientas y entrenamiento del asistente. (RF-18, RF-19)
      Hecho cuando: el asistente completa un estudio por las rutas de la web, y el corpus revisado queda registrado.
- [x] T10 Etiqueta de casos de prueba. (RF-20)
      Hecho cuando: consta en la arquitectura y una prueba lo comprueba.
- [ ] T11 Aceptación real de los dos entregables.
      Hecho cuando: el usuario los revisa en una empresa.
