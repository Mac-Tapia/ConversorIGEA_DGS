# Conversor IGEA/CYMDIST → DIgSILENT PowerFactory DGS

Convierte los TXT que exporta IGEA/CYMDIST (RED, CARGA, BD_Equipo) en ficheros `.dgs`
que se importan en PowerFactory, un alimentador por fichero o todos en una red unida.

## Entorno

- Python **3.12 exacto**, en `.venv` (`.venv/Scripts/python.exe`). La API de PowerFactory 2024 solo carga en 3.12.
- Instalación: `pip install -r requirements.txt`; los drivers opcionales de VNR-GIS, aparte con `pip install -r requirements-drivers.txt`. La web necesita compilar el front una vez: `cd frontend && npm install && npm run build`.
- Web: `run_gui.bat` o `igea-dgs-web`. CLI: `igea-dgs convert --red ... --loads ... --equipment ... --all --out-dir out --workers 0`.

## Skills del proyecto

- `.claude/skills/igea-dgs-backend/SKILL.md`: reglas del motor, la escala y la API. **Léelo antes de tocar `src/igea_dgs/`.**
- `.claude/skills/igea-dgs-frontend/SKILL.md`: UX y checklist de la interfaz web (React en `frontend/`). Léelo antes de tocar `frontend/src/` o `src/igea_dgs/web/`.
- `.claude/skills/igea-dgs-spec/SKILL.md`: desarrollo guiado por especificaciones. Toda funcionalidad o reorganización que no sea un arreglo de una línea empieza por `specs/NNN-*/spec.md` (requisitos `RF-n` en EARS), luego plan y tareas; las pruebas citan `NNN:RF-n`.
- Las copias de `.cursor/skills/` son solo punteros a estas: el texto vigente es uno.

## Especificaciones

