# Spec 057 — El «Caso base» llega convergido: el oráculo corrige antes de importar

Estado: cumplida (2026-11-01) · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01, tras importar
NJA202 (W12882) de Electro Oriente: «se supone que el oráculo detecta y, si no converge,
corrige, y a DIgSILENT va convergido; eso es su trabajo».

## Contexto y objetivo

Esta spec no crea un mecanismo nuevo: cambia el momento y la forma de dos que ya existen.

- El oráculo (034:RF-25, 015:RF-41) calcula con pandapower antes de importar, «sin modificar el
  modelo», y solo informa.
- La convergencia del «Caso base» (015:RF-38, RF-40) se busca después, en DIgSILENT, bajando la
  demanda **por igual** en todas las cargas.
- La reconstrucción auditable (001:RF-17 a RF-22, 034:RF-22) ya guarda de cada cambio el valor
  original, el nuevo y su evidencia, sin tocar los originales.

Con NJA202 las dos primeras fallaron. El oráculo dijo «NO CONVERGE» y la importación siguió, y
DIgSILENT bajó la demanda del 90 % al 10 % sin converger. Causa, medida en la copia ELOR25_V2:
`Sed.MaxDemTotal` vale 39,00 kW en las 8 729 SED, con `PotInstalada` de 5 a 2 000 kVA, así que
470 SED de 5 kVA quedan al 780 %. Bajar por igual no arregla una SED que lleva ocho veces su
potencia sin dejar casi vacías las grandes.

Decisión del usuario (2026-11-01): «el caso base hace algunas correcciones solo para que
converja; en "Sin proyecto" se calibra, y en la recalibrada se deben incluir los cambios
recomendados desde los mismos flujos de siempre».

## Requisitos funcionales (EARS)

- RF-1: SI el flujo del oráculo no converge antes de importar, ENTONCES EL SISTEMA buscará la
  corrección de 015:RF-38 con el oráculo, en vez de importar y buscarla en DIgSILENT.
- RF-2: EL SISTEMA corregirá en esa búsqueda solo las SED cuya demanda sea de relleno (el mismo
  valor en todas las SED de la fuente) o supere su potencia instalada.
- RF-3: EL SISTEMA dejará la demanda de cada SED corregida en su potencia instalada × FP 0,98 ×
  un mismo factor, el mayor con el que converge el oráculo, sin que ninguna pase del 80 %.
- RF-4: EL SISTEMA anotará cada corrección en el informe de reglas del alimentador (el de los
  puentes y el trafomix, en el manifiesto y en la web), con el valor de la fuente, el nuevo y la
  regla, sin cambiar los originales (034:RF-22).
- RF-5: EL SISTEMA importará en DIgSILENT la red corregida y solo la que converge en el oráculo.
- RF-6: SI ni así converge el oráculo, ENTONCES EL SISTEMA no importará ese alimentador y dirá
  qué elementos lo impiden (015:RF-40), y seguirá con los demás del lote.

## Fuera de alcance

- La calibración de «Sin proyecto» y la recalibración (specs 006, 014, 015, 028): siguen igual
  y parten de la red corregida, con los mismos flujos de siempre.
- Una SED con demanda propia y dentro de su potencia instalada: queda como la trae la fuente.
- El flujo por fases (spec 054): el oráculo sigue siendo equilibrado.

## Relación con otras specs

- Cambia 034:RF-25 («sin modificar el modelo») solo para las SED de RF-2, y adelanta 015:RF-38
  al oráculo. Reutiliza el informe de reglas de `aplicar_reglas` y no cambia los originales
  (034:RF-22).

## Criterios de finalización

- `grep -rnoE "057:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-6.
- NJA202 importado por la web con el flujo del «Caso base» convergido en DIgSILENT a la primera.
