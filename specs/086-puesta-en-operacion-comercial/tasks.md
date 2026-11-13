# Tareas — Spec 086

## F0 Decidir e integrar

- [x] T1 Registrar las decisiones D1 a D7 del usuario, con fecha, en `spec.md`.
  Hecho cuando: D1 a D5 están respondidas; D6 y D7 tienen responsable.
  Hecho el 2026-11-07: D1 a D5 según la recomendación; D6, el usuario da los datos; D7 no se considera, cada usuario con sus licencias.
- [x] T2 Integrar `feat/decisiones-usuario`, `entrega/042-doble-terna`, `entrega/083-calibracion` y lo que falte de `fix/acopladores-con-fases`, con una ventana acordada con las otras sesiones. (RF-45)
  Hecho cuando: `git cherry` no da trabajo pendiente en ellas, y suite completa con las nueve variables y `CSG_MCP_PYTHON`, sin omitidas ni fallos, sobre esa revisión.
  Evidencia: suite sobre ab8efa9c, 6 753 aprobadas, 0 omitidas, 0 caídas y 2 fallos de pruebas que leían un texto ya cambiado; corregidos en c7c04175 y c79013c2, que solo tocan esas pruebas, y pasan aparte. La suite limpia de cierre es la T31. `entrega/083-calibracion` queda sustituida por la 042; `fix/*`, ya presentes; 042:RF-48 y la 087 esperan prueba en DIgSILENT.
- [x] T3 Pasar a `main`, `pip install -e .`, compilar, reiniciar la web y aplicar el modelo provisional. (RF-45)
  Hecho cuando: la web muestra el aviso provisional con sus cifras y `test_entry_points_instalados_coinciden_con_pyproject` pasa.
  Evidencia: `main` en c79013c2; navegador real en el 8765, con el aviso «examen 0,964 de 0,98 y F1 0,918 de 0,95 […] sellada 0,860; sintéticas 0,829; se cuela 0,0 %».
- [x] T4 Aclarar `factor_seguridad_set` en `config/perfiles/electro_dunas.json:64` (1,0 frente a un comentario de 1,25) y corregir lo que confirme el usuario. (RF-45, RF-51)
  Hecho cuando: el perfil coincide con su comentario.
  Evidencia: `tests/test_set_nueva.py::test_el_factor_de_la_set_depende_de_si_se_cuenta_la_tasa`; 1,25 sin tasa y 1,0 con ella, como decidió el usuario.
- [x] T5 Cabecera compartida: proponer solución en vez de quedarse sin obra (decidido por el usuario, 2026-11-04). La implementa la sesión de la 042 en `entrega/042-nivel`, sobre 042:RF-53.
  Hecho cuando: el caso produce una solución con su aviso y prueba, medida en DIgSILENT.
  Evidencia (2026-11-06): en `main` como elevador dedicado, 042:RF-61 y RF-62 (`tests/test_escalera_optima.py`, `tests/test_obras_pf_guion_016.py`); la medida en DIgSILENT es la 042 T42.

- [x] T37 El informe separa lo que causa la carga del déficit que ya existía. (RF-48, RF-49, RF-50) (`v1/deficit`)
  Hecho cuando: con una barra baja que no empeora, el informe la lista como déficit previo con su tensión y barra, y nunca dice «en norma» sin ese matiz.
  Evidencia: pruebas con dobles, sin DIgSILENT, en `tests/test_deficit_previo.py`, `tests/test_informe_docx.py`, `tests/test_informe_corrida.py`, `tests/test_casos_por_anio.py` y `tests/test_obras_pf_guion.py`. La confirmación en DIgSILENT queda en las corridas de la F6, y verlo en el navegador real, sin hacer.

- [x] T39 El factor 1,25 en el elevador y en el regulador, cuando no cuentan la tasa de crecimiento. Lo implementa la sesión de la 042 en su rama. (RF-53)
  Hecho cuando: prueba de cada uno con y sin dato en el perfil; el dimensionado se ve en el informe.
  Evidencia (2026-11-06): 042:RF-70 y RF-71 en `tests/test_escalera_optima.py` (con y sin factor, y con perfil parcial); la potencia y la corriente elegidas van en el nombre de la variante que lleva el informe.
