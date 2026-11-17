"""Las fuentes de la empresa del espacio: cada libro que se carga una vez y usan todos los módulos (orden del usuario,
17-11: «todos los módulos están relacionados y vinculados desde el cargado de archivos … con la empresa que se va a
trabajar»). Ver ``config/modulos/vinculos.json`` para qué comparte cada módulo según la norma.

- Una fuente es un fichero (o un .zip con sus miembros) con su clase, su periodo y su huella (sha256).
- Se guarda en ``<espacio>/fuentes/<clase>/<huella16>_<nombre>`` y el índice en ``<espacio>/fuentes/fuentes.json``,
  escrito de forma atómica. La misma huella no se duplica.
- Son reemplazables por periodo: la nueva de su clase y periodo pasa a vigente y la anterior se conserva.
- La red convertida del espacio (la que deja la carga, del mismo conversor para todos) se consulta con
  ``red_del_espacio``.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .util import publicar_duradero, write_json_atomic

CLASES = ('sicodi', 'pit', 'red_area', 'vad', 'vad_caso', 'tdr', 'pide', 'perfil', 'catalogo', 'pfd', 'medicion',
          'demanda', 'cargas_nuevas', 'proyeccion', 'alternativas', 'interrupciones', 'otro')
CARPETA = 'fuentes'
INDICE = 'fuentes.json'
#: Lo que deja la carga del VNR-GIS en el espacio para los módulos (estudio VNR, PIT, VAD…).
CANONICAL_VNR = Path('derivados') / 'vnr' / 'canonical.json'
RED_DEL_ESPACIO = Path('derivados') / 'red.json'


class FuenteError(ValueError):
    """Una fuente que no se puede registrar o que no existe."""


@dataclass(frozen=True)
class Fuente:
    id: str
    clase: str
    periodo: str
    nombre: str
    huella: str
    ruta_rel: str
    registrada: str
    vigente: bool = True
    miembros: list[dict] = field(default_factory=list)


def _huella(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()


def _nombre_seguro(nombre: str) -> str:
    limpio = re.sub(r'[^\w.\- ]+', '_', Path(nombre).name).strip(' .') or 'fichero'
    return limpio[:120]


def _leer(raiz: Path) -> list[dict]:
    ruta = Path(raiz) / CARPETA / INDICE
    if not ruta.is_file():
        return []
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    return list(datos.get('fuentes') or [])


def _escribir(raiz: Path, filas: list[dict]) -> None:
    write_json_atomic(Path(raiz) / CARPETA / INDICE, {'esquema': 'fuentes_empresa_v1', 'fuentes': filas})


def _miembros(ruta: Path) -> list[dict]:
    if ruta.suffix.lower() != '.zip':
        return []
    salida = []
    with zipfile.ZipFile(ruta) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            with z.open(info) as f:
                salida.append({'nombre': info.filename, 'huella': hashlib.sha256(f.read()).hexdigest()})
    return salida


def registrar(raiz: Path | str, clase: str, origen: Path | str, *, nombre: str = '', periodo: str = '') -> Fuente:
    """Copia ``origen`` a las fuentes de la empresa como ``clase`` y ``periodo``; si ya está (misma huella y clase),
    devuelve la registrada y la vuelve vigente."""
    if clase not in CLASES:
        raise FuenteError(f'clase de fuente desconocida: {clase!r}; las válidas son {", ".join(CLASES)}')
    origen = Path(origen)
    if not origen.is_file():
        raise FuenteError(f'no existe el fichero {origen.name}')
    raiz = Path(raiz)
    huella = _huella(origen)
    filas = _leer(raiz)
    nombre = _nombre_seguro(nombre or origen.name)
    existente = next((f for f in filas if f['huella'] == huella and f['clase'] == clase), None)
    for f in filas:
        if f['clase'] == clase and f.get('periodo', '') == periodo:
            f['vigente'] = False
    if existente is not None:
        existente['vigente'] = True
        _escribir(raiz, filas)
        return Fuente(**existente)
    rel = Path(CARPETA) / clase / f'{huella[:16]}_{nombre}'
    destino = raiz / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    fila = asdict(Fuente(huella[:16], clase, periodo, nombre, huella, rel.as_posix(),
                         datetime.now(timezone.utc).isoformat(timespec='seconds'), True, _miembros(destino)))
    filas.append(fila)
    _escribir(raiz, filas)
    return Fuente(**fila)


def listar(raiz: Path | str, clase: str | None = None) -> list[Fuente]:
    return [Fuente(**f) for f in _leer(Path(raiz)) if clase is None or f['clase'] == clase]


def vigente(raiz: Path | str, clase: str, periodo: str | None = None) -> Fuente | None:
    """La vigente de ``clase`` (y de ``periodo`` si se da); sin periodo, la última registrada de las vigentes."""
    candidatas = [f for f in listar(raiz, clase) if f.vigente and (periodo is None or f.periodo == periodo)]
    return max(candidatas, key=lambda f: f.registrada) if candidatas else None


def ruta(raiz: Path | str, id_: str) -> Path:
    for f in listar(raiz):
        if f.id == id_:
            return Path(raiz) / f.ruta_rel
    raise FuenteError(f'no hay ninguna fuente {id_!r} en la empresa del espacio')


def guardar_red(raiz: Path | str, *, fuente: str, empresa: str = '', alimentadores: list[str] | None = None,
                canonical: dict | None = None) -> None:
    """Lo que deja la carga para los módulos: de qué fuente sale la red (txt, mdb o vnr), su empresa, sus
    alimentadores y, si es VNR-GIS, su modelo canónico."""
    raiz = Path(raiz)
    datos = {'fuente': fuente, 'empresa': empresa, 'alimentadores': sorted(alimentadores or [])}
    if canonical is not None:
        ruta_c = raiz / CANONICAL_VNR
        texto = json.dumps(canonical, ensure_ascii=False)
        publicar_duradero(ruta_c, texto)  # el mismo texto del que sale su huella
        datos['canonical'] = CANONICAL_VNR.as_posix()
        datos['huella'] = hashlib.sha256(texto.encode('utf-8')).hexdigest()
    write_json_atomic(raiz / RED_DEL_ESPACIO, datos)


def red_del_espacio(raiz: Path | str) -> dict | None:
    """{'fuente', 'empresa', 'alimentadores', 'canonical' (ruta relativa o ausente), 'huella'} o None sin carga."""
    ruta_r = Path(raiz) / RED_DEL_ESPACIO
    if not ruta_r.is_file():
        return None
    return json.loads(ruta_r.read_text(encoding='utf-8'))
