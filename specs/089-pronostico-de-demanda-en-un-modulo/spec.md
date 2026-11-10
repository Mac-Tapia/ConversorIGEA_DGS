# Spec 089 — Pronóstico de demanda en un módulo: datos vivos, limpieza, tres clases y backtest por método

Estado: aprobada · Fecha: 2026-11-05

## Contexto y objetivo

El usuario, el 2026-11-05: todo lo referido al pronóstico en una sola spec y un solo módulo, con la arquitectura moderna; se trabaja con 2026, y esos datos crecen cada mes con el registro de cabecera y de clientes fijos. Corrigió además los signos en la limpieza para entrenar y pidió usar el histórico 2023–2025 solo como apoyo.

El diagnóstico medido el mismo día: la cabecera no usaba el libro alimentador–medidor; los libros `.xlsb` de clientes daban cero curvas; las escaladas no tenían serie; no había limpieza de medidores congelados ni de atípicos, y el horizonte llegaba a 1 día. Un proyecto anterior de la empresa midió a 28 días un WAPE mediano de 32,7 % con ML recursivo, frente a 21,0 % de un perfil anclado y 17,0 % del semanal: un modelo bueno a un paso pierde el nivel en pocos días.

Cita la 046, la 029 y la 088. La 046 está cumplida y no crece: sus modelos y puertas se usan sin cambios.

## Requisitos funcionales (EARS)

Datos vivos

- RF-1: CUANDO se arme el dataset, EL SISTEMA descubrirá los libros recorriendo las carpetas de cabecera y de clientes.
- RF-2: CUANDO aparezca en la carpeta el libro de un mes nuevo, EL SISTEMA lo incluirá sin ningún cambio de código ni de configuración.
- RF-3: EL SISTEMA obtendrá el rango de fechas de cada serie de sus datos.
- RF-4: CUANDO se arme el dataset, EL SISTEMA dirá los libros leídos con su tamaño y su fecha de modificación.
- RF-5: CUANDO se arme el dataset, EL SISTEMA dirá el último instante con dato de cada clase.

Equivalencia

- RF-6: EL SISTEMA tomará el medidor de cada alimentador del libro alimentador–medidor.
- RF-7: EL SISTEMA clasificará como barra la fila cuyo código empiece por «Barra».
- RF-8: EL SISTEMA clasificará como alimentador la fila de media tensión, hasta 35 kV, que no sea una barra.
- RF-9: EL SISTEMA clasificará como transmisión la fila de más de 35 kV que no sea una barra.
- RF-10: SI una fila no dice su tensión o su medidor, ENTONCES EL SISTEMA la apartará diciendo el motivo.
- RF-11: EL SISTEMA tomará como objetivos de cabecera solo las filas de la clase alimentador.
- RF-12: CUANDO un alimentador tenga varios medidores, EL SISTEMA sumará sus curvas en los instantes comunes.
- RF-13: DONDE el perfil declare la central de un alimentador, EL SISTEMA usará la demanda con la central descontada.

Clientes fijos

- RF-14: EL SISTEMA leerá las hojas de clientes con la disposición «día, hora», con el mes de su libro.
- RF-15: EL SISTEMA leerá la hora «24:00» como las 00:00 del día siguiente.
- RF-16: DONDE el libro de suministros renumere un cliente, EL SISTEMA unirá sus dos códigos en una sola serie con el código actual.
- RF-17: EL SISTEMA asignará cada cliente a su alimentador con el libro de suministros.

Limpieza

- RF-18: CUANDO una serie de cabecera tenga kW negativo en el 95 % o más de sus registros distintos de cero, EL SISTEMA invertirá su kW y su kVAR.
- RF-19: CUANDO se invierta una serie, EL SISTEMA lo anotará en su procedencia.
- RF-20: SI una serie de cabecera tiene kW negativo en más del 5 % y menos del 95 % de sus registros distintos de cero, ENTONCES EL SISTEMA la apartará diciendo el motivo.
- RF-21: EL SISTEMA juzgará el sentido sobre la demanda con la central descontada, si la hay.
- RF-22: EL SISTEMA quitará de la serie para entrenar los tramos de 16 o más registros idénticos y distintos de cero.
- RF-23: EL SISTEMA quitará de las series de cabecera para entrenar los registros con kW cero, porque un corte no es demanda.
- RF-24: EL SISTEMA quitará de la serie para entrenar los atípicos aislados a más de 6 desviaciones robustas de la mediana móvil de los 7 días anteriores.
- RF-25: SI una serie de cabecera tiene más de la mitad de sus registros en cero o sin dato, ENTONCES EL SISTEMA la apartará como no operativa.
- RF-26: EL SISTEMA no rellenará ningún registro quitado.
- RF-27: CUANDO limpie una serie, EL SISTEMA contará en su procedencia los registros quitados por cada causa.
- RF-28: EL SISTEMA no cambiará la curva que usan la calibración y las obras por ninguna regla de limpieza de esta spec.

