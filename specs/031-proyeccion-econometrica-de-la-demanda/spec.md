# Spec 031 — Proyección de la demanda para todos los años del PIDE, con el mejor modelo por métricas

Estado: aprobada · Fecha: 2026-11-08 · Origen: usuario, 2026-10-28 (reserva) y 2026-11-08: «primero se deberían pronosticar y esos pronósticos deberían ser usados en cada año de estudio del PIDE» y «deben pronosticar todos los años requeridos en PIDE, pero debe hacer el mejor modelo con las métricas».

## Contexto y objetivo

El PIDE anual ya exige una proyección por carga y año, con huella y evaluación (072:RF-24), pero nada la producía: la 089 emite curvas a 28 días, las obras usan una tasa del perfil y el ciclo común solo hace competir a la GRU. Los pronósticos estaban aislados de los estudios. El objetivo es pronosticar primero, y que cada año del PIDE use lo pronosticado, con el modelo que gane por métricas medidas y nunca por elección fija.

## Requisitos

- RF-1: CUANDO se pida el PIDE de un estudio, EL SISTEMA pronosticará primero todos los años requeridos por ese estudio, antes de abrir sus casos anuales.
- RF-2: EL SISTEMA hará competir en cada clase y magnitud (cliente y escaladas; kW y kVAR) las referencias, los métodos anuales de `proyeccion_mercado`, los métodos de la 089 y los modelos neuronales disponibles, sobre los mismos datos y los mismos orígenes.
- RF-3: EL SISTEMA medirá cada candidato contra lo ocurrido, en orígenes sucesivos, con WAPE, RMSE relativo, sesgo y error de la máxima, cada uno a cada horizonte que los datos permitan.
- RF-4: EL SISTEMA elegirá al ganador por las métricas, con la regla declarada antes de medir, sin mirar la prueba para ajustar, y si ninguno mejora a la referencia ganará la referencia.
- RF-5: EL SISTEMA emitirá con el ganador P y Q de cada carga en cada año del horizonte, en valores absolutos, con su banda q05 a q95 obtenida de los errores medidos, y sin ninguna fila negativa ni imputada.
- RF-6: EL SISTEMA dirá en la evaluación el horizonte pronosticado y el horizonte validado contra lo ocurrido por separado; un año sin validar no se presentará como validado, ni en el informe del PIDE ni en la web.
- RF-7: EL SISTEMA dará por `aceptado` para planeamiento un pronóstico que el operador haya aceptado por orden expresa o que tenga validado todo su horizonte, y dirá en cuál de los dos casos está.
- RF-8: DONDE haya un histórico anual de la propia empresa (Formato 01), EL SISTEMA lo usará para medir el horizonte de varios años; nunca usará el histórico de otra empresa ni de otra fuente.
- RF-9: EL SISTEMA escribirá la proyección y su evaluación con el formato y las huellas que lee `leer_proyeccion_anual` (072:RF-24), sin debilitar ninguna comprobación de ese lector.
- RF-10: CUANDO el ciclo común (050) publique un ganador de pronóstico, EL SISTEMA usará esa versión como punto de partida del año base de la proyección y lo anotará en la evaluación.
- RF-11: EL SISTEMA usará la misma proyección aceptada para el alcance de las obras (042:RF-73) en lugar de la tasa del perfil, y SI no hay proyección aceptada, ENTONCES seguirá con la tasa del perfil y lo dirá.
- RF-12: SI una carga no tiene serie propia, ENTONCES EL SISTEMA la repartirá con la serie de su alimentador en proporción a su potencia instalada, y lo anotará en su fila.
- RF-13: EL SISTEMA aplicará el mismo procedimiento a cualquier distribuidora y fuente, sin nombres, años ni libros fijos en el código.
- RF-14: EL SISTEMA dará el mismo resultado con los mismos datos y semilla, y no escribirá en la calibración, el «Caso base» ni DIgSILENT.
- RF-15: SI la empresa no tiene Formato 01, ENTONCES EL SISTEMA lo construirá con las mediciones históricas de cabecera, por sistema y año, en el formato que lee `leer_formato_01`, con cada año marcado por sus meses medidos; un año incompleto no se presentará como año completo ni se extrapolará sin decirlo.
- RF-16: EL SISTEMA emitirá con el ganador solo los años que tenga validados, y como mínimo el primero; los siguientes crecerán desde ahí con la tasa de largo plazo del perfil (042:RF-86), y cada fila dirá de cuál de los dos viene. Pisco (2026-11-08): la tasa medida seguida 20 años daba 13 365 MW.
- RF-17: CUANDO se pida el pronóstico del PIDE en la GPU en un paso (`tools/lanzar_pronostico_pide_gpu.py`), EL SISTEMA hará competir las redes neuronales con la misma regla de RF-2 a RF-4, proyectará el quinquenio y el largo plazo (5 y 30 años si no se dicen otros) y no fijará ningún ganador. (2026-11-10: el guion de otra sesión ponía TiDE de ganador sin medir.)
- RF-18: SI no hay CUDA o memoria, o faltan los libros y el dataset, ENTONCES EL SISTEMA lo dirá antes de leer nada y no seguirá: ni series inventadas de demostración ni errores de la proyección escondidos.
- RF-19: DONDE el operador cargue un registro de PBI o de población, EL SISTEMA leerá de cada cifra su variable, región, año, valor, unidad, fuente y fecha de publicación, e identificará el registro por la huella sha256 de su contenido, nunca por el nombre del fichero ni por cifras escritas en el código. (Plan Maestro V1, F-06 / BP-07, 2026-11-14.)
- RF-20: EL SISTEMA usará en cada origen de la competición, y en la emisión, solo las cifras publicadas hasta ese corte, y de cada año la última publicada hasta entonces; SI una cifra se publicó después del corte, ENTONCES la rechazará en ese origen y lo anotará.
- RF-21: DONDE haya registro de PBI y población, EL SISTEMA hará competir con la regla de RF-4 un método anual de elasticidad de la demanda por habitante al PBI por habitante y su ablación con solo la población, y ninguno de los dos llevará esas cifras anuales a la malla de 15 minutos.
- RF-22: SI falta la cifra de un año, la región pedida no está en el registro, el registro está vacío o la unidad es desconocida, nominal, sin año base o mezcla años base, ENTONCES EL SISTEMA lo dirá con la variable, la región y el año, y no interpolará ni inventará la cifra.
- RF-23: EL SISTEMA escribirá en la evaluación la huella, las fuentes, el periodo, la región y el corte de publicación del registro usado, con las cifras rechazadas, y no emitirá con un ganador exógeno si el registro que recibe no tiene la huella con que compitió.

## Fuera de alcance

Sustituir la física de los estudios; las variables exógenas sin fuente real, que entran solo si el operador las carga; validar años para los que no existe medición.