- [x] T38 Obra para el déficit previo, con su costo aparte, con o sin obra para la carga. La implementa la sesión de la 042 en su rama. (RF-52)
  Hecho cuando: «ya cumple» no se queda sin obra si hay una barra previa baja; prueba con doble y medida en DIgSILENT sobre SI112; el informe separa los dos costos.
  Evidencia (2026-11-06): 042:RF-64 y RF-65 con dobles (`tests/test_informe_factibilidad_un_paso.py`, `tests/test_valle.py`); la medida sobre SI112 es la 042 T44 [DIgSILENT].

## F1 Datos que no se pierden (`v1/datos`)

- [x] T6 Escritura duradera, espacio dañado y rutas conservadas. (RF-1, RF-2, RF-3)
  Hecho cuando: pruebas de JSON truncado y de unidad ausente: el espacio se ve, se puede restaurar y ninguna ruta se pierde al guardar.
  Por la API; el botón y el aviso en la interfaz siguen en T35.
- [x] T7 Migraciones, rutas relativas e identidad estable. (RF-4, RF-5, RF-6, RF-7, RF-8)
  Hecho cuando: todos los espacios actuales migran sobre una copia sin perder nada; mover la carpeta conserva los espacios; escribir en otra unidad funciona.
  Evidencia: los 24 de `output/web` (2026-11-04), 0 fallos, 0 diferencias al expandir, 24 copias `workspace.v2.json` idénticas y el origen intacto por sus huellas; los 2 de la raíz de ejecución, igual. Solo se copiaron los JSON: las entradas se ven como no disponibles porque sus ficheros no se copiaron. El espacio abre con las dos raíces (`WorkspaceStore.roots`).
- [x] T8 Trabajos interrumpidos, copia y restauración. (RF-9, RF-10, RF-47)
  Hecho cuando: matar el proceso a media corrida deja el trabajo como interrumpido; restaurar una copia devuelve el mismo estado.
  Por la API y por `tools/copia_datos.py`; verlo en la interfaz sigue en T35. El corte de luz real es la T33.
- [x] T35 Ver en la interfaz lo de T6 y T8: espacio dañado con su botón de restaurar, entradas no disponibles, trabajo interrumpido con su registro y aviso de copia vieja. (RF-2, RF-3, RF-9, RF-47)
  Hecho cuando: los cuatro se ven y funcionan en el navegador real, en claro y oscuro.
  Evidencia: navegador real contra una web propia en el 8792, datos sintéticos, en las dos ediciones. También `avisos_corrida` en informes, y la pestaña abierta tras reiniciar el servidor: `tests/test_edicion_producto.py`, `frontend/test/reconexion.test.mjs`. El trabajo interrumpido de esa prueba se sembró en su diario; matar el proceso de verdad es la T8.

## F2 Renombrar

- [ ] T9 [DIgSILENT] Renombrar la carpeta a `ConverterSmartGrid`, con todo parado y con ensayo previo sobre una copia. (058 T6)
  Pasos, cada uno con su comprobación y vuelta atrás: (1) comprobar que no hay procesos en esa ruta; (2) foto: `pip freeze`, `git worktree list --porcelain`, estado de cada worktree y el `.lnk`; (3) copiar `workspace.json` y `conversiones.json` fuera, y fijar la identidad con `tools/copia_datos.py identidad --fijar`, porque sin ella renombrar cambia la raíz de datos; (4) `Rename-Item`, sin forzar; (5) comprobar que los espacios migran con la T7, sin reescribir evidencia histórica; con la identidad fijada, runtime y caché no se renombran; (6) recrear las junctions; (7) `git worktree repair` con todas las rutas a la vez; (8) **reparar `.venv` en sitio**: `-m venv .venv` y `pip install -e . --no-deps`, sin rehacerlo, porque torch no está en `requirements`; (9) crear `ConverterSmartGrid.lnk`, y retirar el viejo solo cuando funcione; (10) comprobar los espacios antes de que guarden nada, y un vínculo de DIgSILENT; (11) copiar la memoria de Claude y actualizar `ACTIVE.md` y `CLAUDE.md`; (12) suite completa. Vuelta atrás general: parar, restaurar las copias, deshacer los pasos 7 y 4. GitHub y limpieza de identidades antiguas, aparte y con orden del usuario.
  Hecho cuando: la web abre con los mismos espacios que la foto, `torch.cuda.is_available()` es verdadero y la suite pasa sin omitidas.

