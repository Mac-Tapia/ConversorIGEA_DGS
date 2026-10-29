# Revisión de specs, tareas y código — 2026-10-29

Revisión de las 30 carpetas de `specs/` en los dos sentidos: de la spec al código (cada RF
con su tarea y su prueba) y del código a la spec (cada fichero, prueba y commit con su
spec). Sigue el skill `igea-dgs-spec`: primero los hallazgos, en bloques, y después el
plan, que el usuario ha pedido de forma expresa. Continúa a
`docs/VERIFICACION_SPECS_2026-10-14.md`.

Método: una sonda de solo lectura que cruza `spec.md`, `plan.md` y `tasks.md` con las citas
`NNN:RF-n` de `tests/` y `frontend/src/` (incluidos los rangos «RF-a a RF-b» y «RF-2/6/7»),
con `CODIGO_FUENTE.md` y con `git log`; cada anomalía se ha confirmado después a mano en el
fichero. Cifras del 2026-10-29, rama `main` en `2a8c32e1`.

## Resumen

| Medida | Valor |
| --- | --- |
| Specs | 30 (001, 002, 004 a 030 y 032; no existen ni 003 ni 031) |
| RF definidos | 1 458, de ellos 39 con sufijo (RF-36b…) |
| Funciones de prueba | 2 405; 1 636 citan algún `NNN:RF-n` y 769 (32 %) no citan ninguno |
| Tareas abiertas | 50, en 12 specs |
| Specs implementadas con algún RF sin prueba | 011, 016, 027 y 028 (13 RF) |
| RF que ninguna tarea cubre | 63, en 13 specs |
| Tareas sin «Hecho cuando:» | 23, en 13 specs |
| Commits `feat` desde el 2026-10-07 sin spec ni RF en el mensaje | 26 de 125 |

La suite queda en verde con todo esto porque las comprobaciones de la spec 009 tienen
cuatro puntos ciegos (sección 4): no ven los RF con sufijo, solo comparan el estado
«cumplida», se desactivan con una sola tarea de DIgSILENT abierta y no miran las tareas.

## 1. Numeración

### 1.1 Specs

- **003 y 031 no existen**, pero se citan: la 003 en la 002 y en la memoria (lo que queda
  de la rama `feat/integracion-web-retiro-gui`); la 031 en la 029 (la proyección
  econométrica). El siguiente número libre es el **033**. Nada en el repositorio dice
  que esos dos números estén reservados.

### 1.2 Requisitos

| Spec | Hallazgo |
| --- | --- |
| 020 | Salta de **RF-32 a RF-60**: RF-33 a RF-59 no existen y nada lo explica. |
| 022 | Faltan **RF-35, RF-36 y RF-92**, sin nota. |
| 017 | Falta **RF-123**, sin nota. |
| 004, 006, 007, 011, 014 | Nueve líneas `- RF-n:` **repetidas** en las secciones de cambios o aclaraciones (004:RF-15; 006:RF-18 y RF-28; 007:RF-10; 011:RF-2, RF-6 y RF-8; 014:RF-5 y RF-10). Leídas tal cual, cada una es una segunda definición del mismo RF con otro texto. |
| 011, 017, 022, 024, 025 | **39 RF con sufijo** (011:RF-73b; 017:RF-1b a RF-86b, 20; 022:RF-18b a RF-58b, 5; 024:RF-47b a RF-58e, 6; 025:RF-6b a RF-52b, 7). La prueba de la 009 solo lee `- RF-(\d+)`, así que para ella no existen: ni se exige su prueba ni se rechaza una cita a uno que no esté. |

### 1.3 Tareas

| Spec | Hallazgo |
| --- | --- |
| 014 | **T8c repetida** y una tarea `T8c-015` con un nombre fuera de la forma `Tn`. |
| 027 | **T14 va detrás de T22**: numeración y orden de dependencia no coinciden. |
| 027 | **T11 está «cerrada» y «reabierta» a la vez**: su texto dice las dos cosas, la casilla sigue abierta y `CLAUDE.md` la da por cerrada. |
| 13 specs | **23 tareas sin «Hecho cuando:»**: 001 (T17, T20, T23, T26, T27), 015 (T22, T24 a T26), 008 (T6, T7), 009 (T2, T5), 019 (T5, T6), 002 T12, 004 T8, 006 T8, 007 T11, 014 T8c, 018 T6, 023 T6 y 025 T22. |