- `docs/constitution.md`: principios innegociables, cada uno con cómo se comprueba.
- `specs/NNN-<nombre>/{spec,plan,tasks}.md`: una carpeta por funcionalidad. Estado a 2026-10-16 (verificación RF por RF del 2026-10-14 en `docs/VERIFICACION_SPECS_2026-10-14.md`; arquitectura en `docs/ARQUITECTURA.md`):

  | Spec | Estado |
  | --- | --- |
  | 001 reorganización | cumplida |
  | 002 arquitectura por capas | aprobada; plan y tareas escritos el 2026-10-10, **pendientes de aprobar**; T1 (línea base) y T5 (perfil de empresa) adelantadas el 2026-10-12 |
  | 003 | no existe: la citan la 002 y la memoria para lo que queda de la rama `feat/integracion-web-retiro-gui`, tras las capas |
  | 004 cargas en PowerFactory | cumplida (2026-10-14) |
  | 005 carpeta de proyectos PF | implementada; falta la prueba en DIgSILENT (T12) |
  | 006 ajuste a la máxima | implementada; falta la prueba en DIgSILENT (T8): signo y lado de la cabecera |
  | 007 cargas sobre el ajuste | implementada el 2026-10-10 (una variación por carga, base del ajuste, RF-36/37 para varios alimentadores); falta la prueba en DIgSILENT (T11) |
  | 008 pestaña en tres pasos | implementada; falta la prueba en DIgSILENT con dos alimentadores (T7) |
  | 009 inventario del repositorio | cumplida (2026-10-14) |
  | 010 trazado GPS de las líneas | cumplida; probada en DIgSILENT con NA203 + NA205 (574/574 líneas) |
  | 011 estudios y obras de mejora sobre la red calibrada | implementada el 2026-10-12 (129 RF, T1 a T18 y T17b, añadida en la validación para los guiones del operador en la web); falta la prueba en DIgSILENT (T19), con la lista de lo que confirmar en el plan |
  | 012 confiabilidad y capacidad de la red | spec aprobada el 2026-10-11 (72 RF): confiabilidad, reconectadores (`ComOpri`), capacidad de alojamiento, curvas PV y condensadores con los módulos nativos; tasas y costes de un libro Excel de la empresa. Plan y tareas aprobados el mismo día; T1 y T2 hechas (sondas en DIgSILENT real el 2026-10-12, RF-69 a RF-72 nuevos), sigue T3; T7, T8 y T11 dependen de T13, T15a, T16 y T17 de la 011 |
  | 013 mes de análisis y transferencia | borrador del 2026-10-13 con plan, sin `tasks.md` ni aprobación; RF-1 a RF-6 ya tienen prueba; del 2026-10-15, selector de mes en «2.3» (RF-8, RF-10, RF-12, RF-16; RF-7 solo con los meses con libro, sin mirar la cabecera) |
  | 014 calibración en «Sin proyecto» | implementada el 2026-10-14 (28 RF, todos con prueba; T1 a T10): se calibra en «Sin proyecto», donde también van los cambios del operador (gana lo manual); «Con proyecto» es su copia con las cargas nuevas, sin duplicarlas; cambia 006:RF-28, 011:RF-2/6/7/8/50 y 004:RF-15 (anotado en cada una). Falta la prueba en DIgSILENT con CA101 (T9), que espera a la T12 de la 015; del 2026-10-16, RF-29 y RF-30 (T11, probada en DIgSILENT con PN107): la carga nueva ya creada se reconoce por su nombre, también con el sufijo «(n)» que le pone la etapa, o por su punto (≤ 1 m) con otro nombre; PN107 creaba CH_9 dos veces; del 2026-10-17, RF-31 a RF-34 (T12, probada en DIgSILENT en una copia de PN107): lo hecho a mano en «Sin proyecto» pasa a «Con proyecto» |
  | 015 «Caso base» verificado | implementada el 2026-10-14 (67 RF, T1 a T11, T13 a T23; suite en verde; del 2026-10-15: RF-47 a RF-52, validación física con lo que consume cada carga en el flujo y balance de la cabecera; RF-44, RF-45 y RF-53 a RF-58, escaladas por potencia instalada × FP del perfil (Electro Dunas 0,98) con un mismo scale0 y fijas con su EA/ERI; RF-59 a RF-61, clientes sobre su transformador avisados y bancos instalados del propio proyecto listados, sin tomar nada de otro; RF-62 a RF-67, fijas con FP bajo compensadas a 0,98 por su banco propio (FP real y corregido en el informe), bancos a su máxima capacidad y toda escalada a 0,98 comprobada; CA101 calibrado en DIgSILENT a −0,02 %): el «Caso base» se verifica frente al archivo original (GPS, trazado, conectividad, diagrama, capacidades) y su flujo solo al importar el DGS, tras el oráculo; si no converge se reduce la demanda, sin bloquear. «Sin proyecto» es su copia: fijas con su P y Q, escaladas con su P y Q del archivo y un mismo factor de escala (scale0) en su escenario, sin variaciones; los ajustes del flujo que necesitó se quedan para que converja. Variaciones solo en «Con proyecto», una por carga nueva. Probada desde cero con CA101 en DIgSILENT; T12 sigue abierta por el proyecto CA101 existente, que no converge en su «Caso base» |
  | 016 troncal, enlace y conexión en un tramo | cumplida el 2026-10-16 (87 RF, T1 a T15; RF-88 y T16 nuevos el mismo día, falta probarlos en DIgSILENT: cable hasta la carga nueva solo a más de 25 m de su nodo de media; RF-89 y T17, lo que crean cargas y obras queda dibujado en el diagrama (probado con el enlace de IN111 + TA225); aprobada el 2026-10-14 con 73); plan y tareas (T1 a T14) aprobados el mismo día; T1 a T13 hechas (`Application.SplitLine` en DIgSILENT real y en `fake_pf`; `troncal.py`; reglas de las obras en `obras_pf.py`; red, troncal y partir tramo en los guiones; construir el enlace y la migración; «Con proyecto» se crea tras las obras de «Sin proyecto»; cargas nuevas en la troncal; la transferencia no cierra un enlace entre tensiones distintas; web; 007 y 011 anotadas), T14 cerrada el 2026-10-16 (probado en DIgSILENT con IN111 y TA225: cargas, enlace, migración y terna; «Con proyecto» converge; RF-74 a RF-80); T15, enlace trazado por la vía con OSRM sobre OpenStreetMap (RF-81 a RF-87, solo salen las dos coordenadas): troncal de las obras = camino continuo más largo desde la cabecera, toda a la sección pedida (N-1 y transferencia siguen con la de DIgSILENT); toda obra de «Sin proyecto» pasa a «Con proyecto» (cambia 011:RF-57); obra de enlace solo en «Con proyecto», partiendo un tramo con un nodo nuevo donde la tensión y la cargabilidad del que recibe lo permiten; las cargas nuevas también parten el tramo más cercano de la troncal (cambia 007:RF-24/30/31); enlace entre tensiones distintas (IN111 10 kV, TA225 22,9 kV) abierto, y migración a 22,9 kV desde un nodo que indica el operador, aguas abajo, en otra variación |
  | 017 informes de estudio y factibilidad | aprobada el 2026-10-15 (143 RF; plan y tareas T1 a T15 aprobados el mismo día; bancos existentes copiados del proyecto anterior «CA101 13», RF-36b a RF-36d; necesita la 016 para migrar por la troncal hasta la SED del cliente): informe de estudio eléctrico (modelo Casa Blanca, obras en escalera: bancos existentes y nuevos, reguladores, conductor, migración) e informe de factibilidad de una carga nueva (modelo EMAPICA, pérdidas del libro de la empresa, transformador de la SET del proyecto de transmisión), en `.docx` con imágenes de DIgSILENT, y paso «5 · Informes» en la web; sin dudas abiertas; caso de prueba CA101 desde cero; del 2026-10-16, etapa «refuerzo de la red» con la terna y el enlace (RF-126, RF-127, T16) e informe de estudio probado con IN111 y TA225; la factibilidad (T14) es un análisis aparte de una carga nueva sola, pendiente con otro alimentador; del 2026-10-16, informe de estudio por alternativas (RF-128 a RF-135, T17): 1, los bancos; 2, el cambio de sección con el trecho desde–hasta, su plano y su detalle; bancos existentes por nodo; CA101 medido en DIgSILENT |
  | 018 vínculo compartido entre espacios | implementada el 2026-10-15 (13 RF, T1 a T11): el vínculo de un proyecto de DIgSILENT vale en cualquier espacio con la misma fuente (registro `output/web/vinculos_pf.json`, sembrado al arrancar); la verificación del «Caso base» exige el vínculo en el servidor y no la red en memoria; el DGS aceptado se comprueba antes de cada acción; un espacio sin fuente usa sola la ejecución con la que se aceptó (copia ejecución, calibración y libros de demanda); la lista de proyectos sobrevive a un reinicio. Cambia 015 (la verificación ya no crea vínculos). Probada en DIgSILENT con CA101 desde un espacio nuevo |
  | 019 arnés de DIgSILENT | cumplida el 2026-10-15 (T1 a T6) y el 2026-10-18 (T7): un solo dueño del motor en la máquina (`pf_arnes`, turno con quién y desde cuándo, espera de 10 min, libera al dueño muerto, avisa con DIgSILENT abierto a mano); conexión común con reintento ante 4002 en todos los guiones; la web los manda a `tools/pf_servidor.py`, que mantiene DIgSILENT abierto entre órdenes sin reactivar el proyecto (27 s → 1 s en CA101) y se cierra a los 2 min sin órdenes; obra `consigna` de cabecera y registro de validadores. Probada en DIgSILENT con CA101. Del 2026-10-18, RF-14 a RF-16 (T7, probada en DIgSILENT: la sonda entra a los 3 s): el servidor ocioso cede el turno al guion que espera, salida línea a línea y la API de DIgSILENT buscada en su instalación. Del 2026-10-19, RF-17 a RF-22 (T8, T9, probada en DIgSILENT tras el fallo de «Leer proyectos» después de importar): el turno sigue del proceso hasta que muere (DIgSILENT aún se cierra tras `atexit`), identidad por pid e inicio, órdenes de clientes muertos descartadas, corte de la web solo sobre su orden, servidor fuera del árbol del cliente, reintento de «Leer proyectos», `servidor.log` con horas y cola limpia al arrancar |
  | 020 SED fijas sobrecargadas | aprobada el 2026-10-16 (32 RF), con plan y tareas; T1 a T8 hechas: aviso al principio del resultado del ajuste, propuesta por SED con las fichas de la NTP 370.400 del perfil (Tablas 6 y 7 de FONAFE, máxima ≤ 80 %, unidades de 630 kVA en paralelo por encima) y botón «Implementar transformadores», que los cambia en «Sin proyecto», en la red, y recalibra; falta la prueba en DIgSILENT (T10) con PA217 importado de nuevo |
  | 021 maniobras, SED, curvas y central térmica | RF-1 a RF-49 cumplidos el 2026-10-17 (fusibles y seccionadores como `StaSwitch`, SED con su barra, curvas de cabecera, central térmica de NA205 calibrada por zonas en una copia: −0,08 % y −0,01 %). El mismo día, RF-50 a RF-53 (mes de análisis e instante coincidente, T16) y RF-54 a RF-60 (calibración por proyecto: todos los alimentadores en los mismos flujos, T18), hechos. Del mismo día, RF-61 a RF-69 (tensión en la fuente y bancos que faltan, T19 y T20). T17 cerrada: NA203 + NA205 con su central calibrados a la vez desde la web, sin remedios del flujo, tras 11 transformadores con ficha NTP y 2 bancos de 450 kvar en NA203 |
  | 023 VNR-GIS desde la copia de SQL Server | aprobada e implementada el 2026-10-18 (10 RF, T1 a T4): la copia `.bak` de cualquier concesionaria se restaura en SQL Server Express (`.\SQLEXPRESS`, `IGEA_SQLSERVER`) con su huella, se lee por los campos del modelo VNR-GIS del regulador y entra como fuente VNR-GIS en la web y el CLI; tensión (códigos MT de los parámetros, D = 10 kV, G = 22,9 kV) y CRS (`empEmpresa`) salen de la copia. IN111 de Electro Dunas importado en DIgSILENT con su «Caso base» VERIFICADO y flujo convergido: 699 tramos, 364 cargas, 274 SED, 95 maniobras, 4 bancos, GPS 100 % y diagrama igual al mapa. T6 cerrada el mismo día: suite con las siete variables, 2450 pasan, ninguna omitida; sistema Ica desde la copia VERIFICADO y calibrado |
  | 022 conversión y calibración por sistema eléctrico | cumplida el 2026-10-18 (63 RF y RF-58b; T1 a T12, T11b a T11e hechas): estructura zonal → sistema → SET del perfil o de un Excel (`config/perfiles/electro_dunas.estructura.json`), DGS unido por sistema con una red por zonal, `ElmSubstat` de SET con sus barras de 10 y 22,9 kV, red externa por barra, cabeceras como interruptor en su SET, enlaces y anillos abiertos con el oráculo por isla, `ElmZone` por sistema; opción propia «Convertir por sistema eléctrico», aparte de unir. Calibración por sistema: todos los alimentadores del proyecto a la vez, máxima de barra de SET (filas «Barra» del libro de medidores) con sus alimentadores en el instante coincidente; los sin medidor, dichos y con la demanda del archivo. Probada en DIgSILENT: la entrega entera (93 alimentadores) y los sistemas Nasca (NA203 −0,57 %, NA205 por zonas), Pisco (16 de 20, 6 barras con medidor) e Ica (IN111 y TA225 de 30), y Chincha (23 de 26, TM106 reconstruido con su medida y TM104 con la rama junto a su cabecera; CA103 y TM101 miden 0 y PN208 sin medidor), cada uno en su proyecto, calibrados y válidos sin remedios. Ica también desde la copia VNR-GIS, VERIFICADO y válido |
  | 024 PINN como oráculo y gemelo digital | aprobada el 2026-10-21 (63 RF): gemelo local autodidacta (aprendizaje activo en copias, reentrenamiento y promoción automáticos con puertas, adaptación a la deriva; diagnostica la red, planifica por etapas y propone e implementa solo sus obras en «Con proyecto», en una variación propia que el operador puede deshacer) que aprende de episodios fuente–DIgSILENT, evaluados por caso («Caso base» y «Sin proyecto» como diagnóstico de la red real; «Con proyecto» con la norma NTCSE/NTCSER del sistema, pérdidas y confiabilidad), alternativas del PIDE (Anexo N.º 6 del TdR del VAD) optimizadas sin sobredimensionar, y un modelo por tarea (PINN/GNN, RNN, ordenamiento, confiabilidad). Primera entrega (búfer de episodios, T1 a T9) implementada el 2026-10-22: contrato, búfer inmutable con índice SQLite, evaluación por caso, captura tras cada acción de la web y lectura nativa; caso dorado IN111–TA225 probado en DIgSILENT (11 de 11); T10 a T14 (escenarios, PINN, RNN, PIDE) sin empezar; metodología del PIDE de la norma prepublicada con la RM 428-2017-MEM/DM (arts. 7 a 17: mercado, diagnóstico, alternativas, evaluación técnica, económica del art. 14 con costo anual = anualidad del CI + COyM + CP, priorización del art. 15, formatos 01 a 15); obras, nombres y costos del libro CAPEX de la empresa; faltan la tolerancia NTCSER, la tasa y los pesos del art. 15.3 en el perfil |

  Las convenciones de cada empresa (CRS de origen, patrón de SED de medición, escala,
  carpeta de DIgSILENT) van en `config/perfil_empresa.json`, local y fuera de git, que
  puede heredar de un perfil de `config/perfiles/` (`{"perfil": "electro_dunas"}`); los
  alias de tipos de línea en `config/line_type_aliases.json`, también local. Sin perfil
  no se supone nada: el CRS se pide y ninguna SED se excluye por su nombre.
