"""043:RF-14, 043:RF-15: el dataset se regenera sin pisar el anterior y dice si está completo."""
from __future__ import annotations

import json
import os
import random
from types import SimpleNamespace

import pytest

from apoyo import cargar_herramienta

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))


@pytest.fixture
def guion():
    return cargar_herramienta('construir_dataset_entrenamiento.py', 'construir_dataset_prueba')


def _registro(tipo, quality='gold_human', sistema=''):
    return SimpleNamespace(tipo=tipo, quality=quality, sistema=sistema)


def test_lo_sintetico_y_el_contexto_no_completan_el_dataset(guion):
    """043:RF-15 — miles de registros de contexto no suplen las órdenes reales que faltan."""
    rng = random.Random(SEMILLA)
    reales = rng.randint(1, guion.ORDENES_REALES_MINIMAS - 1)
    registros = ([_registro('orden') for _ in range(reales)]
                 + [_registro('orden', 'synthetic') for _ in range(rng.randint(200, 500))]
                 + [_registro('artefacto_contexto', 'context') for _ in range(rng.randint(500, 900))]
                 + [_registro('episodio', 'gold_native', 'P') for _ in range(guion.EPISODIOS_POR_PROYECTO)])
    v = guion.veredicto(registros)
    assert not v['completo'] and v['ordenes_reales'] == reales
    assert any(f'{guion.ORDENES_REALES_MINIMAS - reales} órdenes' in x for x in v['faltan'])


def test_un_proyecto_con_pocos_episodios_lo_deja_incompleto(guion):
    """043:RF-15 — el mínimo es por proyecto, no el total."""
    ordenes = [_registro('orden') for _ in range(guion.ORDENES_REALES_MINIMAS)]
    bien = [_registro('episodio', 'gold_native', 'Grande') for _ in range(50)]
    pocos = [_registro('episodio', 'gold_native', 'Chico') for _ in range(guion.EPISODIOS_POR_PROYECTO - 1)]
    assert guion.veredicto(ordenes + bien)['completo'] is True
    v = guion.veredicto(ordenes + bien + pocos)
    assert not v['completo'] and any('Chico' in x for x in v['faltan'])
    assert guion.veredicto(ordenes)['completo'] is False, 'sin episodios no está completo'


def test_construye_en_carpeta_nueva_y_no_pisa_la_anterior(guion, tmp_path):
    """043:RF-14 — las particiones van a una carpeta nueva; si ya tiene contenido, se rechaza."""
    asistente = tmp_path / 'web' / '_asistente'
    asistente.mkdir(parents=True)
    filas = [{'texto': f'calibrar el alimentador {i}', 'accion': 'calibrar', 'sets': [], 'alimentadores': [f'A{i}']}
             for i in range(12)]
    (asistente / 'ejemplos.jsonl').write_text(''.join(json.dumps(f) + '\n' for f in filas), encoding='utf-8')
    destino = tmp_path / 'dataset_nuevo'
    informe = guion.construir(tmp_path / 'web', asistente, tmp_path / 'gemelo', destino)
    assert (destino / 'manifest.json').is_file() and informe['destino'] == str(destino)
    assert informe['completo'] is False
    anterior = (destino / 'manifest.json').read_bytes()
    with pytest.raises(ValueError, match='no se pisa'):
        guion.construir(tmp_path / 'web', asistente, tmp_path / 'gemelo', destino)
    assert (destino / 'manifest.json').read_bytes() == anterior