## 2. Estado: tres fuentes que no coinciden

El estado de una spec se escribe en tres sitios (la línea `Estado:` de `spec.md`, la tabla
de `CLAUDE.md` y las casillas de `tasks.md`), y ninguna comprobación los compara.

| Spec | `spec.md` dice | `CLAUDE.md` dice | Las tareas dicen |
| --- | --- | --- | --- |
| 005, 006, 008, 011, 014, 015, 020, 021, 023, 025 | aprobada | implementada o cumplida | código hecho |
| 016 | aprobada | **cumplida** | **T16 abierta** |
| 022 | implementada, «T11c y T11d abiertas» | cumplida | **ninguna abierta** |
| 028 | pedida | implementada | T6 y T9 abiertas; el texto de T9 dice que está hecha y probada con Chincha |
| 029, 030 | pedida | cumplida o implementada | todas cerradas |
| 017 | aprobada | informe de estudio probado con IN111 y TA225 | **T5, T7 a T15 y T17 abiertas**; T7 nombra `tools/informes_pf.py`, que **no existe**: el plan y el código han seguido caminos distintos |
| 013 | **borrador, sin `tasks.md`** | RF-1 a RF-6 con prueba, selector de mes hecho | — |
| 002 | aprobada | plan y tareas **pendientes de aprobar desde el 2026-10-10** | T1 y T5 hechas, el resto abiertas |

Consecuencias:

- La 013 tiene código y pruebas sin una spec aprobada: va contra el principio 12 de la
  constitución («la spec manda»).
- La tabla de `CLAUDE.md` (una fila por spec, algunas de más de mil caracteres) se ha
  convertido en un registro de cambios que se carga en cada sesión, y es la fuente que
  más se desfasa.

## 3. De la spec al código

### 3.1 RF sin prueba en specs implementadas

| Spec | RF sin ninguna prueba que los cite |
| --- | --- |
| 011 | RF-2, RF-54, RF-55 |
| 016 | RF-77 |
| 027 | RF-10, RF-21, RF-28, RF-40, RF-45, RF-52, RF-54, RF-55 (algunos de tareas abiertas) |
| 028 | RF-25 |

Las 002, 012, 013 y 017 tienen muchos RF sin prueba (29, 60, 20 y 57), pero eso cuadra
con sus tareas abiertas: son trabajo pendiente, no una incoherencia.

### 3.2 RF sin tarea

Son RF que se añadieron como «cambio» después de escribir las tareas y no entraron en
ellas (el paso 8 del flujo, «spec → plan → tareas → código», se saltó el plan y las
tareas):

| Spec | RF sin tarea |
| --- | --- |
| 004 | RF-42, RF-43, RF-46 a RF-53, RF-56, RF-57, RF-67 |
| 006 | RF-40 a RF-44 |
| 007 | RF-38 a RF-40 |
| 011 | RF-73b |
| 015 | RF-68, RF-69 |
| 017 | RF-36b a RF-36d, RF-39c, RF-39d, RF-40b, RF-42b, RF-51, RF-65b, RF-67b a RF-67e, RF-86b |
| 018 | RF-14, RF-15 |
| 020 | RF-60 a RF-62 |
| 021 | RF-70 |
| 022 | RF-41b, RF-41c, RF-62, RF-63 |
| 024 | RF-47b, RF-47c, RF-58b a RF-58d |
| 025 | RF-69 a RF-77 |
| 027 | RF-52 |

### 3.3 Specs sin plan o sin tareas

- 013: sin `tasks.md`.
- 029 y 030: sin `plan.md`, con el plan metido en el encabezado de las tareas.
- 028: lleva además un `research.md` que no está en las plantillas.

## 4. Del código a la spec, y puntos ciegos de la 009

- **Índice del código desfasado en su columna «Spec».** Ningún fichero de
  `CODIGO_FUENTE.md` apunta a la **018, la 030 ni la 032**, aunque su código existe
  (`web/services.py`, `cargas_pf.py`, `tools/pide_pf.py` y los guiones del ajuste) y sus
  pruebas también. La 012 y la 023 aparecen en una sola fila cada una.
