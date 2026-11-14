# Spec 106 — Un turno de GPU para la suite y los entrenamientos, con plazo y diciendo quién lo tiene

Estado: aprobada · Fecha: 2026-11-12 · Origen: auditoría de la suite de 10a80812 y orden del usuario del
2026-11-12: «las correcciones deben ser sólidas, estables y robustas», «corregir todos los fallos, de fondo».

## Contexto y objetivo
La suite completa de 10a80812 (2026-11-12) dio 62 fallidas de 8 818: 61 «CUDA error: out of memory» y una «ningún
ensayo terminó dentro del presupuesto (027:RF-7)», todas de GPU, con el entrenamiento T7 de la 089 en marcha. Repetidas
solas, las 62 pasaron. Causa: desde 102:RF-22 cada prueba tiene su propia guardia de GPU, así que ninguna veía la del
entrenamiento. Al mismo tiempo, el fixture de módulo `turno` de `test_digital_twin_oraculo.py` se preparaba antes que
el fixture por prueba y tomaba la guardia real: dos puertas de commit esperaron 40 min sin decir nada (hasta 1 800 s,
cada 5 s). Esta spec hace que la suite pida la GPU de la máquina una vez, como cualquier entrenamiento, y que toda
espera tenga plazo y diga quién tiene la GPU.

## Usuarios / actores
La puerta de calidad (spec 102) y quien corre la suite; los entrenamientos de `tools/` que toman `turno_gpu`.

## Requisitos funcionales (EARS)
- RF-1: CUANDO termina la recogida de pytest y alguna prueba elegida usa la GPU en un equipo con CUDA, EL SISTEMA
  tomará el turno de GPU de la máquina una vez para toda la sesión, y dentro de ella cada prueba y cada fixture usará una
  guardia de la propia sesión; una sesión lanzada por una prueba no lo pedirá.
- RF-2: MIENTRAS otro proceso tiene el turno, EL SISTEMA esperará y lo tomará en cuanto quede libre.
- RF-3: MIENTRAS espera, EL SISTEMA dirá cada minuto quién tiene el turno (proceso, orden y desde cuándo); SI vence el
  plazo, ENTONCES lanzará un error con ese dueño.
- RF-4: SI la suite no consigue el turno en su plazo (`CSG_GPU_ESPERA_SUITE_S`, 7 200 s por defecto), ENTONCES pytest
  saldrá con el código 6, fuera de los de pytest (0 a 5), y el dueño, sin juzgar ni omitir ninguna prueba.
- RF-5: EL SISTEMA volcará la pila de todos los hilos de una prueba que dure más de 1 800 s, sin hacerla fallar.
- RF-6: EL SISTEMA marcará `gpu` cada prueba de un módulo que nombre torch, CUDA o la GPU (sin distinguir mayúsculas),
  sin que nadie tenga que acordarse de marcarla.
- Aclaración de RF-6: es conservador a propósito. Un módulo que solo dice «sin GPU» también queda marcado, y como mucho
  espera el turno sin necesitarlo: el 2026-11-12 marcaba 63 de 424 módulos y ninguna prueba de gobierno de la puerta
  del commit. Lo que reserva un proceso hijo no lo ve RF-9: lo cubre RF-10.
- RF-7: MIENTRAS ninguna prueba elegida lleva la marca `gpu`, EL SISTEMA no pedirá el turno ni esperará, aunque otro
  proceso lo tenga (102:RF-18: la puerta de una rama no espera a un entrenamiento).
- RF-8: SI pytest sale con el código de RF-4, ENTONCES la puerta de calidad lo contará como un fallo que dice quién
  tiene la GPU, nunca como «0 fallidas».
- RF-9: SI una prueba sin la marca `gpu` reserva memoria de CUDA en el proceso de pytest, ENTONCES EL SISTEMA la hará
  fallar diciendo que usa CUDA sin la marca, para que el uso indirecto (por `src`, sin nombrar torch) no quede sin turno.
