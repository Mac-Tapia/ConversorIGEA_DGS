# Diseño de integración web y retiro definitivo de la GUI antigua

**Fecha:** 2026-09-27  
**Estado:** aprobado conceptualmente; pendiente de aprobación del documento escrito  
**Estrategia aprobada:** integración incremental sobre React 19 + FastAPI (alternativa A)

## 1. Objetivo

Consolidar el conversor IGEA/CYMDIST → DGS en una única interfaz React + FastAPI,
incorporar la trazabilidad carga–alimentador y las exportaciones eléctricas completas,
mantener los flujos actualmente operativos y retirar por completo la GUI Tkinter y
sus accesos antiguos.

El resultado debe seguir funcionando con uno, dos o más alimentadores dentro de una
misma Grid DGS. Cada carga debe indicar su alimentador real (`NA203`, `NA205`, `PE104`,
`CA101` u otro detectado en la entrada), aunque la Grid conjunta tenga un nombre como
`NA203_NA205`.

## 2. Alcance funcional que debe conservarse

La interfaz web conservará la disposición, ventanas y operaciones vigentes:

1. panel **Entradas** para MDB/TXT y archivos auxiliares;
2. panel **Opciones** de conversión;
3. tabla y selección de **Alimentadores**;
4. ventana **Resultados** con archivos, descargas, ZIP y mapas;
5. ventana **Cargas de SED** con plantillas y aplicación en PowerFactory;
6. ventana **SED nuevas**;
7. ventana **Catálogo de parámetros**;
8. ventana **Sistema completo**;
9. barra de trabajos, progreso, cancelación y resumen;
10. panel redimensionable **Registro**;
11. detección de PowerFactory y ejecución serializada de sus operaciones;
12. persistencia del espacio de trabajo y recuperación de la sesión local.

No se rediseñarán estas ventanas ni se reemplazarán por un editor unifilar. Los
cambios visuales se limitarán a integrar datos, filtros, estados y descargas nuevas
sin romper la navegación existente.

## 3. Arquitectura objetivo

```text
MDB/TXT y catálogos
        │
        ▼
ingesta y validación estricta
        │
        ▼
modelo eléctrico normalizado con procedencia
        │
        ├── trazado carga → terminal → SED → red MT → alimentador
        ├── conversión DGS individual o conjunta
        └── exportación eléctrica completa
        │
        ▼
servicios de aplicación y trabajos
        │
        ├── carril paralelo para lectura/conversión
        └── carril exclusivo para PowerFactory
        │
        ▼
FastAPI REST + WebSocket
        │
        ▼
React 19 (interfaz única)
```

La API será asíncrona en los puntos de entrada, pero las operaciones intensivas o
bloqueantes se ejecutarán fuera del hilo del servidor. PowerFactory seguirá teniendo
un único carril de ejecución porque su motor no admite concurrencia arbitraria.

## 4. Integración de ramas

### 4.1 Base de integración

Se creará un worktree de integración desde la rama vigente. Allí se incorporarán en
primer lugar los cambios limpios de `feat/grid-alimentador-implementation`:

- Grid adaptativo por defecto;
- conservación de procedencia por alimentador;
- metadatos y Data Extension de alimentador;
- asignación y auditoría en PowerFactory;
- columna/descargas en la interfaz;
- soporte de catálogo MDB complementario;
- mapa `Name → Alimentador`;
- exportaciones eléctricas completas;
- conversión conjunta paralelizada y determinista.

Después de cada grupo se ejecutarán pruebas. La integración no avanzará si aparece
una regresión en los flujos web existentes.

### 4.2 Rama de robustecimiento

`feat/robustecimiento-igea` no se fusionará completa porque diverge de la interfaz
actual, elimina componentes vigentes y contiene trabajo local no consolidado. Solo se
extraerán módulos independientes después de revisar su contrato y sus pruebas:

- diagnóstico tipado y procedencia;
- custodia de entradas mediante SHA-256;
- revisiones inmutables;
- publicación atómica;
- validaciones de cobertura y resolución exacta.

La extracción será por commits o archivos concretos, nunca por sobrescritura masiva
del frontend o del servidor actual.

## 5. Contrato carga–alimentador

### 5.1 Fuente de verdad

El valor **Alimentador** se obtiene de la procedencia eléctrica de la sección en la
entrada IGEA/CYMDIST y se conserva al combinar redes. No se infiere por el nombre de
la carga, por proximidad geográfica ni por el nombre de la Grid conjunta.

El recorrido verificable será:

```text
carga → terminal BT → SED/transformador → terminal MT → sección/red de origen
      → NetworkID/alimentador
```

### 5.2 Estados

Cada fila tendrá exactamente uno de estos resultados:

- código de alimentador identificado;
- `NO_IDENTIFICADO`, si falta la procedencia necesaria;
- `AMBIGUO`, si existen propietarios incompatibles;
- `DESCONECTADO`, si no existe un camino eléctrico válido.

