# Tareas — Spec 086

## F0 Decidir e integrar

- [ ] T1 Registrar las decisiones D1 a D7 del usuario, con fecha, en `spec.md`.
  Hecho cuando: D1 a D5 están respondidas; D6 y D7 tienen responsable.
- [ ] T2 Integrar `feat/decisiones-usuario`, `entrega/042-doble-terna`, `entrega/083-calibracion` y lo que falte de `fix/acopladores-con-fases`, con una ventana acordada con las otras sesiones. (RF-45)
  Hecho cuando: `git cherry` no da trabajo pendiente en ellas, y suite completa con las nueve variables y `CSG_MCP_PYTHON`, sin omitidas ni fallos, sobre esa revisión.
- [ ] T3 Pasar a `main`, `pip install -e .`, compilar, reiniciar la web y aplicar el modelo provisional. (RF-45)
  Hecho cuando: la web muestra el aviso provisional con sus cifras y `test_entry_points_instalados_coinciden_con_pyproject` pasa.
- [ ] T4 Aclarar `factor_seguridad_set` en `config/perfiles/electro_dunas.json:64` (1,0 frente a un comentario de 1,25) y corregir lo que confirme el usuario. (RF-45)
  Hecho cuando: el perfil coincide con su comentario.
- [ ] T5 Decidir RF-42 de la 042 con la cabecera compartida frente a la regla «siempre una solución».
  Hecho cuando: el caso produce una solución con su aviso y prueba, o el usuario acepta el comportamiento actual.

## F1 Datos que no se pierden (`v1/datos`)

- [x] T6 Escritura duradera, espacio dañado y rutas conservadas. (RF-1, RF-2, RF-3)
  Hecho cuando: pruebas de JSON truncado y de unidad ausente: el espacio se ve, se puede restaurar y ninguna ruta se pierde al guardar.
  Por la API; el botón y el aviso en la interfaz siguen en T35.
- [ ] T7 Migraciones, rutas relativas e identidad estable. (RF-4, RF-5, RF-6, RF-7, RF-8)
  Hecho cuando: todos los espacios actuales migran sobre una copia sin perder nada; mover la carpeta conserva los espacios; escribir en otra unidad funciona.
  Hecho, salvo una parte: la migración sobre copia se midió con la raíz de ejecución actual (2 espacios, sin perder nada). Falta repetirla con los de `output/web`, que el agente no debía tocar, justo antes de T9.
- [x] T8 Trabajos interrumpidos, copia y restauración. (RF-9, RF-10, RF-47)
  Hecho cuando: matar el proceso a media corrida deja el trabajo como interrumpido; restaurar una copia devuelve el mismo estado.
  Por la API y por `tools/copia_datos.py`; verlo en la interfaz sigue en T35. El corte de luz real es la T33.
- [ ] T35 Ver en la interfaz lo de T6 y T8: espacio dañado con su botón de restaurar, entradas no disponibles, trabajo interrumpido con su registro y aviso de copia vieja. (RF-2, RF-3, RF-9, RF-47)
  Hecho cuando: los cuatro se ven y funcionan en el navegador real, en claro y oscuro.

## F2 Renombrar

- [ ] T9 [DIgSILENT] Renombrar la carpeta a `ConverterSmartGrid`, con todo parado y con ensayo previo sobre una copia. (058 T6)
  Pasos, cada uno con su comprobación y vuelta atrás: (1) comprobar que no hay procesos en esa ruta; (2) foto: `pip freeze`, `git worktree list --porcelain`, estado de cada worktree y el `.lnk`; (3) copiar `workspace.json` y `conversiones.json` fuera; (4) `Rename-Item`, sin forzar; (5) migrar las rutas con la T7, sin reescribir evidencia histórica, y renombrar runtime y caché a su nuevo hash; (6) recrear las junctions; (7) `git worktree repair` con todas las rutas a la vez; (8) **reparar `.venv` en sitio**: `-m venv .venv` y `pip install -e . --no-deps`, sin rehacerlo, porque torch no está en `requirements`; (9) crear `ConverterSmartGrid.lnk`, y retirar el viejo solo cuando funcione; (10) comprobar los espacios antes de que guarden nada, y un vínculo de DIgSILENT; (11) copiar la memoria de Claude y actualizar `ACTIVE.md` y `CLAUDE.md`; (12) suite completa. Vuelta atrás general: parar, restaurar las copias, deshacer los pasos 7 y 4. GitHub y limpieza de identidades antiguas, aparte y con orden del usuario.
  Hecho cuando: la web abre con los mismos espacios que la foto, `torch.cuda.is_available()` es verdadero y la suite pasa sin omitidas.

## F3 Veracidad, seguridad y producto

- [ ] T10 Reproducir y corregir el informe con flujo de otra corrida, y el que elige el estudio de otro alimentador. (RF-11, RF-12) (`v1/informes`)
  Hecho cuando: con «Con proyecto» fallido, cancelado o agotado, el informe no usa datos viejos sin decirlo; prueba con doble.
- [ ] T11 «Caso base» al retomar y su huella. (RF-13, RF-14) (`v1/informes`)
  Hecho cuando: retomar verifica; el guion escribe `caso_base_huella` y la guarda de 081 actúa.
- [ ] T12 Edición de producto: sin suite nocturna, sin entrenar, oculto lo que no se vende. (RF-15, RF-16) (`v1/producto`)
  Hecho cuando: pruebas en las dos ediciones, y comprobación en el navegador real.
- [ ] T13 Host, Origin, token y escucha. (RF-17, RF-18, RF-19, RF-20) (`v1/seguridad`)
  Hecho cuando: pruebas negativas por cada una, también en WebSocket; la web sigue funcionando en el navegador real.
- [ ] T14 Leaflet propio, política de contenido y sin salida a la red por defecto. (RF-21, RF-22) (`v1/seguridad`)
  Hecho cuando: con la red cortada, todo el flujo funciona y el mapa abre; una prueba recorre las salidas conocidas.
- [ ] T15 Tareas por efecto, guiones con confirmación, reintentos e independencia de GPU. (RF-23, RF-24, RF-25, RF-26, RF-27) (`v1/producto`)
  Hecho cuando: una prueba exige que cada tarea declare su efecto; sin CUDA, el trabajo sigue con aviso.

## F4 Universal (`v1/universal`)

- [ ] T16 Moneda, web sin casos y valores por defecto. (RF-28, RF-29, RF-35)
  Hecho cuando: una prueba recorre el núcleo y la web con la lista de términos, y no halla ninguno.
- [ ] T17 Esquema, `validar-perfil` y `docs/PERFIL_EMPRESA.md`. (RF-30)
  Hecho cuando: un perfil incompleto dice qué falta y qué función afecta.
- [ ] T18 Plantillas neutras, perfil plantilla y perfil ficticio. (RF-31, RF-32)
  Hecho cuando: con el perfil ficticio y sin modelos de empresa se convierte y se genera un informe.
- [ ] T19 Lista de lo que entra en el paquete, términos prohibidos y pesos. (RF-33, RF-34)
  Hecho cuando: un candidato con un término o peso ajeno se rechaza; comentarios según D5.

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
