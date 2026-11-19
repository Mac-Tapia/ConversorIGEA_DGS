"""Búfer local de episodios del gemelo digital (spec 024, T2).

Cada episodio es un objeto JSON inmutable en ``objetos/<ab>/<huella>.json``; esa es la
evidencia. SQLite es solo un índice para consultar y se rehace desde los objetos si se
borra o se corrompe (RF-6, RF-8, RF-9). No hay forma de borrar un episodio: lo que se
aprendió de un proyecto anterior tiene que seguir ahí para no olvidarlo (RF-10).
"""
from __future__ import annotations

from ...dominio.runtime_paths import staging_publicacion

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from ...dominio.digital_twin.episode import (
    Episodio,
    EpisodioInvalido,
    contenido_canonico,
    episodio_a_dict,
    leer_episodio,
)

#: Versión del índice: si cambia su forma, el índice viejo se rehace solo.
VERSION_INDICE = 1

_SHA256 = re.compile(r'[0-9a-f]{64}')


class ColisionEpisodio(RuntimeError):
    """En la ruta de una huella hay un contenido distinto: no se pisa la evidencia."""


@dataclass(frozen=True)
class Consulta:
    """Filtros del índice; los vacíos no filtran (RF-8)."""

    proyecto: str | None = None
    alimentador: str | None = None
    caso: str | None = None
    clase: str | None = None
    accion: str | None = None
    fuente: str | None = None
    pf_version: str | None = None


def raiz_buffer() -> Path:
    """``CSG_TWIN_DATA`` o ``_digital_twin`` junto a los espacios de la web: siempre local."""
    env = os.environ.get('CSG_TWIN_DATA', '').strip()
    if env:
        return Path(env)
    # 002:RF-2: la raíz común está en runtime_paths; el gemelo no importa la web.
    from ...dominio.runtime_paths import raiz_componente
    return raiz_componente('_digital_twin', 'CSG_TWIN_DATA')


def _texto(episodio: Episodio) -> str:
    return contenido_canonico(episodio_a_dict(episodio)) + '\n'




#: 086:RF-117: un cerrojo por carpeta del búfer, para que las aperturas a la vez de un mismo proceso rehagan el índice
#: una sola vez (CI del 19-11: «WinError 32 … episodios.nuevo» en la e2e F03).
_CERROJOS: dict[str, threading.Lock] = {}
_CERROJOS_GUARDA = threading.Lock()


def _cerrojo_de(raiz: Path) -> threading.Lock:
    clave = os.path.normcase(str(raiz.resolve()))
    with _CERROJOS_GUARDA:
        return _CERROJOS.setdefault(clave, threading.Lock())


#: 086:RF-120: la identidad 043 deducida de los episodios que se grabaron sin ella, aparte de los objetos (no se
#: reescriben: su huella es su contenido, 024:RF-10) y fuera del índice SQLite (se rehace desde los objetos y la
#: perdería). Los 79 escenarios y 6 calibraciones reales del 2026-11-05 al 2026-11-09 se grabaron así, con la web aún
#: sin 050:RF-23, y la ablación de 045 T3 no tenía ningún episodio con huella 043.
ARCHIVO_IDENTIDAD_043 = 'identidad_043.jsonl'
ESQUEMA_IDENTIDAD_043 = 'convertersmartgrid-twin-identity-043-v1'
CAMPOS_IDENTIDAD_043 = ('period', 'criterio_fijas', 'profile_hash')


def _fila_identidad(fila: object, donde: str) -> dict:
    """Una fila del registro, validada: lo deducido siempre dice de dónde salió y quién lo declaró."""
    if not isinstance(fila, dict) or fila.get('schema') != ESQUEMA_IDENTIDAD_043:
        raise ValueError(f'{donde}: fila sin el esquema {ESQUEMA_IDENTIDAD_043}')
    campos, origen = fila.get('campos'), fila.get('origen')
    if not _SHA256.fullmatch(str(fila.get('episode_id') or '')):
        raise ValueError(f'{donde}: episode_id no es la huella de un episodio')
    if (not isinstance(campos, dict) or not campos or set(campos) - set(CAMPOS_IDENTIDAD_043)
            or any(v is None or not str(v).strip() for v in campos.values())):
        raise ValueError(f'{donde}: campos debe dar valores de {", ".join(CAMPOS_IDENTIDAD_043)}')
    if not isinstance(origen, dict) or set(origen) != set(campos) or not all(str(v).strip() for v in origen.values()):
        raise ValueError(f'{donde}: cada campo deducido lleva su origen')
    if not str(fila.get('declarado_por') or '').strip() or not str(fila.get('fecha') or '').strip():
        raise ValueError(f'{donde}: falta declarado_por o fecha')
    return fila