- **24 ficheros de código solo con «base»** (`dataset.py`, `model.py`, `catalog.py`,
  `schema.py`, `studies.py`…). Es lo previsto: los rige la constitución y 001:RF-14
  mientras la 002 no los mueva a sus capas. Pero la 002 lleva parada desde el 2026-10-10.
- **769 pruebas sin cita.** Una parte es del motor «base», pero no hay forma de saber
  cuáles cubren un comportamiento que no está en ninguna spec.
- **26 commits `feat` sin spec**, entre ellos `4ec961e6` (barra de 60 kV y Chincha
  Nueva), `f7498632` y `ea4678e9` (reconstrucción por medida), `48fae6dc` (arnés del
  agente) y `ee1cc536`. Después se anotaron como RF en las specs 019, 021 o 022, pero el
  código entró antes.
- **Puntos ciegos de `tests/test_inventario.py`:**
  1. `_rf` solo lee `^- RF-(\d+)`: ignora los 39 RF con sufijo y cuenta como uno los RF
     duplicados.
  2. 009:RF-9 solo compara el estado «cumplida» con las tareas; «implementada»,
     «aprobada» o «pedida» con todo hecho no se comprueba nunca.
  3. 009:RF-11 se desactiva con una sola tarea abierta que no diga literalmente «a
     cargo del usuario». Las pruebas en DIgSILENT de las 011, 016, 025, 026, 027 y 028
     no lo dicen, así que en ellas no se comprueba que cada RF tenga su prueba: por eso
     pasan los RF de la sección 3.1.
  4. Nada comprueba que cada RF tenga una tarea, que cada tarea tenga su «Hecho
     cuando:», que los Tn no se repitan ni que las tres fuentes del estado coincidan.

## 5. Plan de mejora y organización

Es una reorganización, así que según el skill entra como spec nueva, la **033
«Trazabilidad y estado de las specs»**, con su plan y sus tareas aprobados antes de tocar
nada. Abajo va la propuesta, ordenada por dependencias. **Regla en todas las fases: no se
renumera ningún RF ni ninguna spec existente.** Hay 1 636 pruebas que citan `NNN:RF-n`, y
renumerar rompería esa trazabilidad. Los huecos se declaran; no se rellenan.

### Fase 0 — Decisiones (usuario)

1. Aprobar que se abra la spec 033 con este alcance.
2. Vocabulario cerrado de estados: `borrador → aprobada → implementada → cumplida`, más
   `reservada` y `retirada`. «Implementada» quiere decir «código y pruebas hechos, falta
   DIgSILENT»; «cumplida», todo cerrado.
3. Marca de las tareas de DIgSILENT: `[DIgSILENT]` al principio del título, en lugar de
   la frase «a cargo del usuario».
4. Qué hacer con la 002 (aprobar el plan, aplazarla con fecha o retirarla) y con la 013
   (aprobarla y escribir sus tareas, o cerrarla remitiendo a la 021, cuyos RF-50 a RF-53
   ya cubren el mes de análisis y el instante coincidente).

### Fase 1 — La puerta primero: ampliar la 009 (pruebas que fallan hoy)

Antes de corregir los documentos se escriben las comprobaciones, para que lo corregido no
vuelva a desfasarse. Son RF nuevos de la 033 en `tests/test_inventario.py`:

| Comprobación | Hoy fallaría en |
| --- | --- |
| `_rf` lee los sufijos (`RF-36b`) y rechaza dos definiciones `- RF-n:` del mismo número | 004, 006, 007, 011, 014 y los RF con sufijo |
| Un hueco en la numeración necesita una línea `- RF-a a RF-b: no se usan (motivo)` | 017, 020, 022 |
| Los Tn no se repiten y siguen la forma `T\d+[a-z]?` | 014 |
| Cada tarea tiene «Hecho cuando:» | 23 tareas |
| Cada RF aparece en alguna tarea (directamente o en un rango) | 63 RF de la sección 3.2 |
| La línea `Estado:` usa el vocabulario cerrado y coincide con las casillas: «implementada» admite solo tareas `[DIgSILENT]` abiertas; «cumplida», ninguna | las de la sección 2 |
| 009:RF-11 se aplica en cuanto las tareas de código están cerradas, ignorando las `[DIgSILENT]` | 011, 016, 027, 028 (sección 3.1) |
| Una spec aprobada o posterior tiene `plan.md` y `tasks.md` | 013, 029, 030 |
| Cada spec implementada o cumplida tiene al menos un fichero en `CODIGO_FUENTE.md` | 018, 030, 032 |
| 003 y 031 existen como carpetas `reservada` con su motivo | 003, 031 |

