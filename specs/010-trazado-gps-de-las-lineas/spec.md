# Spec 010 — Trazado GPS de las líneas

Estado: cumplida · Fecha: 2026-10-10 · Spec, plan e implementación aprobados por el
usuario el 2026-10-10, después de implementarse (lo pidió de forma explícita).

## Contexto y objetivo
Al importar la red unida NA203 + NA205 en PowerFactory, las barras quedan en su punto GPS
original (desvío máximo 0,008 mm), pero las líneas no traen trazado GPS propio: el DGS
escribe `GPScoords` vacío. Los puntos intermedios del origen solo se usan para el
diagrama y para la longitud. Una vista geográfica de PowerFactory dibuja entonces cada
línea como una recta entre sus dos barras, sin las curvas del recorrido real. El usuario
pidió que las líneas sigan su recorrido real.

Un experimento del 2026-10-10 (AL106, 172 líneas) comprobó el formato: con la tabla
normalizada `Matrix` de DGS 7.0, PowerFactory 2024 importa cada trazado como una matriz
de n puntos × 2 columnas (latitud, longitud) idéntica punto a punto al origen, y no
cambia la longitud de ninguna línea.

## Usuarios / actores
Ingeniero de planificación que convierte desde la web o el CLI e importa el DGS en
PowerFactory; la prueba de aceptación en PowerFactory.

## Historias de usuario
- H1: Como ingeniero quiero que cada línea importada en PowerFactory lleve su recorrido
  GPS real para verla en la vista geográfica tal como está en el terreno.

## Requisitos funcionales (EARS)
- RF-1: DONDE la conversión lleva georreferenciación, EL SISTEMA escribirá en cada línea
  su trazado GPS: el punto de la barra inicial, los puntos intermedios del origen en su
  orden y el punto de la barra final.
- RF-2: EL SISTEMA escribirá el primer y el último punto de cada trazado con el mismo
  valor que el GPS de la barra correspondiente.
- RF-3: MIENTRAS la georreferenciación está desactivada, EL SISTEMA escribirá las líneas
  sin trazado GPS y sin tabla de trazados.
- RF-4: CUANDO se convierte una red unida con georreferenciación, EL SISTEMA escribirá el
  trazado de sus líneas igual que en un alimentador suelto.
- RF-5: CUANDO relee el DGS escrito, EL SISTEMA dará un error de validación por cada línea
  cuyo trazado no coincida punto a punto con la geografía del modelo.
- RF-6: CUANDO la prueba de aceptación en PowerFactory recibe el manifiesto geográfico,
  EL SISTEMA informará cuántas líneas tienen trazado GPS en PowerFactory y cuántas
  difieren del manifiesto.
- RF-7: SI alguna línea importada en PowerFactory no tiene el trazado del manifiesto,
  ENTONCES EL SISTEMA dará por fallida la comprobación del diagrama geográfico.

## Requisitos no funcionales
- Determinismo: el DGS sigue siendo idéntico byte a byte con `workers=1` y `workers>1`.
- Escala: escribir los trazados no recorre ninguna tabla completa por alimentador.
- La longitud eléctrica de cada línea no cambia.

## Casos límite
- Línea sin puntos intermedios: trazado de dos puntos.
- Tramos puente fundidos: el trazado de la línea que queda empieza y acaba en las barras
  que existen en el DGS, no en las fundidas.
- Barra de cabecera partida en una red unida (`…@NA203`, `…@NA205`): cada línea usa la
  copia de su alimentador.
- Excel y TSV: la tabla de trazados sale como una hoja o un fichero más.

## Fuera de alcance
- Trazado GPS de interruptores, acoplamientos y tramos puente convertidos en interruptor:
  no son líneas.
- Un CRS de destino distinto de WGS84: el GPS de las barras tampoco lo admite hoy.
- Cambios en el diagrama de la grid: ya sigue el recorrido real.

## Cambio en otra spec
001:RF-14 exige DGS idénticos a la línea base de la reorganización. Esta spec cambia, a
propósito, todos los DGS georreferenciados. La línea base se regenera una vez con el
código de esta spec y RF-14 lo anota como segunda excepción.

## Criterios de finalización
Cada RF citado por al menos una prueba (`grep -rnoE "010:RF-[0-9]+" tests`), suite en
verde con los datos reales y la red unida NA203 + NA205 importada en PowerFactory con
todas sus líneas con el trazado del manifiesto.

## Dudas abiertas
Ninguna.
