# Plan — Spec 091

## DIgSILENT abierto (RF-1 a RF-6)

- `web/services.py`: una función `sin_conexion_digsilent()` sustituye a los seis `UserError` con «Ábralo». Pregunta al
  arnés si hay un DIgSILENT abierto a mano y, si no, toma la última línea `ERROR` de `cola_pf/servidor.log`.
  Descartada: que cada guion devuelva otro código, porque el 3 ya cubre varias causas y hay guiones de otras specs.
- `tools/pf_cliente.py`: al terminar al arrancar, copia esa misma línea al Registro. `pf_arnes.ultima_causa()` es el único sitio que lee el registro.
- `pf_arnes.barrer_marcas()`: al tomar el turno quita `.conexion_<pid>` de procesos muertos.
- `App.tsx` y `FeedersPanel.tsx`: textos.

## Pestañas (RF-7, RF-8)

`App.tsx` deja montada cada pestaña ya visitada, con `hidden`, y las agrupa con la clave del espacio. Descartada:
subir el estado de `CargasTab` al contexto, porque son decenas de estados repartidos en sus hijos.

## Clientes por su hoja (RF-9 a RF-13)

`demanda_medida.py`: `cabeceras_de_hojas(path)`, con caché en memoria por ruta, tamaño y fecha, y
`completar_desde_hojas()`. Descartada: guardarla junto a la POT de 042:RF-96 (`crecimiento.pot_de_los_libros`), porque
esa guarda en disco otro dato (la POT de cada cliente) y vive en un módulo que importa a este; se usa la misma clave
de libro (ruta, tamaño y fecha) para que un libro cambiado se vuelva a leer en las dos. Se
busca la SED por igualdad con las de la red cargada, sin posición ni patrón, para que valga en cualquier empresa
(constitución P13). `_cruzar_clientes_en_red` la llama antes de `reconciliar_radiales`, que ya pone el alimentador de la
red y rechaza lo ambiguo.

## Máxima, cruce y estudio (RF-14 a RF-23)

- `app.py`: `DemandaMedidoresIn.project`, copiado al resultado del trabajo; `ajuste_plan` lo compara.
- `DemandaMedida.tsx`: la máxima se filtra por proyecto y año; el cruce con todo el año se hace por mes y se une
  (cambia 025:RF-10: antes solo lo hacía el ajuste); una máxima nueva borra el cruce. `AjusteCabecera.tsx` recibe si
  falta cruzar, junto al criterio por alimentador de 039:RF-8.
- `services.estudios_plan`: lee `tipo_ajuste` de cada informe (`faltan_recalibrar`, función pura) y
  `avisos_de_recalibracion` añade sus avisos al plan, sin rechazarlo. La web lo anticipa con los mismos informes en
  `CargasTab` y deja el botón activo con el aviso. Descartada: rechazar el plan y apagar el botón, como hacía la rama
  original; nada bloquea salvo la red vacía.

## Informes y textos (RF-24 a RF-34)

- `tools/ajuste_cabecera_pf.py`: `cuadrado_q` al terminar, y el texto del FP de las fijas.
- `demanda_medida.maxima_de_registros`: aviso de empate.
- `web/doctor.py`: usa `documentos_solicitud.tesseract`.
- RF-33 retirada: `web/__main__.py` ya llama a `salidas_red.preparar_entorno_sin_red()` (086:RF-22).
- RF-34: ya está en `digital_twin/integration.py` (el motivo de la lectura bloqueada al Registro); solo se cita su prueba.

## Pruebas

`tests/test_flujo_a_estudio.py`: sintéticas de cruce, plan, estudio, marcas y textos, con guion falso. El navegador real
y DIgSILENT se comprueban en la tarea `[DIgSILENT]`. Suite completa con datos reales al final.