- `CODIGO_FUENTE.md` lista cada fichero de `src/`, `tools/` y `frontend/src/` con su spec.
  **Un fichero nuevo entra en el índice en el mismo cambio**: `tests/test_inventario.py`
  (spec 009) falla si falta, si una herramienta no responde a `--help`, si una función de
  `src/` no la usa nada o si una spec con sus tareas hechas tiene un RF sin prueba.
- `docs/superpowers/specs/` y `plans/`, y `docs/DIAGNOSTICO_*.md`, son históricos: no tienen
  requisitos numerados ni casillas al día.

## Pruebas

```bash
.venv/Scripts/python.exe -m pytest -q                      # sintéticas: omiten las de datos reales
IGEA_RED="referencia/RED_030826(1).txt" IGEA_LOADS="referencia/CARGA_030826(1).txt" \
IGEA_EQUIPMENT="referencia/BD_Equipo_V261124 (1)(1).txt" .venv/Scripts/python.exe -m pytest -q
```

Sin las tres variables `IGEA_*`, la mayoría de las pruebas de integración se omiten en
silencio y la suite «pasa» sin haber probado nada real. `IGEA_TXT_DIR` no basta. La suite se da
por buena solo sin ninguna omitida: con las siete variables (las tres de los TXT, las dos
de Access de abajo, `IGEA_DEMANDA_DIR="referencia"` e
`IGEA_VNR_BAK="referencia/Electro Dunas VNRGIS/DAT_VNR/ELDU_VNR_24_APR.bak"`, con SQL Server
Express en marcha, spec 023) y `-rs` pasan todas.