### Fase 2 — Una sola fuente del estado

- Nuevo `specs/README.md`, **generado** por `tools/estado_specs.py` (con docstring,
  `--help`, entrada en el índice y en `MANUAL_COMANDOS.md`, como pide la 009). Tendrá una
  fila por spec con estado, RF, RF con prueba, tareas abiertas y pruebas de DIgSILENT
  pendientes. Una prueba comprueba que el README está al día.
- La tabla de `CLAUDE.md` se reduce a una línea por spec (número, nombre y estado) más el
  enlace a `specs/README.md`. Las evidencias de DIgSILENT (proyectos, porcentajes,
  fechas) pasan a la tarea correspondiente, debajo de un subapartado «Evidencia:».

### Fase 3 — Corregir los documentos (sin código de producto)

Por orden, cada punto con la puerta de la fase 1 en verde:

1. **Numeración.** Las aclaraciones repetidas pasan a la forma `- Aclaración de RF-15
   (por 014:RF-…):`. Se declaran los huecos de 020 (RF-33 a RF-59), 022 (RF-35, RF-36 y
   RF-92) y 017 (RF-123). Se arreglan las tareas: 014 T8c pasa a T8d y T8c-015 a T8e; 027
   T14 se mueve a su sitio y la casilla de T11 cuadra con su texto.
2. **Estado.** Las líneas `Estado:` se pasan al vocabulario y se cuadran con la tabla de
   la sección 2. Casos concretos: 016 queda «implementada» (T16); 022 y 029 pasan a
   «cumplida»; 030, a «cumplida» o a «implementada» según su T3; 028 queda
   «implementada», con T9 cerrada si se confirma su evidencia.
3. **RF sin tarea.** Se escriben tareas de retroalimentación `Tn (retro)`, una por
   bloque de RF, que citan la prueba que ya los cubre, o se abren como pendientes si no la
   hay.
4. **017.** Su `plan.md` y su `tasks.md` se rehacen con lo que existe de verdad
   (`informes.py`, `informe_docx.py`, `mapa_informe.py`, `libros_informe.py`,
   `InformesPF.tsx`, `transformador_set_pf.py`) y lo que falta, en lugar del
   `tools/informes_pf.py` que nunca se creó.
5. **013, 029 y 030.** La 013 recibe `tasks.md` (o se cierra, según la fase 0). Las 029
   y 030 reciben un `plan.md` corto con lo que hoy tienen en el encabezado de las tareas.
6. **Índice.** `CODIGO_FUENTE.md` actualiza su columna «Spec» con 018, 030 y 032, y la
   amplía para 012 y 023.

### Fase 4 — Cerrar los huecos de cobertura (código de pruebas)

- Pruebas para los 13 RF de la sección 3.1: 011:RF-2, RF-54 y RF-55; 016:RF-77; 028:RF-25;
  y los de la 027 cuyas tareas están cerradas. Si al escribirla un RF resulta no
  implementado, se reabre su tarea; no se marca como cumplido.
- Clasificar las 769 pruebas sin cita en tres grupos: «base» (se citan como
  `001:RF-14`), las que cubren un RF existente (se añade la cita) y las que cubren algo
  que no está en ninguna spec. Estas últimas dan RF nuevos en la spec que corresponda,
  siempre por el paso 8 del flujo.

### Fase 5 — Pendientes de DIgSILENT en una sola cola

Las tareas de DIgSILENT abiertas, agrupadas por lo que piden, para hacerlas desde la web
con `tools/sistema_web.py`, sin tocar proyectos ya trabajados:

