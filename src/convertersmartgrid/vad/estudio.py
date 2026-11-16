"""Registro del estudio VAD: empresa, grupo, periodo y versión del TdR, en su propia carpeta (108:RF-1).

El estudio vive en ``<espacio>/vad/<id>/estudio.json`` y nunca lee ni escribe en las carpetas del PIDE ni del
PIT: G0 (BP-18) encontró que el único rastro del VAD en el conversor eran comentarios dentro del PIDE, y
mezclarlos haría pasar un costeo del PIDE por el estudio de la empresa modelo. La empresa sale del perfil
(P13): sin nombre en el perfil no se supone ninguna.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..perfil_empresa import PerfilEmpresa
from ..registro_normativo import RegistroError, RegistroNormativo
from ..util import publicar_duradero
from . import VadError

#: Estados del estudio. «aprobado» no existe: declararlo está fuera de alcance (spec 108).
ESTADOS = ('pendiente_de_comprobar', 'conforme', 'no_conforme', 'desactualizado')
_PERIODO = re.compile(r'(\d{4})-(\d{4})')


@dataclass(frozen=True)
class EstudioVad:
    id: str
    empresa: str
    grupo: int
    periodo: str
    version_tdr: str
    estado: str = 'pendiente_de_comprobar'
    #: Lo que dejó el estudio en ``no_conforme`` o ``desactualizado``, con el nombre de cada entrada.
    motivos: tuple[str, ...] = ()
    #: Huella del registro normativo con la que se creó: si el TdR cambia, el estudio conserva esta (108:RF-9).
    instantanea_registro: str = ''
    #: Regla del registro → huella con la que se creó el estudio (vacía si la regla no estaba).
    dependencias: Mapping[str, str] = field(default_factory=dict)
    #: Regla → tablas o cálculos que la usan: lo que se nombra si la regla cambia.
    usos: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: Si la empresa está en el ámbito del FONAFE (108:RF-17); None es «no declarado» y no se supone.
    ambito_fonafe: bool | None = None

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise VadError(f'estado del estudio desconocido: {self.estado!r}; los válidos son {ESTADOS}')
        if self.ambito_fonafe is not None and not isinstance(self.ambito_fonafe, bool):
            raise VadError(f'ambito_fonafe tiene que ser verdadero, falso o sin declarar, no {self.ambito_fonafe!r}')
        object.__setattr__(self, 'motivos', tuple(self.motivos))
        object.__setattr__(self, 'dependencias', dict(self.dependencias))
        object.__setattr__(self, 'usos', {k: tuple(v) for k, v in self.usos.items()})


def _slug(texto: str) -> str:
    plano = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '-', plano.lower()).strip('-')


def carpeta_estudio(espacio: Path | str, id_estudio: str) -> Path:
    """La carpeta del estudio dentro del espacio; un id con separadores no sale de ``vad/``."""
    if not id_estudio or _slug(id_estudio) != id_estudio:
        raise VadError(f'identificador de estudio no válido: {id_estudio!r}')
    return Path(espacio) / 'vad' / id_estudio


def escribir_json(ruta: Path, datos: Any) -> None:
    """Escritura atómica y duradera (P6; 001:RF-5): nunca queda un JSON a medias si el proceso se corta, ni tras un
    corte de luz (publicar_duradero sincroniza antes de sustituir). El mismo texto que antes: un str, que se escribe
    en modo texto como hacía el json.dump sobre os.fdopen(…, 'w')."""
    publicar_duradero(ruta, json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True))


def _validar(perfil: PerfilEmpresa, grupo: Any, periodo: Any, version_tdr: Any) -> None:
    if not (perfil.nombre or '').strip():
        raise VadError('el perfil de empresa no trae nombre: la empresa del estudio no se supone')
    if isinstance(grupo, bool) or not isinstance(grupo, int) or grupo < 1:
        raise VadError(f'el grupo de fijación tiene que ser un entero mayor que 0, no {grupo!r}')
    m = _PERIODO.fullmatch(str(periodo or ''))
    if not m or int(m.group(1)) >= int(m.group(2)):
        raise VadError(f'el periodo tiene que ser «AAAA-AAAA» con el primer año menor que el segundo, no {periodo!r}')
    if not str(version_tdr or '').strip():
        raise VadError('el estudio necesita la versión del TdR con la que se arma')


def _huella(registro: RegistroNormativo, clave: str) -> str:
    try:
        return registro.regla(clave).huella()
    except RegistroError:
        return ''


def crear_estudio(espacio: Path | str, perfil: PerfilEmpresa, *, grupo: int, periodo: str, version_tdr: str,
                  registro: RegistroNormativo | None = None,
                  usos: Mapping[str, Sequence[str]] | None = None,
                  ambito_fonafe: bool | None = None) -> EstudioVad:
    """Crea el estudio y su carpeta, con la instantánea del registro y la huella de cada regla que usa.

    Un estudio que ya existe no se sobrescribe. ``usos`` dice qué tablas o cálculos usan cada regla.
    ``ambito_fonafe`` lo declara el operador desde el perfil de la empresa; sin declarar no se supone (108:RF-17).
    """
    _validar(perfil, grupo, periodo, version_tdr)
    usos = {k: tuple(v) for k, v in (usos or {}).items()}
    estudio = EstudioVad(id=_slug(f'{perfil.nombre} g{grupo} {periodo}'), empresa=perfil.nombre.strip(),
                         grupo=grupo, periodo=periodo, version_tdr=str(version_tdr).strip(),
                         instantanea_registro=registro.instantanea() if registro is not None else '',
                         dependencias={k: _huella(registro, k) for k in usos} if registro is not None else {},
                         usos=usos, ambito_fonafe=ambito_fonafe)
    ruta = carpeta_estudio(espacio, estudio.id) / 'estudio.json'
    if ruta.exists():
        raise VadError(f'el estudio {estudio.id} ya existe en este espacio; no se sobrescribe')
    escribir_json(ruta, asdict(estudio))
    return estudio


def guardar_estudio(espacio: Path | str, estudio: EstudioVad) -> None:
    """Guarda un cambio de estado de un estudio ya creado."""
    ruta = carpeta_estudio(espacio, estudio.id) / 'estudio.json'
    if not ruta.exists():
        raise VadError(f'el estudio {estudio.id} no existe en este espacio')
    escribir_json(ruta, asdict(estudio))


def cargar_estudio(espacio: Path | str, id_estudio: str) -> EstudioVad:
    ruta = carpeta_estudio(espacio, id_estudio) / 'estudio.json'
    if not ruta.is_file():
        raise VadError(f'no hay ningún estudio {id_estudio} en este espacio')
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    return EstudioVad(**datos)


def exigir_vigente(estudio: EstudioVad, registro: RegistroNormativo, fecha: str | None = None) -> list[str]:
    """Lo que impide emitir el estudio como conforme (108:RF-10), cada cosa con el nombre de su entrada."""
    motivos: list[str] = []
    try:
        tdr = registro.norma(estudio.version_tdr)
    except RegistroError as exc:
        return [f'el TdR {estudio.version_tdr} no está en el registro normativo: {exc}']
    if not tdr.obligatoria_en(fecha):
        motivos.append(f'el TdR {tdr.acto} está «{tdr.estado_juridico}» en el registro: el estudio no se emite como '
                       'conforme')
    clave_grupo = f'vad.grupo.{estudio.grupo}.periodo'
    try:
        grupo = registro.regla(clave_grupo, fecha)
    except RegistroError:
        grupo = None
    if grupo is None or str(grupo.regla.valor) != estudio.periodo or not grupo.obligatoria:
        motivos.append(f'el TdR {tdr.acto} no registra como vigente el grupo {estudio.grupo} con el periodo '
                       f'{estudio.periodo} ({clave_grupo})')
    for clave in sorted(estudio.usos):
        try:
            rv = registro.regla(clave, fecha)
        except RegistroError:
            motivos.append(f'la regla {clave} no está en el registro')
            continue
        if not rv.regla.citada:
            motivos.append(f'la regla {clave} no tiene cita (literal y página o líneas)')
        elif not rv.obligatoria:
            motivos.append(f'la regla {clave} es de {rv.norma.acto}, que está «{rv.estado}»')
        if rv.regla.igv == 'sin_leer':
            motivos.append(f'la regla {clave} tiene el IGV sin leer en el anexo')
    return motivos


def comprobar_estudio(espacio: Path | str, id_estudio: str, registro: RegistroNormativo,
                      fecha: str | None = None) -> EstudioVad:
    """Fija el estado del estudio con el registro de hoy y lo guarda (108:RF-9, RF-10).

    El estudio conserva la instantánea con la que se creó. Si una regla que usa cambió desde entonces, queda
    ``desactualizado`` y se nombran la regla y las tablas o cálculos que la usan; no se recalcula solo.
    """
    estudio = cargar_estudio(espacio, id_estudio)
    motivos = exigir_vigente(estudio, registro, fecha)
    cambiadas = [f'la regla {clave} cambió en el registro desde que se creó el estudio (afecta a: '
                 f'{", ".join(estudio.usos.get(clave, ())) or "sin uso declarado"})'
                 for clave, huella in sorted(estudio.dependencias.items()) if _huella(registro, clave) != huella]
    estado = 'desactualizado' if cambiadas else ('no_conforme' if motivos else 'conforme')
    nuevo = replace(estudio, estado=estado, motivos=tuple(cambiadas + motivos))
    guardar_estudio(espacio, nuevo)
    return nuevo
