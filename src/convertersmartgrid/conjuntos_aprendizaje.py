"""050:RF-7/8: lectura verificada del conjunto para consumidores, sin preparar ni entrenar."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .model_registry import EstadoModelo, RegistroModelo
from .contratos_aprendizaje import (
    CicloBloqueado, ORDEN_MODELOS, ESQUEMA_CONJUNTO, ESQUEMA_CONJUNTO_V1,
    HEX_SHA256 as _HEX, huella as _huella,
)

def leer_objeto_json(ruta: Path) -> dict[str, Any]:
    dato = json.loads(ruta.read_text(encoding='utf-8'))
    if not isinstance(dato, dict):
        raise ValueError(f'{ruta.name}: no es un objeto')
    return dato

def leer_puntero(raiz: Path, nombre: str) -> dict[str, Any] | None:
    ruta = raiz / 'conjuntos' / nombre
    return leer_objeto_json(ruta) if ruta.is_file() else None

def conjunto_por_id(raiz: Path, identidad: str) -> dict[str, Any]:
    if not isinstance(identidad, str) or not _HEX.fullmatch(identidad):
        raise CicloBloqueado('identidad del conjunto no válida')
    try:
        dato = leer_objeto_json(raiz / 'conjuntos' / f'{identidad}.json')
        esquema = dato.get('schema')
        if esquema not in (ESQUEMA_CONJUNTO, ESQUEMA_CONJUNTO_V1) or dato.get('conjunto_id') != identidad:
            raise CicloBloqueado('esquema o identidad del conjunto no coincide')
        campos = ('miembros', 'snapshot_id', 'ciclo')
        if esquema == ESQUEMA_CONJUNTO:
            campos = ('schema', *campos, 'retencion', 'conjunta')
        if _huella({k: dato[k] for k in campos}) != identidad:
            raise CicloBloqueado('conjunto activo modificado')
        miembros = dato['miembros']
        if (not isinstance(miembros, dict) or not miembros or any(
                f not in ORDEN_MODELOS or not isinstance(cid, str) or not _HEX.fullmatch(cid)
                for f, cid in miembros.items())):
            raise CicloBloqueado('conjunto sin miembros válidos')
        return dato
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CicloBloqueado(f'no se pudo verificar el conjunto: {exc}') from exc

def conjunto_activo(raiz: Path | str) -> dict[str, Any] | None:
    """El conjunto en uso, releído y con su contenido verificado."""
    raiz = Path(raiz)
    try:
        puntero = leer_puntero(raiz, 'activo.json')
        return None if puntero is None else conjunto_por_id(raiz, puntero['conjunto_id'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CicloBloqueado(f'conjunto activo ilegible: {exc}') from exc

def detalle_de_familia(registro: RegistroModelo, familia: str, candidato: str) -> tuple[str, dict]:
    """Resuelve por identidad exacta dentro de los registros declarados de la familia 043."""
    from .model_registry import registros_de
    if familia not in ORDEN_MODELOS or not isinstance(candidato, str) or not _HEX.fullmatch(candidato):
        raise CicloBloqueado('familia o identidad de candidato no válida')
    nombres = [n for n in registros_de(familia) if (registro.raiz / n / 'candidates' / candidato).is_dir()]
    if len(nombres) != 1:
        raise CicloBloqueado(f'{familia}: candidato inexistente o ambiguo en sus registros declarados')
    return nombres[0], registro.detalle(nombres[0], candidato)

def version_del_conjunto(raiz: Path | str, familia: str) -> str | None:
    """La versión que un consumidor usa de una familia: la del conjunto activo, no la última suelta."""
    activo = conjunto_activo(raiz)
    if activo is None:
        return None
    if familia not in activo['miembros']:
        raise CicloBloqueado(f'{familia}: no pertenece al conjunto activo; no se usa un puntero individual')
    return activo['miembros'][familia]

def miembro_del_conjunto(raiz: Path | str, familia: str, *, registro: RegistroModelo) -> dict | None:
    """050:RF-7: referencia coherente y artefactos verificados en una sola relectura del conjunto."""
    activo = conjunto_activo(raiz)
    if activo is None:
        return None
    if familia not in activo['miembros']:
        raise CicloBloqueado(f'{familia}: no pertenece al conjunto activo')
    cid = activo['miembros'][familia]
    try:
        nombre, detalle = detalle_de_familia(registro, familia, cid)
        if ((detalle['decision'].get('gates') or {}).get('approved') is not True
                or detalle['decision'].get('status') != EstadoModelo.PROMOVIDO.value
                or detalle['smoke_reload'].get('ok') is not True):
            raise CicloBloqueado('candidato sin aprobación individual o reapertura')
    except (OSError, ValueError) as exc:
        raise CicloBloqueado(f'{familia}: integridad del miembro: {exc}') from exc
    return {'conjunto_id': activo['conjunto_id'], 'familia': familia, 'candidate_id': cid,
            'modelo_registro': nombre, 'detalle': detalle}

def registro_comun(registro: RegistroModelo | None) -> RegistroModelo:
    if registro is None:
        from .asistente import almacen
        registro = RegistroModelo(almacen.raiz() / 'model_registry')
    return registro

def miembro_en_uso(familia: str, *, registro: RegistroModelo | None = None) -> dict | None:
    """050:RF-7: ubicación común del registro y conjunto para los consumidores de la aplicación."""
    registro = registro_comun(registro)
    return miembro_del_conjunto(registro.raiz.parent / 'aprendizaje', familia, registro=registro)

def exigir_sin_conjunto(*, registro: RegistroModelo | None = None) -> None:
    """050:RF-7: una operación individual no puede declarar activación sobre un puntero ignorado."""
    registro = registro_comun(registro)
    if conjunto_activo(registro.raiz.parent / 'aprendizaje') is not None:
        raise CicloBloqueado('Hay un conjunto activo: la publicación y reversión deben hacerse sobre el conjunto completo.')
