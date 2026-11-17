# Spec 108 — Estudio de costos del VAD con la empresa modelo eficiente

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-18, y orden del usuario del 2026-11-14:
«haz nuevos spec». G0: `D:/csg/G0_PLAN_MAESTRO/D/D_FILAS_BP.md` y `MATRIZ_PIDE_NORMA_FORMULA_VARIABLE.md`.

## Contexto y objetivo
Osinergmin fija el VAD por grupos de empresas: grupo 1, 2026–2030; grupo 2, 2027–2031. Los términos de referencia
están en la RCD 174-2025-OS/CD y la 033-2026-OS/CD. El estudio se hace en cuatro etapas: recopilación, empresa modelo
eficiente, cargos adicionales y VAD. Sus anexos piden la caracterización de la carga (anexo 4), el modelo geométrico
urbano (anexo 5) y el modelo georreferenciado rural, que **conserva la traza real de MT/BT** y las SED reales (anexo 6).
G0 encontró que el conversor solo lee el VNR (RCD 184-2026) y cita el TdR en comentarios: no hay ningún flujo VAD. El
conversor ya tiene lo que el anexo 6 necesita (trazas reales, SED y demanda medida), pero **VNR real ≠ red óptima de la
empresa modelo**: esta spec crea ese cálculo separado.

## Usuarios / actores
- Equipo de regulación de la concesionaria que prepara su estudio de costos.
- Revisor que reproduce los libros.

## Historias de usuario
- H1: Como regulación, quiero armar la empresa modelo de un sistema típico desde el inventario VNR y la demanda
  medida, conservando las trazas reales en el modelo rural, para sustentar los costos del estudio.
- H2: Como revisor, quiero cada tabla del estudio con la fuente, la versión del TdR y la fórmula de cada celda.

## Requisitos funcionales (EARS)
- RF-1: EL SISTEMA guardará el estudio VAD aparte del PIDE y del PIT, con su grupo, su periodo y su empresa.
- RF-2: CUANDO el operador cargue el inventario VNR, las tablas técnicas, comerciales y contables y los costos de un
  sistema, EL SISTEMA validará cada tabla contra el formato del anexo 2 vigente, con sus unidades y su periodo.
- RF-3: SI una tabla obligatoria falta o trae unidades distintas de las del anexo, ENTONCES EL SISTEMA lo dirá por
  tabla y campo, sin rellenarla.
- RF-4: EL SISTEMA caracterizará la carga del sistema (factor de carga, simultaneidad y curvas MT/BT) desde la
  medición del conversor, según el anexo 4.
- RF-5: CUANDO se arme el modelo georreferenciado rural, EL SISTEMA usará las trazas MT/BT, las longitudes y las SED
  reales del VNR sin alterar ningún vértice, y distinguirá la troncal de las derivaciones.
- RF-6: CUANDO se arme el modelo geométrico urbano, EL SISTEMA elegirá la red adaptada por densidad de carga según el
  anexo 5.
- RF-7: EL SISTEMA dimensionará la red de la empresa modelo (conductor, transformación y pérdidas) con el motor
  físico, y nunca dará como costo estándar el costo real del VNR sin ese cálculo.
- RF-8: EL SISTEMA calculará el COyM técnico (anexo 7), las pérdidas estándar y el balance de potencia y energía por
  sistema y tensión.
- RF-9: EL SISTEMA guardará con cada fórmula y cada parámetro el anexo, la versión del TdR, su estado jurídico y la
  moneda, con el IGV incluido o excluido según lo exija el anexo.
- RF-10: SI el TdR aplicable al grupo o al periodo no está registrado como vigente, ENTONCES EL SISTEMA no emitirá
  el estudio como conforme.
- RF-11: CUANDO se emitan los entregables, EL SISTEMA generará las tablas A y B en Excel con sus fórmulas, los mapas
  de densidad (anexo 9) y el manifiesto de fuentes con sus huellas.
- Aclaración de RF-11 (2026-11-14): entre los entregables están las Tablas de Resultados que liste el TdR registrado
  (numeral 9), una hoja por tabla, en el orden y con el título del registro y con las filas por sistema eléctrico. El
  número de tablas no está fijado: lo da el registro (el TdR del periodo 2026-2030 lista 16). Una tabla sin datos se
  entrega como hueco nombrado, nunca vacía en silencio. Absorbe el RF-16 propuesto en el inventario de entregables de
  Osinergmin (veredicto 7e del 2026-11-14).
- Aclaración de RF-11 (2026-11-15, T9 y T10): las «tablas A y B» son los Formatos A y Formatos B del anexo 2: el informe
  del estudio incluye «los Formatos del Anexo N° 2 (Formatos A y Formatos B)» (numeral 9 del anexo de los TdR
  registrado, línea 3418 de la copia de texto de sha256 48ea8cf4…), con el prefijo «A» para la información de la
  empresa y el «B» para la empresa modelo (líneas 2741-2745). Cada celda calculada lleva la fórmula de Excel traducida
  de la fórmula transcrita del anexo 2; un total sin fórmula transcrita, o una fórmula que no se traduce sin suponer,
  queda como hueco nombrado, sin valor. El TdR publica los formatos dentro del PDF, sin libro Excel modelo. El
  anexo 9 fija las entidades y sus campos (nombre, orden, tipo, ancho y decimales), no nombres de carpetas ni de
  ficheros: cada entidad se entrega en un fichero con su nombre.
