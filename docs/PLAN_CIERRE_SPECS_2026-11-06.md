# Diagnóstico y plan de cierre de las specs 001 a 095 (2026-11-06)

Revisión: `main` en 6987208f, con cambios sin confirmar de la sesión eafcf16e (PE102) en 004 y 024.
Fuente del estado: `tools/estado_specs.py` (spec 033), las casillas de cada `tasks.md`, `git cherry`
de las ramas locales y `.agents/coordination/ACTIVE.md`. Este documento no cambia el estado de ninguna
spec: el estado vive solo en su línea `Estado:`.

## 1. Diagnóstico

### 1.1 Recuento

| Estado | Specs | Cuáles |
| --- | --- | --- |
| cumplida | 44 | 001, 004*, 005–007, 009, 010, 014, 015, 018–024, 029, 030, 032–036, 038, 040, 041, 046, 053, 054, 057, 059–064, 066, 076, 077, 080, 082, 088, 090, 095 |
| implementada (solo falta DIgSILENT o navegador) | 29 | 008, 011–013, 016, 017, 026, 028, 037, 039, 042, 044, 048, 051, 052, 055, 056, 067, 070, 073, 075, 078, 079, 081, 083, 084, 087, 092, 093 |
| aprobada (falta código o entrenamiento) | 19 | 002, 025, 027, 043, 045, 047, 049, 050, 058, 065, 068, 069, 071, 072, 074, 085, 086, 089, 094 |
| reservada | 3 | 003, 031, 091 |

\* La 004 figura como cumplida con la T20 abierta (ver 1.3).

Tareas abiertas: **125**. De ellas, **78** son `[DIgSILENT]` (pruebas reales en DIgSILENT o en el
navegador), **7** son de GPU (entrenamiento) y el resto, código o validación.

RF sin prueba que la cite (según el generador): 002 (6), 027 (8), 045 (1), 049 (10, todos), 058 (1),
074 (1), 085 (8), 086 (4), 094 (9).

### 1.2 Recursos hoy

- GPU libre (0 de 8 188 MiB en uso): la pausa del 2026-11-06 por memoria ya no aplica.
- Web del puerto 8765 parada.
- 34 worktrees; casi todas sus ramas ya están en `main` (aplastadas por `integracion/todo`).

### 1.3 Incoherencias que hay que corregir primero

1. **004 cumplida con la T20 abierta.** La T20 pide que ningún transformador de carga nueva pase del
   80 % en «Con proyecto» de PE102; la última medida en DIgSILENT dio 83,5 % (PTAR 4 × 630) y
   81,3 % (vivero 315). No se cumple: la 004 debe volver a «implementada» hasta cerrar la T20, y
   RF-52 (`kva_normalizado` dimensiona al 100 %) es la causa probable.
2. **Cambios sin confirmar de la sesión eafcf16e**: 004 RF-68/RF-69 (transformador de ficha) y 024
   RF-12 (aviso `DIGITAL_TWIN_QUARANTINE`), en `cargas_pf.py`, `tools/cargas_pf.py`,
   `digital_twin/capture.py` y sus pruebas. Hay que confirmar la autoría y pasarlos a un commit.
3. **`specs/README.md` desfasado**: `estado_specs.py --comprobar` sale con 1 (falta la T20 de la 004).
4. **La tabla de `CLAUDE.md` no coincide** con lo generado: 004 (T20), 042 (faltan T29, T37, T42,
   T44, T48, T50), 065 (falta T12) y 081 (falta T24).
5. **Rama `feat/093-retomar-tras-suspender` (68f5592d) sin fundir y con un número tomado**: crea
   `specs/093-retomar-tras-suspender-el-equipo`, pero la 093 ya es «La sigla de la carga…». Hay que
   renumerarla (096) y fundirla, o descartarla.
6. ~~085:RF-7 a RF-9 (parada bayesiana)~~: revisado en la fase 0, ya está en `main` como 087:RF-7 a RF-9.

### 1.4 Defectos conocidos sin spec ni arreglo

| Defecto | Spec que lo recibe |
| --- | --- |
| El refuerzo de tramos sobrecargados de cada variante es siempre terna; debe seguir bancos → sección hasta 240 mm² → terna (PE102) | 042 (RF-43) |
| La escalera mide en DIgSILENT todas las variantes (34 en PE102); debe ordenar por costo, parar en las 3 más baratas que cumplen y añadir una definitiva para el horizonte | 042 / 087 |
| «Con proyecto» relee los 21 libros mensuales de clientes en cada corrida; guardar por alimentador y huella | 029 / 042 |
| Si el refuerzo por terna se compara por costo con la sección (decisión del usuario) | 042 |
| FP por defecto de las cargas nuevas que solo traen kW (hoy Q = 0; decisión del usuario) | 007 |
| Aviso «4 × 630 → 4 × 630» | 020 / 083 |
| `factor_escala` 0,290 frente a 0,884 en el historial de PN103 (por verificar) | 006 |
| `test_cancelar` depende del orden de las pruebas | 067 |
| Un worktree no ve `output/web` del clon principal (`raiz_componente`) | 086 |

