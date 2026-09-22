# Diseño de robustecimiento integral IGEA/CYMDIST → DGS → PowerFactory

**Fecha:** 2026-09-21  
**Estado:** aprobado conceptualmente por el usuario; pendiente de revisión del documento escrito  
**Entorno objetivo:** Windows local, uso por un solo operador, DIgSILENT PowerFactory instalado localmente

## 1. Objetivo

Convertir el proyecto actual en una herramienta local robusta y reproducible que:

1. lea los TXT `RED`, `CARGA` y `BD_Equipo`;
2. represente todos los elementos soportados que estén presentes en esos archivos;
3. preserve topología, fases, secciones, configuración y parámetros eléctricos verificables;
4. genere un DGS sin valores físicos inventados;
5. importe el DGS mediante la API de PowerFactory;
6. complete por API únicamente los equipos respaldados por datos inequívocos;
7. valide el caso original sin modificarlo para forzar convergencia;
8. produzca evidencia auditable de cada transformación.

El desarrollo reforzará el código actual por módulos. No se realizará una reescritura completa ni se eliminará el flujo DGS que ya funciona.

## 2. Principios obligatorios

### 2.1 Política estricta

- Un dato eléctrico obligatorio ausente, inválido o ambiguo detiene el alimentador afectado.
- No habrá selección aproximada de conductores por distancia de edición.
- No habrá `DEFAULT` físico para líneas, cables, transformadores, fuentes o generadores.
- Un cero solo será válido cuando el TXT o una fuente técnica verificable declare realmente cero.
- Los modos exploratorios no podrán producir artefactos etiquetados como producción.
- Cada error indicará archivo, tabla/sección, fila, campo, valor y acción requerida.

### 2.2 Procedencia

Cada parámetro del modelo tendrá una de estas procedencias:

- `observed_txt`: valor explícito del TXT;
- `observed_catalog`: valor exacto de `BD_Equipo`;
- `manufacturer_datasheet`: ficha oficial del fabricante y modelo exactos;
- `approved_mapping`: equivalencia manual aprobada y versionada;
- `derived`: cálculo determinista desde valores anteriores, con fórmula y unidades.

Los valores `missing`, `ambiguous` o `assumed` no se admitirán en producción.

### 2.3 Jerarquía de fuentes técnicas

1. TXT del lote.
2. Registro exacto en `BD_Equipo`.
3. Ficha oficial del fabricante para fabricante y modelo inequívocos.
4. Equivalencia explícita aprobada por el usuario.

Una tesis, artículo o libro puede justificar una fórmula o metodología, pero no sustituirá la ficha técnica de un equipo concreto. Cada ficha local conservará URL oficial, fecha de consulta, SHA-256, fabricante, modelo, revisión, unidades y campos extraídos.

## 3. Alcance funcional

### 3.1 Elementos obligatorios

El inventario debe descubrir y clasificar todas las secciones presentes. Los adaptadores implementarán, cuando existan en los TXT:

- nodos y terminales;
- redes y alimentadores;
- tramos aéreos;
- cables/tramos subterráneos;
- cargas;
- SED válidas;
- interruptores;
- seccionadores;
- fuentes externas;
- centrales solares/fotovoltaicas;
- generadores térmicos;
- bancos de condensadores;
- reguladores;
- transformadores reales cuando exista información técnica completa;
- otros equipos con placement explícito y catálogo suficiente.

Una sección TXT no reconocida será un error de cobertura, no un descarte silencioso.

### 3.2 Fidelidad de líneas y cables

Por cada tramo se conservarán como mínimo:

- `SectionID` original;
- `FromNodeID` y `ToNodeID`;
- medio aéreo/subterráneo;
- fases;
- sección transversal del conductor;
- material;
- cantidad de conductores por fase;
- cantidad de ternas;
- cantidad de circuitos;
- longitud y su fuente;
- R1, X1, R0, X0, B1 y B0 con unidades;
- ampacidad;
- estado operativo;
- identificador exacto de tipo/catálogo.

El número de circuitos/ternas se representará según el significado documentado de los campos fuente y los atributos PowerFactory correspondientes. No se fijará `nlnum=1` sin evidencia.

La longitud TXT será la longitud eléctrica predeterminada. La geometría servirá para control de calidad. Solo podrá sustituir la longitud eléctrica mediante una política explícita, con CRS conocido, unidades verificadas y discrepancia aceptada.

### 3.3 Fases