| Lo que piden | Tareas |
| --- | --- |
| Un alimentador desde cero (CA101 u otro) | 017 T13; 016 T16; 007 T11 (SI213) |
| Dos alimentadores calibrados con carga nueva | 005 T12; 008 T7; 011 T19; 012 T13; 028 T9 |
| Un sistema entero (Chincha, Pisco) | 025 T21; 027 T8 y T22 |
| Nasca con la central de NA205 | 028 T6 |
| Una carga nueva sola (factibilidad) | 017 T14 |
| Órdenes del asistente y todos los sistemas | 026 T12; 027 T14 y T24 |

### Fase 6 — Reglas para que no vuelva a pasar

Se añaden al skill `igea-dgs-spec`:

- Una spec «cumplida» no crece: un cambio sobre ella abre una spec nueva que la cita. La
  017 llegó a 154 RF y la 011 a 130 a base de cambios añadidos al final, y son las que
  más desfases acumulan.
- Un RF nuevo entra en el mismo cambio que su tarea (la fase 1 lo exige).
- Cada commit `feat` cita su spec (`(NNN:RF-n)`); un *hook* de `commit-msg` o una prueba
  sobre `git log` lo avisa.
- Un `tasks.md` separa la casilla, «Hecho cuando:» y «Evidencia:»; la historia de
  intentos va a la evidencia y no al título.

### Orden y tamaño

| Fase | Toca | Tamaño |
| --- | --- | --- |
| 0 | Decisiones | — |
| 1 | `tests/test_inventario.py` | unas 10 pruebas nuevas |
| 2 | `tools/estado_specs.py`, `specs/README.md`, `CLAUDE.md` | una herramienta |
| 3 | unas 20 carpetas de `specs/` y `CODIGO_FUENTE.md` | solo documentos |
| 4 | `tests/` | 13 RF y clasificar 769 pruebas |
| 5 | DIgSILENT desde la web | 17 tareas en 6 grupos |
| 6 | Skill `igea-dgs-spec`, *hook* | reglas |

## 6. Resultado (ejecutado el mismo día, spec 033 cumplida)

El usuario pidió ejecutarlo entero («nada debe quedar suelto»). Se hizo así:

- **Comprobaciones.** `tests/test_trazabilidad_specs.py` (22 pruebas, 033:RF-1 a RF-22) y
  `tools/estado_specs.py`, el único lector de specs, que también usa la 009. Antes de
  corregir nada fallaban 17 de ellas, una por hallazgo; ahora pasan todas.
- **Numeración.** Las nueve definiciones repetidas son ahora «Aclaración de RF-n»; los huecos
  de 017, 020 y 022 están declarados; 003 y 031 son carpetas «reservada»; 014 T8c-015 pasa a
  T8d. No se renumeró nada.
- **Tareas.** «Hecho cuando:» en las 23 que no lo tenían; `[DIgSILENT]` en las pruebas de
  DIgSILENT; 016 T16, 027 T3, T8 y T24 y 028 T9 partidas en código cerrado más una tarea
  `[DIgSILENT]`; tareas retro para los 63 RF sin tarea, con las pruebas que los citan.
- **Estado.** Todas las specs con el vocabulario cerrado y coherentes con sus casillas. La
  013 pasa a «aprobada», con `tasks.md` y tres RF nuevos (RF-30 a RF-32) para lo que el código
  ya hacía sin spec. Las 029 y 030 tienen su `plan.md`. La 017 tiene su cambio de diseño en el
  plan, y su T7 ya no pide un guion que no existe. `specs/README.md` es generado y `CLAUDE.md`
  tiene una fila por spec.
- **Spec y código.** 011:RF-54 y 016:RF-77 tienen la aclaración de las specs posteriores que
  los cambiaron. Los 13 RF sin prueba quedan citados por las pruebas que ya los verificaban,
  más tres pruebas nuevas de la interfaz (013:RF-7, RF-10 y RF-15) y una de las herramientas
  base (034:RF-33).
- **Código sin spec.** La spec 034, retrospectiva, recoge el motor base y el contrato
  universal de fuentes (33 RF). Los 65 ficheros de pruebas la citan, `CODIGO_FUENTE.md` ya no
  tiene ningún fichero solo con «base» y los 17 commits sin spec están atribuidos en la 034.

Queda abierto, y figura como tarea en su spec: el código de las 002, 012, 013 (T5 y T6), 017,
025 (T15) y 027 (T11, T22 y T26), y las pruebas `[DIgSILENT]` de `specs/README.md`.
