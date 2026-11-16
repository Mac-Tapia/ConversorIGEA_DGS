"""Calcula los valores de referencia de las pruebas de la estadística común (044:RF-12).

Los valores fijos de ``tests/test_evaluacion_estadistica.py`` salen de aquí: statsmodels, krippendorff y pingouin, que no
están en el entorno del programa (``.venv``), y scipy, que sí está y por eso las pruebas lo comparan también en vivo. Las
salidas de la última ejecución están versionadas al lado, en ``referencias.json`` y ``referencias_hac.json``, con las
versiones de cada biblioteca; la prueba ``test_las_referencias_fijas_salen_del_guion_versionado`` las contrasta con el
módulo.

No forma parte de la suite (pytest no recoge este fichero) y no se importa desde el programa. Para repetirlo:

    python -m pip install --target <carpeta> statsmodels==0.15.0 krippendorff==0.8.1 pingouin==0.5.5
    python tests/fixtures/estadistica/referencias.py --libs <carpeta> --salida <carpeta de salida>

Escribe ``referencias.json`` y ``referencias_hac.json`` en la carpeta de salida; se comparan con los versionados.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def referencias() -> dict:
    """Valores de statsmodels, krippendorff, pingouin y scipy para los ejemplos publicados de las pruebas."""
    import krippendorff
    import numpy as np
    import pingouin as pg
    import scipy
    import statsmodels
    import statsmodels.api as sm
    from scipy import stats
    from statsmodels.stats.inter_rater import cohens_kappa
    from statsmodels.stats.multitest import multipletests
    from statsmodels.stats.proportion import proportion_confint
    from statsmodels.stats.weightstats import ttost_paired

    out: dict = {'versiones': {'scipy': scipy.__version__, 'statsmodels': statsmodels.__version__,
                               'krippendorff': getattr(krippendorff, '__version__', '0.8.1'),
                               'pingouin': pg.__version__, 'numpy': np.__version__}}
    out['wilson_81_263'] = proportion_confint(81, 263, method='wilson')
    out['wilson_0_10'] = proportion_confint(0, 10, method='wilson')
    out['holm'] = list(multipletests([0.01, 0.04, 0.03, 0.005, 0.2], method='holm')[1])
    x = np.array([5.1, 4.9, 5.3, 5.0, 5.2, 4.8, 5.1, 5.0, 4.9, 5.2])
    y = np.array([5.0, 5.0, 5.2, 5.1, 5.1, 4.9, 5.0, 5.1, 5.0, 5.1])
    r = ttost_paired(x, y, -0.2, 0.2)
    out['tost'] = {'p': r[0], 't_inf': r[1][0], 'p_inf': r[1][1], 't_sup': r[2][0], 'p_sup': r[2][1]}
    k = cohens_kappa(np.array([[20, 5], [10, 15]]))
    out['kappa_tabla'] = {'kappa': k.kappa, 'var': k.var_kappa}
    nan = np.nan
    # Krippendorff (2011), «Computing Krippendorff's Alpha-Reliability»: 4 codificadores, 12 unidades.
    datos = [[1, 2, 3, 3, 2, 1, 4, 1, 2, nan, nan, nan],
             [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, nan, 3],
             [nan, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, nan],
             [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, nan]]
    out['krippendorff_nominal'] = krippendorff.alpha(reliability_data=datos, level_of_measurement='nominal')
    out['krippendorff_intervalo'] = krippendorff.alpha(reliability_data=datos, level_of_measurement='interval')
    # Hollander y Wolfe (1973, p. 29), el ejemplo de wilcox.test de R.
    a = np.array([1.83, 0.50, 1.62, 2.48, 1.68, 1.88, 1.55, 3.06, 1.30])
    b = np.array([0.878, 0.647, 0.598, 2.05, 1.06, 1.29, 1.06, 3.14, 1.29])
    w = pg.wilcoxon(a, b, alternative='two-sided')
    out['wilcoxon'] = {'W': float(w['W-val'].iloc[0]), 'p': float(w['p-val'].iloc[0]), 'rbc': float(w['RBC'].iloc[0])}
    # Newey-West: varianza HAC de la media como OLS sobre una constante, Bartlett, sin corrección.
    rng = np.random.default_rng(7)
    d = np.round(np.cumsum(rng.normal(size=60)) * 0.1 + rng.normal(size=60), 4)
    for retardos in (1, 3):
        m = sm.OLS(d, np.ones_like(d)).fit(cov_type='HAC', cov_kwds={'maxlags': retardos, 'use_correction': False})
        out[f'hac_L{retardos}'] = {'media': float(m.params[0]), 'var_media': float(m.cov_params()[0, 0])}
    out['serie_hac'] = d.tolist()
    # DM-HLN con h = 1 es el t pareado de scipy.
    e1 = rng.normal(size=40)
    e2 = rng.normal(size=40) * 1.2
    out['ttest_rel_h1'] = list(map(float, stats.ttest_rel(e1 ** 2, e2 ** 2)))
    return out


def referencias_hac() -> dict:
    """Varianza HAC de la media (statsmodels) de la serie determinista ``SERIE_HAC`` de las pruebas."""
    import numpy as np
    import statsmodels
    import statsmodels.api as sm

    d = np.array([round(math.sin(t / 3) + 0.5 * math.cos(1.7 * t) + t / 60, 6) for t in range(60)])
    out: dict = {'statsmodels': statsmodels.__version__}
    for nucleo in ('bartlett', 'uniform'):
        for retardos in (0, 1, 3):
            m = sm.OLS(d, np.ones_like(d)).fit(
                cov_type='HAC', cov_kwds={'maxlags': retardos, 'kernel': nucleo, 'use_correction': False})
            out[f'{nucleo}_L{retardos}'] = float(m.cov_params()[0, 0])
    out['media'] = float(d.mean())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--libs', help='carpeta con statsmodels, krippendorff y pingouin instalados aparte (pip --target)')
    ap.add_argument('--salida', required=True, help='carpeta donde escribir referencias.json y referencias_hac.json')
    args = ap.parse_args(argv)
    if args.libs:
        libs = Path(args.libs)
        if not libs.is_dir():
            ap.error(f'--libs no es una carpeta: {libs}')
        sys.path.insert(0, str(libs))
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, datos in (('referencias.json', referencias()), ('referencias_hac.json', referencias_hac())):
        (salida / nombre).write_text(json.dumps(datos, indent=1, default=float) + '\n', encoding='utf-8')
        print(salida / nombre)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
