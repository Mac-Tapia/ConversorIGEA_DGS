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
  Hecho cuando: «ya cumple» no se queda sin obra si hay una barra previa baja; prueba con doble y medida en DIgSILENT sobre SI192; el informe separa los dos costos.
  Evidencia (2026-11-06): 042:RF-64 y RF-65 con dobles (`tests/test_informe_factibilidad_un_paso.py`, `tests/test_valle.py`); la medida sobre SI192 es la 042 T44 [DIgSILENT].

## F1 Datos que no se pierden (`v1/datos`)

- [x] T6 Escritura duradera, espacio dañado y rutas conservadas. (RF-1, RF-2, RF-3)
  Hecho cuando: pruebas de JSON truncado y de unidad ausente: el espacio se ve, se puede restaurar y ninguna ruta se pierde al guardar.
  Por la API; el botón y el aviso en la interfaz siguen en T35.
  Ampliación 2026-11-13 (aclaración de RF-3, auditoría c7): subidas validadas en un staging del espacio y publicadas con
  `os.replace`; lo anterior se retira después de asignar; 409 con un trabajo que lee esos libros o PDF.
  Hecho cuando: `tests/test_datos_duraderos.py` (086:RF-3: casillas, paquete VNR-GIS, demanda, pérdidas y PDF) en verde,
  en rojo sobre 048812bb.
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
  Es la misma mudanza que 058 T6, con la misma herramienta: `tools/mudar_carpeta_principal.py` hace los pasos 1, 4, 6, 7,
  8 y 9, y desde el 2026-11-21 (MEJ33 de d8) también la foto de los espacios (paso 2), su respaldo fuera con `--respaldo`
  (paso 3) y la comprobación de que tras mudar están los mismos (paso 10); `tests/test_mudar_carpeta_principal.py`
  (058:RF-6). El acceso nuevo se llama «ConverterSmartGrid (desarrollo)» y no `ConverterSmartGrid.lnk`: el producto
  instalado ya tiene en el menú de inicio un «ConverterSmartGrid», y con el mismo nombre se confundirían. Falta la mudanza
  real, con todo parado (también Antigravity, que no se cierra sin la orden del usuario), en la ventana que el usuario elija.

## F3 Veracidad, seguridad y producto

- [x] T10 Reproducir y corregir el informe con flujo de otra corrida, y el que elige el estudio de otro alimentador. (RF-11, RF-12) (`v1/informes`)
  Hecho cuando: con «Con proyecto» fallido, cancelado o agotado, el informe no usa datos viejos sin decirlo; prueba con doble.
  Evidencia: `tests/test_informe_corrida.py`, con doble; en DIgSILENT, en la R1 (T24).
- [x] T11 «Caso base» al retomar y su huella. (RF-13, RF-14) (`v1/informes`)
  Hecho cuando: retomar verifica; el guion escribe `caso_base_huella` y la guarda de 081 actúa.
  Evidencia: `tests/test_sistema_web.py` y `tests/test_huella_caso_base.py`, con `fake_pf`. La huella real sigue abierta en 081 T12 (R3, T26).
- [x] T12 Edición de producto: todo activo, con las betas marcadas y desactivables. (RF-15, RF-16) (`v1/producto`)
  Hecho cuando: pruebas en las dos ediciones, y comprobación en el navegador real.
  Evidencia: `tests/test_edicion_producto.py`; navegador real en el 8792 en las dos ediciones, con las rutas negadas también desde la página. La lista de lo que no se empaqueta es la T19.
  Cambio del 2026-11-13 (usuario: «nada debería estar apagado ni bloqueado»): la edición de producto ya no niega rutas ni tareas
  (`edicion.py` sin `_RUTAS_FUERA_DE_ALCANCE`, `TAREAS_FUERA_DE_ALCANCE` ni `MENSAJE_FUERA_DE_ALCANCE`), ni apaga la vigilancia, las
  mejoras, el ciclo del 050, la PINN del oráculo ni los vectores del asistente; la web enseña el gemelo, reentrenar, el equipo, los modelos,
  el aprendizaje y la aceptación en las dos ediciones; el doctor dice la GPU, su CUDA y su memoria libre; sin GPU el trabajo falla con
  un mensaje para el operador y sin traza; `config/entrega.json` entrega los guiones de entrenar (los pesos siguen fuera, RF-34). Se quedan, por seguridad: Host, Origin y token (RF-17 a RF-20), salidas a la red apagadas por
  defecto (RF-22), CORS sin Vite en producto y `CSG_EDICION` solo para forzar «producto». Rojo y verde en `D:/csg/EDICION/`
  (`tests/test_edicion_producto.py`, `tests/test_asistente_reranker.py`, `tests/test_arquitectura_generada.py`,
  `tests/test_instalacion_programa.py`, `frontend/test/edicionTodoActivo.test.mjs`). Ampliación del mismo día: en el programa
  instalado las mejoras del código avisan que son de desarrollo (`edicion.exigir_desarrollo`, decidido por la carpeta instalada
  como M-3) y el reentreno automático no pide permiso (rojo2 y verde2 en `D:/csg/EDICION/`). Pendiente: probar el gemelo y entrenar en el programa instalado con GPU, en la T40.
- [x] T13 Host, Origin, token y escucha. (RF-17, RF-18, RF-19, RF-20) (`v1/seguridad`)
  Hecho cuando: pruebas negativas por cada una, también en WebSocket; la web sigue funcionando en el navegador real.
  Evidencia: `tests/test_seguridad_web.py`; navegador real contra una web propia en el 8791, con una página de otro origen rechazada en POST, GET y WebSocket.
- [x] T14 Leaflet propio, política de contenido y sin salida a la red por defecto. (RF-21, RF-22) (`v1/seguridad`)
  Hecho cuando: con lo externo cortado en el navegador, cargar, convertir, descargar y abrir el mapa funcionan; una prueba recorre las salidas conocidas.
  Evidencia: `tests/test_seguridad_web.py`; navegador real en el 8791, sin conexiones externas del servidor. El flujo completo con la red cortada de verdad es la T36.