## 1.5 Avance de la fase 0 (2026-11-06, sesión 63935039)

| Punto | Resultado | Commit |
| --- | --- | --- |
| 0.1 Cambios de PE102 (004 RF-68/69, 024 RF-12) | confirmados; la 004 pasa a «implementada» | 4ac024b1, 1df549d4 |
| 0.2 README y tabla de `CLAUDE.md` | al día; `test_trazabilidad_specs` en verde | cf3c727f |
| 0.3 Rama `feat/093-retomar-tras-suspender` | integrada como spec 096; contrato de la API regenerado (faltaba `transformadores_automaticos`) | bf7452ee |
| 0.4 Parada bayesiana | ya estaba en `main` como 087:RF-7 a RF-9 (la «085» de las ramas era otra colisión de número); sin cambios | — |
| 0.5 Refuerzo de tramos por escalera (042:RF-94) y variantes por costo (042:RF-95) | hecho | 2332bc2c |
| 0.5 Transformador de carga nueva a la tensión mínima (aclaración de 004:RF-68) | hecho; la 004 T20 sigue pendiente en DIgSILENT | b7abd331 |
| 0.5 Aviso «4 × 630 → 4 × 630» | la SED que ya tiene la propuesta queda en «sin_cambio» (020:RF-24) | 4e9139d4 |
| 0.5 Libros de clientes releídos (042:RF-96) | la POT de cada libro se guarda con su huella | 29b41e62 |
| 0.5 `test_cancelar` según el orden | ya arreglado por otra sesión el 2026-11-06 (cuenta flujos, no consultas) | — |
| 0.5 `factor_escala` de PN103 | verificado, no es un fallo: 0,290 es el factor del reparto determinista, con el que arranca la recalibración (083:RF-9); 0,884 es el del P50 probabilístico sobre su propia base | — |
| 0.5 `raiz_componente` en un worktree | sin cambio a propósito: un worktree no debe escribir en los datos del clon principal; para compartirlos está `CSG_WEB_DATA` | — |
| 0.6 Archivar worktrees | pendiente de la decisión del usuario | — |

## 1.6 Avance de la fase 1 (2026-11-06 noche)

| Punto | Resultado | Commit |
| --- | --- | --- |
| 086 T5, T38, T39 | ya estaban en `main` (042:RF-61, RF-62, RF-64, RF-70, RF-71); su medida en DIgSILENT es la 042 T42 y T44 | 68d03109 |
| 094 T4 | perfil en la web (SVG con el límite) y en el informe de estudio; guardado con la calibración | 2fab76c7 |
| 094 T6 | perfil completo antes y después de cada propuesta, con su comparación | 816cefe3 |
| 094 T7 | espera la sonda T10 [DIgSILENT]: la referencia de PF 2024 no dice cómo se liga el `VisPath` al alimentador | — |
| 049 T1–T3 | en curso en un worktree aparte; los datos de protecciones no existen en ninguna fuente, así que el resultado honesto es «bloqueado, con lo que falta» | — |
| 072 T13 | sin cambios: la carpeta de la Res. 181-2026-OS/CD no está publicada (lo comprobó otra sesión el mismo día) | — |
| 027 T26 | espera a que la cuenta de Codex admita un modelo, y a la GPU | — |
| Fase 2 | campaña integral lanzada en la GPU (`output/asistente_integral_20261106.json`) | — |

Con 0,8 GB de memoria libre (procesos del editor y de otras sesiones), DIgSILENT no se abre en paralelo con el
entrenamiento: la fase 3 empieza al terminar la fase 2.

## 2. Plan de cierre

Reglas: una tarjeta o trabajo pesado a la vez (DIgSILENT, GPU, suite), integrar cada una antes de la
siguiente; DIgSILENT solo en proyectos de prueba nuevos importados por la web, nunca en PA217, AL209
ni otros ya trabajados; la 002 T7–T12 va al final.

### Fase 0. Saneamiento (sin DIgSILENT, en un día)

| # | Tarea | Hecho cuando |
| --- | --- | --- |
| 0.1 | Confirmar con eafcf16e los cambios de 004 y 024 y hacer su commit; 004 a «implementada» | `pytest -q tests/test_cargas_pf*.py tests/test_digital_twin_capture.py` en verde, commit en `main` |
| 0.2 | `estado_specs.py --escribir` y tabla de `CLAUDE.md` al día | `--comprobar` sale con 0 y `test_trazabilidad_specs` pasa |
| 0.3 | Renumerar `feat/093-retomar-tras-suspender` a 096 y fundirla, o descartarla | la spec existe con su número y sus pruebas, o la rama queda archivada con su motivo |
| 0.4 | Comprobar 085:RF-7–9 en `main`; si faltan, traer la parada bayesiana con su prueba | una prueba cita 085:RF-7 a RF-9 |
| 0.5 | Pasar a RF los defectos de 1.4 que no esperan decisión | cada uno con su RF y su tarea en la spec indicada |
| 0.6 | Archivar los worktrees cuyas ramas están en `main` (con permiso del usuario) | `git worktree list` solo con trabajo vivo; archivo en `D:/archivo_worktrees_antiguos_*` |

