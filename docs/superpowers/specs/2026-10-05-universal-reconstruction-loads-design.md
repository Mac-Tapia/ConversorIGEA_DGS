# Diseño universal de reconstrucción, convergencia y cargas masivas

**Fecha:** 2026-10-05
**Estado:** aprobado en conversación; pendiente de revisión del documento
**Alcance:** interfaz web, fuentes TXT/MDB/VNR-GIS, reconstrucción eléctrica
auditable, conversión DGS, aceptación PowerFactory y actualización masiva de
cargas y SED.

## 1. Objetivo

El conversor debe funcionar para cualquier empresa, periodo, CRS, nomenclatura de
alimentadores y combinación válida de equipos. Electro Dunas e IN111 son conjuntos
de aceptación disponibles, no reglas del producto.

Una entrada incompleta no se descarta. El sistema conserva los originales,
construye una copia derivada, completa lo que pueda con catálogos o inferencias
eléctricas trazables y conduce cada alimentador hasta DGS y PowerFactory. Cuando se
requiera un supuesto, el resultado debe declararlo sin presentar el dato derivado
como original.

## 2. Principios invariantes

- TXT, MDB y VNR-GIS permanecen aislados; ninguna modalidad completa otra.
- Los originales se custodian byte a byte, con SHA-256, y nunca se modifican.
- Toda salida pertenece a un único `source_run_id`, modalidad y fingerprint.
- Empresa, periodo, CRS, alimentadores y códigos se descubren en ejecución o se
  solicitan explícitamente; no se permiten valores empresariales incrustados.
- Los valores originales de cable, material, sección, disposición, tensión,
  transformador, carga y equipo tienen prioridad.
- Cada valor derivado conserva origen, regla, confianza, alternativas y motivo.
- Generar DGS, importar, releer y converger son estados diferentes.
- Un alimentador fallido no modifica ni invalida los demás.

## 3. Arquitectura

```text
Original TXT | MDB | VNR-GIS
          ↓
Custodia inmutable + SHA-256
          ↓
Adaptador de fuente
          ↓
Modelo canónico universal
          ↓
Diagnóstico por alimentador
          ↓
Reconstrucción derivada y auditable
          ↓
DGS + manifiesto de transformaciones
          ↓
PowerFactory + relectura + ComLdf
```

El motor de reconstrucción será independiente de los adaptadores y recibirá el
modelo canónico, el catálogo disponible y una política. Producirá otro modelo y un
`ReconstructionReport`; nunca mutará la instantánea original.

Cada decisión tendrá uno de estos niveles:

- `ORIGINAL`: dato conservado de la fuente.
- `CATALOG_MATCH`: dato completado mediante catálogo exacto o compatibilidad
  eléctrica demostrable.
- `ENGINEERING_ASSUMPTION`: inferencia necesaria cuando no existe evidencia
  suficiente en la entrada o catálogos.

## 4. Selección universal de empresa y periodo

El adaptador VNR no tendrá `ELDU` como valor predeterminado. Primero inventariará
empresas y periodos:

- si existe uno de cada uno, los selecciona y registra;
- si hay varios, la API devuelve las opciones y exige selección explícita;
- una publicación oficial puede sugerir empresa/periodo, pero el contenido del
  paquete debe confirmarlos;
- una selección vacía o ambigua no mezcla empresas ni periodos.

La misma regla se aplicará a entregas multiempresa de TXT/MDB cuando sus
identificadores lo permitan.

## 5. Reconstrucción topológica

La reconstrucción conserva todos los tramos y equipos originales y aplica, en
orden, las siguientes reglas:

1. recuperar nodos existentes omitidos por filtros o tablas parciales;
2. crear nodos terminales ausentes usando extremos, coordenadas y relaciones de
   los equipos que los referencian;
3. fundir tramos puente `DEFAULT` cortos y trasladar sus maniobras a acopladores;
4. conectar una discontinuidad cuando exista un único candidato compatible por
   tensión, fase, distancia y radialidad;
5. ante varios candidatos, puntuar y escoger la alternativa eléctricamente viable
   de mayor confianza, conservando la lista completa de candidatos;
6. registrar cualquier isla residual y continuar con un modelo derivado, sin
   ocultarla.

Una unión automática nunca puede cruzar niveles de tensión incompatibles, mezclar
empresas/periodos o modificar la identidad de un equipo original.

