# Dataset PIDE universal a partir del expediente PIDEELOR

## Intención

Construir un dataset auditable que enseñe a ejecutar integralmente la metodología del Plan de
Inversión en Distribución Eléctrica (PIDE) para cualquier empresa distribuidora. `PIDEELOR` será
el primer caso empresarial completo: aporta entregables, cálculos, alternativas, observaciones,
absoluciones, modelos y resultados reales, pero no fija la identidad ni los valores que deberá
tener otra empresa.

El resultado estructural será común: artículos, estudios, formatos, clases de alternativas,
evidencias y entregables. Cambiarán la problemática revelada por el diagnóstico, los activos,
los parámetros, las cantidades, el calendario y la alternativa que resulte técnicamente viable.

## Decisión de diseño

Se implementará un contrato de dos ejes relacionados:

1. **Contrato PIDE universal:** artículos 1–20, requisitos, entradas, procedimientos, formatos,
   familias de alternativas, cálculos, evidencias y criterios de aceptación.
2. **Instancias empresariales:** empresa, concesión, sede, sistema eléctrico, SET, alimentador,
   SED, escenario, horizonte, alternativa y resultados propios.

La identidad de la empresa se conserva obligatoriamente como procedencia. No participa como
característica causal para decidir la metodología ni se oculta mezclando registros de empresas.
Durante el entrenamiento, los ejemplos podrán representar los identificadores mediante roles
(`EMPRESA`, `SISTEMA`, `SET`, `ALIMENTADOR`), pero cada registro conservará una referencia al
archivo original, su empresa custodio y su huella SHA-256.

## Objetivos

- Inventariar cada carpeta y archivo de `referencia/PIDEELOR` sin modificar los originales.
- Representar todos los artículos PIDE mediante requisitos ejecutables y trazables.
- Extraer contenido semántico y estructurado de PDF, DOCX, XLSX/CSV y GIS.
- Registrar, sin fingir lectura, los formatos propietarios como SQL Server, DIgSILENT, Microsoft
  Project, DWG, correo y archivos comprimidos.
- Aprender la secuencia problema → diagnóstico → alternativas → simulación → economía →
  priorización → entregable → observación → absolución.
- Reutilizar los mismos formatos y clases de alternativa para cualquier empresa.
- Separar claramente evidencia documental, cálculo reproducido, simulación nativa, cumplimiento
  eléctrico y aprobación regulatoria.

## No objetivos

- Copiar los resultados numéricos de ELOR como resultados esperados para otra empresa.
- Suponer que un alimentador de otra empresa tiene la topología, demanda o restricciones de ELOR.
- Presentar la prepublicación metodológica o un entregable empresarial como norma vigente.
- Declarar convergencia o cumplimiento porque existe un archivo `.pfd`, `.BAK` o un informe.
- Convertir automáticamente documentos empresariales en ejemplos de entrenamiento `gold`.

## Antiobjetivos

El sistema se considerará incorrecto si:

- pierde la empresa o el archivo de origen;
- memoriza identificadores ELOR como reglas universales;
- mezcla revisiones, alternativas o años incompatibles;
- promueve una observación, borrador o copia como versión definitiva;
- rellena campos ausentes por inferencia silenciosa;
- confunde existencia documental con aceptación eléctrica o regulatoria;
- genera un entregable sin poder explicar qué fuentes y cálculos producen cada campo.

## Modelo conceptual

```text
Artículo PIDE
  └─ Requisito
      ├─ Datos mínimos
      ├─ Procedimiento reproducible
      ├─ Evidencia esperada
      ├─ Estudio o cálculo
      ├─ Criterio de aceptación
      ├─ Formato de salida
      └─ Hallazgo de cumplimiento

Empresa
  └─ Sede / sistema eléctrico
      └─ SET / alimentador / SED / activo
          └─ Diagnóstico
              └─ Problema y causa
                  └─ Alternativas comparables
                      └─ Resultados técnicos y económicos
                          └─ Proyecto priorizado y entregable
```

## Estructura del dataset

### 1. Manifiesto de custodia `pide_files`

Un registro por archivo:

- `file_id`, `relative_path`, `sha256`, `bytes`, `modified_utc`;
- empresa, periodo, entrega, revisión y anexo inferidos con evidencia de ruta;
- extensión declarada, firma real y familia documental;
- estado de apertura y extracción;
- relación de duplicidad por contenido;
- relación con archivo contenedor o conjunto GIS;
- advertencias: temporal de Office, archivo roto, CRS ausente, vínculo externo o lector nativo
  requerido.

### 2. Árbol de expediente `pide_deliverables`

