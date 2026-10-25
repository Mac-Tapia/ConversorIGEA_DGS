# Cierre de pendientes y conversión universal por SET — Plan de implementación

> **Para Codex:** ejecutar este plan por fases con TDD, un commit por tarea y verificación independiente antes de promover resultados. No cerrar requisitos por evidencia estática, mocks, HTTP 200 o mera convergencia del oráculo interno.

**Objetivo:** completar la conversión por sistema eléctrico de modo que cada SET genere un `ElmNet` independiente en cualquier sistema —incluidos Chincha Nueva (CHN) y Pampa de Oca—, cerrar las inconsistencias entre especificaciones y código, y dejar un cierre auditable del backlog sin omitir alimentadores ni aceptación eléctrica nativa.

**Arquitectura:** una selección de sistema produce un único proyecto/DGS con varios `ElmNet`, exactamente uno por SET del alcance. La selección, el alcance esperado y los alimentadores sin topología se modelan antes de combinar datos. La publicación falla de forma cerrada si falta topología; conversión estructural, convergencia, calidad eléctrica y persistencia PowerFactory son puertas independientes.

**Tecnología:** Python 3, pytest, FastAPI, frontend existente, DGS/PowerFactory, lectores TXT/MDB/VNR-GIS, JSON de perfiles y manifiestos SHA-256.

---

## 1. Línea base y definición de “cerrado”

### Evidencia actual que el plan debe resolver

- Hay 25 directorios de especificaciones y la especificación 003 referenciada no existe.
- Se detectaron 1,296 requisitos, 170 sin evidencia de prueba/código y 45 tareas abiertas; la especificación 013 no tiene `tasks.md`.
- La especificación 022 se declara implementada, pero mantiene T11c, T11d, T14 y T16 sin cierre nativo y su `plan.md` aún figura como borrador.
- Nasca genera 6 `ElmNet` para 6 SET; Chincha y Pisco generan hoy un solo `ElmNet` por zonal, aunque la misma ejecución en memoria produjo correctamente 5 y 7 redes por SET, respectivamente.
- Los alimentadores CA103, CN103, PN208 y PI101 tienen fuente pero no topología y pueden quedar omitidos silenciosamente por el filtro actual.
- La API web rechaza sistemas de un alimentador por reutilizar una regla de “unir” que exige dos; la CLI no tiene esa restricción.
- El manifiesto de una selección zonal calcula `faltan` contra toda la empresa, no contra el alcance solicitado.
- La suite focalizada pasó 81 pruebas y el inventario 48; el último conjunto completo conocido en el mismo HEAD fue 2,873 aprobadas y 47 omitidas. Esto es línea base, no aceptación final.
- Los resultados Chincha y Pisco convergen en el oráculo interno, pero presentan mínimos de 0.749 y 0.866 p.u.; convergencia no equivale a calidad eléctrica aceptable.
- No hay duplicados exactos ni archivos vacíos entre los 650 archivos versionados. En datos/resultados no versionados hay 1,155 grupos de hash repetido y unos 6.95 GB potencialmente redundantes, principalmente evidencia de custodia que no debe borrarse por hash solamente.

### Criterio global de cierre

Una tarea solo cambia a cerrada cuando existen, en el mismo commit o cadena trazable:

1. requisito aprobado y no contradictorio;
2. prueba roja reproducible previa;
3. implementación mínima;
4. prueba focalizada verde;
5. evidencia real para TXT, MDB y VNR-GIS cuando aplique;
6. aceptación PowerFactory de importación, lectura posterior, cálculo, guardado y reapertura cuando aplique;
7. matriz requisito → código → prueba → evidencia actualizada;
8. `git status` limpio.

Los estados permitidos serán `pendiente`, `bloqueado_datos`, `implementado`, `validado_real`, `aceptado_nativo` y `cerrado`. “Implementado” no será sinónimo de “cerrado”.

---

## 2. Orden de ejecución y dependencias

```text
Contrato/spec 022
      ↓
Selección y alcance ──→ política universal un ElmNet/SET
      ↓                              ↓
faltantes explícitos           manifiesto scoped
      └──────────────┬───────────────┘
                     ↓
              API/CLI/frontend
                     ↓
          TXT → MDB → VNR-GIS reales
                     ↓
       PowerFactory: importar/calcular/reabrir
                     ↓
          cierre de specs y limpieza segura
```