Las fases de líneas, cargas, maniobras y generadores se conservarán extremo a extremo. El modelo interno no convertirá automáticamente equipos mono o bifásicos en trifásicos. La escritura DGS y la inspección PowerFactory comprobarán la correspondencia de fases.

### 3.4 Regla TRAFOMIX

- `TRAFOMIX` no generará objeto eléctrico ni gráfico.
- La carga asociada específicamente a `TRAFOMIX` tampoco se generará.
- La SED válida y su carga válida sí permanecerán.
- La clasificación se basará en campos y relaciones identificadas en los TXT reales; una simple coincidencia parcial de texto no será suficiente.
- El informe enumerará cada objeto excluido, su clave compuesta, la regla aplicada y la SED/carga que permaneció.
- Una relación ambigua entre `TRAFOMIX`, SED y carga bloqueará el alimentador.

### 3.5 SED y transformadores

Una SED no implicará automáticamente crear `ElmTr2`. Se elimina la síntesis actual de 0.22 kV, Dyn5, uk=4 % y pérdidas estimadas.

- Si la SED tiene datos completos y verificables del transformador, se modelará el transformador real.
- Si solo existe la SED y su carga, se representarán únicamente los objetos respaldados por el TXT y el contrato acordado con PowerFactory.
- No se inferirá una SED exclusivamente mediante una expresión regular sobre nombres cuando falten campos relacionales suficientes.

### 3.6 Fuentes y generación

Cada fuente, central solar o generador térmico presente deberá tener un adaptador específico. El adaptador validará el conjunto mínimo exigido para el estudio solicitado, incluyendo según corresponda:

- nodo de conexión y tensión nominal;
- tecnología/tipo;
- potencia activa y reactiva o modo de control;
- potencia nominal;
- estado de servicio;
- fases;
- límites P/Q;
- datos de cortocircuito o modelo equivalente;
- fabricante/modelo cuando determine parámetros eléctricos;
- perfil/escenario si el TXT lo contiene.

Si el TXT no aporta información suficiente para flujo de carga, el equipo bloquea el alimentador. Si aporta flujo pero no cortocircuito, el flujo podrá aprobarse y el estudio de cortocircuito quedará bloqueado de forma explícita.

## 4. Arquitectura objetivo

```text
src/igea_dgs/
├── ingestion/       lectura, contratos y procedencia
├── quality/         reglas y diagnósticos bloqueantes
├── domain/          entidades eléctricas tipadas
├── rules/           reglas IGEA, incluida TRAFOMIX
├── catalog/         BD_Equipo, fichas y mappings aprobados
├── dgs/             construcción, serialización y parseo DGS
├── powerfactory/    importación, adaptadores API y estudios
├── validation/      puertas independientes y comparaciones
├── reporting/       manifiestos, hashes y reportes
├── cli/             comandos automatizables
└── gui/             interfaz delgada sobre servicios
```

La migración será incremental. Las interfaces públicas actuales se conservarán mediante fachadas mientras cada responsabilidad se extrae de los módulos monolíticos.

## 5. Flujo operativo

```text
TXT
 └─► ingestión estricta
      └─► inventario y cobertura
           └─► reglas IGEA/TRAFOMIX
                └─► catálogo y procedencia
                     └─► modelo eléctrico por fase
                          └─► validación pre-DGS
                               └─► DGS transaccional
                                    └─► validación DGS independiente
                                         └─► importación PowerFactory
                                              └─► adaptadores API
                                                   └─► inspección del modelo importado
                                                        └─► flujo del caso original
                                                             └─► informe final
```

## 6. PowerFactory

### 6.1 Contexto controlado

- Detectar versión de PowerFactory y Python API compatible.
- Conectarse a una instancia conocida.
- Crear o seleccionar un proyecto administrado por la herramienta.
- Crear un caso de estudio y escenario identificados por `run_id`.
- No modificar proyectos ajenos activos de forma implícita.
- Guardar el estado original y registrar cualquier cambio.

### 6.2 Importación y enriquecimiento

El DGS validado se importará primero. Después se ejecutarán adaptadores API pequeños e idempotentes para los elementos que necesiten configuración adicional. Cada adaptador implementará:

- `preflight`: comprueba datos y capacidades/licencia;
- `apply`: crea o actualiza objetos identificados establemente;
- `inspect`: relee atributos efectivos desde PowerFactory;
- `rollback`: revierte cambios de esa unidad cuando sea posible;
- `report`: devuelve cambios y errores estructurados.

Ejecutar dos veces el mismo lote no duplicará objetos.

### 6.3 Estudios

La primera métrica será `converges_original_case`. No se cambiarán cargas, fuentes, estados o parámetros para obtenerla.

