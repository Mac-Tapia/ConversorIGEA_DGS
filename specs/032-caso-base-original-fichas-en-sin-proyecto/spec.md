# Spec 032 — «Caso base» con los datos originales; fichas y potencias en «Sin proyecto»

Estado: aprobada (2026-10-28) · Fecha: 2026-10-28

## Contexto y objetivo

Al convertir todos los alimentadores desde la web, el DGS ya sale con dos cambios sobre lo
que trae la entrada (reglas del proyecto, `reglas.py`): las SED cuya carga supera su kVA se
llevan a un tamaño normalizado (regla 3, `sed_potencia`; en 260924.mdb, `SE50111`, 1197 kW
sobre 50 kVA) y los conductores toman la R, X, B y la corriente nominal de la ficha del
catálogo, aunque el archivo diga otra cosa (regla 4, `catalog.aplicar_correcciones`). Así
el «Caso base» deja de ser la red tal como la registró la distribuidora, y la verificación
de la spec 015 compara capacidades con un archivo que ya no es el que se importó. El
usuario lo ordena así (2026-10-28): «el caso base, sin cambios ni sugerencias de cambios;
los cambios y sugerencias según los catálogos y otros deben ser en la calibración, en el
caso Sin proyecto: ahí se deben sugerir los cambios de potencias instaladas de SED, y a los
cables actualizar sus parámetros eléctricos según fichas de fabricantes, ya sea su
capacidad de amperios y otros». Además, en DIgSILENT el «Caso base» y «Sin proyecto»
comparten la red: lo que la spec 020 escribe «en la red, sin variación» también cambia el
«Caso base». El objetivo es que el «Caso base» conserve las potencias de las SED y los
parámetros de los conductores del archivo original, y que «Sin proyecto» reciba, en una
variación propia, los conductores con su ficha y la propuesta de potencias de SED.

## Usuarios / actores

Ingeniero de planificación desde la web (conversión, importación, calibración); CLI en
lote; DIgSILENT PowerFactory 2024.

## Historias de usuario

- H1: Como ingeniero quiero que el «Caso base» sea la red tal como la registró la
  distribuidora, para poder verificarla y compararla con el archivo sin correcciones mías.
- H2: Como ingeniero quiero que la calibración en «Sin proyecto» ponga a los conductores
  los parámetros de su ficha, para calcular pérdidas, caída y cargabilidad con datos reales.
- H3: Como ingeniero quiero que la calibración me proponga la potencia de las SED que
  quedan cargadas por encima del umbral, fijas y escaladas, para decidir qué cambio.

## Requisitos funcionales (EARS)

«Caso base»: el archivo original

- RF-1: EL SISTEMA escribirá en el DGS la potencia de cada transformador de SED tal como
  la trae la entrada (TXT, MDB o VNR-GIS), aunque su carga la supere.
- RF-2: EL SISTEMA escribirá en el DGS la resistencia, la reactancia, la susceptancia y la
  corriente nominal de cada conductor tal como las trae la entrada, aunque el catálogo del
  proyecto o un catálogo subido a la web den otro valor de ficha.
- RF-3: DONDE la entrada no trae los parámetros de un código de conductor, EL SISTEMA los
  completará con el catálogo del proyecto, como hasta ahora.
- RF-4: CUANDO completa un conductor con el catálogo (RF-3), EL SISTEMA lo anotará en el
  informe de la conversión como dato deducido, con el código, la fuente y los tramos.
- RF-5: EL SISTEMA no incluirá en el informe de la conversión, en el Registro de la web ni
  en la verificación del «Caso base» ninguna propuesta de cambio de potencia de SED ni de
  parámetros de conductor.
- RF-6: EL SISTEMA dará el mismo «Caso base» desde la web, el CLI y la red unida o por
  sistema, porque las tres vías aplican las mismas reglas (constitución P5).
- RF-7: CUANDO verifica el «Caso base» (015:RF-7), EL SISTEMA comparará las capacidades
  de DIgSILENT con las de la entrada sin corregir.
- RF-26: SI el flujo del «Caso base» no converge con las potencias y los conductores
  originales, ENTONCES EL SISTEMA escalará la demanda de sus cargas hasta el mayor factor
  con el que converge (015:RF-38), sin cambiar ninguna SED ni ningún conductor.

«Sin proyecto»: las variaciones del catálogo

- RF-8: EL SISTEMA escribirá cada clase de cambio de esta spec en su propia variación del
  conversor, una por proyecto: los conductores con su ficha en una y los transformadores
  de SED en otra, aunque las dos tengan la misma fecha.
- RF-27: EL SISTEMA tendrá las variaciones de RF-8 activas en «Sin proyecto» y en
  «Con proyecto» e inactivas en el «Caso base».
