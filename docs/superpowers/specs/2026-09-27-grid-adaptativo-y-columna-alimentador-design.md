# Diseño de Grid adaptativo y trazabilidad por alimentador

**Fecha:** 2026-09-27  
**Estado:** aprobado conceptualmente por el usuario; pendiente de revisión del documento escrito  
**Entorno objetivo:** Windows local, PowerFactory 2024 y conversor web IGEA/CYMDIST → DGS

## 1. Objetivo

Corregir la conversión de uno o varios alimentadores para que el diagrama conserve la
escala geográfica de la referencia, el lienzo crezca con la extensión de la red y cada
carga indique inequívocamente su alimentador de origen dentro de una Grid conjunta.

El resultado debe:

1. evitar que una hoja normalizada fija comprima alimentadores grandes;
2. conservar la escala isótropa de referencia, aproximadamente 2,08 unidades de
   diagrama por metro, salvo coordenadas manifiestamente corruptas;
3. excluir los Trafomix identificados por códigos `M…` conforme a la regla existente;
4. conservar interruptores, estados y conectividad;
5. mantener el modelado interno de las SED válidas;
6. mostrar una columna **Alimentador** para las cargas `ElmLod` y extender el mismo
   atributo a `ElmSym` y `ElmXnet` cuando existan;
7. ejecutar ese posprocesamiento desde el flujo normal de la interfaz web;
8. producir evidencia de una importación real en PowerFactory 2024.

## 2. Evidencia del defecto

La regla del proyecto fija actualmente `Reglas.hoja = 'A0'`. Al aplicarse a cada
modelo, selecciona `_diagram_mapper_hoja` y evita el mapeador adaptativo. En el ejemplar
NA203–NA205 se observaron estas magnitudes:

| Magnitud | Lienzo adaptativo | Hoja A0 actual |
|---|---:|---:|
| Extensión horizontal aproximada | 64 226 | 1 120 |
| Extensión vertical aproximada | 32 716 | 574 |
| Escala aproximada | 2,08 u/m | 0,036 u/m |

La hoja A0 comprime el dibujo unas 57 veces respecto de la escala de referencia. Los
textos de PowerFactory no se reducen en la misma proporción y terminan superpuestos.

La comparación también comprobó que la conversión actual:

- excluyó 92 Trafomix `M…` de NA203 y NA205;
- escribió 570 maniobras como `ElmCoup` cerrados;
- escribió un enlace NA203–NA205 como `ElmCoup` abierto;
- escribió 187 acopladores internos de SED;
- creó dos objetos `ElmFeeder`, uno por alimentador;
- no conservó el alimentador como atributo textual de cada carga.

Por tanto, el defecto gráfico principal es la imposición posterior de A0. La falta de
la columna es un defecto separado de procedencia de datos y presentación.

## 3. Decisiones de diseño

### 3.1 Escala y tamaño del lienzo

- `REGLAS_PROYECTO` usará lienzo adaptativo por defecto (`hoja=None`).
- A0–A4 seguirá existiendo como modo explícito de impresión, nunca como regla
  obligatoria de una conversión geográfica.
- El mapeo adaptativo incluirá nodos, vértices intermedios, fuentes y margen suficiente
  para los símbolos.
- X e Y usarán la misma escala.
- El lienzo crecerá según la extensión del conjunto seleccionado, sin depender de un
  número fijo de alimentadores.
- El límite absoluto existente se conservará solamente como defensa ante un CRS o unas
  coordenadas corruptas.

### 3.2 Símbolos y elementos gráficos

- En el modo adaptativo se conservarán los tamaños de referencia de `PointTerm`,
  `d_lin`, `d_couple`, `d_load`, `d_net` y `SecSubProd`.
- Los circuitos paralelos conservarán una separación perpendicular determinista.
- Varios objetos anclados al mismo nodo usarán desplazamientos deterministas.
- Todos los interruptores sin tramo recibirán símbolo y conectores a sus dos barras.
- Las fuentes de todos los alimentadores unidos permanecerán visibles.
- El diagrama geográfico no intentará resolver la colisión de todos los rótulos
  alterando la topología. PowerFactory podrá generar diagramas esquemáticos por
  alimentador como representaciones adicionales.

