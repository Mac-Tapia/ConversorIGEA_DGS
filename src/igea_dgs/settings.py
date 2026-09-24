"""Recuerda entre sesiones lo último que se eligió en la interfaz.

Qué problema resuelve. Cada entrega de la distribuidora trae ficheros nuevos, en otra
carpeta y con otro nombre. Si la ventana vuelve siempre a los TXT de ejemplo de
``referencia/``, hay que volver a buscar los tres a mano cada vez que se abre, y es
fácil convertir sin darse cuenta con la entrega del mes pasado.

Por qué esto existió antes y se quitó. Había un ``gui_state.json`` que se eliminó
deliberadamente «para no arrastrar sesiones». El modo de fallo de guardar rutas es
conocido: se guarda una que luego se borra o se mueve, la ventana arranca con un campo
que apunta a la nada, y el error no aparece hasta que alguien pulsa convertir. Aquí se
ataca de frente:

* **Una ruta solo se restaura si sigue existiendo.** Si el fichero ya no está, el campo
  queda vacío y se recurre al relleno automático, como si nunca se hubiera guardado.
* **Se guarda en cada cambio**, así que lo último elegido es siempre lo que manda. Es
  justo lo que hacía falta: que la entrega nueva sustituya a la vieja sin que nadie
  tenga que acordarse de nada.
* **No se guarda lo que cambia el significado de un botón.** «Convertir TODOS» se queda
  fuera a propósito: restaurarlo en silencio convertiría 101 alimentadores a quien creía
  estar convirtiendo uno.

El fichero vive en el perfil del usuario, no en el repositorio: es preferencia de quien
usa el programa, no del proyecto, y así no ensucia el árbol de trabajo ni viaja en un
commit.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: Campos que son rutas. Se restauran **solo si siguen existiendo**.
CAMPOS_RUTA = (
    'red', 'loads', 'equipment',      # alternativa 1: los tres TXT
    'mdb', 'equipment_mdb', 'study',  # alternativa 2: base Access y estudio
    'aliases',
)

#: Carpeta de salida. Se restaura aunque no exista: se crea al convertir.
CAMPOS_CARPETA = ('out_dir',)

#: Texto suelto: modo de entrada y sistemas de coordenadas.
CAMPOS_TEXTO = ('input_mode', 'source_crs', 'target_crs')

#: Casillas de verificación que son preferencia y no cambian qué hace un botón.
CAMPOS_BOOL = (
    'include_geography', 'strict', 'export_xlsx', 'export_tsv', 'write_preview',
)

#: Deliberadamente fuera: ``convert_all`` cambia a cuántos alimentadores afecta el
#: botón de conversión. Restaurarlo en silencio sería una sorpresa cara.
NO_SE_GUARDAN = ('convert_all',)

VERSION = 1


def ruta_ajustes() -> Path:
    """Dónde se guarda. En el perfil del usuario, no en el repositorio."""
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if base:
        return Path(base) / 'igea-dgs' / 'interfaz.json'
    return Path.home() / '.igea-dgs' / 'interfaz.json'


def guardar(valores: dict, *, path: Path | None = None) -> Path | None:
    """Guarda lo que se pueda. Nunca interrumpe el trabajo si falla.

    Un disco lleno o un perfil sin permisos no son motivo para que la interfaz deje de
    funcionar: lo peor que puede pasar es que la próxima vez haya que elegir los
    ficheros a mano.
    """
    destino = path or ruta_ajustes()
    datos = {'version': VERSION}
    for campo in CAMPOS_RUTA + CAMPOS_CARPETA + CAMPOS_TEXTO:
        valor = str(valores.get(campo, '') or '').strip()
        if valor:
            datos[campo] = valor
    for campo in CAMPOS_BOOL:
        if campo in valores:
            datos[campo] = bool(valores[campo])
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(datos, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        return destino
    except OSError:
        return None


def cargar(*, path: Path | None = None) -> dict:
    """Lo guardado que sigue siendo válido hoy.

    Las rutas que ya no existen **no se devuelven**: arrancar con un campo que apunta a
    un fichero borrado es peor que arrancar con el campo vacío, porque el problema no
    se ve hasta que alguien pulsa convertir.
    """
    origen = path or ruta_ajustes()
    try:
        datos = json.loads(origen.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(datos, dict):
        return {}

    validos: dict = {}
    for campo in CAMPOS_RUTA:
        valor = str(datos.get(campo, '') or '').strip()
        if valor and Path(valor).is_file():
            validos[campo] = valor
    for campo in CAMPOS_CARPETA:
        valor = str(datos.get(campo, '') or '').strip()
        if valor:
            validos[campo] = valor
    for campo in CAMPOS_TEXTO:
        valor = str(datos.get(campo, '') or '').strip()
        if valor:
            validos[campo] = valor
    for campo in CAMPOS_BOOL:
        if isinstance(datos.get(campo), bool):
            validos[campo] = datos[campo]
    return validos


def olvidadas(valores_guardados: dict) -> list[str]:
    """Rutas que estaban guardadas y ya no existen, para poder decirlo.

    Que un fichero desaparezca es normal —se mueve la carpeta de la entrega—, pero el
    operador debería enterarse por un mensaje y no porque el campo aparezca vacío sin
    explicación.
    """
    perdidas = []
    for campo in CAMPOS_RUTA:
        valor = str(valores_guardados.get(campo, '') or '').strip()
        if valor and not Path(valor).is_file():
            perdidas.append(valor)
    return perdidas


def leer_crudo(*, path: Path | None = None) -> dict:
    """Lo guardado tal cual, sin filtrar. Para saber qué se perdió."""
    origen = path or ruta_ajustes()
    try:
        datos = json.loads(origen.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}