- [x] T75 Los marcos los decide la puerta en toda respuesta: los dos mapas que enmarca la interfaz se ven, solo al mismo
      origen, por una lista de rutas con nombre (`seguridad.RUTAS_ENMARCABLES`) y solo si la respuesta es una página HTML
      aislada que no es descarga; todo lo demás, también el 401, el 403, el 303, un error JSON y una descarga de esas rutas,
      sigue con `DENY` y `frame-ancestors 'none'`; las teselas, por sus servidores exactos. (RF-21) (`v1/seguridad`)
      Hecho cuando: `tests/test_seguridad_web.py` (086:RF-21) en verde, con la prueba que recorre `app.routes` y la coteja
      con el contrato OpenAPI, y en rojo sobre el árbol 9d483349; y la revisión en navegador real enseña los dos mapas dentro
      de la web y niega el marco desde otro origen.
  Hecho en la fila 086-T75 (f7, 17-11): la revisión en navegador real es `frontend/e2e/marcos.spec.ts`: dentro de la web,
  el plano de la red y la vista previa del alimentador se ven en un marco de la propia web; desde otro origen (una
  página en localhost:9, sin la cookie de la sesión) no se pintan, también con el 401. Las cabeceras de cada caso,
  en tests/test_seguridad_web.py (086:RF-21).
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
  Ampliación de lanzamiento (L1, 2026-11-14; aclaración de RF-33): los comentarios de `src/` y de los guiones entregados que citaban a
  otras distribuidoras se reescriben sin nombre, código ni cifra; las huellas en git pasan de 49 a 182, con las dos empresas;
  `comprobar_entrega` ve un término partido entre dos líneas y el neutralizador quita las cifras de la línea; `--final` sin lista
  local es un error. La lista local propuesta (U5) está fuera de git, en `D:/csg/LANZAMIENTO/lista_local/`, a la espera del usuario.
  Pruebas: `tests/test_entrega_universal.py` (086:RF-33); rojo y verde en `D:/csg/LANZAMIENTO/`.

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
  Ampliación de lanzamiento (L5, L6, L7; U1 a U8, 2026-11-14; aclaraciones de RF-39, RF-44 y RF-89): `construir_candidato --final`
  exige lista local, el Python 3.12.10 oficial con la firma de la PSF y `pip-audit` (de un entorno aparte, `CSG_PIP_AUDIT`) sin
  vulnerabilidades sin justificar en `config/vulnerabilidades_justificadas.json`; `firmar` (signtool, certificado por variable) y
  `sumas` (`SHA256SUMS`). `LICENCIA_COMERCIAL.txt` en la entrega y en `LicenseFile=` del `.iss`, con `AppPublisher` igual que `authors`
  de la rueda; la MIT no va. `MANUAL_ORDENES.md` sustituye en la entrega al de comandos; la guía de la persona ajena y la parte de
  construir del manual de instalación no se instalan (`config/entrega.json`, `documentos`). El doctor avisa sin Excel ni WPS.
  `pip-audit` real del lock el 2026-11-14: 58 librerías, 0 vulnerabilidades. U8: `MANUAL_DE_USO.md` no se entrega: es del
  2026-10-31, remite a `specs/`, al manual de comandos y a `tools/`, y le falta la 1.0 instalada (instalador y actualizaciones,
  todo activo, perfil desde la web, copia de datos, fondo de mapa, avisos por paso, el asistente y el complemento de IA).
  Sin certificado todavía (trámite del usuario): `firmar` está probado con un doble de signtool.
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
  Avance (2026-11-14, auditoría de lanzamiento L3, L4 y L8; decisiones del usuario del 2026-11-13): `complemento-ia
  --modelos` trae, sin internet, intfloat/multilingual-e5-base en su revisión d1287505 (070:RF-77: la forma de la caché de
  Hugging Face que lee el codificador, cada fichero por su SHA-256 o su blob git del catálogo), qwen3:8b (el manifiesto del
  registro, cuyo SHA-256 es la revisión 500a1f06, y cada capa por su huella) y Ollama 0.40.16 (el zip oficial, con la huella
  que publica su página de versiones), más un corpus de órdenes neutro, de las plantillas con nombres inventados y revisado
  contra la lista de términos (RF-34). Sus pesos están en `pesos_permitidos`, entrenados con datos públicos. Las licencias
  (MIT de e5 y de Ollama, MIT de ggml, Apache-2.0 de Qwen3) se comprobaron en su fuente oficial, permiten redistribuir y van
  en `config/licencias_terceros`, en los avisos, en `licencias/modelos` y en el SBOM como `machine-learning-model` y
  `application`. Los avisos del núcleo y del complemento llevan además las licencias nativas del Python propio, vcruntime, el
  texto de NVIDIA de cada DLL de CUDA y cuDNN, y el código fuente de cada LGPL (GEOS, iconv, psycopg2/libpq, moocore,
  FFmpeg); una DLL LGPL sin su fuente declarada impide armar. El complemento se instala con `instalador/ComplementoIA.iss` y
  `instalar_candidato.py complemento`, sin pip a mano, junto al programa de su misma versión; el lanzador lee los modelos de
  `complemento_ia` sin internet. «Pregunta» en el instalado responde sobre los manuales y notas entregados con la abstención
  por BM25 que calibra el constructor (`asistente/pregunta_entregada.py`), con la muestra mínima y la comprobación de fugas
  de la 097:RF-19, reutilizadas de la tarjeta de la fuga del 077. Pruebas: `tests/test_complemento_integral.py` y
  `tests/test_pregunta_entregada.py`; evidencia en `D:/csg/INSTALADOR_IA/`. Sigue abierto: compilar el complemento real
  (unos 10 GB) e instalarlo en este equipo con la GPU, y lo demás de esta tarea.
  Rebase sobre 00d30651 (B5 de e6, 2026-11-14): si la calibración del corpus entregado falta, no se lee, le falta una
  clave, su umbral no es numérico o es de otro corpus o de otro conjunto, «pregunta» sigue diciendo «No lo sé», pero ya no
  en silencio: `reranker.servicio_entregado` lo avisa en el registro con la causa concreta y la deja en la política
  (`abstencion_sin_calibrar`). Pruebas: `test_sin_calibracion_el_instalado_lo_avisa_y_dice_por_que` y
  `test_una_calibracion_que_no_vale_se_avisa_con_su_causa`.
  Rebase sobre 9d483349 (puerta C, 2026-11-16): la calibración del corpus entregado se escribe con `write_json_atomic`,
  la escritura atómica única de 001:RF-5 (`tests/test_json_atomico.py`), y no con `write_text`.
- [ ] T41 Una persona ajena al proyecto instala y convierte siguiendo el manual. (RF-44)
  Hecho cuando: lo consigue sin ayuda, o lo que no entendió queda corregido en el manual.
  Avance (2026-11-21, MEJ33 de d8; revisor ajeno con origen maestro, sin leer el código): sobre el producto instalado
  comprobó sin ayuda el diagnóstico, los accesos y dónde queda cada cosa; no pudo convertir. Corregido en el manual: el
  paso siguiente a la instalación, cómo se escriben las órdenes `csg.cmd`, el aviso de «Fuentes normativas» y, en el
  manual de uso, a quién va dirigido; en la guía del perfil, dónde está y cómo se valida en el programa instalado.
  Falta: instalar desde un `setup.exe` del candidato en una QA aislada (no sobre el producto instalado del usuario), la
  red de ejemplo inventada que pide para convertir sin datos de una empresa, la sección del operador para instalar el
  complemento de IA y la plantilla del perfil entre los documentos. Hallazgos y evidencia:
  `D:/csg/PM_IMPL/MEJ33_WEB/t41/` y `D:/csg/PM_IMPL/MEJ33_WEB/HANDOFF.md`.

## F6 Corridas reales sobre el candidato congelado

Cada corrida: `tools/sistema_web.py` y el navegador, en serie, con proyectos de prueba nuevos. `D=<DATOS>/<COPIA_ANTERIOR>`.