## F3 Veracidad, seguridad y producto

- [x] T10 Reproducir y corregir el informe con flujo de otra corrida, y el que elige el estudio de otro alimentador. (RF-11, RF-12) (`v1/informes`)
  Hecho cuando: con «Con proyecto» fallido, cancelado o agotado, el informe no usa datos viejos sin decirlo; prueba con doble.
  Evidencia: `tests/test_informe_corrida.py`, con doble; en DIgSILENT, en la R1 (T24).
- [x] T11 «Caso base» al retomar y su huella. (RF-13, RF-14) (`v1/informes`)
  Hecho cuando: retomar verifica; el guion escribe `caso_base_huella` y la guarda de 081 actúa.
  Evidencia: `tests/test_sistema_web.py` y `tests/test_huella_caso_base.py`, con `fake_pf`. La huella real sigue abierta en 081 T12 (R3, T26).
- [x] T12 Edición de producto: sin suite nocturna, sin entrenar, oculto lo que no se vende. (RF-15, RF-16) (`v1/producto`)
  Hecho cuando: pruebas en las dos ediciones, y comprobación en el navegador real.
  Evidencia: `tests/test_edicion_producto.py`; navegador real en el 8792 en las dos ediciones, con las rutas negadas también desde la página. La lista de lo que no se empaqueta es la T19.
- [x] T13 Host, Origin, token y escucha. (RF-17, RF-18, RF-19, RF-20) (`v1/seguridad`)
  Hecho cuando: pruebas negativas por cada una, también en WebSocket; la web sigue funcionando en el navegador real.
  Evidencia: `tests/test_seguridad_web.py`; navegador real contra una web propia en el 8791, con una página de otro origen rechazada en POST, GET y WebSocket.
- [x] T14 Leaflet propio, política de contenido y sin salida a la red por defecto. (RF-21, RF-22) (`v1/seguridad`)
  Hecho cuando: con lo externo cortado en el navegador, cargar, convertir, descargar y abrir el mapa funcionan; una prueba recorre las salidas conocidas.
  Evidencia: `tests/test_seguridad_web.py`; navegador real en el 8791, sin conexiones externas del servidor. El flujo completo con la red cortada de verdad es la T36.
- [ ] T36 [DIgSILENT] El flujo completo con la red del equipo cortada de verdad: importar, calibrar e informe. (RF-22)
  Hecho cuando: sin red, el flujo termina y cada salida apagada lo dice.
- [x] T15 Tareas por efecto, guiones con confirmación, reintentos e independencia de GPU. (RF-23, RF-24, RF-25, RF-26, RF-27) (`v1/producto`)
  Hecho cuando: una prueba exige que cada tarea declare su efecto; sin CUDA, el trabajo sigue con aviso.
  Evidencia: `tests/test_edicion_producto.py`; el diálogo del guion, en el navegador, con el proyecto simulado. En DIgSILENT, en las corridas de la F6.

## F4 Universal (`v1/universal`)

- [x] T16 Moneda, web sin casos y valores por defecto. (RF-28, RF-29, RF-35)
  Hecho cuando: una prueba recorre el núcleo y la web con la lista de términos, y no halla ninguno.
  Fuera de los comentarios, que D5 neutraliza al empaquetar y T19 sigue contando. Evidencia: `tests/test_entrega_universal.py`; navegador real en el 8793, con el perfil ficticio.
- [x] T17 Esquema, `validar-perfil` y `docs/PERFIL_EMPRESA.md`. (RF-30)
  Hecho cuando: un perfil incompleto dice qué falta y qué función afecta.
  Evidencia: `tests/test_entrega_universal.py`. La orden solo lee: nada de lo que falta bloquea más que antes.
- [x] T18 Plantillas neutras, perfil plantilla y perfil ficticio. (RF-31, RF-32)
  Hecho cuando: con el perfil ficticio y sin modelos de empresa se convierte y se genera un informe.
  Sin DIgSILENT: el informe sale de datos de prueba, con la carpeta de perfiles como en un paquete. Con DIgSILENT y otra empresa es la T32.
