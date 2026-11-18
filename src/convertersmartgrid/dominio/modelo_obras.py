"""Modelo aprendido para decidir en qué orden se miden las variantes (spec 087, RF-17 a RF-20).

Un clasificador de árboles que predice qué variante cumplirá en DIgSILENT. No decide nada: DIgSILENT confirma toda obra, y ninguna se
descarta por él. Tampoco se usa hasta demostrar que acierta en un sistema que no ha visto: validar por variante daría una
mejora falsa, porque las variantes de un alimentador se parecen entre sí.

Los rasgos son números: ningún nombre de cliente ni de barra entra en el fichero.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

RASGOS = ('n_obras', 'bancos', 'km_seccion', 'km_terna', 'reguladores', 'costo_anual', 'perdidas_kw', 'v_min', 'oraculo_cumple')
#: La fracción de mediciones que debe ahorrar el modelo frente al orden por costo para usarlo (087:RF-19).
MEJORA_MINIMA = 0.10
SEMILLA = 2026


def rasgos_de(variante: Any, oraculo: Mapping[str, Any] | None) -> dict[str, float]:
    """087:RF-17: lo que se sabe de una variante antes de medirla; sin dato del oráculo, 0."""
    o = oraculo or {}
    c = getattr(variante, 'cantidades', {}) or {}
    return {'n_obras': float(len(getattr(variante, 'obras', ()) or ())), 'bancos': float(c.get('bancos') or 0.0),
            'km_seccion': float(c.get('seccion') or 0.0), 'km_terna': float(c.get('terna') or 0.0),
            'reguladores': float(c.get('regulador') or 0.0), 'costo_anual': float(o.get('costo_anual') or 0.0),
            'perdidas_kw': float(o.get('perdidas_kw') or 0.0), 'v_min': float(o.get('v_min') or 0.0),
            'oraculo_cumple': 1.0 if o.get('cumple') else 0.0}


def fila_medida(sistema: str, grupo: str, rasgos: Mapping[str, float], cumple: bool) -> dict[str, Any]:
    """087:RF-17: una variante medida en DIgSILENT: ``grupo`` es su alimentador dentro de esa evaluación."""
    return {'sistema': str(sistema), 'grupo': str(grupo), 'rasgos': {k: float(rasgos[k]) for k in RASGOS}, 'cumple': bool(cumple)}


def anadir(ruta: Path | str, filas: Iterable[Mapping[str, Any]]) -> None:
    """Añade las filas; medir no puede hacer fallar el trabajo."""
    try:
        with open(ruta, 'a', encoding='utf-8') as f:
            for fila in filas:
                f.write(json.dumps(fila, ensure_ascii=False) + '\n')
    except OSError:
        pass


def leer(ruta: Path | str) -> list[dict[str, Any]]:
    filas = []
    try:
        for ln in Path(ruta).read_text(encoding='utf-8').splitlines():
            try:
                filas.append(json.loads(ln))
            except ValueError:
                continue
    except OSError:
        pass
    return filas


def _matriz(filas: Sequence[Mapping[str, Any]]) -> list[list[float]]:
    return [[float(f['rasgos'][k]) for k in RASGOS] for f in filas]


def _clasificador():
    from sklearn.ensemble import GradientBoostingClassifier

    return GradientBoostingClassifier(n_estimators=60, max_depth=3, random_state=SEMILLA)


def _mediciones_hasta_cumplir(filas: Sequence[Mapping[str, Any]], orden: Sequence[int]) -> int:
    """Cuántas variantes hay que medir, en ese orden, hasta la primera que cumple."""
    return next((i + 1 for i, j in enumerate(orden) if filas[j]['cumple']), len(orden))


def entrenar(filas: Sequence[Mapping[str, Any]], min_sistemas: int = 3) -> dict[str, Any]:
    """087:RF-18, RF-19: valida dejando fuera un sistema entero y, si supera al orden por costo, entrena con todo."""
    sistemas = sorted({f['sistema'] for f in filas})
    base = {'sistemas': len(sistemas), 'filas': len(filas), 'pasa': False, 'modelo': None}
    if len(sistemas) < max(2, int(min_sistemas)):
        return {**base, 'motivo': f'hay {len(sistemas)} sistemas y hacen falta {min_sistemas}'}
    if len({f['cumple'] for f in filas}) < 2:
        return {**base, 'motivo': 'solo hay una clase de resultado'}
    total_modelo = total_costo = 0
    for fuera in sistemas:
        entreno = [f for f in filas if f['sistema'] != fuera]
        if len({f['cumple'] for f in entreno}) < 2:
            continue
        clf = _clasificador().fit(_matriz(entreno), [f['cumple'] for f in entreno])
        grupos: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for f in filas:
            if f['sistema'] == fuera:
                grupos[f['grupo']].append(f)
        for fs in grupos.values():
            prob = clf.predict_proba(_matriz(fs))[:, list(clf.classes_).index(True)]
            total_modelo += _mediciones_hasta_cumplir(fs, sorted(range(len(fs)), key=lambda i: (-prob[i], i)))
            total_costo += _mediciones_hasta_cumplir(fs, sorted(range(len(fs)), key=lambda i: (fs[i]['rasgos']['costo_anual'], i)))
    pasa = bool(total_costo) and (total_costo - total_modelo) / total_costo >= MEJORA_MINIMA
    return {**base, 'pasa': pasa, 'mediciones_modelo': total_modelo, 'mediciones_costo': total_costo,
            'motivo': 'supera al orden por costo' if pasa else 'no supera al orden por costo en otro sistema',
            'modelo': _clasificador().fit(_matriz(filas), [f['cumple'] for f in filas]) if pasa else None}


def ordenar(modelo: Any, variantes: Sequence[Any], oraculo: Mapping[str, Mapping[str, Any]]) -> list[Any]:
    """087:RF-20: las mismas variantes, de más a menos probable; sin descartar ninguna, y sin modelo en su orden."""
    if modelo is None or not variantes:
        return list(variantes)
    filas = [{'rasgos': rasgos_de(v, oraculo.get(v.nombre))} for v in variantes]
    prob = modelo.predict_proba(_matriz(filas))[:, list(modelo.classes_).index(True)]
    return [variantes[i] for i in sorted(range(len(variantes)), key=lambda i: (-prob[i], i))]