- T24. Retirada el 2026-11-08 por orden del usuario, sin hacer: R1 con CA191 + PE194 ya se hizo; sus tareas siguen cada una por su cuenta. Era: [DIgSILENT] R1, CA191 + CHN192, TXT (el usuario la cambió de CA191 + PE194 el 2026-11-08), sobre el proyecto `20261105-124711_CSG_TXT_CA191_CHN192`, sin reconvertir: `--red CA191 CHN192 --grupo CA191_CHN192 --demanda-dir $D --periodo 2026-07`, luego en el navegador calibración, cargas, obras, transferencia e informes. (RF-45)
- [x] T25 [DIgSILENT] R2, SI293 y PN197, MDB, uno por vez, con cargas por el navegador. (RF-45)
  Cierra: 007 T11, 016 T18, 028 T11, 081 T20. Hecho cuando: variación por carga, barra más cercana, base activa al terminar.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T26 [DIgSILENT] R3, Pisco y una SET, TXT: `--zonal Pisco --demanda-dir $D --periodo 2026-07 --reconvertir`, luego `--set <SET>`. (RF-45)
  Cierra: 028 T15, 083 T3, 081 T10 a T13, 078 T6, 027 T22 (borrador). Hecho cuando: instante en 60 kV, LT y centrales; huella igual antes y después; estado veraz; los alimentadores sin medidor, con su motivo.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T27 [DIgSILENT] R4, NA293 + NA295, TXT, proyecto nuevo, con los dos criterios de fijas, cargas y obras. (RF-45)
  Cierra: 039 T4, 042 T6, 052 T4, 084 T8, 017 T14, 073 T8, 073 T10. Hecho cuando: NA293 con «máximo del mes» da 7 707,5 kW y 3 725,5 kvar (039); SET en 0,94–1,06 pu y fuera del trazado; oráculo frente a DIgSILENT; valle.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T28 [DIgSILENT] R5, NJA292 y R295, VNR-GIS de Empresa B. (RF-45, RF-46)
  Cierra: 051 T3, 055 T2, 056 T3, 005 T12, 081 T16. Hecho cuando: cabecera dentro del 1 %; sistemas y SET; vocabulario y carpeta de la empresa. R295 frente a 0205 sin suponer alias.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T29 Navegador: 067 T8, 077 T7, 073 T10, y escritorio con pantalla estrecha. (RF-45)
  Hecho cuando: todo se ve funcionar en el navegador real, en claro y oscuro.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T30 [DIgSILENT] R6, solo si el asistente se vende como beta: un alimentador, una SET y una carga por órdenes escritas. (RF-45)
  Cierra: 070 T9, 070 T10, 067 T9, 026 T12, 078 T7. Hecho cuando: los informes salen de las órdenes, con confirmación.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).

No hacen falta para la 1.0: 025 T21 (PA297 vetado; reformular según D6), 027 T14 y T29 a T31, 028 T6, 044 T4, 045 T4, 048 T4, 049 T4, 070 T11, 075 T6, 079 T7, 081 T14. 065 T12 pasa a ser el conjunto R1 a R5.

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
      Ampliación 2026-11-13 (aclaración de RF-86, auditoría c7): borrar el espacio bajo el cerrojo de encolar.
      Hecho cuando: `tests/test_datos_duraderos.py::test_borrar_el_espacio_y_encolar_van_bajo_el_mismo_cerrojo`
      (086:RF-86) en verde, en rojo sobre 048812bb.
- [x] T61 La calibración reutiliza la `Fichas_`/`SED_NTP_` del conversor que trae una copia del proyecto, reconocida por su
      marca y no por el prefijo (una del operador no se toca; con varias se avisa), y la consigna de la fuente
      llega también a «Cargas nuevas». (RF-87, RF-88)
      Hecho cuando: `tests/test_variaciones_por_marca.py` (086:RF-87, RF-88) y `tests/test_ajuste_proyecto_guion.py`
      (086:RF-88) en verde; la corrida en DIgSILENT sobre una copia de PA297 va en la T32.
- [x] T70 Los manuales y las notas de la publicación en «documentos/» del candidato y en `{app}\documentos`, y el menú Inicio
      abre el manual de instalación; `instalar_candidato.py` los prepara al lado y solo los publica cuando cambia el puntero,
      y si falla deja los anteriores. (RF-89, RF-90, RF-91, RF-97)
      Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-89 a RF-91, RF-97) en verde y el `.iss` compila con ISCC sobre
      un candidato de prueba. Verlo instalado es de la T40, con el rc6.
      Aclaración (2026-11-21, MEJ33b de d8): el setup de la rc6 se armó el 12-11 con un `.iss` anterior al acceso, y el
      producto instalado no abre el manual desde el menú Inicio (lo vio el revisor ajeno de la T41). El código está bien;
      desde hoy armar un candidato comprueba el `.iss` que copia (`construir_candidato.comprobar_accesos_del_menu`,
      `tests/test_instalacion_programa.py`, 086:RF-90), y el de la rc6 no pasa. Verlo instalado sigue en la T40, con el
      próximo setup: en el menú Inicio, «ConverterSmartGrid - manual de instalacion».
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
- [x] T78 Accesibilidad WCAG 2.2 AA de la web: pestañas con el patrón de WAI-ARIA, flechas en los grupos de opciones,
      separador del Registro con teclado y pulsación, salto al contenido, estados con texto o icono, tokens con contraste AA
      en los dos temas y objetivos de 24 px. (RF-106)
      Hecho cuando: `tests/test_accesibilidad_web.py` (086:RF-106) en rojo sobre el árbol 9d483349 y en verde con el cambio, más
      `frontend/test/e2e/teclado.e2e.mjs` en verde con sus capturas revisadas a mano. Evidencia: `D:/csg/PM_IMPL/HEREDADAS_E6/T0c/`.
      Hecho el 2026-11-20 (d8, revisor origen maestro): teclado.e2e.mjs 5/5 en las tres corridas de e2e:todo sobre
      c4326366 (+ NAV_propuesta.patch en la final), capturas revisadas a mano, y revisión WCAG 2.2 AA en navegador
      real con axe 0 en las 14 pestañas y los dos temas tras corregir NAV-4 (target-size de .curva-check). Evidencia:
      D:/csg/PM_IMPL/NAV_BLOQUE/e2e_final/ y t17_final/. test_accesibilidad_web.py: rojo de origen en HEREDADAS_E6/T0c
      y verde en la suite de la puerta. Informe: D:/csg/PM_IMPL/NAV_BLOQUE/INFORME.md, sección «086 T78: WCAG 2.2 AA».
