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

Corrección del usuario, el mismo día: «el valle es registro de energía menos sin incluir valores ceros, eso sale de los
registros de mediciones, este término es usado en demandas eléctricas; el tiempo lo vas a sacar de lo histórico registrado
usando optimización; las demandas no son valle; las cargas nuevas pueden ingresar en cualquiera, pero en análisis de
planeamiento se considera su coincidencia en máximos valores y también se debe considerar los mínimos o valle para la
implementación de bancos y proyectos». RF-1 a RF-4, RF-7 y RF-23 quedan reescritos por ella, con su mismo número, y RF-35 a
RF-41 son nuevos. `valle.dias_ventana` y `valle.factor_cargas_nuevas` desaparecen.

## Usuarios / actores

Ingeniero de planificación de cualquier distribuidora, desde la web; el asistente, por las mismas rutas.

## Requisitos funcionales (EARS)

### Ventana de valle desde la medición

- RF-1: CUANDO se pida el valle de un alcance, EL SISTEMA dará el periodo de menor energía registrada (kWh, no kVA ni el kW de
  un instante) y, como punto para el flujo, el registro de menor energía dentro de él, con su fecha, su kW y su kVAR.
- RF-2: EL SISTEMA sacará el inicio y la duración del valle de los registros históricos, sin ningún parámetro de duración.
- RF-3: SI un registro menor queda fuera del valle, ENTONCES EL SISTEMA lo dirá en sus avisos, con su fecha y su valor.
- RF-4: EL SISTEMA sumará registro a registro la energía de los medidores del alcance (alimentadores, SET o sistema eléctrico)
  y, para el punto del flujo, sus kVAR.
- RF-5: SI a un medidor del alcance le falta un instante, ENTONCES EL SISTEMA no contará ese instante, porque un hueco baja
  la suma y parecería un valle.
- RF-6: EL SISTEMA apartará del mínimo, con su motivo, su número de registros y su menor valor: los ceros, los de signo
  contrario al del medidor, los congelados, las fechas duplicadas con valores distintos, las caídas frente a su misma franja
  horaria (salida de servicio o transferencia) y las caídas aisladas de un registro.
- RF-7: SI un día no llega a la cobertura mínima de registros válidos, ENTONCES EL SISTEMA no contará su energía, y una ventana
  solo lo cruzará si le quedan días con dato en esa misma cobertura, y dirá cuántos tiene.
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
- RF-23: EL SISTEMA no tendrá ninguna opción que decida si las cargas nuevas consumen en valle: mide los dos casos de RF-39.
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
- RF-32: EL SISTEMA pondrá esa frase en la sección de cada alternativa con obras del informe de estudio y en las obras del de
  factibilidad.

### Años futuros y universalidad

- RF-33: DONDE llegue un pronóstico de valle (spec 046), EL SISTEMA lo conservará como dato, sin darlo por comprobado.
- RF-34: EL SISTEMA no llevará en el código nombres de empresa ni tamaños de banco, y la duración del valle no saldrá del perfil.

### Corrección del usuario: optimización, cargas nuevas y alcance

- RF-35: EL SISTEMA hallará la ventana con una optimización declarada y determinista: la búsqueda exacta, entre las ventanas de
  días contiguos, del mínimo del error de la serie diaria de energía en dos niveles, dentro y fuera, más una penalización que
  crece al acortar la ventana.
- RF-36: EL SISTEMA dará de cada ventana su inicio, su fin, su duración, su energía media dentro y fuera, los parámetros de la
  optimización, lo apartado y si toca el borde de los registros.
- RF-37: SI ninguna ventana mejora la serie sin ventana, o no hay días bastantes, ENTONCES EL SISTEMA lo dirá y usará el registro
  menor, en vez de inventar un periodo.
- RF-38: DONDE haya varios años, EL SISTEMA buscará la ventana de cada uno por su cuenta, sin mezclarlos, usará la del último
  y dirá los años usados y si coinciden en la época del año.
- RF-39: EL SISTEMA comprobará cada variante en valle sin las cargas nuevas, el peor caso para la sobretensión, y con ellas, porque
  pueden ingresar en cualquier momento; tiene que cumplir en los dos y el informe dirá los dos.
- RF-40: EL SISTEMA aplicará la comprobación en valle a toda obra que se vaya a implementar, bancos y proyectos, también en el PIDE
  y en la SET nueva.
- RF-41: EL SISTEMA no llamará demanda al valle en sus mensajes ni en sus informes.

## Casos límite

- La curva de un medidor con la convención de signo al revés no es un error: se toma el signo de su mediana.
- Una red real en valle puede quedar ya sobre el límite sin obra: la barra no bloquea salvo que la variante la suba más que
  `escalera.tolerancia_pu`, como en `cumple` (025:RF-50).
- Un apartado que de verdad fuera valle se ve en su motivo, con su menor valor: los umbrales de RF-6 son del perfil.

## Fuera de alcance

Esta fase no escribe en DIgSILENT ni usa GPU. El pronóstico de años futuros no se cambia (046). El alimentador con central
queda sin comprobar hasta llevar su curva de demanda (T9). Generar bancos por pasos en la escalera. La búsqueda de ventana por
algoritmo genético: la exacta cabe en coste y da el óptimo. No se afirma nada de obras ya entregadas.

## Criterios de finalización

Cada RF con su prueba, y la prueba en DIgSILENT de la calibración a valle y de la escalera sobre un proyecto de prueba.
