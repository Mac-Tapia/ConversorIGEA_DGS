# Manual de instalación de ConverterSmartGrid

Para quien instala el programa en el puesto de un operador. No hace falta saber programar, ni tener Python, Node o internet.

## Qué hace falta

| Requisito | Para qué | Si falta |
| --- | --- | --- |
| Windows 10 u 11 de 64 bits | Todo | No se instala |
| 2 GB libres para el programa y unos cuantos más para los datos | Todo | La pantalla de diagnóstico avisa |
| DIgSILENT PowerFactory 2024 con su Python 3.12, y su licencia | Importar, calibrar, estudios, obras e informes | Convertir a DGS sigue funcionando |
| Microsoft Access Database Engine de 64 bits | Cargar una base `.mdb` de CYMDIST | Las otras fuentes siguen funcionando |
| ODBC Driver 18 for SQL Server, y SQL Server Express si la copia es local | Cargar una copia `.bak` de VNR-GIS | Las otras fuentes siguen funcionando |
| Tesseract con el idioma español | Leer un PDF escaneado del solicitante | Un PDF con texto se lee sin él |

Solo DIgSILENT y los dos drivers pueden pedir permisos de administrador. ConverterSmartGrid no los pide.

## Instalar

1. Ejecute `ConverterSmartGrid-<versión>-setup.exe`.
2. Acepte la carpeta propuesta, `%LOCALAPPDATA%\Programs\ConverterSmartGrid`, y el acceso directo si lo quiere. Una carpeta con una ruta
   muy larga no sirve: Windows no carga librerías por encima de 259 caracteres, y el instalador lo dice.
3. Espere: comprueba la huella de cada fichero, instala sin salir a internet y prueba el programa. Si algo falla, lo dice, y lo
   que hubiera instalado sigue como estaba.
4. Abra el acceso directo **ConverterSmartGrid**. Se abre el navegador con la web, en `http://127.0.0.1:8765`, y una ventana negra
   que es el servidor: al cerrarla se cierra el programa.

### Comprobar la instalación

Pulse la versión, junto al título de la web, o abra **ConverterSmartGrid - diagnóstico** en el menú de inicio. Dice qué falta, qué
función afecta y cómo arreglarlo. Lo mismo por órdenes:

```bat
"%LOCALAPPDATA%\Programs\ConverterSmartGrid\csg.cmd" doctor
```

Sale con código 0 si no falta nada imprescindible. Los **avisos** son requisitos opcionales: el programa funciona sin ellos, salvo
la función que indican.

## Dónde queda cada cosa

| Qué | Dónde | Al actualizar | Al desinstalar |
| --- | --- | --- | --- |
| Programa | `%LOCALAPPDATA%\Programs\ConverterSmartGrid` | Se añade la versión nueva | Se borra |
| Datos: espacios, perfil, catálogos, registros | `%LOCALAPPDATA%\ConverterSmartGrid\datos` | Se conservan, con copia previa | **Se conservan** |

Para otra carpeta de datos, por ejemplo con más espacio, defina la variable de usuario `CSG_DATOS_HOME` antes de abrir el programa.

## Perfil de empresa

Sin perfil no se supone nada: el programa pide el sistema de coordenadas y no excluye ninguna SED por su nombre. Para dar el de su
empresa, copie `perfil_plantilla` como se explica en `PERFIL_EMPRESA.md` a `config\perfil_empresa.json` dentro de la carpeta de
datos, y compruébelo:

```bat
csg.cmd validar-perfil
```

## Actualizar

Cierre el programa y ejecute el instalador de la versión nueva. Antes de cambiar de versión copia los datos a
`copias_actualizacion\` dentro de la carpeta de datos. Si la versión nueva no responde, sigue la anterior.

## Volver a la versión anterior

Con el programa cerrado:

```bat
"%LOCALAPPDATA%\Programs\ConverterSmartGrid\volver_atras.cmd"
```

Vuelve a la versión anterior y a los datos de la copia previa. Lo que había se aparta, sin borrarlo; con `--sin-restaurar` se
quedan los datos de ahora. Una versión anterior no abre un espacio que una más nueva ya haya migrado: lo dice, no lo pisa.

## Copias de los datos

```bat
"%LOCALAPPDATA%\Programs\ConverterSmartGrid\copia_datos.cmd" crear --destino E:\copias
```

La web avisa cuando la última copia es vieja. Las órdenes `verificar` y `restaurar` están en su ayuda (`copia_datos.cmd --help`).

## Complemento de IA (opcional)

El núcleo no trae `torch`: pesa gigas y nada de lo que se vende en la 1.0 lo necesita. Su lista está en
`requirements-complemento-ia.txt`. Solo hace falta para los modelos locales del asistente de órdenes, que está en beta; se instala con
salida a internet y con su propia decisión de licencias. La versión 1.0 no entrega pesos entrenados.

## Si algo falla

1. `csg.cmd doctor` dice qué falta.
2. `csg.cmd soporte` deja en la carpeta de datos un `.zip` para enviarlo al soporte. Lleva el diagnóstico, las versiones y los registros
   anonimizados, sin redes, cargas ni informes; dice lo que lleva en `LEAME.txt`. Mírelo antes de enviarlo.

Los registros están en `runtime\registros\` de la carpeta de datos: cinco ficheros de 5 MB como máximo.