Representará convocatoria o periodo, entregables, anexos, observaciones, absoluciones y versión
definitiva. Una relación de sucesión conservará la evolución documental sin reemplazar el
histórico.

### 3. Fragmentos citables `pide_fragments`

Texto de PDF y DOCX segmentado por página, título, sección o tabla. Cada fragmento conservará
`file_id`, localización, método de extracción y calidad. El OCR, cuando sea necesario, se marcará
explícitamente.

### 4. Activos estructurados `pide_assets`

- XLSX/CSV: libro, hoja, rango, encabezados, fórmulas, vínculos externos y unidades.
- GIS: capa, geometría, CRS, extensión, cantidad de entidades, atributos y calidad espacial.
- Modelos y bases propietarias: metadatos verificables sin afirmar contenido no leído.

### 5. Contrato metodológico `pide_requirements`

Catálogo versionado de artículos 1–20, formatos, entradas, estudios, reglas, evidencias y salidas.
La fuente jurídica y su estado (`vigente`, `proyecto`, `pendiente`, `derogada` o
`evidencia_tecnica`) serán obligatorios.

### 6. Casos de entrenamiento `pide_cases`

Cada caso contendrá:

- alcance empresarial y temporal;
- entidades eléctricas implicadas;
- evidencia de entrada;
- problema y causa identificados por el diagnóstico;
- alternativas consideradas, incluidas las descartadas;
- resultados técnicos, económicos y de riesgo;
- alternativa seleccionada y justificación;
- formato o entregable producido;
- observaciones, correcciones y estado de verificación.

Los casos derivados únicamente de documentos serán `context`. Solo una confirmación humana o
una ejecución nativa con guardado, reapertura y lectura posterior podrá promover el aspecto
correspondiente a `gold`.

## Universalidad de formatos y alternativas

Los formatos tendrán identificadores y campos canónicos independientes de la empresa. Una tabla
de adaptación mapeará encabezados, códigos y unidades encontrados en cada expediente al campo
canónico. Se conservarán tanto el valor original como el normalizado.

Las alternativas se representarán mediante clases reutilizables, entre ellas:

- reconfiguración o transferencia de carga;
- cambio de conductor o refuerzo de tramo;
- nuevo alimentador, enlace o salida de SET;
- ampliación, repotenciación o nueva subestación;
- compensación reactiva y regulación de tensión;
- seccionamiento, protección, automatización y Smart Grid;
- reemplazo por antigüedad, seguridad u obsolescencia;
- reducción de pérdidas y mejora de calidad o confiabilidad;
- solución para electrificación, expansión de demanda o sistemas aislados.

La clase puede repetirse entre empresas; ubicación, dimensionamiento, año, costo y resultado se
calculan para la red diagnosticada.

## Controles de generalización

- División de entrenamiento y validación por empresa o sistema, no por filas aleatorias.
- Pruebas metamórficas: renombrar empresa, SET y alimentadores no debe cambiar la secuencia
  metodológica.
- Ningún identificador empresarial podrá ser condición de una regla universal.
- Los valores de ELOR no funcionarán como valores predeterminados.
- La ausencia de datos generará `sin_evidencia`, no imputación silenciosa.
- La recuperación semántica siempre devolverá procedencia, versión y estado jurídico.
- La respuesta distinguirá “así se hizo en ELOR” de “esto exige el contrato PIDE”.

## Hallazgos iniciales que condicionan la implementación

- El corpus tiene 1,397 archivos y aproximadamente 28.32 GB.
- Dos PDF no abren correctamente y un DOCX referencia una imagen inexistente.
- Cinco supuestos XLSX son archivos temporales `~$` y se excluirán como libros.
- Los 271 libros válidos contienen 3,677 hojas y 418 vínculos externos.
- Las 24 capas Shapefile carecen de CRS declarado; los seis GeoPackage declaran EPSG:4326.
- Los archivos `.BAK` y varios archivos sin extensión tienen firma de respaldo SQL Server.
- Los modelos DIgSILENT y cronogramas MPP requieren lectores o aplicaciones nativas para una
  verificación semántica completa.

## Flujo de construcción

1. Inventario determinista, firmas y SHA-256.
2. Agrupación de archivos compuestos y duplicación por contenido.
3. Clasificación por periodo, entrega, revisión, anexo y función PIDE.
4. Extracción por formato con estado explícito.
5. Mapeo de fragmentos, hojas y capas hacia requisitos y formatos canónicos.
6. Construcción de casos problema-alternativa-resultado-entregable.
7. Auditoría de calidad, privacidad, procedencia y estado jurídico.
8. Publicación de JSONL/Parquet e índice de recuperación como datos `context`.
9. Promoción selectiva a `gold` únicamente mediante aceptación demostrable.

