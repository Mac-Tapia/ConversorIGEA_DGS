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

## Llevarlo a otro equipo o a otro usuario

El programa se instala **por usuario de Windows**: cada usuario tiene su instalación y sus datos, y no se comparten solos. DIgSILENT no
viene en el instalador: cada equipo usa el suyo, con su propia licencia.

### En el equipo o el usuario nuevo

1. Compruebe que tiene DIgSILENT PowerFactory 2024 con su Python 3.12, abierto al menos una vez con su licencia. Si está en otra carpeta,
   defina la variable de usuario `PF_PYTHON` con la ruta de su carpeta `Python\3.12`.
2. Copie `ConverterSmartGrid-<versión>-setup.exe` e instálelo como se dice en [Instalar](#instalar). No hace falta internet.
3. Abra **ConverterSmartGrid - diagnóstico**. Tiene que decir «listo para trabajar» y, en DIgSILENT, la carpeta de su API.
4. Si es otra empresa, cree su perfil como se dice en [Perfil de empresa](#perfil-de-empresa) y compruébelo con `validar-perfil`.
5. Pruebe con un proyecto de prueba antes de trabajar: cargue la fuente, convierta un alimentador e impórtelo en DIgSILENT.

### Llevarse los datos, si hace falta

Una instalación nueva empieza sin espacios, y es lo normal en otra empresa. Para conservar los de otro puesto:

1. En el puesto antiguo, con el programa cerrado: `copia_datos.cmd crear --destino E:\copias`.
2. Lleve la carpeta `csg-copia-…` al puesto nuevo.
3. En el puesto nuevo, con el programa cerrado: `copia_datos.cmd verificar --copia E:\copias\csg-copia-…` y, si está bien,
   `copia_datos.cmd restaurar --copia E:\copias\csg-copia-…`. Lo que hubiera se aparta, sin borrarlo.
4. Abra el programa. Lo que estaba fuera de los datos, como una fuente en otra unidad, sale como **no disponible**: vuelva a indicarlo o
   descártelo.

**La copia no lleva los proyectos de DIgSILENT**, que viven en la base de datos de DIgSILENT. Expórtelos e impórtelos con DIgSILENT, o vuelva a
importar desde la web. Los datos de una distribuidora son suyos: no los copie a otro equipo sin su permiso, ni los suba a internet.

### Si algo no sale

| Qué ve | Qué hacer |
| --- | --- |
| El diagnóstico no encuentra DIgSILENT | Defina `PF_PYTHON`, o instale la versión con Python 3.12 |
| «Esta pestaña no tiene sesión» | Abra el acceso directo: cada arranque usa una sesión nueva, y los enlaces guardados dejan de valer |
| En el puerto hay un Conversor de otra sesión | Ciérrelo y vuelva a abrir el acceso directo |
| El instalador rechaza la carpeta | Use una ruta más corta: Windows no carga librerías por encima de 259 caracteres |
| Windows avisa de un editor desconocido | El instalador no va firmado; compruebe que vino de quien se lo dio |

## Construir el instalador

Solo para quien prepara una versión; un operador no lo necesita. Hace falta el repositorio, con Python 3.12, Node e
[Inno Setup 6](https://jrsoftware.org/isinfo.php), y el `python-3.12.x-embed-amd64.zip` de python.org.

```bat
cd frontend && npm ci && npm run build && cd ..
python tools\construir_candidato.py candidato --salida C:\csg\candidato --python-embebido python-3.12.10-embed-amd64.zip
python tools\comprobar_entrega.py --candidato C:\csg\candidato
ISCC.exe /DCandidato=C:\csg\candidato /DVersion=1.0.0rc1 /OC:\csg\salida instalador\ConverterSmartGrid.iss
```

Use rutas cortas: la de construir se suma a la de cada fichero. El candidato rechaza lo que lleve el nombre de una empresa o un peso entrenado.

## Complemento de IA (opcional)

El núcleo no trae `torch`: pesa gigas y nada de lo que se vende en la 1.0 lo necesita. Su lista está en
`requirements-complemento-ia.txt`. Solo hace falta para los modelos locales del asistente de órdenes, que está en beta; se instala con
salida a internet, o desde un paquete offline con su `instalacion.lock` y la carpeta `wheels`.
La versión 1.0 no entrega pesos entrenados.

Para preparar ese paquete con CPython 3.12 de 64 bits en Windows, descargue previamente las ruedas
de la lista y sus dependencias a una caché separada y ejecute:

```powershell
python tools/construir_candidato.py complemento-ia --salida D:/entregas/ia --ruedas-cache D:/cache-ia --version 1.0.0rc3
```

La construcción usa esa caché sin red y respeta las versiones del núcleo. Incluye inventario,
avisos y huellas, y rechaza una salida que ya contenga otro paquete. Pruebe primero sobre una copia
separada de la instalación. Con el programa cerrado, desde la carpeta del complemento y usando
el Python entregado en esa copia:

```powershell
python.exe -m pip install --no-index --require-hashes --find-links wheels -r instalacion.lock
python.exe -m pip check
```

La instalación de dependencias no activa modelos. Compruebe su carga y las capacidades con `doctor`
antes de usar esa copia; el paquete del núcleo sigue disponible para volver atrás.

## Si algo falla

1. `csg.cmd doctor` dice qué falta.
2. `csg.cmd soporte` deja en la carpeta de datos un `.zip` para enviarlo al soporte. Lleva el diagnóstico, las versiones y los registros
   anonimizados, sin redes, cargas ni informes; dice lo que lleva en `LEAME.txt`. Mírelo antes de enviarlo.

Los registros están en `runtime\registros\` de la carpeta de datos: cinco ficheros de 5 MB como máximo.
