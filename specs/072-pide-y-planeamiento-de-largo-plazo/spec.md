# Spec 072 — PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio

Estado: aprobada · Fecha: 2026-11-02 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-02: «el PIDE en su metodología y criterios tiene dos entregables: un PIDE y otro planeamiento de
largo plazo; para esto hemos implementado los pronósticos, se traslada caso por caso de estudio por años; lo que todo se
hizo es un caso de año cero o caso base». Sobre el año: «sí se presenta en año 2027; recuerda que esto no debe ser fijo
porque se presenta cada 4 años». Sobre los costos: «el VNR y SICODI, como los módulos aprobados para PIT, son públicos;
están en la página de Osinergmin de cada empresa».

Hoy el conversor diagnostica por años y da una propuesta parcial de obras, pero no genera ninguno de los dos entregables.
La referencia son los entregables de Electro Oriente: `PIDE 2026` (4.1 largo plazo y 4.2 PIDE, año 0 = 2025) y `PIDE 2021`
(informes sucesivos). Sus cifras son referencia de forma y contenido, no verdad: tienen incoherencias propias (103
proyectos en ALT1 y 81 hojas de evaluación; años 02-07 frente a los 04-07 de la norma).

La norma de partida es RM 428-2017-MEM/DM, que `config/pide_universal_2017.json` marca como prepublicación: su vigencia se
confirma antes de citarla como obligatoria en un entregable.

## Usuarios / actores

Ingeniero de planificación de cualquier distribuidora, desde la web; el asistente, por las mismas rutas.

## Requisitos funcionales (EARS)

### Estudio y años

- RF-1: CUANDO se cree un estudio, EL SISTEMA pedirá el año de presentación y calculará de él el año 00 como el anterior a la
  presentación (art. 7.2). Ningún año irá escrito en el código: la presentación se repite cada 4 años.
- RF-2: EL SISTEMA calculará desde el año 00 los años de largo plazo (04, 08, 12, 16, 20; arts. 5.1, 9) y los de detalle del
  PIDE (04 a 07; art. 11.2), con el horizonte en la configuración de la metodología.
- RF-3: SI la medición que calibró el caso base no es del año 00, ENTONCES EL SISTEMA lo dirá y seguirá (030:RF-12).
- RF-4: EL SISTEMA generará los dos entregables desde un mismo estudio: el PIDE consume el largo plazo, no lo vuelve a calcular
  (arts. 5.1, 6.1).

### Fuentes de costos

- RF-5: EL SISTEMA leerá los costos por un único contrato de fuente, con adaptadores para SICODI (distribución), módulos
  estándar (transmisión, PIT) y libro CAPEX; cada costo declarará fuente, resolución, año, moneda y sector típico.
- RF-6: EL SISTEMA valorará las obras de distribución con SICODI y las de transmisión con módulos estándar, sin mezclarlos
  en un mismo elemento.
- RF-7: CUANDO valore un tramo, EL SISTEMA cruzará código de costo, tensión, estructura y sector típico; SI no cruza,
  ENTONCES lo nombrará y no le atribuirá un costo.
- RF-8: EL SISTEMA no aplicará factores sobre los costos oficiales salvo que el estudio declare el factor y su sustento.
- RF-9: EL SISTEMA guardará de cada fuente pública la URL de Osinergmin, su fecha de descarga y su huella, y usará el VNR
  aprobado de la empresa según su propia resolución de fijación.

### Mercado y años

- RF-10: EL SISTEMA proyectará la demanda anual con el método que gane contra lo ocurrido; la tasa de 029 será la referencia
  que debe superar. La spec 046 es de corto plazo y no alcanza estos horizontes; las variables exógenas son de la 031.
- RF-11: DONDE haya entregables históricos con datos, EL SISTEMA medirá el pronóstico contra lo ocurrido, sin mirar el futuro.
- RF-12: EL SISTEMA trasladará cada caso de estudio a cada año (030) y acumulará en cada año las obras de los anteriores.

### Continuación anual del corto plazo

Orden del usuario del 2026-11-07, ejecutada en P17 (2026-11-08): el PIDE es un
flujo propio, universal, después de los cuatro años del corto plazo (098:RF-37,
RF-39, RF-40). La 089 vigente excluye la proyección a años: una curva de 28 días
no acredita un horizonte anual y no se extrapola silenciosamente.