- [ ] T79 Recorridos E2E F01–F04 con Playwright y axe-core (devDependencies fijadas), sobre una web aislada y sin red, con
      capturas y resultado por SHA. (RF-107)
      Aclaración (59, 19-11): F02 ya existe, es `frontend/e2e/plano.spec.ts` (111 T16 cerrada), y los navegadores de
      Playwright están instalados; Playwright y axe-core van en `package.json` y `package-lock.json` (T0c v3).
      Hecho cuando: `npm run e2e:todo` (los dos arneses: F01, F03 y F04 en `test/e2e`, F02 en `frontend/e2e`) da verde
      sin omitidas sobre el SHA candidato, con `output/e2e/<sha>/` sellado (SHA256SUMS).
      Avance (2026-11-21, MEJ33 de d8): `frontend/test/e2e/todos.mjs` deja en `output/e2e/<sha>/` la evidencia de los dos
      arneses (la del plano en `plano/`) con `resumen_e2e.json`, y solo una corrida en verde la sella con SHA256SUMS
      (`tests/test_ci_e2e_y_evidencias.py`, 086:RF-107). Falta correrlo sobre el SHA candidato, ya en commit:
      `cd frontend && npm run build && npm run e2e:todo`.
- [x] T80 COPIA-PREVIA: previa de la copia en la web (`GET /api/copia-datos/previa` sobre `planificar_copia`, ventana
      `PreviaCopia` con «Copiar» y «Cancelar», la API exige `confirmada`), listado de las copias del destino desde su
      manifiesto (`listar_copias`), el aviso que mira la carpeta recordada (`estado_copia(destino=…)`) y los seis textos.
      (RF-82, RF-83, RF-108, RF-109, RF-110)
      Hecho cuando: `tests/test_copia_datos.py` (086:RF-82, RF-83, RF-108, RF-109), `tests/test_fuente_por_lo_que_se_carga.py`
      (086:RF-110) y `frontend/test/copiaPrevia.test.mjs` (086:RF-82, RF-83, RF-108 a RF-110) en verde, con rojo previo; y el
      recorrido real repetido en el navegador con las carpetas sincronizadas del usuario (`D:/csg/PM_IMPL/COPIA-PREVIA/recorrido/`):
      lectura de la previa y del listado sobre la carpeta de copias, «Cancelar» sin escribir, y una copia pequeña escrita solo
      en `pruebas_1_0` tras «Copiar», con el diff de los listados vacío fuera de esa carpeta.
      Hecho el 2026-11-20 (d8): recorrido real en navegador sobre c4326366 con las carpetas sincronizadas: previa y
      listado de copias_de_datos (la copia del 12-11 como buena), «Cancelar» sin escribir, y una copia de 4,2 MB solo
      en pruebas_1_0 tras «Copiar», verificada huella a huella, con el diff de las siete raíces vacío fuera de
      pruebas_1_0 (16 pasos OK). test_copia_datos y test_fuente_por_lo_que_se_carga en verde (237 passed con el resto)
      y copiaPrevia.test.mjs en npm test 334/334; rojos de la pieza en COPIA-PREVIA/rojo.log. Evidencia:
      D:/csg/PM_IMPL/NAV_BLOQUE/t80/. Informe: D:/csg/PM_IMPL/NAV_BLOQUE/INFORME.md, sección «086 T80: previa de la
      copia (COPIA-PREVIA)».
- [x] T81 Las sales de las huellas se calculan al cambiar la lista, no en cada ventana de palabras. (RF-111)
      Hecho cuando: `tests/test_entrega_universal.py` (086:RF-111) en verde, con rojo previo, y la rueda real sigue pasando la
      comprobación (`tests/test_instalacion_programa.py`). Evidencia: `D:/csg/PM_IMPL/INST-RUEDA/`.
- [x] T31 Suite completa sin omitidas sobre el candidato, con líneas base y determinismo. (058 T5, 025 T22, 065 T13) (RF-46)
  Hecho cuando: cero fallos, cero omitidas.
  Evidencia: suite completa del 2026-11-12 sobre 6306cc65 con las doce variables de datos reales y `-rs`: 8 682 aprobadas, 0 fallidas, 0 omitidas (59 min; `.git/puerta_calidad/6306cc65….json`). Las líneas base y el determinismo (`workers` 1 y >1) están dentro de esa suite.
- [ ] T32 [DIgSILENT] Instalación con el `setup.exe` en este equipo, con su DIgSILENT, y corrida de otra empresa de punta a punta hasta el informe. (RF-46)
  Hecho cuando: sin tocar el código, solo su perfil, sale un informe que un ingeniero da por bueno.
- [x] T33 [DIgSILENT] Ensayo de corte a media calibración y a media importación, matando los procesos con las demás sesiones paradas. (RF-46)
  Hecho cuando: ningún espacio se pierde, el trabajo se ve interrumpido y se retoma sin trabajo repetido ni datos mezclados.
  Corrida del 2026-11-20 (parte de la calibración): reprodujo dos fallos, las variaciones del conversor apagadas tras el
  corte y las cargas a medias tomadas por manuales. Su código: 083:RF-35 y 083:RF-36 (083 T20, T21). Falta repetir la
  corrida con ese código y hacer la parte de la importación sobre una red de prueba sin proyecto (005:RF-22).
  Hecho el 2026-11-21 (bloque DIgSILENT 2 de d8, wt_d8_dig2 = 7ed2c05d, web propia 8794 sobre la copia del espacio de
  prueba). Corte a media calibración (los dos alimentadores de prueba, kill a los 45 s de `ajuste_aplicar`): el espacio queda intacto,
  el trabajo `interrumpido` y el diario de 083:RF-35 abierto con su token. Al retomar, sin reconvertir ni reimportar,
  las variaciones del conversor se encienden antes de leer (083:RF-36) y la central y los bancos se ven; las 47 cargas
  que dejó la orden cortada salen como «de una orden cortada» y no como cambios a mano (0 cambiadas). Los dos
  alimentadores quedan VALIDO y el diario se cierra. Corte a media importación (uno de ellos solo, red de prueba sin proyecto
  previo, kill a los 10 s): ningún proyecto a medias ni borrado. La vuelta usa el proyecto verificado, sin repetir
  trabajo, y queda un solo proyecto de la red, calibrado VALIDO. Las demás sesiones no se pudieron parar desde aquí;
  se mataron solo los procesos propios. Evidencia: `D:/csg/PM_IMPL/DIG_BLOQUE2/T33_corte/`.
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
- [x] T76 LIC-MIT (usuario, 2026-11-15, «MIT + comercial opcional»): la entrega lleva la MIT como licencia del programa
  (`LICENSE` → `documentos/LICENSE.txt`, la que muestra `LicenseFile=` del `.iss`); `LICENCIA_COMERCIAL.txt` pasa a acuerdo
  opcional de soporte y garantía (`config/entrega.json` → `documentos.opcionales`), sin abogado ni cláusula de jurisdicción;
  manuales y notas al día. (RF-44)
  Hecho cuando: `tests/test_instalacion_programa.py` (086:RF-44: la licencia de la entrega es la MIT y la comercial es
  opcional; el .iss muestra la MIT; LICENSE.txt con BOM) en verde, con rojo previo. Evidencia: `D:/csg/PM_IMPL/LIC-MIT/`.
