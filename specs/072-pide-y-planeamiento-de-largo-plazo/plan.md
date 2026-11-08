# Plan — Spec 072

Lee: `docs/constitution.md` y `specs/072-pide-y-planeamiento-de-largo-plazo/spec.md`.

Se reutilizan `pide.py`, `pide_economia.py`, `tools/pide_pf.py`, `crecimiento.py`, 042/052, 046, 048, `informe_docx.py`,
`asistente/ejemplos_pide.py`, `pide_dataset.py`, `vnr_etl` y el perfil de empresa.

| Parte nueva | Cubre | Encaje |
| --- | --- | --- |
| Estudio de planeamiento: año de presentación, año 00, años | RF-1 a RF-4 | Contenedor sobre 030 |
| Contrato de fuentes de costos y adaptadores | RF-5 a RF-9 | Dentro de `pide_economia` |
| Metrados desde la red | RF-7, RF-15 | Alimenta F02, F08 y F13 |
| Proyección de mercado | RF-10, RF-11 | 031/046, puerta de entrada al escalado |
| Obras acumuladas por año | RF-12 | `tools/pide_pf.py`, en «Con proyecto» |
| Evaluación con y sin proyecto, F01 a F15 | RF-13, RF-14 | Amplía `pide_economia` |
| Generadores 4.1 y 4.2 | RF-13, RF-14, RF-16 | `informe_docx.py`, perfil de empresa |
| Herramientas y entrenamiento del asistente | RF-18, RF-19 | Coordinado con la spec 070 |
| COyM del perfil en la propuesta | RF-22 | `propuesta_pide(coym_pct_anual=)`, `formatos_pide._por_grupo`; lo pasa `web/services.py` |

Fuentes públicas ubicadas el 2026-11-02, en Procesos Regulatorios de Osinergmin: SICODI y VNR al 31-12-2025 (Res. 184-2026-OS/CD);
VNR de Electro Oriente, fijación 2022 (Res. 186-2023-OS/CD). Falta el fichero de módulos estándar (Res. 152-2026-OS/CD; su base la sustituyó la Res. 181-2026-OS/CD, 2026-11-06): el
adaptador `costos_fuentes.leer_modulos_transmision` pide sus columnas declaradas y `valorar_obra` separa los ámbitos (T3); el
fichero real es T13. La base de la 152 trae una hoja por tipo de módulo y no dice la unidad: se leen las hojas declaradas, con la
unidad de cada una declarada (T13).

Asistente (T9): la tarea `pide` comprueba en `web/asistente_operacion._pide` el año de presentación y los libros que nombra la
orden antes de confirmar; el corpus de redacción (`asistente/corpus_redaccion.py`) solo admite revisiones humanas con uso
`redaccion` o `formato`, y exporta sin cifras.

Coordinación: `pide_economia` y `escalera_optima` también los toca la 073; se avisa la zona antes de escribir.

## P17: continuación anual autorizada (2026-11-08)

RF-23 a RF-28 se implementan en `pide.py` (contrato puro de proyección anual) y
el modo `anual` del guion existente `tools/pide_pf.py`. El modo de diagnóstico
por tasa existente se conserva y nunca sirve de alternativa silenciosa al anual.
El perfil materializado de demanda contiene P/Q por carga, alimentador, clase,
objetivo y año relativo; se verifica el archivo y la evaluación de aceptación
por sus huellas y por cobertura anual. No se entrena otro modelo ni se convierte
una predicción de 28 días de 089 en veinte años. La materialización científica
del horizonte anual sigue dependiendo de P16/031.

Los casos y escenarios se guardan bajo un identificador de estudio nuevo. Se
reutiliza `casos_del_anio` para copiar el estado previo con sus obras y se
reutilizan los escritores de carga del proyecto, con unidades y relectura. Las
obras son variaciones físicas identificadas por ruta, ya definidas por la vía
de obras existente; no se construye una red supuesta si falta su diseño.
La demanda por fases exige cobertura física compatible: un modo no representable
por el perfil materializado se bloquea, sin modificar la topología de origen.

Pruebas primero con `fake_pf`: continuación mayor que cuatro, acumulación sobre
copias anteriores, primera recaída, proyección P/Q distinta y relectura,
huellas/aceptación/cobertura ausentes, NaN, identidad ambigua, obra ausente o
insuficiente, error de guardado, interrupción y restitución de origen. Ninguna
de estas pruebas abre PowerFactory ni acredita la aceptación nativa de T14.

T13 se comprueba contra la carpeta exacta de la Res. 181-2026-OS/CD: se custodian
capturas y respuestas primarias actuales. La base antigua de la 152 se conserva
como antecedente y no se renombra como la 181. T9b y T11 mantienen su revisión
humana pendiente; P17 prepara un paquete de revisión con huecos y procedencia.

## Conexión anual web P17 (2026-11-08)