- [x] T19 Lista de lo que entra en el paquete, términos prohibidos y pesos. (RF-33, RF-34)
  Hecho cuando: un candidato con un término o peso ajeno se rechaza; comentarios según D5.
  `config/entrega.json` es la lista que leerá la T21. Neutralizar los comentarios es un paso de empaquetar: hoy se cuentan y solo rechazan en un candidato, no en el repositorio.

## F5 Instalador y soporte (`v1/instalador`)

- [x] T20 Trasladar a datos del paquete lo que se lee del checkout. (RF-36)
  Hecho cuando: el programa corre desde un wheel fuera del repositorio y las líneas base siguen iguales.
  Evidencia: `tests/test_instalacion_programa.py`, que construye la rueda y compara sus DGS con los del árbol en las dos disposiciones y con `workers` 1 y 2. Con los ocho casos de `ExportSpec` de la base `c79013c2`, los DGS desde el programa instalado salen idénticos byte a byte. Las líneas base con datos reales las corre el integrador en su suite completa (T31).
- [x] T21 Candidato sin internet, núcleo aparte del complemento de IA, datos aparte y actualización con vuelta atrás, probados fuera del repositorio. (RF-36, RF-37, RF-38, RF-39)
  Hecho cuando: instalar, actualizar y volver atrás en una carpeta con el Python embebido, sin `PATH` y sin Node conserva los datos; `comprobar_entrega` acepta el candidato.
  Evidencia: `tests/test_instalacion_programa.py`, y ensayo real del 2026-11-04 con el candidato, en una carpeta fuera del repositorio, con Python 3.12.10 embebido y `PATH` solo con `System32`: instaló en 150 s; convirtió por la web instalada; rechazó un candidato alterado sin cambiar nada; actualizó de rc1 a rc2 y volvió a rc1, con los mismos datos por huella (solo se añade el apunte de la copia) y lo posterior apartado. Las librerías salieron de `--no-index`; la red de la máquina no se cortó. No es una máquina limpia, no se compiló el `.iss` (no hay Inno Setup aquí), DIgSILENT no se tocó y el complemento de IA solo está declarado: todo eso es la T40.
- [x] T22 `doctor`, registro rotativo, paquete de soporte y versión única. (RF-40, RF-41, RF-42, RF-43)
  Hecho cuando: quitar cada requisito opcional dice qué función afecta; el paquete de soporte no lleva datos del cliente.
  Evidencia: `tests/test_instalacion_programa.py`, y en el navegador real, contra el programa instalado, la pantalla del doctor con sus datos, y sus colores calculados en claro y oscuro; la captura de imagen falló en esa máquina, así que el aspecto no se ha mirado. `vnr_etl` conserva su propia versión de módulo interno, que la web no enseña.
- [x] T23 Manuales, hoja de seguridad, `THIRD_PARTY_NOTICES`, SBOM, `pip-audit`; corregir README y `MANUAL_COMANDOS` (órdenes rotas en `:629,676`). (RF-44)
  Hecho cuando: los documentos existen sin nombres de empresa y sus órdenes responden; auditoría sin vulnerabilidades graves.
  Evidencia: `tests/test_instalacion_programa.py`; `pip-audit` del lock el 2026-11-04, sin avisos, tras subir Pillow, pypdf y certifi (`docs/regresiones/2026-11-04-versiones-con-vulnerabilidades-en-el-entorno.md`). Las licencias quedan como inventario para la asesoría (D7), sin conclusiones. La persona ajena es la T41.