Las correcciones de diagnóstico se permitirán únicamente en una copia separada y producirán:

- `converges_after_modification`;
- diff de objetos/atributos;
- razón de cada cambio;
- prohibición de publicar esa copia como caso original validado.

Los estudios se habilitarán solo cuando sus datos mínimos estén completos: flujo de carga, cortocircuito IEC 60909, y posteriormente contingencia u otros módulos licenciados.

## 7. Puertas de validación

### G1. Ingestión

- encabezados y columnas obligatorios;
- codificación;
- filas malformadas;
- duplicados;
- claves y referencias;
- cobertura de todas las secciones.

### G2. Completitud física

- unidades;
- rangos;
- fases;
- parámetros requeridos por tipo de equipo;
- procedencia admisible;
- fichas exactas y hashes.

### G3. Fidelidad TXT ↔ modelo

- conteos por clase;
- identidad de elementos;
- topología y componentes conexas considerando maniobras;
- fases;
- parámetros eléctricos;
- exclusiones TRAFOMIX exactas;
- totales P/Q y capacidad instalada.

### G4. Fidelidad modelo ↔ DGS

- esquema y referencias;
- circuitos/ternas/conductores;
- fases;
- impedancias y longitudes;
- estados;
- fuentes y generación;
- ausencia de defaults físicos.

### G5. Fidelidad DGS/modelo ↔ PowerFactory

- conteos e identidad;
- conectividad;
- atributos efectivos;
- fases;
- tipos;
- casos y escenarios;
- diff cero fuera de transformaciones documentadas.

### G6. Estudios

- convergencia del caso original;
- límites de tensión y cargabilidad configurables;
- balance P/Q;
- pérdidas plausibles;
- cortocircuito solo con fuente/generación completa;
- comparación contra casos dorados o resultados de referencia.

## 8. Errores y transacciones

- Cada alimentador se procesará en un directorio temporal exclusivo.
- Los artefactos finales se publicarán mediante reemplazo atómico solo después de aprobar sus puertas.
- El último resultado válido no se sobrescribirá ante un fallo.
- Cada ejecución tendrá `run_id` y manifiesto de estado.
- Los errores usarán códigos estables y severidad `blocking`, `warning` o `info`.
- Una excepción inesperada conservará traceback en el log técnico y una explicación útil en GUI/CLI.
- La API PowerFactory usará checkpoints o un proyecto temporal para evitar estados parciales.

## 9. Seguridad

- Escapar identificadores y textos en HTML.
- Neutralizar fórmulas peligrosas en Excel/TSV.
- No ejecutar contenido procedente de TXT o fichas.
- Validar rutas de entrada y salida.
- No incluir credenciales ni rutas privadas en artefactos publicados.
- Registrar hashes SHA-256 de TXT, configuración, fichas, DGS y reportes.

## 10. Dependencias y reproducibilidad

Se mantendrán grupos separados:

- `requirements.txt`: runtime mínimo;
- `requirements-powerfactory.txt`: integración local y herramientas auxiliares, sin intentar instalar `powerfactory.pyd` desde PyPI;
- `requirements-export.txt`: geografía, Excel y preview;
- `requirements-dev.txt`: pruebas, cobertura, lint, tipado, propiedades y seguridad;
- `constraints.txt`: versiones resueltas compatibles con el Python local;
- archivo de hashes/lock generado para reproducir la instalación.

La instalación se hará únicamente en `.venv`. Antes se comprobarán versión de Python, arquitectura de 64 bits y compatibilidad con `PowerFactory 2024/Python/3.12`. Después se verificarán imports, versiones, CLI, suite de pruebas y conexión API real.

## 11. Interfaces de usuario

### CLI

Comandos previstos:

- `inspect`: inventario y cobertura sin crear DGS;
- `validate-input`: puertas G1–G2;
- `convert`: modelo y DGS, puertas G1–G4;
- `import-pf`: importación y adaptadores API;
- `validate-pf`: puerta G5;
- `study`: puerta G6;
- `run`: flujo completo;
- `catalog`: fichas y mappings aprobados.

Todos devolverán códigos de salida consistentes y permitirán JSON para automatización.

### GUI

La GUI será una capa delgada y mostrará:

- progreso por puerta;
- errores bloqueantes corregibles;
- cobertura por tipo de elemento;
- exclusiones TRAFOMIX;
- procedencia de parámetros;
- estado PowerFactory;
- diferencia entre caso original y copia diagnóstica.

## 12. Estrategia de pruebas

