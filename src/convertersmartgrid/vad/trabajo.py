"""El armado de la empresa modelo como trabajo en cola, sistema por sistema (108:RF-1, RF-5, RF-7; P6 y P7).

``armar_empresa_modelo(ctx, …)`` es la función que el gestor de trabajos encola en el carril ``engine``: el armado es
largo y no cabe en una petición (P7). Recibe el ``JobContext`` del trabajo, o cualquier objeto con ``check_cancel``,
``progress`` y ``log`` (el guion ``tools/vad_estudio.py`` da uno de consola); por eso este módulo no importa la web.

- **Cancelable entre sistemas.** Antes de cada sistema llama a ``ctx.check_cancel()``. Si se cancela, los sistemas que
  no llegaron a armarse quedan «CANCELADO» en el manifiesto y la cancelación sigue su curso.
- **Independiente por sistema (P6).** Cada sistema pasa por los pasos que se le den (``pasos``: nombre → función
  ``(sistema, entrada) → resultado``), en orden. Un paso que falla deja ese sistema «FAIL» con el paso y el error, y
  los demás sistemas siguen. Un paso cuya entrada no trae el caso no se inventa: queda «sin entrada» con su nombre.
- **Manifiesto siempre.** ``<espacio>/vad/<id>/manifiesto.json`` se escribe tras cada sistema, al terminar y también
  al cancelar o al fallar el trabajo, con la escritura atómica única (001:RF-5). Lleva la empresa, el grupo, el
  periodo, la versión del TdR y el estado del estudio, que nunca es «aprobado» (fuera de alcance).

Qué pasos hay lo decide quien llama: :func:`pasos_del_caso` da el del anexo 2 (``validar_tablas``), el único cuya
entrada se lee hoy de ficheros del caso; los demás pasos del plan (caracterización, modelo rural, dimensionamiento,
costos, COyM y balance) se pasan con su entrada cuando el caso la trae.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from ..util import write_json_atomic
from . import VadError
from .anexo2 import Formatos, validar_tablas
from .estudio import cargar_estudio, carpeta_estudio

MANIFIESTO = 'manifiesto.json'
ESTADOS = ('OK', 'FAIL', 'CANCELADO')
Paso = Callable[[str, Any], Mapping[str, Any]]


class Contexto(Protocol):
    def check_cancel(self) -> None: ...
    def progress(self, index: int, total: int, label: str = '') -> None: ...
    def log(self, text: str) -> None: ...


def _es_cancelacion(exc: BaseException) -> bool:
    """La cancelación del carril (``web.jobs.JobCancelled``) o la del guion, sin importar la web (su capa)."""
    return type(exc).__name__ in ('JobCancelled', 'Cancelado') or isinstance(exc, KeyboardInterrupt)


def _serializable(valor: Any) -> Any:
    return json.loads(json.dumps(valor, ensure_ascii=False, default=str))


def armar_empresa_modelo(ctx: Contexto, espacio: Path | str, id_estudio: str, entradas: Mapping[str, Mapping[str, Any]],
                         pasos: Sequence[tuple[str, Paso]]) -> dict[str, Any]:
    """Arma cada sistema de ``entradas`` (sistema → {paso: entrada}) con ``pasos``, en el orden de los sistemas, y
    devuelve el manifiesto que deja escrito. Sin sistemas o sin pasos no hay nada que armar: es un error."""
    estudio = cargar_estudio(espacio, id_estudio)
    if not entradas:
        raise VadError(f'el estudio {id_estudio} no trae ningún sistema que armar')
    if not pasos:
        raise VadError('el armado necesita al menos un paso')
    nombres = [n for n, _ in pasos]
    if len(set(nombres)) != len(nombres):
        raise VadError(f'pasos repetidos en el armado: {nombres}')
    sistemas = list(entradas)
    ruta = carpeta_estudio(espacio, id_estudio) / MANIFIESTO
    manifiesto: dict[str, Any] = {
        'estudio': estudio.id, 'empresa': estudio.empresa, 'grupo': estudio.grupo, 'periodo': estudio.periodo,
        'version_tdr': estudio.version_tdr, 'estado_estudio': estudio.estado, 'pasos': nombres,
        'sistemas': {s: {'estado': 'CANCELADO', 'motivo': 'no llegó a armarse'} for s in sistemas},
        'terminado': False, 'cancelado': False,
    }

    def escribir() -> None:
        write_json_atomic(ruta, manifiesto)

    escribir()
    try:
        for i, sistema in enumerate(sistemas):
            ctx.check_cancel()
            ctx.progress(i, len(sistemas), sistema)
            entrada = entradas[sistema] or {}
            res: dict[str, Any] = {'estado': 'OK', 'pasos': {}, 'sin_entrada': []}
            for nombre, paso in pasos:
                if nombre not in entrada:
                    res['sin_entrada'].append(nombre)
                    continue
                try:
                    res['pasos'][nombre] = _serializable(paso(sistema, entrada[nombre]))
                except MemoryError:
                    raise  # sin memoria no se arma ningún sistema más: es del trabajo, no del sistema
                except Exception as exc:  # P6: un sistema que falla no tumba a los demás
                    if _es_cancelacion(exc):
                        raise
                    res.update(estado='FAIL', paso=nombre, error=f'{type(exc).__name__}: {exc}')
                    ctx.log(f'{sistema}: falla el paso {nombre}: {exc}')
                    break
            manifiesto['sistemas'][sistema] = res
            escribir()
        ctx.progress(len(sistemas), len(sistemas), 'terminado')
        manifiesto['terminado'] = True
    except BaseException as exc:
        manifiesto['cancelado'] = _es_cancelacion(exc)
        if not manifiesto['cancelado']:
            manifiesto['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        escribir()
    return manifiesto


def pasos_del_caso(formatos: Formatos, periodo: str | None = None) -> list[tuple[str, Paso]]:
    """Los pasos cuya entrada se lee de ficheros del caso. Hoy, «anexo2»: la ruta de un JSON con las tablas del
    sistema (la forma de :func:`.anexo2.validar_tablas`), que se validan contra los formatos transcritos sin rellenar
    nada; el resultado son sus huecos y sus avisos, cada uno con su tabla y su campo."""
    def anexo2(sistema: str, ruta: Any) -> dict[str, Any]:
        tablas = json.loads(Path(ruta).read_text(encoding='utf-8'))
        r = validar_tablas(tablas, formatos, periodo=periodo)
        return {'tablas': sorted(r.tablas), 'completo': r.completo, 'huecos': [h.linea() for h in r.huecos],
                'avisos': [a.linea() for a in r.avisos]}
    return [('anexo2', anexo2)]


def leer_caso(carpeta: Path | str) -> dict[str, dict[str, Any]]:
    """Las entradas de un caso: ``<carpeta>/sistemas.json`` con ``{"sistemas": {sistema: {paso: ruta}}}``; cada ruta,
    relativa a la carpeta del caso. El caso vive fuera de git (P9) y su forma no es la de ninguna empresa."""
    carpeta = Path(carpeta)
    fichero = carpeta / 'sistemas.json'
    if not fichero.is_file():
        raise VadError(f'el caso no trae sistemas.json: {fichero}')
    datos = json.loads(fichero.read_text(encoding='utf-8'))
    sistemas = datos.get('sistemas') if isinstance(datos, Mapping) else None
    if not isinstance(sistemas, Mapping) or not sistemas:
        raise VadError(f'{fichero}: «sistemas» tiene que ser un objeto sistema → {{paso: ruta}} no vacío')
    return {str(s): {str(p): str((carpeta / r).resolve()) for p, r in (pasos or {}).items()}
            for s, pasos in sistemas.items()}
