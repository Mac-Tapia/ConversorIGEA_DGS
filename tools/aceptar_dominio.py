#!/usr/bin/env python
"""Preaceptación de replay nativo (065:RF-21), solo lectura y sin conectar motores.

Reabre fuentes y evidencias selladas. La disponibilidad de diagnóstico nunca acredita
licencia, persistencia actual, convergencia ni aceptación eléctrica. Ejemplo:
python tools/aceptar_dominio.py --workspace RUTA --project PROYECTO --alimentador AL001
    --caso sin_proyecto --periodo 2026-09 --evidencias custodia.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))


def preaceptar(workspace: Path, project: str, feeders: list[str], *, caso: str,
              periodo: str, evidencias: list[dict], requiere_ml: bool = False) -> dict:
    """Exige replay exacto sin alterar la política operativa flexible del vínculo."""
    from convertersmartgrid.asistente.llm_destilacion import custodiar, verificar_fuente
    from convertersmartgrid.powerfactory_binding import require_project_binding
    from convertersmartgrid.sources.snapshot import fingerprint
    from convertersmartgrid.web.source_runs import load_source_run
    from convertersmartgrid.web.workspace import REGISTRO_VINCULOS_FILE

    bloqueos: list[str] = []
    resultado = {'schema_version': 1, 'proyecto': project, 'alimentadores': feeders,
        'caso': caso, 'periodo': periodo, 'workspace': str(workspace.resolve()),
        'listo_diagnostico': False, 'aceptacion_electrica': False,
        'operaciones_nativas': 0, 'licencia_verificada': False,
        'bloqueos': bloqueos, 'fuentes': [], 'evidencias': []}
    try:
        if not caso.strip() or not periodo.strip():
            raise ValueError('caso y periodo explícitos obligatorios')
        p = workspace / 'workspace.json'
        ws_raw = json.loads(p.read_text(encoding='utf-8-sig'))
        ws = SimpleNamespace(root=workspace, active_run_id=ws_raw.get('active_run_id'),
            pf_project_bindings=ws_raw.get('pf_project_bindings') or {},
            pf_inventory=ws_raw.get('pf_inventory') or {}, vinculos_compartidos=None)
        # El registro compartido aislado, si existe, tiene la prioridad canónica.
        registro = workspace.parent / REGISTRO_VINCULOS_FILE
        if registro.exists():
            ws.vinculos_compartidos = registro
        snapshot = load_source_run(ws, ws.active_run_id)
        ws.active_run = lambda: snapshot
        resultado['source_tuple'] = [snapshot.run_id, snapshot.mode, snapshot.fingerprint]
        manifest = json.loads((snapshot.root / 'source_manifest.json').read_text(encoding='utf-8'))
        if snapshot.run_id != ws.active_run_id or len(snapshot.files) != len(manifest.get('files') or []):
            raise ValueError('identidad ambigua del manifiesto o slots repetidos')
        if fingerprint(snapshot.mode, list(snapshot.files.values())) != snapshot.fingerprint:
            raise ValueError('huella agregada de fuente inválida')
        for item in snapshot.files.values():
            evidencia = {'ruta': str(item.path.resolve()), 'sha256': item.sha256,
                         'bytes': item.size, 'localizador': item.slot}
            verificar_fuente(evidencia)
            resultado['fuentes'].append(evidencia)
        binding = require_project_binding(ws, project, feeders)
        if snapshot.run_id != binding.source_run_id:
            raise ValueError('replay exige source_run_id exacto, aunque otra carga conserve la huella')
        resultado['binding_sha256'] = binding.binding_sha256
        resultado['workspace_custodia'] = custodiar(p, localizador='workspace de preaceptación')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        bloqueos.append(str(exc))
    if not evidencias:
        bloqueos.append('falta evidencia custodiada del caso y periodo declarados')
    for evidencia in evidencias:
        try:
            verificar_fuente(evidencia['custodia'])
            esperado = {'project': project, 'caso': caso, 'periodo': periodo,
                        'source_tuple': resultado.get('source_tuple')}
            if evidencia.get('contexto') != esperado:
                raise ValueError('evidencia de otro proyecto, caso, periodo o fuente')
            resultado['evidencias'].append(evidencia)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            bloqueos.append(str(exc))
    if requiere_ml:
        from convertersmartgrid.training_coordinator import exigir_memoria_ml
        try:
            resultado['recursos_ml'] = exigir_memoria_ml(6., minimo_commit_gib=8.)
        except (OSError, ValueError, RuntimeError) as exc:
            bloqueos.append(str(exc))
    resultado['listo_diagnostico'] = not bloqueos
    resultado['estado'] = 'LISTO_DIAGNOSTICO' if not bloqueos else 'BLOQUEADO_PREACEPTACION'
    return resultado


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--project', required=True)
    p.add_argument('--alimentador', action='append', required=True)
    p.add_argument('--caso', required=True)
    p.add_argument('--periodo', required=True)
    p.add_argument('--evidencias', type=Path, required=True,
                   help='JSON [{custodia:{ruta,sha256,bytes,localizador},contexto:{project,caso,periodo,source_tuple}}]')
    p.add_argument('--requiere-ml', action='store_true')
    p.add_argument('--output-json', type=Path, help='Informe nuevo fuera del checkout')
    args = p.parse_args(argv)
    if args.output_json and (args.output_json.exists() or ROOT in args.output_json.resolve().parents):
        p.error('el informe debe ser nuevo y estar fuera del checkout')
    try:
        evidencias = json.loads(args.evidencias.read_text(encoding='utf-8-sig'))
        if not isinstance(evidencias, list):
            raise TypeError('evidencias debe ser una lista de custodias')
        resultado = preaceptar(args.workspace, args.project, args.alimentador, caso=args.caso,
            periodo=args.periodo, evidencias=evidencias, requiere_ml=args.requiere_ml)
    except (OSError, ValueError, TypeError) as exc:
        p.error(str(exc))
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with args.output_json.open('x', encoding='utf-8') as f:
            f.write(texto + '\n')
    print(texto)
    return 0 if resultado['listo_diagnostico'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
