# Plan — Spec 014

Lee: `docs/constitution.md` y `specs/014-calibracion-en-sin-proyecto/spec.md`.

## Contexto técnico

Todo ocurre en los guiones de DIgSILENT del carril `powerfactory`. La web solo cambia en
lo que pasa al plan y en los avisos que muestra, que ya se pintan como lista.

- `tools/casos_pf.py`: prepara los tres casos. Hoy `clasificar()` separa las variaciones
  solo por su nombre (`Ajuste_…` y `Carga_…`), y `preparar()` exige un ajuste previo y
  desactiva en «Sin proyecto» y «Con proyecto» todos los ajustes anteriores (011:RF-50).
- `tools/ajuste_cabecera_pf.py`: ya ajusta en «Sin proyecto» cuando existen los tres casos
  (`ejecutar`, líneas 556 a 560). Desactiva todos los `ajustes_de(feeder)` (líneas 679 a
  681), graba en los escenarios de «Con proyecto» y «Caso base» (`al_escenario`, línea 276)
  y, al final, desactiva los ajustes anteriores en «Con proyecto» (líneas 857 a 869).
- `tools/cargas_pf.py`: `resolver_nuevas()` busca «ya existe» con `ElmFeeder.GetObjs`, que
  solo ve la red activa (línea 517). La fase 2 entra en «Con proyecto» y activa la base
  (líneas 1128 a 1138). `crear_variacion()` toma como fecha de la etapa el `iStudyTime` del
  caso.
- `tools/estudios_pf.py`: usa los casos que deja `casos_pf.preparar`, que la web lanza
  antes de estudiar (`services.py`, línea 2449).
- `tests/fake_pf.py`: casos con sus propias variaciones activas y su escenario. Una
  variación recuerda sus cambios en `_cambios`, pero una etapa no lista sus objetos.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Qué contiene una variación | `tools/casos_pf.py` (`objetos_de_variacion`, `es_del_operador`, `clasificar`), `tests/fake_pf.py` | Definiciones; RF-3, RF-15, RF-20 |
| B. Casos sin ajuste previo | `tools/casos_pf.py` (`preparar(..., sin_base=True)`) | RF-5 |
| C. Variaciones por caso al preparar | `tools/casos_pf.py` (`preparar`) | RF-15, RF-16, RF-18, RF-20 a RF-22 |
| D. Ajuste que respeta al operador | `tools/ajuste_cabecera_pf.py` (`ejecutar`, `al_escenario`) | RF-1 a RF-4, RF-14 |
| E. Cargas nuevas durante el ajuste | `tools/ajuste_cabecera_pf.py` | RF-6 a RF-9 |
| F. Gana lo manual | `tools/ajuste_cabecera_pf.py`, `src/igea_dgs/ajuste_cabecera.py` (`fijas` con origen `manual`) | RF-10 a RF-13 |
| G. Inserción sin duplicados | `tools/cargas_pf.py` (`indice_de_cargas_nuevas`, `resolver_nuevas`, fase 2) | RF-19, RF-21 a RF-28 |
| H. Avisos sin bloqueo | `src/igea_dgs/powerfactory_binding.py` (ya existe), pruebas | RF-17 |
| I. Documentos | specs 004, 006, 007 y 011 (nota «cambiado por 014:RF-n»), `CODIGO_FUENTE.md`, `docs/MANUAL_COMANDOS.md` | Trazabilidad |

### A. Qué contiene una variación

`objetos_de_variacion(v)` devuelve `(clase, nombre)` de los objetos de todas sus etapas
(`IntSstage.GetContents('*')`), una vez por variación. Una variación es **del operador**
si no es `Carga_…` y no es un ajuste «puro». Un ajuste puro es un `Ajuste_<alim>_…`
cuyas etapas solo contienen `ElmLod` del alimentador. `_3` de CA101, con 168 `ElmLod` y 4
`ElmTr2`, sale del operador. `clasificar()` añade el grupo `operador`. `anteriores` queda
solo con los ajustes puros.

### B. Casos sin ajuste previo