- [x] T77 SSRF-ARCGIS (BP-29, P0): `salidas_red.get_sin_redireccion_ajena` y su uso en `connectors/arcgis.py`,
  `discovery/official.py` y `discovery/download.py`: ninguna redirección a otra máquina se pide; la rechazada no se reintenta.
  Pruebas en `tests/test_vnr_etl.py` (127.0.0.1, 169.254.169.254, otro host; mismo servidor sí; https→http no). (RF-22)
  Hecho cuando: `tests/test_vnr_etl.py` (086:RF-22: ninguna redirección a otra máquina se pide, en ArcGIS, el
  descubrimiento y la descarga) y `tests/test_seguridad_web.py` en verde, con rojo previo. Evidencia: `D:/csg/PM_IMPL/SSRF-ARCGIS/v2/`.
- [x] T82 TRABAJOS-ROBUSTOS (auditoría del 18-11, C1: H01 y H02): `presentacion/web/jobs.py` comprueba el recibo durable
  antes de encolar todo trabajo con diario, y aísla del carril los fallos de evento y de diario al empezar y al terminar,
  sin volver a llamar al observador roto. (RF-112)
  Hecho cuando: `tests/test_jobs_resiliencia.py` (086:RF-112) en verde, con rojo previo por aserción, y las pruebas de
  trabajos, recuperación y relanzado sin regresión. Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/c1/`.
- [x] T83 COTA-DE-INGRESO (auditoría del 18-11, C3: H04): `presentacion/web/seguridad.py` `PresupuestoIngreso` cuenta lo
  que entrega `receive` y corta con 413 al pasar el tope; `create_app` lo instala siempre, también sin la puerta. (RF-113)
  Hecho cuando: `tests/test_subidas_presupuesto_ingreso.py` (086:RF-113: sin leer con Content-Length mayor; corte sin
  longitud o con una falsa; límite exacto y un byte más; espacio libre; GET sin contar) en verde, con rojo previo por
  aserción, y las pruebas de subidas sin regresión. Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/c3/`.
- [x] T84 COLA-ACOTADA (auditoría del 18-11, C4: H05): `presentacion/web/jobs.py` rechaza con `TrabajoRechazado` el
  trabajo que pasa el tope de espera de su espacio y carril antes de cualquier efecto, y depura los terminados al
  terminar uno, con los protegidos de RF-114. (RF-114)
  Hecho cuando: `tests/test_jobs_capacidad.py` (086:RF-114: cola llena sin efectos, otro carril y otro espacio libres,
  depuración que no pierde lo referenciado, valores de entorno no válidos) en verde, con rojo previo por aserción, y las
  pruebas de trabajos, recuperación y relanzado sin regresión. Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/c4/`.
- [x] T85 HISTORIAL-TRUNCADO (auditoría del 18-11, C4: H15): `EventLog` antepone `historial_truncado` cuando el
  cursor quedó por detrás de lo descartado; `useWorkspace.ts` lo anota en el Registro y relee el espacio. (RF-115)
  Hecho cuando: `tests/test_eventos_truncados.py` (086:RF-115: buffer 2, cuatro eventos, cursor inicial y cursor al
  día) y `frontend/test/reconexion.test.mjs` (la línea y la relectura) en verde, con rojo previo por aserción.
  Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/c4/`.
- [x] T86 ARRANQUE-HASTA-CONECTAR (prueba funcional del 19-11): `presentacion/web/jobs.py` `run_process` da por
  arrancado un guion de PowerFactory solo con la marca de conexión y, hasta entonces, mide el silencio desde la última
  línea. (RF-116)
  Hecho cuando: `tests/test_pf_arranque_hasta_conectar.py` (086:RF-116: aviso de turno y silencio se corta y se
  reintenta; espera de turno con avisos y conexión no se corta; ya conectado no se corta; cancelar sin conectar
  termina) en verde, con rojo previo por aserción, y las pruebas de 005:RF-21 y del servidor de PowerFactory sin
  regresión. Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/pfvigia/`.
- [x] T87 BUFFER-CONCURRENTE (CI del 19-11): `adaptadores/digital_twin/buffer.py` rehace el índice bajo un cerrojo
  por carpeta, con temporal propio y aceptando el índice válido de otro proceso. (RF-117)
  Hecho cuando: `tests/test_buffer_indice_concurrente.py` (086:RF-117: 8 aperturas a la vez sin índice, seis vueltas,
  ninguna falla, 12 episodios indexados, sin temporales) en verde, con rojo previo por aserción (7 de 8 con
  PermissionError), y las pruebas del búfer y del gemelo sin regresión. Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/pfvigia/`.
- [x] T88 LISTADO-UNA-LECTURA (revisión web del 19-11, W4): `WorkspaceStore.list` analiza cada `workspace.json` una
  vez (`_examinar` da el problema y los datos) y guarda el resumen por la huella del fichero y de su copia. (RF-118)
  Hecho cuando: `tests/test_revision_web_estados.py` (086:RF-118: una lectura por espacio, ninguna en el segundo
  listado, un cambio que se ve y un espacio dañado con su motivo) en verde con rojo previo por aserción, y las pruebas de
  espacios sin regresión. Hecho en esta entrega (ce): rojo VALIDO (2 F) y verde 226 passed en
  `D:/csg/PM_IMPL/REVISION_WEB/w4/`; con los datos del acceso directo, 52 espacios en 2,1 s el primero y 0 s después.
- [x] T89 SIN-PLURAL-ENTRE-PARENTESIS (revisión web del 19-11, W5 a W8): `plural`/`cuenta` en `frontend/src/shared/formato.ts`,
  los «(s)»/«(es)» de todas las pantallas con la cuenta concordada, el Registro con la etiqueta de la casilla, la ayuda
  del CRS sin la clave del perfil y la línea de la entrada sin pedir otra carga cuando ya está cargada. (RF-110)
  Hecho cuando: `frontend/test/sinPluralEntreParentesis.test.mjs` (recorre `frontend/src`) y
  `tests/test_revision_web_estados.py::test_086_rf110_el_registro_nombra_la_casilla_como_la_ve_el_operador` en verde
  con rojo previo por aserción, y `npm test` entero en verde. Hecho en esta entrega (ce): rojos por aserción en
  `D:/csg/PM_IMPL/REVISION_WEB/w5/` a `w8/` y `gpf/w6/`, `npm test` 305/305 sobre gPF (`gpf/npm_test.log`), tsc rc=0.
- [x] T90 CAPEX-SIN-HOJA (prueba funcional del 19-11): `aplicacion/pide_economia.py` `leer_capex` reconoce por su
  contenido las hojas del CAPEX cuando el perfil no declara la hoja, y si ninguna sirve dice qué falta. (RF-119)
  Hecho cuando: `tests/test_capex_sin_hoja.py` (086:RF-119: sin hoja ni columnas, una hoja de costos entre otras se
  lee; sin hoja y ninguna válida, error en español sin «None» que nombra columnas, hojas y el perfil; con la hoja
  declarada, igual que antes) en verde, con rojo previo por aserción, y `tests/test_pide_economia.py` y las de
  procedencia del CAPEX sin regresión. Evidencia: `D:/csg/INTEGRA_54/cierre_tareas/capex_hoja/`.
