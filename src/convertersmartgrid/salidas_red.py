"""Cada salida a la red, declarada y con su interruptor (086:RF-22).

La revisión de la spec 086 encontró que el programa salía a internet desde sitios sueltos
(búsquedas del asistente, OSRM, las teselas del mapa, Codex, Hugging Face, el portal de
Osinergmin) sin un lugar donde verlos ni apagarlos. Un cliente que instala esto en la red de
una distribuidora tiene que saber qué sale, y que por defecto no sale nada.

En desarrollo siguen encendidas, como hasta ahora. En la edición de producto están apagadas y
cada una se enciende con su variable. La variable manda en las dos ediciones.
``tests/test_seguridad_web.py`` recorre el código: un módulo nuevo que abra la red sin estar
aquí la hace fallar.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping, MutableMapping

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
    'teselas': Salida('CSG_SALIDA_TESELAS', 'OpenStreetMap',
                      'el fondo del mapa de la vista previa, que pide el navegador',
                      ('src/convertersmartgrid/preview.py',)),
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


def salida_permitida(nombre: str, environ: Mapping[str, str] | None = None) -> bool:
    """Si esta salida puede abrirse: su variable manda; sin ella, según la edición."""
    env = os.environ if environ is None else environ
    valor = env.get(SALIDAS[nombre].variable, '').strip().lower()
    if valor in _ENCENDIDA:
        return True
    if valor in _APAGADA:
        return False
    return not es_edicion_producto()


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
    return contraer(f'La salida a {s.destino} está apagada ({s.para_que}). '
                    f'Para activarla, ponga {s.variable}=1 al arrancar.')


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