`preparar()` acepta un plan sin `base` cuando lo llama el ajuste: renombra el caso activo
a «Caso base», crea las copias y no activa ninguna calibración. La comprobación «primero
hay que calibrar» (011:RF-13) se mantiene cuando lo pide la web para estudiar.

### C. Variaciones por caso al preparar

- «Caso base»: desactiva la calibración, las cargas nuevas y los ajustes puros. Las del
  operador no se tocan.
- «Sin proyecto»: activa la calibración, desactiva las cargas nuevas (RF-16) y los
  ajustes puros anteriores. Las del operador no se tocan (RF-15).
- «Con proyecto»: activa la calibración, las cargas nuevas y las del operador que estén
  activas en «Sin proyecto» (RF-21). Desactiva solo los ajustes puros anteriores (RF-20).
  El informe da `variaciones_operador_activadas` (RF-22).

### D. Ajuste que respeta al operador

- Con los tres casos, el ajuste trabaja en «Sin proyecto», como hoy (RF-1). Sin ellos,
  llama antes a `casos_pf.preparar(sin_base=True)` (RF-5).
- Desactiva solo los ajustes puros del alimentador. Las variaciones del operador siguen
  activas durante el cuadre, así que la cabecera las incluye (RF-3, RF-14).
- `al_escenario` graba en «Sin proyecto» y «Con proyecto», nunca en «Caso base» (RF-4).
- Al final, en «Con proyecto»: activa la variación nueva, desactiva solo los ajustes
  puros y no toca las del operador (RF-3).
- El aviso «Ajustes anteriores desactivados» nombra solo los puros. Otro aviso lista las
  variaciones del operador que quedaron activas.

### E. Cargas nuevas durante el ajuste

Las cargas nuevas son los `ElmLod` de las variaciones `Carga_…` (parte A). Antes del
cuadre, las que estén en servicio en el caso de medida se ponen fuera de servicio en su
escenario. En «Sin proyecto» no debería haber ninguna (RF-16), así que esto es una guarda.
Al terminar o cancelar, en el `finally`, cada una vuelve a su estado (RF-7, RF-8).
`al_escenario` escribe solo las cargas de `cargas_sed()` del alimentador, que no incluye
las nuevas (RF-9).

### F. Gana lo manual

La demanda que grabó el último ajuste se lee en DIgSILENT, en la etapa del último ajuste
del alimentador (el valor de cada `ElmLod` en la etapa). La demanda actual se lee en
«Sin proyecto» con su escenario activo. Si difieren más que la tolerancia de relectura,
es un cambio manual de demanda. Esa carga entra en el reparto como fija, con origen
`manual` y su demanda actual (RF-10). No se escribe en ningún escenario (RF-11). El
informe da `cargas_manuales` con las dos demandas, y un aviso las resume (RF-12). Sin
ajuste anterior no se compara nada (RF-13).

### G. Inserción sin duplicados

- `indice_de_cargas_nuevas(app, feeders)` recorre una vez las variaciones `Carga_…` y la
  red de «Con proyecto». Devuelve, por nombre de carga en su alimentador, la lista de
  variaciones que la contienen y si está en la red (RF-23, RF-27).
- `resolver_nuevas()` lo usa en lugar de `GetObjs`:
  - en una sola variación: no se crea, se activa esa variación en «Con proyecto» y se
    informa (RF-24);
  - en la red fuera de una variación: no se crea y se dice dónde está (RF-25);
  - en varias variaciones: no se crea, no se toca ninguna y se avisa (RF-26);
  - si la potencia o el punto difieren de la fila: aviso con los dos valores (RF-28).
- Fase 2: al entrar en «Con proyecto», activa las variaciones del operador activas en
  «Sin proyecto» (RF-21, RF-22). Si faltan los tres casos, los prepara antes (RF-19).

## Decisiones

- **El ajuste sigue grabando en su variación `Ajuste_…` y en los escenarios.** Descartado:
  grabar solo en el escenario, porque la idempotencia de la 006 (RF-41 a RF-43) y la base
  de la 007 leen la variación del ajuste.
- **Variación del operador por su contenido, no por su nombre.** Descartado: por nombre,
  porque `_3` se llama como un ajuste y lleva los transformadores del operador.
