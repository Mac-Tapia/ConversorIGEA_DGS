"""043:RF-3 043:RF-4 — Regresiones del donante de reentrenamiento."""
from types import SimpleNamespace


def _row(text, task, group, quality='gold_human'):
    return SimpleNamespace(texto=text, tarea=task, group_id=group, quality=quality,
                           provenance={}, alimentadores=())


def test_exact_duplicate_across_partitions_invalidates_dataset():
    from igea_dgs.asistente.calidad_datos import auditar_contaminacion

    audit = auditar_contaminacion({
        'train': (_row('reentrena la pinn', 'gemelo_entrenar', 'g1'),),
        'validation': (_row('reentrena la pinn', 'gemelo_entrenar', 'g2'),),
        'test': (),
    })

    assert not audit['valid']
    assert audit['exact_text_leaks'] == ['reentrena la pinn']


def test_same_group_across_partitions_invalidates_dataset_even_if_text_changes():
    from igea_dgs.asistente.calidad_datos import auditar_contaminacion

    audit = auditar_contaminacion({
        'train': (_row('convierte CA101', 'convertir', 'family-1'),),
        'validation': (),
        'test': (_row('haz la conversión de CA101', 'convertir', 'family-1'),),
    })

    assert not audit['valid'] and audit['group_leaks'] == ['family-1']


def test_feeder_entities_do_not_inflate_human_gold_count():
    from igea_dgs.asistente.calidad_datos import resumir_calidad

    rows = [_row(f'Fuente contiene F{i:03d}', 'convertir', f'g{i}', 'context')
            for i in range(101)]
    summary = resumir_calidad(rows)

    assert summary['records'] == 101
    assert summary['qualities']['context'] == 101
    assert summary['qualities'].get('gold_human', 0) == 0


def test_unknown_quality_is_reported_and_blocks_audit():
    from igea_dgs.asistente.calidad_datos import auditar_contaminacion

    audit = auditar_contaminacion({'train': (_row('x', 'convertir', 'g', 'invented'),),
                                   'validation': (), 'test': ()})

    assert not audit['valid'] and audit['unknown_qualities'] == ['invented']
