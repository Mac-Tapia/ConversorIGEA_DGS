"""047:RF-38 / RF-43 — la T8 se mide con un conjunto nuevo, declarado antes de medir y fijado por su huella.

Los 12 casos del 2026-11-03 orientaron el diagnóstico de la T8, así que la medida que la cierra es con
`docs/REVISION_ROLES_CASOS_047b.json`. Aquí no hay Ollama: el cliente es falso y solo prueba el camino de la
herramienta (qué conjunto se mide, con qué huella, cuándo no se mide); no acredita la calidad de ningún LLM.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
from pathlib import Path
import re

import pytest

RAIZ = Path(__file__).resolve().parents[1]
NUEVO = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047b.json'
#: Declarada el 2026-11-19 antes de medir; si el conjunto cambia, esta prueba lo dice (047:RF-43).
HUELLA_047B = '54f2a035bc7c173d87830a5faaf2e5fdca79851df448abb854efff60e2f4e910'
#: Distribuidoras y generadoras del país, por la huella sha256 (16 primeras cifras) de su nombre en minúsculas: ningún
#: caso sintético las nombra y el repositorio público tampoco las escribe. Más la forma de razón social (s.a., s.a.a.).
HUELLAS_EMPRESAS = frozenset({
    '091d17b796e0ff23', '0c5d30a5384dc504', '1321de9d4d0c0ca1', '21b54ba286c5cfd5',
    '343a94b1664ba820', '36777843cab9cb0f', '38e2f0c32250ef22', '3adb2c360f695813',
    '468b1c53c8d79d78', '4ea1cb4445a496aa', '6089d2678baafca8', '68ee314367b7b2b6',
    '7ac270e60f6d25d2', '8c44285051dd10df', '8f68a64cdce4f2da', '8f9a8ca0f4158013',
    '9bba7092a276327e', 'a9586690262ee5d0', 'c33153aa1f430e90', 'c3f01efafd801e51',
    'c927c7179f07ee61', 'e6ba15f112864ec5', 'e76c842eec933a10', 'ea4c24d46eb55761',
    'f0f668bf610e5cf9',
})
RAZON_SOCIAL = re.compile(r'(?<![a-záéíóúñ])s\.a\.(?:a\.)?(?![a-záéíóúñ])')


def _herramienta():
    ruta = RAIZ / 'tools/asistente_comparar_revision.py'
    spec = importlib.util.spec_from_file_location('comparar_revision_047b', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _main(herramienta, argv) -> int:
    try:
        return herramienta.main(argv)
    except SystemExit as e:       # argparse: una opción que no conoce
        return int(e.code or 0)


def _huella_sin_declaracion(contenido: dict) -> str:
    cuerpo = {k: v for k, v in contenido.items() if k != 'declaracion'}
    return hashlib.sha256(json.dumps(cuerpo, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _leer(herramienta, ruta):
    assert 'ruta' in inspect.signature(herramienta.leer_casos).parameters, 'leer_casos no acepta otro conjunto'
    return herramienta.leer_casos(ruta)


@pytest.fixture
def ollama_falso(monkeypatch):
    """ClienteOllama de verdad con un ``abrir`` falso: dictamen favorable con toda la evidencia, sin red ni GPU."""
    from convertersmartgrid.aplicacion import trabajadores_ml
    from convertersmartgrid.aplicacion.asistente import ollama
    peticiones = []

    def abrir(peticion, timeout):
        peticiones.append(peticion.full_url)
        if peticion.full_url.endswith('/api/tags'):
            return io.BytesIO(json.dumps({'models': [{'name': 'falso:1'}]}).encode())
        cuerpo = json.loads(peticion.data)
        evidencia = json.loads(cuerpo['messages'][-1]['content'])['evidencia']
        dictamen = {'contradicciones': [], 'incertidumbres': [], 'evidencia_ids': sorted(evidencia),
                    'decision': 'favorable'}
        return io.BytesIO(json.dumps({'message': {'content': json.dumps(dictamen)}, 'prompt_eval_count': 100,
                                      'eval_count': 10}).encode())

    class Falso(ollama.ClienteOllama):
        def __init__(self, *a, **k):
            super().__init__(*a, **{**k, 'abrir': abrir})

    monkeypatch.delenv(getattr(ollama, 'VARIABLE_APAGADO', 'CSG_OLLAMA'), raising=False)
    monkeypatch.setattr(ollama, 'ClienteOllama', Falso)
    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', lambda nombre: contextlib.nullcontext())
    return peticiones


def test_conjunto_047b_declarado_antes_de_medir_y_fijo():
    """047:RF-43 — su huella está en la herramienta, en el propio fichero y en la T8 de la spec, con la fecha."""
    herramienta = _herramienta()
    contenido = json.loads(NUEVO.read_text(encoding='utf-8'))
    assert getattr(herramienta, 'DECLARADOS', {}).get(NUEVO.name) == HUELLA_047B
    assert _huella_sin_declaracion(contenido) == HUELLA_047B, 'el conjunto 047b cambió después de declararse'
    declaracion = contenido['declaracion']
    assert declaracion['sha256'] == HUELLA_047B and declaracion['fecha'] == '2026-11-19'
    assert declaracion['origen'] == 'maestro' and 'maestro' in contenido['descripcion']
    assert herramienta.huella(NUEVO) == HUELLA_047B
    tareas = next((RAIZ / 'specs').glob('047-*')) / 'tasks.md'
    t8 = tareas.read_text(encoding='utf-8').split('- [ ] T8.', 1)[1].split('\n- [', 1)[0]
    assert HUELLA_047B in t8 and '2026-11-19' in t8 and 'REVISION_ROLES_CASOS_047b.json' in t8


def test_conjunto_047b_seis_sanos_seis_con_defecto_opacos_y_sinteticos(tmp_path):
    """047:RF-39 / RF-43 — 6 y 6, un defecto por caso, nombres opacos y ningún nombre de empresa real."""
    herramienta = _herramienta()
    casos = _leer(herramienta, NUEVO)
    assert len(casos) == 12
    assert sum(c['defecto'] is None for c in casos) == 6 and sum(c['defecto'] is not None for c in casos) == 6
    assert {c['defecto'] for c in casos if c['defecto']} <= herramienta.DEFECTOS - {None}
    viejos = {c['propuesta']['accion'] for c in _leer(herramienta, herramienta.CONJUNTO)}
    assert not viejos & {c['propuesta']['accion'] for c in casos}, 'el conjunto nuevo repite propuestas del viejo'
    texto = json.dumps([{k: c[k] for k in ('id', 'propuesta', 'evidencia')} for c in casos], ensure_ascii=False).lower()
    assert not re.search(r'sano|defecto|fisica|física|coste-|riesgo-|fuentes-', ' '.join(c['id'] for c in casos))
    assert 'sano' not in texto and 'defecto' not in texto
    palabras = re.findall(r'[a-záéíóúñ]+', texto)
    for n in range(1, 5):
        for i in range(len(palabras) - n + 1):
            grupo = ' '.join(palabras[i:i + n])
            huella = hashlib.sha256(grupo.encode('utf-8')).hexdigest()[:16]
            assert huella not in HUELLAS_EMPRESAS, f'nombre de empresa en la palabra {i}'
    assert not RAZON_SOCIAL.search(texto)
    for caso in herramienta.materializar(casos, tmp_path):
        assert not re.search(r'sano|defecto', caso['contexto'].project)
    assert all(not re.search(r'sano|defecto', f.name) for f in tmp_path.iterdir())


def test_conjunto_elegido_se_mide_y_su_huella_va_al_informe(tmp_path, ollama_falso):
    """047:RF-43 — `--conjunto` mide ese conjunto y el informe dice cuál y con qué huella."""
    herramienta = _herramienta()
    salida = tmp_path / 'informe.json'
    rc = _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(NUEVO), '--salida', str(salida)])
    assert rc == 0
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['conjunto'] == NUEVO.name and informe['conjunto_sha256'] == HUELLA_047B
    assert informe['casos'] == 12 and informe['con_defecto'] == 6 and informe['modelo'] == 'falso:1'
    # El falso aprueba todo: 0 falsas alarmas y los 6 defectos perdidos; mide el camino, no la revisión.
    for modo in ('rol_unico', 'equipo'):
        assert informe[modo]['falsas_alarmas'] == 0 and informe[modo]['perdidos'] == 6
    assert informe['autoriza_ejecucion'] is False
    assert sum(u.endswith('/api/chat') for u in ollama_falso) > 0


def test_sin_conjunto_se_mide_el_de_siempre(capsys):
    """047:RF-43 — sin `--conjunto`, los casos de siempre y su huella; el informe dice cuál."""
    herramienta = _herramienta()
    assert _main(herramienta, ['--solo-conjunto']) == 0
    resumen = json.loads(capsys.readouterr().out)
    assert resumen.get('conjunto') == 'REVISION_ROLES_CASOS_047.json'
    assert resumen['conjunto_sha256'] == herramienta.HUELLA


def test_conjunto_con_otra_huella_o_sin_declarar_no_se_mide(tmp_path, capsys, ollama_falso):
    """047:RF-38 / RF-43 — tocar un caso después de declararlo, o no declararlo, no se mide: error claro y nada al LLM."""
    herramienta = _herramienta()
    contenido = json.loads(NUEVO.read_text(encoding='utf-8'))
    contenido['casos'][0]['evidencia']['e1'] += ' Retocado después de declarar.'
    tocado = tmp_path / NUEVO.name
    tocado.write_text(json.dumps(contenido, ensure_ascii=False), encoding='utf-8')
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(tocado), '--salida', str(salida)]) == 2
    assert 'no es el declarado' in capsys.readouterr().err
    assert not salida.exists() and not ollama_falso
    sin_declarar = tmp_path / 'otros_casos.json'
    sin_declarar.write_text(json.dumps({k: v for k, v in contenido.items() if k != 'declaracion'}, ensure_ascii=False),
                            encoding='utf-8')
    assert _main(herramienta, ['--solo-conjunto', '--conjunto', str(sin_declarar)]) == 2
    assert 'sin huella declarada' in capsys.readouterr().err


def test_salida_existente_no_se_pisa(tmp_path, capsys, ollama_falso):
    """047:RF-43 — cada medición se hace una vez: un informe que ya existe se conserva tal cual."""
    herramienta = _herramienta()
    salida = tmp_path / 'informe.json'
    salida.write_text('{"previo": true}', encoding='utf-8')
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(NUEVO), '--salida', str(salida)]) == 2
    assert 'ya existe' in capsys.readouterr().err
    assert salida.read_text(encoding='utf-8') == '{"previo": true}' and not ollama_falso
