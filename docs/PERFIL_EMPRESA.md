# Perfil de empresa

Guía para quien configura ConverterSmartGrid en una distribuidora nueva (spec 086, RF-30). El programa es universal: lo propio de cada
empresa va en un perfil, nunca en el código. **Sin perfil se puede trabajar**: una clave ausente no bloquea nada, y cada función dice
qué hace sin ella.

## Cómo empezar

1. Copie `config/perfiles/plantilla.json` como `config/perfil_empresa.json`. Ese fichero es local y no se comparte.
2. Rellene lo que conozca. `config/perfiles/ficticia.json` muestra uno completo, de una empresa inventada.
3. Compruébelo:

   ```
   convertersmartgrid validar-perfil
   convertersmartgrid validar-perfil --ruta otro_perfil.json
   convertersmartgrid validar-perfil --perfil ficticia --json
   ```

   La orden solo lee. Dice qué valores son imposibles (sale con código 1), qué claves faltan con la función que afectan y qué hace el
   programa sin ellas (sale con 0), y qué claves no conoce, por si hay una errata.

Un perfil puede heredar de otro con `"perfil": "<nombre>"`: sus claves pisan las heredadas y una clave en `null` anula la heredada.

## Empresa o norma

Cada clave dice de quién es el dato. **Empresa**: una convención suya, que el programa nunca toma de otra. **Norma**: lo fija una norma
aplicable. Si no se da, el programa puede usar un valor de referencia, y siempre lo avisa. En la 1.0 el alcance es Perú: la frecuencia
es de 60 Hz y las normas de referencia son las peruanas.

## Claves

### Generales

| Clave | Origen | Función afectada | Si falta |
| --- | --- | --- | --- |
| `perfil` | empresa | Herencia de un perfil con nombre | El perfil da sus valores él mismo |
| `empresa` | empresa | Nombre en los informes de planeamiento y el PIDE | Queda el hueco señalado |
| `codigo_empresa` | empresa | Elegir la empresa propia dentro de un paquete VNR-GIS con varias | Se pide si el paquete trae varias |
| `crs_origen` | empresa | Georreferenciar la red: un EPSG proyectado en metros | La web y el CLI lo piden; sin él, se convierte sin GPS |
| `patron_sed_medicion` | empresa | Expresión regular de las SED que solo son medición | No se excluye ninguna por su nombre |
| `escala_diagrama` | empresa | Unidades de diagrama por metro del DGS | La escala del motor |
| `forma_alimentador` | empresa | Expresión regular de los nombres de alimentador; solo avisa | No se avisa de ninguno |
| `patron_libro_clientes` | empresa | Reconocer los libros de clientes: una expresión o varias, con grupos `mes` y `anio` | Se eligen a mano |
| `carpeta_proyectos_pf` | empresa | Carpeta de DIgSILENT de los proyectos | «ConverterSmartGrid» |
| `raices_llm` | empresa | Carpetas que puede leer el asistente local | Solo las del proyecto |
| `estructura` | empresa | Zonales, SET y sistemas: un JSON aparte junto al perfil | La de la propia fuente si la trae |
| `centrales_termicas` | empresa | Medidores de una central dentro de un alimentador | Se conectan desde la web |
| `vias` | empresa | Trazar enlaces por la vía pública con un servicio externo | Línea recta, sin salir a la red |
| `normas` | norma | Normas de calidad distintas de la principal | Solo la principal |
| `gemelo` | empresa | Modelos que no se venden en la 1.0 | Sin efecto |
| `asistente` | empresa | Subtipos de estudio del asistente | Los del programa |
| `valle` | empresa | Puntos de la búsqueda de la ventana de valle | Los del programa |

### Límites de los estudios

| Clave | Origen | Función afectada | Si falta |
| --- | --- | --- | --- |
| `estudios.tension_min_pu` | norma | Juzgar la tensión | Los estudios usan 0,95 de referencia; los informes lo piden en la web |
| `estudios.tension_max_pu` | norma | Juzgar la tensión | Los estudios usan 1,05 de referencia; los informes lo piden en la web |
| `estudios.cargabilidad_max_pct` | norma | Juzgar la cargabilidad | Los estudios usan 100 % de referencia; los informes lo piden en la web |

Los informes los piden porque concluyen con ellos ante el regulador.

### Protecciones

| Clave | Origen | Función afectada | Si falta |
| --- | --- | --- | --- |
| `protecciones.cti_s` | empresa | Intervalo de coordinación entre primaria y respaldo, en segundos | La coordinación no se evalúa y lo dice |
| `protecciones.factor_sensibilidad` | empresa | Corriente de falla mínima entre el arranque de cada dispositivo | La sensibilidad no se evalúa y lo dice |
| `protecciones.margen_poder_corte` | empresa | Poder de corte mínimo entre la corriente de falla máxima | El poder de corte no se evalúa y lo dice |

Ninguno tiene valor de referencia (spec 049): un CTI supuesto aprobaría o rechazaría parejas
que la empresa no ha juzgado. Los ajustes de cada dispositivo van en la hoja «Protecciones» del
libro de la empresa.

### Calibración