## Salidas previstas

- Herramienta reproducible de inventario y extracción PIDE.
- Manifiesto completo archivo por archivo.
- Dataset normalizado y corpus citable.
- Matriz artículos–requisitos–evidencias–entregables.
- Informe de calidad y cobertura por carpeta, formato y artículo.
- Pruebas de independencia de empresa y de conservación de procedencia.
- Adaptador al constructor del dataset del asistente sin acoplarlo al conversor eléctrico.

## Alternativas consideradas

1. **Dataset universal con procedencia empresarial — elegida.** Mantiene un contrato común y
   conserva cada empresa como instancia auditable. Permite generalizar sin perder custodia.
2. **Entrenamiento directo con ELOR.** Más rápido, pero memoriza nombres, valores y decisiones
   particulares; no demuestra transferencia a otra empresa.
3. **Anonimización irreversible y mezcla de empresas.** Reduce identificadores visibles, pero
   destruye linaje, dificulta corregir errores y puede mezclar resultados incompatibles.

## Fundamento regulatorio y científico

La Resolución Osinergmin N.° 264-2016-OS/CD define la secuencia de presentación, publicación,
observación, absolución y aprobación del PIDE, condicionada a criterios y metodología aprobados
por el MINEM. Los Informes Legales N.° 570-2023-GRT y N.° 628-2025-GRT documentan que esos
instrumentos continuaban pendientes; por ello, el corpus empresarial se clasificará como
evidencia técnica/metodológica y no se presentará automáticamente como norma vigente.

Mansor (2018), en su tesis doctoral sobre planificación integrada de redes de distribución,
demuestra la necesidad de integrar inversión, operación, seguridad, confiabilidad y estándares
de empresa. Soni (2018), en su tesis de maestría, muestra que la previsión geográfica debe
evaluarse con estudios y datos reales de red. Zambrano Asanza (2022), en su tesis doctoral,
integra previsión espacio-temporal, red MT existente y expansión de subestaciones. Las revisiones
de *Renewable and Sustainable Energy Reviews* sobre expansión moderna e incertidumbre (2024)
justifican representar escenarios, alternativas, flexibilidad e incertidumbre, no solo una
solución determinista.

## Criterios de aceptación

- Cada archivo original aparece exactamente una vez en el manifiesto de custodia.
- Cada registro derivado apunta a un archivo y localización verificables.
- Los duplicados no generan ejemplos semánticos repetidos, pero conservan todas sus ubicaciones.
- Los 20 artículos poseen contrato, evidencia esperada y estado de cobertura.
- Los formatos canónicos no contienen nombres empresariales en su definición.
- Un caso puede sustituir todos sus identificadores empresariales sin alterar la metodología.
- ELOR puede reconstruirse como instancia sin contaminar valores predeterminados universales.
- Ninguna fuente documental se declara aceptación nativa, eléctrica o regulatoria.
- Los archivos ilegibles o propietarios quedan inventariados con causa y siguiente verificación.
- La suite enfocada y la suite completa terminan sin omisiones ocultas.

## Referencias

- Mansor, N. N. (2018). *Integrated planning of modern distribution networks incorporating UK
  utility practices* [Doctoral dissertation, University of Manchester].
  https://research.manchester.ac.uk/en/studentTheses/integrated-planning-of-modern-distribution-networks-incorporating/
- Soni, M. (2018). *Assessment of geographical based load forecast approach in distribution
  planning* [Master's thesis, University of Cape Town]. http://hdl.handle.net/11427/30175
- Zambrano Asanza, S. P. (2022). *Planejamento integrado da expansão de sistemas de distribuição
  de energia elétrica considerando previsão espaço-temporal da demanda* [Doctoral dissertation,
  Universidade Estadual Paulista].
  https://repositorio.unesp.br/entities/publication/4811b265-8b80-4d12-ac79-e3e3bcc4ca73
- *Modern distribution system expansion planning considering new market designs: Review and
  future directions*. (2024). *Renewable and Sustainable Energy Reviews, 202*, 114709.
  https://doi.org/10.1016/j.rser.2024.114709
- *A review of uncertainty management approaches for active distribution system planning*.
  (2024). *Renewable and Sustainable Energy Reviews, 205*, 114808.
  https://doi.org/10.1016/j.rser.2024.114808
- Osinergmin. (2016). Resolución N.° 264-2016-OS/CD.
- Osinergmin. (2023). Informe Legal N.° 570-2023-GRT.
- Osinergmin. (2025). Informe Legal N.° 628-2025-GRT.
