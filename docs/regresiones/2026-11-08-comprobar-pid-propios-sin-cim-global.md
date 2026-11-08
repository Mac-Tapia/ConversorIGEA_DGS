# Comprobar los PID propios sin depender de una enumeración global

## Síntoma

La prueba que confirma el cierre de un guion y su hijo podía omitirse si la consulta
global de procesos devolvía una lista vacía. No llegaba a comprobar los dos PID que
el propio proceso de prueba había guardado, por lo que el cierre del árbol quedaba
sin verificar.

La primera corrección comprobaba los dos PID guardados por el padre. En Windows,
el PID devuelto por Popen puede ser un redirector: su ausencia no demuestra que
haya terminado el intérprete hoja. La revisión reprodujo ese falso verde con el
envoltorio muerto y su hijo real aún vivo.

## Causa

La comprobación final usaba la enumeración global como condición previa para comprobar
dos identidades ya conocidas. El resultado vacío no permite distinguir un error de
consulta de otros motivos. La causa concreta de la consulta vacía observada durante
la suite no se pudo reproducir; no se atribuye a un timeout ni se amplía su límite.
Además, el PID de Popen se había tratado como si siempre fuera el intérprete real.

## Comprobación permanente

Mantener el proceso real, su hijo, el límite de arranque de tres segundos y el retorno
de tiempo agotado. Leer los dos PID positivos y distintos registrados por ese proceso
y leer el handshake escrito por el propio intérprete hijo con su `os.getpid()`.
Consultar padre, redirector e hijo real mediante `psutil.pid_exists`, disponible en
el entorno. Conservar los dos PID originales positivos y distintos; la hoja debe
ser positiva y distinta del padre, y puede coincidir con Popen cuando no hay
redirector. Un handshake ausente, vacío o inválido falla sin omitir. Un PID presente
falla la comprobación; una excepción de consulta se propaga
y nunca se convierte en una confirmación de muerte (005:RF-21).

La enumeración global se simula vacía solo después de que el cierre real haya
terminado, sin alterar el mecanismo de cierre ni sus guardias de propiedad. No se
envían señales para comprobar existencia. La prueba negativa crea únicamente su
propio hijo y lo termina y espera mediante su objeto Popen en la limpieza.
La negativa del envoltorio crea un árbol propio, captura identidades de creación,
termina su envoltorio y confirma que la hoja sigue viva. La comprobación debe
rechazarla aunque los dos PID originales ya estén ausentes; su limpieza solo actúa
sobre los descendientes propios con identidad capturada.

## Prueba

- `tests/test_carpeta_pf.py::test_cortar_un_guion_termina_tambien_sus_hijos`.
- `tests/test_carpeta_pf.py::test_comprobar_pids_rechaza_un_hijo_propio_vivo_sin_cim`.
- `tests/test_carpeta_pf.py::test_comprobar_pids_no_trata_access_denied_como_muerto`.
- `tests/test_carpeta_pf.py::test_redirector_muerto_no_oculta_hoja_propia_viva`.
- `tests/test_carpeta_pf.py::test_pid_hijo_real_ausente_o_invalido_no_confirma_cierre`.
- `tests/test_carpeta_pf.py::test_pid_hijo_real_puede_coincidir_con_popen_sin_redirector`.

Evidencia externa `p25_guardia_pid_propios_20261108`: las negativas detectan que el
criterio anterior omitía comprobar PID propios cuando CIM estaba vacío; con la
consulta directa, las tres pruebas pasan sin omisiones. No cambia el runtime de
procesos, sus timeouts o las guardias, ni se ejecuta PowerFactory o GPU.
El correctivo posterior queda en `p25_guardia_pid_leaf_20261108`: siete fallos
deterministas muestran la hoja omitida y los handshakes no comprobados; diez casos
finales pasan con los tres PID explícitos, sin omisiones. La evidencia previa se
conserva y no se presenta como aceptación de la hoja que entonces no se comprobaba.
