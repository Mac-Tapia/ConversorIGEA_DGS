"""Registro común inmutable y promoción atómica de cualquier modelo."""
from __future__ import annotations

from .runtime_paths import staging_publicacion

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Any, Sequence


class EstadoModelo(str, Enum):
    PROMOVIDO = 'PROMOVIDO'
    RECHAZADO = 'RECHAZADO'
    BLOQUEADO_POR_DATOS = 'BLOQUEADO_POR_DATOS'
    ERROR_ENTORNO = 'ERROR_ENTORNO'


#: 043:RF-8: el pronóstico se registra por clase (046) y se informa dentro de la etapa ``gru``;
#: sin este alias, una decisión real del registro quedaba como «sin evidencia» en la web.
_REGISTROS_DE_FAMILIA = {'gru': ('gru', 'pronostico_cabecera', 'pronostico_cliente', 'pronostico_escaladas')}


def registros_de(familia: str) -> tuple[str, ...]:
    """Los nombres del registro común en que anota sus candidatos una familia del coordinador."""
    return _REGISTROS_DE_FAMILIA.get(familia, (familia,))


def estado_heredado(raiz: Path) -> dict[str, Any] | None:
    """060:RF-7: inspección de metadatos heredados, sin cargar ni promover pesos."""
    puntero = raiz / 'promovido.json'
    if not puntero.is_file():
        return None
    dato = json.loads(puntero.read_text(encoding='utf-8'))
    version = dato.get('version')
    if not isinstance(version, str) or not version or (raiz / version).resolve().parent != raiz.resolve():
        raise ValueError('versión heredada inválida')
    carpeta = raiz / version
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    return {'version': version, 'aceptado_registro': False, 'puntero': str(puntero),
            'cfg': meta.get('cfg'), 'metricas': meta.get('metricas'),
            'mae_v': meta.get('mae_v'), 'particiones': meta.get('particiones'),
            'requiere_validacion_actual': True}


def _canonico(valor: Any) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), default=str, allow_nan=False).encode('utf-8')


def _sha_archivo(ruta: Path) -> str:
    with ruta.open('rb') as contenido:
        return hashlib.file_digest(contenido, 'sha256').hexdigest()


