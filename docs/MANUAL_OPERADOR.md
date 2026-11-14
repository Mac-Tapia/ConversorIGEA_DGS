# Manual del operador de ConverterSmartGrid

Lo que se hace cada día, de la red exportada a un informe. Para instalar, vea `MANUAL_INSTALACION.md`; para el perfil de la empresa,
`PERFIL_EMPRESA.md`.

## Qué hace y qué no

Lleva a DIgSILENT PowerFactory la red de una distribuidora, y estudia en DIgSILENT lo que pasa al añadir demanda.

| Se puede | Cómo se marca |
| --- | --- |
| Cargar la fuente y convertir; importar con «Caso base» verificado; calibrar; cargas nuevas; «Con proyecto» con escalera; informes de estudio y de factibilidad con su Excel; flujo, N-1 y transferencia | Sin marca |
| Asistente de órdenes, SET nueva, diagnóstico y borrador del PIDE, confiabilidad | **Beta**, dicho en su pantalla: revise lo que proponga. Se pueden apagar con `CSG_BETA_APAGADAS` |
| Entrenar los modelos, gemelo digital (PINN y GRU), pronóstico por modelos, mejoras y aprendizaje continuo, revisión por roles, preguntas sobre el código | Activos. Piden una GPU NVIDIA con CUDA y el complemento de IA (ver «Entrenar los modelos») |

**No hay** cortocircuito ni protecciones.

### Entrenar los modelos

El programa no trae pesos entrenados: los modelos aprenden en su equipo, con sus datos, que no salen de él. Hace falta:

- Una tarjeta **NVIDIA con CUDA** y su controlador al día. El gemelo digital (PINN y GRU) y los entrenamientos solo corren en la GPU,
  nunca en el procesador: sin ella, el trabajo termina con un mensaje que lo dice, y lo demás del programa sigue igual.
- El **complemento de IA** de capacidades integrales, que trae PyTorch con CUDA y lo de entrenar (`MANUAL_INSTALACION.md`,
  «Complemento de IA»).

`csg.cmd doctor` dice si hay GPU, qué tarjeta es, su versión de CUDA y su memoria libre. Con eso:

- **Asistente → Reentrenar** entrena el modelo de órdenes; el paso 5.2 «Gemelo digital» de la pestaña de cargas aprende y reentrena
  el gemelo.
- Cada modelo nuevo pasa sus puertas antes de usarse; si no las pasa, sigue el anterior y el panel de modelos dice por qué.
- El aprendizaje continuo (050) reentrena solo cuando hay datos nuevos, en segundo plano y cediendo a lo que usted esté haciendo,
  con el plan del ciclo de los datos del asistente; para pararlo, `CSG_AUTOENTRENAMIENTO=0`.
- Las mejoras del código que propone el asistente solo funcionan en el entorno de desarrollo; en el programa instalado lo dice.

## El recorrido

1. **Cargar la fuente.** Una por vez: los tres TXT de CYMDIST, una base `.mdb` o un paquete VNR-GIS. Se reconocen por su contenido, no
   por el nombre. Nunca se mezclan en un espacio de trabajo. Cada espacio es un trabajo: «Nuevo espacio» empieza otro y el anterior se
   conserva.
   En **Empresa del espacio**, escriba el nombre de la distribuidora y pulse **Guardar empresa** si la fuente no lo declara. La empresa de la fuente tiene prioridad. Para retirar el nombre del espacio, vacíe el campo y guarde; si falta en ambos sitios se informa el supuesto. Cambiar este dato no mueve proyectos ya importados. El campo espera mientras se ejecuta un trabajo del motor.
2. **Revisar y elegir alimentadores.** La tabla dice lo que falta. Lo que se pueda deducir con el catálogo se deduce y se anota.
3. **Convertir.** Un fichero `.dgs` por alimentador, o una red unida. Se puede cancelar: lo convertido se queda.
4. **Importar.** Crea el proyecto en la carpeta de DIgSILENT del perfil, con su «Caso base» verificado por el flujo de carga.
5. **Calibrar** («Sin proyecto»). Con el libro de demanda, cuadra la máxima de cabecera. Solo cambia la demanda.
6. **Cargas nuevas y obras** («Con proyecto»). Lleva las cargas y sube por la escalera de bancos, sección y terna, y se para en el
   primer escalón que deja la red en norma. Si ya está en norma, no propone obras.
7. **Informes.** Salen de lo que guardaron la calibración y las obras al correr. Si «Con proyecto» falló o se canceló, el informe lo dice:
   no usa un flujo de otra corrida.

## Cosas que conviene saber

- **DIgSILENT se usa de uno en uno.** Los trabajos que lo necesitan esperan su turno; no hace falta hacer nada.
- **Cerrar el navegador no para un trabajo.** Cancélelo desde la barra de trabajos. Si se cerró el servidor a medias, el trabajo aparece como
  interrumpido, con lo que alcanzó a escribir.
- **Un cambio manual en DIgSILENT es intencionado.** El programa avisa; no lo borra.
- **La salida a internet está apagada.** Cada una se activa aparte y dice cuál falta: vea `SEGURIDAD_Y_PRIVACIDAD.md`.
- **Solo en este equipo.** La web escucha en `127.0.0.1`: no se puede abrir desde otro.

## Si algo no va

| Qué se ve | Qué hacer |
| --- | --- |
| No abre, o falta una función | Pulse la versión, junto al título: dice qué falta y cómo arreglarlo |
| «No converge» | Lea el `historial` del informe: dice lo que informó DIgSILENT, y qué se corrigió antes de importar |
| Espacio marcado como dañado | Ofrece restaurar su copia anterior |
| Un fichero marcado como no disponible | Vuelva a conectar la unidad; la ruta se conserva |
| Aviso de copia vieja | Haga una copia: vea el manual de instalación |
| Fallo que no entiende | `csg.cmd soporte`, y envíe el `.zip` tras mirarlo |
