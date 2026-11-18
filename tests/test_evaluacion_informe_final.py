"""044:RF-10, RF-11: el informe único de la evaluación final de la 1.0 y su rechazo si la revisión o una huella no cuadran.

Sobre un repositorio git de juguete en ``tmp_path``: sin datos de la distribuidora, sin GPU ni DIgSILENT.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.evaluacion_harness import informe_final as inf


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / 'repo'
    r.mkdir()
    _git(r, 'init', '-q')
    _git(r, 'config', 'user.email', 'prueba@ejemplo.invalid')
    _git(r, 'config', 'user.name', 'prueba')
    (r / 'docs').mkdir()
    (r / 'docs' / 'leeme.txt').write_text('x', encoding='utf-8')
    _git(r, 'add', '.')
    _git(r, 'commit', '-q', '-m', 'inicio')
    return r


@pytest.fixture
def conjunto(tmp_path):
    ruta = tmp_path / 'sellados' / 'humanas_final.jsonl'
    ruta.parent.mkdir()
    ruta.write_text('{"texto": "convierte AB101"}\n', encoding='utf-8')
    return ruta


def _entrada(repo: Path, conjunto: Path) -> dict:
    rev = _git(repo, 'rev-parse', 'HEAD')
    return {
        'rev': rev,
        'conjuntos': {'humanas_final': {'ruta': str(conjunto), 'sha256': hashlib.sha256(conjunto.read_bytes()).hexdigest(),
                                        'n': 1}},
        'bloques': {
            'M1_interprete': {'rev': rev, 'medidas': {
                'acierto_tarea_frente_e5': {'valor': 0.91, 'ic95': [0.87, 0.94], 'n': 300, 'metodo_ic': 'wilson',
                                            'prueba': 'mcnemar_exacta', 'p': 0.01, 'conjunto': 'humanas_final',
                                            'hipotesis': 'el candidato acierta más que e5+LR', 'negativo': False},
                'acierto_tarea_frente_llm': {'valor': 0.91, 'ic95': [0.87, 0.94], 'n': 300, 'metodo_ic': 'wilson',
                                             'prueba': 'mcnemar_exacta', 'p': 0.04, 'conjunto': 'humanas_final',
                                             'hipotesis': 'el candidato acierta más que el LLM', 'negativo': True},
            }},
        },
    }


def test_consolida_rev_huellas_ic_holm_y_negativos(repo, conjunto):
    """044:RF-10: un único informe con rev, árbol limpio, huellas, n, IC, prueba, p ajustada por Holm y negativos."""
    entrada = _entrada(repo, conjunto)
    informe = inf.consolidar(entrada, repo=repo, rev=entrada['rev'])
    assert informe['esquema'] == inf.ESQUEMA and informe['rev'] == entrada['rev'] and informe['arbol_limpio'] is True
    assert informe['conjuntos']['humanas_final']['sha256'] == entrada['conjuntos']['humanas_final']['sha256']
    medidas = informe['medidas']['M1_interprete']
    assert medidas['acierto_tarea_frente_e5']['p_holm'] == pytest.approx(0.02)
    assert medidas['acierto_tarea_frente_llm']['p_holm'] == pytest.approx(0.04)
    assert medidas['acierto_tarea_frente_e5']['ic95'] == [0.87, 0.94] and medidas['acierto_tarea_frente_e5']['n'] == 300
    assert [(n['bloque'], n['metrica']) for n in informe['negativos']] == [('M1_interprete', 'acierto_tarea_frente_llm')]
    ruta = inf.escribir(informe, repo)
    assert ruta == repo / inf.DESTINO
    assert json.loads(ruta.read_text(encoding='utf-8')) == informe
    # Escribir el informe no ensucia el árbol para la relectura: solo cambia su propio fichero.
    inf.validar(json.loads(ruta.read_text(encoding='utf-8')), repo=repo)


def test_cada_medida_en_la_forma_que_lee_la_tesis(repo, conjunto):
    """044:RF-10: cada medida va como {valor, ic95, n} bajo su nombre, la forma de intervalo que ya lee el recolector."""
    entrada = _entrada(repo, conjunto)
    informe = inf.consolidar(entrada, repo=repo, rev=entrada['rev'])
    for bloque in informe['medidas'].values():
        for medida in bloque.values():
            assert set(medida) >= {'valor', 'ic95', 'n', 'prueba', 'p', 'p_holm', 'conjunto', 'negativo'}
            assert len(medida['ic95']) == 2 and medida['ic95'][0] <= medida['ic95'][1]


def test_rechaza_una_rev_distinta(repo, conjunto):
    """044:RF-11: si la rev declarada no es el HEAD del repositorio, el informe se rechaza y no se escribe."""
    entrada = _entrada(repo, conjunto)
    otra = 'f' * 40
    with pytest.raises(inf.InformeRechazado, match='rev'):
        inf.consolidar(entrada, repo=repo, rev=otra)
    mala = copy.deepcopy(entrada)
    mala['bloques']['M1_interprete']['rev'] = otra
    with pytest.raises(inf.InformeRechazado, match='M1_interprete'):
        inf.consolidar(mala, repo=repo, rev=entrada['rev'])
    assert not (repo / inf.DESTINO).exists()


def test_rechaza_una_huella_alterada(repo, conjunto):
    """044:RF-11: si el conjunto cambió después de sellarlo, la huella no cuadra y el informe se rechaza."""
    entrada = _entrada(repo, conjunto)
    conjunto.write_text('{"texto": "convierte CD202"}\n', encoding='utf-8')
    with pytest.raises(inf.InformeRechazado, match='humanas_final'):
        inf.consolidar(entrada, repo=repo, rev=entrada['rev'])
    # Y si el informe ya escrito se altera, su relectura también lo rechaza.
    conjunto.write_text('{"texto": "convierte AB101"}\n', encoding='utf-8')
    informe = inf.consolidar(entrada, repo=repo, rev=entrada['rev'])
    alterado = copy.deepcopy(informe)
    alterado['conjuntos']['humanas_final']['sha256'] = '0' * 64
    with pytest.raises(inf.InformeRechazado, match='humanas_final'):
        inf.validar(alterado, repo=repo)


def test_rechaza_arbol_sucio(repo, conjunto):
    """044:RF-11: con cambios sin commit en el árbol, la evaluación no corresponde a la rev y se rechaza."""
    entrada = _entrada(repo, conjunto)
    (repo / 'docs' / 'leeme.txt').write_text('cambiado', encoding='utf-8')
    with pytest.raises(inf.InformeRechazado, match='árbol'):
        inf.consolidar(entrada, repo=repo, rev=entrada['rev'])


def test_relectura_rechaza_codigo_cambiado_despues(repo, conjunto):
    """044:RF-11: tras la rev solo puede cambiar el propio informe; otro commit con código invalida la relectura."""
    entrada = _entrada(repo, conjunto)
    informe = inf.consolidar(entrada, repo=repo, rev=entrada['rev'])
    inf.escribir(informe, repo)
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-q', '-m', 'informe')
    inf.validar(informe, repo=repo)
    (repo / 'codigo.py').write_text('print(1)\n', encoding='utf-8')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-q', '-m', 'código')
    with pytest.raises(inf.InformeRechazado, match='codigo.py'):
        inf.validar(informe, repo=repo)


def test_rechaza_medidas_incompletas(repo, conjunto):
    """044:RF-10: una medida sin n, sin IC, con un conjunto no declarado o sin decir si es negativa no entra."""
    entrada = _entrada(repo, conjunto)
    for campo, valor in (('n', None), ('ic95', [0.9]), ('conjunto', 'otro'), ('negativo', None), ('p', 1.5),
                         ('valor', float('nan'))):
        mala = copy.deepcopy(entrada)
        medida = mala['bloques']['M1_interprete']['medidas']['acierto_tarea_frente_e5']
        if valor is None:
            medida.pop(campo)
        else:
            medida[campo] = valor
        with pytest.raises(inf.InformeRechazado):
            inf.consolidar(mala, repo=repo, rev=entrada['rev'])


def test_herramienta_consolida_y_comprueba(repo, conjunto, tmp_path):
    """044:RF-10, RF-11: ``tools/evaluacion_final.py`` escribe el informe y ``--comprobar`` lo relee."""
    import importlib.util
    raiz = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('evaluacion_final', raiz / 'tools' / 'evaluacion_final.py')
    herramienta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(herramienta)
    entrada = _entrada(repo, conjunto)
    ruta = tmp_path / 'entrada.json'
    ruta.write_text(json.dumps(entrada), encoding='utf-8')
    assert herramienta.main(['--entrada', str(ruta), '--repo', str(repo), '--rev', entrada['rev']]) == 0
    assert herramienta.main(['--comprobar', '--repo', str(repo)]) == 0
    assert herramienta.main(['--entrada', str(ruta), '--repo', str(repo), '--rev', 'e' * 40]) == 1