La ruta PIDE conserva el diagnóstico histórico por defecto y añade `modo=anual`
con DTO explícito. La carga de tres JSON (perfil anual, evaluación y evidencia de
corto plazo) conserva sus bytes y huellas en custodia del espacio; un perfil
derivado únicamente sustituye la referencia de evaluación por la custodiada y
registra esa transformación. Ninguna ruta anidada del cliente se abre.
Antes de encolar se verifican identidad completa, huellas, aceptación documental,
cobertura anual P/Q y obras físicas explícitas. El trabajo vuelve a verificarlas
antes del mismo `tools/pide_pf.py`, en el carril PowerFactory. Cancelar transmite
el protocolo cooperativo antes de conectar y siempre pasa por restitución.
La interfaz muestra fuentes, bloqueos, años, obras acumuladas y restitución;
no concede aceptación científica mediante un control. Las pruebas son API real
sin motor y render React, contrato generado, typecheck y build. La verificación
visual y la corrida nativa permanecen pendientes.

## Corrección de integridad de P17 tras revisión independiente (2026-11-08)

Sin ampliar la API ni cambiar RF-23 a RF-28: `tools/pide_pf.py` comprueba el
destino nuevo de AddCopy (clase, carpeta e identidad distinta del origen), los
retornos de activación/desactivación y el caso/escenario activos antes de escribir
o guardar. El escenario esperado acompaña internamente a cada copia; una
activación aparentemente correcta no permite escribir contra el original. El
finally del consumidor sigue restituyendo ambos contextos aunque falle crear.

El inventario de medición se relee con `Alimentadores`, incluyendo el terminal
conectado de cada carga. Se exige cobertura de las mismas cargas del alcance,
P/Q/fases/modos y escala del perfil; una maniobra dentro del alcance puede cambiar
su ruta si mantiene el servicio. Tensión y cargabilidad requieren unidad y medida
finita de cada elemento esperado; una clase vacía solo es válida si el inventario
no contiene esa clase. La lectura se limita al alcance elegido y admite Tr3 por su
atributo nativo, sin omitirlos por el lector histórico de Tr2. El dictamen de BT y
consumo reutiliza `comprobacion_flujo`; se añaden las guardias de conexión, consumo
P/Q disponible y tensión de cada fase con demanda explícita. Una falta de servicio
real es incumplimiento; un dato desconocido bloquea, sin convertirlo en cero válido.

La custodia anual usa `runtime_paths.staging_publicacion`: prepara los tres JSON,
perfil derivado y procedencia en privado, con referencias al destino final; publica
el directorio completo por rename. Un fallo de escritura/publicación no devuelve
un token utilizable ni afecta custodias anteriores. La cancelación se consulta
también después de preparar demanda y antes de cada obra/flujo posterior.
Si falla también el recibo de cierre de staging, se retiran solo los cinco JSON
propios antes de salir del intento fallido. Si rename ya publicó el conjunto
íntegro, un fallo posterior de ese recibo se registra y se entrega el token válido,
sin anunciar que no existe una publicación que sí terminó. Una obstrucción física
que impida retirar un fichero sigue siendo error de E/S y conservación administrada,
no una garantía de borrado ante un sistema de archivos inaccesible.

Regresiones CPU en `tests/test_pide_integridad.py`: escenarios originales de 50 kW
sin escritura/Save anual ante fallo/alias/proyecto ajeno; retirada de servicio,
cambio de demanda/representación y consumo ausente; mapas parciales/unidad y fase
sin tensión; custodia IO/rename fallidos y API 422; cancelación sin flujo adicional.
Positivas: ruta alternativa que mantiene servicio y grupo vacío de transformadores
cuando no existen. El doble anual declara medidas sintéticas de línea/BT/fases que
antes omitía: estas fixtures no acreditan resultados ni persistencia de PowerFactory.
T14/T13/T11/T9b y la aceptación científica/nativa permanecen abiertas.

## Segundo contraste de integridad anual (2026-11-08)

La revisión independiente reprodujo dos dictámenes inválidos: un terminal de la
carga fuera de servicio con resultados finitos antiguos, y una fase NaN del corto
plazo sin filas de proyección aunque los agregados fuesen finitos. El primero daba
completo en el ciclo CPU; el segundo podía iniciar flujo/copias antes de bloquear,
sin demostrar que terminase completo. `_comprobar_demanda_anual` valida antes de
modificar ComLdf o iniciar flujo P/Q, escala y las seis entradas por fase, sus
unidades MW/Mvar y la finitud de la demanda efectiva. Las fases cero siguen siendo
válidas. `_servicio_anual` añade incumplimiento por terminal conectado fuera de
servicio aunque sus medidas almacenadas parezcan servir la carga.

La misma revisión encontró una cancelación conocida tras la lectura interior que
no impedía el flujo corto. Se consulta después de las lecturas y antes de esa
medición. Todas las mediciones del ciclo reciben además el callback interno
`comprobar_cancelacion`, invocado justo antes de flujo tras la validación nativa.
La cancelación no interrumpe el motor ya iniciado y conserva el finally original.
No cambian la API/JSON públicos, los umbrales, los originales ni los dobles globales.
Pruebas negativas y control con demanda pequeña en r, Q cero y s/t cero en
`tests/test_pide_integridad.py`; las maniobras legítimas y la restitución anteriores
siguen verificándose. La falta de finitud inicial no se disimula con cero ni se
convierte en una restitución válida si su readback no puede confirmarse.

La evidencia CPU de `correccion_p17_segunda_revision_20261108` registra rojo/verde,
revisión exacta y límites; no acredita PowerFactory real, aceptación eléctrica,
ciencia ni T14/T13/T11/T9b. El fundamento académico del primer contraste se mantiene:
perfil servido, cobertura y conservación son criterios distintos de convergencia.
