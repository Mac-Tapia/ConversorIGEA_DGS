# Spec 094 — Perfil de tensión en la calibración y bancos ubicados según el perfil

Estado: aprobada · Fecha: 2026-11-06 · Origen: usuario, 2026-11-06, AL209 con Cemento Inka: «los perfiles de tensión se
deben evaluar en la calibración y recalibración; en base de ese perfil se deben plantear las ubicaciones óptimas, viendo
todo el alimentador, o los alimentadores si es por sistema».

## Contexto y objetivo

En AL209 (2026-11-06) la escalera ponía el banco en la barra de la carga o en la más baja, y la búsqueda del oráculo
(087:RF-55) amontonaba los bancos en el extremo del alimentador: barras que eléctricamente son el mismo punto. El
perfil de tensión (tensión de cada barra de media frente a su distancia a la cabecera) no se calculaba ni se guardaba
con la calibración, y nadie lo usaba para ubicar bancos. Con el perfil de AL209 (de 0,9998 a 0,9498 p.u. en 20,85 km),
tres bancos de 450 kvar en las barras donde la caída llega a 1/3, 2/3 y el total dejan la misma tensión mínima con
menos pérdidas (359 kW frente a 363 kW de la regla 2/7-4/7-6/7).

## Requisitos funcionales (EARS)

- RF-1: CUANDO termina una calibración o una recalibración, EL SISTEMA calculará en DIgSILENT el perfil de tensión de
  cada alimentador calibrado: la tensión de cada barra de media y su distancia eléctrica a la cabecera.
- RF-2: EL SISTEMA guardará el perfil con la calibración, en «Sin proyecto», para que lo usen los estudios sin volver
  a leer DIgSILENT.
- RF-3: EL SISTEMA mostrará el perfil de cada alimentador en la web y en el informe del estudio, con el límite de
  tensión del perfil de la empresa.
- RF-4: CUANDO se buscan bancos para un alimentador (escalera de «Con proyecto», déficit previo, estudio), EL SISTEMA
  propondrá sus ubicaciones a partir del perfil, entre todas las barras de media del alimentador: por caída igual, por
  la regla 2i/(2n+1) de la distancia y un banco por tramo del perfil, y elegirá con el oráculo la de mayor tensión
  mínima y, a igualdad, menores pérdidas.
- RF-5: DONDE el estudio sea de un sistema (varios alimentadores), EL SISTEMA aplicará RF-1 a RF-4 a cada alimentador
  del sistema.
- RF-6: EL SISTEMA no propondrá dos bancos en barras a menos de `escalera.separacion_bancos_km` (perfil; 0,5 km si no
  lo da) por el camino eléctrico.
- RF-7: EL SISTEMA comprobará la ubicación elegida en DIgSILENT, en la máxima y en el valle (073), antes de aplicarla.
- RF-8: EL SISTEMA añadirá bancos de un módulo del perfil de la empresa (`bancos_kvar_por_tension`), uno a uno y
  ubicados por RF-4, hasta que la tensión mínima de media llegue a `escalera.tension_objetivo_pu` (1,0 p.u. si el perfil
  no lo da). Usuario, 2026-11-06: «hasta una tensión objetivo».
- RF-9: SI un módulo más sube la tensión mínima menos de `escalera.mejora_minima_pu` (0,001 p.u. si el perfil no lo
  da), o lleva alguna barra del valle por encima del límite (073), ENTONCES EL SISTEMA se detendrá ahí y dirá cuál de
  las dos razones lo detuvo y qué tensión alcanzó frente al objetivo. (AL209: con bancos se estanca hacia 0,977 p.u.)

- RF-10: EL SISTEMA calculará el perfil de RF-1 al final del flujo de calibración del conversor, sin pasos propios:
  primero el cuadre de P y después la recalibración de P y Q (035), con los bancos existentes del alimentador en
  servicio; guardará con él la P y la Q de cabecera medidas y simuladas. Usuario, 2026-11-06: «primero se hace el
  cuadre de P y después se recalibra la P y Q; debe seguir el flujo del conversor».
- RF-11: SI la Q de cabecera no queda cuadrada (AVISO_KVAR), ENTONCES EL SISTEMA marcará el perfil y las ubicaciones de
  bancos que salgan de él con ese aviso y el desvío de Q. (AL209, 2026-11-06: 2 833 kvar simulados frente a 2 668
  medidos, +6 %.)
- RF-12: EL SISTEMA no cuadrará P ni Q en «Con proyecto»: la cabecera ahí es la que da DIgSILENT al integrar las cargas
  nuevas y las obras, y con ese resultado se juzgan los bancos propuestos y su perfil. El cuadre de P y Q es solo de la
  calibración, en «Sin proyecto» (RF-10). Usuario, 2026-11-06: «en Con proyecto y obras ya no se hacen los cuadres;
  los resultados en la cabecera son reales, resultado de la ejecución en DIgSILENT».

- RF-13: EL SISTEMA juzgará cada propuesta de bancos con el perfil completo del alimentador, todas sus barras de media
  y no solo el camino a la más baja, y guardará el perfil completo antes y después de la propuesta.
- RF-14: EL SISTEMA dirá, por propuesta, si el perfil mejora: tensión mínima, barras bajo el límite, tensión máxima
  y pérdidas antes y después, y en el valle.
- RF-15: EL SISTEMA dejará en el proyecto de DIgSILENT el gráfico de perfil de tensión del alimentador (el de la
  herramienta de perfil de tensión de DIgSILENT, por alimentador) en «Sin proyecto» y en «Con proyecto», para que el
  operador compruebe con el flujo nativo lo que dice el informe. Usuario, 2026-11-06: «para plantear debe ver todo el
  perfil de tensión del alimentador y ver también si propone todo el perfil para ver si mejora; además, en DIgSILENT
  existe una herramienta para graficar el perfil de tensión, ahí se podría ver o comprobar».

- RF-16: EL SISTEMA ubicará los bancos solo sobre la troncal del alimentador (el camino más largo desde la cabecera,
  016) y sobre la troncal de cada ramal largo (el que mide desde su derivación al menos `escalera.ramal_largo_km`; 2 km
  si el perfil no lo da); cada banco más irá al eje donde más suba la tensión mínima de todo el alimentador. Usuario,
  2026-11-06: «el camino debe ser solo por la troncal y troncales de las ramas largas».
- RF-17: EL SISTEMA calculará el camino de cada barra a la cabecera sin ciclos, también con ramas de largo cero
  (acopladores, transformadores). AL209 (2026-11-06): la calibración quedó en un bucle sin fin.

## Fuera de alcance

Bancos automáticos o con escalones maniobrables. Reguladores y cambio de tomas de la SET: cuando los bancos no llegan
al objetivo, el sistema lo dice (RF-9), pero no los propone desde esta spec.

## Criterios de finalización

Cada RF citado por una prueba, suite enfocada en verde y AL209 recalibrado desde la web con su perfil guardado y los
bancos propuestos desde él, confirmados en DIgSILENT.