- RF-9: EL SISTEMA no modificará ningún tipo de línea ni de transformador que use el
  «Caso base»: los valores nuevos van en tipos propios, y la variación reasigna a ellos los
  elementos.
- RF-10: SI ya existe un tipo propio con el mismo nombre y los mismos datos, ENTONCES EL
  SISTEMA lo reutilizará.
- RF-11: SI ya existe un tipo propio con el mismo nombre y otros datos, ENTONCES EL
  SISTEMA no cambiará los elementos de ese tipo y nombrará el tipo y el dato que difiere.
- RF-12: SI en «Sin proyecto» hay una variación del operador grabando, ENTONCES EL
  SISTEMA escribirá en su propia variación de RF-8, devolverá la grabación a la etapa del
  operador al terminar y lo dirá, sin dejar de calibrar. Usuario, 2026-10-28: «verifica que
  se van a poder hacer las modificaciones manuales por mí en DIgSILENT […] esto no debería
  bloquear nada, porque yo actualizo en DIgSILENT algunos datos de tramos, incluyo nuevas
  ternas según las instalaciones actuales en campo». Antes no cambiaba nada (020:RF-17).
- RF-13: CUANDO se vuelve a calibrar, EL SISTEMA reutilizará cada variación de RF-8 sin
  duplicar sus cambios.

Conductores con su ficha

- RF-14: CUANDO calibra «Sin proyecto», antes del primer flujo, EL SISTEMA pondrá a cada
  conductor cuyo código tiene ficha en el catálogo (el del proyecto o el subido a la web)
  la resistencia, la reactancia, la susceptancia y la corriente nominal de la ficha que
  difieran de las del archivo.
- RF-15: EL SISTEMA conservará en el cambio de RF-14 el código, el material, la sección y
  qué tramo usa qué conductor: solo cambian los parámetros eléctricos.
- RF-16: CUANDO termina el cambio de RF-14, EL SISTEMA informará por código el parámetro,
  el valor del archivo, el de la ficha, la variación en %, cuántos tramos y cuántos km toca
  y la fuente de la ficha.
- RF-17: EL SISTEMA mostrará el informe de RF-16 en el resultado del ajuste de la web y lo
  guardará en el informe del ajuste.
- RF-18: SI el catálogo no tiene ficha de un código, ENTONCES EL SISTEMA dejará los
  valores del archivo y listará el código como «sin ficha».
- RF-19: SI la ficha de un código trae un valor no positivo donde el archivo lo tiene
  positivo, ENTONCES EL SISTEMA no aplicará ese valor y nombrará el código y el parámetro.

Potencias de SED propuestas

- RF-20: CUANDO calibra «Sin proyecto», EL SISTEMA marcará cada SED, fija o escalada, cuya
  demanda aparente en el flujo calibrado supere el umbral de carga del perfil de empresa.
- RF-21: EL SISTEMA propondrá para cada SED de RF-20 la potencia según las tablas de
  fichas del perfil, con las reglas de 020:RF-6 a RF-8 y RF-31.
- RF-28: EL SISTEMA distinguirá en la tabla de la propuesta las SED que superan el 100 %
  de su potencia instalada de las que están entre el umbral del perfil y el 100 %.
- RF-22: EL SISTEMA mostrará la propuesta con una casilla por SED y el botón
  «Implementar transformadores» de la spec 020, sin cambiar ninguna SED hasta que el
  operador lo pulse.
- RF-23: CUANDO el operador implementa la propuesta, EL SISTEMA escribirá los
  transformadores en la variación de los transformadores de SED (RF-8) y volverá a calibrar
  (020:RF-25).
- RF-24: EL SISTEMA reportará cada SED cambiada en la tabla de cambios de 020:RF-60, con lo
  original del archivo y lo nuevo.
- RF-25: DONDE el perfil de empresa no trae tablas de fichas, EL SISTEMA listará las SED
  de RF-20 sin propuesta (020:RF-10).
- RF-29: MIENTRAS «Sin proyecto» tenga variaciones del operador activas o una etapa suya
  grabando, EL SISTEMA pondrá los bancos que faltan (021:RF-64) en la red como siempre,
  apartando esas variaciones solo mientras los crea y volviéndolas a dejar activas y con
  su etapa grabando, en vez de detener la calibración (antes lanzaba «tiene variaciones
  activas o una etapa grabando»).

## Requisitos no funcionales

- Determinismo (P1): el DGS es idéntico byte a byte con `workers=1` y `workers>1`.
- Universal (P13): ni normas, ni umbrales, ni potencias en el código; vienen del perfil y
  del catálogo. Sin perfil ni catálogo, el «Caso base» sale igual y «Sin proyecto» no
  cambia nada, con un aviso.
