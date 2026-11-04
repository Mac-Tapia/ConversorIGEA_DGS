# Tareas — Spec 086

## F0 Decidir e integrar

- [ ] T1 Registrar las decisiones D1 a D7 del usuario, con fecha, en `spec.md`.
  Hecho cuando: D1 a D5 están respondidas; D6 y D7 tienen responsable.
- [x] T2 Integrar `feat/decisiones-usuario`, `entrega/042-doble-terna`, `entrega/083-calibracion` y lo que falte de `fix/acopladores-con-fases`, con una ventana acordada con las otras sesiones. (RF-45)
  Hecho cuando: `git cherry` no da trabajo pendiente en ellas, y suite completa con las nueve variables y `CSG_MCP_PYTHON`, sin omitidas ni fallos, sobre esa revisión.
  Evidencia: suite sobre ab8efa9c, 6 753 aprobadas, 0 omitidas, 0 caídas y 2 fallos de pruebas que leían un texto ya cambiado; corregidos en c7c04175 y c79013c2, que solo tocan esas pruebas, y pasan aparte. La suite limpia de cierre es la T31. `entrega/083-calibracion` queda sustituida por la 042; `fix/*`, ya presentes; 042:RF-48 y la 087 esperan prueba en DIgSILENT.
- [x] T3 Pasar a `main`, `pip install -e .`, compilar, reiniciar la web y aplicar el modelo provisional. (RF-45)
  Hecho cuando: la web muestra el aviso provisional con sus cifras y `test_entry_points_instalados_coinciden_con_pyproject` pasa.
  Evidencia: `main` en c79013c2; navegador real en el 8765, con el aviso «examen 0,964 de 0,98 y F1 0,918 de 0,95 […] sellada 0,860; sintéticas 0,829; se cuela 0,0 %».
- [x] T4 Aclarar `factor_seguridad_set` en `config/perfiles/electro_dunas.json:64` (1,0 frente a un comentario de 1,25) y corregir lo que confirme el usuario. (RF-45, RF-51)
  Hecho cuando: el perfil coincide con su comentario.
  Evidencia: `tests/test_set_nueva.py::test_el_factor_de_la_set_depende_de_si_se_cuenta_la_tasa`; 1,25 sin tasa y 1,0 con ella, como decidió el usuario.
- [ ] T5 Cabecera compartida: proponer solución en vez de quedarse sin obra (decidido por el usuario, 2026-11-04). La implementa la sesión de la 042 en `entrega/042-nivel`, sobre 042:RF-53.
  Hecho cuando: el caso produce una solución con su aviso y prueba, medida en DIgSILENT.

- [x] T37 El informe separa lo que causa la carga del déficit que ya existía. (RF-48, RF-49, RF-50) (`v1/deficit`)
  Hecho cuando: con una barra baja que no empeora, el informe la lista como déficit previo con su tensión y barra, y nunca dice «en norma» sin ese matiz.
  Evidencia: pruebas con dobles, sin DIgSILENT, en `tests/test_deficit_previo.py`, `tests/test_informe_docx.py`, `tests/test_informe_corrida.py`, `tests/test_casos_por_anio.py` y `tests/test_obras_pf_guion.py`. La confirmación en DIgSILENT queda en las corridas de la F6, y verlo en el navegador real, sin hacer.

- [ ] T39 El factor 1,25 en el elevador y en el regulador, cuando no cuentan la tasa de crecimiento. Lo implementa la sesión de la 042 en su rama. (RF-53)
  Hecho cuando: prueba de cada uno con y sin dato en el perfil; el dimensionado se ve en el informe.
- [ ] T38 Obra para el déficit previo, con su costo aparte, con o sin obra para la carga. La implementa la sesión de la 042 en su rama. (RF-52)
  Hecho cuando: «ya cumple» no se queda sin obra si hay una barra previa baja; prueba con doble y medida en DIgSILENT sobre SI112; el informe separa los dos costos.

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

- [ ] T20 Trasladar a datos del paquete lo que se lee del checkout. (RF-36)
  Hecho cuando: el programa corre desde un wheel fuera del repositorio y las líneas base siguen iguales.
- [ ] T21 Instalador sin internet, núcleo y complemento de IA, datos aparte, actualización con vuelta atrás. (RF-36, RF-37, RF-38, RF-39)
  Hecho cuando: instalar, actualizar y volver atrás en una máquina virtual limpia conserva los datos.
- [ ] T22 `doctor`, registro rotativo, paquete de soporte y versión única. (RF-40, RF-41, RF-42, RF-43)
  Hecho cuando: quitar cada requisito opcional dice qué función afecta; el paquete de soporte no lleva datos del cliente.
- [ ] T23 Manuales, hoja de seguridad, `THIRD_PARTY_NOTICES`, SBOM, `pip-audit`; corregir README y `MANUAL_COMANDOS` (órdenes rotas en `:629,676`). (RF-44)
  Hecho cuando: una persona ajena instala y convierte siguiendo el manual; auditoría sin vulnerabilidades graves.