def leer_identidades_043(raiz: Path | str) -> dict[str, dict]:
    """``episode_id → fila`` del registro aparte; un búfer sin él (todos los anteriores) da ``{}``.

    Solo lee: la preparación del ciclo no puede escribir en el búfer que consume (050:RF-12).
    """
    ruta = Path(raiz) / ARCHIVO_IDENTIDAD_043
    if not ruta.is_file():
        return {}
    filas: dict[str, dict] = {}
    for n, linea in enumerate(ruta.read_text(encoding='utf-8').splitlines(), 1):
        if linea.strip():
            fila = _fila_identidad(json.loads(linea), f'{ruta.name}:{n}')
            filas[fila['episode_id']] = fila
    return filas


def registrar_identidades_043(raiz: Path | str, filas: list[dict]) -> int:
    """Añade al registro las filas de episodios que aún no tienen; devuelve cuántas añadió (086:RF-120).

    Se escribe entero en un temporal y se reemplaza de una vez: un corte a mitad no deja una línea partida. Nunca
    toca ``objetos/`` ni el índice, y no admite la fila de un episodio que no está en el búfer.
    """
    raiz = Path(raiz)
    ruta = raiz / ARCHIVO_IDENTIDAD_043
    with _cerrojo_de(raiz):
        previas = leer_identidades_043(raiz)
        nuevas: list[dict] = []
        for i, fila in enumerate(filas):
            fila = _fila_identidad(fila, f'fila {i}')
            eid = fila['episode_id']
            if not (raiz / 'objetos' / eid[:2] / f'{eid}.json').is_file():
                raise ValueError(f'fila {i}: el episodio {eid} no está en {raiz / "objetos"}')
            if eid not in previas and all(f['episode_id'] != eid for f in nuevas):
                nuevas.append(fila)
        if not nuevas:
            return 0
        texto = ruta.read_text(encoding='utf-8') if ruta.is_file() else ''
        if texto and not texto.endswith('\n'):
            texto += '\n'
        texto += ''.join(json.dumps(f, ensure_ascii=False, sort_keys=True) + '\n' for f in nuevas)
        with staging_publicacion(ruta) as tmp:
            with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
                f.write(texto)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, ruta)
    return len(nuevas)