Los tres últimos estados aparecerán en el diagnóstico y bloquearán la aceptación
estricta, pero no se ocultarán ni se sustituirán por un valor predeterminado.

### 5.3 PowerFactory

La propiedad se publicará como Data Extension visible **Alimentador** en `ElmLod` y,
cuando existan, en `ElmSym` y `ElmXnet`. La operación será idempotente y se verificará
releyendo cada valor después de escribirlo.

## 6. API de inventario eléctrico

Se añadirá un contrato tipado y paginado, integrado al espacio de trabajo:

```text
GET /api/workspaces/{workspace_id}/electrical-inventory
```

Filtros mínimos:

- `feeder`;
- `class_name`;
- `status`;
- búsqueda por nombre/SED;
- `offset` y `limit`.

La respuesta incluirá conteo total, filtros efectivos y filas. Una fila de carga
contendrá, cuando estén disponibles:

- `name`;
- `class_name`;
- `alimentador`;
- `network_id`;
- `grid`;
- `sed`;
- `terminal_substation`;
- `terminal`;
- `kw`, `kvar`, `kva` y factor de potencia;
- tensión MT y BT;
- potencia nominal, impedancia, pérdidas en cobre y vacío del transformador;
- grupo vectorial;
- estado, diagnóstico y procedencia de entrada.

Las descargas CSV/JSON usarán la misma fuente de datos y los mismos filtros para
evitar discrepancias entre pantalla y archivos.

## 7. Integración React

La ventana **Cargas de SED** conservará su flujo actual de plantilla y aplicación en
PowerFactory. Antes de ese flujo se agregará una sección **Inventario de cargas** con:

- columna `Name`;
- columna `Alimentador` inmediatamente después de `Grid` cuando esta se muestre;
- SED y terminales;
- magnitudes eléctricas principales;
- estado de trazabilidad;
- filtros por alimentador, estado y texto;
- paginación del servidor;
- descarga CSV/JSON.

La tabla no cargará decenas de miles de filas en el navegador. Se mantendrá una
cantidad limitada por página y las búsquedas se resolverán en el servidor.

Los diagnósticos críticos se mostrarán también en la tabla de alimentadores y en el
Registro. No se incorporarán React Flow, Cytoscape ni edición de topología en esta
fase; una vista de topología de solo lectura podrá evaluarse después sin condicionar
la consolidación actual.

## 8. Grid, escala y modelado

- El lienzo DGS será adaptativo a la extensión geográfica de los alimentadores.
- Las escalas X/Y serán isótropas y los tamaños no dependerán de una hoja A0 fija.
- A0–A4 permanecerán disponibles solo como formatos explícitos de impresión.
- Los Trafomix identificados correctamente con `M…` seguirán excluidos.
- Los interruptores conservarán identidad, terminales y estado normal.
- Las SED válidas conservarán barras MT/BT, transformador, acopladores y cargas.
- Al combinar alimentadores, cada objeto conservará su propietario original.
- Los enlaces entre alimentadores se representarán como normalmente abiertos cuando
  así corresponda a la fuente.

## 9. Exportaciones

Cada ejecución publicará de manera atómica:

- DGS por alimentador;
- DGS conjunto cuando se solicite;
- inventario de redes;
- inventario de SED;
- inventario de cargas;
- transformadores, líneas, interruptores, fuentes y generadores;
- mapa `Name → Alimentador`;
- diagnósticos y exclusiones;
- manifiesto con conteos, procedencia y hashes.

La lectura MDB o TXT debe producir el mismo contrato normalizado. La ausencia o
ambigüedad de una entrada obligatoria será un error explícito, no una selección
silenciosa del primer archivo disponible.

## 10. Retiro definitivo de la interfaz antigua

La eliminación se ejecutará solamente después de demostrar equivalencia funcional de
la interfaz web. Se retirarán:

- `src/igea_dgs/gui.py`;
- `run_gui_escritorio.bat`;
- `run_gui.bat`;
- el subcomando CLI `gui`;
- el entry point `igea-dgs-gui`;
- `tests/test_gui_wiring.py`;
- referencias de uso de Tkinter o de los lanzadores anteriores.

Se creará `run_web.bat` como lanzador oficial, sin alias de compatibilidad. La función
de selección de versión de PowerFactory hoy reutilizada desde `gui.py` se moverá a un
módulo no visual antes de eliminar el archivo.

La documentación conservará únicamente estos accesos:

```text
run_web.bat
python -m igea_dgs.web
igea-dgs-web
igea-dgs list|convert|web
```

## 11. Errores, seguridad y recuperación

- Se conservarán las defensas contra traversal en cargas y descargas.
- Los archivos fuente permanecerán de solo lectura y con hash registrado.
- Los resultados parciales no reemplazarán una publicación válida.
- La cancelación conservará alimentadores terminados y descartará de forma atómica el
  alimentador en curso.
- Los errores REST tendrán código estable, mensaje y contexto; el frontend no deberá
  analizar textos libres para decidir estados.