Clases

- RF-29: EL SISTEMA dará objetivos de kW y kVAR de tres clases: cabecera, cliente y escaladas.
- RF-30: EL SISTEMA calculará la P de las escaladas de un alimentador como su cabecera menos sus clientes fijos en cada instante.
- RF-31: SI ese resto de P es negativo, ENTONCES EL SISTEMA lo dejará en cero.
- RF-32: SI un cliente no tiene dato en un instante posterior a su primer dato, ENTONCES EL SISTEMA dejará ese instante sin dato de escaladas.
- RF-33: EL SISTEMA anotará que la Q de las escaladas incluye los bancos de la red.
- RF-34: CUANDO el cambio de la cabecera y el de la suma de fijas se correlacionen al menos 0,2 mejor con otro desfase, y alcancen 0,5, EL SISTEMA dirá ese desfase sin corregirlo.

Apoyo

- RF-35: DONDE se declare una carpeta de apoyo, EL SISTEMA usará sus registros solo en los instantes anteriores al primer dato de la serie base.
- RF-36: SI la serie de apoyo difiere de la base más de un 2 % en mediana en sus instantes comunes, ENTONCES EL SISTEMA no la usará y lo dirá.
- RF-37: EL SISTEMA no evaluará ningún método sobre instantes de apoyo.

Métodos y backtest

- RF-38: EL SISTEMA hará competir los métodos semanal, perfil calendario y perfil anclado en orígenes sucesivos, con un horizonte de 28 días por defecto.
- RF-39: CUANDO prediga desde un origen, EL SISTEMA usará solo lo observado antes de ese origen.
- RF-40: EL SISTEMA evaluará cada método sobre los registros observados del horizonte, con WAPE, RMSE relativo y sesgo.
- RF-41: EL SISTEMA elegirá el método de cada objetivo en los orígenes anteriores al último.
- RF-42: EL SISTEMA informará el error del método elegido en el último origen, que no intervino al elegirlo.
- RF-43: SI una serie no llega a dos orígenes completos, ENTONCES EL SISTEMA la apartará como historia insuficiente.

Exógenas

- RF-44: DONDE se declare una carpeta de exógenas, EL SISTEMA tratará los días no laborables como domingos en los perfiles.
- RF-45: EL SISTEMA dirá los no laborables de su archivo que no citen una norma.
- RF-46: CUANDO haya temperatura, EL SISTEMA ajustará el residuo del perfil anclado con lo anterior al origen, como un método aparte.
- RF-47: CUANDO prediga con temperatura, EL SISTEMA usará en el futuro su climatología por mes y hora anterior al origen.
- RF-48: EL SISTEMA usará el método con temperatura solo si mejora el WAPE del perfil anclado al menos un 1 % en los mismos orígenes.
- RF-49: CUANDO la temperatura no entre en un objetivo, EL SISTEMA dirá el resultado de esa comparación.

Salida

- RF-50: CUANDO emita un pronóstico, EL SISTEMA dará q05, q50 y q95 de cada instante con el error de los orígenes de elección.
- RF-51: EL SISTEMA marcará cada fila emitida como `pronostico`, con su objetivo, clase, unidad, emisión, horizonte y método.
- RF-52: EL SISTEMA no llevará ningún medidor, alimentador, libro, mes ni año de una empresa en el código.
- RF-55: DONDE se declare una carpeta de apoyo de clientes, EL SISTEMA usará sus registros solo antes del primer dato de la serie base de cada cliente.

Modelos

