"""Spec 026 (RF-3): la medida de los modelos de Ollama como intérpretes, sin razonamiento previo."""
from __future__ import annotations

import json

from apoyo import cargar_herramienta


def test_se_mide_sin_razonar_y_se_guarda_asi(tmp_path, monkeypatch):
    """026:RF-3 — qwen3:8b razonaba antes de cada orden (48 de 144 sin respuesta, 2026-11-07): se mide con `pensar=False`
    y el elegido queda con esa opción para la web."""
    from convertersmartgrid.asistente import ollama

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    creados = []

    class Falso:
        def __init__(self, modelo='', tiempo_max_s=30.0, pensar=None, **_k):
            self.modelo, self.pensar = modelo, pensar
            creados.append(self)

        def modelos(self):
            return ['qwen3:8b', 'llama3.1:8b']

        def interpretar(self, texto):
            return {'tarea': 'estado', 'confianza': 1.0, 'datos': {}}

    monkeypatch.setattr(ollama, 'ClienteOllama', Falso)
    herramienta = cargar_herramienta('asistente_medir_ollama.py')
    salida = tmp_path / 'medida.json'
    assert herramienta.main(['--output-json', str(salida), '--modelos', 'qwen3:8b', 'llama3.1:8b', '--por-tarea', '1']) == 0
    medidos = creados[1:]                                  # el primero solo lista los instalados
    assert medidos and all(c.pensar is False for c in medidos)
    assert json.loads((tmp_path / 'ollama.json').read_text(encoding='utf-8'))['pensar'] is False