Para la vía Access (`tests/test_access_input.py`) hacen falta dos bases, porque la red
más reciente no trae catálogo de equipos:
`IGEA_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/260924.mdb"` e
`IGEA_EQUIPMENT_MDB="D:/BaseDatosElectroDunas/260919BaseDatos/202603/BASE JUL25 1.mdb"`.

Las fuentes son independientes: un TXT, una `.mdb` o un paquete VNR-GIS se convierten
y se prueban cada uno por su cuenta, sean de la empresa y la fecha que sean. No hay
pruebas que comparen una fuente con otra (se retiraron el 2026-10-14). Con las cinco
variables a la vez la suite pasa entera; solo dos pruebas de la demanda medida piden
además `IGEA_DEMANDA_DIR`.

## Probar en DIgSILENT

- Siempre por la web, como el operador: un sistema eléctrico entero con
  `.venv/Scripts/python.exe tools/sistema_web.py --espacio <id> --zonal Pisco --demanda-dir referencia --periodo 2026-07`
  (convierte, importa y calibra; retoma lo hecho). Nada de guiones del scratchpad que
  repitan la API.
- Tras cambiar `src/igea_dgs/web/` o `src/igea_dgs/*.py` que use la web, reiniciarla: parar
  el proceso del puerto 8765 y abrir el acceso directo «Conversor IGEA-DGS» del escritorio.
  Los guiones de `tools/` no: el servidor de DIgSILENT los carga de nuevo en cada orden.
