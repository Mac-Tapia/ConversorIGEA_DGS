# Spec 082 — El oráculo calcula todo lo del modelo, y por fases

Estado: implementada · Fecha: 2026-11-03

## Contexto y objetivo

Órdenes del usuario, 2026-11-03: «el oráculo debe hacer también cálculo desequilibrado», «el oráculo
debe hacer todos los tramos y SED de todos los alimentadores, nada debe ser omitido», «no debe ignorar
el oráculo nada» y «todo esto debe incluirse en los spec y debe implementarse en el proyecto conversor,
esto debe aplicarse ya, es de mejora continua universal».

La spec 057 dejó el oráculo equilibrado por escrito, y con Electro Oriente lo que se corrigió fue
DIgSILENT (054:RF-7), no el oráculo. Medido con DIgSILENT el 2026-11-03, sobre los proyectos importados
de cada empresa:

| Alimentador | Oráculo equilibrado sin bancos | DIgSILENT desequilibrado | Efecto |
| --- | --- | --- | --- |
| TI01 de Electro Sur Este | Vmin 0,802 p.u. | Vmin 0,790 p.u. | Se importó por debajo del umbral |
| C+æ02 de Luz del Sur, 3 bancos | Vmin 0,804 p.u. con 4,63 MW | Vmin 0,934 p.u. con 4,63 MW | Se le quitó el 57 % de su demanda sin motivo |

El oráculo por fases, con los bancos, queda a +0,00 y −0,34 puntos de media de DIgSILENT, con un
máximo de 2,5 y 1,3 puntos, frente a los 10 puntos de media de C+æ02 sin bancos. El flujo equilibrado de DIgSILENT deja sin calcular las SED
monofásicas (TI01: 5,09 MW en cabecera para 6,13 MW de carga), y por eso no sirve de comparación en
DIgSILENT, solo aquí.

La sesión que midió la entrega TXT (96 alimentadores, sin bancos) no halló pérdidas en lo que entra a
la red, y sí estas omisiones en el código: tramos sin tipo o sin impedancia, SED, cargas y maniobras
sin barra, y todos los bancos.

## Usuarios / actores

- El operador, que importa una red sin que el oráculo le cambie la demanda por lo que no calculó.
- Quien trae otra distribuidora: TXT, MDB o VNR-GIS, sin ningún ajuste por empresa.

## Historias de usuario

- Como operador, quiero que el oráculo diga la misma tensión que DIgSILENT dirá, para no importar una
  red que está por debajo del umbral ni reducir una que no lo necesita.
- Como revisor, quiero ver por clase cuántos elementos del modelo entraron en la red calculada.

## Requisitos funcionales (EARS)

- RF-1: SI un tramo no tiene tipo o su impedancia es nula o negativa, ENTONCES EL SISTEMA lo calculará como una conexión y mantendrá el hallazgo de error que lo nombra.
- RF-2: EL SISTEMA calculará todo elemento citado por el modelo, también el que cuelgue de un nodo sin definir o la maniobra que no apunte a un extremo de su tramo, y lo anotará.
- RF-3: EL SISTEMA informará, por clase de elemento, cuántos hay en el modelo y cuántos entraron en la red calculada.
- RF-4: EL SISTEMA calculará cada banco de condensadores con la potencia que escribe el DGS y en el estado de servicio que trae el modelo.
- RF-5: DONDE un alimentador tenga tramos o cargas de menos de tres fases, EL SISTEMA sacará el veredicto del flujo desequilibrado.
- RF-6: MIENTRAS calcule por fases, EL SISTEMA pondrá cada carga en sus fases y conservará el transformador de cada SED, sea cual sea su número de fases.
- RF-7: MIENTRAS calcule por fases, EL SISTEMA informará la tensión mínima de cada fase, medida solo en las barras que tienen esa fase.
- RF-8: DONDE el veredicto salga del flujo desequilibrado, EL SISTEMA informará también lo que da el flujo equilibrado.
- RF-9: SI el flujo declara convergencia y alguna barra alimentada queda sin tensión, ENTONCES EL SISTEMA lo tratará como no convergido.
- RF-10: DONDE una red unida tenga tramos o cargas de menos de tres fases, EL SISTEMA calculará sus islas con el flujo desequilibrado.
- RF-11: CUANDO corrija la demanda antes de importar (spec 057, 080:RF-45), EL SISTEMA medirá cada factor con el mismo flujo y los mismos bancos del veredicto.
- RF-12: EL SISTEMA aplicará estas reglas a cualquier fuente y distribuidora, sin ningún dato ni condición de una empresa.
- RF-13: EL SISTEMA dejará una comprobación permanente que falle si una clase de elemento del modelo no entra en la red calculada.
- RF-14: EL SISTEMA quedará contrastado con el flujo desequilibrado de DIgSILENT en un alimentador de cada fuente con fases, con un error medio de tensión de 0,5 puntos o menos.

## Fuera de alcance

- Los reguladores con su tomas en movimiento: el DGS los escribe en la toma neutra, y así se calculan.
- Cambiar el DGS: el escritor no cambia. Su demanda solo cambia cuando la corrección de RF-11 da otro factor.
- La calibración de «Sin proyecto», que sigue en DIgSILENT (specs 006, 015, 035).

## Relación con otras specs

- Deja sin efecto la exclusión de 057 («el oráculo sigue siendo equilibrado»), que al estar cumplida no crece.
- Se apoya en 054:RF-7 y usa la corrección de 080:RF-43 y RF-45, de la que depende: se integra después de la 080.
- La 081 decide qué hace la importación con el veredicto; esta spec, cómo se calcula el veredicto.

## Criterios de aceptación

- Un modelo sintético con un elemento de cada clase cuadra su recuento, en las dos disposiciones de export.
- Un ramal monofásico da en su fase una caída mayor que el flujo equilibrado.
- TI01 y C+æ02 reimportados y en Caso base, con su demanda ya corregida con este flujo.