- [x] T94 TWIN-ID (orden del integrador del 19-11 por la ablación de 045 T3): `presentacion/web/services.py`
  `identidad_de_captura` toma la última calibración aplicada; `adaptadores/digital_twin/buffer.py` lleva el registro
  aparte `identidad_043.jsonl`; `tools/rellenar_identidad_043.py` lo rellena y `tools/preparar_ciclo_aprendizaje.py` lo
  combina con los objetos. (RF-120)
  Hecho cuando: `tests/test_identidad_043_relleno.py` (086:RF-120: captura tras una calibración fallida; en seco no
  escribe; `--aplicar` solo escribe el registro y el ciclo saca el episodio de cuarentena; lo no deducible sigue apartado;
  un registro que contradice no sustituye; registro atómico que sobrevive al índice y búfer viejo legible) en verde, con
  rojo previo por aserción, las pruebas del búfer, del gemelo y del ciclo sin regresión, y el preflight sobre una copia
  del búfer real con `proyectos_043` ≥ 1 y `contexto_hash` no nulo. Aplicar el relleno al búfer real lo decide el
  integrador. Evidencia: `D:/csg/PM_IMPL/TWIN_ID/`.
- [x] T96 CENTRALES-SET (orden del usuario del 19-11; amplía 022:RF-88): `demanda_centrales_de_barra` da todas las SET de
      la estructura con sus alimentadores; la tabla de centrales de la máxima por barra (DemandaMedida.tsx, con
      `centralesDeSet.ts`) elige la SET de cada una con dos grupos (las de los analizados y las otras), ofrece el tramo de
      un alimentador de esa SET y dice «no entra» si su SET no tiene ninguno de los analizados; `centrales_set` llega al
      trabajo y `demanda_medida.centrales_en_su_set` pone cada central en su SET y deja fuera las que no entran, con su
      aviso. Pruebas: tests/test_centrales_de_set.py y frontend/test/centralesDeSet.test.mjs (rojo por aserción). (RF-122)
      Hecho cuando: rojo por aserción (sin la lista de SET ni la SET elegida) y verde con sus pruebas, y, ya integrada, un
      recorrido en navegador real por la web del operador (solo lectura, con sus libros y su estructura): la tabla de
      centrales con el selector de SET, las de los analizados primero y el «no entra» de las que no lo son. Evidencia:
      `D:/csg/PM_IMPL/CENTRALES_SET/` y `D:/csg/PM_IMPL/GWEB2/`.
      Hecho el 2026-11-21 (MEJ33 de d8): recorrido en navegador real (Chromium, claro y oscuro, axe 0) sobre una web
      propia en el 8791 con el árbol de 7ed2c05d (ya en main), no la del operador del 8766, por la regla de coordinación;
      con sus libros de medidores y de cabecera por su ruta, en solo lectura, y la estructura de una copia de su perfil;
      la lista de proyectos de DIgSILENT dada hecha, como en F03. Tres alimentadores de una misma SET, año 2026.
      En «Por SET» y en «Sistema eléctrico», la tabla de centrales da las tres del libro con su selector, el grupo «SET de
      los alimentadores analizados» primero, y las dos de otras SET apagadas con «… no tiene ninguno de los alimentadores
      analizados: no entra.». Evidencia: `D:/csg/PM_IMPL/MEJ33_WEB/recorrido/` (resultado_light.json, resultado_dark.json
      y capturas *_centrales.png).
- [x] T97 ETIQUETAS-MAXIMA (orden del usuario del 19-11): `CurvaCabecera.tsx` con varias curvas pinta la etiqueta de
      cada máxima (alimentador · kW · fecha y hora), con su muestra de color, halo y guía al punto si se movió;
      `graficos.separarEtiquetas` las reparte sin taparse y dentro del gráfico. Prueba:
      frontend/test/etiquetasMaxima.test.mjs (200 casos sorteados con la semilla en el registro; rojo por aserción). (RF-123)
      Hecho cuando: rojo por aserción (sin etiquetas ni su reparto) y verde con su prueba sorteada, y, ya integrada, la
      gráfica de curvas de cabecera vista en navegador real en la web del operador con una etiqueta por máxima.
      Evidencia: `D:/csg/PM_IMPL/CENTRALES_SET/` y `D:/csg/PM_IMPL/GWEB2/`.
      Hecho el 2026-11-21 (MEJ33 de d8): recorrido en navegador real (Chromium, claro y oscuro, axe 0) sobre una web
      propia en el 8791 con el árbol de 7ed2c05d (ya en main), no la del operador del 8766, por la regla de coordinación;
      con sus libros de medidores y de cabecera por su ruta, en solo lectura, y la estructura de una copia de su perfil;
      la lista de proyectos de DIgSILENT dada hecha, como en F03. Tres alimentadores de una misma SET, año 2026.
      En los tres análisis, la gráfica de curvas de cabecera da una etiqueta por máxima (7 etiquetas para 7 curvas:
      alimentador · medidor · kW · fecha y hora). Evidencia: `D:/csg/PM_IMPL/MEJ33_WEB/recorrido/` (capturas *_curvas.png).
- [x] T98 CALIB-IMPOSIBLE (orden del usuario del 19-11; amplía 083:RF-30): en una corrida real de cuatro alimentadores,
      tres cumplían y el cuarto tenía fijas que con sus pérdidas pasaban de su cabecera; el oráculo dejó su factor casi en
      cero, «escaladas al mínimo» se medía contra ese factor y el bucle gastó los 30 flujos sin causa, marcando a los cuatro
      como violación. `cuadrar_conjunto(factores_iniciales=…)` mide el mínimo contra el factor de antes del oráculo; el
      imposible queda en `CuadreConjunto.imposibles` con `causa_imposible` y se para si los demás cumplen;
      `CuadreConjunto.cumple`; el guion pasa los factores, guarda la causa y da por cuadrado al que cumple. Lo mismo para
      una SET o un sistema eléctrico (el mismo `_ejecutar_proyecto`) y con un solo alimentador: `cuadrar(factor_inicial=…)`
      corrige las fijas (083:RF-30, que en ese camino no existía) o para con `Cuadre.imposible`. Pruebas:
      tests/test_calibracion_imposible.py (red sintética sorteada; rojo por aserción: la base gasta los 30 flujos). (RF-124)
      Hecho cuando: rojo por aserción sobre la base (gasta los 30 flujos sin causa) y verde con sus pruebas, las selladas de
      la 083 en su orden, capas e inventario; la prueba real en DIgSILENT, en el turno que dé el integrador. Evidencia:
      `D:/csg/PM_IMPL/CALIB_IMPOSIBLE/`.
      Hecho el 2026-11-20 (bloque DIgSILENT de d8, wt_d8_mej567 = c4326366, web propia): prueba real sobre el proyecto
      de cuatro Informe: D:/csg/PM_IMPL/DIG_BLOQUE/INFORME.md, sección «086 T98: CALIB-IMPOSIBLE en una corrida real
      de cuatro alimentadores».