- RF-12: EL SISTEMA registrará las observaciones del regulador con su respuesta y la tabla o el cálculo al que
  afectan.
- Aclaración de RF-12 (2026-11-14): con las observaciones respondidas, EL SISTEMA generará el Informe Definitivo con
  los documentos que liste el TdR registrado (numeral 9.2), y en el informe de respuestas cada respuesta llevará su
  sustento y la tabla o el cálculo que cambió. Absorbe el RF-20 propuesto en el inventario (veredicto 7e).
- RF-13: EL SISTEMA no tendrá valores de una empresa, de un sistema típico ni de un periodo en el código (P13).
- RF-14: EL SISTEMA generará el Informe de Resultados Relevantes con los apartados del anexo 3 del TdR registrado.
- RF-15: EL SISTEMA generará el Informe del Estudio con la estructura del numeral 9 del TdR registrado, en Word y en
  un PDF integrado.
- RF-16: EL SISTEMA calculará el cargo fijo y el VAD de cada nivel de tensión, con las variantes, las fórmulas y los
  coeficientes del numeral 8 del TdR registrado, y también el factor de economía de escala y la fórmula de reajuste.
- RF-17: DONDE el estudio declare la empresa dentro del ámbito del FONAFE, EL SISTEMA incorporará al VAD la inversión,
  el COyM y la demanda del PIDE aprobado que le entregue la spec 072, con la fórmula del TdR registrado.
- RF-18: EL SISTEMA verificará la calidad de servicio de la empresa modelo con los indicadores y los límites del
  registro normativo, y dirá qué indicador no cumple.
- RF-19: EL SISTEMA dimensionará el VNR no eléctrico y los costos comerciales, indirectos y adicionales de la empresa
  modelo por los rubros del TdR registrado, y el costo real solo entrará como referencia rotulada.
- RF-20: EL SISTEMA registrará la «Guía de Elaboración del VNR de las Instalaciones de Distribución Eléctrica» (RCD
  232-2017-OS/CD) con su vigencia según su art. 2, y cada regla del cálculo del VNR citará su artículo o anexo; las
  tablas de equivalencia del Anexo 6 saldrán del texto oficial con su huella, nunca escritas a mano.
- RF-21: CUANDO el operador pida la zonificación de una concesión, EL SISTEMA calculará la densidad de carga por
  cuadrículas UTM de 1000, 500 y 250 m con la máxima demanda de las SED del año previo, asignará las zonas de la Tabla
  N° 1 del art. 22, aplicará la zona predominante a la cuadrícula aislada, eliminará las de densidad cero y dará un
  mapa de MT (todas las SED) y otro de BT (las SED de uso no industrial).
- RF-22: EL SISTEMA adaptará el metrado de cada instalación eléctrica con los criterios de su sector típico, su zona y
  su ambiente (arts. 23 a 44), y con las tablas del Anexo 6 para el cambio de tensión y de tecnología; cada tramo
  conservará su metrado existente junto al adaptado y la regla que lo cambió.
- RF-23: EL SISTEMA calculará el VNR al 31 de diciembre del año que corresponda como VNR = MIE × CEIE + MINE × CINE
  (art. 17.2), con los costos estándar de inversión de la última fijación (art. 12.1) tomados del libro SICODI
  registrado (`CSG_SICODI`); una instalación sin costo estándar quedará como hueco nombrado, nunca como cero.
- RF-24: EL SISTEMA entregará el VNR en los formatos de valorización y metrados del Anexo 5 (A1, B1, C1 y D1). El VNR
  adaptado de las instalaciones reales es la entrada de la verificación de la TIR de la empresa (arts. 70 y 71 de la
  LCE, citados por la RCD 232-2017) y se contrasta con el costo estándar de la empresa modelo con su anualidad
  calculada con los mismos factores del VAD; el aVNR del VAD sigue saliendo de la empresa modelo, nunca del VNR real.
- RF-25: CUANDO el operador cargue dos inventarios VNR consecutivos de una empresa, EL SISTEMA determinará las altas y
  bajas del año (art. 18) por instalación y su efecto en el VNR.
- RF-26: EL SISTEMA ofrecerá el estudio del VAD en su pestaña de la web, «Estudio VAD», como el VNR y el PIT: crear el
  estudio, subir el caso y armar la empresa modelo como trabajo con el estado de cada sistema, registrar y responder las
  observaciones del regulador, armar el Informe Definitivo como trabajo con cada documento sin fuente nombrado como
  hueco, y descargar las salidas del estudio. Cada ruta de la web del VAD tendrá su control en la pantalla.

