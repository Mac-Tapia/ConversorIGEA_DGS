# Spec 095 — Escaladas proporcionales a su potencia instalada

Estado: cumplida · Fecha: 2026-11-06 · Origen: usuario, 2026-11-06, AL209: «los escalados deben hacer el probabilístico
según su potencia instalada; ningún SED debe estar sin carga» y, preguntado, «proporcional a su kVA».

## Contexto y objetivo

La 041 (RF-2) daba más utilización a las escaladas de mayor potencia, con una pendiente sacada de las fijas. En AL209
(fijas coincidentes, 2026-11-06) la pendiente fue 0,306: con un factor común de 0,107, las SED de 5 y 10 kVA quedaban
con 0,10 a 0,26 kW (2 a 3 % de su kVA) frente al 10 % de media, y 23 de 69 escaladas por debajo de 1 kW. Cambia 041:RF-2
y la parte de 041:RF-3 que saca la pendiente de las fijas o del perfil (spec cumplida, que no crece).

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA dará a cada SED escalada la misma utilización esperada (kW por kVA instalado): su P esperada será
  proporcional a su potencia instalada, sin pendiente con la potencia.
- RF-2: EL SISTEMA seguirá sorteando el factor propio de cada escalada (041:RF-1) con la dispersión de las fijas del
  mismo alimentador, medida alrededor de su utilización media; de las fijas ya no tomará pendiente.
- RF-3: SI el perfil de empresa trae `calibracion.reparto_probabilistico.pendiente`, ENTONCES EL SISTEMA usará solo su
  dispersión y dirá en el informe que la pendiente se ignora por RF-1.

## Fuera de alcance

Cambiar cómo se cuadran P y Q (035) o el trato de las fijas.

## Criterios de finalización

`grep -rnoE "095:RF-[0-9]+" tests | sort -u` cita los tres RF; suite enfocada en verde; AL209 recalibrado con todas las
escaladas proporcionales a su kVA.
