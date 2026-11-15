# Manual de órdenes del programa instalado

Para el operador y para la TI del cliente. Todo lo que se hace con el programa se hace desde la web; estas órdenes son para
comprobar la instalación, preparar el soporte, hacer copias y volver atrás. Se escriben en una ventana de órdenes (`cmd`) y están en
la carpeta del programa, por defecto `%LOCALAPPDATA%\Programs\ConverterSmartGrid`. Cada una responde a `--help`.

Solo se describe lo que trae el programa instalado. Las herramientas de desarrollo y de construcción no se entregan.

## Abrir el programa

| Orden | Qué hace |
| --- | --- |
| `ConverterSmartGrid.cmd` | Lo que abre el acceso directo: arranca el servidor en una ventana negra y abre la web en `http://127.0.0.1:8765` |
| `csg.cmd web` | Lo mismo, desde una ventana de órdenes |

Al cerrar la ventana negra se cierra el programa.

## Comprobar la instalación

| Orden | Qué hace |
| --- | --- |
| `csg.cmd doctor` | Dice qué falta, qué función afecta y cómo arreglarlo: Python, librerías, la web, la carpeta de datos, DIgSILENT, el perfil, el complemento de IA, la GPU, Tesseract y Excel o WPS. `--json` da lo mismo en JSON |
| `csg.cmd version` | La versión instalada y sus notas |
| `csg.cmd validar-perfil` | Comprueba el perfil de empresa activo: qué falta y qué función afecta. Con `--ruta FICHERO`, uno antes de cargarlo |

## Soporte

| Orden | Qué hace |
| --- | --- |
| `csg.cmd soporte` | Deja en la carpeta de datos un `.zip` con el diagnóstico, las versiones y los registros anonimizados, sin redes, cargas ni informes. Dice lo que lleva en `LEAME.txt`; mírelo antes de enviarlo |

Los registros están en `runtime\registros\` de la carpeta de datos.

## Convertir sin la web

La web hace lo mismo con más ayuda; estas órdenes sirven para un lote desde un guion.

| Orden | Qué hace |
| --- | --- |
| `csg.cmd list --red RED.txt --loads CARGA.txt --equipment EQUIPO.txt` | Lista los alimentadores de la entrada y su inventario |
| `csg.cmd convert --red RED.txt --loads CARGA.txt --equipment EQUIPO.txt --all --out-dir SALIDA` | Convierte todos los alimentadores a DGS; `--workers 0` usa los procesos que convenga |

## Copias de los datos

Con el programa cerrado y sin trabajos en curso:

| Orden | Qué hace |
| --- | --- |
| `copia_datos.cmd crear --destino CARPETA` | Crea una copia `csg-copia-…` con su manifiesto y la huella de cada fichero |
| `copia_datos.cmd estado` | Cuándo fue la última copia |
| `copia_datos.cmd verificar --copia CARPETA` | Comprueba las huellas de una copia sin tocar nada |
| `copia_datos.cmd restaurar --copia CARPETA` | Restaura una copia; lo que hubiera se aparta, sin borrarlo |

## Volver a la versión anterior

| Orden | Qué hace |
| --- | --- |
| `volver_atras.cmd` | Vuelve a la versión anterior y a los datos de la copia que se hizo al actualizar; `--sin-restaurar` deja los datos de ahora |

## Instalar sin preguntas

La instalación silenciosa para la TI está en el manual de instalación, apartado «Instalación silenciosa, para la TI del cliente».
