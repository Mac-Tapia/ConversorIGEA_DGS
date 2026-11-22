# Spec 112 — Datasets de referencia anonimizados y benchmarks reproducibles

Estado: aprobada (2026-11-20: RF-15 a RF-19, dejar una empresa fuera cada vez; queda T16, la corrida con los paquetes públicos; y RF-20 y RF-21, la medición de escala de la web, con la corrida de 200 alimentadores y el dibujo en navegador hechos el 2026-11-21, T18 y T19); cumplida el 2026-11-17 · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-22 y BP-21, y orden del usuario del 2026-11-14:
«haz nuevos spec». G0: `D:/csg/G0_PLAN_MAESTRO/C/C_FILAS_BP.md` (BP-22: solo existe la anonimización del paquete de
soporte).

## Contexto y objetivo
La tesis y la evaluación necesitan comparar métodos con datos que se puedan compartir. Los datos reales de la
distribuidora no se publican (constitución, principio 9). G0 encontró que solo existe la anonimización del paquete de
soporte (`web/soporte.py:66-77@51895566`) y que no hay cohortes por empresa. Esta spec genera, desde los datos reales y
solo en local:
- benchmarks sintéticos o desidentificados con su manifiesto;
- protocolos de evaluación por cohortes de empresa y de tiempo.

Así los resultados se pueden reproducir sin revelar nada de la empresa.

## Usuarios / actores
- El investigador o la tesis.
- La evaluación de los modelos (089, 045 y 069).
- El revisor externo.

## Historias de usuario
- H1: Como investigador, quiero un paquete de redes y series desidentificadas, con su manifiesto y sus métricas de
  referencia, que pueda compartir sin datos de la empresa.
- H2: Como evaluador, quiero evaluar cada modelo con cohortes separadas por empresa y por tiempo.

## Requisitos funcionales (EARS)
- RF-1: CUANDO el operador genere un benchmark, EL SISTEMA lo creará en local desde los datos reales, sin enviarlos
  a ningún servicio externo.
- RF-2: EL SISTEMA reemplazará en el benchmark los identificadores, los nombres, las coordenadas absolutas y los
  códigos de cliente por valores sin relación recuperable con los originales.
- RF-3: EL SISTEMA conservará en el benchmark la topología, las fases, las impedancias y la forma de las series que
  hacen falta para que el estudio dé el mismo resultado dentro de la tolerancia declarada.
- RF-4: SI un control de reidentificación encuentra algún identificador, coordenada o patrón original, ENTONCES EL
  SISTEMA no emitirá el benchmark y dirá qué lo delató.
- Aclaración de RF-4 (2026-11-14, auditoría R3 de 7e): SI el perfil de la empresa que se pide para el control falta o
  no se puede leer, ENTONCES EL SISTEMA no emitirá el benchmark y dirá qué fichero y por qué, en vez de buscar «ningún
  término» y dejar pasar en silencio el nombre de la empresa. El paquete de soporte (086:RF-42), que se usa justo cuando
  algo falla, sí sale, pero sin los registros ni el texto libre del diagnóstico, y su LEAME dice por qué.
- RF-5: EL SISTEMA guardará con cada benchmark su manifiesto: la huella del origen (sin revelarlo), la versión del
  generador, la semilla, las transformaciones, la tolerancia y las métricas de referencia.
- RF-6: CUANDO se evalúe un modelo, EL SISTEMA podrá separar las cohortes por empresa (dejando una fuera) y por
  tiempo, sin que un mismo alimentador ni un mismo cliente caiga en dos particiones.
- RF-7: EL SISTEMA guardará el conjunto de prueba sellado antes de la selección del modelo, y su huella no cambiará
  después.
- RF-8: EL SISTEMA publicará también los resultados negativos de cada evaluación.
- RF-9: SI solo hay datos de una empresa, ENTONCES EL SISTEMA dirá en el informe que la generalización entre empresas
  no está demostrada.
- RF-10: EL SISTEMA no incluirá nunca en el benchmark el texto de los libros, de los informes ni de los documentos de
  la empresa.
- RF-11: DONDE el origen tenga un dataset de pronóstico de demanda (089), EL SISTEMA incluirá en el benchmark sus series
  desidentificadas, con las métricas de referencia de los métodos de base calculadas en el original y en el benchmark.
