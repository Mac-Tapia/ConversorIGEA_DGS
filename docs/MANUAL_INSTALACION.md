# Manual de instalación de ConverterSmartGrid

Para quien instala el programa en el puesto de un operador. No hace falta saber programar, ni tener Python, Node o internet.
Guarde este manual junto al instalador: el programa instalado no trae una copia aparte.

Lo que va marcado *(pendiente de comprobar con el rc6)* está en el programa, pero todavía no se ha comprobado en una
instalación hecha con el instalador.

## Qué hace falta

| Requisito | Para qué | Si falta |
| --- | --- | --- |
| Windows 10 u 11 de 64 bits | Todo | No se instala |
| Al menos 2 GB libres en el disco de los datos | Conversiones grandes, resultados e informes | El diagnóstico avisa |
| DIgSILENT PowerFactory 2021 o posterior, con su licencia | Importar en DIgSILENT, calibrar, estudios, obras e informes | Convertir a DGS sigue funcionando |
| Microsoft Access Database Engine de 64 bits | Cargar una base `.mdb` de CYMDIST | Las otras fuentes siguen funcionando |
| «ODBC Driver 18 for SQL Server» de Microsoft, y SQL Server Express si la copia es local | Cargar una copia `.bak` de VNR-GIS | Las otras fuentes siguen funcionando |
| Tesseract OCR con el idioma español (`spa`) | Leer un PDF escaneado del solicitante | Un PDF con texto se lee sin él |

DIgSILENT, los drivers, SQL Server Express y Tesseract pueden pedir permisos de administrador al instalarlos. ConverterSmartGrid no
los pide: se instala para su usuario de Windows.