No ejecutar limpieza de evidencias ni cerrar la especificación 022 antes de superar la aceptación nativa.

---

## 3. Fase A — cerrar el contrato antes del código

### Tarea A1: corregir la especificación 022 y su estado

**Archivos:**

- Modificar: `specs/022-conversion-sistema-electrico/spec.md`
- Modificar: `specs/022-conversion-sistema-electrico/plan.md`
- Modificar: `specs/022-conversion-sistema-electrico/tasks.md`
- Pruebas: `tests/test_inventario.py`

**Paso 1 — escribir prueba roja**

Agregar una comprobación que falle si una especificación se declara implementada/cerrada con tareas abiertas, o si `spec.md`, `plan.md` y `tasks.md` usan estados incompatibles.

**Paso 2 — redefinir los requisitos contradictorios**

- Sustituir RF64/RF67/RF70 por un contrato universal: toda conversión por sistema crea un `ElmNet` por SET, sin lista especial de zonales.
- Precisar que “sistema seleccionado” puede abarcar varios códigos `ElmZone`, pero nunca fusiona SET distintas en el mismo `ElmNet`.
- Establecer que un alimentador declarado sin topología produce `bloqueado_datos`; no se omite ni se inventa red.
- Separar selección de sistema de la operación “unir dos o más alimentadores”.
- Definir el alcance del manifiesto solo sobre SET/alimentadores solicitados.
- Dejar T14/T16 abiertas hasta evidencia PowerFactory; retirar cualquier texto que las presente como corregidas.

**Paso 3 — ejecutar prueba**

`pytest tests/test_inventario.py -q`

**Paso 4 — commit**

`git commit -m "spec: define conversion universal por SET"`

### Tarea A2: resolver la referencia inexistente a la especificación 003

**Archivos:**

- Modificar: `specs/002-arquitectura-por-capas/spec.md`
- Crear solo si existe alcance documental verificable: `specs/003-<alcance>/spec.md`, `plan.md`, `tasks.md`
- Pruebas: `tests/test_inventario.py`

**Pasos:**

1. Añadir prueba que falle ante referencias `specs/NNN-*` inexistentes.
2. Determinar por historial Git si la referencia delega trabajo real o es obsoleta.
3. Crear la especificación 003 completa únicamente si hay requisitos recuperables; en otro caso, eliminar la delegación y devolver los requisitos a 002.
4. Ejecutar `pytest tests/test_inventario.py -q`.
5. Commit: `git commit -m "spec: resolve missing specification 003"`.

---

## 4. Fase B — selección completa y fail-closed

### Tarea B1: introducir un resultado de selección común

**Archivos:**

- Modificar: `src/igea_dgs/estructura.py`
- Modificar: `src/igea_dgs/cli.py`
- Modificar: `src/igea_dgs/web/services.py`
- Crear: `tests/test_seleccion_sistema.py`

**Interfaz propuesta:**

```python
@dataclass(frozen=True)
class SeleccionSistema:
    zonales: tuple[str, ...]
    sets: tuple[str, ...]
    alimentadores_esperados: tuple[str, ...]
    alimentadores_convertibles: tuple[str, ...]
    sin_topologia: tuple[str, ...]
    fuera_de_alcance: tuple[str, ...]

def seleccionar_sistema(
    estructura: EstructuraEmpresa,
    alimentadores_fuente: Collection[str],
    alimentadores_topologia: Collection[str],
    zonales: Collection[str],
) -> SeleccionSistema:
    ...
```

**Pasos TDD:**

1. Probar Chincha: CHN/SET esperadas aparecen aunque CN103 carezca de topología.
2. Probar Pisco: PN208 y PI101 se clasifican en `sin_topologia`, no desaparecen.
3. Probar un sistema de un solo alimentador: selección válida.
4. Probar códigos desconocidos: error explícito, sin fallback global.
5. Implementar una única función y reemplazar los filtros duplicados de CLI/web.
6. Ejecutar `pytest tests/test_seleccion_sistema.py tests/test_reglas.py tests/test_sistema_web.py -q`.
7. Commit: `git commit -m "feat: centraliza seleccion completa de sistemas"`.

### Tarea B2: impedir publicación parcial silenciosa

**Archivos:**