## 6. Conductores, equipos y catálogos

La prioridad para completar parámetros es:

1. registro original de equipo;
2. coincidencia exacta del catálogo incluido en la entrega;
3. catálogo del fabricante;
4. catálogo global controlado y versionado;
5. coincidencia compatible por clase, material, sección, número de conductores,
   disposición, aislamiento, tensión y condición aérea/subterránea;
6. derivación física de impedancia/capacidad cuando los atributos necesarios estén
   disponibles;
7. perfil técnico provisional universal como último recurso.

No se reemplazará un código original por un código similar. El modelo conservará
el código original y asociará los parámetros adoptados como una resolución
separada. Cada catálogo tendrá nombre, versión, fuente, fabricante cuando aplique y
SHA-256.

## 7. Transformadores, SED y cargas

- Se conservan potencia, tipo, tensión y fases originales.
- Los parámetros ausentes se completan con la misma jerarquía de catálogos.
- Una SED sobrecargada puede redimensionarse al tamaño normalizado inmediato que
  cubra su carga; se registran tamaño original y derivado.
- Una carga ausente no se inventa si no existe evidencia de demanda. Puede
  mantenerse en cero y marcarse como supuesto.
- Las actualizaciones de carga nunca sobrescriben silenciosamente el caso base:
  usan escenario de operación y las SED nuevas usan variación.

## 8. Estrategia de convergencia

La secuencia es determinista y auditable:

1. ejecutar `ComLdf` sobre el modelo reconstruido sin cambiar demanda;
2. corregir configuración de fuente/slack y estados incoherentes;
3. tratar áreas no alimentadas, islas y elementos fuera de servicio;
4. corregir parámetros provisionales físicamente inconsistentes;
5. repetir con inicialización y opciones numéricas documentadas;
6. como último recurso, aislar o reducir carga temporalmente y declararlo en el
   informe, sin presentar esa ejecución como solución eléctrica definitiva.

Cada intento registra plan, objetos afectados, valores anteriores/nuevos, código
de retorno, diagnóstico y resultado. Si una escritura falla se restaura el valor
anterior. Un proyecto nuevo fallido queda aislado para inspección; un proyecto
existente se revierte.

## 9. Estados del alimentador

- `READY_ORIGINAL`: convertible sin completar datos.
- `READY_RECONSTRUCTED`: convertible después de aplicar catálogo o reglas.
- `CONVERGED_ORIGINAL`: relectura y `ComLdf` válidos sin reconstrucción.
- `CONVERGED_RECONSTRUCTED`: relectura y `ComLdf` válidos con cambios trazados.
- `CONVERTED_WITH_ASSUMPTIONS`: DGS producido con supuestos que requieren revisión.
- `NEEDS_OPERATOR_REVIEW`: se conservaron DGS, diagnóstico e intentos, pero no se
  obtuvo convergencia después de agotar la política.

Los estados anteriores sustituyen el bloqueo preventivo como experiencia normal.
Solo se impedirá una mutación peligrosa: cruce de identidad de fuente, mezcla de
modalidades, escritura fuera del workspace o plan de PowerFactory distinto del
preflight.

## 10. Interfaz web

### 10.1 Entrada

- Tres alternativas mutuamente excluyentes: TXT, MDB y VNR-GIS.
- Empresa y periodo detectados, con selector cuando sean ambiguos.
- Banda permanente con modalidad, empresa, periodo, `source_run_id` y fingerprint.
- Electro Dunas no aparece como marca del producto.

### 10.2 Alimentadores

La tabla permite seleccionar uno, varios, visibles o todos y añade:

- calidad de la fuente;
- número de reparaciones y supuestos;
- catálogo empleado;
- estado de conversión y convergencia;
- acceso al informe original → reconstruido.

Las acciones serán `Diagnosticar`, `Reconstruir y convertir`, `Convertir todos`,
`Ver cambios`, `Cargar en PowerFactory` y `Descargar evidencia`.

### 10.3 Semáforo

- verde: original y convergente;
- azul: reconstruido mediante catálogo;
- amarillo: contiene supuestos explícitos;
- rojo: no convergió y requiere revisión, pero conserva artefactos y diagnóstico.

## 11. Actualización masiva de cargas y SED

El módulo web existente se consolidará como flujo productivo:

