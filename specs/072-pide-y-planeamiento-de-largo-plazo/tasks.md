# Tareas — Spec 072

- [x] T1 Estudio de planeamiento: año de presentación, año 00 y años calculados. (RF-1, RF-2, RF-3)
      Hecho cuando: prueba con dos años de presentación distintos, sin ningún año en el código.
- [x] T2 Contrato de costos y adaptador SICODI, con cruce por código, tensión, estructura y sector típico. (RF-5, RF-7, RF-8, RF-9)
      Hecho cuando: prueba con los TXT públicos y medida de cuántos tramos de una red real cruzan.
      Medido el 2026-11-02, SICODI de la Res. 184-2026-OS/CD contra los 25 códigos de línea que lista el inventario de una red de ELOR:
      22 con costo y 94,7 % de sus tramos. Los otros 3 terminan en `H`, tensión que el SICODI no trae, y quedan como hueco nombrado.
      Falta declarar la moneda (el TXT no la dice) y el sector típico de cada sistema.
- [x] T3 Adaptador de módulos estándar de transmisión. (RF-5, RF-6)
      Hecho cuando: el fichero de la resolución está ubicado y una obra de transmisión se valora con él.
      Hecho el 2026-11-06: el adaptador; el fichero real pasa a T13. `costos_fuentes.leer_modulos_transmision` lee un libro de
      módulos por el mismo contrato que el SICODI (ámbito `transmision`, resolución, año, moneda, URL, fecha y huella), con las
      columnas declaradas porque cada resolución cambia la disposición; `valorar_obra` valora cada elemento con la fuente de su
      ámbito, nombra lo que no cruza (sin módulo, sin zona, sin metrado, otra unidad) y suma por moneda sin convertir; y
      `valorar_metrados` rechaza una fuente que no sea de distribución. Evidencia: `pytest -q tests/test_modulos_transmision.py
      tests/test_estudio_y_costos.py`, 37 aprobadas con los tres `CSG_*` de los TXT, sin omitidas. Ubicado el 2026-11-06: la base
      la aprobó la Res. 152-2026-OS/CD y la sustituyó la Res. 181-2026-OS/CD (vigente desde el 26-07-2026, factor de Amazonía 1,0869
      con su sustento en el art. 2), publicada en `https://www.osinergmin.gob.pe/Resoluciones/Resoluciones-GRT-2026.aspx` como carpeta
      «Base de Datos de los Módulos Estándares de Transmisión»; esa página solo enlaza los PDF, y la carpeta no se descargó.
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
- [x] T9 Herramientas del asistente y registro del corpus revisado. (RF-18, RF-19)
      Hecho cuando: el asistente completa un estudio por las rutas de la web, y el corpus revisado queda registrado.
      Hecho el 2026-11-06: la parte de código; la revisión humana real y el entrenamiento pasan a T9b (spec 033: la GPU está en
      pausa por orden del usuario). La orden «haz el pide de P para 2031» propone un plan que espera confirmación y, confirmado,
      va por `POST /pide` con la cola real y deja los siete módulos del plan y del PIDE (072:RF-4); sin año de presentación en la
      orden ni en el perfil, el plan lo pide antes de confirmar, y el del perfil se usa y se dice; el libro CAPEX y el Formato 01
      que nombra la orden van en el cuerpo de la misma ruta, y uno que no existe se dice (`web/asistente_operacion._pide`,
      `asistente/ejecutor`). El corpus: `asistente/corpus_redaccion.py` y `tools/corpus_redaccion_pide.py` registran, en un JSONL
      de solo añadir junto al corpus, la decisión de una persona por fragmento (revisor, fecha, uso `redaccion` o `formato`,
      huella del texto); el maestro no cuenta como revisión humana, «verdad eléctrica» no es un uso, y lo aprobado se exporta con
      las cifras y los códigos de elementos ocultos. Evidencia: `pytest -q tests/test_asistente_planeamiento.py
      tests/test_corpus_redaccion.py`, 11 aprobadas.