### Fase 1. Código pendiente (aprobadas)

En este orden, porque las primeras desbloquean pruebas en DIgSILENT de la fase 3:

1. **042 / 087 / 086**: refuerzo por escalera (RF-43), escalera por costo con las 3 más baratas y la
   definitiva, y 086 T5, T38, T39 (cabecera compartida, déficit previo, factor 1,25).
2. **004 RF-52**: dimensionar el transformador de carga nueva a máxima ≤ 80 %.
3. **094** T4, T6, T7: perfil en la web y en el informe, antes y después de cada propuesta, gráfico de DIgSILENT.
4. **049** T1–T3: protecciones (no empezada; 0 de 10 RF con prueba).
5. **045** T3, **074** T5, T7, T8, **071** T5, **089** T5, T7, **072** T13, **050** T1b–T5b.
6. **027** T26, **047** T4, T8.

### Fase 2. GPU (libre hoy)

Una sola campaña, `tools/asistente_entrenar.py --integral --afinar --validacion-cruzada`, cierra a la vez
068 T7, 069 T7, 075 T6, 079 T7 y 085 T6; después 070 T11 (candidato en la prueba nueva). Aparte, por
turno: 043 T9 (reapertura en CUDA), 027 T11 y 047 T7 (QLoRA, solo si las puertas lo piden).
Hecho cuando: la decisión del registro de cada familia queda leída y anotada en su tarea.

### Fase 3. DIgSILENT por proyecto de prueba (78 tareas)

Cada proyecto se importa una vez por la web (`tools/sistema_web.py`) y sirve a varias tareas:

| Grupo | Proyecto de prueba | Tareas |
| --- | --- | --- |
| G1 | CA101 + PE104, TXT (086 T24, R1) | 008 T7, 011 T19, 012 T13, 013 T7, 017 T13, T14, T19, 037 T4, 044 T4, 048 T4 |
| G2 | Pisco, TXT (086 T26, R3) | 028 T15, 042 T37, T44, T48, T50, 073 T8, 081 T24, 083 T3, 087 T12, T13, T27, 092 T2, 084 T8, T9 |
| G3 | NA203 + NA205, TXT (086 T27, R4) | 039 T4, 042 T6, 052 T4, 028 T6, 067 T9 |
| G4 | NJA202 y R205, VNR-GIS de Electro Oriente (086 T28, R5) | 051 T3, 055 T2, 056 T3, 042 T29, 087 T14, 081 T16, 058 T7 |
| G5 | SI213 y PN107, MDB (086 T25, R2) | 016 T18, 081 T20 |
| G6 | Copias de prueba de AL209, PA217/TM105 y PE102 | 094 T5, 093 T2, 025 T21, 004 T20, 042 T42 |
| G7 | Asistente desde la consola | 026 T12, 070 T9, T10, 078 T6, T7, 027 T14, T22, T29–T31, 086 T30 |
| G8 | Navegador sin DIgSILENT | 081 T22, 073 T12, 086 T29 |
| G9 | Robustez y cortes | 081 T10–T14, 086 T33, T36 |
| G10 | Protecciones y gemelo | 049 T4, 045 T4, 065 T12 |

Cada tarea cierra con su evidencia (trabajo de la web, JSON de salida) anotada en su `tasks.md`.

### Fase 4. Versión 1.0 (086)

086 T1 (decisiones D1–D7), T9 / 058 T6 (renombrar la carpeta, con ensayo en copia), T40 y T32
(`setup.exe` en este equipo), T41 (persona ajena), T31 / 058 T5 / 025 T22 / 065 T13 (suite completa
sin omitidas, líneas base y determinismo) y T34 (legal, licencia, `v1.0.0`).

### Fase 5. Al final

002 T7–T12 (capas y `frontend/src`), con todas las ramas ya fundidas o descartadas; luego decidir las
reservadas 003 (rama `feat/integracion-web-retiro-gui`, 67 commits), 031 y 091: activarlas o retirarlas.

## 3. Decisiones del usuario que bloquean

1. FP por defecto de las cargas nuevas que solo traen kW.
2. Si el refuerzo por terna compite por costo con la sección.
3. 086 D1–D7, asesoría legal (T34) y quién hace de persona ajena (T41).
4. Si el asistente se vende como beta (086 T30).
5. Archivar los worktrees antiguos (0.6) y destino de las reservadas 003, 031 y 091.
