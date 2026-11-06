# Spec 083 — El oráculo antes de calibrar y recalibrar

Estado: implementada · Fecha: 2026-11-03 · Origen: petición del usuario

## Contexto y objetivo

Usuario, 2026-11-03: «debería ingresar el PINN como oráculo antes de calibrar y recalibrar para que sean más rápidas las
calibraciones en DIgSILENT» y «de qué sirve si lanzas de nuevo con los mismos problemas, no es eficiente». Hasta hoy cada intento
de la calibración era un flujo en DIgSILENT, hasta 30 por pasada, en un sistema de 22 alimentadores y unas 5 000 barras.

La búsqueda de factores corre primero en el oráculo y DIgSILENT arranca de lo hallado. DIgSILENT sigue siendo la referencia: el
oráculo propone el arranque, nunca da una calibración por buena (024, principio 1). No se entrena ningún modelo.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se calibra o recalibra un proyecto, EL SISTEMA buscará antes con el oráculo el factor de cada alimentador, con la
  misma búsqueda de la calibración, y DIgSILENT arrancará de esos factores.
- RF-2: EL SISTEMA medirá en el oráculo cada alimentador como lo que consumen sus cargas más las pérdidas de sus ramas.
- RF-3: DONDE haya un PINN promovido cuyo dominio incluya la red, EL SISTEMA lo usará para la tensión; SI la red está fuera de su
  dominio (071:RF-2), ENTONCES decidirá el flujo físico, y dirá cuál usó.
- RF-4: SI el oráculo no converge o falla, ENTONCES EL SISTEMA lo dirá y calibrará con el arranque de siempre: nada se bloquea.
- RF-5: EL SISTEMA guardará en el informe el modelo usado, sus evaluaciones, sus segundos y los factores hallados, para medir la
  ganancia en flujos de DIgSILENT.
- RF-6: EL SISTEMA no usará este arranque en un alimentador con central en su tramo, cuyas zonas se miden de otra forma: lo dirá.
- RF-7: SI un flujo no converge y ninguno ha convergido, ENTONCES EL SISTEMA probará las escaladas casi en cero; SI tampoco converge,
  la causa no son las escaladas: lo señalará y pasará al remedio siguiente sin gastar los medios caminos. En Pisco (2026-11-03), 15
  de 18 flujos no convergían con 20 SED fijas por encima de su transformador.
- RF-8: CUANDO el guion del sistema termina sin calibración válida y hay SED fijas con transformador propuesto, EL SISTEMA pedirá
  esos transformadores (020) y repetirá la calibración, sin que el operador lo pida.
- RF-9: CUANDO se recalibra, EL SISTEMA arrancará del factor de la última calibración de ese alimentador si el oráculo no halló uno.
- RF-10: EL SISTEMA dejará quieto el factor del alimentador que ya está dentro de tolerancia mientras los demás cuadran.
- RF-11: EL SISTEMA mantendrá cada factor dentro del intervalo donde ya sabe que está la solución (por debajo y por encima del objetivo);
  con otro remedio, ese intervalo se olvida porque la red ya no es la misma.
- RF-12: SI el error de los alimentadores deja de bajar en el cuadre conjunto, ENTONCES EL SISTEMA dará el paso con Broyden, que tiene en
  cuenta cómo un alimentador afecta a otro.
- RF-13: EL SISTEMA hará todo esto igual con uno, varios alimentadores, una SET o un sistema, y dirá en el informe qué método usó.
- RF-14: CUANDO un libro de clientes no traiga «maestro_lib», EL SISTEMA hallará la hoja de cada cliente por su contenido (su código en la
  cabecera de la hoja) y leerá su registro en las dos disposiciones: «FECHA, HORA, EA, ERI, POT» y «día, hora» con el último grupo «EA, ERI,
  ERC, Pot», en la fecha y hora de la barra. En Pisco (2026-11-03) los libros de enero a mayo no lo traen: las fijas iban con la potencia del
  mes, no con la coincidente, y en AL209 y PA217 sumaban más que la medida y pasaban todas a escaladas. Usuario: «la tabla cruzada de fijas
  debe ser también en la máxima fecha de las barras SET».
- RF-16: EL SISTEMA resolverá el oráculo con cualquiera de sus motores (Z-bus, Anderson, Newton con KLU, power-grid-model y OpenDSS) sobre la
  misma red ya factorizada, con la misma salida. Usuario, 2026-11-03: «estas opciones más debes implementar» y «debe adaptar lo ya existente».
- RF-17: POR DEFECTO EL SISTEMA usará el Z-bus y, si no converge, Newton, por lo medido en 5 000 barras: Anderson no mejoró en ningún nivel de
  carga en que convergió; `CSG_MOTOR_FLUJO` elige otro, y el informe dice cuál decidió.
- RF-18: SI un motor no está instalado, ENTONCES EL SISTEMA seguirá con otro: nada se bloquea por un motor.
- RF-19: EL SISTEMA dará con todos los motores las mismas tensiones en una misma red, dentro de 10⁻³ p.u.
- RF-20: DONDE haya oráculo, EL SISTEMA cuadrará y leerá en él las muestras del reparto probabilístico (041) y DIgSILENT confirmará solo el P50, que
  es lo que se escribe; sin oráculo, las muestras irán a DIgSILENT como siempre. Cambia 041:RF-8 en dónde corren los N flujos. En Pisco (2026-11-03), cuando
  por fin cuadró, eran 200 muestras por alimentador con 5 o más fijas, a unos 8 s por flujo: más de una hora. Usuario: «por qué demora la calibración si hemos
  implementado para su mejora».
