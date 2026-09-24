# De conversor a plataforma de planificación PIDE

**Fecha**: 23 de septiembre de 2026
**Estado**: propuesta, pendiente de decidir la secuencia
**Escrito para**: quien decide el rumbo y el presupuesto del proyecto, y el equipo que lo va a construir

---

## 0. Lo primero: qué se implementó de la propuesta de front React + API

**Nada.** Comprobado en el repositorio a fecha de hoy:

```
package.json        no existe
Dockerfile          no existe
docker-compose.yml  no existe
*.tsx / *.jsx       no existe
FastAPI             no está en requirements.txt
```

Aquello (GridMind, BambooGrid, TENSA) fue una recomendación del diagnóstico del 22 de
septiembre, presentada entonces como «más trabajo, más robusto» y con la advertencia de
que «para solo diagnóstico + tabla SED suele ser exceso». Esa advertencia sigue siendo
correcta **para el alcance de entonces**. Deja de serlo con la meta que se plantea
ahora, y este documento explica por qué y qué cambia.

Lo que sí existe hoy, verificado:

| Capa | Estado |
|---|---|
| Motor de conversión CYMDIST → DGS | Completo, 96 alimentadores, 4.185,7 km |
| Dos alternativas de entrada (TXT y Access) | Completo |
| Georreferenciación y diagrama | Completo |
| Catálogo de parámetros y corrección por ficha | Completo |
| Módulos de cargas (4) y creación de SED | Completo |
| Integración con PowerFactory | Por subproceso, `powerfactory.pyd` |
| Validación independiente | pandapower como oráculo |
| Interfaz | **Tkinter de escritorio**, un solo usuario, síncrona |
| Persistencia | **Ninguna**: ficheros sueltos en `output/` |
| Servicio / API / concurrencia | **No existe** |
| Pruebas | 350 pasan, 58 se omiten |

El motor está maduro. **Lo que no existe es todo lo que convierte un motor en un
producto**: servicio, persistencia, concurrencia, multiusuario y despliegue.

---

## 1. Qué es PIDE, con la fuente delante

PIDE es el **Plan de Inversiones en Distribución Eléctrica**. Las concesionarias lo
presentan a Osinergmin al inicio de cada fijación del VAD, asociado a un *Estudio de
Planificación Eléctrica de Largo Plazo*; Osinergmin lo aprueba y lo incorpora a la
inversión anual reconocida en la tarifa.

No es un ejercicio interno de ingeniería: **es el expediente del que depende cuánta
inversión le reconocen a la empresa en la tarifa**. Eso fija el listón de calidad del
software: lo que produzca tiene que ser defendible ante el regulador.

### 1.1 El hallazgo que cambia el proyecto