- Aclaración de RF-11 (2026-11-15, rebase de la T5 sobre e182c823): el desplazamiento por semanas completas no conserva
  el mes, y el método de base «perfil_calendario» del 089 agrupa por mes. Para que sus métricas se reproduzcan, el mes de
  calendario viaja como una exógena más (columna `mes`), y el 089 la usa cuando viene (`Exogenas.meses`, vacío por
  defecto). Sin ella, el 089 da los mismos resultados que antes; se descarta copiar sus métodos de base en la 112, que
  dejaría dos versiones de la misma métrica (P5). Límite declarado: con el mes y el día de la semana de cada fila, un
  atacante puede rehacer la fecha original; las fechas no identifican a la empresa (los valores van escalados y los
  identificadores seudonimizados), y el manifiesto lo dice.
- Aclaración de RF-5 (auditoría de la T2, 2026-11-14): «la semilla» del manifiesto es la **semilla pública** de RF-12,
  nunca la de los seudónimos.
- RF-12: EL SISTEMA guardará la semilla de los seudónimos solo en el equipo de la empresa, nunca en el manifiesto ni en
  el benchmark, y publicará en su lugar una semilla derivada de ella por una función de un solo sentido.
- RF-13: EL SISTEMA publicará en el benchmark de redes unas coordenadas de un trazado sintético que conserva la
  topología, y unas longitudes eléctricas con una perturbación sorteada y acotada, en vez de la forma real de la red.
- RF-14: SI la huella de longitudes de un alimentador del benchmark coincide con la del original, o el estudio sobre el
  benchmark se sale de la tolerancia por la perturbación, ENTONCES EL SISTEMA no emitirá el benchmark y dirá qué
  alimentador y qué control fallaron.
- Aclaración de RF-13 y RF-14 (medición del subagente de la T13, 2026-11-14): con ε ~ U(−5 %, 5 %), la correlación de
  Spearman tramo a tramo da 0,988–0,9998, y sobre las longitudes ordenadas, 1,0. Un atacante que conozca el margen
  empareja los tramos dentro del ±5 %, así que una perturbación que cabe en la tolerancia del estudio NO oculta la huella
  de longitudes. Por eso:
  - el control de RF-14 modela a ese atacante: «identificado» si un emparejamiento de las longitudes ordenadas dentro
    del margen declarado cubre el 50 % de los tramos o más;
  - un benchmark derivado de una red real se emite solo como «uso local» (marcado en el manifiesto) y la vía de
    publicación lo rechaza;
  - lo publicable son redes sintéticas generadas con las estadísticas agregadas del origen (número de alimentadores y
    de tramos y percentiles de longitud y de carga), nunca con sus tramos.
  - un agregado solo se usa si junta al menos 5 alimentadores y 500 tramos (condición del auditor: los agregados de
    una red pequeña también la delatan). Si no llega, se agrupa con otras redes de la misma entrega, y si aun así no
    llega, no se emite y se dice por qué. Los mínimos van en el manifiesto y se pueden subir, nunca bajar.
- RF-15: CUANDO se evalúe si la conversión VNR o el pronóstico generalizan a otra empresa, EL SISTEMA dejará una
  empresa fuera cada vez: ajustará solo con las demás y medirá solo en la retenida, un pliegue por empresa.
- RF-16: SI hay menos de 3 empresas, ENTONCES EL SISTEMA dará el veredicto «NO DEMOSTRADA» y dirá cuántas hay y cuántas
  hacen falta; con 3 o más, dará «DEMOSTRADA» solo si cada empresa retenida pasa su criterio, y si no, «NO DEMOSTRADA»
  con las que no lo pasan y su motivo.
- RF-17: EN la conversión VNR, EL SISTEMA ajustará con las empresas de entrenamiento el catálogo de fichas de conductor
  y medirá en la retenida, por longitud, la parte de sus tramos cuyo conductor encuentra ficha en ese catálogo por la
  misma regla del modelo (el código igual o el más parecido) y la parte cuya ficha queda dentro de la tolerancia de la
  suya propia en R1, X1 y corriente admisible; el pliegue pasa con un acierto del 90 % de la longitud o más, con una
  tolerancia del 10 %, y los dos valores se pueden cambiar y van en el informe.
- RF-18: EN el pronóstico, EL SISTEMA ajustará con las empresas de entrenamiento la forma semanal de la demanda (cada
  serie de potencia activa dividida por su media, mediana por día de la semana y cuarto de hora) y la comparará en la
  retenida, en el mismo origen y con el WAPE del 089, con la base «semanal» de la propia serie; el pliegue pasa si la
  forma de las demás no empeora el WAPE de esa base en más del 10 %.