- [ ] T40 [DIgSILENT] Con el `setup.exe`, en este equipo y sin nada de desarrollo en el entorno: instalar, actualizar y volver atrás, y una importación real en DIgSILENT con el Python del programa. Construir y probar el complemento de IA. (RF-36, RF-37, RF-38, RF-39)
  Hecho cuando: el instalador conserva los datos, una importación real termina con el Python del programa, y el complemento instala con huella y carga sus modelos.
  Hecho (2026-11-04): compilado con Inno Setup 6.7.3 (129 MB, 17 s), instalado con `PATH` solo de System32 (158 s, 519 MB), doctor «listo para trabajar» en edición de producto, y `import powerfactory` con el Python del programa, sin abrir el motor. Falta lo demás: la sesión de la 042 ocupa DIgSILENT.
  Avance parcial (2026-11-08, P01/P22): `tests/test_complemento_integral.py`
  cubre cierre offline de todos los extras de ejecución y requisitos opcionales,
  conservando núcleo separado y excluyendo herramientas de desarrollo ajenas al
  cierre. Verifica huellas/procedencias, ABI, Python, licencias, restricciones,
  markers/extras, rechazo de URLs transitivas y ruedas extra. pip vuelve a
  resolver las ruedas pequeñas sin red ni instalación. El paquete de inferencia
  previo no representa las capacidades integrales. Sigue pendiente ensayar la
  entrega final congelada y su instalación/relectura nativa; no se cierra T40.
  Corrección de revisión P22 (2026-11-08): una rueda compartida debe tener SHA autorizado por
  el lock previo del núcleo (también en inferencia y con varios hashes permitidos); los extras activos
  se validan contra Provides-Extra según PEP 685. Una sola validación de textos/rutas bloquea alias
  Windows/ADS/colisiones y se relee la copia de la entrega antes de publicarla. La selección real
  sigue siendo de 238 ruedas y pip dry-run coincide exactamente, con 57 hashes compartidos autorizados,
  sin copiar ruedas ni instalar. Pruebas/negativas: `tests/test_complemento_integral.py`; evidencia externa
  `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/correccion_revision_p22_20261108/`.
  No se construyó todavía el paquete final integrado ni se acreditan DLL/GPU, modelos o instalación nativa.
  Avance de cierre (2026-11-08): complemento integral rc6 construido una sola vez,
  238 ruedas y ZIP SHA256 0cdd6d9f2ddcadd38e6d64c778eb5ea6ef444b1cfa9d2457b066bc7a446be3ca,
  carpeta/ZIP verificados independientemente. P04 captura única/publicación y
  procedencia CAPEX integradas con revisión cruzada; 92 pruebas combinadas correctas.
  QA tiene AppId/ruta/accesos propios. El rechazo de una versión ya existente
  conserva ahora su carpeta: 109 pruebas de instalación/QA correctas sin omitidas.
  Esto prepara el núcleo/setup congelado y su ensayo real; no cierra T40,
  no acredita modelos, importación nativa final ni la red físicamente cortada.
  Evidencias externas: p25_fuentes_capex_integracion_20261108,
  p25_instalador_integrado_20261108 y p22_construccion_integral_rc6_20261108.
- [ ] T41 Una persona ajena al proyecto instala y convierte siguiendo el manual. (RF-44)
  Hecho cuando: lo consigue sin ayuda, o lo que no entendió queda corregido en el manual.

## F6 Corridas reales sobre el candidato congelado

Cada corrida: `tools/sistema_web.py` y el navegador, en serie, con proyectos de prueba nuevos. `D=D:/BaseDatosElectroDunas/referencia_retirada_20261102`.