- [x] T99 GEMELO-NO-CONVERGE (orden del usuario del 19-11): `tools/digital_twin_snapshot_pf.py` lee el grafo aunque
  el flujo no converja, marca `flujo_converge` y dice la causa en `resumen_salida`; `adaptadores/digital_twin/capture.py`
  clasifica `rejected` con su causa una lectura válida que no converge, e `integration.py` avisa el rechazo en el
  Registro. (RF-125)
  Hecho cuando: `tests/test_digital_twin_snapshot_pf.py`, `tests/test_digital_twin_capture.py` y
  `tests/test_digital_twin_integration.py` (086:RF-125) en verde, con rojo previo por aserción (4 F), y las pruebas del
  gemelo sin regresión. Evidencia: `D:/csg/INTEGRA_54/cierre_tareas/gemelo/` (rojo2, 4 F) y `cierre_tareas/calib/verde2.log` (701 passed).
- [x] T100 MAXIMA-NO-COINCIDENTE (orden del usuario del 19-11; amplía 028:RF-27, RF-28): DemandaMedida.tsx ofrece «Máxima
      de cada alimentador (no coincidente)» en el selector del instante, que sale también en el análisis de una SET o de un sistema; la pide
      sin barra, sin sistema y sin coincidente (las máximas propias que ya da el servidor) y avisa con la fecha de cada
      uno; tools/ajuste_cabecera_pf.py `aviso_de_instantes` lo dice en el informe sin bloquear. (RF-126)
      Hecho cuando: rojo por aserción (sin la opción ni el selector por SET o por sistema) y verde con
      frontend/test/maximaNoCoincidente.test.mjs y tests/test_centrales_de_set.py, y, ya integrada, un recorrido en
      navegador real por la web del operador (solo lectura) con el selector en los tres análisis, el por defecto sin
      cambiar y el aviso con la fecha de cada alimentador. Evidencia: `D:/csg/PM_IMPL/GWEB2/`.
      Hecho el 2026-11-21 (MEJ33 de d8): recorrido en navegador real (Chromium, claro y oscuro, axe 0) sobre una web
      propia en el 8791 con el árbol de 7ed2c05d (ya en main), no la del operador del 8766, por la regla de coordinación;
      con sus libros de medidores y de cabecera por su ruta, en solo lectura, y la estructura de una copia de su perfil;
      la lista de proyectos de DIgSILENT dada hecha, como en F03. Tres alimentadores de una misma SET, año 2026.
      En «Alimentadores», «Por SET» y «Sistema eléctrico», tras buscar, el selector queda en su opción por defecto y
      ofrece «Máxima de cada alimentador (no coincidente)»; al elegirla, el aviso da la fecha de cada uno de los tres.
      17 pasos en cada tema, 0 fallos. Evidencia: `D:/csg/PM_IMPL/MEJ33_WEB/recorrido/`.
- [x] T101 REFERENCIA-SOPORTE (Plan Maestro PM-14 y PM-25): `dominio/traza.py` (referencia en curso, validación y
      `CSG_TRAZA`); `seguridad.TrazaPeticion`, por fuera de todo en `app.py`, la fija por petición y la devuelve en
      `X-CSG-Traza`; `jobs.Job.traza` la hereda, sale en `public()` y en el diario, y el trabajo corre con ella en su
      contexto, en `run_process` (`CSG_TRAZA`) y en `en_proceso`; `tools/pf_cliente.py` la deja en la orden,
      `tools/pf_servidor.py` la dice en `servidor.log` y `estadistica_ordenes.registro` en `ordenes.jsonl`;
      `informe_docx._guardar` la pone en las propiedades del Word y en su JSON; `JobRespuesta.traza` con el contrato
      regenerado; `ReferenciaSoporte` en el aviso del trabajo y en su resumen. (RF-127)
      Hecho cuando: rojo por aserción sobre faf67626 y verde con tests/test_traza_soporte.py, sin regresión en
      tests/test_pf_servidor.py, tests/test_jobs_capacidad.py, tests/test_jobs_resiliencia.py, tests/test_jobs_en_proceso.py
      y tests/test_informe_docx.py, el contrato sin deriva (`tools/generar_contrato_api.py --check`), capas e inventario.
      Evidencia: `D:/csg/PM_IMPL/MEJ_TRAZA/`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T102 RESTAURACION-COMPROBADA (Plan Maestro PM-25; amplía RF-10 y RF-47): `copia_datos._comprobar_restaurado`
      relee cada nombre restaurado en su sitio y revierte todo si uno no da su huella; `restaurar_copia` devuelve
      `comprobados_despues`. (RF-128)
      Hecho cuando: rojo por aserción sobre faf67626 y verde con
      tests/test_copia_datos.py::test_restaurar_comprueba_las_huellas_de_lo_restaurado_en_su_sitio y
      ::test_si_lo_restaurado_no_cuadra_se_niega_y_vuelve_lo_de_antes, y el resto de tests/test_copia_datos.py sin
      regresión. Evidencia: `D:/csg/PM_IMPL/MEJ_TRAZA/`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T103 SIN-PLURAL-SERVIDOR (revisión web del 19-11, W5b; completa T89 en el servidor): `plural`/`cuenta` en
      `dominio/util.py`, la regla de `formato.ts`; los literales de `src/convertersmartgrid` que llegan al operador
      (avisos, motivos, `detail`, Registro, informes y cabeceras de los libros) concuerdan con su cuenta, verbo y adjetivo
      incluidos («1 carga no cabe», «3 cargas no caben»), sin cambiar cálculos ni claves de JSON. (RF-110)
      Hecho cuando: rojo por aserción y verde con su prueba, `tests/test_sin_plural_entre_parentesis_servidor.py`
      (086:RF-110: recorre con `ast` los literales y los trozos de las f-strings, sin docstrings ni comentarios; un
      grupo opcional de expresión regular, `medidor(es)?`, no cuenta), y las pruebas que leen esos textos sin regresión.
      Evidencia: `D:/csg/PM_IMPL/MEJ_W5B/`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T104 SIN-PLURAL-TOOLS (revisión web del 19-11, W5c; completa T89 y T103 en `tools/`): `tools/_plural.py` con
      `cuenta`/`plural` (biblioteca estándar, Python 3.9, la regla de `formato.ts`) y los 86 literales de 22 guiones de
      `tools/`, los de DIgSILENT incluidos, concuerdan con su cuenta, verbo y adjetivo incluidos («1 SED fija pide»,
      «3 SED fijas piden»), sin cambiar cálculos, claves ni órdenes a DIgSILENT; la copia del aviso de los transformadores
      de la primera pasada se reconoce por «antes de calibrar, en la misma pasada», que no depende de la cuenta. (RF-110)
      Hecho cuando: rojo por aserción sobre el árbol `faf67626` y verde con `tests/test_sin_plural_entre_parentesis_tools.py`
      (086:RF-110: recorre con `ast` los literales de `tools/`, sin docstrings ni comentarios), y las pruebas que leen esos
      textos sin regresión. Evidencia: `D:/csg/PM_IMPL/MEJ_W5C/`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [ ] T105 MEJ3-CALIB-DIGSILENT [DIgSILENT] (orden del usuario del 19-11; bloque de DIgSILENT del 20-11, con 086 T98):
      corrida real sobre una copia de prueba de un proyecto con fijas que llenan su cabecera, uno con central y bancos y
      uno con escaladas pequeñas: las fijas quedan con su P en «Sin proyecto» y el alimentador sale imposible con su
      causa (006:RF-46), el aviso de escaladas casi en cero (015:RF-71), los bancos a su máxima con central (015:RF-72),
      DIgSILENT arranca con las fijas del oráculo sin rebajar (083:RF-33) y el tope acumulado (083:RF-34).
      Hecho cuando: el informe de la corrida en DIgSILENT trae esos cinco puntos con su cita del registro y ningún
      proyecto trabajado se toca. Evidencia: `D:/csg/PM_IMPL/MEJ3_CALIB/`.
