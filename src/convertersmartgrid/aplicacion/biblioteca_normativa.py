"""La biblioteca normativa general: una sola, actualizable, para cualquier empresa, estudio y módulo (orden del usuario,
17-11-2026: «esa base de datos debe ser actualizable, como biblioteca general para cualquier empresa y cualquier
estudio y cualquier módulo»).

- La base viaja con el programa: ``config/normativa`` (normas nacionales e internacionales con sus reglas citadas) y
  ``config/vad`` (las reglas del VAD).
- La capa del usuario vive fuera del paquete (``ruta_capa_usuario``): ficheros del mismo esquema que añaden una norma o
  sustituyen la versión de una que viene con el programa (por ejemplo, una modificatoria publicada después de la
  entrega). Lo sustituido queda anotado en ``sustituidas``; nada se borra.
- ``cargar_biblioteca(fecha)`` da el registro de todo; cada estudio toma la regla vigente en su fecha con el mismo
  registro (``RegistroNormativo.reglas_vigentes`` y ``obligatoria_en``).
- ``huella_biblioteca()`` cambia cuando cambia cualquier fichero de las dos capas: el índice del asistente y los
  datasets saben así cuándo regenerarse.
- ``agregar_norma(fichero)`` valida un fichero del esquema y lo copia a la capa del usuario; ``exportar_dataset(destino)``
  escribe ``normas.jsonl`` y ``reglas.jsonl`` (una línea por norma y por regla, con su cita) solo si la huella cambió.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ..dominio.registro_normativo import (ESQUEMA, Norma, Regla, RegistroError, RegistroNormativo, cargar_registro, leer_norma,
                                 leer_regla)
from ..dominio.util import publicar_duradero
from ..dominio.util import sha256_file

#: Variable que cambia la carpeta de la capa del usuario.
VARIABLE_CAPA = 'CSG_NORMATIVA_USUARIO'


def _raiz_paquete() -> Path:
    return Path(__file__).resolve().parents[3]


def rutas_base(raiz: Path | None = None) -> list[Path]:
    """Las carpetas de la biblioteca que viajan con el programa."""
    raiz = raiz or _raiz_paquete()
    return [p for p in (raiz / 'config' / 'normativa', raiz / 'config' / 'vad') if p.is_dir()]


def ruta_capa_usuario() -> Path:
    """La carpeta de las normas que añade o actualiza el usuario, fuera del paquete."""
    propia = os.environ.get(VARIABLE_CAPA, '').strip()
    if propia:
        return Path(propia)
    from ..dominio.runtime_paths import raiz_local  # la de cada instalación: sobrevive a las actualizaciones del programa
    return raiz_local() / 'normativa_usuario'


def _ficheros(carpetas: list[Path]) -> list[Path]:
    return sorted((f for c in carpetas if c.is_dir() for f in c.glob('*.json')), key=lambda p: p.as_posix())


def cargar_biblioteca(fecha: str | None = None, *, raiz: Path | None = None,
                      capa_usuario: Path | None = None) -> RegistroNormativo:
    """La base del programa más la capa del usuario. Una norma de la capa del usuario con el mismo acto sustituye a la
    de la base (su versión más reciente); las sustituidas quedan en ``registro.sustituidas``. ``fecha`` no filtra:
    se da para que el que llama declare la de su estudio; la vigencia la aplica cada consulta del registro."""
    del fecha
    registro = cargar_registro(*rutas_base(raiz))
    sustituidas: dict[str, str] = {}
    capa = capa_usuario if capa_usuario is not None else ruta_capa_usuario()
    for f in _ficheros([capa]) if capa and Path(capa).is_dir() else []:
        try:
            datos = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistroError(f'{f}: no se puede leer ({exc})') from exc
        if not isinstance(datos, dict) or datos.get('esquema') != ESQUEMA:
            continue
        for n in datos.get('normas') or ():
            norma = leer_norma(n, str(f))
            if norma.acto in registro.normas:
                sustituidas[norma.acto] = f.name
            registro.normas[norma.acto] = norma
        if datos.get('amplia'):
            base = registro.norma(datos['amplia'])
            nuevas = tuple(leer_regla(r, f'{f}:{base.acto}') for r in datos.get('reglas') or ())
            registro.normas[base.acto] = Norma(**{**{k: getattr(base, k) for k in Norma.__dataclass_fields__},
                                                  'reglas': base.reglas + nuevas})
    registro.sustituidas = sustituidas  # type: ignore[attr-defined]
    return registro


def huella_biblioteca(*, raiz: Path | None = None, capa_usuario: Path | None = None) -> str:
    """sha256 del conjunto: cada fichero de las dos capas por su ruta relativa y su contenido, en orden."""
    h = hashlib.sha256()
    capa = capa_usuario if capa_usuario is not None else ruta_capa_usuario()
    for etiqueta, carpetas in (('base', rutas_base(raiz)), ('usuario', [Path(capa)] if capa else [])):
        for f in _ficheros(carpetas):
            h.update(f'{etiqueta}/{f.parent.name}/{f.name}\n'.encode('utf-8'))
            h.update(f.read_bytes())
    return h.hexdigest()


def agregar_norma(fichero: Path | str, *, capa_usuario: Path | None = None) -> list[str]:
    """Valida ``fichero`` (esquema del registro, cada norma y cada regla como las de la base) y lo copia a la capa del
    usuario. Devuelve los actos que añade o sustituye. Un fichero que no valida no se copia."""
    origen = Path(fichero)
    try:
        datos = json.loads(origen.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistroError(f'{origen}: no se puede leer ({exc})') from exc
    if not isinstance(datos, dict) or datos.get('esquema') != ESQUEMA:
        raise RegistroError(f'{origen}: no es del esquema {ESQUEMA}')
    actos = [leer_norma(n, str(origen)).acto for n in datos.get('normas') or ()]
    for r in datos.get('reglas') or ():
        leer_regla(r, str(origen))
    if not actos and not datos.get('amplia'):
        raise RegistroError(f'{origen}: no trae ninguna norma ni amplía ninguna')
    capa = Path(capa_usuario if capa_usuario is not None else ruta_capa_usuario())
    capa.mkdir(parents=True, exist_ok=True)
    copia = capa / origen.name
    anterior = copia.read_bytes() if copia.is_file() else None
    copia.write_bytes(origen.read_bytes())
    try:
        cargar_biblioteca(capa_usuario=capa)  # el conjunto sigue cargando: si no, el error sale aquí y no en un estudio
    except RegistroError:
        if anterior is None:
            copia.unlink()
        else:
            copia.write_bytes(anterior)
        raise
    return actos or [str(datos['amplia'])]


# Auditoría D.2 (2026-11-24): la huella de un fichero es una sola, la de dominio/util; este nombre queda por quien lo llama.
_sha256 = sha256_file


def comprobar_fuentes(carpeta: Path | str | None, fecha: str, *, raiz: Path | None = None,
                      capa_usuario: Path | None = None) -> dict:
    """026:RF-46, 107:RF-22: la huella de la fuente oficial de cada norma contra la registrada, y su vigencia en
    ``fecha``. Solo lee: cada norma con ``fichero_local`` dice «cuadra», «alterada» (y entonces no se regenera desde
    ella), «falta» (dónde ponerla) o «sin_carpeta»; las que no traen fichero, «sin_fuente_local». Nada se descarga."""
    registro = cargar_biblioteca(fecha, raiz=raiz, capa_usuario=capa_usuario)
    base = Path(carpeta) if carpeta else None
    filas = []
    for acto in sorted(registro.normas):
        n = registro.normas[acto]
        fila = {'acto': acto, 'fichero': n.fichero_local, 'estado_juridico': n.estado_juridico,
                'obliga': n.obligatoria_en(fecha), 'vigencia_desde': n.vigencia_desde,
                'vigencia_hasta': n.vigencia_hasta, 'motivo': ''}
        if not n.fichero_local or not n.sha256:
            fila['fuente'] = 'sin_fuente_local'
        elif base is None or not base.is_dir():
            fila['fuente'], fila['motivo'] = 'sin_carpeta', 'falta la carpeta de fuentes normativas'
        else:
            ruta = base / n.fichero_local
            if not ruta.is_file():
                fila['fuente'], fila['motivo'] = 'falta', f'ponga la fuente oficial en {n.fichero_local}'
            elif _sha256(ruta) != n.sha256.lower():
                fila['fuente'], fila['motivo'] = 'alterada', ('su sha256 no es el registrado: recupere el original '
                                                              '(del comprimido oficial); no se regenera desde ella')
            else:
                fila['fuente'] = 'cuadra'
        filas.append(fila)
    cuenta: dict[str, int] = {}
    for f in filas:
        cuenta[f['fuente']] = cuenta.get(f['fuente'], 0) + 1
    return {'fecha': fecha, 'carpeta': bool(base and base.is_dir()), 'cuenta': cuenta, 'normas': filas}


def _campos_regla(r: Regla) -> str:
    return json.dumps({'valor': r.valor, 'unidad': r.unidad, 'articulo_o_anexo': r.articulo_o_anexo,
                       'pagina': r.pagina, 'cita_literal': r.cita_literal}, sort_keys=True, default=str)


def comparar_con_vigente(fichero: Path | str, *, raiz: Path | None = None,
                         capa_usuario: Path | None = None) -> list[dict]:
    """107:RF-22: qué reglas de un registro regenerado entran, salen o cambian frente a la biblioteca vigente, por
    norma, y si cambia su vigencia o su estado. El fichero se valida como en ``agregar_norma``; no se escribe nada."""
    origen = Path(fichero)
    try:
        datos = json.loads(origen.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistroError(f'{origen}: no se puede leer ({exc})') from exc
    if not isinstance(datos, dict) or datos.get('esquema') != ESQUEMA:
        raise RegistroError(f'{origen}: no es del esquema {ESQUEMA}')
    vigente = cargar_biblioteca(raiz=raiz, capa_usuario=capa_usuario)
    nuevas = [leer_norma(n, str(origen)) for n in datos.get('normas') or ()]
    if datos.get('amplia'):
        base = vigente.norma(datos['amplia'])
        extra = tuple(leer_regla(r, f'{origen}:{base.acto}') for r in datos.get('reglas') or ())
        nuevas.append(Norma(**{**{k: getattr(base, k) for k in Norma.__dataclass_fields__},
                               'reglas': base.reglas + extra}))
    salida = []
    for n in nuevas:
        antes = vigente.normas.get(n.acto)
        viejas = {r.clave: _campos_regla(r) for r in (antes.reglas if antes else ())}
        ahora = {r.clave: _campos_regla(r) for r in n.reglas}
        vigencia = {} if antes is None else {
            k: [getattr(antes, k), getattr(n, k)] for k in ('vigencia_desde', 'vigencia_hasta', 'estado_juridico')
            if getattr(antes, k) != getattr(n, k)}
        salida.append({'acto': n.acto, 'nueva': antes is None,
                       'entran': sorted(set(ahora) - set(viejas)),
                       'salen': sorted(set(viejas) - set(ahora)),
                       'cambian': sorted(k for k in set(viejas) & set(ahora) if viejas[k] != ahora[k]),
                       'vigencia': vigencia})
    return salida


def _fila_regla(norma: Norma, regla: Regla) -> dict:
    return {'acto': norma.acto, 'estado': norma.estado_juridico, 'vigencia_desde': norma.vigencia_desde,
            'vigencia_hasta': norma.vigencia_hasta, 'solo_referencia': norma.solo_referencia,
            'clave': regla.clave, 'valor': regla.valor, 'unidad': regla.unidad,
            'articulo_o_anexo': regla.articulo_o_anexo, 'pagina': regla.pagina, 'lineas': regla.lineas,
            'cita_literal': regla.cita_literal, 'interpretacion': regla.interpretacion, 'citada': regla.citada}


def _jsonl(ruta: Path, filas: list[dict]) -> None:
    publicar_duradero(ruta, ''.join(json.dumps(f, ensure_ascii=False, default=str) + '\n' for f in filas))


def exportar_dataset(destino: Path | str, *, raiz: Path | None = None, capa_usuario: Path | None = None) -> dict:
    """``normas.jsonl``, ``reglas.jsonl`` y ``huella.txt`` en ``destino``; no reescribe si la huella no cambió."""
    destino = Path(destino)
    huella = huella_biblioteca(raiz=raiz, capa_usuario=capa_usuario)
    previa = destino / 'huella.txt'
    if previa.is_file() and previa.read_text(encoding='utf-8').strip() == huella:
        return {'huella': huella, 'regenerado': False}
    registro = cargar_biblioteca(raiz=raiz, capa_usuario=capa_usuario)
    sustituidas = getattr(registro, 'sustituidas', {})
    normas = [registro.normas[a] for a in sorted(registro.normas)]
    destino.mkdir(parents=True, exist_ok=True)
    _jsonl(destino / 'normas.jsonl', [
        {'acto': n.acto, 'titulo': n.titulo, 'estado': n.estado_juridico, 'url': n.url,
         'fecha_publicacion': n.fecha_publicacion, 'vigencia_desde': n.vigencia_desde,
         'vigencia_hasta': n.vigencia_hasta, 'solo_referencia': n.solo_referencia, 'sha256': n.sha256,
         'reglas': len(n.reglas), 'sustituida_por_el_usuario': n.acto in sustituidas} for n in normas])
    reglas = [_fila_regla(n, r) for n in normas for r in n.reglas]
    _jsonl(destino / 'reglas.jsonl', reglas)
    previa.write_text(huella + '\n', encoding='utf-8', newline='\n')
    return {'huella': huella, 'regenerado': True, 'normas': len(normas), 'reglas': len(reglas)}