- RF-23: CUANDO se continúe el corto plazo, EL SISTEMA partirá de una copia del caso y escenario identificados por sus rutas completas, con las obras de corto plazo declaradas comprobadas activas.
- RF-24: EL SISTEMA usará en cada año únicamente una proyección anual aceptada con archivo y huella, modelo y evaluación identificados, cobertura del horizonte y P/Q por identidad completa de carga, sin sustituirla por una tasa cuando falte.
- RF-25: CUANDO un año incumpla los límites del perfil, EL SISTEMA comprobará las obras físicas declaradas para ese año y releerá el flujo después de aplicarlas; sin obra o sin solución lo dejará bloqueado.
- RF-26: EL SISTEMA copiará el estado con las obras del año anterior antes de evaluar el siguiente y registrará el primer año en que vuelven los problemas y las obras acumuladas.
- RF-27: CUANDO termine o falle el flujo anual, EL SISTEMA restituirá proyecto, caso, escenario y demandas originales, y no informará éxito si la relectura no lo confirma.
- RF-28: SI faltan identidad, proyección aceptada, unidad, datos físicos o conservación verificable, ENTONCES EL SISTEMA nombrará el faltante y no sobrescribirá estudios existentes ni inventará magnitudes o cumplimiento.

- Aclaración de RF-28 (P04, 2026-11-08): las nuevas lecturas CAPEX que alimenten cálculos conservarán
  la identidad SHA256 de los bytes realmente leídos, su ruta, hoja, configuración, unidades, escala y moneda
  declaradas y fecha de lectura en planes, resultados e informes persistidos. El recibo no acredita vigencia
  ni aprobación presupuestal; un dato no declarado queda explícito y una obra histórica sin enlace no recibe
  una procedencia retrospectiva. Se preservan costos, capacidades, ubicaciones, elecciones y fórmulas.

Contrato web de RF-18 y RF-23 a RF-28 (P17, 2026-11-08): el modo histórico
conserva sus entradas y comportamiento por defecto. El modo anual recibe tres
JSON del operador: perfil, evaluación y aceptación del corto plazo. Se conservan
los originales y sus SHA-256; un derivado del perfil cambia únicamente la ruta
de evaluación por la custodiada con la misma huella. Ninguna referencia anidada
subida se abre como ruta del servidor ni permite leer otro espacio. La petición
comprueba las fuentes e identidades antes de encolar, y el trabajo las relee
antes del controlador CLI común. El carril PowerFactory comunica cancelación
entre etapas y conserva el informe parcial con restitución verificada, también
si el proyecto objetivo difiere del inicialmente activo. La interfaz muestra
fuentes, faltantes, obras acumuladas y aceptación nativa pendiente; subir un
archivo no concede aceptación científica ni reemplaza una revisión humana.
- Aclaración de RF-24: una carga desequilibrada exige P/Q explícitas de sus fases r/s/t, con suma coherente con el total y unidades verificadas; su representación anual conserva la conexión y el modo físicos originales.

### Entregables

- RF-13: EL SISTEMA generará el informe de largo plazo con mercado, diagnóstico, alternativas, técnico-económico, plan de obras
  y los formatos F01 a F07.
- RF-14: EL SISTEMA generará el informe PIDE con alternativas, evaluación con y sin proyecto, VAN, TIR, costo anual, priorización
  y los formatos F08 a F15.
- RF-21: EL SISTEMA generará los entregables por módulos, un documento ligero por cada uno y con sus tablas y formatos del anexo,
  siguiendo su artículo paso a paso: del plan, el diagnóstico y la formulación de alternativas; del PIDE, la formulación en su
  periodo, la evaluación técnica, la económica, la priorización y selección, y la propuesta (usuario, 2026-11-02: «para que sea
  ligero los informes se haga por módulos y entregables»).
- RF-15: EL SISTEMA generará metrados desde la red de cada proyecto; sin metrado no habrá costo supuesto.
- RF-16: SI un dato del entregable falta, ENTONCES EL SISTEMA dejará el hueco nombrado, sin inventarlo.
- RF-17: EL SISTEMA tomará de un perfil de empresa todo lo propio de cada distribuidora; una fuente no alimenta a otra.
- RF-22: DONDE el perfil dé el COyM en % de la inversión (`escalera.coym_pct_anual`, el mismo dato de 025:RF-53), EL SISTEMA lo
  sumará al costo anual de cada obra con inversión conocida (024:RF-58) y lo escribirá en F10, F11 y F12; un grupo con alguna obra
  sin COyM queda vacío, con su hueco nombrado (RF-16). (Revisión de la 076, fila `formatos_pide-012`, 2026-11-03: la propuesta
  pasaba siempre el COyM vacío y la columna quedaba en blanco aunque el perfil lo diera.)

### Tipo de análisis en la web