- RF-19: EL SISTEMA escribirá el informe de la evaluación en JSON con escritura atómica (001:RF-5): el veredicto, su
  motivo, el número de empresas y el mínimo, los criterios y cada pliegue con sus métricas; las empresas irán como
  `E1…En`, por la huella del nombre de su carpeta, nunca con su nombre.
- Aclaración de RF-6 y RF-9 (2026-11-20, Plan Maestro PM-17): las cohortes de RF-6 reparten los registros por empresa;
  RF-15 a RF-19 son el bucle que ajusta y mide con ellas. «Una sola empresa» de RF-9 se amplía a «menos de 3» para el
  veredicto entre empresas (RF-16): con dos, cada pliegue ajusta con una sola y no sostiene una generalización. Para la
  conversión VNR se usan los paquetes públicos de Osinergmin de cada empresa (RF-14), bajados bajo demanda y fuera del
  programa; el pronóstico necesita series de al menos tres empresas.

- RF-20: CUANDO se mida la escala de la web, EL SISTEMA generará redes sintéticas, sin ningún nombre, código ni
  coordenada de una empresa, de 10, 50 y 200 alimentadores (o de los tamaños que se pidan) con la misma semilla, y medirá
  para cada tamaño, en un proceso propio y por la API con su puerta de seguridad encendida, el tiempo de la carga de la
  red, el p50 y el p95 de las peticiones que hace la pantalla al abrir el espacio (con la primera llamada aparte), el
  tamaño de cada respuesta y la memoria pico del proceso, y guardará el resultado con la revisión del código con que se
  midió.
- RF-21: SI una magnitud de la escala no se puede medir sin un navegador real (el dibujo de la pantalla), ENTONCES EL
  SISTEMA la dejará en el resultado como «no medido» con su motivo, nunca como un cero, y se medirá aparte con su guion
  de navegador sobre las mismas redes sintéticas.

## Requisitos no funcionales
- Reproducible: con la misma semilla y el mismo origen sale el mismo benchmark, byte a byte.
- Universal: sirve para cualquier empresa.

## Casos límite
- Una red con un solo alimentador.
- Coordenadas que delatan la ciudad.
- Una serie con patrón único, como una carga industrial.
- Un cliente que aparece en dos alimentadores por una transferencia.

## Fuera de alcance
- Un tope de milisegundos en la suite para la escala de la web: depende de la máquina y de lo que corra a la vez;
  la medición da los números y su revisión, y la decisión de un presupuesto se toma con ellos (RF-20).
- Publicar en un repositorio público: la decisión y la acción son del usuario.
- Garantizar la privacidad diferencial formal.

## Criterios de finalización
Cada RF citado por una prueba (`grep "112:RF-"`). Hay una prueba de reidentificación negativa (un benchmark con
fugas plantadas se rechaza). El estudio sobre el benchmark reproduce el original dentro de la tolerancia en al menos
dos redes.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario (`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 5).
- Tolerancia de reproducción (RF-3): la de la spec del estudio correspondiente. Si el estudio no declara ninguna, 0,005
  p.u. en tensión y un 1 % en corriente (carga de líneas y transformadores). Para las series, la diferencia relativa de
  WAPE y MASE de cada método de base no pasa del 1 %. La tolerancia usada queda en el manifiesto (RF-5).
- Hay benchmark de redes y también de series de demanda: entra como RF-11.
- Privacidad, revisada tras la auditoría de la T2 (2026-11-14, decisión del implementador por delegación del usuario):
  - Con la semilla y la lista pública de alimentadores (VNR-GIS) se rehace el mapa de seudónimos, así que la semilla es
    secreta y solo se publica una derivada de un solo sentido (RF-12).
  - Un giro y una traslación conservan la forma, y la forma se cuadra contra la geometría pública de Osinergmin. Por eso
    lo publicado lleva un trazado sintético por el grafo y longitudes perturbadas dentro de la tolerancia del estudio
    (RF-13), con un control de reidentificación por la huella de longitudes (RF-14).
  - Descartado: publicar la red girada, que se reidentifica; y publicar solo redes enteramente sintéticas, que ya no
    sirven para validar el lector ni las reglas con casos reales. El usuario puede elegir esta segunda opción; entonces
    RF-13 se sustituye por «solo redes sintéticas».
