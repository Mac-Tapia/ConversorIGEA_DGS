"""Reranker local por cross-encoder, solo si la evaluación sellada lo adoptó (047:RF-4, RF-27, RF-30).

Solo CUDA: en CPU, con 16 GB compartidos, el modelo grande dejaría sin memoria a la web y a los
entrenamientos. Sin GPU no se cae a CPU; se aparta y queda el orden sin reranker, dicho en la
respuesta. Se carga, puntúa y descarga en cada respuesta: la GPU de 8 GB la comparten Ollama y los
entrenamientos, y retenerlo ocuparía justo lo que el reentrenamiento necesita.
"""
from __future__ import annotations

import contextlib
import gc
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .indice import CORPUS_047, CORPUS_AMPLIADO, Abstencion, RerankerNoDisponible

_RAIZ = Path(__file__).resolve().parents[3]
CATALOGO = _RAIZ / 'docs' / 'MODELOS_IA_LOCK.json'
INFORME = _RAIZ / 'docs' / 'EVALUACION_RAG_047.json'
CONJUNTO = _RAIZ / 'docs' / 'RAG_PREGUNTAS_SINTETICAS_047.json'
CALIBRACION = _RAIZ / 'docs' / 'CALIBRACION_ABSTENCION_047.json'
CONJUNTO_CALIBRACION = _RAIZ / 'docs' / 'RAG_ABSTENCION_CALIBRACION_047.json'
#: Lo del corpus ampliado (spec 077): otros conjuntos, otros umbrales y otra medición.
CALIBRACION_077 = _RAIZ / 'docs' / 'CALIBRACION_ABSTENCION_077.json'
CONJUNTO_CALIBRACION_077 = _RAIZ / 'docs' / 'CONJUNTO_ABSTENCION_CALIBRACION_077.json'
CONJUNTO_SELLADO_077 = _RAIZ / 'docs' / 'CONJUNTO_ABSTENCION_SELLADO_077.json'
MEDICION_077 = _RAIZ / 'docs' / 'EVALUACION_ABSTENCION_077.json'
#: La puerta declarada en el plan de la 047 antes de medir; la 077 no la baja (077:RF-42).
ABSTENCION_MINIMA = 0.90
#: Candidatos de la evaluación, ambos con revisión fijada en el catálogo.
MODELOS = ('BAAI/bge-reranker-v2-m3', 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')
MAX_LARGO = 256
LOTE = 4


def sha256_de(ruta: Path) -> str:
    """El sello del conjunto, sin el final de línea: Git en Windows lo pasa a CRLF al sacarlo a otro
    worktree, y el mismo conjunto no puede dejar de valer por eso."""
    return hashlib.sha256(Path(ruta).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def ficha_modelo(modelo: str) -> dict[str, Any]:
    """La ficha del catálogo: revisión, licencia y huellas. Un modelo sin ficha no se carga."""
    catalogo = json.loads(CATALOGO.read_text(encoding='utf-8'))
    ficha = next((m for m in catalogo['modelos'] if m['id'] == modelo and m['backend'] == 'huggingface'), None)
    if ficha is None:
        raise ValueError(f'reranker no fijado en el catálogo: {modelo}')
    return ficha


class Puntuador:
    """El modelo cargado en la GPU: ``(consulta, textos) -> puntuaciones``."""

    def __init__(self, modelo: Any, torch: Any, lote: int = LOTE):
        self._modelo, self._torch, self._lote = modelo, torch, lote

    def __call__(self, consulta: str, textos: Sequence[str]) -> list[float]:
        try:
            puntos = self._modelo.predict([(consulta, t) for t in textos], batch_size=self._lote,
                                          show_progress_bar=False)
        except RuntimeError as exc:                                     # incluye la falta de memoria de CUDA
            raise RerankerNoDisponible(f'el reranker falló en CUDA: {exc}') from exc
        return [float(x) for x in puntos]

    def liberar(self) -> None:
        # El modelo guarda ciclos de referencias: sin recolectar, la Fase 2 mantuvo 2,3 GB de la GPU tras
        # descargar bge-reranker, y empty_cache no devuelve lo que aún tiene dueño.
        self._modelo = None
        gc.collect()
        self._torch.cuda.empty_cache()


def cargar_puntuador(modelo: str, revision: str) -> Puntuador:
    """Carga la revisión fijada, con sus huellas comprobadas, en CUDA y sin red; si no, dice por qué."""
    ficha = ficha_modelo(modelo)
    if revision != ficha['revision']:
        raise RerankerNoDisponible(f'la revisión de {modelo} no es la fijada en el catálogo')
    # Con local_files_only, CrossEncoder aún consultó el Hub en la Fase 2 (aviso de peticiones sin token).
    os.environ['HF_HUB_OFFLINE'] = '1'
    from ..training_coordinator import MemoriaMLInsuficiente, exigir_memoria_ml

    try:
        exigir_memoria_ml(1.0, minimo_commit_gib=4.0)
    except MemoriaMLInsuficiente as exc:
        raise RerankerNoDisponible(str(exc)) from exc
    try:
        import torch
    except ImportError as exc:
        raise RerankerNoDisponible('sin torch no hay CUDA para el reranker') from exc
    if not torch.cuda.is_available():
        raise RerankerNoDisponible('CUDA no disponible: el reranker no corre en CPU')
    from .embeddings import identidad_encoder

    try:
        identidad_encoder(modelo)                                       # pesos iguales al catálogo
        from sentence_transformers import CrossEncoder

        cargado = CrossEncoder(modelo, revision=revision, device='cuda', local_files_only=True, max_length=MAX_LARGO)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise RerankerNoDisponible(f'no se pudo cargar {modelo}: {exc}') from exc
    return Puntuador(cargado, torch)


class PuntuadorPerezoso:
    """Carga al primer uso y descarga al terminar: la medición pasa un modelo tras otro por la GPU."""

    def __init__(self, modelo: str, revision: str):
        self.modelo, self.revision, self._cargado = modelo, revision, None

    def __call__(self, consulta: str, textos: Sequence[str]) -> list[float]:
        if self._cargado is None:
            self._cargado = cargar_puntuador(self.modelo, self.revision)
        return self._cargado(consulta, textos)

    def liberar(self) -> None:
        if self._cargado is not None:
            self._cargado.liberar()
            self._cargado = None


def reordenar(consulta: str, candidatos: Sequence[Mapping], *, modelo: str, revision: str,
              puntuar: Callable[[str, Sequence[str]], Sequence[float]] | None = None) -> list[dict]:
    """Los mismos candidatos, con su id, fuente y fragmento intactos, por la puntuación del modelo."""
    propio = None
    if puntuar is None:
        puntuar = propio = cargar_puntuador(modelo, revision)
    try:
        puntos = list(puntuar(consulta, [str(c['texto']) for c in candidatos]))
    finally:
        if propio is not None:
            propio.liberar()
    if len(puntos) != len(candidatos):
        raise RerankerNoDisponible('el reranker no puntuó todos los candidatos')
    orden = sorted(range(len(candidatos)), key=lambda i: -puntos[i])     # estable: un empate no reordena
    return [{**candidatos[i], 'reranker': float(puntos[i])} for i in orden]


def politica(informe: Path = INFORME, conjunto: Path = CONJUNTO) -> dict[str, Any]:
    """Qué métodos autoriza la evaluación guardada (047:RF-27). Sin informe válido, ningún reranker."""
    apagado = {'hibrido': True, 'modelo': None, 'revision': None}
    if not informe.is_file() or not conjunto.is_file():
        return {**apagado, 'motivo': 'sin evaluación sellada'}
    try:
        datos = json.loads(informe.read_text(encoding='utf-8'))
        decision = datos['decision']
    except (ValueError, KeyError, TypeError):
        return {**apagado, 'motivo': 'informe de evaluación ilegible'}
    if datos.get('conjunto_sha256') != sha256_de(conjunto):
        return {**apagado, 'motivo': 'el conjunto sellado cambió desde la evaluación'}
    salida = {**apagado, 'hibrido': (decision.get('hibrido') or {}).get('adoptado') is True,
              'motivo': 'la evaluación no adoptó ningún reranker'}
    elegido = decision.get('reranker') or {}
    if elegido.get('adoptado') is True:
        try:
            fijada = ficha_modelo(str(elegido.get('modelo')))['revision']
        except ValueError:
            return {**salida, 'motivo': 'el modelo adoptado no está en el catálogo'}
        if elegido.get('revision') == fijada:
            return {**salida, 'modelo': elegido['modelo'], 'revision': fijada, 'motivo': ''}
        return {**salida, 'motivo': 'la revisión adoptada no es la del catálogo'}
    return salida


def abstencion(calibracion: Path = CALIBRACION, conjunto: Path = CONJUNTO_CALIBRACION) -> Abstencion:
    """Los umbrales guardados, solo si salen del conjunto de calibración de hoy (047:RF-33, RF-34).
    Sin ellos, una ``Abstencion`` sin calibrar: «No lo sé» antes que una cita que no apoya."""
    try:
        datos = json.loads(calibracion.read_text(encoding='utf-8'))
        if datos['conjunto_sha256'] != sha256_de(conjunto):
            return Abstencion()
        umbrales, modelo = datos['umbrales'], datos.get('modelo_reranker')
        valido = bool(modelo) and ficha_modelo(modelo)['revision'] == datos.get('revision')
    except (OSError, ValueError, KeyError, TypeError):
        return Abstencion()
    return Abstencion(calibrada=True, modelo_reranker=modelo if valido else None,
                      umbral_reranker=umbrales.get('reranker') if valido else None,
                      umbral_coseno=umbrales.get('coseno'), umbral_bm25=umbrales.get('bm25'),
                      umbral_bm25_solo=umbrales.get('bm25_solo'))


def _medicion_aprobada(medicion: Path, conjunto: Path) -> dict[str, Any] | None:
    """La medición del corpus ampliado, solo si es de su conjunto sellado y pasa la regla de la 047, la que aceptó el
    usuario el 2026-11-02: reranker con la puerta completa, e híbrido y BM25 con la abstención mínima (077:RF-47, RF-48)."""
    try:
        datos = json.loads(medicion.read_text(encoding='utf-8'))
        if datos['corpus'] != CORPUS_AMPLIADO or datos['conjunto_sha256'] != sha256_de(conjunto):
            return None
        if datos['puerta']['reranker']['cumple'] is not True:
            return None
        if any(float(datos['metodos'][m]['abstention_accuracy']) < ABSTENCION_MINIMA for m in ('hibrido', 'bm25')):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return datos


def servicio(medicion: Path | None = None, conjunto: Path | None = None, calibracion: Path | None = None,
             conjunto_calibracion: Path | None = None) -> dict[str, Any]:
    """Qué corpus, política y umbrales sirve la web. Sin una medición aprobada del corpus ampliado, los de la 047: seguir
    con sus umbrales sobre un índice mayor daría una abstención sin medir (077:RF-47)."""
    base = {'corpus': CORPUS_047, 'politica': politica(), 'abstencion': abstencion()}
    datos = _medicion_aprobada(medicion or MEDICION_077, conjunto or CONJUNTO_SELLADO_077)
    if datos is None:
        return base
    umbrales = abstencion(calibracion or CALIBRACION_077, conjunto_calibracion or CONJUNTO_CALIBRACION_077)
    if not umbrales.calibrada or umbrales.modelo_reranker != datos.get('modelo_reranker'):
        return base
    revision = ficha_modelo(umbrales.modelo_reranker)['revision']
    return {'corpus': CORPUS_AMPLIADO, 'abstencion': umbrales,
            'politica': {'hibrido': True, 'modelo': umbrales.modelo_reranker, 'revision': revision, 'motivo': ''}}


def reordenador_de(pol: Mapping[str, Any], turno: Callable[[], Any] = contextlib.nullcontext
                   ) -> Callable[[str, Sequence[Mapping]], list[dict]] | None:
    """La función que espera ``indice.responder``, o ``None`` si la política no adoptó ninguno.

    ``turno`` es la guardia de la GPU: si otro la tiene, salta y queda el orden sin reranker."""
    modelo, revision = pol.get('modelo'), pol.get('revision')
    if not modelo:
        return None

    def reordenador(consulta: str, candidatos: Sequence[Mapping]) -> list[dict]:
        try:
            with turno():
                return reordenar(consulta, candidatos, modelo=modelo, revision=revision)
        except RerankerNoDisponible:
            raise
        except (OSError, RuntimeError, ValueError) as exc:             # la guardia de la GPU: otro la tiene
            raise RerankerNoDisponible(f'GPU sin turno para el reranker: {exc}') from exc

    reordenador.etiqueta = f'reranker:{modelo}'
    return reordenador