- RF-10: SI una prueba sin la marca `gpu` deja tomado alguna vez el turno de GPU de su propia guardia (ella o un proceso
  que lanzó, porque todo entrenamiento lo pide), ENTONCES EL SISTEMA la hará fallar diciéndolo.
- RF-11: EL SISTEMA hará que la puerta de calidad importe el código del árbol que juzga, también en un worktree que usa
  el `.venv` del árbol principal.
- RF-12: EL SISTEMA hará que todo proceso hijo que lance una prueba con el intérprete del `.venv` cargue el código del
  árbol que se prueba, también en un worktree.
- RF-14: EL SISTEMA dará al Python de DIgSILENT el paquete del conversor solo desde la ruta que fija 103:RF-6, sin
  ninguna otra carpeta con el paquete que traiga el `PYTHONPATH` heredado.
- RF-13: CUANDO un commit cambia lo que ven todas las pruebas (`tests/conftest.py`, `pyproject.toml`), EL SISTEMA
  correrá en su puerta todas las pruebas; y CUANDO cambia un ayudante de `tests/` o un fichero que no es un módulo de
  Python (el `.iss` del instalador, un `.json`, un `.ts`…), las que lo nombran. (2026-11-13: un commit cambió el `.iss`
  y su puerta no eligió `test_instalador_qa`, que lo lee; la regresión entró en la rama.)
- RF-15: EL SISTEMA guardará en el resultado de cada suite las 30 pruebas más lentas con sus segundos, y dirá cuáles pasan
  del umbral de RF-5, sin hacerlas fallar.
- RF-16: CUANDO empieza una sesión de pruebas sin `CSG_RUNTIME_HOME`, EL SISTEMA le dará un runtime propio en una
  carpeta temporal de la sesión, antes de importar la web; y SI al terminar algún registro real de la web
  (`<runtime>/registros/*.log`) recibió líneas con rutas de pytest, ENTONCES la sesión fallará diciendo cuáles.
  (Auditoría del 2026-11-13: 10 de las 85 carpetas del runtime real tenían líneas de pruebas en `registros/web.log`.)
- RF-17: CUANDO empieza una sesión de pruebas sin `CSG_ASISTENTE_DATA` o sin `CSG_TWIN_DATA`, EL SISTEMA dará al
  almacén del asistente y al del gemelo una carpeta de la sesión, nunca `output/web/_asistente`, `output/web/_digital_twin`
  ni `<runtime>/data/web/…` del usuario; lo que una prueba fije por su cuenta manda. (Mismo día: sin ellas, desde el
  árbol principal caían en los 3,8 GB y 1,1 GB del usuario, y desde un worktree en el almacén de un runtime real.)
- RF-18: DONDE el equipo tiene en Windows un adaptador NVIDIA cuyo controlador trae `nvdxgdmal64.dll`, EL SISTEMA dejará
  esa DLL fijada en memoria antes del primer inicio de CUDA de cada proceso del producto y de cada sesión de pruebas; sin
  Windows, sin NVIDIA, sin la clave del registro o sin la DLL no hará nada ni fallará. La fijará con cualquier versión del
  controlador: no se sabe en cuáles está el defecto, y fijarla es inocuo con uno sano. (2026-11-13: con el controlador
  560.94, iniciar CUDA cargaba y descargaba esa DLL y dejaba un hilo que, al siguiente aviso del sistema, ejecutaba en
  ella ya descargada: el proceso moría con 0xC0000005 a los ~90 s, también con `CUDA_VISIBLE_DEVICES=-1`, y la suite caía
  a mitad. Diagnóstico y reproducción mínima en `D:/csg/AV_diagnostico`.) El inicio de CUDA no hace falta pedirlo:
  el primer `backward` de autograd, también en CPU, cuenta los dispositivos de cada backend y llama a `cuInit`, así
  que lo cubre también el entrenamiento en CPU con la GPU oculta, como el reentreno del pronóstico, que corre torch y
  LightGBM en el mismo proceso de la web. (2026-11-14, auditoría de c7: `tests/test_pronostico_demanda.py` entero con
  `CUDA_VISIBLE_DEVICES=-1` caía con 0xC0000005 y se sospechó de los dos OpenMP, `libiomp5md.dll` de torch y
  `vcomp140.dll` de LightGBM. Se descartó: con la DLL fijada conviven 1018 vueltas en 480 s, y sin fijarla caen a la
  vez, en el mismo instante, dos procesos sin relación, uno sin LightGBM. Evidencia en `D:/csg/OPENMP`.)
