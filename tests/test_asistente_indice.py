"""Spec 026, T8: el índice del proyecto y las respuestas con cita."""
from __future__ import annotations

from pathlib import Path

from igea_dgs.asistente import indice

RAIZ = Path(__file__).resolve().parents[1]


def _repo(tmp_path: Path) -> Path:
    (tmp_path / 'src' / 'pkg').mkdir(parents=True)
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'specs' / '099-prueba').mkdir(parents=True)
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'CODIGO_FUENTE.md').write_text('| `src/pkg/barra.py` | Calibra una barra sin medidor repartiendo '
                                               'la medida de la SET por potencia instalada. | 099 (RF-1) |\n',
                                               encoding='utf-8')
    (tmp_path / 'src' / 'pkg' / 'barra.py').write_text(
        '"""Reparto de la barra."""\n\ndef repartir():\n    """Reparte la medida de la barra entre los '
        'alimentadores sin medidor por su potencia instalada."""\n', encoding='utf-8')
    (tmp_path / 'specs' / '099-prueba' / 'spec.md').write_text(
        '- RF-1: EL SISTEMA repartirá la medida de la barra entre los alimentadores sin medidor\n'
        '  por su potencia instalada.\n', encoding='utf-8')
    (tmp_path / 'docs' / 'MANUAL_COMANDOS.md').write_text('# Manual\n\nNada de interés.\n', encoding='utf-8')
    return tmp_path


def test_indice_con_specs_codigo_y_manual(tmp_path, monkeypatch):
    """026:RF-17 — el índice trae CODIGO_FUENTE, cada RF, cada docstring y el manual, y se
    reconstruye cuando cambia un fichero."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'datos'))
    repo = _repo(tmp_path / 'repo')
    i = indice.cargar_o_construir(repo)
    fuentes = {f.fuente.split(':')[0] for f in i.frags}
    assert {'CODIGO_FUENTE.md', 'src/pkg/barra.py', 'specs/099-prueba/spec.md', 'docs/MANUAL_COMANDOS.md'} <= fuentes
    assert any('099-prueba RF-1' in f.texto and 'potencia instalada' in f.texto for f in i.frags)
    h = indice.huella(repo)
    (repo / 'src' / 'pkg' / 'nuevo.py').write_text('"""Módulo nuevo de transferencias."""\n', encoding='utf-8')
    assert indice.huella(repo) != h
    i2 = indice.cargar_o_construir(repo)
    assert any('transferencias' in f.texto for f in i2.frags)


def test_responde_con_cita_o_no_lo_sabe(tmp_path, monkeypatch):
    """026:RF-18 — la respuesta cita fichero y línea; si nada responde, «No lo sé»."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'datos'))
    i = indice.cargar_o_construir(_repo(tmp_path / 'repo'))
    r = indice.responder(i, '¿cómo se reparte la medida de la barra en alimentadores sin medidor?')
    assert r['sabe'] and r['citas'] and any(c['fuente'].startswith('specs/099-prueba/spec.md:') for c in r['citas'])
    assert '[1]' in r['respuesta']
    r = indice.responder(i, 'receta de la tortilla de patatas')
    assert not r['sabe'] and r['respuesta'].startswith('No lo sé') and not r['citas']


def test_el_proyecto_real_se_indexa(tmp_path, monkeypatch):
    """026:RF-17 / 026:RF-18 — con el repositorio real, una pregunta del gemelo cita su spec."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'datos'))
    i = indice.construir(RAIZ)
    r = indice.responder(i, 'flujo de carga por matriz de admitancias con lazos del gemelo')
    assert r['sabe'] and any('flujo.py' in c['fuente'] or '024' in c['texto'] for c in r['citas'])


class _Redactor:
    modelo = 'falso'

    def __init__(self, texto):
        self.texto = texto

    def responder(self, pregunta, contexto):
        return self.texto


def test_cita_falsa_se_cambia_por_los_trozos(tmp_path, monkeypatch):
    """027:RF-41 — una respuesta con una cita que no existe o que no apoya su frase se cambia
    por los trozos citados; con citas que la apoyan, se deja."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'datos'))
    i = indice.cargar_o_construir(_repo(tmp_path / 'repo'))
    pregunta = '¿cómo se reparte la medida de la barra en alimentadores sin medidor?'
    buena = ('La medida de la barra se reparte entre los alimentadores sin medidor por su potencia '
             'instalada [1].')
    r = indice.responder(i, pregunta, _Redactor(buena))
    assert r['redactada_por'] == 'falso' and 'citas_sin_apoyo' not in r
    falsa = 'Las tortillas llevan huevo y patatas fritas en aceite de oliva caliente [1]. Y cebolla [9].'
    r = indice.responder(i, pregunta, _Redactor(falsa))
    assert r['redactada_por'] is None and r['respuesta'].startswith('[1]')
    assert any('[9] no está' in p for p in r['citas_sin_apoyo']) and any('[1] no apoya' in p for p in r['citas_sin_apoyo'])


def test_medicion_de_las_consultas(tmp_path, monkeypatch):
    """027:RF-42 — la fracción respondida con la cita esperada y la de «No lo sé» acertados."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'datos'))
    i = indice.cargar_o_construir(_repo(tmp_path / 'repo'))
    m = indice.medir(i, [{'pregunta': '¿cómo se reparte la medida de la barra sin medidor?', 'fuente': 'specs/099-prueba'},
                         {'pregunta': 'receta de la tortilla de patatas', 'fuente': None},
                         {'pregunta': 'potencia instalada del reparto de la barra', 'fuente': 'no/existe.py'}])
    assert m == {'preguntas': 3, 'con_cita_correcta': 0.5, 'no_lo_se_acertados': 1.0}