- Modificar: `src/igea_dgs/combine.py`
- Modificar: `src/igea_dgs/batch.py`
- Modificar: `src/igea_dgs/cli.py`
- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Crear: `tests/test_sistema_faltantes.py`

**Comportamiento:**

- Con `sin_topologia != ()`, permitir diagnóstico y previsualización.
- No promover el DGS como resultado completo.
- Devolver `bloqueado_datos` con lista, SET, archivos fuente y acción de remediación.
- Solo un parámetro diagnóstico explícito y no predeterminado podrá producir cabeceras sin red; nunca marcará el resultado como completo.

**Pruebas:** CN103, CA103, PN208 y PI101 deben quedar visibles y causar el estado correcto.

**Verificación:**

`pytest tests/test_sistema_faltantes.py tests/test_web_api.py -q`

**Commit:** `git commit -m "fix: bloquea sistemas con topologia faltante"`.

---

## 5. Fase C — un `ElmNet` por SET para cualquier sistema

### Tarea C1: eliminar la excepción específica de Nasca

**Archivos:**

- Modificar: `src/igea_dgs/estructura.py`
- Modificar: `src/igea_dgs/combine.py`
- Modificar: `config/perfiles/electro_dunas.estructura.json`
- Modificar: `tests/test_estructura.py`
- Modificar: `tests/test_estructura_nuevos.py`
- Modificar: `tests/test_dgs_por_set.py`
- Crear: `tests/test_sistema_por_set_universal.py`

**Contrato:**

```python
def estructurar_por_set(
    seleccion: SeleccionSistema,
    dataset: Dataset,
) -> ResultadoEstructurado:
    """Produce exactamente una red por SET del alcance."""
```

La configuración no enumerará zonales autorizadas para dividir por SET. El nombre de red será determinista y derivado de identificadores canónicos, no del texto libre del TXT.

**Casos rojos mínimos:**

- Nasca: 6 SET → 6 `ElmNet`.
- Chincha: 5 SET → 5 `ElmNet`; CHN102 pertenece solo a Chincha Nueva.
- Pisco: 7 SET → 7 `ElmNet`; Pampa de Oca conserva únicamente sus alimentadores.
- Ica: cada SET presente genera su propia red.
- Ningún alimentador aparece en dos redes.

**Implementación:** retirar `zonales_por_set` como interruptor funcional y convertir por SET siempre que la operación sea “sistema eléctrico”. Mantener el modo individual sin estructura artificial.

**Verificación:**

`pytest tests/test_sistema_por_set_universal.py tests/test_dgs_por_set.py tests/test_estructura.py tests/test_estructura_nuevos.py -q`

**Commit:** `git commit -m "feat: genera una red por SET en todo sistema"`.

### Tarea C2: validar recorridos completos de Chincha Nueva y Pampa de Oca

**Archivos:**

- Crear: `tests/test_recorridos_chn_pdo.py`
- Modificar si falla el algoritmo: `src/igea_dgs/model.py`, `src/igea_dgs/validate.py` y/o `src/igea_dgs/combine.py`

**Pruebas por alimentador:**

1. identificar fuente/cabecera;
2. recorrer todos los nodos y tramos alcanzables;
3. detectar islas, ciclos inválidos, extremos huérfanos y equipos sin nodo;
4. comparar conteos antes/después por tipo de objeto;
5. comprobar codificación canónica y unicidad global;
6. exigir asignación única a SET y `ElmNet`.

Para CHN102, la prueba debe enumerar su recorrido real y fallar si cualquier objeto alcanzable desaparece. Para Pampa de Oca se aplica el mismo oráculo a cada alimentador, no una muestra.

**Verificación:** `pytest tests/test_recorridos_chn_pdo.py -q`.

**Commit:** `git commit -m "test: cubre recorridos completos de CHN y Pampa de Oca"`.

---

## 6. Fase D — manifiesto y estados de aceptación

### Tarea D1: hacer el manifiesto dependiente del alcance

**Archivos:**

- Modificar: `src/igea_dgs/batch.py`
- Modificar: `src/igea_dgs/combine.py`
- Crear: `tests/test_manifest_scope.py`

**Campos obligatorios:**

```json
{
  "alcance": {"zonales": [], "sets": [], "alimentadores": []},
  "por_set": {},
  "sin_topologia": [],
  "fuera_de_alcance": [],
  "estado_conversion": "...",
  "estado_convergencia": "...",
  "estado_calidad_electrica": "...",
  "estado_powerfactory": "..."
}
```