- RF-19: DONDE el equipo tiene un controlador NVIDIA que no pasa de la última versión con el fallo de RF-18 comprobado,
  EL SISTEMA avisará en el doctor de que conviene actualizarlo, sin bloquear nada, y dirá si la protección de RF-18 está
  activa.

## Requisitos no funcionales
- Sin GPU (GitHub Actions, 102:RF-17) la sesión no pide turno y nada cambia.
- Ningún umbral de modelo ni ninguna prueba se debilita, omite o borra.

## Casos límite
- Dos sesiones de pytest a la vez (la puerta de un commit y la suite completa): la segunda espera a la primera.
- Un entrenamiento que toma el turno a mitad de la suite: no puede, porque lo tiene la suite; espera o falla diciendo
  «GPU ocupada por PID … (suite-pytest)».
- El dueño del turno muere: `BloqueoGPU` reconoce el proceso muerto y lo libera (043:RF-6).

## Fuera de alcance
- Repartir la memoria de una GPU entre dos trabajos a la vez: el tope por proceso quedó refutado (T7, fracción 0,6, y
  aun así 61 fallos por memoria).
- El presupuesto de la prueba de 027:RF-7, que depende del reloj: va en su propia corrección (A3).

## Referencias (verificadas el 2026-11-12; las de RF-18 y RF-19, el 2026-11-13)
- FluidVoice, issue 585 (https://github.com/altic-dev/FluidVoice/issues/585): el mismo cierre al iniciar CUDA, con el
  controlador 555.85. Ni la incidencia ni NVIDIA dicen en qué versión se corrige: por eso RF-19 compara con la última
  versión con el fallo comprobado. chia-gigahorse, issue 336 (https://github.com/madMAx43v3r/chia-gigahorse/issues/336):
  el módulo culpable sale como «nvdxgdmal64.dll_unloaded». Blender, issue 122826
  (https://projects.blender.org/blender/blender/issues/122826), citada en el diagnóstico: el 2026-11-13 su servidor
  respondió 403 y no se pudo releer. Microsoft, *GetModuleHandleExW*
  (https://learn.microsoft.com/windows/win32/api/libloaderapi/nf-libloaderapi-getmodulehandleexw): con
  `GET_MODULE_HANDLE_EX_FLAG_PIN` el módulo queda cargado hasta que termina el proceso, se llame a `FreeLibrary` las
  veces que se llame. Sustentan RF-18.
- PyTorch, *CUDA semantics*, sección de gestión de memoria (https://docs.pytorch.org/docs/2.5/notes/cuda.html): el
  asignador con caché guarda memoria que «seguirá apareciendo como usada en nvidia-smi», así que un proceso no puede dar
  por libre la que otro reservó. Sustenta RF-1 y el fuera de alcance: dos procesos de PyTorch no comparten una GPU con
  seguridad solo con topes.
- pytest-xdist, *Making session-scoped fixtures execute only once*
  (https://pytest-xdist.readthedocs.io/en/stable/how-to.html): un recurso común a varios procesos de prueba se protege
  con un candado de fichero (`FileLock`). Aquí se usa el candado de fichero que ya tiene el proyecto (`BloqueoGPU`,
  043:RF-6), uno por máquina.
- pytest, *How to handle test failures*, `faulthandler_timeout` (https://docs.pytest.org/en/stable/how-to/failures.html):
  «vuelca la pila de todos los hilos si una prueba tarda más de X segundos». Sustenta RF-5.

## Criterios de finalización
Cada RF citado por `tests/test_turno_gpu_de_la_suite.py`; las 62 de la suite de 10a80812 en verde dentro de una suite
completa corrida con un entrenamiento esperando su turno.
