# Spec 054 — Fases reales en el DGS: tramos y SED monofásicos y bifásicos

Estado: cumplida · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01, al calibrar
NJA202 y R205 de Electro Oriente («del R5 y del alimentador de Amazonas debe ver los tramos
monofásicos, todos debes calibrar, y los SED monofásicos»; «haz la recomendación; recuerda que
debes implementar todas estas mejoras para que sea universal»).

## Contexto y objetivo

El escritor del DGS (`src/convertersmartgrid/dgs.py`) escribe todas las líneas con `TypLne.nlnph = 3` y
todos los transformadores de SED con `TypTr2.nt2ph = 3`, sea cual sea la fuente (TXT, MDB o
VNR-GIS) y la empresa. Las fases que trae la fuente se pierden: en NJA202 (Electro Oriente) hay
3 531 tramos monofásicos (698 km) y 166 bifásicos frente a 1 880 trifásicos, y unas 780 SED
monofásicas (normas `SM…01`, 1×5 a 1×37 kVA) que se importan como trifásicas D-YN. Un ramal
monofásico modelado como trifásico reparte su corriente en tres conductores: la caída de tensión
y las pérdidas salen subestimadas.

PowerFactory 2024 (leído en el proyecto importado de NJA202, 2026-11-01) tiene: `ElmTerm.phtech`
(0 ABC, 1 ABC-N, 2 BI, 3 BI-N, 4 2PH, 5 2PH-N, 6 1PH, 7 1PH-N, 8 N), `StaCubic.nphase` e
`it2p1..3` (fase de la barra que toma cada fase: 0 A, 1 B, 2 C), `TypLne.nlnph` (1, 2, 3) y
`nneutral`, `TypTr2.nt2ph`, `ElmLod.phtech` e `i_sym`, y `ComLdf.iopt_net` (0 equilibrado, 1
desequilibrado).

Por decisión del usuario (recomendación b, 2026-11-01), primero se midió en DIgSILENT. En una
copia del proyecto NJA202 importado (autorizada por el usuario y borrada al terminar), la SED
monofásica W2874838 (SM03701) pasada a trafo monofásico, en el caso calibrado «Sin proyecto»:

| Trafo monofásico | Flujo equilibrado | Flujo desequilibrado |
| --- | --- | --- |
| Alta en D a 22,9 kV (entre líneas, como dice la referencia técnica para el retorno por tierra) | la SED desaparece: BT a 0 pu, sin resultados | converge: BT 0,910 pu, trafo 37,6 %, carga servida |
| Alta en YN a 13,22 kV | desaparece | converge con la BT a 1,586 pu: incorrecto |

Cabecera: 6 499 kW con el equilibrado y 6 516 kW con el desequilibrado; la diferencia es la carga
de esa SED, que el equilibrado deja fuera. Además, `TypTr2.nt2ph` acepta 1, 2 y 3 (número de
fases); `StaCubic.nphase` lo calcula DIgSILENT (no se escribe) y sí `it2p1..3`; una carga sin
tipo toma la tecnología de su barra («1PH PH-E» en una barra 1PH). Conclusión: con fases reales,
el flujo desequilibrado es obligatorio donde haya elementos monofásicos o bifásicos.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA llevará al modelo las fases de cada tramo y de cada SED que dé la fuente: en
  VNR-GIS, las dos cifras de fases de la norma (01, 02, 03) y la fase o fases del tramo; en TXT y
  MDB, la fase de la sección de CYMDIST.
- RF-2: EL SISTEMA escribirá cada tipo de línea con su número de fases (`nlnph`) y sus neutros
  (`nneutral`), uno por combinación de conductor y fases.
- RF-3: EL SISTEMA escribirá cada barra con la tecnología de fases del elemento de más fases que
  llega a ella (`phtech`), y cada cubículo con sus fases (`nphase`, `it2p1..3`) según las fases
  del tramo o del equipo que conecta.
- RF-4: EL SISTEMA escribirá cada SED monofásica como transformador monofásico (`nt2ph` = 1,
  alta en D a la tensión entre líneas de su barra, conectado a su fase con `it2p1`), su barra de
  baja como 1PH (`phtech` = 6) y su carga sin tipo, que DIgSILENT hace «1PH PH-E»; una SED de dos
  unidades (sufijo 02), igual con `nt2ph` = 2 entre sus dos fases.
- RF-5: CUANDO la fuente no diga las fases de un elemento, EL SISTEMA lo escribirá trifásico, como
  hasta ahora, y lo anotará.
- RF-6: EL SISTEMA no cambiará nada de un alimentador que sea todo trifásico: su DGS saldrá igual
  byte a byte que antes de esta spec, con `workers=1` y con `workers>1`.
- RF-7: CUANDO una red tenga elementos monofásicos o bifásicos, EL SISTEMA usará el flujo
  desequilibrado (`ComLdf.iopt_net` = 1) en la importación, la calibración y los estudios, y lo
  dirá en sus informes; una red toda trifásica sigue con el equilibrado.
- RF-8: EL SISTEMA lo hará igual para cualquier fuente y empresa (constitución P13).
- RF-9: EL SISTEMA dejará a cada tramo y SED solo fases que le lleguen desde la cabecera: el hijo
  con fases que no le llegan toma las del padre; el tramo que tiene más fases que su padre las
  devuelve aguas arriba hasta un tramo que ya las tenga, y la SED toma las que le llegan; cada
  cambio se anota (`FASE_RECONSTRUIDA`). En NJA202 (2026-11-01) 374 de 849 SED
  quedaban sin tensión en el flujo por 18 empalmes así.
- RF-10: EL SISTEMA conectará los elementos trifásicos que crea (bancos de la calibración y cargas nuevas) solo en barras con
  las tres fases: uno trifásico en una barra de dos fases deja a DIgSILENT sin flujo en todo el proyecto («The no. of phases
  (3) of the element must be less than or equal to the no. of phases (2)»; BC_CAL_CHI201_3 en Pisco, 2026-11-03). Toma la
  barra trifásica más cercana y, si no hay ninguna, no lo crea y lo dice.
- RF-11: EL SISTEMA escribirá la potencia de una carga no trifásica en las entradas de su modo aunque sus tres fases tengan
  valor, porque es lo que consume en el flujo; decide su técnica (`phtech`), no cuántas fases tienen valor. Medido en DIgSILENT:
  SE10008 (1PH PH-E, 0 kW en el TXT) quedaba con `plini` 10⁻¹⁰ y la calibración esperaba 24,5 kW.
- RF-12: CUANDO la calibración o la inserción escriben una carga trifásica con sus fases iguales, EL SISTEMA la dejará equilibrada
  (`i_sym=0`) y escribirá su potencia en el escenario, sin reescribir las fases, que son dato de red compartido: el «Caso base»
  conserva así su demanda y su convergencia. La carga con fases distintas conserva su reparto. Usuario, 2026-11-03: «debe hacer
  que converja, recuerda: el caso llega convergido».

## Relación con otras specs

- Cambia el escritor del DGS (specs 001, 034) y la fuente VNR-GIS (023).
- La calibración (006, 025, 035) y los estudios usan el flujo desequilibrado donde haya
  monofásicos (RF-7).

## Criterios de finalización

- `grep -rnoE "054:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-8.
- NJA202 reimportado con sus tramos y SED monofásicos y calibrado con el flujo desequilibrado.