| Clave | Origen | Función afectada | Si falta |
| --- | --- | --- | --- |
| `calibracion.factor_potencia_cargas` | empresa | FP de las SED escaladas | Se conserva el de la fuente |
| `calibracion.factor_potencia_minimo_fijas` | empresa | Mínimo de los clientes fijos | Su FP medido |
| `calibracion.factor_potencia_minimo_escaladas` | empresa | Cuánto puede bajar para cuadrar la reactiva de cabecera | No baja |
| `calibracion.bancos_kvar_por_tension` | empresa | Tamaño de banco por tensión, `{"kV": kvar}` | Tamaño de referencia en «Con proyecto», con aviso |
| `calibracion.transformadores_sed` | norma | Fichas de los transformadores nuevos de SED | Se avisa de la sobrecarga sin proponer transformador |
| `calibracion.reparto_probabilistico` | empresa | Reparto probabilístico de las SED escaladas | Reparto determinista |

### Informes

| Clave | Origen | Función afectada | Si falta |
| --- | --- | --- | --- |
| `informes.moneda` | empresa | Rótulo de la moneda en informes y pantallas | «moneda de la empresa»: no se supone ninguna |
| `informes.modelo_estudio` | empresa | Forma del informe de estudio: un `.docx` suyo | Plantilla neutra, y se dice |
| `informes.modelo_factibilidad` | empresa | Forma del informe de factibilidad: un `.docx` suyo | Plantilla neutra, y se dice |
| `informes.modelo_libro` | empresa | Libro Excel de cada informe | Sin libro, y se dice |
| `informes.modelo_planeamiento` | empresa | Forma de los documentos de planeamiento | Documento en blanco |
| `informes.bandas_tension_pct` | empresa | Coloreado por tensión de las figuras: % crecientes | Se pide en la web; sin dato, sale de la banda de tensión, con aviso |
| `informes.bandas_cargabilidad_pct` | empresa | Coloreado por cargabilidad de las figuras: % crecientes | Se pide en la web; sin dato, sale del umbral, con aviso |
| `informes.proyecto_transmision` | empresa | Transformador de la SET en la factibilidad | Esa sección queda señalada |
| `informes.cabecera` | empresa | Rótulos de la cabecera del modelo donde van n.º y referencia | Queda como en el modelo |
| `informes.norma` | norma | Norma de calidad que citan los textos | No nombran ninguna |
| `informes.regulador` | norma | Regulador que citan los textos | No nombran ninguno |
| `informes.libro_perdidas` | empresa | Leer las pérdidas reconocidas de su libro | Se escriben a mano |
| `informes.libro_informe` | empresa | Plano del libro Excel del informe | Sin libro, y se dice |

Si la empresa declara un modelo y el fichero no está, el informe da un error con la ruta: cree tener su forma, y no se le entrega
otra sin que lo pida. Si no declara ninguno, sale con la plantilla neutra y lo dicen la pantalla, el Registro y el JSON del informe.

### Obras y planificación

| Clave | Origen | Función afectada | Si falta |
| --- | --- | --- | --- |
| `escalera.moneda` | empresa | Moneda del costo de las obras | Sin rótulo de moneda |
| `escalera.secciones_normalizadas` | empresa | Conductores de refuerzo | Ficha universal, con aviso |
| `escalera.costos_unitarios` | empresa | Costo de bancos y reguladores | Esas variantes se evalúan sin elegirse por costo |
| `escalera.conductor_terna` | empresa | Conductor de los dos circuitos de una terna nueva: `{"aereo": código, "cable": código}`, códigos como los de `secciones_normalizadas`. El tramo más delgado pasa a él y la terna es del mismo; el de igual o más corriente añade la de su tipo (042:RF-98, RF-99) | La terna se añade del mismo tipo del tramo, con aviso |
| `escalera.alternativas` | empresa | Alternativas de obras por alimentador, un entero de 3 a 6; otro valor es un error (042:RF-105, RF-106) | Se presentan 3 |
| `planificacion.tasa_regulada` | norma | Evaluación económica | 12 % de referencia, con aviso |
| `planificacion.vida_util_anios` | norma | Evaluación económica y SET nueva | 30 años de referencia, con aviso |
| `planificacion.factor_seguridad_set_sin_tasa` | norma | SET nueva sin tasa de crecimiento | 1,25 de referencia, con aviso; con tasa se usa `factor_seguridad_set` |
| `planificacion.capex` | empresa | Leer el libro CAPEX | Sin costo del libro, y se dice |
| `planificacion.tarifas` | empresa | Evaluación privada del PIDE | Queda señalada como pendiente |

`escalera` y `planificacion` tienen más claves técnicas (tolerancias, sorteos, módulos de SET, ternas). Sus valores de referencia se
aplican con aviso, y cada una se valida al usarse.

## Valores que no vienen del perfil

Se conservan a propósito, y se dicen para que nadie los tome por convención de una empresa:

- Los formatos F01 a F15 del PIDE se expresan en US$, porque así los define la norma de planificación.
- La evaluación técnico-económica de DIgSILENT rotula sus costos en US$: es el rótulo de su módulo.
- Una red reconstruida sin tensión conocida usa una tensión provisional, y lo anota en su informe de reconstrucción.
- Una SET nueva sin tensión de alta en el libro ni en el perfil supone la de subtransmisión de la distribución, y lo anota.