- T24. Retirada el 2026-11-08 por orden del usuario, sin hacer: R1 con CA101 + PE104 ya se hizo; sus tareas siguen cada una por su cuenta. Era: [DIgSILENT] R1, CA101 + CHN102, TXT (el usuario la cambió de CA101 + PE104 el 2026-11-08), sobre el proyecto `20261105-124711_CSG_TXT_CA101_CHN102`, sin reconvertir: `--red CA101 CHN102 --grupo CA101_CHN102 --demanda-dir $D --periodo 2026-07`, luego en el navegador calibración, cargas, obras, transferencia e informes. (RF-45)
- [x] T25 [DIgSILENT] R2, SI213 y PN107, MDB, uno por vez, con cargas por el navegador. (RF-45)
  Cierra: 007 T11, 016 T18, 028 T11, 081 T20. Hecho cuando: variación por carga, barra más cercana, base activa al terminar.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T26 [DIgSILENT] R3, Pisco y una SET, TXT: `--zonal Pisco --demanda-dir $D --periodo 2026-07 --reconvertir`, luego `--set <SET>`. (RF-45)
  Cierra: 028 T15, 083 T3, 081 T10 a T13, 078 T6, 027 T22 (borrador). Hecho cuando: instante en 60 kV, LT y centrales; huella igual antes y después; estado veraz; los alimentadores sin medidor, con su motivo.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T27 [DIgSILENT] R4, NA203 + NA205, TXT, proyecto nuevo, con los dos criterios de fijas, cargas y obras. (RF-45)
  Cierra: 039 T4, 042 T6, 052 T4, 084 T8, 017 T14, 073 T8, 073 T10. Hecho cuando: NA203 con «máximo del mes» da 7 707,5 kW y 3 725,5 kvar (039); SET en 0,94–1,06 pu y fuera del trazado; oráculo frente a DIgSILENT; valle.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T28 [DIgSILENT] R5, NJA202 y R205, VNR-GIS de Electro Oriente. (RF-45, RF-46)
  Cierra: 051 T3, 055 T2, 056 T3, 005 T12, 081 T16. Hecho cuando: cabecera dentro del 1 %; sistemas y SET; vocabulario y carpeta de la empresa. R205 frente a 0205 sin suponer alias.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T29 Navegador: 067 T8, 077 T7, 073 T10, y escritorio con pantalla estrecha. (RF-45)
  Hecho cuando: todo se ve funcionar en el navegador real, en claro y oscuro.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T30 [DIgSILENT] R6, solo si el asistente se vende como beta: un alimentador, una SET y una carga por órdenes escritas. (RF-45)
  Cierra: 070 T9, 070 T10, 067 T9, 026 T12, 078 T7. Hecho cuando: los informes salen de las órdenes, con confirmación.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).

No hacen falta para la 1.0: 025 T21 (PA217 vetado; reformular según D6), 027 T14 y T29 a T31, 028 T6, 044 T4, 045 T4, 048 T4, 049 T4, 070 T11, 075 T6, 079 T7, 081 T14. 065 T12 pasa a ser el conjunto R1 a R5.

## F7 Aceptación y v1.0

- [x] T42 Sustituir un fichero de estado reintenta un bloqueo pasajero de Windows. (RF-54)
      Hecho cuando: `tests/test_datos_duraderos.py` en verde.
- [x] T43 El diagnóstico avisa un perfil sin fichas de transformadores o sin bancos por tensión. (RF-55)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-55) en verde.
- [x] T44 El perfil de la empresa y su estructura se cargan desde la web («Perfil de la empresa»), validados antes de guardar. (RF-56)
      Hecho cuando: `tests/test_web_api.py` (086:RF-56) en verde y el panel compila.
- [x] T45 El instalador deja en su registro y en su aviso el motivo por el que `instalar_candidato.py` no terminó. (RF-57)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-57) en verde.
- [x] T46 El instalador no reutiliza la carpeta de una instalación anterior que está en la temporal o ya no tiene el programa. (RF-58)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-58) en verde y el `.iss` compila.
- [x] T47 Tras «Cargar perfil», la web vuelve a leer el estado del servidor y el CRS de origen enseña el del perfil. (RF-59)
      Hecho cuando: `frontend/test/relecturaServidor.test.mjs` (086:RF-59) en verde.
- [x] T48 «DIgSILENT» bien escrito en la web, el registro y el código. (RF-60)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-60) en verde.
- [x] T49 Las contracciones «al» y «del» en los avisos de las salidas a la red. (RF-61)
      Hecho cuando: `tests/test_seguridad_web.py` (086:RF-61) en verde.
- [x] T50 «Recalibrar «Sin proyecto»» vuelve a leer sus datos del servidor cuando cambian los libros en «2.1». (RF-62)
      Hecho cuando: `frontend/test/relecturaServidor.test.mjs` (086:RF-62) en verde.
- [x] T51 La vista previa con calles y satélite, su selector y su aviso por capa; sin teselas si la salida está apagada. (RF-63, RF-64, RF-65)
      Hecho cuando: `tests/test_seguridad_web.py` (086:RF-63 a RF-65) en verde.
- [x] T52 La salida se decide por variable, equipo y edición, y la API la lee y cambia (`GET /api/salidas`, `POST /api/salidas/teselas`). (RF-66, RF-68, RF-69)
      Hecho cuando: `tests/test_seguridad_web.py` (086:RF-66) y `tests/test_web_api.py` (086:RF-68, RF-69) en verde.