- [ ] T9b Revisión humana del corpus PIDE de la empresa de referencia y entrenamiento del asistente con lo aprobado. (RF-19)
      Hecho cuando: el registro `revision_redaccion.jsonl` del corpus real tiene revisiones de una persona, su resumen consta aquí,
      y un modelo entrenado con lo exportado pasa sus puertas (070, 071) sin bajar la prueba sellada.
      Falta: la revisión, que es de una persona (`tools/corpus_redaccion_pide.py --dataset <corpus> --pendientes 20`, luego
      `--decisiones <json> --revisor "<nombre>"`), y el entrenamiento en GPU, en pausa por orden del usuario.
      Relectura P17 (2026-11-08): corpus existente de 12 255 fragmentos elegibles;
      cero revisados y cero aprobados; el registro de revisión no existe. Preparada
      selección revisable de 19 documentos DOCX distintos, con fragmentos y
      procedencia, y plantilla de decisiones sin completar. No se creó ninguna
      revisión humana ni se entrenó; evidencia externa `paralelo_p17_20261108/revision_humana`.
- [x] T10 Etiqueta de casos de prueba. (RF-20)
      Hecho cuando: consta en la arquitectura y una prueba lo comprueba.
- [x] T12 El COyM del perfil en la propuesta del PIDE y en F10 a F12. (RF-22)
      Hecho cuando: `pytest -q tests/test_formatos_pide.py -k coym` en verde.
- [ ] T11 Aceptación real de los dos entregables.
      Hecho cuando: el usuario los revisa en una empresa.
      P17 prepara una comparación de cabeceras declaradas con los ejemplos
      custodiados, sin filas reales ni aprobación: esto no cierra 027 T22 ni T11.
- [ ] T13 Base real de módulos estándar de transmisión y una obra valorada con ella. (RF-5, RF-6, RF-9)
      Hecho cuando: la carpeta de la Res. 181-2026-OS/CD (que sustituye la base de la 152-2026-OS/CD) está descargada fuera de git
      con su URL, fecha y huella, sus columnas declaradas a `leer_modulos_transmision`, y una obra de transmisión de una red real
      queda valorada con `valorar_obra`, con sus huecos nombrados.
      Avance del 2026-11-06, sin cerrar: la carpeta de la 181 no está enlazada ni se halló. La página GRT 2026 y los PDF de las Res.
      152 y 181 y del Informe 567-2026-GRT solo remiten a esa página. Probadas en `.../Resoluciones/pdf/2026/` (y en `www2`, espejo
      del mismo servidor) unas 70 rutas: responden la `Base de Datos de los Módulos Estándares de Transmisión.rar` (506 718 534
      bytes, del 26-07-2026: la publicación de la 152), un `.zip` del 02-03-2026 (proyecto de la Res. 34-2026) y una carpeta suelta
      del mismo nombre con los anexos A a C de marzo; ningún nombre con «RR», «181» o «reconsideración». Descargado fuera de git, en
      `~/.convertersmartgrid/costos/bdme_2026/` con su `fuente.json`: el `.rar` de la 152 (SHA-256 `06da65d4…68bc`) y su libro
      `REST_MOD_INV_2025_PU.xlsm` (SHA-256 `670be02c…60cb`). Ese libro trae una hoja de resumen por tipo de módulo y ninguna
      columna de unidad, así que `leer_modulos_transmision` lee ahora varias hojas y la unidad se declara por hoja (km en las
      siete de líneas y cables, `u` en las ocho de equipos; la hoja de valorización del mismo módulo da 25 km); columnas `CODIGO`,
      `Descripción` y `TOTAL GENERAL (USD)`, moneda USD: 1 651 módulos sin repetidos. Una obra de prueba (SET 60/22,9 kV de 25 MVA en
      costa con 8 km de LT 60 kV AAAC 240) se valora en 2 360 890,48 USD con seis elementos, y quedan nombrados el terreno, que no
      tiene módulo, y un metrado en m frente a un módulo por km. Faltan la carpeta de la 181 (pedirla a la GRT o esperar a que se
      enlace) y una obra de una red real.
      Revalidación primaria P17 (2026-11-08): capturados índice GRT 2026 y PDF de
      la 181 con fecha/URL/SHA; el índice solo enlaza sus PDF, sin carpeta de datos
      actualizada. HEAD de la RAR anterior sigue declarando 506 718 534 bytes y
      fecha 26-07-2026; no se volvió a descargar ni se declaró como base de la 181.
      La moneda y las unidades del archivo actualizado no están acreditadas.
      Evidencia externa `paralelo_p17_20261108/fuentes_oficiales/captura_fuentes.json`.
