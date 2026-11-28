# Spec 113 — Entrenamiento remoto en Colab con evaluación local

Estado: aprobada · Fecha: 2026-11-26 · Origen: orden del usuario del 2026-11-26 («crear un notebook […] clonar este
proyecto […] con el mismo nombre del proyecto […] entrenar desde VS Code con la extensión de Colab […] con todos los
datasets reales […] y regresar el modelo para que se integre en su operación»).

## Contexto y objetivo

Los modelos del conversor se entrenan hoy en la GPU del equipo (RTX 4060, 8 GB) y compiten por la RAM con la web y
DIgSILENT. Colab Pro da más GPU y CPU. El objetivo es un circuito único: los datasets se preparan en local, el
entrenamiento corre en Colab desde un cuaderno del propio proyecto y el candidato vuelve al equipo, donde lo examinan las
puertas de siempre frente a los conjuntos sellados, que nunca salen. Vale para todo lo que aprende el conversor:
asistente (intérprete y redacción PIDE, destilación maestro → alumno), RAG, oráculo PINN y gemelo GRU, pronóstico
(transformers de series y boosting), MADRL/MASAC (spec 114) y la búsqueda de hiperparámetros.

## Usuarios / actores

El operador desde la web o desde VS Code con la extensión de Colab; Colab Pro; Google Drive del operador; las puertas de
modelos (043, 047, 070, 071, 089).

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA tendrá el cuaderno `notebooks/ConverterSmartGrid.ipynb` en el repositorio, sin celdas ejecutadas, sin
  datos y sin credenciales; una prueba impedirá integrarlo con salidas.
- RF-2: CUANDO el cuaderno arranque, clonará el repositorio y la revisión que lleva escritos el manifiesto de su
  paquete (el repositorio, del remoto `origin` del clon que lo preparó) y comprobará que es esa; con el repositorio privado, el token se leerá de los secretos de Colab, nunca del cuaderno.
- RF-3: EL SISTEMA instalará en Colab las versiones fijadas del proyecto (con su huella) y lo dirá si alguna falta.
- RF-4: CUANDO el operador pulse «Entrenar en Colab» en la web, EL SISTEMA comprobará que el árbol no tiene cambios sin
  commit (si los tiene, avisará: Colab no los vería), preparará los datasets elegidos con su manifiesto (huellas, origen,
  revisión, qué contiene), le dirá qué sube y a dónde, y solo con su confirmación los dejará en una carpeta privada de su
  Google Drive (spec 109); luego abrirá Colab con el cuaderno de esa revisión.
- RF-5: EL SISTEMA anonimizará cada dataset según su tipo antes de subirlo (nombres de clientes, SED y empresas, como la
  072:RF-49) salvo lo que el modelo necesite tal cual (la red y las curvas), y lo dirá en el manifiesto.
- RF-6: EL SISTEMA no subirá nunca los conjuntos sellados de evaluación ni los datos crudos de la distribuidora (TXT, MDB,
  `.bak`, libros); una prueba lo comprobará sobre el manifiesto.
- RF-7: CUANDO el cuaderno entrene, EL SISTEMA guardará puntos de control en Drive y retomará desde el último si Colab
  corta la sesión.
- RF-8: DONDE la familia lo admita, EL SISTEMA buscará hiperparámetros con un presupuesto fijo (Optuna) y registrará
  todas las pruebas, no solo la ganadora.
- RF-9: AL terminar, EL SISTEMA dejará en Drive cada candidato con su manifiesto: revisión, huellas de los datasets,
  semilla, entorno (versiones y GPU), hiperparámetros y métricas de entrenamiento.
- RF-10: CUANDO el operador pulse «Traer los candidatos de Colab» (o lo pida desde VS Code), EL SISTEMA los descargará,
  comprobará sus huellas, su revisión y las de sus datasets, y rechazará con su motivo el que no cuadre.
- RF-11: EL SISTEMA registrará el candidato sin activarlo y lo pasará por las puertas locales de su familia frente a los
  conjuntos sellados; solo si las pasa moverá el puntero del modelo en uso, de forma atómica, conservando el anterior
  para volver atrás (043, 071).
- RF-12: SI un candidato no pasa, ENTONCES EL SISTEMA dejará su diagnóstico (por qué no pasó y qué cambiar en la
  siguiente corrida) y el modelo en uso no cambiará.
- RF-13: CUANDO haya datos nuevos suficientes para una familia (aprendizaje continuo, 050), EL SISTEMA lo avisará en la
  web y propondrá reentrenarla por este circuito.
- RF-14: EL SISTEMA permitirá ejecutar el mismo cuaderno desde VS Code con un núcleo de Colab, con el mismo resultado que
  abierto desde la web.
- RF-15: EL SISTEMA podrá preparar como datasets los paquetes VNR-GIS públicos de las distribuidoras (080), cada red en
  su entorno, sin mezclar fuentes ni empresas.

