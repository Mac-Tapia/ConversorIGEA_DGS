# Spec 073 — El número de bancos lo define la tensión en las ventanas de valle

Estado: aprobada · Fecha: 2026-11-02 · Origen: orden del usuario

## Contexto y objetivo

El usuario, el 2026-11-02, al preguntarle si la escalera probaba 1 y 2 o 2 y 3 bancos: «eso lo debe definir las demandas en
ventanas de valle donde podría ocurrir sobretensiones». Un banco fijo no se va cuando baja la demanda: eleva la tensión
justo cuando menos carga hay, y mirarlo solo en la máxima no lo detecta.

Hoy `escalera_optima._escalon_bancos` prueba `n in (1, 2)`; `cumple` mira el límite superior, pero con la demanda de la
máxima; y los sorteos recorren la curva, con una fracción de cumplimiento que deja pasar justo los pocos instantes de valle
(la prueba `test_sobretension_en_valle_se_cuela_por_la_fraccion` lo reproduce). Ninguna spec nombraba valle ni sobretensión
como requisito.

Regla que se conserva (specs 025, 042, 052, 063): bancos primero, con el módulo por tensión del perfil; luego sección,
terna y regulador; para en el primer escalón que cumple, y dentro de él la más barata; obras solo si hay problemas; el
informe dice el nodo de media tensión del banco. Lo que cambia es de dónde sale cuántos módulos se prueban y que una
variante no vale si no cumple también en valle.

## Usuarios / actores

Ingeniero de planificación de cualquier distribuidora, desde la web; el asistente, por las mismas rutas.

## Requisitos funcionales (EARS)

### Ventana de valle desde la medición

- RF-1: CUANDO se pida el valle de un alcance, EL SISTEMA dará el instante de menor demanda en kVA, con su fecha y el kW y el
  kVAR de ese mismo instante.
- RF-2: DONDE el perfil dé `valle.dias_ventana`, EL SISTEMA dará también los N días de calendario contiguos con menor demanda
  media en kVA, con su inicio, su fin, su kW y kVAR medios y el instante mínimo dentro de ellos.
- RF-3: SI el perfil no da `valle.dias_ventana`, ENTONCES EL SISTEMA usará solo el instante mínimo y lo dirá en sus avisos.
- RF-4: EL SISTEMA sumará los medidores del alcance (alimentadores, SET o sistema eléctrico) registro a registro y
  vectorialmente: el kVA sale de la suma de kW y de la suma de kVAR.
- RF-5: SI a un medidor del alcance le falta un instante, ENTONCES EL SISTEMA no contará ese instante, porque un hueco baja
  la suma y parecería un valle.
- RF-6: EL SISTEMA apartará del mínimo, con su motivo, su número de registros y su menor valor: los ceros, los de signo
  contrario al del medidor, los congelados, las fechas duplicadas con valores distintos, las caídas frente a su misma franja
  horaria (salida de servicio o transferencia) y las caídas aisladas de un registro.
- RF-7: SI un día no llega a la cobertura mínima de registros válidos, ENTONCES EL SISTEMA no lo contará en ninguna ventana y
  esa ventana no lo saltará.
- RF-8: SI un medidor no llega a la cobertura mínima en el periodo, ENTONCES EL SISTEMA lo dejará fuera de la suma y lo dirá,
  en vez de reducir los instantes de todos (Chincha, julio de 2026: 801 de 2 976 registros de una barra de 8 kW).
- RF-9: EL SISTEMA dará el mismo valle con la misma entrada, en una sola pasada por los registros, y a igual valor el primero.
- RF-10: SI no queda ningún instante válido, ENTONCES EL SISTEMA devolverá el valle sin comprobar, con su motivo, sin error.
- RF-11: EL SISTEMA leerá la medición de 15 minutos solo con los lectores de `demanda_medida`.
- RF-12: SI un alimentador lleva central en su calibración, ENTONCES EL SISTEMA dejará el valle sin comprobar y lo dirá,
  porque su cabecera no es su demanda (021:RF-28).

### Calibración a valle

- RF-13: CUANDO se calibre a valle, EL SISTEMA usará un caso y un escenario propios, «Valle <año>», copia de «Sin proyecto
  <año>», con su marca de rol.
