"""067:RF-12 a RF-19: los planes que escriben sobreviven a un reinicio de la web, sin reanudarse.

Vivían en memoria: reiniciar la web, cosa que pide cada cambio de código, perdía lo que el operador tenía a
la espera de confirmar. Se guarda solo lo que hace falta para volver a proponerlo: el plan, lo que la web
sabía de él y el sello de su contexto. Lo que nunca se guarda es una confirmación.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..runtime_paths import staging_publicacion
from .almacen import ahora
from .plan import Plan

_ID = re.compile(r'[0-9a-f]{12}')


def _firma(doc: dict) -> str:
    cuerpo = {k: v for k, v in doc.items() if k != 'huella'}
    return hashlib.sha256(json.dumps(cuerpo, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _extras_compactas(extras: dict) -> dict:
    """Sin las curvas de la última máxima: pesan megas y los pasos solo usan su trabajo y sus medidores."""
    salida = dict(extras or {})
    maxima = salida.get('ultima_maxima')
    if isinstance(maxima, dict):
        filas = (maxima.get('result') or {}).get('resultados') or []
        salida['ultima_maxima'] = {'id': maxima.get('id'), 'result': {'resultados': [
            {k: r.get(k) for k in ('alimentador', 'medidor', 'error')} for r in filas]}}
    return salida


class PlanesGuardados:
    """Una carpeta por espacio, fuera de las ejecuciones: el plan no depende de la fuente activa."""

    def __init__(self, raiz: Path):
        self.carpeta = Path(raiz) / 'asistente_planes'

    def _ruta(self, plan_id: str) -> Path | None:
        # El identificador llega por la URL: solo el formato que da el servidor compone una ruta.
        return self.carpeta / f'{plan_id}.json' if _ID.fullmatch(str(plan_id)) else None

    def _escribir(self, ruta: Path, doc: dict) -> None:
        doc = {**doc, 'huella': _firma(doc)}
        self.carpeta.mkdir(parents=True, exist_ok=True)
        with staging_publicacion(ruta) as temporal:
            temporal.write_text(json.dumps(doc, ensure_ascii=False, default=str), encoding='utf-8')
            os.replace(temporal, ruta)

    def guardar(self, plan: Plan, extras: dict, gobierno: Any) -> None:
        ruta = self._ruta(plan.id)
        if ruta is None:
            raise ValueError('identificador de plan inválido')
        self._escribir(ruta, {'schema_version': 1, 'plan': asdict(plan), 'extras': _extras_compactas(extras),
                              'sello': gobierno.sello(), 'estado': 'pendiente', 'fecha': ahora(), 'ultimo_error': ''})

    def leer(self, plan_id: str) -> dict | None:
        """El documento, o ``None`` si no existe o se alteró: un plan dudoso no se ofrece."""
        ruta = self._ruta(plan_id)
        if ruta is None or not ruta.is_file():
            return None
        try:
            doc = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return doc if isinstance(doc, dict) and doc.get('huella') == _firma(doc) else None

    def marcar(self, plan_id: str, estado: str, *, error: str = '') -> None:
        ruta, doc = self._ruta(plan_id), self.leer(plan_id)
        if ruta is not None and doc is not None:
            self._escribir(ruta, {**doc, 'estado': estado, 'ultimo_error': error})

    def borrar(self, plan_id: str) -> None:
        ruta = self._ruta(plan_id)
        if ruta is not None:
            ruta.unlink(missing_ok=True)

    def identificadores(self) -> list[str]:
        if not self.carpeta.is_dir():
            return []
        rutas = sorted(self.carpeta.glob('*.json'), key=lambda p: p.stat().st_mtime)
        return [p.stem for p in rutas if _ID.fullmatch(p.stem)]

    def listar(self) -> list[dict]:
        return [d for d in map(self.leer, self.identificadores()) if d is not None]


def plan_de(doc: dict) -> Plan:
    """El plan guardado, con sus alternativas como las daba el intérprete."""
    datos = dict(doc['plan'])
    datos['alternativas'] = [tuple(a) for a in datos.get('alternativas') or []]
    return Plan(**datos)