- **El cambio manual de demanda se detecta con la etapa del último ajuste, en
  DIgSILENT.** Descartado: el informe guardado en la web, porque depende del espacio de
  trabajo y no ve un ajuste hecho desde otra máquina. Descartado también escribir una
  marca en la carga, porque cambia el modelo y cae en la variación que esté grabando.
- **En «Caso base» las variaciones del operador no se tocan.** Descartado: desactivarlas
  para dejar la red «tal como vino», porque la regla es no tocar nada del operador.
- **«Con proyecto» solo activa las variaciones del operador, nunca apaga.** Lo pide la
  spec en «Fuera de alcance».
- **Manda el escenario de operación** (usuario, 2026-10-14). Para eso existen los casos
  de estudio: al activar un caso se activan su escenario y sus variaciones. Cuando una
  carga tiene su potencia en el escenario y en una o varias etapas, vale la del
  escenario. Toda acción termina dejando cada caso con su propio escenario activo
  (011:RF-46). El ajuste, que apaga el escenario mientras cuadra (006:RF-9), lo vuelve a
  activar en su `finally` también si falla o se cancela. Descartado: confiar en el orden
  de las etapas, que el manual no define para etapas de la misma fecha (16.5).

## Comprobación contra la constitución

- P13 universal: los nombres de los casos vienen de `NOMBRES`, y ningún alimentador ni
  SED está fijo en el código ni en las pruebas.
- Escala: `objetos_de_variacion` e `indice_de_cargas_nuevas` recorren las variaciones una
  vez por trabajo, no por carga ni por alimentador. Una prueba sorteada con varios
  alimentadores comprueba que se llama una sola vez.
- Determinismo: los grupos se ordenan por nombre, como ya hace `clasificar()`.
- Datos reales: no se leen ficheros de `referencia/` en código nuevo.
- Reconstruir, no bloquear: ningún RF nuevo devuelve un error. Las duplicadas y los
  cambios manuales son avisos.

## Estrategia de pruebas

- Doble de DIgSILENT (`tests/fake_pf.py`): `IntSstage.GetContents` lista los objetos que
  la etapa cambió. Un ayudante crea una variación del operador con un `ElmTr2`.
- `tests/test_casos_pf.py`: clasificación por contenido, preparar sin base y las
  variaciones activas por caso (014:RF-5, RF-15, RF-16, RF-18, RF-20 a RF-22).
- `tests/test_ajuste_cabecera_guion.py`: una variación del operador sigue activa en
  «Sin proyecto» y en «Con proyecto» tras el ajuste. «Caso base» no recibe escritura.
  Cargas nuevas fuera y luego restauradas, incluso al cancelar. Una carga manual queda
  fija y sin sobrescribir (014:RF-1 a RF-14).
- `tests/test_cargas_pf_guion_007.py`: repetir una inserción no duplica (variación
  inactiva, red, dos variaciones) y avisa de las diferencias de potencia y punto
  (014:RF-19, RF-21 a RF-28).
- `tests/test_native_project_gate.py` o `test_powerfactory_binding.py`: una modificación
  manual da aviso y no bloquea (014:RF-17).
- Número de alimentadores sorteado con `IGEA_SCALE_SEED`, como en las pruebas actuales.
- Prueba en DIgSILENT con CA101 (T9): el ajuste deja `_3` activa en «Sin proyecto» y
  «Con proyecto», y repetir una inserción no crea cargas duplicadas.

## Riesgos

- **Orden de etapas de la misma fecha.** Con `_3` activa y el ajuste nuevo activo, las
  dos tienen `ElmLod` en la misma fecha (`iStudyTime` del caso), y el manual no dice
  cuál manda (16.5). La decisión es que mande el escenario de operación. T5 comprueba que
  cada caso termina con su escenario activo, y T9 mide en DIgSILENT la cabecera con las
  dos variaciones activas.
- **`crear_variacion` con variaciones del operador activas.** Hoy puede desactivarlas un
  momento para conseguir la etapa que graba y luego las reactiva. Hay que comprobar que
  siempre las reactiva, también si falla.
- **Coste de leer etapas** en proyectos con cientos de variaciones: una lectura por
  trabajo, medida en T9.
