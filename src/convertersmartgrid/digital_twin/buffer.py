"""Búfer local de episodios del gemelo digital (spec 024, T2).

Cada episodio es un objeto JSON inmutable en ``objetos/<ab>/<huella>.json``; esa es la
evidencia. SQLite es solo un índice para consultar y se rehace desde los objetos si se
borra o se corrompe (RF-6, RF-8, RF-9). No hay forma de borrar un episodio: lo que se
aprendió de un proyecto anterior tiene que seguir ahí para no olvidarlo (RF-10).
"""
from __future__ import annotations

from ..runtime_paths import staging_publicacion

import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .episode import (
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
    from ..web.workspace import raiz_componente
    return raiz_componente('_digital_twin', 'CSG_TWIN_DATA')


def _texto(episodio: Episodio) -> str:
    return contenido_canonico(episodio_a_dict(episodio)) + '\n'


def muestras_aprendizaje(instantanea: dict, referencias: dict) -> list:
    """050:RF-2/3: relee objetos inmutables y reproduce el reparto PINN sin escribir SQLite."""
    from ..aprendizaje_continuo import CicloBloqueado, crear_observacion_id, muestra_de_registro, ruta_de
    from .oraculo import _grupos, _muestras, separar_calibracion

    episodios = []
    for ruta in sorted((ruta_de(instantanea, 'twin') / 'objetos').glob('*/*.json')):
        e = leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))
        if ruta.stem != e.episode_id:
            raise CicloBloqueado('episodio congelado con identidad distinta del nombre')
        if e.clase.value in ('accepted', 'counterfactual') and e.nativo.get('reopen_verified') is not True:
            raise CicloBloqueado('episodio sin reapertura nativa comprobada')
        episodios.append(e)

    class LecturaCongelada:
        def consultar(self, consulta):
            if consulta != Consulta():
                raise CicloBloqueado('el productor solo admite la consulta común del ciclo')
            return episodios

    muestras, ids = _muestras(LecturaCongelada(), Consulta())
    grupos = separar_calibracion(_grupos(muestras, ids, None))
    identidad = {id(m): i for m, i in zip(muestras, ids, strict=True)}
    por_id = {e.episode_id: e for e in episodios}
    nombres = {'validacion': 'seleccion'}
    resultado = []
    for parte, ms in grupos.items():
        for m in ms:
            e = por_id[identidad[id(m)]]
            muestra = muestra_de_registro(instantanea, referencias, 'twin',
                e.episode_id, episodio_a_dict(e), familia='pinn',
                particion=nombres.get(parte, parte), origen='simulado_nativo', etiqueta='motor_nativo')
            referencia = referencias['twin'][e.episode_id]
            if muestra.observacion_id != crear_observacion_id(muestra.contexto,
                    referencia['fuente_hash'], e.episode_id, e.creado):
                raise CicloBloqueado('la referencia no corresponde a la observación fuente del episodio')
            resultado.append(muestra)
    return resultado


class BuferEpisodios:
    def __init__(self, raiz: Path | str | None = None):
        self.raiz = Path(raiz) if raiz is not None else raiz_buffer()
        self.indice = self.raiz / 'episodios.sqlite3'
        (self.raiz / 'objetos').mkdir(parents=True, exist_ok=True)
        if not self._indice_valido():
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
        nuevo = self.indice.with_suffix('.nuevo')
        nuevo.unlink(missing_ok=True)
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
        os.replace(nuevo, self.indice)
        return n

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
