# Guía de la prueba con una persona ajena al proyecto

Para la tarea T41 de la versión 1.0: una persona que no conoce el proyecto instala el programa y convierte un alimentador
**siguiendo solo `MANUAL_INSTALACION.md`**. La prueba sale bien si lo consigue sin ayuda; si no, lo que no entendió se corrige en
el manual y se repite.

Lo marcado *(pendiente de comprobar con el rc6)* sale del código y del manual, pero aún no se ha visto en una instalación hecha con
el instalador de la versión que se prueba.

## Antes de empezar (lo prepara quien organiza la prueba)

- [ ] Un equipo con Windows 10 u 11 de 64 bits y una cuenta de Windows **en la que nunca se instaló ConverterSmartGrid**. En esa
      cuenta no debe haber `%LOCALAPPDATA%\Programs\ConverterSmartGrid` ni `%LOCALAPPDATA%\ConverterSmartGrid\datos`.
- [ ] El instalador `ConverterSmartGrid-<versión>-setup.exe` del candidato que se prueba, y `MANUAL_INSTALACION.md` impreso o en
      otra pantalla.
- [ ] Una fuente de prueba para convertir, una sola: los tres TXT de CYMDIST, una base `.mdb` o un paquete VNR-GIS, con permiso de
      la distribuidora para usarla en la prueba. No la saque del equipo ni la suba a internet.
- [ ] Si la prueba llega a DIgSILENT (paso 9, opcional): DIgSILENT PowerFactory 2021 o posterior, con licencia, y un proyecto de
      prueba nuevo. No use proyectos de trabajo.
- [ ] Un observador que **no ayuda**: solo anota en la hoja. Si la persona se atasca más de 10 minutos en un paso, el observador
      anota dónde y le dice solo el número de la sección del manual que lo explica.

## Pasos

Cada paso dice lo que la persona hace (según el manual) y lo que debe ver. El observador marca «bien» si lo vio, o anota qué vio en
su lugar.

1. **Leer «Qué hace falta».** La persona dice qué tiene y qué no de la tabla de requisitos.
   Debe ver: que sin DIgSILENT puede convertir igual, y que lo demás es opcional según su fuente.

2. **Ejecutar el instalador.**
   Debe ver: quizá el aviso de Windows de editor desconocido (el instalador no va firmado); luego el instalador en español,
   con la carpeta `%LOCALAPPDATA%\Programs\ConverterSmartGrid` y la casilla «Crear un acceso directo en el escritorio».

3. **Esperar a que termine.**
   Debe ver: «Comprobando las huellas e instalando...» y, al final, el instalador terminado sin el aviso «No se pudo terminar la
   instalacion». En el menú de inicio, **ConverterSmartGrid** y **ConverterSmartGrid - diagnostico**.

4. **Abrir el diagnóstico** (**ConverterSmartGrid - diagnostico**).
   Debe ver: una consola cuya primera línea dice «ConverterSmartGrid <versión>: listo para trabajar.», líneas con `[bien]` y
   algunas con `[aviso]` (por ejemplo «Complemento de IA: No instalado.»). Ninguna con `[FALTA]`.

5. **Abrir el programa** (**ConverterSmartGrid**).
   Debe ver: una ventana negra (el servidor) y el navegador en `http://127.0.0.1:8765`, con «Conectando con el conversor…» y luego
   el título **ConverterSmartGrid** y la tarjeta **1 Entrada de datos**. Arriba puede salir «Aún no hay ninguna copia de sus
   datos.»: es normal en una instalación nueva.

6. **Elegir la fuente y darle los ficheros.** En **1 Entrada de datos**, elegir «Tres TXT de CYMDIST», «Base Access (.mdb)» o
   «VNR-GIS», y soltar o elegir los ficheros. Con los TXT basta soltarlos juntos en «Suelte aquí los TXT de la entrega».
   Debe ver: cada fichero en su casilla y, debajo, «Los tres TXT están listos. Pulse «Cargar / listar alimentadores».» (o «Base de
   datos lista.» o «Paquete VNR-GIS listo.»).

7. **Indicar el sistema de coordenadas, si se pide.** Sin perfil de empresa, «Opciones de conversión» avisa «Sin perfil de empresa
   no se supone ningún CRS…».
   Debe ver: que puede escribir el EPSG de su zona en «CRS de origen», o cargar un perfil en **Perfil de la empresa** (si quien
   organiza le dio uno).

8. **Listar y convertir.** En **2 Alimentadores**, pulsar **Cargar / listar alimentadores**; marcar un alimentador de la tabla y
   pulsar **Convertir <alimentador> → DGS**.
   Debe ver: las cifras de la fuente (alimentadores, convertibles, tramos, cargas) y, al terminar, «DGS convertidos» con al menos
   1; luego **Descargar selección (.zip)** activo. Al descargar, un `.zip` con el `.dgs` del alimentador.