- RF-56: EL SISTEMA hará competir N-HiTS, NBEATSx, PatchTST, TFT, iTransformer, TimesNet, TiDE, TSMixerx, BiTCN, GRU y LightGBM directo con los perfiles.
- RF-57: EL SISTEMA entrenará cada modelo sobre el resto de la demanda frente al perfil anclado, con los registros de 15 minutos y sin rellenar los que faltan.
- RF-58: EL SISTEMA dará a los modelos como futuro conocido el reloj, los no laborables y la climatología anterior al origen.
- RF-59: CUANDO ajuste un modelo para un origen, EL SISTEMA usará solo lo anterior a ese origen.
- RF-60: EL SISTEMA medirá modelos y perfiles en los mismos orígenes y registros.
- RF-61: SI un modelo falla al ajustar o predecir, ENTONCES EL SISTEMA lo dejará en `ERROR_ENTORNO` con su motivo y seguirá con los demás.
- RF-62: EL SISTEMA entrenará las redes solo en CUDA, sin pasar a la CPU.
- RF-63: EL SISTEMA exigirá para promover un modelo un WAPE ponderado de prueba al menos un 2 % mejor que el del mejor perfil de elección.
- RF-64: EL SISTEMA exigirá que su error mediano de la máxima no sea peor que el de ese perfil.
- RF-65: EL SISTEMA exigirá que la cobertura de su intervalo q05–q95 en prueba esté entre 0,85 y 0,95.
- RF-66: SI ningún modelo pasa la puerta, ENTONCES EL SISTEMA dejará el perfil y lo dirá.
- RF-67: EL SISTEMA informará el error de cada método a 1 día, a 7 días y al horizonte.
- RF-68: EL SISTEMA guardará el dataset limpio con su huella y lo reabrirá para entrenar sin volver a leer los libros.
- RF-70: EL SISTEMA guardará las curvas de los objetivos en arreglos, con 16 bytes o menos por registro.
- RF-71: EL SISTEMA calculará la forma del perfil anclado sin sus últimos 28 días, y anclará sumando donde el cociente no sea estable.
- RF-72: SI un cliente lleva más de 45 días sin dato frente al último de todos los clientes, ENTONCES EL SISTEMA lo tomará como dado de baja.
- RF-73: SI faltan los clientes o el libro de suministros, ENTONCES EL SISTEMA no dará escaladas.
- RF-74: EL SISTEMA restará de las escaladas a un cliente apartado como objetivo.
- RF-75: SI un libro no se puede abrir o no se usa, ENTONCES EL SISTEMA lo dirá en los avisos del dataset.
- RF-76: CUANDO la suma de los medidores de un alimentador acabe antes que alguno de ellos, EL SISTEMA dirá hasta dónde llega.
- RF-77: CUANDO el mismo medidor cambie de nombre de canal entre libros, EL SISTEMA unirá sus registros.
- RF-78: SI el balance de la central no cuadra, ENTONCES EL SISTEMA apartará el alimentador diciendo el motivo.
- RF-79: SI una hoja de clientes repite un registro, ENTONCES EL SISTEMA lo quitará y lo contará.
- RF-80: EL SISTEMA elegirá el método sin los orígenes que no tengan datos con que medir.
- RF-81: SI un alimentador tiene clientes fijos, ENTONCES EL SISTEMA no dará escaladas en los instantes anteriores al primer dato de todos los libros de clientes.
- RF-82: SI la cabecera sube menos de la mitad del consumo de un cliente en los 14 días siguientes a su primer dato, ENTONCES EL SISTEMA no dará escaladas de ese alimentador antes de ese dato.
- RF-83: SI la cabecera sube la mitad o más del consumo de un cliente en los 14 días siguientes a su primer dato, ENTONCES EL SISTEMA conservará las escaladas anteriores a ese dato.
- RF-84: SI un cliente consume menos del 20 % de la cabecera en los 14 días siguientes a su primer dato, ENTONCES EL SISTEMA conservará las escaladas anteriores a ese dato.
- RF-85: EL SISTEMA informará el MASE de cada método, con el error de repetir lo de hace una semana como escala, emparejado por fecha.
- RF-86: SI la escala del MASE es cero o no se puede medir, ENTONCES EL SISTEMA dirá que ese objetivo no tiene MASE.
- RF-87: EL SISTEMA calculará la escala del MASE de cada origen solo con los datos anteriores a ese origen.
- RF-88: EL SISTEMA dará en el resumen la mediana del MASE por clase, magnitud y método.
- RF-69: CUANDO haya dos o más modelos evaluados, EL SISTEMA hará competir la media de los tres mejores en elección, con la misma puerta.

- RF-54: EL SISTEMA juzgará el sentido de una serie por sus últimos 60 días, quitará los registros anteriores de sentido contrario y los contará en su procedencia.
- RF-53: CUANDO resuma el backtest por clase, EL SISTEMA dará también el WAPE ponderado por la energía de cada objetivo.

- RF-89: CUANDO se pida entrenar por alimentador (`tools/entrenar_alimentadores_gpu.py`), EL SISTEMA entrenará uno tras otro, en la GPU, los alimentadores pedidos o todos los del libro de equivalencia, con los libros que se le den por argumento y sin rutas fijas; liberará la memoria de la GPU entre uno y otro y retomará los ya entrenados con el mismo modelo. (2026-11-10: el guion de otra sesión fijaba las rutas de los libros de la distribuidora.)
- RF-90: SI un alimentador falla al entrenar, ENTONCES EL SISTEMA seguirá con los demás, lo dirá en el resumen y terminará con código 1; uno sin historia suficiente queda `SIN_HISTORIA` con su motivo. No elige ni promociona modelos: eso es de la competición con su puerta.

## Fuera de alcance

La proyección a años con variables exógenas, que necesita al menos un año completo y sigue en la 031; las curvas propias de fijas y escaladas en los sorteos de obras, que tocan `obras_pf` y `entrega-087q`; descargar temperatura; corregir el desfase de relojes; PBI y población; panel en la web. Los umbrales de RF-18, RF-20, RF-22, RF-24, RF-34 y RF-36 son propuesta, sin confirmar por el usuario.

## Criterios de finalización

Cada RF citado por una prueba `089:RF-n` y en verde; backtest real de 2026 con `CSG_DEMANDA_DIR`, con sus resultados anotados en las tareas sin datos de la distribuidora.