### 3.3 Trafomix

- Se mantendrá la exclusión de equipos cuya identificación normalizada corresponda a
  `M…`.
- El Trafomix excluido no producirá `ElmSubstat`, `ElmTr2`, `ElmLod` ni gráfico.
- Una carga MT real con potencia distinta de cero no se eliminará solo porque uno de
  sus textos contenga la letra `M`.
- El manifiesto informará los excluidos por alimentador.

### 3.4 Interruptores

- Los dispositivos montados en tramos auxiliares `DEFAULT` de hasta 10 m se
  representarán como `ElmCoup`; no se mantendrá una línea ficticia con impedancia
  inventada.
- Cada `ElmCoup` conservará identificador, alimentador, sección, extremos y estado
  normal de CYMDIST.
- Los enlaces entre alimentadores permanecerán normalmente abiertos.
- Los acopladores internos de SED permanecerán cerrados.
- Un interruptor cuyos dos extremos se fusionen en la misma barra será un error o una
  exclusión explícita; nunca desaparecerá silenciosamente.

### 3.5 SED y cargas

Cada SED válida conservará su `ElmSubstat`, barras MT/BT, `ElmTr2`, acoplador MT y
carga `ElmLod` conectada a la barra BT. El requisito de nueva columna corresponde a la
**carga `ElmLod`**; que su nombre sea `SE50033` no cambia su clase ni la convierte en
una columna de SED.

## 4. Contrato de propiedad por alimentador

### 4.1 Fuente de verdad

El alimentador de origen se obtendrá del `NetworkID` que poseía la sección en la
entrada IGEA/CYMDIST. No se inferirá por:

- el prefijo o número de `SE…`;
- la cercanía geográfica;
- el nombre de la Grid combinada;
- el estado operativo posterior de un enlace.

### 4.2 Modelo interno

El modelo conservará una propiedad `feeder_name` o un mapa de propiedad equivalente
para cada objeto que deba exponerse. La elección concreta se fijará en el plan de
implementación, respetando estas condiciones:

- la propiedad se asigna antes de combinar modelos;
- sobrevive a fusiones de barras y eliminación de tramos auxiliares;
- una carga tiene exactamente un alimentador de origen;
- compartir un nodo con otro alimentador no cambia el propietario;
- una ambigüedad bloquea la publicación del resultado.

### 4.3 Manifiesto de importación

El artefacto que acompaña al DGS conservará, como mínimo:

- clase PowerFactory;
- FID u otra clave estable de importación;
- nombre del objeto;
- alimentador;
- sección y nodo de origen cuando correspondan.

Este manifiesto permitirá poblar los atributos en PowerFactory sin depender de nombres
no únicos.

## 5. Columna Alimentador en PowerFactory

### 5.1 Clases

Se creará una Data Extension de texto con etiqueta visible **Alimentador** para:

- `ElmLod` — General Load, requisito y aceptación principal;
- `ElmSym` — Synchronous Machine, preparado para entradas que la contengan;
- `ElmXnet` — External Grid.

El proyecto real evaluado actualmente no contiene `ElmSym`; esa clase se probará con
un modelo sintético y no se declarará validada con datos reales hasta disponer de un
ejemplar fuente.

### 5.2 Valores esperados

En la Grid conjunta `NA203_NA205`, una fila debe distinguir:

| Campo | Ejemplo |
|---|---|
| Name | `SE50033` |
| Grid | `NA203_NA205` |
| Alimentador | `NA203` o `NA205`, según la entrada |
| Terminal Substation | `SE50033` |
| Terminal | `SE50033_BT` |

El nombre `SE50033` del ejemplo no determina el valor; solo la trazabilidad de la
sección y el `NetworkID` originales lo hacen.

### 5.3 Creación y población

El posprocesamiento de PowerFactory:

1. comprobará el proyecto activo importado por la herramienta;
2. abrirá una modificación de Data Extensions;
3. creará el atributo si no existe, sin duplicarlo;
4. cerrará correctamente la modificación, incluso ante un error;
5. resolverá cada objeto por una clave estable;
6. asignará el alimentador;
7. releerá el valor efectivo;
8. informará asignados, vacíos, ambiguos y no encontrados.

La operación será idempotente. Ejecutarla dos veces no creará columnas ni objetos
duplicados.

### 5.4 Vista del Network Model Manager

La vista objetivo tendrá este orden:

```text
Name | In Folder | Grid | Alimentador | Type | Terminal Substation | Terminal
```

La primera prueba de integración determinará si PowerFactory 2024 permite insertar
programáticamente el atributo en la pestaña fija **Basic Data**:

- si lo permite, se configurará allí;
- si no lo permite, se creará o documentará una vista **Flexible Data** equivalente;
- el desarrollo no se aceptará sin una captura real donde **Alimentador** aparezca
  junto a **Grid** y los valores de NA203 y NA205 sean visibles.

No se reutilizarán `classif`, `chr_name`, `loc_name` ni otros atributos eléctricos para
simular la columna.

## 6. Integración con la interfaz

El botón web **Cargar DGS en DigSILENT + flujo** conservará su trabajo asíncrono y
ejecutará, dentro del carril serie de PowerFactory:

```text
importar DGS
  → activar proyecto/caso/escenario
  → crear o verificar Data Extension
  → poblar Alimentador
  → releer y auditar valores
  → validar inventario y conectividad
  → ejecutar flujo solicitado
  → guardar informe y mostrar resumen en el Registro
```

El Registro mostrará:

- cargas etiquetadas;
- fuentes etiquetadas;
- generadores etiquetados;
- objetos sin correspondencia;
- asignaciones ambiguas;
- estado de la columna/vista;
- resultado de importación y flujo.

Una carga sin alimentador o con varios alimentadores será un fallo bloqueante para la
aceptación de la importación.

## 7. Validación

### 7.1 Pruebas locales

- La regla predeterminada deja `diagram_sheet=None`.
- A0–A4 continúan funcionando cuando se solicitan explícitamente.
- Una red pequeña y otra grande conservan la misma escala adaptativa.
- El lienzo contiene nodos, trazas intermedias y márgenes.
- La unión de alimentadores conserva el propietario de cada carga.
- Una carga NA203 produce `Alimentador=NA203`.
- Una carga NA205 produce `Alimentador=NA205`.
- Los nodos de enlace no vuelven ambigua una carga.
- Los Trafomix `M…` no aparecen en el DGS ni en el manifiesto de cargas.
- Los interruptores conservan conteo, extremos y estado.
- La estructura interna de cada SED es consistente.
- La Data Extension simulada es idempotente.
- Se prueban las disposiciones reducida y completa del export.
- La salida sigue siendo idéntica con uno o varios procesos.
- No se introduce un recorrido completo de las tablas por alimentador.

### 7.2 Aceptación real

La aceptación final exige una ejecución real en PowerFactory 2024 con NA203–NA205:

1. DGS generado con lienzo adaptativo;
2. importación sin errores bloqueantes;
3. inventario y conectividad comparados con el manifiesto;
4. cero Trafomix `M…` modelados;
5. 570 maniobras de origen representadas, salvo diferencias justificadas por el lote;
6. enlace NA203–NA205 normalmente abierto;
7. cargas conectadas a la barra BT de su SED cuando corresponda;
8. cero cargas sin alimentador;
9. cero cargas con alimentador ambiguo;
10. muestras de NA203 y NA205 verificadas en la tabla;
11. columna **Alimentador** visible junto a **Grid**;
12. captura de la tabla y captura del diagrama;
13. informe JSON/TXT con versión de PowerFactory y resultado del flujo.

Una suite sintética aprobada no sustituye esta puerta propietaria.

## 8. Errores, reversibilidad y seguridad