- Escala (P2): sin número fijo de alimentadores; el cambio de conductores es por código,
  no por tramo.
- Mensajes en español (P10).

## Casos límite

- `SE50111` (1197 kW sobre 50 kVA): el «Caso base» lo lleva con 50 kVA; si su flujo no
  converge, se escala la demanda hasta que converja, sin bloquear (RF-26, 015:RF-38 a
  RF-40), y la SED aparece en la propuesta de «Sin proyecto» como por encima del 100 %
  (RF-1, RF-20, RF-28).
- Conductor `AA01003D` registrado como 10 mm² con la R de otra sección: en el «Caso base»,
  la R del archivo; en «Sin proyecto», la de la ficha, con el cambio en el informe (RF-2,
  RF-14, RF-16).
- Dos disposiciones de export, TXT, MDB y VNR-GIS: el mismo «Caso base» sin correcciones.
- Proyecto ya importado con el DGS anterior (SED redimensionadas y conductores con ficha
  en la red): su «Caso base» no se arregla solo (ver «Fuera de alcance»).
- Una variación de RF-8 borrada a mano por el operador: se crea de nuevo al recalibrar
  (RF-13).
- Varios alimentadores en un proyecto o un sistema: una variación de cada clase para todo
  el proyecto, calibración de todos a la vez.
- Las variaciones de conductores y de SED con la misma fecha que la de la central y las
  de las cargas: cada una graba y se aplica por separado (RF-8).
- Cancelar entre el cambio de conductores y el flujo: los cambios quedan en la variación y
  el informe dice que falta calibrar.

## Fuera de alcance

- Proyectos ya importados: esta spec se aplica a los proyectos de conversión nuevos; el
  «Caso base» de uno anterior no se corrige (hay que convertir e importar de nuevo).
- Cambiar conductores por sobrecarga (sección mayor): es una obra de «Con proyecto»
  (specs 016, 017).
- Bancos de condensadores, reguladores y otros equipos: siguen sus specs (015, 021).
- Las demás reglas del proyecto (puentes fundidos, trafomix, diagrama): no cambian.
- `--literal` del CLI: sigue igual.

## Requisitos que esta spec cambia

| Requisito | Antes | Ahora |
| --- | --- | --- |
| Reglas del proyecto 3 y 4 (`reglas.py`) | SED redimensionadas y fichas del catálogo aplicadas al convertir | No se aplican al convertir (RF-1, RF-2); las fichas van a «Sin proyecto» (RF-14) |
| 020:RF-1, RF-6 | Solo SED fijas por encima del 100 % de su potencia | Fijas y escaladas por encima del umbral del perfil (RF-20, RF-21) |
| 020:RF-16 | Transformadores en la red de «Sin proyecto», sin variación | En su propia variación, inactiva en el «Caso base» (RF-8, RF-23, RF-27) |
| 020, «Fuera de alcance» | Sin SED escaladas | Con SED escaladas (RF-20) |
| 020:RF-17, 032:RF-12 | Con una variación del operador grabando, no se cambia nada | Se graba en la variación propia y se devuelve la grabación al operador (RF-12) |
| 021:RF-64 | Con variaciones del operador activas, los bancos que faltan detienen la calibración | Se apartan mientras se crean los bancos y vuelven activas (RF-29) |

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "032:RF-[0-9]+" tests | sort -u`).
- Suite en verde con las siete variables y `-rs`, ninguna omitida; DGS idéntico con
  `workers=1` y `workers>1`.
- Prueba en DIgSILENT desde la web con un sistema entero: «Caso base» con los kVA y los
  conductores del archivo (verificación sin diferencias de capacidad), «Sin proyecto» con
  la variación del catálogo, el informe de conductores y la propuesta de SED.

## Dudas resueltas

1. Conductores en «Sin proyecto»: se aplican solos con informe, sin botón (usuario,
   2026-10-28; RF-14 a RF-17).
2. SED propuestas: todas las sobrecargadas, fijas y escaladas, con el botón de la spec 020
   (usuario, 2026-10-28; RF-20 a RF-22).
3. Conductores sin parámetros en la entrada: se completan con el catálogo en el «Caso
   base» y se anotan (usuario, 2026-10-28; RF-3, RF-4).
4. SED entre el umbral y el 100 %: se proponen, distinguidas en la tabla de las que pasan
   del 100 % (usuario, 2026-10-28; RF-28).
5. «Caso base» que no converge con los datos originales: se escala la carga hasta que
   converja (usuario, 2026-10-28; RF-26).
6. Proyectos ya importados: fuera de alcance; vale para las conversiones nuevas (usuario,
   2026-10-28).
7. Una variación por clase de cambio, aunque compartan fecha (usuario, 2026-10-28; RF-8).