- Parar un cliente no para el trabajo de la web: cancelarlo con `POST /api/jobs/<id>/cancel`.
- Una sonda suelta conecta con `pf_arnes.conectar('nombre')`, sin `PYTHONPATH` (019:RF-16);
  si el servidor de la web está ocioso, le pide que se cierre (019:RF-14). Su salida va
  línea a línea (019:RF-15). Solo sobre proyectos importados, nunca con datos inventados.
- En el Bash de esta máquina, un heredoc reduce cada barra invertida doble a una sola: rutas con `/`, `re.escape`
  para las rutas en expresiones, y los ficheros largos con la herramienta de escribir.
- Un flujo que no converge dice lo que informa DIgSILENT en el `historial` del informe:
  leerlo antes de tocar nada (Chincha: TM106 con su factor de escala en 13,7).

## Reglas que más se rompen

- Universal: TXT, MDB y VNR-GIS de cualquier distribuidora. Electro Dunas es un caso de prueba; sus convenciones (CRS `EPSG:32718`, SED `M…`, escala NA205) van en un perfil de empresa, nunca como valor por defecto (constitución P13).
- El número de alimentadores es variable (10, 50, 200…): nada de recorrer una tabla entera por alimentador, y nada de tamaños fijos en las pruebas. Ver la sección «Escala» del skill.
- Dos disposiciones de export (reducida y completa): todo cambio en el lector se prueba con las dos.
- Determinismo: el DGS es idéntico byte a byte con `workers=1` y con `workers>1`.
- Idioma: código, comentarios, mensajes y commits en español, con el estilo de los existentes. Los comentarios explican **por qué**, con el caso real que lo motivó.
- Los TXT de `referencia/` y `D:\BaseDatosElectroDunas` son datos de la distribuidora: nunca se publican ni se suben. Tampoco se envían a un modelo de terceros: `.claude/settings.json` niega leerlos con la herramienta Read. Las pruebas los siguen leyendo por las variables `IGEA_*`.
