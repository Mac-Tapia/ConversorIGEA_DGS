# Plan — Spec 028

## Módulos

- `src/igea_dgs/escaneo.py` (RF-3, RF-4, RF-5, RF-7, RF-11, RF-12): reglas puras, sin
  DIgSILENT. `origen_de(nombre, variacion)` con los prefijos propios del conversor
  (`Central_`, `BC_CAL_`, `Obra_`, cargas nuevas), `resumen` del informe y
  `nodo_de_central(escaneo, alimentador)`: la barra del único generador en servicio del
  alimentador (el del operador antes que el del conversor). Se prueba con datos sorteados.
- `tools/escanear_alimentador_pf.py` (RF-1, RF-2, RF-4 a RF-6, RF-8): con `pf_arnes`, activa
  el proyecto y el caso «Sin proyecto», corre un flujo para que los `ElmFeeder` den sus
  objetos y lee generadores (`Alimentadores.objetos`), bancos (`bancos_instalados`),
  variaciones (`IntScheme` de la carpeta de variaciones) y cambios de carga
  (`cambios_manuales` con la última calibración que manda la web). Un alimentador que falla
  sale con su error. No escribe nada.
- `src/igea_dgs/web/services.py` y `app.py` (RF-9, RF-10): `escanear_alimentadores`, trabajo
  del carril `powerfactory` con `_guion_pf`; el resultado se guarda en el espacio
  (`ws.escaneo`) y `ajuste_plan` completa con él la barra de las centrales sin `nodo` (RF-12).
  Ruta `POST /api/workspaces/{wid}/pf/escanear`.
- `frontend/src/components/DemandaMedida.tsx` (RF-9 a RF-11): botón «Escanear en DIgSILENT»
  junto a la tabla de medidores, tabla del escaneo por alimentador y central declarada con la
  barra del generador encontrado.
- `tools/ajuste_cabecera_pf.py` (RF-13, RF-14): `central_en_sin_proyecto` busca primero un
  generador en servicio del operador en la barra de la central; `_con_bancos_que_faltan` no
  pide bancos a un alimentador que ya tiene `BC_CAL_`.
- `tools/sistema_web.py` (RF-15): escanea antes de calibrar y rellena el `nodo` de la central
  del perfil con `nodo_de_central`.

## Decisiones

- El origen se decide por los prefijos del conversor, no por fechas ni por el autor que guarda
  DIgSILENT: la API no da el autor de cada objeto y los prefijos ya son la convención de las
  specs 011, 016, 021 y 007. Descartado: comparar con el DGS (lo hace la 015 y es lento).
- Con un generador del operador en la barra, se le escribe la P y Q medidas en vez de crear otro:
  dos generadores en la misma barra inyectarían dos veces. Descartado: dejar su P y Q, porque la
  cabecera medida es la demanda menos la generación de ese instante.

## Pruebas

- `tests/test_escaneo.py`: reglas de `escaneo.py` con nombres sorteados (028:RF-3 a RF-7,
  RF-11, RF-12); el guion contra `tests/fake_pf.py` (RF-1, RF-2, RF-8); la ruta de la web
  (RF-9, RF-10) y el front compilado con el botón (RF-9, RF-11).
- `tests/test_ajuste_cabecera_pf.py` o la prueba de centrales existente para RF-13 y RF-14.
- En DIgSILENT: escanear Nasca tras poner el usuario la central de NA205 a mano.

## Continuación RF-24 y RF-25

- `sistema_web.py --red COD [COD ...] [--grupo NOMBRE]`: convierte e importa un alimentador
  o una red unida; con el proyecto registrado, recalibra sin reconvertir. Usa máximas
  individuales, comprueba pertenencia y resultados de cada etapa antes del plan.
- `sistema_del_proyecto(..., todos=True)` permite consultar los alimentadores de proyectos
  individuales y unidos sin cambiar el alcance por defecto de los consumidores por sistema.
- `recalibrar_datos` y `recalibrar_sistema` conservan los alimentadores del grupo registrado;
  el botón los muestra y el subproceso recibe `--red` y `--grupo`.
- `research.md` contiene el sustento académico y distingue escenarios de máximas propias
  de una máxima coincidente. La aceptación nativa y los informes permanecen en T9.