- RF-14: EL SISTEMA no cambiará al calibrar a valle ni el caso ni el escenario de la máxima.
- RF-15: SI ya hay un caso con ese nombre que el sistema no creó, ENTONCES EL SISTEMA no lo tocará y lo dirá.
- RF-16: EL SISTEMA armará el plan de la calibración a valle con la misma máquina de la calibración: la cabecera, las fijas de
  la tabla medidas a esa hora y las escaladas, en el instante de valle.

### Escalera y PIDE

- RF-17: EL SISTEMA dará por factible una variante solo si cumple con la máxima y en cada punto de valle comprobado.
- RF-18: EL SISTEMA no compensará un incumplimiento en valle con la fracción de sorteos, tampoco en la elección de 063:RF-33.
- RF-19: EL SISTEMA probará de 1 al mayor número de módulos que no sobrepasa el límite superior en valle, sin cifra fija en
  el código, con el módulo por tensión del perfil.
- RF-20: SI la máxima pide más módulos de los que aguanta el valle, ENTONCES EL SISTEMA seguirá la escalera y lo dirá, con la
  variante de un módulo más medida y rechazada.
- RF-21: EL SISTEMA aplicará el mismo criterio de valle en la búsqueda de cuántas cargas caben, en la bayesiana, en el frente
  de Pareto y en el reparto de Shapley.
- RF-22: EL SISTEMA medirá el valle con el kW y el kVAR de su registro, cada uno con su factor sobre la máxima.
- RF-23: EL SISTEMA medirá las cargas nuevas en valle por `valle.factor_cargas_nuevas` del perfil y, sin él, apagadas, porque
  de ellas no hay medición y el banco sigue conectado.
  [NECESITA ACLARACIÓN: ¿una carga nueva consume en valle? Por defecto, el caso más exigente; el perfil lo cambia.]
- RF-24: SI no hay valle medido, ENTONCES EL SISTEMA no bloqueará nada, marcará la variante como no comprobada y probará los
  módulos de `escalera.modulos_max` o, sin él, los de la regla anterior a esta spec.
- RF-25: DONDE el plan de `tools/obras_pf.py --evaluar` traiga puntos de valle, EL SISTEMA medirá cada variante en ellos, en
  un escenario temporal que no deja nada en el proyecto.
- RF-26: SI «Con proyecto» ya cumple con lo que tiene y en valle no, ENTONCES EL SISTEMA lo dirá en su aviso.
- RF-27: EL SISTEMA dejará constancia de que la escalera no genera bancos por pasos: la obra los modela (011:RF-71, RF-72),
  el oráculo no.
- RF-28: SI el valle no admite ningún módulo en un alimentador, ENTONCES `propuesta_pide` tomará la alternativa siguiente de
  esa causa y, sin ninguna, dejará la obra descartada con su motivo.
- RF-29: EL SISTEMA no propondrá en el PIDE más módulos de los que admite el valle, y dirá cuántos admite.

### Informe

- RF-30: EL SISTEMA dará por cada alternativa la tensión máxima en valle, con su nodo y su fecha.
- RF-31: SI no hay valle medido, ENTONCES EL SISTEMA dirá «no comprobado en valle», nunca que cumple.
- RF-32: EL SISTEMA pondrá esa frase en la sección de cada alternativa con bancos del informe de estudio.

### Años futuros y universalidad

- RF-33: DONDE llegue un pronóstico de valle (spec 046), EL SISTEMA lo conservará como dato, sin darlo por comprobado.
- RF-34: EL SISTEMA no llevará en el código nombres de empresa, tamaños de banco ni número de días: salen del perfil.

## Casos límite

- La curva de un medidor con la convención de signo al revés no es un error: se toma el signo de su mediana.
- Una red real en valle puede quedar ya sobre el límite sin obra: la barra no bloquea salvo que la variante la suba más que
  `escalera.tolerancia_pu`, como en `cumple` (025:RF-50).
- Un apartado que de verdad fuera valle se ve en su motivo, con su menor valor: los umbrales de RF-6 son del perfil.

## Fuera de alcance

Esta fase no escribe en DIgSILENT ni usa GPU. El pronóstico de años futuros no se cambia (046). El alimentador con central
queda sin comprobar hasta llevar su curva de demanda (T9). Generar bancos por pasos en la escalera. La búsqueda de ventana por
algoritmo genético: es una búsqueda exacta. No se afirma nada de obras ya entregadas.

## Criterios de finalización

Cada RF con su prueba; la prueba en DIgSILENT de la calibración a valle y de la escalera sobre un proyecto de prueba; y la
aclaración de RF-23.