Usuario, 2026-11-11: «desde la web se debe diferenciar si va a ser un análisis de corto plazo, el PIDE o el planeamiento de
largo plazo, según la normativa», «cada uno bien hilado y robusto», con los botones o pasos necesarios. Hasta ahora la web
llegaba a los tres por pasos sueltos (4 · Obras y estudios, 5 · Planificación PIDE) y un único «Planificar» escribía siempre
los dos entregables.

- RF-29: EL SISTEMA hará que el operador elija en la web, de forma explícita, uno de tres tipos de análisis: corto plazo,
  PIDE o planeamiento de largo plazo.
- RF-30: EL SISTEMA dará el horizonte de cada tipo desde la metodología y el perfil, sin años en el código: el corto plazo,
  del año 00 al periodo de corto plazo (098:RF-37); el PIDE, los años de detalle (art. 11.2); el largo plazo, los años de
  largo plazo (arts. 5.1 y 9); y, DONDE haya año de presentación, el año de calendario de cada uno (RF-1).
- RF-31: EL SISTEMA dará las obras que admite cada tipo según 098:RF-50: el corto plazo, solo las de implementación
  inmediata; el PIDE, las de su periodo empezando por la de corto plazo (098:RF-37); el largo plazo, además, las integrales.
- RF-32: EL SISTEMA dará los entregables de cada tipo: el corto plazo, los informes de estudio y de factibilidad (spec 017)
  con su libro (spec 066); el PIDE, los módulos de los arts. 11 a 17 con F08 a F15; el largo plazo, los de los arts. 6 a 10
  con F01 a F07; los artículos y formatos, los de la metodología.
- RF-33: EL SISTEMA mostrará los pasos de cada tipo en su orden, cada uno con su estado según los trabajos del proyecto y un
  acceso al paso de la web que lo hace, sin quitar ni duplicar ningún paso. El estado también sale de lo guardado en disco
  (calibración, cargas nuevas aplicadas, flujos de «Con proyecto», obras e informes), no solo de la sesión; y CUANDO los
  alimentadores marcados ya están calibrados, EL SISTEMA ofrecerá ir directo a 4.2 y a 4.4, sin ocultar los pasos 2 y 3
  (CA101_CHN102, 2026-11-13).
- RF-34: CUANDO se planifique como largo plazo, EL SISTEMA escribirá solo los módulos del plan de largo plazo.
- RF-35: SI se planifica como largo plazo con la aplicación de obras pedida, ENTONCES EL SISTEMA lo rechazará antes de
  encolar: el plan plantea las obras, no las aplica en «Con proyecto».
- RF-36: SI se planifica como PIDE o largo plazo sin año de presentación en la petición ni en el perfil, ENTONCES EL SISTEMA
  lo rechazará antes de encolar, diciendo que falta el año de presentación.
- RF-37: EL SISTEMA dirá con los tipos de análisis la norma de la que salen y su estado jurídico, sin presentarla como
  vigente mientras la metodología la marque como proyecto.
- RF-38: MIENTRAS el tipo elegido sea PIDE y no conste un «Con proyecto» del proyecto, EL SISTEMA avisará que el PIDE parte
  de la obra de corto plazo (098:RF-37), sin bloquear.

### Asistente

- RF-18: EL SISTEMA dará al asistente herramientas para ejecutar cada paso del estudio por las mismas rutas que la web, con
  plan y confirmación.
- RF-19: EL SISTEMA podrá usar los entregables de Electro Oriente para entrenar al asistente, con revisión humana, solo para
  redactar y dar formato, nunca como verdad eléctrica. Cambia 027:RF-47 por orden del usuario del 2026-11-02, a la propuesta
  «¿autorizas usar los resultados de ELOR para entrenar, con revisión humana?»: «has la 3 y 4 según lo recomendado».

### Casos de prueba

- RF-20: EL SISTEMA tratará los nombres de empresas, clientes y proyectos de ejemplos, pruebas y documentos como casos de prueba
  del conversor, no como valores por defecto (usuario, 2026-11-02: «etiqueta como de prueba del conversor»).

## Requisitos no funcionales

Universal: cualquier distribuidora y número de alimentadores. Determinismo del DGS intacto. Los datos descargados quedan fuera
de git.

## Casos límite

Una empresa sin VNR fijado en el último proceso usa el de su última resolución y lo dice. Una red con códigos sin costo
sigue con el hueco nombrado. Un año base distinto del año medido se avisa.

## Fuera de alcance

El piloto MADRL. La tensión en valle en la elección de obras es de la spec 073. No se reproduce el consultor: los entregables
históricos son referencia.

## Criterios de finalización

Cada RF con su prueba, una aceptación real de los dos entregables en una empresa, y suite completa sin omitidas.