`faltan` se calcula solo contra `alcance.alimentadores`; los demás se informan como `fuera_de_alcance` y no degradan la selección.

**Verificación:** `pytest tests/test_manifest_scope.py -q`.

**Commit:** `git commit -m "fix: limita manifiestos al sistema solicitado"`.

### Tarea D2: separar las cuatro puertas de aceptación

**Archivos:**

- Modificar: `src/igea_dgs/validate.py`
- Modificar: `src/igea_dgs/batch.py`
- Modificar: `src/igea_dgs/web/app.py`
- Modificar: `src/igea_dgs/web/services.py`
- Crear: `tests/test_acceptance_gates.py`

**Puertas:**

1. estructura y esquema DGS;
2. completitud del alcance;
3. convergencia del oráculo/PowerFactory;
4. calidad eléctrica y persistencia nativa.

Una tensión mínima de 0.749 p.u. puede ser convergente, pero debe fallar calidad eléctrica. Umbrales deberán provenir del perfil aprobado y quedar registrados en el manifiesto.

**Verificación:** `pytest tests/test_acceptance_gates.py -q`.

**Commit:** `git commit -m "feat: separa puertas de aceptacion electrica"`.

---

## 7. Fase E — paridad de API, CLI y frontend

### Tarea E1: separar “seleccionar sistema” de “unir alimentadores”

**Archivos:**

- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Modificar: `src/igea_dgs/cli.py`
- Modificar: `frontend/src/**` únicamente en componentes consumidores identificados con `rg "sistema|alimentador|unir" frontend/src`
- Modificar: `tests/test_sistema_web.py`
- Modificar: `tests/test_web_api.py`

**Pasos:**

1. Escribir prueba de contrato común para CLI/API con sistema de uno y varios alimentadores.
2. Mantener `>=2` solo en la operación de unión manual.
3. Mostrar “un proyecto, una red por SET” y los bloqueos de datos.
4. Exponer conteos por SET y recorrido por alimentador.
5. Ejecutar pruebas backend y pruebas frontend existentes.

**Commit:** `git commit -m "fix: alinea seleccion de sistemas en web y CLI"`.

---

## 8. Fase F — fuentes reales y determinismo

### Tarea F1: aplicar el mismo contrato a TXT, MDB y VNR-GIS

**Archivos:**

- Modificar solo según fallos: `src/igea_dgs/sources/txt.py`, `src/igea_dgs/sources/mdb.py`, `src/igea_dgs/sources/vnr.py` y adaptadores consumidores identificados con `rg "TXT|MDB|VNR|GIS" src/igea_dgs`
- Crear: `tests/test_sistema_por_set_fuentes_reales.py`
- Actualizar: fixtures/manifiestos de evidencia, sin copiar fuentes de custodia al repositorio

**Matriz obligatoria:**

| Fuente | Nasca | Chincha | Pisco | Ica |
|---|---:|---:|---:|---:|
| TXT | requerida | requerida | requerida | requerida |
| MDB | requerida | requerida | requerida | requerida |
| VNR-GIS | requerida | requerida | requerida | requerida |

Cada celda debe comprobar alcance, redes por SET, conteos, codificación, faltantes explícitos y hash de entrada. Si una fuente real no existe, la celda queda `bloqueado_datos`, nunca verde por mock.

**Commit:** `git commit -m "test: valida conversion por SET en todas las fuentes"`.

### Tarea F2: demostrar determinismo

**Archivos:**

- Crear: `tests/test_sistema_por_set_determinismo.py`

**Pasos:** ejecutar cada caso con 1 y 4 trabajadores y comparar hashes normalizados, orden, nombres y manifiestos. Dos ejecuciones equivalentes deben producir artefactos equivalentes.

**Commit:** `git commit -m "test: exige determinismo por sistema y SET"`.

---

## 9. Fase G — aceptación PowerFactory obligatoria

### Tarea G1: protocolo nativo por sistema/SET

**Archivos:**

- Modificar: herramientas PowerFactory existentes localizadas con `rg "PowerFactory|ComLdf|ElmNet" tools tests`
- Crear: `tests/native/test_sistemas_por_set_powerfactory.py`
- Crear: `docs/evidence/powerfactory/sistemas_por_set/README.md`