## F6 Corridas reales sobre el candidato congelado

Cada corrida: `tools/sistema_web.py` y el navegador, en serie, con proyectos de prueba nuevos. `D=D:/BaseDatosElectroDunas/referencia_retirada_20261102`.

- [ ] T24 [DIgSILENT] R1, CA101 + PE104, TXT: `--red CA101 PE104 --grupo PRUEBA_CA101_PE104 --demanda-dir $D --periodo 2026-07 --reconvertir`, luego en el navegador calibración, cargas, obras, transferencia e informes. (RF-45)
  Cierra: 008 T7, 011 T19, 013 T7, 017 T13, 017 T19, 028 T11, 037 T4, 058 T7, 078 T6, 084 T9, 081 T22; 012 T13 si hay libro real. Hecho cuando: cabecera dentro del 1 %, `VALIDO`, `m:Psum`; «Sin proyecto» intacto; Word y Excel revisados por el usuario.
- [ ] T25 [DIgSILENT] R2, SI213 y PN107, MDB, uno por vez, con cargas por el navegador. (RF-45)
  Cierra: 007 T11, 016 T18, 028 T11, 081 T20. Hecho cuando: variación por carga, barra más cercana, base activa al terminar.
- [ ] T26 [DIgSILENT] R3, Pisco y una SET, TXT: `--zonal Pisco --demanda-dir $D --periodo 2026-07 --reconvertir`, luego `--set <SET>`. (RF-45)
  Cierra: 028 T15, 083 T3, 081 T10 a T13, 078 T6, 027 T22 (borrador). Hecho cuando: instante en 60 kV, LT y centrales; huella igual antes y después; estado veraz; los alimentadores sin medidor, con su motivo.
- [ ] T27 [DIgSILENT] R4, NA203 + NA205, TXT, proyecto nuevo, con los dos criterios de fijas, cargas y obras. (RF-45)
  Cierra: 039 T4, 042 T6, 052 T4, 084 T8, 017 T14, 073 T8, 073 T10. Hecho cuando: NA203 con «máximo del mes» da 7 707,5 kW y 3 725,5 kvar (039); SET en 0,94–1,06 pu y fuera del trazado; oráculo frente a DIgSILENT; valle.
- [ ] T28 [DIgSILENT] R5, NJA202 y R205, VNR-GIS de Electro Oriente. (RF-45, RF-46)
  Cierra: 051 T3, 055 T2, 056 T3, 005 T12, 081 T16. Hecho cuando: cabecera dentro del 1 %; sistemas y SET; vocabulario y carpeta de la empresa. R205 frente a 0205 sin suponer alias.
- [ ] T29 Navegador: 067 T8, 077 T7, 073 T10, y escritorio con pantalla estrecha. (RF-45)
  Hecho cuando: todo se ve funcionar en el navegador real, en claro y oscuro.
- [ ] T30 [DIgSILENT] R6, solo si el asistente se vende como beta: un alimentador, una SET y una carga por órdenes escritas. (RF-45)
  Cierra: 070 T9, 070 T10, 067 T9, 026 T12, 078 T7. Hecho cuando: los informes salen de las órdenes, con confirmación.

No hacen falta para la 1.0: 025 T21 (PA217 vetado; reformular según D6), 027 T14 y T29 a T31, 028 T6, 044 T4, 045 T4, 048 T4, 049 T4, 070 T11, 075 T6, 079 T7, 081 T14. 065 T12 pasa a ser el conjunto R1 a R5.

## F7 Aceptación y v1.0

- [ ] T31 Suite completa sin omitidas sobre el candidato, con líneas base y determinismo. (058 T5, 025 T22, 065 T13) (RF-46)
  Hecho cuando: cero fallos, cero omitidas.
- [ ] T32 [DIgSILENT] Instalación en un equipo limpio con su DIgSILENT, y corrida de otra empresa de punta a punta hasta el informe. (RF-46)
  Hecho cuando: sin tocar el código, solo su perfil, sale un informe que un ingeniero da por bueno.
- [ ] T33 [DIgSILENT] Ensayo de corte de luz a media calibración y a media importación. (RF-46)
  Hecho cuando: ningún espacio se pierde, el trabajo se ve interrumpido y se retoma sin trabajo repetido ni datos mezclados.
- [ ] T34 Asesoría legal cerrada, repositorio de producto, licencia, y etiqueta `v1.0.0` con sus notas. (D3, D7)
  Hecho cuando: el usuario da la orden de publicar.

## Después de la 1.0

002 T7 a T12; 043 T9; 045 T3; 047 T4, T7, T8; 048; 049 (cortocircuito y protecciones, lo primero que pedirá un cliente); 050 T1b a T5b; 068 T7, 069 T7, 085 T6 (campaña de GPU); 071 T5; 072 T3, T9, T11; 074; 027 T11, T26.