- El WebSocket podrá reconectarse y recuperar el estado mediante REST.
- El servidor seguirá enlazado a loopback por defecto.
- Las modificaciones de PowerFactory se limitarán al proyecto importado y validarán
  su identidad antes de escribir.

## 12. Pruebas y puertas de aceptación

### 12.1 Automatizadas

- pruebas unitarias del trazado carga–alimentador;
- casos NA203, NA205, PE104, CA101 y alimentador desconocido;
- combinación de dos y varios alimentadores;
- equivalencia MDB/TXT;
- Trafomix, interruptores y estructura SED;
- inventario paginado, filtros y exportaciones;
- API REST, WebSocket, cancelación y rutas protegidas;
- componentes React mediante Vitest y React Testing Library;
- recorrido de interfaz mediante Playwright;
- compilación TypeScript y Vite;
- prueba de instalación limpia y `run_web.bat`;
- prueba que confirme la ausencia de archivos, comandos y referencias GUI antiguos.

### 12.2 Regresión de ventanas

Playwright recorrerá las cinco ventanas vigentes, cargará entradas, seleccionará
alimentadores, iniciará una conversión simulada, abrirá resultados, preparará cargas,
accederá a SED nuevas, catálogo y sistema completo, y comprobará el Registro. La
retirada de Tkinter no se aceptará hasta que ese recorrido esté en verde.

### 12.3 Aceptación real

La terminación exige ejecuciones reales con los ejemplares de referencia:

1. NA203 y NA205, individualmente y en Grid conjunta;
2. PE104;
3. CA101;
4. importación en PowerFactory 2024;
5. columna **Alimentador** visible y correcta en cargas reales;
6. conteos de SED, cargas, líneas e interruptores conciliados;
7. cero Trafomix excluidos indebidamente;
8. flujo ejecutado y resultado documentado, sin confundir una prueba sintética con la
   aceptación propietaria.

Si PowerFactory o algún ejemplar no está disponible, la implementación podrá quedar
lista y sus pruebas automatizadas aprobadas, pero la validación real se informará como
pendiente y no como superada.

## 13. Secuencia de entrega

1. crear worktree de integración y línea base reproducible;
2. integrar y verificar `feat/grid-alimentador-implementation`;
3. implementar API e inventario React con TDD;
4. ejecutar regresión completa de ventanas;
5. extraer componentes seguros de robustecimiento por unidades independientes;
6. ejecutar regresión completa nuevamente;
7. crear `run_web.bat` y migrar documentación;
8. eliminar GUI antigua y sus entry points;
9. probar instalación limpia y ausencia de referencias antiguas;
10. ejecutar aceptación NA203/NA205, PE104 y CA101;
11. generar informe final con evidencia, limitaciones y artefactos.

## 14. Alternativas rechazadas

1. **Fusionar íntegramente la rama de robustecimiento.** Destruiría componentes web
   vigentes y mezclaría cambios incompletos.
2. **Reescribir la plataforma con React Flow o Cytoscape.** Amplía el alcance sin
   resolver primero la trazabilidad y la conversión auditada.
3. **Mantener Tkinter como respaldo.** Duplica cableados y permite que ambas
   interfaces diverjan.
4. **Conservar `run_gui.bat` como alias.** Contradice el retiro estricto aprobado y
   perpetúa documentación ambigua.
5. **Copiar el nombre de la Grid a Alimentador.** No distingue los objetos de redes
   combinadas.

## 15. Fundamento técnico y científico

- La tesis de maestría *Automatic Single-Line Diagram Generation for LV Networks
  from GIS Data* sustenta el procesamiento modular de datos GIS y la evaluación de
  legibilidad en redes de distinta complejidad:
  https://repositorio.comillas.edu/jspui/handle/11531/99737
- La tesis doctoral sobre descomposición de dominio y procesamiento paralelo de redes
  eléctricas respalda particionar trabajos independientes preservando interfaces
  explícitas entre subredes:
  https://orbi.uliege.be/handle/2268/183353
- El artículo indexado sobre flujo de potencia multinúcleo sustenta paralelizar tareas
  computacionalmente independientes con particiones controladas:
  https://doi.org/10.3233/JIFS-169350
- GridMind, BambooGrid y TENSA muestran la viabilidad del patrón React + API para
  análisis eléctrico, aunque no se copiará su alcance de edición gráfica:
  https://github.com/shikharmishra1/gridmind
  https://github.com/kickstage/bamboogrid
  https://github.com/Roger-GO/TENSA

## 16. Criterio de terminación

El trabajo estará completo cuando:

- la interfaz React conserve todas las ventanas y operaciones actuales;
- la tabla de cargas muestre el alimentador real y permita filtrar/exportar;
- las conversiones de referencia generen Grid y escala adaptativas;
- MDB y TXT exporten redes, SED y características eléctricas completas;
- las pruebas Python, frontend y end-to-end estén en verde;
- exista evidencia separada de la aceptación real en PowerFactory;
- `run_web.bat` sea el único lanzador visual;
- no existan código, entry points, pruebas ni documentación operativa de la GUI
  Tkinter antigua.