class BuferEpisodios:
    def __init__(self, raiz: Path | str | None = None):
        self.raiz = Path(raiz) if raiz is not None else raiz_buffer()
        self.indice = self.raiz / 'episodios.sqlite3'
        (self.raiz / 'objetos').mkdir(parents=True, exist_ok=True)
        if not self._indice_valido():
            with _cerrojo_de(self.raiz):
                if not self._indice_valido():            # otro hilo pudo rehacerlo mientras se esperaba
                    self.reconstruir_indice()

    # ------------------------------------------------------------------ objetos

    def _ruta(self, episode_id: str) -> Path:
        return self.raiz / 'objetos' / episode_id[:2] / f'{episode_id}.json'

    def guardar(self, episodio: Episodio) -> Path:
        """Escribe el episodio si no estaba; si estaba igual, no toca nada (RF-6)."""
        ruta = self._ruta(episodio.episode_id)
        texto = _texto(episodio)
        if ruta.exists():
            if ruta.read_text(encoding='utf-8') != texto:
                raise ColisionEpisodio(f'{ruta}: otro contenido con la huella {episodio.episode_id}')
        else:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with staging_publicacion(ruta) as tmp:
                with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(texto)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, ruta)
        with closing(self._conectar()) as con, con:
            self._indexar(con, episodio, ruta)
        return ruta

    def leer(self, episode_id: str) -> Episodio:
        # Solo una huella: el identificador llega de la web y no puede nombrar otra ruta.
        if not _SHA256.fullmatch(str(episode_id)):
            raise KeyError(f'«{episode_id}» no es la huella de un episodio')
        ruta = self._ruta(episode_id)
        if not ruta.is_file():
            raise KeyError(f'No hay episodio {episode_id} en {self.raiz}')
        return leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))

    def registrar_decision(self, decision: dict) -> dict:
        """Añade lo que decidió el operador sobre una propuesta (RF-48), con su fecha.

        Solo se añade, como los episodios: una decisión posterior no borra la anterior, y el
        entrenamiento las lee todas en orden.
        """
        from datetime import UTC, datetime

        fila = {**decision, 'fecha': datetime.now(UTC).isoformat(timespec='seconds')}
        with open(self.raiz / 'decisiones.jsonl', 'a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + '\n')
            f.flush()
            os.fsync(f.fileno())
        return fila

    def decisiones(self) -> list[dict]:
        ruta = self.raiz / 'decisiones.jsonl'
        if not ruta.is_file():
            return []
        return [json.loads(x) for x in ruta.read_text(encoding='utf-8').splitlines() if x.strip()]

    def cuarentena(self) -> list[Path]:
        """Manifiestos que no se pudieron leer al reconstruir, conservados tal cual."""
        return sorted((self.raiz / 'cuarentena').glob('*.json'))

    # ------------------------------------------------------------------ índice

    def _conectar(self) -> sqlite3.Connection:
        return sqlite3.connect(self.indice, timeout=30)

    def _indice_valido(self) -> bool:
        if not self.indice.is_file():
            return False
        try:
            with closing(self._conectar()) as con:
                version = con.execute('PRAGMA user_version').fetchone()[0]
                con.execute('SELECT count(*) FROM episodios').fetchone()
            return version == VERSION_INDICE
        except sqlite3.DatabaseError:
            return False

    @staticmethod
    def _crear(con: sqlite3.Connection) -> None:
        con.executescript(f"""
            CREATE TABLE episodios (
                episode_id TEXT PRIMARY KEY, clase TEXT, caso TEXT, proyecto TEXT,
                accion TEXT, fuente TEXT, pf_version TEXT, creado TEXT, ruta TEXT);
            CREATE TABLE alimentadores (episode_id TEXT, alimentador TEXT, orden INTEGER,
                PRIMARY KEY (episode_id, orden));
            CREATE INDEX ix_proyecto ON episodios (proyecto);
            CREATE INDEX ix_caso_clase ON episodios (caso, clase);
            CREATE INDEX ix_fuente ON episodios (fuente);
            CREATE INDEX ix_alimentador ON alimentadores (alimentador);
            PRAGMA user_version = {VERSION_INDICE};
        """)

    def _indexar(self, con: sqlite3.Connection, e: Episodio, ruta: Path) -> None:
        con.execute('INSERT OR IGNORE INTO episodios VALUES (?,?,?,?,?,?,?,?,?)', (
            e.episode_id, e.clase.value, e.caso.value, e.nativo['project'],
            e.accion.get('tipo'), e.fuente['source_fingerprint'], e.nativo.get('pf_version'),
            e.creado, ruta.relative_to(self.raiz).as_posix()))
        con.executemany('INSERT OR IGNORE INTO alimentadores VALUES (?,?,?)',
                        [(e.episode_id, f, i) for i, f in enumerate(e.nativo['feeders'])])

    def reconstruir_indice(self) -> int:
        """Rehace el índice desde los objetos; lo ilegible va a cuarentena (RF-9).

        Devuelve cuántos episodios quedaron indexados.
        """
        # 086:RF-117: un temporal propio por llamada; con uno común, otro proceso lo borraba o reemplazaba abierto.
        nuevo = self.indice.with_name(f'{self.indice.stem}.{os.getpid()}.{uuid.uuid4().hex[:8]}.nuevo')
        cuarentena = self.raiz / 'cuarentena'
        n = 0
        with closing(sqlite3.connect(nuevo)) as con, con:
            self._crear(con)
            for ruta in sorted((self.raiz / 'objetos').glob('*/*.json')):
                try:
                    e = leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))
                    if ruta.stem != e.episode_id:
                        raise EpisodioInvalido('episode_id', 'no coincide con el nombre del objeto')
                except (ValueError, OSError):
                    cuarentena.mkdir(exist_ok=True)
                    os.replace(ruta, cuarentena / ruta.name)
                    continue
                self._indexar(con, e, ruta)
                n += 1
        for intento in range(20):
            try:
                os.replace(nuevo, self.indice)
                return n
            except PermissionError:
                # 086:RF-117: en Windows el índice abierto por otro proceso no se reemplaza. Si ya es válido, otro
                # proceso lo rehízo con los mismos objetos: vale el suyo; si no, se reintenta un momento.
                if self._indice_valido():
                    nuevo.unlink(missing_ok=True)
                    return n
                time.sleep(0.05 * (intento + 1))
        nuevo.unlink(missing_ok=True)
        raise PermissionError(f'No se pudo reemplazar el índice {self.indice}: lo tiene abierto otro proceso.')

    def consultar(self, consulta: Consulta) -> list[Episodio]:
        """Episodios que cumplen todos los filtros, por fecha y huella (RF-8)."""
        donde, args = [], []
        for campo in ('proyecto', 'caso', 'clase', 'accion', 'fuente', 'pf_version'):
            valor = getattr(consulta, campo)
            if valor is not None:
                donde.append(f'e.{campo} = ?')
                args.append(valor)
        if consulta.alimentador is not None:
            donde.append('e.episode_id IN (SELECT episode_id FROM alimentadores WHERE alimentador = ?)')
            args.append(consulta.alimentador)
        sql = 'SELECT e.episode_id FROM episodios e'
        if donde:
            sql += ' WHERE ' + ' AND '.join(donde)
        sql += ' ORDER BY e.creado, e.episode_id'
        with closing(self._conectar()) as con:
            ids = [fila[0] for fila in con.execute(sql, args)]
        return [self.leer(i) for i in ids]
