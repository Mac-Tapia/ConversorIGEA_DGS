"""046:RF-1 046:RF-2 046:RF-3 — datos temporales sin acceso al futuro."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest


def test_escala_usa_solo_entrenamiento():
    """046:RF-1 — un pico posterior al corte no cambia la escala del entrenamiento."""
    from igea_dgs.digital_twin.temporal import GemeloGRU
    serie = np.linspace(1.0, 2.0, 40)
    pico = serie.copy()
    pico[-1] = 10000
    for s in (serie, pico):
        modelo = GemeloGRU(ventana=4, ocultas=4, epocas=1, fraccion_validacion=0.25)
        modelo.entrenar(s)
        assert modelo.escala == pytest.approx(max(serie[:31]))
        assert modelo.disp.type == 'cuda'


def filas():
    inicio = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [{'instante': (inicio + timedelta(minutes=15 * i)).isoformat(),
             'valor': float(i + 1), 'unidad': 'kW'} for i in (0, 1, 3, 4)]


def test_hueco_no_es_cero():
    """046:RF-3 — un hueco conserva máscara y no entra en la escala."""
    from igea_dgs.digital_twin.series_causales import preparar_serie
    salida = preparar_serie(filas(), corte='2026-09-01T01:00:00+00:00',
                           cadencia_min=15, zona_horaria='America/Lima', covariables={})
    assert salida['filas'][2]['valor'] is None
    assert salida['mascara'] == [True, True, False, True, True]
    assert salida['transformaciones']['escala'] == 4.0


def test_covariable_sin_asof_se_excluye():
    """046:RF-2 — el valor futuro medido no se presenta como conocido al pronosticar."""
    from igea_dgs.digital_twin.series_causales import preparar_serie
    salida = preparar_serie(filas(), corte='2026-09-01T01:00:00+00:00', cadencia_min=15,
        zona_horaria='UTC', covariables={'clima': [
            {'instante': '2026-09-01T01:00:00+00:00', 'valor': 99,
             'disponible_desde': '2026-09-02T00:00:00+00:00'}]})
    assert salida['covariables']['clima'][-1] is None


def test_timestamp_duplicado_rechaza():
    """046:RF-3 — dos medidas del mismo instante requieren resolución de fuente."""
    from igea_dgs.digital_twin.series_causales import preparar_serie
    with pytest.raises(ValueError, match='duplicado'):
        preparar_serie(filas() + filas()[:1], corte='2026-09-01T01:00:00+00:00',
                       cadencia_min=15, zona_horaria='UTC', covariables={})
