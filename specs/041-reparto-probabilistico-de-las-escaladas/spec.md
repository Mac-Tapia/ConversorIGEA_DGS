# Spec 041 — Reparto probabilístico de las SED escaladas

Estado: cumplida · Fecha: 2026-10-31 · Origen: petición del usuario, 2026-10-31, al recalibrar
NA203 («ahí debes aplicar la estocástica, incertidumbre y probabilidad en la escalabilidad»;
«la probabilidad debe ser de acuerdo de la mayor potencia a menos de las escaladas»).
Respuestas del usuario: lo incierto es la carga de cada SED escalada; en DIgSILENT se escribe el
P50 y las bandas van en el informe.

## Contexto y objetivo

Hoy todas las SED escaladas (las que no están en la tabla cruzada) llevan un mismo factor sobre
su kVA (spec 006, 015:RF-54): el reparto es una sola foto, como si todos los transformadores
estuvieran igual de cargados en la máxima. No lo están, y nadie sabe cuánto lleva cada uno: una
SED que en la realidad va al 120 % puede salir al 70 % y el estudio no lo avisa.

Se quiere tratar la carga de cada escalada como una variable aleatoria, con más probabilidad de ir
cargada cuanto mayor es su potencia: muchos repartos posibles, todos cuadrados a la misma
cabecera, y de ellos la mediana (P50), que es lo que se escribe, y las bandas y probabilidades por
SED, que van al informe.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se calibra o se recalibra, EL SISTEMA dará a cada SED escalada un factor de
  utilización propio, aleatorio, y generará N repartos.
- RF-2: EL SISTEMA ordenará las escaladas de mayor a menor potencia instalada (kVA) y dará a las
  de mayor potencia más probabilidad de ir cargadas: la utilización esperada de cada una crece con
  su lugar en ese orden, y la suma de todas sigue siendo la que pide la cabecera.
- RF-3: EL SISTEMA tomará la dispersión de los factores de datos reales del mismo alimentador o
  proyecto: la de la utilización (kW / kVA) de las SED fijas en el instante de la máxima, y de
  ellas también cómo cambia la utilización con la potencia (RF-2). SI hay menos fijas que el
  mínimo para estimarlas, ENTONCES usará las del perfil de empresa
  (`calibracion.reparto_probabilistico`); sin ninguna de las dos, no hará el reparto
  probabilístico y lo dirá (no se supone ningún número, constitución P13).
- RF-4: EL SISTEMA cuadrará la P de cada reparto a la cabecera (±1 %) partiendo del factor del
  cuadre determinista, con la Q de las escaladas de ese cuadre y las fijas a escala 1 sin
  tocarlas; el P50 (RF-5) se cuadra entero, P y Q, como cualquier calibración (035:RF-28).
- RF-5: EL SISTEMA escribirá en «Sin proyecto» el reparto P50: por SED, la mediana de su P en los
  N repartos, cuadrado de nuevo a la cabecera; es el que queda en DIgSILENT y se valida como hoy.
- RF-6: EL SISTEMA dirá en el informe y en la web, por SED escalada, su potencia, su P05, P50 y
  P95 de kW y de cargabilidad, y la probabilidad de pasar del 100 % de su transformador; y por
  alimentador, la probabilidad de que alguna barra quede fuera de la banda de tensión del perfil.
- RF-7: EL SISTEMA será reproducible: con la misma semilla (guardada en el informe) los N
  repartos y sus resultados serán los mismos.
- RF-8: EL SISTEMA correrá los N flujos en el mismo caso, sin crear casos ni variaciones nuevas,
  y dejará el caso con el reparto P50 al terminar o al cancelar.

SED con medida (usuario, 2026-10-31: «esto debe ser cuando no existan cargas medidas
suministradas en actualización de cargas en bloque; en algún momento se cargará un archivo de
todas las SED escaladas con sus mediciones reales, donde deberán ser fijas como las tablas
cruzadas»; «es 3.1 demanda en bloque»)

- RF-9: SI una SED tiene su demanda medida en el libro de «3.1 Demandas en bloque» del proyecto,
  ENTONCES EL SISTEMA la calibrará fija a escala 1 con esa medida, como las de la tabla cruzada,
  y no entrará al reparto probabilístico; sin escaladas sin medida, no hay sorteo. Una demanda
  cambiada a mano en DIgSILENT sigue mandando (014:RF-10).

Decisiones (aprobadas por el usuario el 2026-10-31, «haz las correcciones e implementación
correcta según ya manifestado»): N = 200 por defecto (`calibracion.reparto_probabilistico.n` lo
cambia); factor lognormal de media 1, con la media creciente con el kVA (potencia); mínimo de 5
fijas para estimar dispersión y pendiente.

## Fuera de alcance

- La incertidumbre de la medida de cabecera (el usuario eligió solo la de cada SED).
- Alimentadores con central (021): su reparto es por zonas.
- Escribir en DIgSILENT otros percentiles (P95 en casos propios).

## Criterios de finalización

- `grep -rnoE "041:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-9.
- NA203 recalibrado desde la web con el reparto probabilístico: el informe da P05/P50/P95 por SED
  ordenadas por potencia y la probabilidad de sobrecarga, y la misma semilla repite los mismos
  números.