9. **(Opcional) Importar en DIgSILENT.** Con el alimentador marcado, **Cargar en DIgSILENT + flujo**.
   Debe ver: el trabajo en la barra de trabajos y, al terminar, el proyecto en DIgSILENT con su flujo de carga. Si no converge, el
   informe lo dice con lo que devolvió DIgSILENT.

10. **Cerrar el programa** cerrando la ventana negra, y volver a abrirlo con el acceso directo.
    Debe ver: el mismo espacio de trabajo, con el alimentador convertido.

11. **Hacer una copia de los datos**, con el programa cerrado, con la orden del manual (`copia_datos.cmd crear --destino …`), en una
    carpeta de prueba.
    Debe ver: una carpeta `csg-copia-…` en el destino; al abrir de nuevo el programa, el aviso de la copia ya no sale.
    *(Pendiente de comprobar con el rc6: el botón «Hacer una copia ahora» del aviso.)*

12. **Preparar el paquete de soporte** (`csg.cmd soporte`).
    Debe ver: un `.zip` en la carpeta de datos con un `LEAME.txt` que dice lo que lleva.

13. **Instalar la versión B encima** (quien organiza le da el instalador de una segunda versión, B, que sigue a la A
    instalada en el paso 2), con el programa cerrado.
    Debe ver: el instalador terminado sin el aviso «No se pudo terminar la instalacion»; el diagnóstico dice
    «ConverterSmartGrid <B>: listo para trabajar.», y en `%LOCALAPPDATA%\Programs\ConverterSmartGrid\documentos` el manual
    y las notas de B. El registro del instalador dice «Se puede volver a la version <A> con volver_atras.cmd.».

14. **Volver a la versión anterior**, con el programa cerrado, con `volver_atras.cmd` del manual.
    Debe ver: en la consola, `"version": "<A>"` y `"dejada": "<B>"`; el diagnóstico vuelve a decir
    «ConverterSmartGrid <A>: listo para trabajar.», y «documentos» tiene el manual y las notas de A, sin los de B. Al abrir
    el programa, el mismo espacio de trabajo.

15. **Volver atrás otra vez.**
    Debe ver: «No hay una versión anterior a la que volver.», y nada cambia (el diagnóstico sigue en A).

16. **Reinstalar la versión B** con su mismo instalador.
    Debe ver: el instalador terminado sin aviso, sin «ya es la instalada»; el diagnóstico dice «ConverterSmartGrid <B>: listo
    para trabajar.», «documentos» tiene los de B y el registro del instalador dice «Se puede volver a la version <A> con
    volver_atras.cmd.». Si algún paso dice «Cierre los documentos de ConverterSmartGrid abiertos (manual, notas) y vuelva a
    intentarlo», cerrar el manual o las notas abiertos y repetirlo: lo instalado sigue como estaba.

Al terminar, quien organiza desinstala desde «Aplicaciones instaladas» y borra la carpeta de datos y la fuente de prueba de ese
equipo.

## Hoja del observador

Prueba: candidato `____________` · equipo `____________` · fecha `__________` · persona (iniciales) `____` · observador `____`

| Paso | ¿Bien? | Minutos | Dónde dudó o se atascó (sus palabras) | Qué vio en lugar de lo esperado | Sección del manual que faltaba o confundía |
| --- | --- | --- | --- | --- | --- |
| 1 Requisitos | | | | | |
| 2 Instalador | | | | | |
| 3 Fin de la instalación | | | | | |
| 4 Diagnóstico | | | | | |
| 5 Abrir el programa | | | | | |
| 6 Fuente y ficheros | | | | | |
| 7 Coordenadas | | | | | |
| 8 Listar y convertir | | | | | |
| 9 DIgSILENT (opcional) | | | | | |
| 10 Cerrar y reabrir | | | | | |
| 11 Copia de los datos | | | | | |
| 12 Paquete de soporte | | | | | |
| 13 Instalar B encima | | | | | |
| 14 Volver a la anterior | | | | | |
| 15 Volver atrás otra vez | | | | | |
| 16 Reinstalar B | | | | | |

Palabras del manual que no entendió: `________________________________________________`

¿Pidió ayuda? En qué paso y qué se le dijo: `________________________________________________`

Resultado: [ ] lo consiguió sin ayuda · [ ] lo consiguió con la ayuda anotada · [ ] no lo consiguió

## Qué se hace con la hoja

1. Cada fila con una duda o un atasco se convierte en un cambio de `MANUAL_INSTALACION.md`, en el mismo cambio que cita la hoja.
2. Si lo que vio no coincide con lo que dice el manual, se mira si falla el programa o el manual, y se corrige el que esté mal.
3. La T41 se da por hecha cuando una persona lo consigue sin ayuda, o cuando todo lo anotado está corregido en el manual. La hoja
   rellenada se guarda como evidencia, fuera de git si lleva datos de la distribuidora.
