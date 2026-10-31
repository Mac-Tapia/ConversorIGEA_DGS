"""Registro común inmutable y promoción atómica de cualquier modelo."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Sequence


class EstadoModelo(str, Enum):
    PROMOVIDO = 'PROMOVIDO'
    RECHAZADO = 'RECHAZADO'
    BLOQUEADO_POR_DATOS = 'BLOQUEADO_POR_DATOS'
    ERROR_ENTORNO = 'ERROR_ENTORNO'


def _canonico(valor: Any) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), default=str, allow_nan=False).encode('utf-8')


class RegistroModelo:
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz)

    def _modelo(self, modelo: str) -> Path:
        if not isinstance(modelo, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', modelo):
            raise ValueError('identidad de modelo inválida')
        return self.raiz / modelo

    def _reemplazar_json(self, ruta: Path, payload: dict[str, Any]) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(f'.{ruta.name}.{os.getpid()}.tmp')
        tmp.write_bytes(_canonico(payload))
        os.replace(tmp, ruta)

    def registrar_candidato(self, modelo: str, *, model_manifest: dict, dataset_manifest: dict,
                            metrics: dict, decision: dict, smoke_reload: dict,
                            artifacts: Sequence[Path | str] = ()) -> dict[str, Any]:
        modelo_raiz = self._modelo(modelo)
        try:
            estado = EstadoModelo(decision['status'])
        except (KeyError, ValueError) as exc:
            raise ValueError('estado terminal desconocido') from exc
        if estado == EstadoModelo.PROMOVIDO and not (
                (decision.get('gates') or {}).get('approved') and smoke_reload.get('ok')):
            raise ValueError('PROMOVIDO requiere puertas y reapertura exitosas')
        hashes = {}
        for artefacto in artifacts:
            ruta = Path(artefacto)
            if not ruta.is_file():
                raise ValueError(f'artefacto ausente: {ruta}')
            if ruta.name in hashes:
                raise ValueError(f'artefacto duplicado: {ruta.name}')
            hashes[ruta.name] = hashlib.sha256(ruta.read_bytes()).hexdigest()
        identidad = hashlib.sha256(_canonico({
            'model': modelo, 'model_manifest': model_manifest,
            'dataset_manifest': dataset_manifest, 'metrics': metrics,
            'decision': decision, 'smoke_reload': smoke_reload, 'artifacts': hashes})).hexdigest()
        final = modelo_raiz / 'candidates' / identidad
        if not final.exists():
            final.parent.mkdir(parents=True, exist_ok=True)
            temporal = Path(tempfile.mkdtemp(prefix=f'.{identidad}.', dir=final.parent))
            try:
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
            except BaseException:
                shutil.rmtree(temporal, ignore_errors=True)
                raise
        return {'candidate_id': identidad, 'model': modelo, 'status': estado.value,
                'path': str(final)}

    def _candidato(self, modelo: str, candidate_id: str) -> tuple[Path, dict, dict]:
        detalle = self.detalle(modelo, candidate_id)
        return Path(detalle['path']), detalle['decision'], detalle['smoke_reload']

    def detalle(self, modelo: str, candidate_id: str) -> dict[str, Any]:
        if not isinstance(candidate_id, str) or not re.fullmatch(r'[0-9a-f]{64}', candidate_id):
            raise ValueError('identidad de candidato inválida')
        raiz = self._modelo(modelo) / 'candidates' / candidate_id
        if not raiz.is_dir():
            raise ValueError('candidato inexistente')
        datos = {nombre: json.loads((raiz / f'{nombre}.json').read_text(encoding='utf-8'))
                 for nombre in ('model_manifest', 'dataset_manifest', 'metrics', 'decision', 'smoke_reload', 'artifacts')}
        for nombre, esperado in datos['artifacts'].items():
            if Path(nombre).name != nombre or '/' in nombre or '\\' in nombre:
                raise ValueError('integridad: nombre de artefacto inválido')
            ruta = raiz / 'artifacts' / nombre
            if not ruta.is_file() or hashlib.sha256(ruta.read_bytes()).hexdigest() != esperado:
                raise ValueError(f'integridad: artefacto modificado o ausente: {nombre}')
        if hashlib.sha256(_canonico({'model': modelo, **datos})).hexdigest() != candidate_id:
            raise ValueError('integridad: manifiesto de candidato modificado')
        return {'path': str(raiz), **datos}

    def promover(self, modelo: str, candidate_id: str) -> dict[str, Any]:
        _raiz, decision, smoke = self._candidato(modelo, candidate_id)
        if decision.get('status') != EstadoModelo.PROMOVIDO.value \
                or not (decision.get('gates') or {}).get('approved') or not smoke.get('ok'):
            raise ValueError('candidato no aprobado o no reabierto')
        activo_ruta = self._modelo(modelo) / 'active.json'
        anterior = self.activo(modelo)
        payload = {'candidate_id': candidate_id, 'status': EstadoModelo.PROMOVIDO.value}
        if anterior is not None:
            self._reemplazar_json(self.raiz / modelo / 'previous.json', anterior)
        self._reemplazar_json(activo_ruta, payload)
        return payload

    def activo(self, modelo: str) -> dict[str, Any] | None:
        ruta = self._modelo(modelo) / 'active.json'
        return json.loads(ruta.read_text(encoding='utf-8')) if ruta.is_file() else None

    def volver_al_anterior(self, modelo: str) -> dict[str, Any]:
        ruta = self._modelo(modelo) / 'previous.json'
        if not ruta.is_file():
            raise ValueError('no existe modelo anterior')
        payload = json.loads(ruta.read_text(encoding='utf-8'))
        self._candidato(modelo, payload['candidate_id'])
        self._reemplazar_json(self.raiz / modelo / 'active.json', payload)
        return payload


def reabrir_en_subproceso(comando: Sequence[str], *, timeout_s: float = 120.0,
                          cwd: Path | str | None = None) -> dict[str, Any]:
    try:
        proceso = subprocess.run(list(comando), cwd=cwd, capture_output=True, text=True,
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