## Requisitos no funcionales
- Fidelidad geométrica: el hash de los vértices de cada tramo del modelo rural coincide con el del VNR.
- El armado de la empresa modelo es un trabajo en cola, cancelable (P7).
- Universal: las pruebas usan al menos dos empresas sintéticas.

## Casos límite
- Un sistema con zonas urbanas y rurales a la vez.
- Un VNR sin la geometría de parte de la BT.
- Un cambio del TdR a mitad del estudio.
- Una SED sin medición.

## Fuera de alcance
- La fijación tarifaria.
- El plan SMI (anexo 8) y los cargos adicionales de innovación, que se tratan en una iteración posterior.
- Copiar resultados de estudios anteriores: solo se aprende su estructura.
- Declarar el estudio «aprobado».
- Escribir en la spec 072: el contrato 072 → 108 de RF-17 lo redacta la tarjeta que lleva la 072.

## Criterios de finalización
Cada RF citado por una prueba (`grep "108:RF-"`). El modelo rural conserva el hash de los vértices del VNR. Un libro
de un estudio publicado se reproduce en su estructura con una empresa autorizada, y un revisor coteja una muestra de
celdas.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario («debes hacer lo recomendado, piensa como un humano»), en
`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 3.
- Primer caso: una empresa del grupo de fijación vigente, **solo como caso de prueba**. Su nombre, su grupo y su
  sistema típico van en el perfil local, nunca en la spec, el código ni las pruebas (P13; usuario, 2026-11-14: «VAD,
  PIT y PIDE siguen siendo universales; los archivos reales son de prueba»). Su grupo se deduce de la resolución
  vigente que publica la agrupación y se comprueba en su anexo.
- Primera iteración: el anexo 6 rural, que reutiliza las trazas reales. El anexo 5 urbano (RF-6) viene después, en
  una tarea propia.
- Costos estándar: los del catálogo SICODI con `valorar_obra`, con la fuente anotada en cada elemento.

## Enmienda del 2026-11-14 (inventario de entregables de Osinergmin)
Origen: `D:/csg/PM_IMPL/OSINERGMIN_ENTREGABLES/INVENTARIO.md`, sección 4, y el veredicto de 7e
(`D:/csg/AUDITORIA/VEREDICTO_INVENTARIO_OSINERGMIN_7e.md`, con su corrección de las 20:20). La numeración vigente no
se toca: los RF aceptados toman los siguientes números libres y los que se absorbieron como aclaración nunca se
definieron.

| Propuesto en el inventario | Aquí |
| --- | --- |
| RF-14, Resultados Relevantes (anexo 3) | RF-14 |
| RF-15, Informe del Estudio (numeral 9) | RF-15 |
| RF-16, las Tablas de Resultados | Aclaración de RF-11 |
| RF-17, CF, VAD, variantes, FEE y reajuste (numeral 8) | RF-16 |
| RF-18, incorporación del PIDE (numeral 7.5) | RF-17 |
| RF-19, calidad de servicio (numeral 6.11) | RF-18 |
| RF-20, Informe Definitivo (numeral 9.2) | Aclaración de RF-12 |
| RF-21, VNR no eléctrico y costos de explotación (6.8.3, 6.13 a 6.15) | RF-19 |

Las listas (tablas, apartados, estructura, conceptos, variantes, indicadores y rubros), las fórmulas y los
coeficientes salen del registro normativo (RF-9, RF-13): un periodo nuevo cambia el registro, no el código. Lo que el
TdR no da en forma cerrada (la fórmula de reajuste) o remite a otra norma sin transcribir (los límites de la NTCSE y
la NTCSER) queda como hueco nombrado con su cita.

## Enmienda del 2026-11-16 (VNR según la Guía, RCD 232-2017-OS/CD)
Orden del usuario: «debe haber ese módulo, porque es parte y está vinculado al cálculo del VAD». Hasta hoy el conversor
solo leía el VNR que fija Osinergmin (inventario VNR-GIS, RCD 184-2026-OS/CD) y valoraba la red de la empresa modelo
con el SICODI; no calculaba el VNR de las instalaciones reales adaptadas. La Guía (texto oficial en
`CSG_FUENTES_NORMATIVAS`, «OSINERGMIN No.232-2017-OS-CD.pdf», sha256/16 c2236182c2032033) fija la fórmula del art. 17.2,
la zonificación del art. 22, los criterios de adaptación por sector típico (capítulos sexto a décimo primero) y los
anexos 2 (códigos VNR), 4 (estructura de datos), 5 (formatos A1, B1, C1 y D1) y 6 (tablas de equivalencia). RF-20 a
RF-25 amplían esta spec en vez de abrir otra: el VNR adaptado de la empresa real es la entrada de la TIR que decide si
el VAD es definitivo (arts. 70 y 71 de la LCE); el aVNR del VAD sigue saliendo de la empresa modelo. El VNR que fija
Osinergmin sirve de referencia para contrastar el cálculo.