- RF-16: Colab será siempre una opción y nunca una condición, como ordenó el usuario el 2026-11-26 («todo lo que se
  está haciendo para Google Colab debe ser una opción, que no limite ni impida el entrenamiento local»): EL SISTEMA
  ofrecerá entrenar «En este equipo» o «En Colab Pro» con el mismo dataset y la misma orden de `tools/`; lo entrenado en
  Colab pasará por las mismas puertas locales que lo entrenado aquí; y sin carpeta de Drive ni cuaderno, el entrenamiento
  y la evaluación locales funcionarán igual, sin error ni aviso que los bloquee.
- RF-17: (usuario, 2026-11-27: «debe haber un vínculo directo a Colab desde el notebook») EL cuaderno llevará al
  principio un enlace «Abrir en Colab» al cuaderno de la rama principal en GitHub; la revisión con la que entrena
  sigue siendo la de su paquete (RF-2).
- RF-18: (orden del usuario del 2026-11-27: las corridas largas del intérprete, 069 T7 y 070 T28, deben poder ir a
  Colab) CUANDO el operador prepare el intérprete de órdenes para Colab, EL SISTEMA construirá en el equipo el mismo
  corpus de la vía integral y sacará de él solo las particiones de entrenamiento y selección, con los proyectos, SED,
  SET, casos, estudios y rutas cambiados por un seudónimo estable de la misma forma (con una sal que no sale del
  equipo), el texto libre por `sin_nombres` (072:RF-49), los datos de cada frase en su sitio y la huella del corpus
  completo en su manifiesto; la calibración, la prueba (selladas y órdenes humanas) y los mensajes reservados se
  quedarán en el equipo.
- RF-19: CUANDO Colab entrene el intérprete, EL SISTEMA entrenará y elegirá el candidato por la selección con el mismo
  código que en el equipo, sin calibrar, medir pruebas, registrar ni poner nada en uso, bajará el codificador con su
  revisión fija si falta en la caché, y rechazará antes de entrenar un corpus que traiga otra partición.
- RF-20: CUANDO se examine en el equipo un candidato del intérprete traído de Colab, EL SISTEMA lo calibrará, lo medirá
  y lo registrará con el corpus completo del que salió su paquete y con las mismas puertas que uno entrenado aquí, y solo
  lo pondrá en uso si las pasa; SI el corpus dado no es aquel, ENTONCES lo rechazará con su motivo.
- RF-21: (excepción a RF-6; usuario, 2026-11-27: «sí, autorizo que salgan anonimizadas a Colab», sobre la validación
  cruzada de la 070 T28) DONDE el operador pida la validación cruzada del intérprete (075:RF-35) en Colab, EL SISTEMA
  sacará en el paquete, además de lo de RF-18, solo las órdenes humanas confirmadas que usa esa validación, con los
  mismos seudónimos estables de RF-18 (la sal no sale) y con lo que entrena de cada una ya decidido en el equipo frente
  a lo que mide (075:RF-28), de modo que ningún texto de las pruebas selladas, de la calibración ni de los mensajes
  reservados salga; Colab hará las vueltas y el modelo final con la misma orden que en el equipo, y la puerta final
  seguirá en el equipo con lo sellado, leyendo la medida fuera de grupo de Colab con los valores reales.
- RF-22: (revisión del paquete del intérprete con el usuario, 2026-11-28) EL SISTEMA ocultará en todo lo que sale a
  Colab el nombre de un lugar que sigue a su clase (fundo, hacienda, predio, caserío, centro poblado, urbanización,
  asentamiento, anexo, calle, jirón, avenida, pasaje, comunidad, parcela, lote…), con sus artículos y enlaces, hasta una
  palabra de enlace, una cifra o un nombre de la red, y conservará la clase («fundo ‹lugar›»). (Una orden confirmada real
  decía «…para 800 kW en el fundo Santa Rosa» y salía entera: el catálogo solo conoce los nombres de la red.)
- RF-23: (revisión del paquete de MADRL con el usuario, 2026-11-28) EL SISTEMA sacará a Colab el grafo de una red
  con cada ruta de objeto de DIgSILENT cambiada por un seudónimo estable de su misma clase, con la sal de RF-18, y con su
  topología y sus valores eléctricos tal cual. (El grafo de LL203 llevaba la estructura del proyecto, los códigos de SED y
  el nombre de un cliente en una barra; el modelo aprende de la red, no de los nombres.)

## Requisitos no funcionales

- Reproducible: misma revisión, mismos datasets y misma semilla dan el mismo candidato (salvo el no determinismo de la GPU,
  que se declara).
- Nada de datos ni salidas en el repositorio público (constitución, MEJ7-NOMBRES).
- La web sigue funcionando con el modelo en uso mientras se entrena fuera.

## Casos límite

- Colab corta la sesión: se retoma desde el punto de control (RF-7).
- El candidato se entrenó con otra revisión del código: se rechaza (RF-10).
- Drive sin espacio o sin permiso: se dice y no se sube nada.
- Ningún candidato mejora al vigente: no se activa nada (RF-12).

## Fuera de alcance

Entrenar en otra nube que no sea Colab; subir datos sin la confirmación del operador; activar un modelo sin puertas.