- [x] T53 Interruptor «Fondo de mapa» en «Opciones de conversión», recordado en el equipo y bloqueado si lo fija la variable. (RF-67, RF-68)
      Hecho cuando: `frontend/test/fondoMapa.test.mjs` (086:RF-67, RF-68) y `tests/test_web_api.py` (086:RF-67) en verde.
- [x] T54 Tabla de cada `kind` del servidor a su paso, en `frontend/src/shared/pasoDeTrabajo.ts`, y los avisos de trabajo en su paso, con «Reintentar» en los repetibles. (RF-70, RF-71, RF-72)
      Hecho cuando: `frontend/test/avisosEnSuPaso.test.mjs` (086:RF-70 a RF-72) en verde.
- [x] T55 Un aviso resuelto por un trabajo posterior del mismo tipo y ámbito no se muestra. (RF-73)
      Hecho cuando: `frontend/test/avisosEnSuPaso.test.mjs` (086:RF-73) en verde.
- [x] T56 Arriba solo los avisos generales, en una línea; la pestaña cuenta los avisos de sus pasos. (RF-74, RF-75)
      Hecho cuando: `frontend/test/avisosEnSuPaso.test.mjs` (086:RF-74, RF-75) en verde.
- [x] T57 «Con proyecto» sin cargas nuevas: obras solo donde el estado actual viola límites, desde la web. (RF-76, RF-77)
      Hecho cuando: `tests/test_con_proyecto_sin_cargas.py` (086:RF-76) y `frontend/test/obrasEstadoActual.test.mjs`
      (086:RF-77) en verde; la corrida real va en la T32.
- [x] T58 La copia guarda cada fichero físico una vez, con todos sus nombres en el manifiesto 3, y restaurar los recrea
      como enlaces duros o como copias; el manifiesto 1 y 2 se sigue leyendo. (RF-78, RF-79, RF-80)
      Hecho cuando: `tests/test_copia_datos.py` (086:RF-78 a RF-80) en verde.
- [x] T59 Reintentos ante un destino que bloquea, cálculo de lo que ocupa frente al libre antes de copiar, y nada con
      aspecto de buena si se cancela; orden `calcular` y `--programa`. (RF-81, RF-82, RF-83, RF-84)
      Hecho cuando: `tests/test_copia_datos.py` (086:RF-81 a RF-84) en verde.
      Evidencia: copia real del 2026-11-12 de los datos del árbol principal a Google Drive
      (`G:/Mi unidad/ConverterSmartGrid/copias_de_datos/csg-copia-20261112T184236-40574e83`, manifiesto 3): 8 989
      ficheros físicos con 11 933 nombres, 19,8 GB guardados de 83,0 GB lógicos, 0 errores; `tools/copia_datos.py
      verificar --copia …` releyó cada huella el 2026-11-12: `"ok": true`, 0 faltan, 0 distintos, código 0 (7 min 27 s).
      Esa copia es anterior a la marca `fisico` de RF-80: al restaurarla, sus ficheros de igual contenido vuelven
      enlazados; las copias nuevas ya los separan.
- [x] T60 «Hacer una copia ahora» en el aviso general, con la carpeta recordada en `config/copia_datos.json`, y la copia
      como trabajo `copia_datos` con progreso y cancelación. (RF-85, RF-86)
      Hecho cuando: `tests/test_copia_datos.py` (086:RF-85, RF-86) y `frontend/test/avisosEnSuPaso.test.mjs` (086:RF-85) en verde.
- [x] T61 La calibración reutiliza la `Fichas_`/`SED_NTP_` del conversor que trae una copia del proyecto, reconocida por su
      marca y no por el prefijo (una del operador no se toca; con varias se avisa), y la consigna de la fuente
      llega también a «Cargas nuevas». (RF-87, RF-88)
      Hecho cuando: `tests/test_variaciones_por_marca.py` (086:RF-87, RF-88) y `tests/test_ajuste_proyecto_guion.py`
      (086:RF-88) en verde; la corrida en DIgSILENT sobre una copia de PA217 va en la T32.
- [x] T70 Los manuales y las notas de la publicación en «documentos/» del candidato y en `{app}\documentos`, y el menú Inicio
      abre el manual de instalación; `instalar_candidato.py` los prepara al lado y solo los publica cuando cambia el puntero,
      y si falla deja los anteriores. (RF-89, RF-90, RF-91, RF-97)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-89 a RF-91, RF-97) en verde y el `.iss` compila con ISCC sobre
      un candidato de prueba. Verlo instalado es de la T40, con el rc6.