- [x] T106 SIN-GPU-CLARO: `tools/digital_twin_entrenar.py` captura `SinGPU` (informe con `sin_gpu`, código 3);
      `trabajadores_ml.fallo` lo marca; `services.gemelo_entrenar(estricto=True)` (la ruta de reentrenar),
      `gemelo_pronostico`, `gemelo_evaluar` y `gemelo_deriva` fallan con el motivo; el aprendizaje activo queda
      «parcial». (RF-129)
      Hecho cuando: rojo por aserción y verde con su prueba: `tests/test_motores_web_mej4.py` (086:RF-129) y las vecinas
      `tests/test_asistente_maestro.py`, `tests/test_asistente_equipo_web.py` y `tests/test_aprendizaje_continuo.py`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T107 OCUPADO-NO-ES-LICENCIA: `pf_arnes.causa_sin_conexion` mira el turno (`ocupado_por_otra_sesion`) antes de la
      última causa y de la licencia. (RF-130)
      Hecho cuando: rojo por aserción y verde con su prueba: `tests/test_motores_web_mej4.py` (086:RF-130) y las vecinas
      `tests/test_flujo_a_estudio.py` y `tests/test_pf_arnes_sin_atajos.py`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T108 VERSION-DE-PYTHON-DE-PF: `powerfactory_env.falta_python_de_pf` en `_require_pf` y en la fila «digsilent»
      del doctor, que dice el Python que pide la instalación; la fila «python» deja de atribuir a DIgSILENT el 3.12.
      (RF-131)
      Hecho cuando: rojo por aserción y verde con su prueba: `tests/test_motores_web_mej4.py` (086:RF-131) y las vecinas
      `tests/test_powerfactory_versiones.py` y `tests/test_instalacion_programa.py`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T109 RECALIBRACION-SIN-CORTES: `jobs.reserva_de_digsilent` en la admisión de la cola, el middleware
      `TrabajoPropio` con la cabecera `X-CSG-Trabajo-Propio`, y `tools/sistema_web.py` que la envía y espera su carril
      ante «Ya hay un trabajo en curso». (RF-132)
      Hecho cuando: rojo por aserción y verde con su prueba: `tests/test_motores_web_mej4.py` (086:RF-132) y las vecinas
      `tests/test_web_api.py`, `tests/test_jobs_capacidad.py`, `tests/test_jobs_en_proceso.py`, `tests/test_jobs_resiliencia.py`
      y `tests/test_sistema_web.py`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T110 MEJ23-TRABAJO-FALLIDO-Y-DEL: `services.causa_del_guion` y `exigir_guion` en «Aplicar el libro»
      (`datos_empresa_aplicar`) y en `pfd_importar`; `historico_interrupciones.con_de` en `frase_exposicion`. (RF-133, RF-134)
      Hecho cuando: rojo por aserción y verde con `tests/test_estudios_red_web.py -k fallido_queda_fallido`,
      `tests/test_pfd_web.py -k fallido` y `tests/test_historico_interrupciones.py -k contrae` (086:RF-133, 086:RF-134).
      Hecho el 2026-11-21 (MEJ23, código): rojo por aserción D:/csg/PM_IMPL/MEJ23_PFD/rojo.log y verde D:/csg/PM_IMPL/MEJ23_PFD/verde_nucleo.log,
      verde_vecinas.log, tsc.log, npm_test.log y build.log (ESTADO.txt: 0 F, 0 omitidas).
- [x] T111 CURVAS-EN-MEMORIA (MEJ33b; hallazgo del recorrido de T96, T97 y T100): `Workspace.public()` da
      `curvas_cabecera` (las máximas cuyas curvas tiene el servidor en memoria) y `EspacioRespuesta` lo declara;
      `tablaMaxima.curvasEnMemoria` decide en `AjusteCabecera.tsx` si se piden las curvas y la máxima con central o se
      dice «Para ver las curvas de esta máxima, vuelva a buscarla.». (RF-135)
      Hecho cuando: rojo por aserción y verde con tests/test_web_api.py y frontend/test/tablaMaxima.test.mjs (086:RF-135),
      npm test y tsc, y el contrato regenerado (`tools/generar_contrato_api.py --check`).
      Hecho el 2026-11-21 (MEJ33b de d8): rojo por aserción sobre el árbol de MEJ33 y verde (293 y 9 pruebas, 0 F, 0
      omitidas), npm test 335/335, tsc, build y contrato sin deriva; en navegador real, dos recorridos seguidos en la misma
      web dan 0 errores HTTP y 0 de consola (antes, 8 por carga) y siguen pintando las curvas. Evidencia:
      `D:/csg/PM_IMPL/MEJ33_WEB/` (rojo_b.log, verde_b.log, npm_test_b.log, tsc_b.log, recorrido/t111/).
- [x] T112 FLECHAS-CON-SERVIDOR-LENTO (CI de 14f92ddd: F01 falló con el foco fuera de la opción elegida): la alternativa
      de entrada marca la opción al elegirla y descarta las respuestas de elecciones anteriores. (RF-106)
      Hecho cuando: `frontend/test/e2e/f01_vnr.e2e.mjs` (086 F-12, servidor lento) en rojo por aserción con el
      componente anterior y en verde con el nuevo, y el recorrido entero de F01 en verde.
      Código, 2026-11-24 (d8): `InputsPanel.tsx`, `elegido` y `pedidoModo` en `setMode`.
      Hecho el 2026-11-24 (d8): rojo por aserción con el InputsPanel de HEAD (`aria-checked` «false» donde se esperaba
      «true»: la opción no se marca hasta que responde el servidor), D:/csg/PM_IMPL/N12/t112/e2e_rojo.log; verde con
      el arreglo, F01 entero (3 passed), D:/csg/PM_IMPL/N12/t112/e2e_verde.log; `npm test` en verde
      (D:/csg/PM_IMPL/N12/front_unit.log).