- Unitarias por parser, regla y adaptador.
- Property-based/fuzz para filas, delimitadores, encoding y duplicados.
- Golden tests con expectativas independientes.
- Casos mono, bi y trifásicos desbalanceados.
- Casos aéreos, subterráneos, multicircuito y multiterna.
- Casos con fuentes externas, solar y térmica.
- Regresión específica TRAFOMIX/SED/cargas.
- Fallos inyectados durante escritura para probar atomicidad.
- Dobles de API para CI y pruebas reales separadas con PowerFactory.
- Comparación cuantitativa de tensión, corriente, pérdidas y P/Q contra casos dorados.

La suite diferenciará pruebas puramente locales, integración con TXT reales y aceptación propietaria PowerFactory.

## 13. Criterios de aceptación

- 100 % de secciones TXT clasificadas; ninguna ignorada silenciosamente.
- 100 % de elementos soportados presentes convertidos o bloqueados con diagnóstico específico.
- 0 defaults físicos no respaldados.
- 0 auto-mapeos aproximados.
- 100 % de parámetros productivos con procedencia admisible.
- 100 % de fases preservadas.
- Circuitos, ternas, conductores y sección iguales al TXT/catálogo aprobado.
- TRAFOMIX y su carga excluidos; SED y carga válida preservadas, comprobado por claves.
- DGS escrito atómicamente y último resultado bueno preservado.
- Reimportación API idempotente y sin objetos duplicados.
- Fidelidad PowerFactory aprobada para todos los alimentadores convertibles.
- Convergencia del caso original reportada separadamente para cada alimentador.
- Dependencias instalables desde cero en `.venv` con versiones bloqueadas.
- Puertas de calidad, tipado, seguridad y pruebas en verde.

## 14. Entregas incrementales

1. Entorno reproducible y mapa de dependencias.
2. Ingestión estricta y diagnóstico completo.
3. Procedencia, catálogo técnico y fichas.
4. Modelo eléctrico por fase y cobertura de elementos.
5. Regla TRAFOMIX y semántica SED/carga.
6. DGS fiel y transaccional.
7. Adaptadores de fuentes, solar y térmica.
8. PowerFactory modular e idempotente.
9. Validación independiente y casos dorados.
10. GUI/CLI final, documentación y aceptación completa.

Cada entrega deberá ser utilizable y comprobable antes de iniciar la siguiente.

## 15. Evidencia de diseño

- DIgSILENT documenta el patrón GIS → DGS → importación PowerFactory y la validación posterior: https://www.digsilent.de/en/paper-reader-pf-en/gis-integration.html
- La metodología de referencia de TU Wien utilizó GIS/DGS → PowerFactory y controles de plausibilidad sobre miles de redes: https://repositum.tuwien.at/bitstream/20.500.12708/7709/2/Kadam%20Serdar%20-%202018%20-%20Definition%20and%20validation%20of%20reference%20feeders%20for...pdf
- Kersting desarrolla el modelado físico de líneas, transformadores, cargas y alimentadores de distribución: https://www.routledge.com/Distribution-System-Modeling-and-Analysis/Kersting/p/book/9781498772136
- Kersting analiza expresamente líneas paralelas aéreas y subterráneas: https://doi.org/10.1109/TIA.2006.880897
- La tesis de maestría de Alonso García construye en PowerFactory redes con datos reales, líneas y cargas desbalanceadas/monofásicas: http://hdl.handle.net/10651/38720
- La tesis doctoral sobre integración solar muestra la necesidad de modelar PV como entidad diferenciada y validarla en PowerFactory: http://hdl.handle.net/11531/2643
- IEC 60909 exige datos específicos para representar contribuciones de fuentes y unidades convertidoras en cortocircuito: https://webstore.iec.ch/en/publication/24100
- La experiencia sobre una red real advierte que errores en datos de empresas eléctricas producen resultados problemáticos en motores físicos: https://doi.org/10.1016/j.segan.2025.101710
- La validación industrial de redes sintéticas combina datos, visualización, revisión experta y pruebas en plataformas reales: https://www.sciencedirect.com/science/article/abs/pii/S2452414X22000747

## 16. Fuera de alcance inicial

- SaaS, nube, multiusuario y facturación.
- Sustitución de PowerFactory por otro motor.
- Inferencia automática de fichas por similitud de nombres.
- Generación automática de parámetros eléctricos desconocidos.
- RMS, armónicos, confiabilidad y OPF antes de completar sus datos y validar flujo/cortocircuito.
- Modificación irreversible de proyectos PowerFactory ajenos al proyecto administrado.