**Secuencia por Chincha, Pisco, Nasca e Ica:**

1. importar en proyecto nuevo;
2. releer objetos y comprobar un `ElmNet` por SET;
3. comprobar que cada alimentador y equipo pertenece a una sola red;
4. ejecutar `ComLdf` y registrar código de retorno;
5. registrar tensiones, sobrecargas, islas y equipos fuera de servicio;
6. guardar, cerrar, reabrir y repetir lectura/convergencia;
7. conservar hashes, versión de PowerFactory, proyecto y log.

La prueba debe fallar si el runtime no está disponible en el entorno de aceptación; no usar `skip`/`xfail` para una liberación marcada cerrada.

**Commit:** `git commit -m "test: acepta sistemas por SET en PowerFactory"`.

### Tarea G2: completar T14 y T16 de la especificación 022

Actualizar `tasks.md` solo después de que la evidencia nativa anterior demuestre importación, caso base, calibración mínima y procedencia de cada diagrama. Commit separado: `git commit -m "spec: cierra aceptacion nativa de sistemas"`.

---

## 10. Fase H — cierre controlado de las demás especificaciones

Los 45 pendientes no deben mezclarse en un único cambio. Crear y aprobar estos planes hijos antes de modificar código de cada frente:

1. `docs/superpowers/plans/2026-10-25-spec-002-arquitectura-por-capas.md` — 29 RF sin evidencia y 10 tareas abiertas.
2. `docs/superpowers/plans/2026-10-25-specs-011-016-estudios-troncal.md` — dependencias de modelo y estudios.
3. `docs/superpowers/plans/2026-10-25-spec-012-confiabilidad-capacidad.md` — 60 RF sin evidencia y 11 tareas abiertas.
4. `docs/superpowers/plans/2026-10-25-spec-013-definicion-y-tareas.md` — convertir el borrador en contrato aprobado y crear `tasks.md` antes de implementar.
5. `docs/superpowers/plans/2026-10-25-spec-017-informes.md` — 57 RF sin evidencia y 11 tareas abiertas.
6. `docs/superpowers/plans/2026-10-25-spec-025-calibracion-anual.md` — cerrar tres tareas con datos reales y aceptación eléctrica.
7. `docs/superpowers/plans/2026-10-25-aceptaciones-nativas-restantes.md` — tareas abiertas en 005, 007, 008, 014, 020, 022 y 026.

Cada plan hijo debe inventariar requisitos exactos, propietario, dependencias, prueba roja, implementación, evidencia real/nativa y criterio de reversión. La matriz global no puede contar una mención textual como cobertura.

### Tarea H1: automatizar la matriz bidireccional

**Archivos:**

- Crear: `tools/spec_traceability.py`
- Crear: `tests/test_spec_traceability.py`
- Modificar: `tests/test_inventario.py`
- Generar: `docs/evidence/spec-traceability.json`

**Reglas:** todo RF debe enlazar código o decisión explícita, al menos una prueba pertinente y evidencia cuando corresponda; toda prueba/implementación debe enlazar un RF o deuda aprobada. Detectar referencias rotas, tareas abiertas incompatibles con el estado y especificaciones sin `tasks.md`.

**Commit:** `git commit -m "feat: valida trazabilidad bidireccional de specs"`.

---

## 11. Fase I — duplicados, obsoletos y limpieza recuperable

### Tarea I1: clasificar antes de deduplicar

**Archivos:**

- Crear: `tools/inventory_storage.py`
- Crear: `tests/test_inventory_storage.py`
- Crear: `docs/evidence/storage-inventory.json`

Clasificar cada duplicado como `custodia_inmutable`, `resultado_reproducible`, `cache`, `temporal_bloqueado` o `desconocido`. Registrar ruta, hash, tamaño, productor, consumidor y prueba de regeneración. Los archivos `~$` bloqueados no se eliminan mientras estén abiertos.

### Tarea I2: deduplicación conservadora

Solo después de validar el inventario, sustituir copias de custodia por almacenamiento direccionado por contenido o enlaces compatibles, manteniendo manifiestos y rutas lógicas. Mover antes a cuarentena recuperable; verificar todos los consumidores; borrar solo material reproducible y aprobado.

**Commit:** `git commit -m "chore: deduplica evidencia con custodia verificable"`.

---

## 12. Fase J — puerta final de liberación

