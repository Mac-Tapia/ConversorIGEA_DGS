"""047:RF-12 a RF-15 — la web usa el protocolo integral sin activar candidatos bloqueados."""
import json
import pytest


def test_web_lanza_integral_y_no_recalibra_candidato_bloqueado(tmp_path, monkeypatch):
    """047:RF-13 / 047:RF-15 — entrenar no equivale a modificar el modelo que atiende."""
    from igea_dgs.asistente import senales
    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    ws = Workspace(id='ensayo', root=tmp_path / 'web')
    comandos = []
    class Contexto:
        def run_process(self, cmd, **kwargs):
            comandos.append(cmd)
            salida = cmd[cmd.index('--output-json') + 1]
            from pathlib import Path
            Path(salida).write_text(json.dumps({'ordenes': {'promovido': False,
                'status': 'BLOQUEADO_POR_DATOS'}}), encoding='utf-8')
            return 0
        def log(self, mensaje):
            pass
    def no_recalibrar():
        raise AssertionError('un candidato no activo no recalibra el modelo en uso')
    monkeypatch.setattr(senales, 'calibrar_y_guardar', no_recalibrar)
    resultado = services.asistente_entrenar(ws, Contexto())
    assert '--integral' in comandos[0]
    assert resultado['ordenes']['status'] == 'BLOQUEADO_POR_DATOS'


def test_web_no_declara_hecho_un_entrenamiento_fallido(tmp_path, monkeypatch):
    """047:RF-14 — un proceso fallido con informe sigue siendo un trabajo fallido."""
    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    ws = Workspace(id='ensayo', root=tmp_path / 'web')
    class Contexto:
        def run_process(self, cmd, **kwargs):
            from pathlib import Path
            Path(cmd[cmd.index('--output-json') + 1]).write_text(json.dumps(
                {'training_completed': False, 'error': 'GPU ocupada'}), encoding='utf-8')
            return 2
    with pytest.raises(services.UserError, match='GPU ocupada'):
        services.asistente_entrenar(ws, Contexto())