1. leer proyectos PowerFactory y sus alimentadores;
2. seleccionar proyecto y orden de alimentadores;
3. cargar uno o ambos libros: actualización y SED nuevas;
4. aceptar por fila `kW+kvar`, `kW+FP` o `kVA+FP`;
5. separar columnas de entrada de los valores actuales;
6. distribuir cada SED por identidad, hoja, nodo o coordenada, con evidencia;
7. mostrar plan y errores antes de escribir;
8. aplicar un escenario para cargas y una variación para SED nuevas;
9. releer P, Q, FP, fases y objetos creados;
10. ejecutar `ComLdf` por alimentador;
11. revertir solo el alimentador fallido y continuar según la política seleccionada;
12. producir JSON/TXT/XLSX de valores anteriores/nuevos, creación, convergencia y
    rollback.

Los libros con múltiples alimentadores son válidos. La interfaz no supone códigos
ni nombres concretos de empresa.

## 12. API y contratos

Se incorporarán contratos explícitos para:

- inventario de empresas y periodos por fuente;
- diagnóstico y reconstrucción por selección;
- política de reconstrucción y nivel máximo de supuesto;
- informes y decisiones por objeto;
- historial de intentos de convergencia;
- planificación, aplicación y rollback de cargas masivas.

Todos los endpoints de mutación verifican workspace, run activo, modo, fingerprint,
hash de artefacto y plan preflight.

## 13. Pruebas

### 13.1 Automatizadas

- fuentes y nombres genéricos, sin códigos de Electro Dunas;
- selección universal de empresa/periodo;
- aislamiento TXT/MDB/VNR-GIS;
- custodia y preservación de originales;
- reconstrucción de nodos, tramos, islas y catálogos incompletos;
- jerarquía de resolución y trazabilidad de cada dato;
- uno/varios/todos los alimentadores;
- API, seguridad de rutas y compilación frontend;
- actualización masiva, SED nuevas, conflicto de pares y distribución por
  alimentador;
- relectura, rollback y aislamiento de fallos.

### 13.2 Eléctricas

- conectividad y radialidad esperada;
- tensiones y fases compatibles;
- balance P/Q y capacidad instalada;
- conservación cuantitativa entre fuente, modelo y DGS;
- DGS releído y comparado con el modelo derivado.

### 13.3 Reales

- Fixtures universales prueban la lógica general.
- Electro Dunas/IN111 se usa como aceptación real disponible, no como requisito.
- TXT y MDB se ejecutan en runs independientes.
- Un VNR-GIS se declara real solo con paquete oficial/completo.
- PowerFactory exige relectura efectiva y `ComLdf`; éxito de comando no basta.

## 14. Criterios de producción

- La suite completa y el build frontend terminan sin fallos.
- Los originales y sus hashes permanecen sin cambios.
- Todo valor derivado tiene procedencia y nivel de confianza.
- No existen defaults empresariales incrustados.
- La conversión de un alimentador no consume archivos de otra modalidad.
- La aceptación PowerFactory utiliza el mismo plan y `source_run_id` del preflight.
- Las pruebas reales distinguen ejecución, importación, relectura y convergencia.
- Los cambios se comprometen de forma aislada y se publican en la rama actual solo
  después de la verificación final.

## 15. Fundamento científico

La representación canónica, validación y conversión entre herramientas
propietarias se apoya en la tesis doctoral de McMorran sobre CIM:
<https://stax.strath.ac.uk/concern/theses/cc08hf706>.

La reconstrucción de modelos mediante GIS, teoría de grafos y validación con flujo
de potencia se sustenta en la tesis de maestría de Özdamar:
<https://open.metu.edu.tr/handle/11511/44535>.

El uso de datos limitados para producir modelos GIS y análisis de flujo accionables
está documentado en la tesis doctoral de Strathclyde:
<https://stax.strath.ac.uk/concern/theses/1r66j1947>.

La identificación conjunta de topología y parámetros ante información incompleta
está respaldada por IEEE Transactions on Power Systems:
<https://ieeexplore.ieee.org/document/9781319/> y por IET Generation,
Transmission & Distribution: <https://doi.org/10.1049/gtd2.12634>.

La integración práctica GIS-simulador sobre una red real está documentada por
Valverde et al.: <https://doi.org/10.1049/iet-gtd.2016.1560>.