### Tarea J1: ejecución completa

Ejecutar, registrar y archivar:

```powershell
pytest -q
pytest tests/native -q --run-native
python tools/spec_traceability.py --fail-on-gap
python tools/inventory_storage.py --verify-only
git diff --check
git status --short
```

Además:

- ejecutar el frontend/linter/build usados por CI;
- ejecutar conversiones reales TXT/MDB/VNR-GIS con 1 y 4 trabajadores;
- comparar manifiestos y hashes;
- verificar que no haya `skip`/`xfail` en las pruebas necesarias para el cierre;
- revisar que los únicos bloqueos sean externos, documentados y no etiquetados como completados.

### Tarea J2: revisión independiente y cierre

Revisar en cuatro capas:

1. **Código:** contratos, errores, determinismo y compatibilidad.
2. **Datos:** alcance, custodia, codificación y conteos.
3. **Eléctrica:** conectividad, convergencia, límites y PowerFactory.
4. **Trazabilidad:** RF ↔ código ↔ prueba ↔ evidencia.

Corregir hallazgos, repetir la puerta completa y crear el commit final solo con árbol limpio:

`git commit -m "release: cierra conversion universal por SET y trazabilidad"`

No etiquetar la versión si CN103/CA103/PN208/PI101 siguen sin topología dentro de un alcance que se pretende completo; mantener `bloqueado_datos` hasta obtener o reconstruir evidencia autorizada.

---

## 13. Justificación científica y académica

- El modelado explícito de subestaciones, barras y conectividad como grafo respalda el recorrido completo y la asignación única de activos: [Cal Poly, tesis de maestría sobre modelado gráfico de sistemas eléctricos](https://digitalcommons.calpoly.edu/theses/2301/).
- La topología desactualizada o incompleta limita la monitorización y el análisis, por lo que los alimentadores sin red deben bloquear la aceptación y no desaparecer: [TU Delft, tesis doctoral sobre identificación de topología](https://repository.tudelft.nl/record/uuid%3A69618edf-ffc9-4b6e-93b9-364853a90a33).
- La identificación topológica depende de calidad de datos, observabilidad y tratamiento de múltiples subestaciones: [Electric Power Systems Research, revisión indexada 2024](https://www.sciencedirect.com/science/article/pii/S0378779624004243) e [IEEE, identificación de topología](https://ieeexplore.ieee.org/document/9435253).
- La validación cruzada entre transformadores/redes con datos limitados justifica comprobar cada SET y no extrapolar la aceptación de Nasca a Chincha o Pisco: [TU Delft, tesis de maestría sobre modelos de red con datos limitados](https://repository.tudelft.nl/file/File_6428ba4e-ef8e-46c6-bba9-343916edfb22).
- La trazabilidad conservadora y bidireccional justifica la matriz RF → código → prueba → evidencia y el cierre fail-closed: [University of York, tesis doctoral sobre ejecuciones trazables](https://etheses.whiterose.ac.uk/id/eprint/30114/1/Conservative%20and%20traceable%20executions%20of%20heterogeneous%20model%20management%20workflows.pdf) y [NASA SWE-072](https://swehb.nasa.gov/spaces/7150/pages/16449898/SWE-072%2B-%2BBidirectional%2BTraceability%2BBetween%2BSoftware%2BTest%2BProcedures%2Band%2BSoftware%2BRequirements).
- Las fuentes GIS abiertas e incompletas requieren declarar calidad y lagunas, no asumir completitud: [International Journal of Electrical Power & Energy Systems, artículo indexado](https://www.sciencedirect.com/science/article/pii/S0142061524006185).

---

## 14. Resultado esperado

El cierre correcto no es “todos los checks marcados”, sino un repositorio en el que:

- cualquier sistema se convierte con una red independiente por SET;
- CHN102 y cada alimentador de Pampa de Oca conservan su recorrido, códigos y equipos;
- ningún alimentador fuente queda omitido silenciosamente;
- web, CLI y API aplican el mismo contrato;
- los manifiestos informan únicamente el alcance pedido y separan las puertas de aceptación;
- TXT, MDB y VNR-GIS tienen evidencia real;
- PowerFactory confirma importación, cálculo, guardado y reapertura;
- cada requisito y cada tarea tienen evidencia bidireccional;
- la limpieza preserva custodia y el árbol Git queda limpio.
