# Comprobar los PID propios sin depender de una enumeración global

## Síntoma

La prueba que confirma el cierre de un guion y su hijo podía omitirse si la consulta
global de procesos devolvía una lista vacía. No llegaba a comprobar los dos PID que
el propio proceso de prueba había guardado, por lo que el cierre del árbol quedaba
sin verificar.

## Causa

La comprobación final usaba la enumeración global como condición previa para comprobar
dos identidades ya conocidas. El resultado vacío no permite distinguir un error de
consulta de otros motivos. La causa concreta de la consulta vacía observada durante
la suite no se pudo reproducir; no se atribuye a un timeout ni se amplía su límite.

## Comprobación permanente

Mantener el proceso real, su hijo, el límite de arranque de tres segundos y el retorno
de tiempo agotado. Leer los dos PID positivos y distintos registrados por ese proceso
y consultar directamente cada uno mediante `psutil.pid_exists`, disponible en el
entorno. Un PID presente falla la comprobación; una excepción de consulta se propaga
y nunca se convierte en una confirmación de muerte (005:RF-21).

La enumeración global se simula vacía solo después de que el cierre real haya
terminado, sin alterar el mecanismo de cierre ni sus guardias de propiedad. No se
envían señales para comprobar existencia. La prueba negativa crea únicamente su
propio hijo y lo termina y espera mediante su objeto Popen en la limpieza.

## Prueba

- `tests/test_carpeta_pf.py::test_cortar_un_guion_termina_tambien_sus_hijos`.
- `tests/test_carpeta_pf.py::test_comprobar_pids_rechaza_un_hijo_propio_vivo_sin_cim`.
- `tests/test_carpeta_pf.py::test_comprobar_pids_no_trata_access_denied_como_muerto`.

Evidencia externa `p25_guardia_pid_propios_20261108`: las negativas detectan que el
criterio anterior omitía comprobar PID propios cuando CIM estaba vacío; con la
consulta directa, las tres pruebas pasan sin omisiones. No cambia el runtime de
procesos, sus timeouts o las guardias, ni se ejecuta PowerFactory o GPU.