class RegistroModelo:
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz)

    def _modelo(self, modelo: str) -> Path:
        if not isinstance(modelo, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', modelo):
            raise ValueError('identidad de modelo inválida')
        return self.raiz / modelo

    def _reemplazar_json(self, ruta: Path, payload: dict[str, Any]) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with staging_publicacion(ruta) as tmp:
            tmp.write_bytes(_canonico(payload))
            # Windows puede abrir brevemente el mismo puntero desde otro hilo.
            for intento in range(20):
                try:
                    os.replace(tmp, ruta)
                    break
                except PermissionError:
                    if intento == 19:
                        raise
                    time.sleep(0.01)

    def registrar_candidato(self, modelo: str, *, model_manifest: dict, dataset_manifest: dict,
                            metrics: dict, decision: dict, smoke_reload: dict,
                            artifacts: Sequence[Path | str] = ()) -> dict[str, Any]:
        modelo_raiz = self._modelo(modelo)
        try:
            estado = EstadoModelo(decision['status'])
        except (KeyError, ValueError) as exc:
            raise ValueError('estado terminal desconocido') from exc
        if estado == EstadoModelo.PROMOVIDO and not (
                (decision.get('gates') or {}).get('approved') is True and smoke_reload.get('ok') is True):
            raise ValueError('PROMOVIDO requiere puertas y reapertura exitosas')
        hashes = {}
        for artefacto in artifacts:
            ruta = Path(artefacto)
            if not ruta.is_file():
                raise ValueError(f'artefacto ausente: {ruta}')
            if ruta.name in hashes:
                raise ValueError(f'artefacto duplicado: {ruta.name}')
            hashes[ruta.name] = _sha_archivo(ruta)
        identidad = hashlib.sha256(_canonico({
            'model': modelo, 'model_manifest': model_manifest,
            'dataset_manifest': dataset_manifest, 'metrics': metrics,
            'decision': decision, 'smoke_reload': smoke_reload, 'artifacts': hashes})).hexdigest()
        final = modelo_raiz / 'candidates' / identidad
        if not final.exists():
            final.parent.mkdir(parents=True, exist_ok=True)
            with staging_publicacion(final) as temporal:
                temporal.mkdir()
                for nombre, payload in (
                    ('model_manifest.json', model_manifest), ('dataset_manifest.json', dataset_manifest),
                    ('metrics.json', metrics), ('decision.json', decision),
                    ('smoke_reload.json', smoke_reload), ('artifacts.json', hashes)):
                    (temporal / nombre).write_bytes(_canonico(payload))
                carpeta = temporal / 'artifacts'
                carpeta.mkdir()
                for artefacto in artifacts:
                    shutil.copy2(artefacto, carpeta / Path(artefacto).name)
                os.replace(temporal, final)
        self._reemplazar_json(modelo_raiz / 'latest.json', {'candidate_id': identidad, 'status': estado.value})
        return {'candidate_id': identidad, 'model': modelo, 'status': estado.value,
                'path': str(final)}

    def _candidato(self, modelo: str, candidate_id: str) -> tuple[Path, dict, dict]:
        detalle = self.detalle(modelo, candidate_id)
        return Path(detalle['path']), detalle['decision'], detalle['smoke_reload']

    def detalle(self, modelo: str, candidate_id: str, *, verificar_artefactos: bool = True) -> dict[str, Any]:
        if not isinstance(candidate_id, str) or not re.fullmatch(r'[0-9a-f]{64}', candidate_id):
            raise ValueError('identidad de candidato inválida')
        raiz = self._modelo(modelo) / 'candidates' / candidate_id
        if not raiz.is_dir():
            raise ValueError('candidato inexistente')
        datos = {nombre: json.loads((raiz / f'{nombre}.json').read_text(encoding='utf-8'))
                 for nombre in ('model_manifest', 'dataset_manifest', 'metrics', 'decision', 'smoke_reload', 'artifacts')}
        if any(not isinstance(valor, dict) for valor in datos.values()):
            raise ValueError('integridad: manifiesto de candidato no es un objeto')
        for nombre, esperado in datos['artifacts'].items():
            if Path(nombre).name != nombre or '/' in nombre or '\\' in nombre:
                raise ValueError('integridad: nombre de artefacto inválido')
            ruta = raiz / 'artifacts' / nombre
            if not ruta.is_file() or (verificar_artefactos and _sha_archivo(ruta) != esperado):
                raise ValueError(f'integridad: artefacto modificado o ausente: {nombre}')
        if hashlib.sha256(_canonico({'model': modelo, **datos})).hexdigest() != candidate_id:
            raise ValueError('integridad: manifiesto de candidato modificado')
        return {'path': str(raiz), **datos}

    def promover(self, modelo: str, candidate_id: str) -> dict[str, Any]:
        _raiz, decision, smoke = self._candidato(modelo, candidate_id)
        if decision.get('status') != EstadoModelo.PROMOVIDO.value \
                or (decision.get('gates') or {}).get('approved') is not True or smoke.get('ok') is not True:
            raise ValueError('candidato no aprobado o no reabierto')
        activo_ruta = self._modelo(modelo) / 'active.json'
        anterior = self.activo(modelo)
        payload = {'candidate_id': candidate_id, 'status': EstadoModelo.PROMOVIDO.value}
        # Repetir la promoción del activo no borra el anterior al que se puede volver.
        if anterior is not None and anterior.get('candidate_id') != candidate_id:
            self._reemplazar_json(self.raiz / modelo / 'previous.json', anterior)
        self._reemplazar_json(activo_ruta, payload)
        return payload

    def activo(self, modelo: str) -> dict[str, Any] | None:
        ruta = self._modelo(modelo) / 'active.json'
        if not ruta.is_file():
            return None
        payload = json.loads(ruta.read_text(encoding='utf-8'))
        if not isinstance(payload, dict) or not isinstance(payload.get('candidate_id'), str):
            raise ValueError('puntero activo inválido')
        return payload

    def volver_al_anterior(self, modelo: str) -> dict[str, Any]:
        ruta = self._modelo(modelo) / 'previous.json'
        if not ruta.is_file():
            raise ValueError('no existe modelo anterior')
        payload = json.loads(ruta.read_text(encoding='utf-8'))
        _raiz, decision, smoke = self._candidato(modelo, payload['candidate_id'])
        if (decision.get('status') != EstadoModelo.PROMOVIDO.value
                or (decision.get('gates') or {}).get('approved') is not True or smoke.get('ok') is not True):
            raise ValueError('modelo anterior no aprobado o no reabierto')
        self._reemplazar_json(self.raiz / modelo / 'active.json', payload)
        return payload

    def retirar_activo(self, modelo: str) -> None:
        """Deja el registro sin activo cuando se vuelve a un modelo heredado, que no está en él (067:RF-23);
        el retirado queda como anterior."""
        activo = self.activo(modelo)
        if activo is None:
            return
        self._reemplazar_json(self._modelo(modelo) / 'previous.json', activo)
        (self._modelo(modelo) / 'active.json').unlink()

    def validar_uso_provisional(self, modelo: str, candidate_id: str) -> dict[str, Any]:
        """El detalle íntegro de un candidato rechazado y reabierto, el único que se puede usar sin aprobar (085:RF-27).

        Uno aprobado entra por ``promover``; uno que no reabrió no cargaría, y uno sin datos no se midió."""
        detalle = self.detalle(modelo, candidate_id)
        if detalle['decision'].get('status') != EstadoModelo.RECHAZADO.value:
            raise ValueError(f"el uso provisional es de un candidato rechazado; este está en {detalle['decision'].get('status')}")
        if detalle['smoke_reload'].get('ok') is not True:
            raise ValueError('el candidato no reabrió en un proceso nuevo: no se puede poner en uso')
        return detalle

    def anotar_uso_provisional(self, modelo: str, candidate_id: str, *, version: str, decidido_por: str, motivo: str,
                               fecha: str, cifras: dict, anterior: str | None) -> dict[str, Any]:
        """Anota la decisión del usuario junto al candidato, sin tocar su decisión ni ``active.json`` (085:RF-26, RF-28).

        La decisión de las puertas entra en la identidad del candidato: reescribirla como aprobada daría otro
        candidato, y es justo lo que el usuario no pidió. Esto es otra cosa, y queda aparte, con su autor."""
        if not str(decidido_por).strip() or not str(motivo).strip() or not str(fecha).strip():
            raise ValueError('una puesta en uso provisional necesita quién la decide, cuándo y su motivo')
        self.validar_uso_provisional(modelo, candidate_id)
        fila = {'decision': 'uso_provisional', 'candidate_id': candidate_id, 'version': version,
                'decidido_por': str(decidido_por).strip(), 'motivo': str(motivo).strip(), 'fecha': str(fecha).strip(),
                'cifras': cifras, 'modelo_anterior': anterior, 'puertas_aprobadas': False,
                'confirmacion_obligatoria': True}
        ruta = self._modelo(modelo) / 'usos_provisionales.jsonl'
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open('a', encoding='utf-8') as f:
            f.write(json.dumps(fila, ensure_ascii=False, allow_nan=False) + '\n')
        return fila

    def uso_provisional(self, modelo: str, candidate_id: str) -> dict[str, Any] | None:
        """La última decisión de uso provisional de ese candidato (085:RF-26)."""
        ruta = self._modelo(modelo) / 'usos_provisionales.jsonl'
        if not ruta.is_file():
            return None
        filas = [json.loads(x) for x in ruta.read_text(encoding='utf-8').splitlines() if x.strip()]
        return next((f for f in reversed(filas) if f.get('candidate_id') == candidate_id), None)

    def ultimo(self, modelo: str) -> dict[str, Any] | None:
        """Última decisión; no implica que el candidato esté activo."""
        ruta = self._modelo(modelo) / 'latest.json'
        if not ruta.is_file():
            return None
        payload = json.loads(ruta.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('última decisión ilegible')
        detalle = self.detalle(modelo, payload.get('candidate_id'), verificar_artefactos=False)
        if detalle['decision'].get('status') != payload.get('status'):
            raise ValueError('última decisión no coincide con el candidato')
        return {**payload, 'detalle': detalle}


def reabrir_en_subproceso(comando: Sequence[str], *, timeout_s: float = 120.0,
                          cwd: Path | str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        proceso = subprocess.run(list(comando), cwd=cwd, env=env, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace',
                                 timeout=timeout_s, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'returncode': None, 'error': str(exc)}
    payload = None
    if proceso.stdout.strip():
        try:
            payload = json.loads(proceso.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            payload = None
    return {'ok': proceso.returncode == 0 and isinstance(payload, dict) and payload.get('ok') is True,
            'returncode': proceso.returncode, 'payload': payload,
            'stderr': proceso.stderr[-2000:]}