Los Términos de Referencia del VAD 2026-2030 / 2027-2031
([R033-2026-OS-CD, Anexo N° 6](https://www2.osinergmin.gob.pe/GRT/Procesos-Regulatorios/VAD-2026-2030_2027-2031/Anexo-T%C3%A9rminosVAD-2026-2030-2027-2031-R033-2026-OS-CD.pdf))
describen un **«Modelo Geo-referenciado para la Optimización de Redes Eléctricas»**.
Merece la pena leer cómo lo plantean, porque describe este proyecto:

> «La metodología de diseño actual […] ubica los centros de carga en función de la
> experiencia del diseñador, entregando solo resultados de caída de tensión, limitándose
> a otros parámetros eléctricos de la red, tales como: desbalance de carga, pérdidas
> técnicas de potencia, flujos de potencia, cargabilidad de los conductores y no
> considera parámetros o cuantificadores económicos.»

Y lo que el modelo debe hacer:

> «La implementación de un modelo georreferenciado aplicado a la red real permite, a
> partir de la traza real de los circuitos y de la ubicación de la demanda, evaluar por
> circuito los calibres y niveles de pérdidas eficientes. […] Este modelo mantiene
> inalterada la traza de la red real.»

**Esa es exactamente la posición del proyecto.** Ya tiene la traza real georreferenciada,
las SED con su potencia, las cargas por cliente y —desde esta semana— un catálogo de
parámetros de conductor contrastado con ficha de fabricante. Lo que falta es la capa de
optimización económica encima.

### 1.2 Criterios numéricos que el TdR fija

Se transcriben porque son el contrato con el regulador, no una preferencia de diseño:

| Criterio | Valor | Dónde |
|---|---|---|
| Tasa de retorno para el conductor económico | **12 %** | Anexo 6, MT |
| Tasa de devolución por incumplimiento de calidad | 12 % | § Mejora de calidad |
| Valor de la energía no suministrada (ENS) | **1 US$/kWh** | § Mejora de calidad |
| Caída de tensión máxima en zonas rurales | **6 %** | Anexo 6, MRT |
| Sección mínima normalizada | **25 mm² Al, 16 mm² Cu** | Anexo 6 |
| Sección mínima recomendada (ACSR y aleación) | 35 mm² | Anexo 6 |
| Umbral para adoptar red monofásica | corriente **< 10 A** | Anexo 6 |
| Corriente admisible en LMRT | 10 A a 20 A | Anexo 6 |
| Tensiones fase-fase | **10 kV y 22,9 kV** | Anexo 6 |
| Vano típico MRT | 160 m | Anexo 6 |
| Tensión de paso / contacto | 65 V a 30 mA | Anexo 6 |
| Tope de proyectos de innovación | 1 % de ingresos del año anterior | § Innovación |
| Indicadores exigidos por proyecto | **VAN, TIR y período de retorno** | § Proyectos |

Y el método de selección de calibre:

> «La elección de los calibres óptimos para red troncal y derivaciones se realizará
> considerando la corriente económica. […] Esta selección considerará los costos de
> energía, una tasa de retorno del 12 %, la vida útil del conductor, el factor de carga
> y las pérdidas típicas.»

Más reglas de negocio explícitas: conductores de **cobre en zonas corrosivas**, ajuste de
calibres trifásicos a secciones equivalentes en tramos mono y bifásicos, y conservación
de la proporción real de red monofásica/bifásica/trifásica por circuito.

### 1.3 Una observación sobre el trabajo ya hecho

El selector de conductor que se construyó para las SED nuevas usa **ampacidad y caída de
tensión**. Ya se documentó que en el rango de una SED (15–630 kVA) ninguno de los dos
criterios discrimina y sale siempre el menor del catálogo.

El TdR explica por qué: **el criterio correcto no es ninguno de esos dos, es el coste
total capitalizado**. La «corriente económica» es la que iguala el coste marginal de
más cobre con el valor presente de las pérdidas que ese cobre evita, a 12 % y a lo largo
de la vida del conductor. Ampacidad y caída de tensión son **restricciones**, no la
función objetivo.

Es decir: el módulo existente no está mal, está **incompleto**, y el TdR dice
exactamente en qué dirección completarlo. Es el mejor punto de entrada a la meta.

---

## 2. Los módulos de PowerFactory que hacen falta

Leído el índice del `UserManual_en.pdf` de PowerFactory 2024 (1.490 páginas, instalado
en `C:\Program Files\DIgSILENT\PowerFactory 2024\Help\`). Estos son los capítulos que
sirven a PIDE, con lo que aporta cada uno:

| Cap. | Módulo | Para qué en PIDE | Hoy |
|---|---|---|---|
| 24 | Load Flow Analysis | Base de todo; **desequilibrado**, que el TdR exige | ✅ usado |
| 25 | Short-Circuit Analysis | Dimensionar protecciones, verificar Ithr | ❌ |
| 26 | Contingency Analysis | Criterio N-1, respaldo entre alimentadores | ❌ |
| 27 | **Quasi-Dynamic Simulation** | Perfiles anuales → factor de pérdidas real | ❌ |
| 32 | Protection | Coordinación, selectividad; incentivo de calidad | ❌ |
| 34 | **Cable Analysis** (Sizing, Ampacity) | Calibre y ampacidad con criterio IEC | ❌ |
| 38 | **Optimal Power Flow** | Optimización con restricciones de red | ❌ |
| 41.2 | Hosting Capacity | Capacidad de alojamiento de GD | ❌ |
| 41.3 | Backbone Calculation | Troncal vs. derivaciones, que el TdR distingue | ⚠️ parcial |
| 41.6 | **Tie Open Point Optimisation** | Reconfiguración: punto de apertura óptimo | ❌ |
| 41.7 | Phase Balance Optimisation | Desbalance de fases, que el TdR nombra | ❌ |
| 41.8 | Voltage Profile Optimisation | Perfil de tensión | ❌ |
| 41.9 | **Optimal Equipment Placement** | Dónde poner reconectadores y seccionadores | ❌ |
| 41.10 | **Optimal Capacitor Placement** | «Niveles de compensación» del Anexo 6 | ❌ |
| 41.11 | Optimisation Algorithms | El motor que usan los anteriores | ❌ |
| 43.2 | **Techno-Economical Calculation** | VAN / TIR / período de retorno | ❌ |
| 43.3 | Techno-Economical Study Case Comparison | **Comparar alternativas de inversión** | ❌ |
| 44 | Probabilistic Analysis | Incertidumbre de la demanda proyectada | ❌ |
| 45 | **Reliability Analysis** | SAIDI / SAIFI / **ENS a 1 US$/kWh** | ❌ |
| 46.3 | **Optimal RCS Placement** | Telemando óptimo (proyecto típico de calidad) | ❌ |
| 46.5 | **Optimal Recloser Placement** | Reconectadores (proyecto típico de calidad) | ❌ |
| 16 | Network Variations / Expansion Stages | **Horizonte multianual del plan** | ❌ |
| 17 | Parameter Characteristics, Load States | Proyección de demanda por año | ❌ |
| 21/22 | Task Automation / Scripting | Lanzar todo sin tocar la interfaz | ⚠️ parcial |

El capítulo 43 merece una cita, porque describe el problema de PIDE con esas palabras:

> «This chapter presents the PowerFactory Economic Analysis Tools, which are dedicated
> functions for the economic assessment and profitability evaluation of **network
> development plans**. […] It allows the user to calculate the net present value of a
> particular network expansion strategy, which is defined through **Network Variations
> and their respective Expansion Stages over time**, considering […] the monetary value
> of the equipment necessary for the renovation, optimisation or expansion of the
> investigated network, its depreciation over time, its residual value and its expected
> useful life.»

Valor presente neto de una estrategia de expansión definida por etapas a lo largo del
tiempo, con depreciación, valor residual y vida útil. Es el PIDE, descrito por el manual
de una herramienta que la empresa ya tiene instalada.

**Lo que esto significa**: PowerFactory ya trae casi todo lo que PIDE pide, incluida la
evaluación técnico-económica y la comparación de alternativas. El proyecto **no tiene que
reimplementar los algoritmos**; tiene que construir la capa que prepara los casos, los
lanza, recoge resultados y los convierte en el expediente del PIDE.

Eso cambia el tamaño del problema. No es «escribir un optimizador multiobjetivo desde
cero»; es «orquestar los módulos de PowerFactory y poner encima la función objetivo
multiobjetivo y la lógica regulatoria peruana, que PowerFactory no conoce».

---

## 3. La restricción que condiciona todo el despliegue

**PowerFactory no se contenedoriza en Linux.** Soporta modo *engine* sin interfaz para
despliegue en servidor, pero el camino oficial es Windows: el `ConnectorService` es un
servicio Windows sobre ASP.NET Core, y `powerfactory.pyd` es una extensión binaria atada
a una versión concreta de CPython (PF 2024 → 3.12). A esto se suma la licencia, que no es
de las que se replican en un contenedor efímero.

Hay que decirlo ahora porque define la arquitectura: **no se puede meter todo en un
`docker compose up`**. Lo que sí se puede, y es lo que propone este documento:

- **Contenedorizable**: API, base de datos, cola de trabajos, interfaz web, y toda la
  analítica que no necesita PowerFactory (pandapower, la optimización, la evaluación
  económica, la proyección de demanda, los informes).
- **No contenedorizable en Linux**: el *worker* de PowerFactory, que corre en una
  máquina Windows con licencia y se conecta a la misma cola.

Esto no es una limitación del diseño, es una propiedad del producto de terceros. La
arquitectura la absorbe en lugar de fingir que no existe.

---

## 4. Arquitectura propuesta

```
┌──────────────────────────────────────────────────────────┐
│  Navegador — React + TypeScript                          │
│  mapa (MapLibre) · unifilar (Cytoscape) · tablas · KPI   │
└───────────────────────┬──────────────────────────────────┘
                        │ HTTP + WebSocket (progreso en vivo)
┌───────────────────────┴──────────────────────────────────┐
│  API — FastAPI (async)                          contenedor│
│  proyectos · casos · escenarios · trabajos · resultados   │
└───────┬───────────────────────────────────┬──────────────┘
        │                                   │
┌───────┴────────────┐            ┌─────────┴──────────────┐
│ PostgreSQL+PostGIS │            │ Cola de trabajos       │
│ red, escenarios,   │            │ (Redis / RQ o Celery)  │
│ resultados, audit  │ contenedor │                        │ contenedor
└────────────────────┘            └─────────┬──────────────┘
                                            │
                    ┌───────────────────────┴──────────────┐
                    │                                      │
         ┌──────────┴───────────┐            ┌─────────────┴─────────────┐
         │ Worker analítico     │            │ Worker PowerFactory       │
         │ pandapower, optim.,  │ contenedor │ powerfactory.pyd          │ Windows
         │ economía, informes   │            │ OPF, fiabilidad, QDS…     │ (sin contenedor)
         └──────────────────────┘            └───────────────────────────┘
                    │                                      │
                    └──────────────┬───────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │  igea_dgs  — el motor de hoy │
                    │  intacto, como biblioteca    │
                    └──────────────────────────────┘
```

**Principio rector**: `igea_dgs` no se reescribe. Es una biblioteca de Python con 350
pruebas que funciona; se le pone un servicio encima. La Tkinter actual se mantiene
mientras la web no la iguale, porque hoy es lo que la empresa usa para trabajar.

### 4.1 Por qué cada pieza

- **PostgreSQL + PostGIS** — la red es geometría. Hoy vive en ficheros y no se puede
  consultar, versionar ni comparar entre años. PostGIS permite «qué tramos están a menos
  de 500 m de este punto» y «qué cambió entre el escenario 2027 y el 2031» sin cargar
  nada en memoria. Es además lo que hace posible el multiusuario.
- **Cola de trabajos** — una optimización multiobjetivo sobre 96 alimentadores no cabe
  en una petición HTTP. Hoy la Tkinter lo resuelve con hilos y subprocesos, que es lo
  correcto para un escritorio y no escala a varios usuarios.
- **WebSocket** — el progreso ya existe en el motor (`on_progress`); solo hay que
  sacarlo por un canal que el navegador entienda.
- **React** — el unifilar y el mapa son el producto. La tabla de SED se puede servir en
  HTML plano; un unifilar interactivo sobre 38.657 tramos, no.

---

## 5. Lo que hay que construir, por fases

Cada fase deja algo utilizable. Ninguna exige terminar la siguiente para dar valor.

### Fase A — Conductor económico y evaluación económica *(la que más valor da por esfuerzo)*

El corazón del Anexo 6, y se apoya en todo lo que ya existe.

1. `economics.py` — valor presente de pérdidas, anualidad a 12 %, VAN, TIR, período de
   retorno, ENS a 1 US$/kWh.
2. `conductor_economico.py` — rangos de corriente económica por calibre a partir del
   coste de energía, el factor de carga, la vida útil y el precio de la sección.
   Sustituye al criterio de ampacidad como función objetivo y lo conserva como
   restricción, junto con la caída de tensión (6 % rural) y las secciones mínimas.
3. Reglas del TdR: cobre en zona corrosiva, monofásico por debajo de 10 A, conservación
   de la proporción real mono/bi/trifásica, equivalencia de secciones.
4. Salida en el **formato VNR por sector típico** que el TdR exige.

**Entregable**: por cada circuito, el calibre económico tramo a tramo, las pérdidas
eficientes y el ahorro capitalizado frente a la red actual. Eso ya es un capítulo del
PIDE.

### Fase B — Fiabilidad y calidad de suministro

`ElmTerm`/`ElmLne` necesitan tasas de falla y tiempos de reposición (el catálogo ya tiene
las columnas `FailRate`, `TmpFailRate`, `OutageTime` del CYMDIST, hoy en cero).

1. Poblar los parámetros de fiabilidad desde el histórico de la empresa.
2. Lanzar `Reliability Analysis` (cap. 45) → SAIDI, SAIFI, ENS.
3. `Optimal Recloser Placement` y `Optimal RCS Placement` (cap. 46) → los proyectos de
   calidad que el TdR nombra uno por uno.
4. Valorizar con ENS a 1 US$/kWh y producir la hoja de ruta de calidad que exige el
   régimen de incentivos.

### Fase C — Horizonte multianual y proyección de demanda

1. Proyección de demanda por SED y por circuito, con los factores de caracterización
   (consumo y simultaneidad) que el TdR menciona.
2. `Network Variations` y `Expansion Stages` (cap. 16) para representar cada año.
3. `Quasi-Dynamic Simulation` (cap. 27) para el factor de pérdidas real en lugar de uno
   típico.
4. `Probabilistic Analysis` (cap. 44) para la incertidumbre.

### Fase D — Optimización multiobjetivo

Aquí y no antes, porque necesita A, B y C para tener funciones objetivo que medir.

Objetivos: coste de inversión, pérdidas capitalizadas, ENS, y cumplimiento de tensión y
cargabilidad. Restricciones: las del TdR. Salida: **frente de Pareto** de alternativas de
inversión, no una única respuesta — que es justamente lo que el TdR pide cuando exige
«evaluación técnica y económica que justifique el beneficio» y comparación de
alternativas.

Los algoritmos de PowerFactory (cap. 41.11, 38) cubren buena parte; encima va la
formulación multiobjetivo y la lógica regulatoria.

### Fase E — Servicio, persistencia y web

1. Esquema PostgreSQL + PostGIS y migración de lo que hoy son ficheros.
2. FastAPI: proyectos, escenarios, trabajos, resultados.
3. Cola de trabajos y los dos tipos de *worker*.
4. React: mapa, unifilar, tablero de KPI y comparador de alternativas.
5. `docker compose` para todo menos el *worker* de PowerFactory.

### Fase F — Producto comercial

Autenticación y roles, trazabilidad de quién cambió qué (imprescindible para un
expediente regulatorio), licenciamiento, copias de seguridad, observabilidad, y el
generador del expediente PIDE completo.

---

## 6. Sobre el orden

La tentación es empezar por la Fase E, porque es la más visible. Sería un error: se
tendría una web bonita que enseña lo mismo que hoy enseña la Tkinter.

La Fase A, en cambio, **produce un capítulo del PIDE con la red real de la empresa** y
no necesita ni API ni base de datos. Y deja construido el vocabulario económico (VAN,
TIR, anualidad, ENS) del que dependen B, C y D.

Recomendación: **A → B → C/E en paralelo → D → F**. La E puede adelantarse en cuanto
haya más de una persona usando el sistema a la vez, que es cuando el escritorio deja de
bastar.

---

## 7. Lo que falta averiguar

Sin esto, varias fases se quedan a medias, y no está en el código ni en el TdR:

1. **Precios unitarios** de conductor, estructura y SED de la empresa. Sin ellos no hay
   conductor económico: la función objetivo necesita el coste marginal de la sección.
2. **Coste de la energía** (US$/kWh) y **factor de carga** por sector típico.
3. **Histórico de fallas** por tipo de elemento, para las tasas de la Fase B.
4. **Proyección de demanda** o la serie histórica para construirla.
5. **Zonas corrosivas** delimitadas, para la regla del cobre.
6. **Sector típico** de cada circuito (ST1…ST4, SER), que gobierna varios criterios.
7. Qué **módulos de PowerFactory tiene licenciados** la empresa. El manual los documenta
   todos; la licencia decide cuáles se pueden usar. Conviene comprobarlo antes de
   diseñar sobre uno que no esté disponible.
