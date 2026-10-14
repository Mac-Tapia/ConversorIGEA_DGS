"""El ajuste convergente completa el vínculo provisional del proyecto adoptado."""

from __future__ import annotations


def test_kw_square_with_kvar_warning_promotes_native_binding(tmp_path):
    from igea_dgs.powerfactory_binding import (
        PowerFactoryProjectBinding,
        promote_project_binding_after_calibration,
    )
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='promotion', root=tmp_path)
    pending = PowerFactoryProjectBinding(
        project='P', folder='F', source_run_id='run', source_mode='mdb',
        source_fingerprint='f' * 64, feeders=('CA101',),
        dgs_sha256={'CA101': 'd' * 64}, native_inventory_sha256='n' * 64,
        native_reread={'status': 'IDENTIDAD_VERIFICADA_PENDIENTE_CONVERGENCIA'},
    )
    ws.pf_project_bindings['P'] = pending.as_dict()
    report = {
        'modo': 'aplicar', 'feeder': 'CA101', 'cuadrado': True,
        'status': 'AVISO_KVAR', 'fallos': [],
        'cabecera': {'kw': 5997.12, 'kvar': 1556.39},
        'objetivo': {'kw': 6000.0, 'kvar': 302.0},
        'kvar_no_bloqueante': {'status': 'AVISO_KVAR', 'bloquea': False},
        'relectura_cargas_nativas': {'status': 'VERIFICADO_PERSISTENCIA', 'cantidad': 168},
        'relectura_bancos': {'status': 'VERIFICADO_PERSISTENCIA', 'reread': 3},
    }

    promoted = promote_project_binding_after_calibration(ws, 'P', report)

    assert promoted is not None
    assert promoted.native_reread['status'] == 'VERIFICADO_PERSISTENCIA'
    assert promoted.native_reread['effective_reread']['comldf_valid'] is True
    assert promoted.native_reread['calibration']['status'] == 'AVISO_KVAR'
    assert promoted.native_reread['calibration']['kvar_blocks'] is False
    assert ws.pf_project_bindings['P']['binding_sha256'] == promoted.binding_sha256

