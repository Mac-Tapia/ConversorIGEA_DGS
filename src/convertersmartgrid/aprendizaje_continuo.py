"""050 — Ciclo común de aprendizaje: instantánea, vistas por familia, ciclo único y conjunto publicado.

Cada familia (LLM, GRU, PINN, evolutivos, recuperador) ya se entrenaba y registraba por su cuenta
(043, 044, 045). Entrenarlas por separado no acreditaba que cooperaran: cada una leía el búfer o el
dataset tal como estuviera en el momento de arrancar, y la web daba por «reentrenado» el último
modelo individual. Este módulo no entrena: fija lo que todas consumen, decide si toca un ciclo,
lo ejecuta con el ``TrainingCoordinator`` existente y publica un conjunto compatible desde el
``RegistroModelo`` común, con su vuelta atrás.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any

from .experimentos import ContextoExperimento, clave_contexto
from .model_registry import EstadoModelo, RegistroModelo
from .runtime_paths import staging_publicacion
from .training_coordinator import ORDEN_MODELOS, TrainingCoordinator, TrainingStage, pid_vivo

ESQUEMA_INSTANTANEA = 'convertersmartgrid-learning-snapshot-v1'
ESQUEMA_INSTANTANEA_MULTIPROYECTO = 'convertersmartgrid-learning-snapshot-v2'
ESQUEMA_CICLO = 'convertersmartgrid-learning-cycle-v1'
ESQUEMA_CONJUNTO = 'convertersmartgrid-model-ensemble-v1'
ESQUEMA_CONTEXTO_CICLO = 'convertersmartgrid-learning-context-v1'

#: 050:RF-2: de dónde sale una muestra. Un dato redactado por el maestro no se vuelve humano.
ORIGENES = ('observado', 'simulado_nativo', 'redactado')
#: Quién puso la etiqueta. Solo las dos primeras son verdad eléctrica (050:RF-3).
ETIQUETAS_FISICAS = ('medicion', 'motor_nativo')
ETIQUETAS = ETIQUETAS_FISICAS + ('operador', 'maestro', 'prediccion', 'llm')
#: Familias cuya etiqueta es una magnitud eléctrica o una serie medida: sin fuente nativa no aprenden.
FAMILIAS_FISICAS = frozenset({'gru', 'pinn'})
#: 050:RF-10: lo que la web o el CLI muestran, en el orden en que ocurre.
FASES = ('preparacion', 'entrenamiento', 'seleccion', 'evaluacion', 'publicacion', 'activacion',
         'aceptacion_nativa')
#: 050:RF-5: lo que cada propuesta conjunta debe decir de dónde sacó.
APORTES = ('interpretacion', 'pronostico', 'estimacion_fisica', 'alternativas', 'evidencia',
           'validacion_nativa')
_HEX = re.compile(r'[0-9a-f]{64}')


class CicloBloqueado(ValueError):
    """050:RF-8: el ciclo no puede seguir; el conjunto aceptado no cambia."""


def _canonico(valor: Any) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False, default=str).encode('utf-8')


def _huella(valor: Any) -> str:
    return hashlib.sha256(_canonico(valor)).hexdigest()


def _sha(ruta: Path) -> str:
    with ruta.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _escribir(ruta: Path, payload: Mapping[str, Any]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(ruta) as tmp:
        tmp.write_bytes(_canonico(payload))
        os.replace(tmp, ruta)


def _leer(ruta: Path) -> dict[str, Any]:
    dato = json.loads(ruta.read_text(encoding='utf-8'))
    if not isinstance(dato, dict):
        raise ValueError(f'{ruta.name}: no es un objeto')
    return dato


# --------------------------------------------------------------------------- T1: instantánea

def _ficheros(ruta: Path) -> list[tuple[str, Path]]:
    """Ficheros de una fuente con su ruta relativa; un enlace podría apuntar fuera y cambiar solo."""
    if ruta.is_symlink():
        raise CicloBloqueado(f'{ruta.name}: es un enlace; se copia el dato, no un puntero')
    if ruta.is_file():
        return [(ruta.name, ruta)]
    salida = []
    for p in sorted(ruta.rglob('*')):
        if p.is_symlink():
            raise CicloBloqueado(f'{p.name}: enlace dentro de la fuente')
        if p.is_file():
            salida.append((p.relative_to(ruta).as_posix(), p))
    return salida


def huellas_de(ruta: Path | str) -> dict[str, str]:
    return {rel: _sha(p) for rel, p in _ficheros(Path(ruta))}


def crear_contexto_ciclo(proyectos: Mapping[str, str]) -> dict[str, Any]:
    """050:RF-1: contexto agregado sin sustituir las identidades 043 individuales."""
    if not isinstance(proyectos, Mapping) or not proyectos:
        raise CicloBloqueado('contexto de ciclo sin proyectos')
    for proyecto, huella in proyectos.items():
        if not isinstance(proyecto, str) or not proyecto.strip() or proyecto != proyecto.strip():
            raise CicloBloqueado('identidad de proyecto vacía o ambigua en el contexto')
        if not isinstance(huella, str) or not _HEX.fullmatch(huella):
            raise CicloBloqueado(f'{proyecto}: contexto 043 sin SHA-256')
    cuerpo = {'schema': ESQUEMA_CONTEXTO_CICLO, 'proyectos': dict(sorted(proyectos.items()))}
    return {**cuerpo, 'contexto_hash': _huella(cuerpo)}


def _contexto_hash(contexto: ContextoExperimento | Mapping[str, Any] | str) -> str:
    if isinstance(contexto, ContextoExperimento):
        return clave_contexto(contexto)
    if isinstance(contexto, Mapping):
        reconstruido = crear_contexto_ciclo(contexto.get('proyectos'))
        if (contexto.get('schema') != ESQUEMA_CONTEXTO_CICLO
                or reconstruido['contexto_hash'] != contexto.get('contexto_hash')):
            raise CicloBloqueado('manifiesto del contexto de ciclo modificado')
        return reconstruido['contexto_hash']
    if not isinstance(contexto, str) or not _HEX.fullmatch(contexto):
        raise CicloBloqueado('contexto 043 ausente o sin huella SHA-256')
    return contexto


def crear_observacion_id(contexto_hash: str, fuente_hash: str, registro_id: str, instante: str) -> str:
    """050:RF-2: la observación fuente conserva identidad entre familias y snapshots."""
    for nombre, valor in (('contexto_hash', contexto_hash), ('fuente_hash', fuente_hash)):
        if not isinstance(valor, str) or not _HEX.fullmatch(valor):
            raise CicloBloqueado(f'{nombre}: falta SHA-256 de procedencia')
    if not isinstance(registro_id, str) or not registro_id.strip():
        raise CicloBloqueado('registro_id: falta identidad de la observación fuente')
    try:
        if not isinstance(instante, str):
            raise ValueError('no es texto')
        fecha = datetime.fromisoformat(instante)
        if fecha.utcoffset() is None:
            raise ValueError('sin zona horaria')
        utc = fecha.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, OverflowError) as exc:
        raise CicloBloqueado('instante: se exige fecha ISO-8601 con zona horaria explícita') from exc
    return _huella({'schema': 'convertersmartgrid-observation-v1', 'contexto_hash': contexto_hash,
                    'fuente_hash': fuente_hash, 'registro_id': registro_id, 'instante': utc})


def registrar_bloqueo(raiz: Path | str, etapa: str, motivos: Sequence[str], **extra: Any) -> dict:
    """050:RF-8: el bloqueo queda escrito; nada anuncia un entrenamiento que no ocurrió."""
    fila = {'fecha': _ahora(), 'etapa': etapa, 'estado': 'bloqueado', 'motivos': list(motivos), **extra}
    ruta = Path(raiz) / 'bloqueos.jsonl'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open('a', encoding='utf-8') as f:
        f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True, default=str) + '\n')
    return fila


def congelar_instantanea(fuentes: Mapping[str, Path | str | None], raiz: Path | str, *,
                         contexto: ContextoExperimento | Mapping[str, Any] | str, versiones: Mapping[str, str],
                         obligatorias: Iterable[str] | None = None) -> dict[str, Any]:
    """050:RF-1, RF-2, RF-8: copia verificada de todo lo que el ciclo consume, antes de preparar nada.

    Se copian los datos, no punteros: el búfer del gemelo sigue recibiendo episodios mientras otra
    familia entrena, y una PINN y una GRU que leen el búfer «vivo» aprenden de redes distintas.
    La identidad es la huella del contenido: congelar dos veces lo mismo da la misma instantánea.
    """
    raiz = Path(raiz)
    obligatorias = set(fuentes if obligatorias is None else obligatorias)
    motivos = []
    try:
        ctx = _contexto_hash(contexto)
    except CicloBloqueado as exc:
        ctx, motivos = None, [str(exc)]
    if not versiones or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip()
                            for k, v in versiones.items()):
        motivos.append('versiones de código y modelos sin declarar')
    for nombre in sorted(obligatorias):
        ruta = fuentes.get(nombre)
        if ruta is None or not Path(ruta).exists():
            motivos.append(f'{nombre}: fuente obligatoria ausente')
    antes: dict[str, dict[str, str]] = {}
    if not motivos:
        for nombre, ruta in sorted(fuentes.items()):
            if ruta is None:
                continue
            try:
                antes[nombre] = huellas_de(ruta)
            except CicloBloqueado as exc:
                motivos.append(str(exc))
                continue
            if not antes[nombre] and nombre in obligatorias:
                motivos.append(f'{nombre}: fuente obligatoria vacía')
    if motivos:
        registrar_bloqueo(raiz, 'instantanea', motivos)
        raise CicloBloqueado('; '.join(motivos))
    esquema = ESQUEMA_INSTANTANEA_MULTIPROYECTO if isinstance(contexto, Mapping) else ESQUEMA_INSTANTANEA
    identidad = _huella({'schema': esquema, 'contexto_hash': ctx,
                         'versiones': dict(versiones), 'archivos': antes})
    final = raiz / 'instantaneas' / identidad
    if final.is_dir():
        return verificar_instantanea(final)
    manifiesto = {'schema': esquema, 'snapshot_id': identidad, 'contexto_hash': ctx,
                  'versiones': dict(versiones), 'archivos': antes, 'creada': _ahora(),
                  'origenes': {n: str(Path(r).resolve()) for n, r in fuentes.items() if r is not None},
                  'tipos': {n: 'fichero' if Path(r).is_file() else 'carpeta'
                            for n, r in fuentes.items() if r is not None}}
    if isinstance(contexto, Mapping):
        manifiesto['contextos'] = dict(contexto['proyectos'])
    final.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(final) as tmp:
        tmp.mkdir()
        for nombre, ruta in sorted(fuentes.items()):
            if ruta is None:
                continue
            for rel, origen in _ficheros(Path(ruta)):
                destino = tmp / 'datos' / nombre / rel
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origen, destino)
        copias = {n: huellas_de(tmp / 'datos' / n) for n in antes}
        despues = {n: huellas_de(fuentes[n]) for n in antes}
        cambiadas = sorted(n for n in antes if despues[n] != antes[n])
        if cambiadas:
            # Un episodio nuevo llegó a mitad de la copia: se repite en el siguiente ciclo, no se mezcla.
            registrar_bloqueo(raiz, 'instantanea', [f'{n}: la fuente cambió durante la copia' for n in cambiadas])
            raise CicloBloqueado(f'fuentes cambiadas durante la copia: {cambiadas}')
        if copias != antes:
            registrar_bloqueo(raiz, 'instantanea', ['la copia no coincide con su fuente'])
            raise CicloBloqueado('la copia no coincide con su fuente')
        (tmp / 'manifiesto.json').write_bytes(_canonico(manifiesto))
        os.replace(tmp, final)
    return verificar_instantanea(final)


def verificar_instantanea(carpeta: Path | str) -> dict[str, Any]:
    """Relee la instantánea; una copia tocada después no pasa por la congelada."""
    carpeta = Path(carpeta)
    manifiesto = _leer(carpeta / 'manifiesto.json')
    esquema = manifiesto.get('schema')
    if esquema not in (ESQUEMA_INSTANTANEA, ESQUEMA_INSTANTANEA_MULTIPROYECTO):
        raise CicloBloqueado('instantánea de otro esquema')
    if esquema == ESQUEMA_INSTANTANEA_MULTIPROYECTO and 'contextos' not in manifiesto:
        raise CicloBloqueado('instantánea de varios proyectos sin mapa de contextos')
    if 'contextos' in manifiesto:
        agregado = crear_contexto_ciclo(manifiesto['contextos'])
        if agregado['contexto_hash'] != manifiesto.get('contexto_hash'):
            raise CicloBloqueado('mapa de contextos de la instantánea modificado')
    esperado = _huella({'schema': esquema, 'contexto_hash': manifiesto.get('contexto_hash'),
                        'versiones': manifiesto.get('versiones'), 'archivos': manifiesto.get('archivos')})
    if esperado != manifiesto.get('snapshot_id') or carpeta.name != esperado:
        raise CicloBloqueado('manifiesto de instantánea modificado')
    for nombre, huellas in manifiesto['archivos'].items():
        if huellas_de(carpeta / 'datos' / nombre) != huellas:
            raise CicloBloqueado(f'{nombre}: la copia congelada cambió')
    return {**manifiesto, 'ruta': str(carpeta), 'verificada': True}


def ruta_de(instantanea: Mapping[str, Any], nombre: str) -> Path:
    """La copia congelada de una fuente, que es lo que las etapas leen (nunca el origen vivo)."""
    if nombre not in instantanea.get('archivos', {}):
        raise CicloBloqueado(f'{nombre}: no está en la instantánea')
    base = Path(instantanea['ruta']) / 'datos' / nombre
    # Una fuente de un fichero se entrega como fichero; una carpeta, como carpeta.
    if instantanea.get('tipos', {}).get(nombre) == 'fichero':
        return base / next(iter(instantanea['archivos'][nombre]))
    return base


# --------------------------------------------------------------------------- T2: vistas por familia

@dataclass(frozen=True)
class Muestra:
    """050:RF-2: una muestra de una familia, atada a la instantánea y a su observación."""

    observacion_id: str
    familia: str
    snapshot_id: str
    origen: str
    etiqueta: str
    particion: str
    contexto: str = ''
    record_id: str = ''

    def __post_init__(self):
        if self.familia not in ORDEN_MODELOS:
            raise ValueError(f'familia desconocida: {self.familia}')
        if self.origen not in ORIGENES:
            raise ValueError(f'origen desconocido: {self.origen}')
        if self.etiqueta not in ETIQUETAS:
            raise ValueError(f'etiqueta desconocida: {self.etiqueta}')
        if self.particion not in ('entrenamiento', 'seleccion', 'calibracion', 'prueba'):
            raise ValueError(f'partición desconocida: {self.particion}')
        if not self.observacion_id or not _HEX.fullmatch(self.snapshot_id):
            raise ValueError('muestra sin observación o sin instantánea')
        if not self.record_id:
            object.__setattr__(self, 'record_id', _huella([self.familia, self.observacion_id, self.particion]))


def _cuarentena(m: Muestra) -> str | None:
    if m.familia in FAMILIAS_FISICAS and m.etiqueta not in ETIQUETAS_FISICAS:
        # 050:RF-3: una tensión que dio el LLM, o el propio gemelo, no es lo que midió DIgSILENT.
        return f'{m.familia}: etiqueta «{m.etiqueta}» no es verdad eléctrica'
    if m.familia in FAMILIAS_FISICAS and m.origen == 'redactado':
        return f'{m.familia}: un dato redactado no es una observación eléctrica'
    if m.etiqueta == 'prediccion':
        return 'la predicción de un modelo no es etiqueta verdadera'
    return None


def preparar_vistas(instantanea: Mapping[str, Any], muestras: Iterable[Muestra], *,
                    historicas: Iterable[Muestra] = ()) -> dict[str, Any]:
    """050:RF-2, RF-3, RF-6: una vista por familia sobre la misma instantánea y las mismas particiones.

    La partición es de la observación, no de la familia: si el episodio X es prueba de la PINN y
    entrenamiento del LLM, el ciclo conjunto se evalúa sobre algo que una de sus partes ya vio.
    El replay solo añade al entrenamiento lo que ya fue entrenamiento: una prueba antigua nunca
    elige hiperparámetros del candidato nuevo.
    """
    sid = instantanea.get('snapshot_id')
    if not isinstance(sid, str) or not instantanea.get('verificada'):
        raise CicloBloqueado('la preparación necesita una instantánea verificada')
    vistas: dict[str, dict[str, list[Muestra]]] = {}
    cuarentena, particion_de, vistos = [], {}, {}
    duplicadas = 0

    def validar_contexto(m):
        if 'contextos' in instantanea and m.contexto not in instantanea['contextos'].values():
            raise CicloBloqueado(f'{m.observacion_id}: contexto no declarado en el ciclo')

    def repetida(m, *, historica=False):
        clave = (m.familia, m.record_id)
        previa = vistos.get(clave)
        comparable = replace(m, snapshot_id=previa.snapshot_id) if previa is not None and historica else m
        if previa is not None and previa != comparable:
            raise CicloBloqueado(f'{m.record_id}: colisión de identidad de registro')
        if previa is None:
            vistos[clave] = m
        return previa is not None

    for m in muestras:
        if m.snapshot_id != sid:
            raise CicloBloqueado(f'{m.observacion_id}: muestra de otra instantánea')
        validar_contexto(m)
        previa = particion_de.setdefault(m.observacion_id, m.particion)
        if previa != m.particion:
            raise CicloBloqueado(f'{m.observacion_id}: partición distinta entre familias (fuga)')
        if repetida(m):
            duplicadas += 1
            continue
        motivo = _cuarentena(m)
        if motivo:
            cuarentena.append({'observacion_id': m.observacion_id, 'familia': m.familia, 'motivo': motivo})
            continue
        vistas.setdefault(m.familia, {}).setdefault(m.particion, []).append(m)
    replay = 0
    for h in historicas:
        if (h.observacion_id in particion_de and particion_de[h.observacion_id] != 'entrenamiento'
                and h.particion == 'entrenamiento'):
            raise CicloBloqueado(f'{h.observacion_id}: el replay metería en entrenamiento una prueba vigente')
        if h.particion != 'entrenamiento' or _cuarentena(h):
            continue
        validar_contexto(h)
        # Un registro vigente prevalece sobre su copia histórica de otra instantánea.
        if repetida(h, historica=True):
            duplicadas += 1
            continue
        particion_de[h.observacion_id] = h.particion
        vistas.setdefault(h.familia, {}).setdefault('entrenamiento', []).append(h)
        replay += 1
    resumen = {f: {p: len(v) for p, v in partes.items()} for f, partes in sorted(vistas.items())}
    return {'snapshot_id': sid, 'vistas': vistas, 'resumen': resumen, 'cuarentena': cuarentena,
            'replay': replay, 'duplicadas': duplicadas, 'particiones_hash': _huella(sorted(particion_de.items()))}


def validar_propuestas(propuestas: Iterable[Mapping[str, Any]]) -> dict[str, list[dict]]:
    """050:RF-9: un escenario o anotación que propone el propio sistema entra solo con contraste ajeno.

    Lo rechazado no se borra: muestra qué pidió el sistema y por qué no se aceptó.
    """
    aceptadas, rechazadas = [], []
    for p in propuestas:
        motivos = []
        if not p.get('procedencia'):
            motivos.append('sin procedencia')
        contraste = p.get('contraste') or {}
        if contraste.get('fuente') not in ETIQUETAS_FISICAS + ('operador',):
            motivos.append('sin contraste independiente')
        elif contraste.get('fuente') == p.get('autor'):
            motivos.append('el contraste es del mismo autor')
        if p.get('etiqueta') == 'prediccion' or p.get('recompensa_de') == p.get('autor'):
            motivos.append('usa su propia predicción como etiqueta o recompensa')
        if p.get('consistente') is not True:
            motivos.append('consistencia no comprobada')
        (rechazadas if motivos else aceptadas).append({**p, 'motivos': motivos})
    return {'aceptadas': aceptadas, 'rechazadas': rechazadas}


# --------------------------------------------------------------------------- T3: ciclo único

@dataclass(frozen=True)
class Presupuesto:
    """050:RF-4: lo que un ciclo puede gastar; sin declararlo no arranca."""

    tiempo_s: float
    memoria_gib: float
    usa_gpu: bool
    usa_licencia_nativa: bool = False

    def __post_init__(self):
        for nombre in ('tiempo_s', 'memoria_gib'):
            v = getattr(self, nombre)
            if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
                raise ValueError(f'presupuesto: {nombre} debe ser positivo')


def clave_ciclo(snapshot_id: str, familias: Sequence[str], politica_hash: str) -> str:
    """Idempotencia: la misma instantánea con las mismas familias y política es el mismo ciclo."""
    return _huella({'schema': ESQUEMA_CICLO, 'snapshot_id': snapshot_id,
                    'familias': sorted(familias), 'politica_hash': politica_hash})


def decidir_ciclo(*, datos_nuevos: int, deriva: bool, minimo: int, ultimo_snapshot: str | None,
                  snapshot_actual: str | None) -> dict[str, Any]:
    """050:RF-4: toca un ciclo con datos nuevos válidos (umbral 027) o con deriva; no por reloj."""
    if snapshot_actual is not None and snapshot_actual == ultimo_snapshot:
        return {'toca': False, 'motivo': 'la instantánea ya tuvo su ciclo'}
    if deriva:
        return {'toca': True, 'motivo': 'deriva detectada'}
    if datos_nuevos >= minimo:
        return {'toca': True, 'motivo': f'{datos_nuevos} datos nuevos válidos (mínimo {minimo})'}
    return {'toca': False, 'motivo': f'{datos_nuevos} datos nuevos, menos del mínimo {minimo}'}


def _activos(registro: RegistroModelo, familias: Iterable[str]) -> dict[str, str | None]:
    from .model_registry import registros_de
    salida = {}
    for f in familias:
        for nombre in registros_de(f):
            try:
                a = registro.activo(nombre)
            except ValueError:
                a = {'candidate_id': 'ilegible'}
            salida[nombre] = (a or {}).get('candidate_id')
    return salida


def ejecutar_ciclo(raiz: Path | str, instantanea: Mapping[str, Any], etapas: Sequence[TrainingStage], *,
                   politica_hash: str, presupuesto: Presupuesto, registro: RegistroModelo,
                   operador_ocupado: Callable[[], bool] = lambda: False,
                   memoria_libre_gib: Callable[[], float] | None = None,
                   reloj: Callable[[], float] = time.monotonic,
                   liberar_ollama: Callable[[], Any] = lambda: None) -> dict[str, Any]:
    """050:RF-4, RF-5, RF-8: un solo ciclo por instantánea, presupuestado, cancelable y sin promociones sueltas.

    Reutiliza el ``TrainingCoordinator`` (orden, guardia GPU, reanudación). Las etapas reciben ya
    construidas sobre las copias de la instantánea; aquí se comprueba que ninguna cambió por su
    cuenta el modelo en uso, porque el conjunto se publica entero o no se publica.
    """
    raiz = Path(raiz)
    instantanea = verificar_instantanea(instantanea['ruta'])
    familias = [e.name for e in etapas]
    clave = clave_ciclo(instantanea['snapshot_id'], familias, politica_hash)
    carpeta = raiz / 'ciclos' / clave
    ruta = carpeta / 'ciclo.json'
    if ruta.is_file():
        previo = _leer(ruta)
        if previo.get('estado') in ('terminado', 'bloqueado', 'cancelado'):
            return {**previo, 'repetido': True}
    marca = carpeta / 'en_curso'
    if marca.exists():
        try:
            pid = int(marca.read_text(encoding='utf-8').strip() or 0)
        except (OSError, ValueError):
            pid = -1
        if pid < 0 or pid_vivo(pid):
            return {'clave': clave, 'estado': 'en_curso', 'repetido': True}
        # El proceso murió a mitad: se retoma con la reanudación del coordinador, no se empieza otro.
        marca.unlink(missing_ok=True)
    base = {'schema': ESQUEMA_CICLO, 'clave': clave, 'snapshot_id': instantanea['snapshot_id'],
            'contexto_hash': instantanea['contexto_hash'], 'familias': familias,
            'politica_hash': politica_hash, 'presupuesto': vars(presupuesto), 'inicio': _ahora()}

    def cerrar(estado: str, motivos: Sequence[str], **extra) -> dict[str, Any]:
        fila = {**base, 'estado': estado, 'motivos': list(motivos), 'fin': _ahora(), **extra}
        _escribir(ruta, fila)
        (carpeta / 'en_curso').unlink(missing_ok=True)
        if estado == 'bloqueado':
            registrar_bloqueo(raiz, 'ciclo', motivos, clave=clave)
        return fila

    carpeta.mkdir(parents=True, exist_ok=True)
    if operador_ocupado():
        # La prioridad es del operador: el ciclo espera, no se registra como hecho ni como fallido.
        return {**base, 'estado': 'pospuesto', 'motivos': ['el operador tiene trabajos en la cola']}
    if presupuesto.usa_licencia_nativa:
        return cerrar('bloqueado', ['el ciclo no toma la licencia nativa: la validación nativa va por el turno de 019'])
    if memoria_libre_gib is not None and memoria_libre_gib() < presupuesto.memoria_gib:
        return cerrar('bloqueado', [f'memoria libre bajo el presupuesto de {presupuesto.memoria_gib} GiB'])
    if not presupuesto.usa_gpu and any(e.uses_gpu for e in etapas):
        return cerrar('bloqueado', ['el presupuesto no admite GPU y hay etapas que la piden'])
    (carpeta / 'en_curso').write_text(str(os.getpid()), encoding='utf-8')
    antes = _activos(registro, familias)
    inicio = reloj()
    cancelar = carpeta / 'cancelar'

    def vigilada(etapa: TrainingStage) -> TrainingStage:
        def run():
            if cancelar.exists():
                raise ValueError('cancelado por el operador')
            if reloj() - inicio > presupuesto.tiempo_s:
                raise ValueError(f'presupuesto de tiempo agotado ({presupuesto.tiempo_s} s)')
            return etapa.run()
        return TrainingStage(etapa.name, run, uses_gpu=etapa.uses_gpu)

    try:
        informe = TrainingCoordinator([vigilada(e) for e in etapas], carpeta / 'coordinador',
                                      config_hash=clave, liberar_ollama=liberar_ollama).run(resume=True)
    except Exception as exc:  # frontera: el ciclo no se da por empezado si el coordinador no arranca
        return cerrar('bloqueado', [f'coordinador: {exc}'])
    despues = _activos(registro, familias)
    sueltas = sorted(n for n in despues if despues[n] != antes.get(n))
    etapas_inf = informe.get('stages') or []
    if cancelar.exists():
        return cerrar('cancelado', ['cancelado por el operador'], etapas=etapas_inf)
    motivos = []
    if sueltas:
        motivos.append(f'promoción individual durante el ciclo: {sueltas}')
    sin_informe = [e['model'] for e in etapas_inf if e.get('status') in (
        EstadoModelo.ERROR_ENTORNO.value, EstadoModelo.BLOQUEADO_POR_DATOS.value)]
    if sin_informe:
        motivos += [f"{e['model']}: {e.get('reason', '')}" for e in etapas_inf if e['model'] in sin_informe]
    candidatos = {e['model']: e.get('candidate_id') for e in etapas_inf if e.get('candidate_id')}
    faltan = [f for f in familias if f not in candidatos and f not in sin_informe]
    if faltan:
        motivos.append(f'etapas sin candidato en el registro: {faltan}')
    if motivos:
        return cerrar('bloqueado', motivos, etapas=etapas_inf, candidatos=candidatos, activos_antes=antes)
    return cerrar('terminado', [], etapas=etapas_inf, candidatos=candidatos, activos_antes=antes)


def cancelar_ciclo(raiz: Path | str, clave: str) -> bool:
    """050:RF-4: el operador corta el ciclo; la etapa en curso termina y no empieza la siguiente."""
    carpeta = Path(raiz) / 'ciclos' / clave
    if not (carpeta / 'en_curso').exists():
        return False
    (carpeta / 'cancelar').write_text(_ahora(), encoding='utf-8')
    return True


def registrar_aportes(propuesta_id: str, aportes: Mapping[str, Mapping[str, Any]],
                      conjunto: Mapping[str, Any]) -> dict[str, Any]:
    """050:RF-5: de qué versión salió cada parte de una propuesta conjunta.

    Un aporte cita la familia y el candidato del conjunto activo; uno de otro conjunto no cuenta.
    La validación nativa la da DIgSILENT, no un modelo: se cita su evidencia, no un candidato.
    """
    miembros = conjunto.get('miembros') or {}
    fichas, faltan = {}, []
    for clave in APORTES:
        a = aportes.get(clave)
        if not a:
            faltan.append(clave)
            continue
        if clave == 'validacion_nativa':
            if not a.get('evidencia'):
                faltan.append(clave)
                continue
            fichas[clave] = {'evidencia': a['evidencia']}
            continue
        familia, cid = a.get('familia'), a.get('candidate_id')
        if miembros.get(familia) != cid:
            raise CicloBloqueado(f'{clave}: {familia}/{cid} no es del conjunto {conjunto.get("conjunto_id")}')
        fichas[clave] = {'familia': familia, 'candidate_id': cid}
    return {'propuesta_id': propuesta_id, 'conjunto_id': conjunto.get('conjunto_id'), 'aportes': fichas,
            'faltan': faltan, 'completa': not faltan}


# --------------------------------------------------------------------------- T4: retención y conjunto

def evaluar_retencion(candidato: Mapping[str, Mapping[str, float]], vigente: Mapping[str, Mapping[str, float]],
                      *, metricas: Mapping[str, str], tolerancia: float = 0.0) -> dict[str, Any]:
    """050:RF-6: por contexto, el candidato no olvida lo que el vigente ya hacía bien.

    ``candidato`` y ``vigente`` dan, por contexto histórico, sus métricas sobre los mismos ejemplos.
    ``metricas`` dice si cada una se quiere ``alta`` o ``baja``. Un contexto o una métrica ausente
    no se da por retenido.
    """
    if tolerancia < 0 or not math.isfinite(tolerancia):
        raise ValueError('tolerancia inválida')
    fallos = []
    for ctx in sorted(set(vigente) | set(candidato)):
        c, v = candidato.get(ctx), vigente.get(ctx)
        if c is None or v is None:
            fallos.append(f'{ctx}: sin medida del candidato o del vigente')
            continue
        for nombre, sentido in metricas.items():
            a, b = c.get(nombre), v.get(nombre)
            if not all(type(x) in (int, float) and math.isfinite(x) for x in (a, b)):
                fallos.append(f'{ctx}: {nombre} ausente o no finita')
            elif (sentido == 'alta' and a < b - tolerancia) or (sentido == 'baja' and a > b + tolerancia):
                fallos.append(f'{ctx}: {nombre} retrocede ({b:.4g} → {a:.4g})')
    if not vigente:
        fallos.append('sin contextos históricos con que medir la retención')
    return {'retiene': not fallos, 'fallos': fallos}


def evaluar_conjunto(candidato: Mapping[str, float], vigente: Mapping[str, float] | None, *,
                     metricas: Mapping[str, str]) -> dict[str, Any]:
    """050:RF-7: sobre la evidencia reservada común, el conjunto nuevo tiene que mejorar algo y no empeorar nada.

    Un empate no acredita mejora: con el mismo resultado se queda el conjunto en uso.
    """
    fallos, mejoras = [], []
    for nombre, sentido in metricas.items():
        a = candidato.get(nombre)
        if type(a) not in (int, float) or not math.isfinite(a):
            fallos.append(f'{nombre}: ausente o no finita en el candidato')
            continue
        if vigente is None:
            continue
        b = vigente.get(nombre)
        if type(b) not in (int, float) or not math.isfinite(b):
            fallos.append(f'{nombre}: el conjunto vigente no tiene medida comparable')
        elif (a < b) if sentido == 'alta' else (a > b):
            fallos.append(f'{nombre}: empeora ({b:.4g} → {a:.4g})')
        elif a != b:
            mejoras.append(nombre)
    if vigente is not None and not fallos and not mejoras:
        fallos.append('empate: el conjunto nuevo no mejora al vigente')
    return {'aprobado': not fallos, 'fallos': fallos, 'mejoras': mejoras}


def _puntero(raiz: Path, nombre: str) -> dict[str, Any] | None:
    ruta = raiz / 'conjuntos' / nombre
    return _leer(ruta) if ruta.is_file() else None


def conjunto_activo(raiz: Path | str) -> dict[str, Any] | None:
    """El conjunto en uso, releído y con su contenido verificado."""
    raiz = Path(raiz)
    puntero = _puntero(raiz, 'activo.json')
    if puntero is None:
        return None
    dato = _leer(raiz / 'conjuntos' / f"{puntero['conjunto_id']}.json")
    if _huella({k: dato[k] for k in ('miembros', 'snapshot_id', 'ciclo')}) != puntero['conjunto_id']:
        raise CicloBloqueado('conjunto activo modificado')
    return dato


def publicar_conjunto(raiz: Path | str, registro: RegistroModelo, ciclo: Mapping[str, Any], *,
                      retencion: Mapping[str, Mapping[str, Any]], conjunta: Mapping[str, Any],
                      obligatorias: Iterable[str]) -> dict[str, Any]:
    """050:RF-7, RF-8: el conjunto se publica entero, con cada miembro aprobado y reabierto, o no se publica.

    El puntero cambia de una vez y el anterior queda para volver. Los consumidores resuelven su
    versión con ``version_del_conjunto``, no con el último candidato de cada familia.
    """
    raiz = Path(raiz)
    motivos = []
    if ciclo.get('estado') != 'terminado':
        motivos.append(f"el ciclo está {ciclo.get('estado')}, no terminado")
    candidatos = dict(ciclo.get('candidatos') or {})
    for familia in sorted(set(obligatorias)):
        cid = candidatos.get(familia)
        if not cid:
            motivos.append(f'{familia}: sin candidato')
            continue
        try:
            detalle = registro.detalle(familia, cid)
        except ValueError as exc:
            motivos.append(f'{familia}: {exc}')
            continue
        if (detalle['decision'].get('gates') or {}).get('approved') is not True:
            motivos.append(f'{familia}: no pasó sus puertas individuales')
        if detalle['smoke_reload'].get('ok') is not True:
            motivos.append(f'{familia}: no se reabrió')
        if (retencion.get(familia) or {}).get('retiene') is not True:
            motivos.append(f'{familia}: no demuestra retención')
    if conjunta.get('aprobado') is not True:
        motivos += [f'conjunto: {f}' for f in conjunta.get('fallos') or ['evaluación conjunta no aprobada']]
    if motivos:
        registrar_bloqueo(raiz, 'publicacion', motivos, ciclo=ciclo.get('clave'))
        return {'publicado': False, 'motivos': motivos, 'activo': conjunto_activo(raiz)}
    miembros = {f: candidatos[f] for f in sorted(set(obligatorias))}
    cuerpo = {'miembros': miembros, 'snapshot_id': ciclo['snapshot_id'], 'ciclo': ciclo['clave']}
    cid = _huella(cuerpo)
    dato = {'schema': ESQUEMA_CONJUNTO, 'conjunto_id': cid, **cuerpo, 'retencion': dict(retencion),
            'conjunta': dict(conjunta), 'publicado': _ahora()}
    _escribir(raiz / 'conjuntos' / f'{cid}.json', dato)
    anterior = _puntero(raiz, 'activo.json')
    if anterior is not None and anterior['conjunto_id'] != cid:
        _escribir(raiz / 'conjuntos' / 'anterior.json', anterior)
    _escribir(raiz / 'conjuntos' / 'activo.json', {'conjunto_id': cid})
    leido = conjunto_activo(raiz)
    if leido is None or leido['conjunto_id'] != cid:
        raise CicloBloqueado('la relectura no devuelve el conjunto publicado')
    return {'publicado': True, 'conjunto': leido, 'anterior': (anterior or {}).get('conjunto_id')}


def revertir_conjunto(raiz: Path | str) -> dict[str, Any]:
    """050:RF-7: vuelta al conjunto anterior, comprobada por relectura."""
    raiz = Path(raiz)
    anterior, activo = _puntero(raiz, 'anterior.json'), _puntero(raiz, 'activo.json')
    if anterior is None:
        raise CicloBloqueado('no hay conjunto anterior al que volver')
    _escribir(raiz / 'conjuntos' / 'activo.json', anterior)
    if activo is not None:
        _escribir(raiz / 'conjuntos' / 'anterior.json', activo)
    leido = conjunto_activo(raiz)
    if leido is None or leido['conjunto_id'] != anterior['conjunto_id']:
        raise CicloBloqueado('la relectura no devuelve el conjunto anterior')
    return leido


def version_del_conjunto(raiz: Path | str, familia: str) -> str | None:
    """La versión que un consumidor usa de una familia: la del conjunto activo, no la última suelta."""
    activo = conjunto_activo(raiz)
    return None if activo is None else activo['miembros'].get(familia)


# --------------------------------------------------------------------------- T5: estado visible

def estado_aprendizaje(raiz: Path | str) -> dict[str, Any]:
    """050:RF-10: cada fase con su estado y motivo reales; nada se da por hecho sin su fichero."""
    raiz = Path(raiz)
    ciclos = []
    for ruta in sorted((raiz / 'ciclos').glob('*/ciclo.json')) if (raiz / 'ciclos').is_dir() else ():
        try:
            ciclos.append(_leer(ruta))
        except (OSError, ValueError):
            ciclos.append({'clave': ruta.parent.name, 'estado': 'ilegible'})
    ciclos.sort(key=lambda c: str(c.get('fin') or c.get('inicio') or ''))
    ultimo = ciclos[-1] if ciclos else None
    try:
        activo = conjunto_activo(raiz)
    except (OSError, ValueError) as exc:
        activo = {'error': str(exc)}
    bloqueos = []
    if (raiz / 'bloqueos.jsonl').is_file():
        bloqueos = [json.loads(l) for l in (raiz / 'bloqueos.jsonl').read_text(encoding='utf-8').splitlines()
                    if l.strip()][-5:]
    fases = {f: {'estado': 'pendiente', 'motivo': ''} for f in FASES}
    if ultimo:
        fases['preparacion'] = {'estado': 'hecho', 'motivo': f"instantánea {ultimo['snapshot_id'][:12]}"}
        etapas = ultimo.get('etapas') or []
        entrenadas = [e['model'] for e in etapas if e.get('training_completed') is True]
        fases['entrenamiento'] = {
            'estado': {'terminado': 'hecho', 'en_curso': 'en_curso'}.get(ultimo['estado'], ultimo['estado']),
            'motivo': '; '.join(ultimo.get('motivos') or ()) or f'entrenadas: {entrenadas}',
            'versiones': ultimo.get('candidatos') or {}}
        if ultimo['estado'] == 'terminado':
            fases['seleccion'] = {'estado': 'hecho', 'motivo': 'candidatos con decisión en el registro',
                                  'versiones': ultimo.get('candidatos') or {}}
    if isinstance(activo, dict) and activo.get('conjunto_id'):
        hecho_aqui = ultimo is not None and activo.get('ciclo') == ultimo.get('clave')
        for f in ('evaluacion', 'publicacion', 'activacion'):
            fases[f] = {'estado': 'hecho' if hecho_aqui else 'anterior',
                        'motivo': f"conjunto {activo['conjunto_id'][:12]}", 'versiones': activo.get('miembros')}
    ultimo_bloqueo = bloqueos[-1] if bloqueos else None
    if ultimo_bloqueo and ultimo_bloqueo.get('etapa') == 'publicacion' and (
            ultimo is None or ultimo_bloqueo.get('ciclo') == ultimo.get('clave')):
        fases['evaluacion'] = {'estado': 'rechazado', 'motivo': '; '.join(ultimo_bloqueo['motivos'])}
    # La aceptación nativa la da DIgSILENT por el turno de 019: aquí solo se dice si consta.
    nativa = (activo or {}).get('aceptacion_nativa') if isinstance(activo, dict) else None
    fases['aceptacion_nativa'] = ({'estado': 'hecho', 'motivo': str(nativa)} if nativa else
                                  {'estado': 'pendiente', 'motivo': 'sin validación en DIgSILENT del conjunto'})
    return {'fases': fases, 'ultimo_ciclo': ultimo, 'conjunto_activo': activo, 'bloqueos': bloqueos}
