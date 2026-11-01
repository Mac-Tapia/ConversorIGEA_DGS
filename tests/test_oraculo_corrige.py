"""El oráculo corrige, antes de importar, la demanda de relleno o fuera de escala (spec 057).

Caso real que lo motivó (2026-11-01): en la copia VNR-GIS ELOR25_V2 de Electro Oriente,
``Sed.MaxDemTotal`` vale 39 kW en las 8 729 SED, con potencias instaladas de 5 a 2 000 kVA.
NJA202 llegó a DIgSILENT con 470 SED de 5 kVA al 780 %; el oráculo dijo «no converge», se
importó igual y DIgSILENT bajó la demanda al 10 % sin converger. Aquí se fuerza ese relleno
sobre exports sintéticos, en las dos disposiciones.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

pytest.importorskip('pandapower')

from convertersmartgrid import oraculo  # noqa: E402
from convertersmartgrid.model import build_feeder_model  # noqa: E402
from convertersmartgrid.reglas import REGLAS_PROYECTO, SIN_REGLAS, aplicar_reglas  # noqa: E402
from convertersmartgrid.sed_potencia import FP_CORRECCION, corregir_demanda, demanda_fuera_de_escala  # noqa: E402
from synthetic_export import ExportSpec, load_export  # noqa: E402

LAYOUTS = ('reducido', 'completo')
KVA = (5.0, 10.0, 25.0, 50.0, 100.0, 160.0)


def _modelo(tmp_path, layout='reducido', seed=11):
    spec = ExportSpec(feeders=1, sections_per_feeder=8, loads_per_feeder=6, layout=layout, seed=seed)
    ds = load_export(spec, tmp_path / layout)
    modelo = build_feeder_model(ds, ds.feeder_ids()[0], strict=True)
    # Potencias instaladas distintas, como en la fuente real.
    modelo.seds = [dataclasses.replace(s, design_kva=KVA[i % len(KVA)])
                   for i, s in enumerate(sorted(modelo.seds, key=lambda s: s.load_key))]
    return modelo


def _relleno(modelo, kw):
    """La misma demanda en todas las cargas de SED, sin reactiva, como ELOR25_V2."""
    claves = {s.load_key for s in modelo.seds}
    modelo.loads = [dataclasses.replace(c, p_mw=kw / 1000.0, q_mvar=0.0)
                    if (c.section_id, c.device_number) in claves else c for c in modelo.loads]
    return modelo


def _kva(modelo):
    return {s.load_key: float(s.design_kva) for s in modelo.seds}


@pytest.mark.parametrize('layout', LAYOUTS)
def test_reconoce_la_demanda_de_relleno(tmp_path, layout):
    """057:RF-2 — el mismo valor en todas las SED con kVA distintos es relleno."""
    modelo = _relleno(_modelo(tmp_path, layout), 3.9)   # 3,9 kW: dentro de todas las SED
    assert demanda_fuera_de_escala(modelo) == sorted(_kva(modelo))


def test_reconoce_la_sed_que_supera_su_potencia(tmp_path):
    """057:RF-2 — una SED con más carga que su potencia instalada está fuera de escala."""
    modelo = _modelo(tmp_path)
    kva = _kva(modelo)
    # Cada carga distinta y dentro de su SED, salvo una al triple de su potencia.
    pequena = min(kva, key=lambda k: (kva[k], k))
    nuevas = []
    for i, c in enumerate(modelo.loads):
        clave = (c.section_id, c.device_number)
        if clave in kva:
            p = kva[clave] * 3.0 if clave == pequena else kva[clave] * 0.1 * (1 + i / 100)
            c = dataclasses.replace(c, p_mw=p / 1000.0, q_mvar=0.0)
        nuevas.append(c)
    modelo.loads = nuevas
    assert demanda_fuera_de_escala(modelo) == [pequena]


def test_no_toca_la_demanda_real_ni_la_cero(tmp_path):
    """057:RF-2 — demanda propia dentro de su SED, o en cero, no es relleno."""
    modelo = _modelo(tmp_path)
    kva = _kva(modelo)
    nuevas = []
    for i, c in enumerate(modelo.loads):
        clave = (c.section_id, c.device_number)
        if clave in kva:
            p = 0.0 if i == 0 else kva[clave] * 0.3 * (1 + i / 50)
            c = dataclasses.replace(c, p_mw=p / 1000.0)
        nuevas.append(c)
    modelo.loads = nuevas
    assert demanda_fuera_de_escala(modelo) == []


def test_corrige_por_la_potencia_instalada(tmp_path):
    """057:RF-3 — P = kVA × factor × 0,98 y Q con el mismo FP; el cambio queda anotado."""
    modelo = _relleno(_modelo(tmp_path), 39.0)
    kva = _kva(modelo)
    claves = demanda_fuera_de_escala(modelo)
    cambios = corregir_demanda(modelo, claves, 0.5)
    seno = math.sqrt(1.0 - FP_CORRECCION ** 2)
    por_clave = {(c.section_id, c.device_number): c for c in modelo.loads}
    for clave in claves:
        c = por_clave[clave]
        assert c.p_mw == pytest.approx(kva[clave] * 0.5 * FP_CORRECCION / 1000.0)
        assert c.q_mvar == pytest.approx(kva[clave] * 0.5 * seno / 1000.0)
    assert len(cambios) == len(claves)
    assert all(ch.p_fuente_kw == pytest.approx(39.0) for ch in cambios)


@pytest.mark.parametrize('layout', LAYOUTS)
def test_el_oraculo_busca_el_factor_y_converge(tmp_path, layout):
    """057:RF-1, 057:RF-3 — sin converger, busca el mayor factor ≤ 0,8 con el que converge."""
    modelo = _relleno(_modelo(tmp_path, layout), 50_000.0)   # 50 MW por SED: no converge
    assert not oraculo.validar(modelo).convergio
    res = oraculo.corregir_para_converger(modelo)
    assert res.convergio and 0.0 < res.factor <= 0.8
    assert oraculo.validar(modelo).convergio
    kva = _kva(modelo)
    for c in modelo.loads:
        clave = (c.section_id, c.device_number)
        if clave in kva:
            s = math.hypot(c.p_mw, c.q_mvar) * 1000.0
            assert s <= kva[clave] * 0.8 + 1e-9


def test_no_corrige_lo_que_ya_converge(tmp_path):
    """057:RF-1 — si el oráculo converge, el modelo queda como lo trae la fuente."""
    modelo = _relleno(_modelo(tmp_path), 3.9)
    antes = repr(sorted(modelo.loads, key=lambda c: (c.section_id, c.device_number)))
    res = oraculo.corregir_para_converger(modelo)
    assert res.convergio and not res.cambios
    assert repr(sorted(modelo.loads, key=lambda c: (c.section_id, c.device_number))) == antes


def test_aplicar_reglas_lo_informa_y_es_determinista(tmp_path):
    """057:RF-4 — la corrección va al informe de reglas con el valor de la fuente y el nuevo."""
    informes = []
    for i in range(2):
        modelo = _relleno(_modelo(tmp_path / str(i)), 50_000.0)
        informes.append(aplicar_reglas(modelo, REGLAS_PROYECTO))
    dc = informes[0]['demanda_corregida']
    assert dc['convergio'] and dc['sed'] > 0 and 0 < dc['factor'] <= 0.8
    assert all('50000' in linea and 'kW' in linea for linea in dc['lineas'])
    assert informes[0] == informes[1]
    modelo = _relleno(_modelo(tmp_path / 'literal'), 50_000.0)
    assert 'demanda_corregida' not in aplicar_reglas(modelo, SIN_REGLAS)


def test_la_importacion_deja_fuera_lo_que_no_converge(tmp_path, monkeypatch):
    """057:RF-5, 057:RF-6 — solo se importa lo que converge en el oráculo; el resto se nombra."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services
    from convertersmartgrid.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    ws.out_dir.mkdir(parents=True)
    jobs = []
    for nombre in ('BIEN', 'MAL'):
        dgs = ws.out_dir / f'{nombre}.dgs'
        dgs.write_text('DGS', encoding='ascii')
        dgs.with_name(f'{nombre}_feeder_metadata.json').write_text('{}', encoding='utf-8')
        jobs.append((nombre, dgs, None))
    monkeypatch.setattr(services, 'dgs_jobs', lambda _ws, _feeders: (jobs, []))
    monkeypatch.setattr(services, '_script', lambda _name: tmp_path / 'script.py')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, tmp_path / 'python.exe'))
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _pf_dir: {})
    monkeypatch.setattr(services, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'Carpeta')
    monkeypatch.setattr(services, 'powerfactory_status', lambda: {'interpreter_reason': 'test'})
    monkeypatch.setattr(services, 'pandapower_preflight', lambda *_args: {
        'disponible': True, 'avisos': [], 'feeders': [],
        'no_convergen': {'MAL': 'ERROR no_converge [TR_X]: el flujo no converge'},
    })
    logs: list[str] = []
    commands: list[list[str]] = []
    ctx = SimpleNamespace(log=logs.append, progress=lambda *_a: None, check_cancel=lambda: None,
                          run_process=lambda command, **_kw: commands.append(command) or 0)

    result = services.powerfactory_flow(ws, ctx, ['BIEN', 'MAL'])

    importados = [c[c.index('--import-dgs') + 1] for c in commands]
    assert importados == [str(ws.out_dir / 'BIEN.dgs')]
    assert result['ok'] == 1 and result['failed'] == 1
    assert any(l.startswith('NO_CONVERGE MAL') and 'TR_X' in l for l in result['lines'])