- [x] T71 La versión solo en `__version__`: pyproject la lee, el candidato la pone en su rueda y el `.iss` la saca de su
      nombre, sin `/DVersion`; «Acerca de» enseña el apartado de esa versión. (RF-92, RF-93)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-92, RF-93) en verde, y ISCC da la versión de la rueda y
      rechaza `/DVersion`. La etiqueta `v1.0.0` es la T34.
- [x] T72 Instalar sobre otra versión registra la anterior, también sobre un rc sin `anterior.txt` o con el puntero roto, y el
      instalador anota a cuál se puede volver; volver atrás cambia documentos y punteros juntos, una sola vez, y un fallo a
      mitad lo deja todo como estaba; reinstalar la versión apartada la vuelve a poner en uso. (RF-94, RF-95, RF-96, RF-98,
      RF-99, RF-100, RF-101, RF-102)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-94 a RF-96, RF-98 a RF-102) en verde con versiones de prueba.
      Instalar el rc6 sobre el rc5 de este equipo y volver es de la T40.
- [x] T73 El cambio de versión aguanta sus propios fallos: cada paso del deshacer va por su cuenta y el error lleva el
      original con los pasos que no se pudieron deshacer; renombrar una carpeta o un puntero en uso se reintenta con espera creciente y,
      si sigue, pide cerrar los documentos; las carpetas de paso que no se borran se avisan en el registro. (RF-103, RF-104,
      RF-105)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-103 a RF-105) en verde, con rojo previo, y las pruebas de
      RF-97 a RF-102 siguen en verde. Evidencia: `D:/csg/F2/rojo_*.log` y `D:/csg/F2/verde_*.log`.
- [x] T31 Suite completa sin omitidas sobre el candidato, con líneas base y determinismo. (058 T5, 025 T22, 065 T13) (RF-46)
  Hecho cuando: cero fallos, cero omitidas.
  Evidencia: suite completa del 2026-11-12 sobre 6306cc65 con las doce variables de datos reales y `-rs`: 8 682 aprobadas, 0 fallidas, 0 omitidas (59 min; `.git/puerta_calidad/6306cc65….json`). Las líneas base y el determinismo (`workers` 1 y >1) están dentro de esa suite.
- [ ] T32 [DIgSILENT] Instalación con el `setup.exe` en este equipo, con su DIgSILENT, y corrida de otra empresa de punta a punta hasta el informe. (RF-46)
  Hecho cuando: sin tocar el código, solo su perfil, sale un informe que un ingeniero da por bueno.
- [ ] T33 [DIgSILENT] Ensayo de corte a media calibración y a media importación, matando los procesos con las demás sesiones paradas. (RF-46)
  Hecho cuando: ningún espacio se pierde, el trabajo se ve interrumpido y se retoma sin trabajo repetido ni datos mezclados.
- [ ] T34 Repositorio de producto, licencia y etiqueta `v1.0.0` con sus notas; la asesoría legal no se considera (D7, 2026-11-07): cada usuario con sus licencias. (D3, D7)
  Hecho cuando: el usuario da la orden de publicar.

## Después de la 1.0

002 T7 a T12; 043 T9; 045 T3; 047 T4, T7, T8; 048; 049 (cortocircuito y protecciones, lo primero que pedirá un cliente); 050 T1b a T5b; 068 T7, 069 T7, 085 T6 (campaña de GPU); 071 T5; 072 T3, T9, T11; 074; 027 T11, T26.
## Nota correctiva: procedencia portable (2026-11-08)

RF-39/RF-44: el constructor publica identidad/SHA de recibos externos, preserva
su JSON original y verifica sus bytes si se declara un recibo. Solo el descriptor
exportado omite rutas privadas; URL/commit/versión/SHA de rueda no cambian.
Pruebas permanentes en `tests/test_complemento_integral.py`: traslado entre dos
raíces privadas con entorno/cwd distintos y rechazo de mutaciones del recibo.
No se cambian estados de aceptación ni se da por reconstruido/instalado el
complemento de 238 ruedas o el programa final con este correctivo CPU.