- RF-21: EL SISTEMA guardará en el informe los segundos de cada etapa de la calibración y los dirá mientras corre, para saber dónde se va el tiempo sin suponerlo.
- RF-22: EL SISTEMA apagará y encenderá las variaciones una sola vez para marcar las cargas de todos los alimentadores, no una por alimentador: cada vez DIgSILENT
  rehace la red. En Pisco (2026-11-03) una calibración pasó minutos sin llegar a su primer flujo.
- RF-23: SI el oráculo no cuadró el arranque, ENTONCES EL SISTEMA lo probará con los factores ya cuadrados en DIgSILENT y, si converge, llevará a él las
  muestras del reparto probabilístico. En Pisco (2026-11-03) el arranque no convergió y las 200 muestras de cada alimentador fueron a DIgSILENT: más de una hora.
- RF-24: EL SISTEMA guardará la entrada del oráculo de la última calibración (grafo, nodos de las SED, ramas y factores) junto a la cola de DIgSILENT del
  equipo, la releerá y dirá dónde quedó o por qué no, para reproducir sin DIgSILENT por qué no converge; nunca va a git.
- RF-25: CUANDO las muestras del reparto probabilístico vayan a DIgSILENT, EL SISTEMA parará al llegar al tope de tiempo
  (`calibracion.reparto_probabilistico.tope_s` del perfil; sin él, 180 s por alimentador) con al menos 20 muestras, escribirá el P50 de las hechas y
  dirá cuántas fueron y por qué. Usuario, 2026-11-03: «si no te hago consulta seguimos esperando algo que nunca hubiera… debes evitar esas cosas».
- RF-26: CUANDO empieza una calibración, EL SISTEMA dejará en 0 los ajustes del flujo que cambian lo que consumen las cargas (`iopt_lev`, `iopt_pq`) que
  vengan de antes, en «Sin proyecto» y en «Con proyecto», y lo dirá; los remedios pueden volver a ponerlos. El caso del operador no se toca. En Pisco (2026-11-03) `iopt_lev=1` heredado hacía que 19 alimentadores cuadraran y
  ninguno quedara válido: SE30037 escribía 2 524 kW y consumía 1 578 kW.
- RF-27: EL SISTEMA guardará, al terminar cada calibración aunque falle o se cancele, lo que escribió en cada carga; una carga que sigue con eso no es un
  cambio manual (014:RF-10). En Pisco, lo escrito por corridas que no quedaron registradas salía «cambiado a mano» en 73 cargas de AL209 y tapaba a sus
  clientes fijos.
- RF-28: CUANDO el oráculo converge, EL SISTEMA arrancará DIgSILENT de sus factores aunque no cuadre algún alimentador, y nombrará el que no puede
  cuadrar porque sus fijas más sus pérdidas ya pasan de la medida, con las dos cifras. En Pisco (2026-11-03) PA219 (fija de 4 163 kW, medida 4 289 kW)
  quedaba un 2,2 % arriba con sus escaladas casi en cero, y por él se tiraban los factores de los otros 17, que ya estaban dentro del 1 %.
- RF-29: CUANDO empieza una calibración, EL SISTEMA dejará activas en «Sin proyecto» y «Con proyecto» las variaciones del conversor del proyecto
  (`SED_NTP_`, `Fichas_`), y lo dirá si alguna estaba apagada. Una orden que termina con fallo restituye el estado (064:RF-5) y las apaga si las activó ella.
  Pisco (2026-11-03): cada calibración no válida deshacía los transformadores puestos; la siguiente veía SE30037 con 300 kVA en vez de 6 × 630 kVA, no
  convergía y los proponía de nuevo, iguales.
- RF-30: SI un alimentador sigue por encima de su medida con las escaladas al mínimo (por debajo del 5 % de su factor inicial) y el exceso no pasa del 10 % de
  sus fijas, ENTONCES EL SISTEMA bajará sus fijas en esa proporción y lo dirá por SED, con lo que tenían y lo que quedan; con más exceso no las toca y lo
  nombra (RF-28). Fijas y medida de cabecera son dos medidas y pueden no ser coherentes. PA219 (Pisco, 2026-11-03): cliente 4 163 kW más 216 kW de pérdidas
  frente a 4 289 kW medidos en cabecera. Usuario: «deben entrar todos, analizar las mediciones y corregirlas».
- RF-15: EL SISTEMA comparará la Q escrita con el margen que deja la precisión de DIgSILENT en el modo P y cos φ (10⁻⁵ de la P), porque con
  un factor de potencia casi 1 un cos φ de precisión simple no reproduce una Q pequeña, y eso no es un fallo del reparto.
- RF-31: CUANDO la calibración se pide en modo automático y en DIgSILENT hay SED fijas sobre su transformador con ficha propuesta,
  EL SISTEMA pondrá esos transformadores en la misma pasada, antes de calibrar, en vez de calibrar en falso y repetir (cambia
  RF-8, que queda como respaldo). En PRUEBA_007 (2026-11-06), SE20497 pedía 1 429 kW en 160 kVA: cada calibración fallaba
  la primera vez y se repetía entera. Usuario: «debe buscar la solución, no seguir intentando».

## Fuera de alcance

- Entrenar la PINN con redes nuevas: es del gobierno de modelos (045, 071).
- Lo que modela el flujo físico (bancos, tramos, desequilibrado): spec 082.
- La corrección del oráculo al convertir una red unida (`reglas.py`).

## Fundamento

Reutiliza la búsqueda de `ajuste_cabecera.cuadrar_conjunto` (021:RF-54) y `optimizacion_oraculo.Oraculo` (052).