**DIgSILENT de cualquier versión desde la 2021.** No hace falta configurar nada: el programa busca las PowerFactory instaladas en
`Program Files` de cada unidad y las que registra Windows, y usa la más nueva que pueda cargar. Para eso trae los Python que piden
las versiones 2021 a 2023 (3.9, 3.10 y 3.11), además del suyo (3.12). Si tiene varias, puede elegir otra desde la web (vea
[Elegir la versión de DIgSILENT](#elegir-la-versión-de-digsilent)).

**Tesseract en español.** Instálelo de forma que la orden `tesseract` se encuentre: en el `PATH`, en su carpeta de instalación
habitual, o indicando el ejecutable con la variable de usuario `CSG_TESSERACT`. Si no puede escribir en la carpeta de Tesseract
para añadir el idioma `spa`, ponga `spa.traineddata`, con una copia de `eng.traineddata` al lado, en
`%USERPROFILE%\.convertersmartgrid\tessdata`, o en la carpeta que diga la variable `CSG_TESSDATA`.

**Licencias.** El programa no incluye ni concede licencias de terceros. Cada usuario necesita las suyas: la de DIgSILENT y el
permiso de la distribuidora para usar sus datos.

## Instalar

1. Ejecute `ConverterSmartGrid-<versión>-setup.exe`. El instalador no va firmado: si Windows avisa de un editor desconocido,
   compruebe que el fichero vino de quien se lo dio antes de ejecutarlo.
2. El instalador está en español. Acepte la carpeta propuesta, `%LOCALAPPDATA%\Programs\ConverterSmartGrid`, y marque «Crear un
   acceso directo en el escritorio» si lo quiere. Use una ruta corta: Windows no carga librerías por encima de 259 caracteres.
3. Espere. Verá «Comprobando las huellas e instalando...»: comprueba cada fichero, instala sin salir a internet y prueba el
   programa con su diagnóstico antes de darlo por instalado.
   Si algo falla, sale el aviso «No se pudo terminar la instalacion. Lo que hubiera instalado sigue igual.», con el motivo
   debajo. El más común es que el programa esté abierto: ciérrelo y vuelva a ejecutar el instalador.
4. En el menú de inicio quedan dos accesos: **ConverterSmartGrid** y **ConverterSmartGrid - diagnostico**.
5. Abra **ConverterSmartGrid**. Se abren dos cosas:
   - una ventana negra, que es el servidor del programa: **al cerrarla se cierra el programa**;
   - el navegador, en `http://127.0.0.1:8765`, primero con «Conectando con el conversor…» y luego con la página: arriba el título
     **ConverterSmartGrid** y, en la columna izquierda, la tarjeta **1 Entrada de datos**.

Si el programa ya estaba abierto, no se abre otro: se muestra el que había. Si en ese puerto hay un ConverterSmartGrid de otra
sesión, el nuevo se abre en el puerto libre siguiente y la ventana negra lo dice.

### Comprobar la instalación

Pulse la versión, que sale bajo el título de la web tras «DIgSILENT PowerFactory ·», o abra **ConverterSmartGrid - diagnostico**
en el menú de inicio. Lo mismo por órdenes:

```bat
"%LOCALAPPDATA%\Programs\ConverterSmartGrid\csg.cmd" doctor
```

La primera línea dice «ConverterSmartGrid <versión>: listo para trabajar.» o «… falta algo imprescindible.». Debajo, una línea
por comprobación:

- `[bien]`: está.
- `[aviso]`: falta algo opcional. El programa funciona sin ello, salvo lo que dice «Afecta a:»; «Cómo arreglarlo:» dice qué hacer.
- `[FALTA]`: falta algo imprescindible. Vuelva a ejecutar el instalador, que repone lo que falte sin tocar sus datos.

En un puesto sin perfil de empresa y sin complemento de IA es normal ver avisos en «Calibración del perfil» y en «Complemento de
IA». En la línea «DIgSILENT PowerFactory» debe ver «API en …» con la carpeta de su PowerFactory. La orden sale con código 0 si no
falta nada imprescindible.

### Elegir la versión de DIgSILENT

En la barra del título de la web hay una etiqueta con la PowerFactory en uso y su Python. Al pulsarla se abre «DIgSILENT
PowerFactory en esta máquina», con las instalaciones encontradas. **Usar esta** elige otra, y el equipo la recuerda; **Usar la
más nueva** vuelve a la elección automática. Solo se pueden elegir las que tienen un Python que pueda cargar su API. Si no
encuentra ninguna, lo dice, y convertir a DGS sigue funcionando.

Si su PowerFactory está en una carpeta que no se encuentra, defina la variable de usuario `PF_PYTHON` con la carpeta
`Python\3.x` de su PowerFactory que trae `powerfactory.pyd`. Con esa variable, la elección de la web no se usa, y la web lo dice.

## Dónde queda cada cosa

| Qué | Dónde | Al actualizar | Al desinstalar |
| --- | --- | --- | --- |
| Programa | `%LOCALAPPDATA%\Programs\ConverterSmartGrid` | Se añade la versión nueva; quedan la actual y la anterior | Se borra |
| Datos: espacios de trabajo, perfil, catálogos, registros | `%LOCALAPPDATA%\ConverterSmartGrid\datos` | Se conservan, con copia previa | **Se conservan** |

Para otra carpeta de datos, por ejemplo con más espacio, defina la variable de usuario `CSG_DATOS_HOME` antes de abrir el programa.

Para desinstalar, use «Aplicaciones instaladas» de Windows y elija **ConverterSmartGrid**. Sus datos se quedan.

## Perfil de empresa

El perfil reúne las convenciones de su empresa: sistema de coordenadas, bancos de condensadores por tensión, fichas de
transformadores, estructura de zonales y subestaciones, y modelos de informe. Sin perfil el programa no supone nada: pide el
sistema de coordenadas y no aparta ninguna subestación por su nombre.

**Desde la web.** En la columna izquierda, la tarjeta **Perfil de la empresa**:

1. En «Perfil (JSON)», elija el fichero de su perfil. Si el perfil nombra una estructura de la empresa, elíjala en «Estructura de
   la empresa (JSON, si el perfil la nombra)».
2. Pulse **Cargar perfil**. Mientras lo comprueba, el botón dice «Comprobando…».
3. Si el perfil tiene errores, sale «El perfil tiene errores y no se guardó», con cada error, y se queda el que había. Si está bien,
   la tarjeta dice «Perfil activo en …» con la carpeta donde quedó (guarda una copia del anterior), y «Faltan N dato(s) que conviene
   dar» lista lo que falta, qué función afecta y qué pasa sin ello.
4. En «Opciones de conversión», el «CRS de origen» enseña el del perfil *(pendiente de comprobar con el rc6: en el rc5 no se ponía
   al día hasta recargar la página)*.

**Para escribir el perfil**, parta de la plantilla vacía o del ejemplo de una empresa inventada que trae el programa, como explica
`PERFIL_EMPRESA.md`. Puede comprobar un fichero antes de cargarlo, y después el perfil activo:

```bat
csg.cmd validar-perfil --ruta C:\ruta\a\mi_perfil.json
csg.cmd validar-perfil
```

Las dos dicen qué falta y qué función afecta, y terminan con «Resultado: N error(es), …».

## Actualizar

1. Cierre el programa: cierre la ventana negra. Si sigue abierto, el instalador se niega con «El programa está abierto en el puerto
   8765: ciérrelo antes de actualizar».
2. Ejecute el instalador de la versión nueva. Antes de cambiar de versión copia sus datos a `copias_actualizacion\` dentro de la
   carpeta de datos, y solo pasa a la nueva si su diagnóstico responde. Si no, sigue la anterior.

Instalar otra vez la misma versión no cambia nada: dice que ya es la instalada.

## Volver a la versión anterior

Con el programa cerrado:

```bat
"%LOCALAPPDATA%\Programs\ConverterSmartGrid\volver_atras.cmd"
```

Vuelve a la versión anterior y a los datos de la copia que se hizo al actualizar. Lo que había se aparta, sin borrarlo; con
`--sin-restaurar` se quedan los datos de ahora. Si nunca se ha actualizado, dice «No hay una versión anterior a la que volver.».
Una versión anterior no abre un espacio que una más nueva ya haya pasado a su formato: lo dice, no lo pisa.

## Copias de los datos

La web avisa arriba cuando no hay copia o cuando la última tiene más días de los permitidos (siete, salvo que la variable
`CSG_COPIA_MAX_DIAS` diga otra cosa): «Aún no hay ninguna copia de sus datos.» o «La última copia de sus datos tiene N días…».

Sin trabajos en curso, y mejor con el programa cerrado:

```bat
"%LOCALAPPDATA%\Programs\ConverterSmartGrid\copia_datos.cmd" crear --destino E:\copias
```

Deja una carpeta `csg-copia-…` con un manifiesto y la huella de cada fichero. `copia_datos.cmd estado` dice cuándo fue la
última; `verificar` y `restaurar` están en su ayuda (`copia_datos.cmd --help`). Restaurar comprueba cada huella antes de tocar
nada y aparta lo que hubiera, sin borrarlo; con la web abierta se niega.

*(Pendiente de comprobar con el rc6.)* El aviso de la web trae **Hacer una copia ahora**: escriba la carpeta destino (otro disco
o una carpeta que sincroniza, como Google Drive), que el equipo recuerda. La copia corre como un trabajo, con su progreso y
«Cancelar» en la barra de trabajos; antes de empezar dice cuánto ocupará y cuánto hay libre, y si no cabe no empieza. Cada fichero
se guarda una vez aunque esté repetido. Mientras copia no se admite otro trabajo.

## Llevarlo a otro equipo o a otro usuario

El programa se instala **por usuario de Windows**: cada usuario tiene su instalación y sus datos, y no se comparten solos. DIgSILENT no
viene en el instalador: cada equipo usa el suyo, con su propia licencia.

### En el equipo o el usuario nuevo

1. Compruebe que tiene DIgSILENT PowerFactory 2021 o posterior, abierto al menos una vez con su licencia.
2. Copie `ConverterSmartGrid-<versión>-setup.exe` e instálelo como se dice en [Instalar](#instalar). No hace falta internet.
3. Abra **ConverterSmartGrid - diagnostico**. Tiene que decir «listo para trabajar» y, en «DIgSILENT PowerFactory», «API en …».
4. Si es otra empresa, cargue su perfil como se dice en [Perfil de empresa](#perfil-de-empresa).
5. Pruebe con un proyecto de prueba antes de trabajar: cargue la fuente, convierta un alimentador e impórtelo en DIgSILENT.

### Llevarse los datos, si hace falta

Una instalación nueva empieza sin espacios de trabajo, y es lo normal en otra empresa. Para conservar los de otro puesto:

1. En el puesto antiguo, con el programa cerrado: `copia_datos.cmd crear --destino E:\copias`.
2. Lleve la carpeta `csg-copia-…` al puesto nuevo.
3. En el puesto nuevo, con el programa cerrado: `copia_datos.cmd verificar --copia E:\copias\csg-copia-…` y, si está bien,
   `copia_datos.cmd restaurar --copia E:\copias\csg-copia-…`. Lo que hubiera se aparta, sin borrarlo.
4. Abra el programa. Lo que estaba fuera de la carpeta de datos, como una fuente en otra unidad, sale como **no disponible**:
   vuelva a indicarlo o descártelo.

**La copia no lleva los proyectos de DIgSILENT**, que viven en la base de datos de DIgSILENT. Expórtelos e impórtelos con DIgSILENT, o vuelva a
importar desde la web. Los datos de una distribuidora son suyos: no los copie a otro equipo sin su permiso, ni los suba a internet.

## Si algo falla

| Qué ve | Qué hacer |
| --- | --- |
| El instalador dice «No se pudo terminar la instalacion» | Lea el motivo del aviso; si es el programa abierto, ciérrelo y repita |
| El instalador rechaza la carpeta | Use una ruta más corta: Windows no carga librerías por encima de 259 caracteres |
| Windows avisa de un editor desconocido | El instalador no va firmado; compruebe que vino de quien se lo dio |
| La ventana negra dice «No se pudo abrir el programa» | Ejecute `csg.cmd doctor` y siga lo que diga |
| El diagnóstico no encuentra DIgSILENT | Instale PowerFactory 2021 o posterior, o defina `PF_PYTHON` con la carpeta de su API |
| «Esta pestaña no tiene sesión con el Conversor» | Abra el acceso directo: cada arranque usa una sesión nueva, y los enlaces guardados dejan de valer |
| La web dejó de responder | Mire si la ventana negra sigue abierta; si se cerró, abra otra vez el acceso directo |
| Un espacio marcado como dañado | La web ofrece restaurar su copia anterior |
| Un fichero marcado como no disponible | Vuelva a conectar la unidad; la ruta se conserva |
| Un fallo que no entiende | Prepare el paquete de soporte, como se dice abajo |

Para el soporte:

1. `csg.cmd doctor` dice qué falta.
2. `csg.cmd soporte` deja en la carpeta de datos un `.zip` para enviarlo al soporte. Lleva el diagnóstico, las versiones y los registros
   anonimizados, sin redes, cargas ni informes; dice lo que lleva en `LEAME.txt`. Mírelo antes de enviarlo.

Los registros están en `runtime\registros\` de la carpeta de datos: cinco ficheros de 5 MB como máximo.

---

## Para quien prepara una versión

Un operador no necesita esta parte.

### Construir el instalador

Hace falta el repositorio, con Python 3.12, Node e [Inno Setup 6](https://jrsoftware.org/isinfo.php); el
`python-3.12.x-embed-amd64.zip` de python.org; y, para las PowerFactory 2021 a 2023, la carpeta con los Python embebidos y las
ruedas de numpy que fija `config/entrega.json`.

```bat
cd frontend && npm ci && npm run build && cd ..
python tools\construir_candidato.py candidato --salida C:\csg\candidato --python-embebido python-3.12.10-embed-amd64.zip --python-pf C:\csg\python_pf
python tools\comprobar_entrega.py --candidato C:\csg\candidato
ISCC.exe /DCandidato=C:\csg\candidato /OC:\csg\salida instalador\ConverterSmartGrid.iss
```

Use rutas cortas: la de construir se suma a la de cada fichero. El candidato rechaza lo que lleve el nombre de una empresa o un
peso entrenado. La versión sale de un solo sitio, la del paquete (`__version__`): el candidato la toma de ahí y el instalador la
lee de la rueda del candidato, así que no se pasa a mano. Desde el rc6, `ISCC` rechaza `/DVersion`, y `--version` del candidato
solo sirve para ensayar una actualización (pendiente de comprobar con el rc6).

### Complemento de IA (opcional)

El núcleo no trae `torch`: pesa gigas y nada de lo que se vende en la 1.0 lo necesita. Su lista está en
`requirements-complemento-ia.txt`. Solo hace falta para los modelos locales del asistente de órdenes, que está en beta; se instala con
salida a internet, o desde un paquete offline con su `instalacion.lock` y la carpeta `wheels`.
La versión 1.0 no entrega pesos entrenados.

Para preparar ese paquete con CPython 3.12 de 64 bits en Windows, descargue previamente las ruedas
de la lista y sus dependencias a una caché separada y ejecute:

```powershell
python tools/construir_candidato.py complemento-ia --salida D:/entregas/ia --ruedas-cache D:/cache-ia
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
