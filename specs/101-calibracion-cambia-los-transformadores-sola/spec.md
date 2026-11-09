# Spec 101 — La calibración cambia sola los transformadores que impiden converger

Estado: implementada · Fecha: 2026-11-09 · Origen: usuario, 2026-11-09, calibración de CA101 + CHN102
(`20261109-152654_CSG_TXT_CA101_CHN102`): «no se acepta que no converge, todo tiene que converger, y para eso
debería hacer los cambios físicos según corresponde».

## Contexto y objetivo

La calibración de CA101 + CHN102 del 2026-11-09 terminó en FALLO_VALIDACION_NATIVA. Seis SED fijas de CA101 y una de
CHN102 piden más que su transformador: SE20701 pide 1 506 kVA y el TXT le da 50 kVA, y SE20049 pide 2 824 kVA con
500 kVA. Sin `iopt_lev` el flujo no converge, y con `iopt_lev` las cargas pasan a impedancia y no consumen lo escrito.
El guion ya proponía para cada una el transformador de la ficha NTP 370.400 (020:RF-6), pero lo dejaba para que el
operador lo marcara y pulsara «Implementar transformadores» (020:RF-13 a RF-15). El objetivo es que la calibración
haga ese cambio físico ella misma, en el mismo trabajo, y vuelva a calibrar hasta converger con lo que la red consume.
La 020 está cumplida y no crece; esta spec la cita.

## Usuarios / actores

Operador que calibra «Sin proyecto» desde la web (spec 006, 014, 015 y 020), y `tools/sistema_web.py`, que calibra
por la misma ruta.

## Requisitos funcionales (EARS)

- RF-1: CUANDO una calibración aplicada no queda válida, EL SISTEMA buscará en su informe las SED que piden más del
  100 % de su potencia instalada y tienen propuesta de transformador de la 020.
- RF-2: CUANDO hay SED de RF-1, EL SISTEMA implementará sus transformadores en «Sin proyecto» en el mismo trabajo,
  sin esperar al operador, con las reglas de 020:RF-16 a RF-24.
- RF-3: CUANDO termina el cambio de RF-2, EL SISTEMA volverá a calibrar todo el proyecto a la vez (021:RF-54), con el
  mismo plan.
- RF-4: SI tras recalibrar sigue sin quedar válida y aparecen SED de RF-1 que aún no se cambiaron o necesitan más
  potencia, ENTONCES EL SISTEMA repetirá RF-2 y RF-3 con ellas.
- RF-5: EL SISTEMA no repetirá la ronda de RF-4 más de 3 veces.
- RF-6: EL SISTEMA dejará de repetir en cuanto una ronda no traiga ningún cambio nuevo.
- RF-7: SI la calibración no queda válida y no hay SED de RF-1, ENTONCES EL SISTEMA dará el fallo con su motivo físico
  y lo que falta para cambiarlas: la tabla de fichas, la tensión fuera de rango o más de un transformador
  (020:RF-10 a RF-12).
- RF-8: EL SISTEMA anotará en el Registro, por alimentador y por ronda, las SED cambiadas, con su potencia de antes y la
  nueva.
- RF-9: EL SISTEMA dará en el resultado del trabajo los cambios de todas las rondas y la calibración de la última ronda.
- RF-10: SI el trabajo se cancela, ENTONCES EL SISTEMA no empezará otra ronda.
- RF-11: SI el trabajo se cancela, ENTONCES EL SISTEMA conservará los cambios ya hechos (020:RF-27).
- RF-12: EL SISTEMA dejará al operador las SED entre el umbral de carga del perfil y el 100 %, con la casilla y el botón
  de 020:RF-13: no impiden converger.
- RF-13: MIENTRAS se simula la calibración, EL SISTEMA no cambiará ningún transformador.

## Requisitos no funcionales

- Universal: vale para cualquier distribuidora con tabla de fichas en su perfil (constitución P13). Sin tabla, rige RF-7.
- Escala: las rondas son por proyecto, no por alimentador; con todos los alimentadores del sistema, cada ronda es una
  sola recalibración.

## Casos límite

- La SED pasa del 100 % solo con el reparto de la calibración (una escalada): entra en RF-1 igual que una fija.
- La propuesta de una ronda es la misma que ya se aplicó (mismo transformador y misma potencia): no cuenta como cambio
  nuevo (RF-6).
- Un alimentador del proyecto da error al prepararse: los demás siguen y el error queda en su informe (021:RF-57).

## Fuera de alcance

- Las escaleras de obras de «Con proyecto» (042) y las cargas nuevas.
- Cambiar los datos del archivo o el «Caso base», que sigue con los kVA del TXT (032:RF-14).
- Decidir si un cliente está mal cruzado con su SED: se avisa como en 015:RF-59, y el transformador se cambia igual.

## Criterios de finalización

Cada RF citado por una prueba (`grep -rnoE "101:RF-[0-9]+" tests`), la suite en verde, y una calibración real de
CA101 + CHN102 desde la web que termine válida sin pulsar ningún botón.