- [ ] T14 Desde la 098 (2026-11-07): en cada año del PIDE, la obra que pida el año, encima de las anteriores y empezando
      por la de corto plazo del estudio de «Con proyecto» (098:RF-37), con el año en que esta vuelve a fallar
      (098:RF-39, RF-40) como punto de partida. Usuario (2026-11-07): el PIDE se integra como flujo propio, para
      cualquier alimentador y empresa; cubre los años siguientes a los 4 del corto plazo; parte de copias de los casos
      del estudio con su obra de corto plazo ya puesta, y calibra cada año con las proyecciones de demanda de la spec
      de pronóstico (089). Antes, el año 0 a 4 bien hecho (098).
      Contrato autorizado en P17 el 2026-11-08: RF-23 a RF-28. La 089 actual no produce
      proyección anual aceptada: sin ella se bloquea, sin extrapolar sus 28 días.
      Hecho cuando: el modo anual, con proyección aceptada y obras físicas, dé la obra
      de cada año encima de la anterior y su restitución se relea; repetir con datos
      y caso nativo autorizado y conectar el flujo del operador antes de cerrarla.
- [x] T15 Contrato anual y continuación en copias con pruebas CPU. (RF-23 a RF-28)
      Hecho cuando: `pytest -q tests/test_pide_anual.py` compruebe acumulación,
      proyección P/Q trazable, negativas y restitución, sin abrir motor.
      Esta tarea de implementación no sustituye la corrida nativa de T14 ni la
      revisión humana de los entregables de T11.
      Implementado en P17 (2026-11-08): demanda absoluta P/Q equilibrada o por
      fases explícitas, por identidad de carga y con archivo/evaluación anual
      aceptada; copias desde el corto plazo y el año previo; obras físicas solo
      cuando el diagnóstico lo exige; relectura y restitución de cargas,
      escenario, obras, referencias físicas, modo/factor de flujo, etapa/hora.
      Pruebas enfocadas: `test_pide_anual`, `test_pide_pf`, `test_pide`,
      `test_pide_economia`, `test_formatos_pide`, `test_modulos_transmision`:
      95 aprobadas en 3,89 s, sin motor ni GPU. T14 sigue abierta por la demanda
      anual real aceptada, la conexión con el operador y el ensayo nativo.
      Verificación ampliada final: 109 aprobadas en 4,66 s con corpus y ejemplos;
      el CLI del corpus funciona desde checkout y sin `src` adyacente con paquete
      disponible. Corregidos bootstrap y UTF-8 de su salida; las pruebas de
      registro/exportación usan corpus temporal, no el registro real.
- [x] T16 Conexión web anual de RF-18 y RF-23 a RF-28. Conservar el flujo histórico,
      custodiar los tres JSON y rechazar rutas/huellas/identidades inválidas antes
      de encolar. Usar el mismo controlador anual en el carril PowerFactory con
      cancelación cooperativa y reporte de restitución. Mostrar fuentes, bloqueos
      y obras por año en React. Hecho cuando pasen API, render, contrato generado,
      typecheck y build CPU; no cierra T14, T13, T11 ni T9b.
      Implementado y probado en P17 web (2026-11-08): DTO generado, custodia de
      originales/derivado con hashes, rechazo previo a la cola, controlador CLI
      único y cancelación cooperativa. Panel React conserva el flujo histórico;
      muestra obras, fuentes y restitución anual. T14/T13/T11/T9b siguen abiertas.
      Evidencia externa: `paralelo_p17_web_20261108/HANDOFF.md`. Sin PowerFactory,
      GPU, aceptación científica ni revisión visual en navegador.