- Las Data Extensions se modificarán solo en el proyecto nuevo importado por la
  herramienta, no en un proyecto ajeno activo.
- Antes del posprocesamiento se comprobará la identidad del proyecto.
- Si falla la creación de la extensión, se cerrará la transacción y el informe marcará
  el proyecto como no aceptado.
- El DGS original y sus manifiestos permanecerán intactos.
- No se cambiarán cargas, estados ni parámetros eléctricos para forzar convergencia.
- Toda corrección diagnóstica posterior se hará en una copia separada y quedará
  diferenciada del caso original.

## 9. Componentes afectados

- `src/igea_dgs/reglas.py`: valor predeterminado de hoja.
- `src/igea_dgs/model.py`: procedencia por alimentador de las cargas.
- `src/igea_dgs/combine.py`: conservación al unir modelos.
- `src/igea_dgs/dgs.py`: manifiesto de objetos y escala gráfica.
- `src/igea_dgs/batch.py`: publicación del manifiesto de asociación.
- `tools/powerfactory_acceptance.py`: Data Extension, población y puerta real.
- `src/igea_dgs/web/services.py`: invocación y Registro.
- pruebas de reglas, gráficos, combinación, DGS, API web y PowerFactory.

El frontend React solo cambiará si hace falta mostrar un nuevo campo de resultado. No
se añadirá una opción de usuario para desactivar la trazabilidad obligatoria.

## 10. Alternativas rechazadas

1. **Conservar A0 y reducir símbolos.** No mantiene el tamaño geográfico real y los
   rótulos continúan solapándose.
2. **Prefijar `loc_name` con el alimentador.** Rompe nombres operativos, búsquedas y
   plantillas de cargas.
3. **Reutilizar `classif` o `chr_name`.** Mezcla la procedencia con atributos de
   clasificación o fuente.
4. **Separar permanentemente cada alimentador en una Grid.** Impide estudiar enlaces,
   respaldo y reconfiguración entre alimentadores.
5. **Inferir por proximidad o por código `SE…`.** No es una relación estable ni
   auditable.

## 11. Fundamento técnico y científico

- DIgSILENT describe DGS como interfaz para modelos GIS/SCADA y recomienda crear los
  `ElmFeeder` desde el inicio de las líneas para representar y trazar alimentadores:
  https://www.digsilent.de/en/paper-reader-pf-en/gis-integration.html
- DIgSILENT documenta la creación de atributos personalizados con
  `BeginDataExtensionModification`, `AddConfiguration`, `AddString` y
  `EndDataExtensionModification`:
  https://www.digsilent.de/en/faq-reader-powerfactory/how-can-i-create-data-extensions-via-python.html
- El trabajo de maestría *Automatic Single-Line Diagram Generation for LV Networks
  from GIS Data* trata redes reales de complejidad variable y usa la ausencia de
  solapamientos como criterio explícito de validez:
  https://repositorio.comillas.edu/jspui/handle/11531/99738
- Rao y Deekshit, en *Electric Power Systems Research*, formulan criterios de
  legibilidad para la generación automática de unifilares de alimentadores:
  https://doi.org/10.1016/j.epsr.2003.12.005
- La tesis doctoral *Optimal Distribution Feeder Reconfiguration with Distributed
  Generation Using Intelligent Techniques* distingue los seccionadores normalmente
  cerrados de los enlaces normalmente abiertos y exige conservar la radialidad:
  https://uknowledge.uky.edu/ece_etds/134/

## 12. Criterio de terminación

El trabajo estará completo solo cuando:

- las pruebas locales y de interfaz estén en verde;
- NA203–NA205 se convierta con lienzo adaptativo;
- la importación real en PowerFactory 2024 sea satisfactoria;
- la columna **Alimentador** sea visible en General Load;
- cargas reales de NA203 y NA205 muestren el valor correcto;
- Trafomix, interruptores y SED cumplan los conteos y reglas documentados;
- las capturas y los informes de aceptación queden guardados;
- no se presente una prueba sintética como sustituto de la validación real.
