# Plan — Spec 107

Lee: `docs/constitution.md`, `specs/107-plan-de-inversiones-en-transmision/spec.md`, la spec 072 (PIDE, de la que el PIT
se separa) y la 042 (SET nueva y módulos PIT del libro CAPEX). Revisión de referencia: `51895566`. Decisiones de
partida: `D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 3. Fuentes de G0, que aquí no se rehacen:
`D/D_FILAS_BP.md` (BP-17), `D/D_REFERENCIAS_NORMATIVAS.md` y `B/ESTUDIOS_CAPACIDADES_AUDITADAS.md`.

## Contexto técnico

Lo que ya existe y se reutiliza. Todo se comprobó leyendo el código en `51895566`:

| Módulo | Qué aporta al PIT | Cómo se usa |
| --- | --- | --- |
| `src/convertersmartgrid/oraculo.py` | pandapower ya está en el núcleo (`requirements.txt`: `pandapower>=3.0`). `_ejecutar` (NR, `numba=False`), `_tensiones`, `_carga_lineas` y `_carga_trafos` (l. 466-511) | Se importan esos auxiliares y no se copian. `red_pandapower` **no** se reutiliza tal cual: construye un `FeederModel` de MT (barra por nodo, SED → 0,22 kV) y no conoce las SET, los transformadores de potencia de dos y tres devanados ni las líneas de 60 kV o más |
| `src/convertersmartgrid/estudios_pf.py` | Límites de tensión y cargabilidad del perfil, violaciones y diferencias entre casos (RF-33 a RF-35 de la 011), y ficheros de resultados deterministas | Mismo contrato de «medida» por elemento, para que el diagnóstico del PIT y el de la 011 se lean igual |
| `src/convertersmartgrid/estudios_red_pf.py` | `confiabilidad`, `aportes`, `comparar` y `cambios_de_estado`, que interpretan lo que devuelve DIgSILENT (`ComRel3`, `ComOpri`) | Confiabilidad de cada alternativa cuando el motor es DIgSILENT, y la comprobación de que el estudio no dejó nada cambiado |
| `src/convertersmartgrid/set_nueva.py` | `leer_modulos_pit` (l. 127-170) lee los módulos de SET y transformador **del libro CAPEX de la empresa**; `elegir_modulo` da el menor que cubre | Catálogo de candidatos de transformación de las alternativas. Su costo es de la empresa y no es oficial: el expediente lo rotula así (RF-7) |
| `src/convertersmartgrid/costos_fuentes.py` | `leer_modulos_transmision` (módulos estándar, ámbito `transmision`), `exigir_ambito` y `valorar_obra` (l. 319-359): metrado × costo, lo que no cruza queda nombrado y fuera del total, y los totales por moneda | Inversión de cada alternativa, con la fuente y la huella de la base. No se modifica |
| `src/convertersmartgrid/proyeccion_anual.py` | `proyectar` (P y Q por carga y año, con su banda), `formato_01_de_cabecera` (MW coincidentes por sistema) y `proyeccion_aceptada` | Demanda del área por año: se agregan las cargas proyectadas por barra de SET con la correspondencia área → SET → alimentadores del perfil. No se modifica |
| `src/convertersmartgrid/pide_economia.py` | `frc` y `van`, aritmética pura | Se **importan** y no se modifican (la 107 no toca `pide_economia.py`). `costo_anual` no se usa: suma como 0 el COyM o el CP que faltan (BP-28) |
| `src/convertersmartgrid/libro_informe.py` | `ConfigLibro.de_perfil`, `plan_del_libro`, `comprobar_libro` y `rellenar_con_excel`: el libro modelo que declara el perfil, celda por celda | Los cuadros del expediente en el libro modelo de la empresa, con el mismo mecanismo y sin otro escritor de Excel |
| `src/convertersmartgrid/estudio_planeamiento.py` y `pide_dataset.py` | El estado jurídico ya existe para el PIDE (`'vigente', 'proyecto', 'pendiente', 'derogada', 'evidencia_tecnica'`, `pide_dataset.py:65-66`) | Se lee solo para fijar la correspondencia con los estados del registro común. No se migran: eso es de la 072 |
| `tools/transformador_set_pf.py` | Ya lee, en el proyecto de transmisión de DIgSILENT, las cargas por barra de SET y el transformador del que cuelgan (017 T10) | Patrón y funciones del guion nuevo `tools/pit_pf.py` |
| `tools/estudios_pf.py` | `ComLdf` y `ComSimoutage` con `ComOutage` (l. 509-598), en el carril `powerfactory` | Mismas órdenes y el mismo arnés para el N-1 del área |

Lo que no existe (grep de G0 sobre `src/` y `tools/`, sin resultados): nada de la RCD 217-2013, del PIT 2025-2029
(RCD 112-2024 y 149-2024) ni de la 199-2026, y ningún modelo de la red de transmisión del área en el motor abierto.

Lo que el plan **no** toca: `src/convertersmartgrid/web/services.py`, `pide_economia.py` y el adaptador VNR
(`src/convertersmartgrid/adaptadores/entrada/vnr/`), que corrige el integrador f9. Lo que haya que cablear en
`web/app.py` se pacta con f9 (G1, punto 6).

Carriles de trabajo: `engine` para pandapower y `powerfactory` para DIgSILENT, en serie (P7).

## Diseño por partes

Paquete nuevo `src/convertersmartgrid/pit/`, separado del PIDE (RF-1). Un módulo común nuevo, compartido con la 108:
`src/convertersmartgrid/registro_normativo.py`.

| Parte | Ficheros (propuestos) | Cubre |
| --- | --- | --- |
| **A. Registro normativo común (107 y 108).** Contrato de una norma: acto, título, URL, fecha de publicación, fecha de consulta, huella SHA-256 del texto leído, estado jurídico (`vigente_comprobada`, `modificada`, `prepublicada`, `no_verificada`, `derogada`), vigencia desde y hasta, `modifica` y `modificada_por`, y sus **reglas**: clave, valor, unidad, artículo o anexo, página y cita literal. `regla(clave, fecha)` devuelve la regla con su estado y dice si es obligatoria (solo `vigente_comprobada`, o `modificada` en su versión vigente). `instantanea()` da la huella del registro entero, que el expediente fija al empezar | `src/convertersmartgrid/registro_normativo.py`; `src/convertersmartgrid/schemas/registro_normativo_v1.schema.json`; datos en `config/normativa/*.json` (uno por norma) | RF-7, RF-8, RF-11 |
| **B. Ámbito del área.** Del perfil, `pit.areas`: número o código del área, titulares, SET, la correspondencia SET → alimentadores, la tensión mínima del ámbito y la asignación de los elementos compartidos. Reúne del modelo de red del área las SET, los transformadores, las celdas, las líneas y la compensación de esa área y de ninguna otra | `src/convertersmartgrid/pit/ambito.py` | RF-2, RF-11 |
| **C. Red del área (contrato neutro).** `RedArea`: barras, transformadores de 2 y 3 devanados, líneas, celdas, compensación, red externa y carga por barra de SET, cada elemento con su titular, su área y su fuente. La llenan dos adaptadores: el proyecto de transmisión de DIgSILENT (`tools/pit_pf.py --exportar-red`, cuando hay licencia) y un libro de la red declarado en el perfil (hoja y columnas, igual que `modulos_pit`). Un elemento sin parámetros queda en `faltantes` con el dato que le falta | `src/convertersmartgrid/pit/red_area.py`; `tools/pit_pf.py` | RF-2, RF-4 |
| **D. Motores y matriz de capacidades.** `MOTORES = {'abierto', 'digsilent'}` y la matriz estudio × motor: flujo, tensión, cargabilidad y N-1 en los dos; cortocircuito y confiabilidad (`ComRel3`) solo en DIgSILENT. Con el motor abierto, la confiabilidad se reduce a la potencia que queda sin servir en cada contingencia, y el resultado lo dice. Por defecto el abierto; DIgSILENT si hay licencia y el operador lo pide. Cada resultado nombra el motor | `src/convertersmartgrid/pit/motores.py`; `pit/red_pandapower.py` (de `RedArea` a pandapower: `create_transformer_from_parameters`, `create_transformer3w_from_parameters`, `create_line_from_parameters`, `create_shunt`, y los auxiliares de `oraculo.py`) | RF-3, RF-5 |
| **E. Diagnóstico por año.** Para cada año del horizonte (del registro y del perfil, nunca escrito): la demanda del área de `proyeccion_anual` en sus barras de SET, el flujo, la tensión y la cargabilidad de cada elemento, y el N-1 (cada línea y cada transformador fuera de servicio, de uno en uno) contra los límites que declare el registro o el perfil. Un año sin demanda proyectada no se extrapola: queda nombrado. Es un trabajo en cola, cancelable entre años | `src/convertersmartgrid/pit/diagnostico.py` | RF-3, RF-4 |
| **F. Alternativas.** Cada alternativa es un conjunto de cambios sobre `RedArea` (transformador del catálogo de `set_nueva.leer_modulos_pit` o de los módulos estándar, línea, celda o compensación), mutuamente excluyente con las demás. Se evalúa con la misma demanda y el mismo motor: inversión por `costos_fuentes.valorar_obra` (ámbito `transmision`), COyM según la regla que declare el registro, pérdidas del flujo y, si el registro da su precio y su factor, su valor anual, y confiabilidad según la matriz D. El valor actual usa `pide_economia.frc` y `van`, con la tasa y la vida útil del registro. Lo que falte deja la alternativa incompleta y fuera de la comparación, nunca con un 0 | `src/convertersmartgrid/pit/alternativas.py` | RF-5, RF-8 |
| **G. Programa.** De la alternativa elegida por el operador: cada elemento con su año de puesta en servicio, su titular y su área, con las bajas y los reemplazos que implica. Con varios titulares, un programa por titular y el del área | `src/convertersmartgrid/pit/programa.py` | RF-6 |
| **H. Expediente y cuadros.** Carpeta propia del PIT, aparte de la del PIDE. Fija la instantánea del registro al abrirse; si el registro cambia después (una modificatoria nueva), avisa y lista las celdas afectadas, sin recalcular solo. Cada celda lleva su traza: fuente (con su huella), cálculo (función y parámetros), motor y regla del registro con su estado. Los cuadros salen de la definición transcrita del registro (parte A), no del código, y se escriben en el libro modelo con `libro_informe`. Mismo caso, misma norma y mismos costos: mismo expediente, byte a byte | `src/convertersmartgrid/pit/expediente.py`; `pit/cuadros.py` | RF-1, RF-7, RF-8, RF-9 |
| **I. Observaciones del regulador.** Cada observación con su número, su fecha, su texto, la respuesta y el elemento, el caso o la celda a los que afecta, enlazada con la traza de la parte H | `src/convertersmartgrid/pit/observaciones.py` | RF-10 |
| **J. Web.** Rutas propias `/api/pit/…` en un `APIRouter` aparte; el diagnóstico y las alternativas como trabajos en cola (`engine` o `powerfactory`) con progreso por WebSocket. Solo el registro del router en `web/app.py`, pactado con f9. Un panel en la web, con la microcopia mínima | `src/convertersmartgrid/web/rutas_pit.py`; `frontend/src/features/pit/` | RF-1 a RF-10 (borde) |

Coordinación de la parte A con la 108: la interfaz de arriba es la propuesta común. Quien la implemente primero crea
el módulo; la otra spec la usa sin copiarla (P5). Por el orden de G1 (108 antes que 107), lo previsible es que la cree
la 108. En ese caso, la tarea T1 de la 107 solo añade lo que le falte, con su prueba. El borrador de plan de la 108
(2026-11-14) propone `vad/normativa.py` con el vocabulario de `pide_dataset`. Antes de implementar, el integrador fija
un solo módulo y un solo vocabulario. La 107 necesita, al menos, distinguir `vigente_comprobada`, `modificada`,
`prepublicada` y `no_verificada` (RF-7), y que el módulo no quede dentro de `vad/` ni de `pit/`.

## Ampliación del 2026-11-14: entregables de Osinergmin (aclaraciones de RF-9 y RF-10; RF-13 a RF-18)

Del veredicto de 7e sobre `OSINERGMIN_ENTREGABLES/INVENTARIO.md`. Cada parte amplía un módulo que ya existe o añade
uno al paquete `pit/`; ninguna crea una spec nueva.

| Parte | Ficheros (propuestos) | Cubre |
| --- | --- | --- |
| **K. Formatos de la norma registrada.** La lista de formatos y sus columnas salen de la regla de formatos de la norma vigente del registro (`pit.formatos_*`, con `transcrito: true` y las columnas de cada formato); el escritor no conoce ningún número de formato ni de columnas. Un formato listado y no transcrito va a `cuadros_no_transcritos` del resumen. Una celda derivada de otro formato se escribe como fórmula que apunta a la celda de origen, con el mecanismo `formulas` de `libro_informe`. | `pit/cuadros.py` (ampliado), `config/normativa/` | Aclaración de RF-9 |
| **L. Absolución.** `observaciones.escribir_absolucion`: cada observación con su objeto, su respuesta y la traza de lo que cambió (celdas o elementos antes y después, por su huella). | `pit/observaciones.py` (ampliado) | Aclaración de RF-10 |
| **M. Resumen ejecutivo.** Demanda del área por año, alternativa elegida y programa, leídos del expediente emitido; ninguna cifra calculada aparte. | `pit/informe.py` | RF-13 |
| **N. Memoria y relación de sustento.** `expediente.emitir` añade a cada sección su memoria (criterios, metodología, entradas, resultados) y la relación de los documentos de sustento con descripción, uso y huella. | `pit/expediente.py` (ampliado) | RF-14 |
| **O. Unifilar DXF.** Una hoja (bloque de presentación) por alternativa y año, con el marco, las barras, los transformadores y el flujo de cada línea del diagnóstico. El DXF se escribe con `ezdxf`; el DWG, solo si la configuración o el PATH dan el ODA File Converter, nunca con una ruta fija; si falta, el DXF se entrega con un aviso que dice cómo obtener el DWG. | `pit/unifilar.py` | RF-15 |
| **P. Transformadores de reserva.** Con la regla del procedimiento vigente registrado (la RCD 094-2022 cuando esté transcrita); sin regla, un aviso que la nombra. | `pit/reserva.py` | RF-16 |
| **Q. Modificación del plan vigente.** Modo `modificacion` del expediente: compara el programa vigente con el nuevo y lista lo que se elimina, cambia o agrega, con su razón; demanda y alternativas con los mismos criterios. | `pit/programa.py` y `pit/expediente.py` (ampliados) | RF-17 |
| **R. Formato F-208.** La estadística de fallas y los índices de desempeño de las fuentes importadas (confiabilidad, spec 012); el hueco nombrado cuando faltan. | `pit/cuadros.py` (ampliado) | RF-18 |

## Decisiones

- **Un paquete `pit/` aparte del PIDE.** Descartado: ampliar `pide.py` y `formatos_pide.py` (lo que proponía la fila
  BP-17 de G0), porque el PIT tiene otra norma, otro horizonte y otros formatos (RF-1), y mezclarlo con el PIDE haría
  pasar un costeo de módulos por cumplimiento del PIT, que es el riesgo que señaló G0.
- **Motor abierto (pandapower) por defecto y DIgSILENT si hay licencia, con la misma matriz de capacidades** (G1,
  punto 3). Descartado: solo DIgSILENT, porque el PIT no podría estudiarse sin licencia; y solo pandapower, porque el
  cortocircuito y `ComRel3` no tienen equivalente abierto en el repositorio (G0-B, familias 8 y 11). La matriz hace que
  falte algo, no que se invente.
- **Contrato neutro `RedArea` con dos adaptadores.** Descartado: partir de la red unida de MT (spec 022) o de
  `oraculo.red_pandapower`, porque modelan una red externa por barra de SET y no traen las líneas de 60 kV ni los
  transformadores de potencia con sus parámetros; partir solo del proyecto de DIgSILENT dejaría al motor abierto sin red.
- **Registro normativo común con la 108, en datos (`config/normativa/`), no en código.** Descartado: un registro por
  spec, que duplicaría la lógica (P5) y dejaría estados distintos para la misma norma; y escribir artículos o fórmulas en
  el código, que fijaría una norma y un periodo (P13, RF-11).
- **Estados del registro: `vigente_comprobada`, `modificada`, `prepublicada`, `no_verificada` y `derogada`.**
  Descartado: reutilizar los de `pide_dataset` (`vigente`, `proyecto`, `pendiente`…), porque no distinguen «vigente y
  comprobada» de «vigente según un tercero», que es la distinción que hizo G0. Se documenta la correspondencia; la
  migración del PIDE queda para la 072.
- **Una regla que no esté `vigente_comprobada` se usa como referencia y el expediente lo dice** (RF-8). Descartado:
  bloquear el estudio, porque la tasa del art. 79 de la LCE, por ejemplo, solo está comprobada de forma indirecta (G0,
  fila 15) y el estudio quedaría parado sin que nadie pueda resolverlo desde la web.
- **La instantánea del registro se fija al abrir el expediente.** Descartado: leer siempre el registro vigente, porque
  una modificatoria publicada a mitad del expediente cambiaría cifras sin que nadie lo decidiera (caso límite de la
  spec).
- **La RCD 199-2026 entra como `no_verificada` y sin reglas** hasta que se lea (G0: el enlace daba 404). Descartado:
  suponer su contenido por su título.
- **Los cuadros salen de su transcripción en el registro.** Descartado: escribir ahora sus columnas, porque los anexos
  A y B del Informe Técnico 565-2024-GRT y los formatos de la 217-2013 no se han leído. Hasta transcribirlos, el
  expediente da sus tablas de trabajo y dice que el cuadro oficial no está transcrito.
- **Reutilizar `frc` y `van` y no `costo_anual`.** Descartado: copiar las fórmulas, por P5; y usar `costo_anual`, que
  suma como 0 lo que falta (BP-28).
- **Elemento compartido entre dos áreas: su asignación la declara el perfil.** Sin declaración, el elemento aparece en
  los dos ámbitos marcado como compartido y sin asignar, y el diagnóstico de ese elemento no se da por completo (RF-4).
  Descartado: repartirlo a partes iguales, que sería un dato inventado.
- **Unifilar en DXF, y DWG solo como añadido** (RF-15, decisión de e6 por orden del usuario). Descartado: entregar
  solo DWG, porque es un formato cerrado que exige un convertidor externo y dejaría la entrega a merced de él; y dibujar
  el unifilar como imagen, porque el entregable pide ficheros que se editen en CAD. No hay escritor de DXF en el
  conversor (los diagramas de `mapa_informe` son imágenes), así que no se duplica ninguno.

## Comprobación contra la constitución

- **P5.** Una vía: costos por `valorar_obra`, demanda por `proyeccion_anual`, aritmética financiera por `frc` y `van`,
  libro por `libro_informe`, auxiliares de pandapower de `oraculo`, y el registro normativo como único sitio de las
  normas para la 107 y la 108.
- **P7.** El diagnóstico de varios años y la evaluación de alternativas son trabajos en cola, cancelables entre años y
  entre alternativas; DIgSILENT, en su carril en serie.
- **P8.** pandapower ya es dependencia del núcleo; no hace falta ninguna nueva para RF-1 a RF-14 y RF-16 a RF-18. RF-15 necesita
  `ezdxf` (escribir y leer DXF), que no está en el `.venv`: es dependencia OBLIGATORIA, con versión fijada (veredicto del
  auditor ca, 2026-11-14 20:55), porque el DXF es la entrega garantizada; solo el DWG, con el ODA File Converter, es
  opcional. Su tarea queda bloqueada hasta que el integrador la añada.
- **P9.** El expediente y los datos del área se quedan en local o en la nube propia del usuario. Nada se envía al
  regulador desde el sistema (fuera de alcance).
- **P10.** Código, mensajes y expediente en español.
- **P12.** Cada RF tiene su tarea y su prueba que lo cita (`107:RF-n`).
- **P13 y RF-11.** Ningún número de área, titular, tensión, límite, tasa, vida útil ni año en el código: van en el
  perfil (`pit.areas`, libro de la red, libro modelo) o en el registro. La primera empresa de prueba es el primer caso real, con su área
  y su titular en su perfil (G1, punto 3).
- **Determinismo (requisito no funcional).** Orden estable de elementos, años y alternativas; JSON con claves ordenadas;
  sin fecha de reloj dentro del expediente salvo la que entra como dato.

## Estrategia de pruebas

- **Dos perfiles sintéticos** en `tests/datos_pit.py`, sorteados con semilla:
  - *Perfil A*: un área con un titular, SET de 60/22,9 kV con transformadores de dos devanados, líneas radiales, un
    horizonte corto y todos los datos.
  - *Perfil B*: un área con varios titulares, transformadores de tres devanados (por ejemplo 138/60/10 kV), un anillo
    (el N-1 no deja carga sin servir en todos los casos), un elemento compartido con otra área, una línea sin
    parámetros y un año sin demanda proyectada.
  Los dos convierten y diagnostican; los números de área, las tensiones y los años de cada uno salen del sorteo y no se
  fijan en las pruebas.
- **Dos registros sintéticos** con normas en cada estado, y una modificatoria con fecha posterior a la apertura de un
  expediente. El registro real de `config/normativa/` se valida contra el esquema.
- **Motor abierto** con pandapower de verdad (sin GPU ni licencia). **DIgSILENT** con el doble `tests/fake_pf.py` para el
  guion `tools/pit_pf.py`. La corrida real va en las tareas `[DIgSILENT]`, sobre una copia del proyecto de transmisión,
  nunca sobre el del operador.
- **Coherencia de motores:** la misma `RedArea` en pandapower y en DIgSILENT, con la tolerancia por defecto de la 112
  (0,005 p.u. en tensión y 1 % en corriente; G1, punto 5).
- **Determinismo:** el mismo caso dos veces da el mismo expediente byte a byte.
- **Universalidad:** `tests/test_entrega_universal.py::test_nucleo_y_web_sin_terminos_en_el_codigo` cubre también
  `pit/` y `registro_normativo.py`.
- No toca el lector de TXT, MDB ni VNR: no hacen falta las dos disposiciones de export ni las variables `CSG_*`.
- Cada prueba cita su requisito: `"""107:RF-n — …"""`.

## Riesgos

- **Formatos oficiales sin leer.** Los cuadros oficiales del PIT dependen de transcribir la 217-2013 y el IT
  565-2024-GRT. Sin ellos, RF-9 se cumple solo con tablas de trabajo. Lo vigila T2.
- **RCD 199-2026 no verificada.** Si existe y cambia el PIT del área, el primer caso real puede cambiar. Lo vigila T3.
- **Modelos distintos en los dos motores.** La conversión de `RedArea` a pandapower (tomas, grupos de conexión, tres
  devanados) puede alejarse de DIgSILENT. Se detecta con la comparación de T14.
- **Choque con f9.** Cualquier cambio en `web/app.py` fuera del registro del router entraría en su superficie. Se evita
  con el router aparte y el pacto previo (T13).
- **Choque con la 108 en el registro común.** Dos escritores del mismo fichero. Se evita con la interfaz de la parte A y
  un único integrador del módulo.
- **Que se lea como aprobado.** El expediente nunca dice «aprobado por Osinergmin» (fuera de alcance); una prueba lo
  comprueba en T10.
