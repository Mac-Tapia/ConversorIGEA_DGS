"""Cada salida a la red, declarada y con su interruptor (086:RF-22).

La revisión de la spec 086 encontró que el programa salía a internet desde sitios sueltos
(búsquedas del asistente, OSRM, las teselas del mapa, Codex, Hugging Face, el portal de
Osinergmin) sin un lugar donde verlos ni apagarlos. Un cliente que instala esto en la red de
una distribuidora tiene que saber qué sale, y que por defecto no sale nada.

En desarrollo siguen encendidas, como hasta ahora. En la edición de producto están apagadas y
cada una se enciende con su variable. La variable manda en las dos ediciones; sin ella, lo que el
operador guardó en este equipo desde la web (086:RF-66, hoy solo el fondo de mapa), y si no, la edición.
``tests/test_seguridad_web.py`` recorre el código: un módulo nuevo que abra la red sin estar
aquí la hace fallar.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, MutableMapping

from .edicion import es_edicion_producto

_ENCENDIDA = ('1', 'si', 'sí', 'true', 'on')
_APAGADA = ('0', 'no', 'false', 'off')


@dataclass(frozen=True)
class Salida:
    variable: str
    destino: str
    para_que: str
    #: Ficheros, relativos a la raíz del repositorio, que abren esta salida.
    modulos: tuple[str, ...]


SALIDAS: dict[str, Salida] = {
    'internet': Salida('CSG_SALIDA_INTERNET', 'GitHub, PyPI y arXiv',
                       'las búsquedas técnicas del asistente',
                       ('src/convertersmartgrid/asistente/internet.py',)),
    'vias': Salida('CSG_SALIDA_VIAS', 'el enrutador OSRM del perfil de empresa',
                   'trazar una línea nueva por la vía pública',
                   ('src/convertersmartgrid/vias.py',)),
    # 017:RF-111: también la imagen de ubicación del informe, que pide las teselas desde el servidor.
    'teselas': Salida('CSG_SALIDA_TESELAS', 'OpenStreetMap y Esri World Imagery',
                      'el fondo de calles y satélite de la vista previa y del mapa de las cargas nuevas, que pide el '
                      'navegador, y de la imagen de ubicación del informe',
                      ('src/convertersmartgrid/preview.py', 'src/convertersmartgrid/mapa_cargas.py')),
    'codex': Salida('CSG_SALIDA_CODEX', 'el servicio de Codex, por su CLI',
                    'el maestro de destilación del asistente',
                    ('src/convertersmartgrid/asistente/destilacion.py',)),
    'hugging_face': Salida('CSG_SALIDA_HUGGING_FACE', 'Hugging Face',
                           'descargar los modelos del catálogo',
                           ('tools/preparar_modelos_ia.py',)),
    'vnr_oficial': Salida('CSG_SALIDA_VNR_OFICIAL', 'el portal de Osinergmin',
                          'buscar y descargar los paquetes VNR-GIS',
                          ('src/convertersmartgrid/adaptadores/entrada/vnr/discovery/official.py', 'src/convertersmartgrid/adaptadores/entrada/vnr/discovery/download.py')),
    'arcgis': Salida('CSG_SALIDA_ARCGIS', 'el servidor ArcGIS que indique el usuario',
                     'leer una capa de un servicio ArcGIS',
                     ('src/convertersmartgrid/adaptadores/entrada/vnr/connectors/arcgis.py',)),
}


class SalidaApagada(RuntimeError):
    """Se pidió una salida a la red que está apagada."""


#: 086:RF-69: las que el operador puede cambiar desde la web. El resto, solo con su variable al arrancar.
CAMBIABLES_DESDE_LA_WEB = frozenset({'teselas'})
#: Otra ruta para lo guardado en el equipo; la usan las pruebas, para no leer el de la máquina.
VARIABLE_RUTA_GUARDADAS = 'CSG_SALIDAS_RUTA'

Origen = Literal['variable', 'equipo', 'edicion']


def ruta_guardadas(environ: Mapping[str, str] | None = None) -> Path:
    """086:RF-67: junto a ``config/powerfactory.json`` (103:RF-3), en la carpeta local que una actualización no borra."""
    env = os.environ if environ is None else environ
    otra = str(env.get(VARIABLE_RUTA_GUARDADAS) or '').strip()
    if otra:
        return Path(otra)
    from .runtime_paths import raiz_local
    return raiz_local(environ=env) / 'config' / 'salidas.json'


def salidas_guardadas(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Lo que el operador dejó en este equipo; un fichero roto o ajeno cuenta como nada guardado."""
    try:
        datos = json.loads(ruta_guardadas(environ).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {k: v for k, v in datos.items() if k in CAMBIABLES_DESDE_LA_WEB and isinstance(v, bool)}


def guardar_salida(nombre: str, encendida: bool, environ: Mapping[str, str] | None = None) -> None:
    """086:RF-67: recuerda en el equipo la elección del operador; solo las que se cambian desde la web."""
    if nombre not in CAMBIABLES_DESDE_LA_WEB:
        raise ValueError(f'La salida {nombre!r} no se cambia desde la web.')
    ruta = ruta_guardadas(environ)
    datos = salidas_guardadas(environ)
    datos[nombre] = bool(encendida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + '.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temporal, ruta)


def estado_salida(nombre: str, environ: Mapping[str, str] | None = None) -> tuple[bool, Origen]:
    """086:RF-66: si está encendida y quién lo decide: la variable, lo guardado en el equipo o la edición."""
    env = os.environ if environ is None else environ
    valor = env.get(SALIDAS[nombre].variable, '').strip().lower()
    if valor in _ENCENDIDA:
        return True, 'variable'
    if valor in _APAGADA:
        return False, 'variable'
    guardada = salidas_guardadas(env).get(nombre)
    if guardada is not None:
        return guardada, 'equipo'
    return not es_edicion_producto(), 'edicion'


def salida_permitida(nombre: str, environ: Mapping[str, str] | None = None) -> bool:
    """Si esta salida puede abrirse: su variable manda; sin ella, lo guardado en el equipo; si no, la edición."""
    return estado_salida(nombre, environ)[0]


def estado_salidas(environ: Mapping[str, str] | None = None) -> list[dict[str, object]]:
    """086:RF-69: cada salida con su estado, su origen y su destino, para la web."""
    filas = []
    for nombre, s in SALIDAS.items():
        encendida, origen = estado_salida(nombre, environ)
        filas.append({'nombre': nombre, 'encendida': encendida, 'origen': origen, 'variable': s.variable,
                      'destino': s.destino, 'para_que': s.para_que,
                      'cambiable': nombre in CAMBIABLES_DESDE_LA_WEB and origen != 'variable'})
    return filas


#: «a el» y «de el» con el artículo en minúscula; «de El Carmen», nombre propio, no se contrae (RAE).
_SIN_CONTRAER = re.compile(r'\b([Aa]|[Dd]e) el\b')


def contraer(texto: str) -> str:
    """«a el» pasa a «al» y «de el» a «del» (086:RF-61).

    Los destinos se escriben con su artículo («el portal de Osinergmin») y se unen a «a» o «de» al armar el texto: la web
    del rc5 decía «La salida a el portal de Osinergmin está apagada».
    """
    return _SIN_CONTRAER.sub(lambda m: m.group(1)[0] + ('l' if m.group(1) in 'Aa' else 'el'), texto)


def motivo_apagada(nombre: str) -> str:
    """Por qué no sale, y cómo se enciende: lo lee el operador, en el aviso o en el registro."""
    s = SALIDAS[nombre]
    # 086:RF-67: la que se cambia desde la web dice también dónde, sin tener que rearrancar.
    web = ' o enciéndala en la web, en «Opciones de conversión»' if nombre in CAMBIABLES_DESDE_LA_WEB else ''
    return contraer(f'La salida a {s.destino} está apagada ({s.para_que}). '
                    f'Para activarla, ponga {s.variable}=1 al arrancar{web}.')


def exigir_salida(nombre: str) -> None:
    """Corta aquí si la salida está apagada, antes de abrir ninguna conexión."""
    if not salida_permitida(nombre):
        raise SalidaApagada(motivo_apagada(nombre))


def preparar_entorno_sin_red(environ: MutableMapping[str, str] | None = None) -> None:
    """Sin salida a Hugging Face, sus librerías lo saben desde que arranca el proceso.

    ``huggingface_hub`` lee ``HF_HUB_OFFLINE`` al importarse: el que pone ``reranker.py`` al cargar
    el modelo llega tarde si otro lo importó antes, y deja el resto del proceso como le toque.
    Con esto se decide una vez, antes de importar nada, y lo heredan los procesos hijos.
    """
    env = os.environ if environ is None else environ
    if not salida_permitida('hugging_face', env):
        # 086:RF-22: una variable heredada con valor 0 no reabre la salida apagada.
        env['HF_HUB_OFFLINE'] = '1'
        env['TRANSFORMERS_OFFLINE'] = '1'
