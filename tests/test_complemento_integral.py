"""086:RF-37/39/44: capacidades opcionales offline, con cierre y procedencia."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from apoyo import cargar_herramienta

CC = cargar_herramienta('construir_candidato.py')
IC = cargar_herramienta('instalar_candidato.py')


def _wheel(cache, name, requires=(), version='1.0', license='MIT', tag='py3-none-any'):
    path = cache / f'{name.replace("-", "_")}-{version}-{tag}.whl'
    info = f'{name.replace("-", "_")}-{version}.dist-info'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(f'{info}/METADATA', f'Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n'
                   f'License-Expression: {license}\nProvides-Extra: mapa\n' + ''.join(f'Requires-Dist: {r}\n' for r in requires))
        z.writestr(f'{info}/WHEEL', f'Wheel-Version: 1.0\nGenerator: prueba\nRoot-Is-Purelib: true\nTag: {tag}\n')
        z.writestr(f'{info}/licenses/LICENSE', 'Permiso del titular de prueba.\n')
    return path


@pytest.fixture
def sources(tmp_path):
    source, cache = tmp_path / 'source', tmp_path / 'cache'
    source.mkdir()
    cache.mkdir()
    (source / 'pyproject.toml').write_text('''[project.optional-dependencies]
ml = ["torch>=1", "peft>=1", "bitsandbytes>=1", "git-model @ git+https://example.org/model.git@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
preview = ["mapa[mapa]>=1"]
dev = ["pytest>=1"]
''', encoding='utf-8')
    for group, name in [('motores', 'motor'), ('madrl', 'madrl'), ('mcp', 'mcp'), ('drivers', 'driver')]:
        (source / f'requirements-{group}.txt').write_text(f'{name}>=1\n', encoding='utf-8')
    (source / 'requirements-nucleo.lock').write_text('comun==1.0 \\\n+    --hash=sha256:base\n', encoding='utf-8')
    names = ['torch', 'peft', 'bitsandbytes', 'git-model', 'mapa', 'motor', 'madrl', 'mcp', 'driver', 'comun', 'extra-mapa', 'pytest']
    for name in names:
        _wheel(cache, name, ['extra-mapa; extra == "mapa"', 'ausente; sys_platform == "linux"'] if name == 'mapa' else ['comun>=1'] if name == 'peft' else [])
    freeze = tmp_path / 'freeze.txt'
    freeze.write_text('\n'.join(f'{n}==1.0' for n in names) + '\n', encoding='utf-8')
    provenance = tmp_path / 'origins.json'
    git = cache / 'git_model-1.0-py3-none-any.whl'
    provenance.write_text(json.dumps([{'name': 'git-model', 'version': '1.0', 'url': 'https://example.org/model.git',
        'commit_id': 'a' * 40, 'wheel': git.name, 'sha256': hashlib.sha256(git.read_bytes()).hexdigest()}]), encoding='utf-8')
    return source, cache, freeze, provenance


def test_integral_cierra_extras_y_grupos_sin_herramientas_de_desarrollo(sources, tmp_path):
    """086:RF-37/39/44 — las raíces y sus transitivas reales determinan las ruedas entregadas."""
    source, cache, freeze, provenance = sources
    output = tmp_path / 'output'
    manifest = CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
        capacidades='integrales', versiones=freeze, procedencias=provenance)
    names = {CC._nombre_y_version(w.name)[0] for w in (output / 'wheels').glob('*.whl')}
    assert names == {'torch', 'peft', 'bitsandbytes', 'git-model', 'mapa', 'motor', 'madrl', 'mcp', 'driver', 'comun', 'extra-mapa'}
    assert manifest['capacidades'] == 'integrales'
    assert not manifest['modelos_activados'] and not manifest['pesos_del_proyecto_incluidos']
    assert manifest['proyecto_completo'] is False
    coverage = json.loads((output / 'cobertura.json').read_text(encoding='utf-8'))
    assert set(coverage['grupos']) == {'ml', 'preview', 'motores', 'madrl', 'mcp', 'drivers'}
    assert coverage['procedencias'][0]['commit_id'] == 'a' * 40
    bom = json.loads((output / 'sbom.cdx.json').read_text(encoding='utf-8'))
    git = next(c for c in bom['components'] if c['name'] == 'git-model')
    assert 'purl' not in git
    assert git['externalReferences'] == [{'type': 'vcs', 'url': 'https://example.org/model.git'}]
    assert git['properties'] == [{'name': 'git_commit', 'value': 'a' * 40}]
    assert IC.verificar_candidato(output)['version'] == '1.0rc6'
    _wheel(output / 'wheels', 'intruso')
    with pytest.raises(IC.ErrorInstalacion, match='extra|declarad'):
        IC.verificar_candidato(output)


def test_torch_cuda_del_cdn_del_indice_oficial(sources):
    """086:RF-39 — el índice oficial de PyTorch enlaza también su CDN download-r2."""
    source, cache, freeze, provenance = sources
    (cache / 'torch-1.0-py3-none-any.whl').unlink()
    wheel = _wheel(cache, 'torch', version='1.0+cu126')
    freeze.write_text(freeze.read_text(encoding='utf-8').replace('torch==1.0\n', 'torch==1.0+cu126\n'), encoding='utf-8')
    origins = json.loads(provenance.read_text(encoding='utf-8'))
    origins.append({'name': 'torch', 'version': '1.0+cu126', 'wheel': wheel.name,
        'url': f'https://download-r2.pytorch.org/whl/cu126/{wheel.name}',
        'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()})
    provenance.write_text(json.dumps(origins), encoding='utf-8')
    selected, coverage = CC.seleccionar_capacidades_integrales(source, [cache], freeze, provenance)
    assert wheel.resolve() in selected
    assert len(coverage['procedencias']) == 2


def test_metadatos_con_licencia_utf8(tmp_path):
    """086:RF-44 — las cabeceras License UTF-8 también se conservan como texto."""
    path = tmp_path / 'ejemplo-1.0-py3-none-any.whl'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('ejemplo-1.0.dist-info/METADATA', 'Name: ejemplo\nVersion: 1.0\nLicense: MIT — permiso\n')
    metadata, _ = CC.leer_metadatos_de_rueda(path)
    assert metadata['license'] == 'MIT — permiso'


@pytest.mark.parametrize('altered', [False, True])
def test_licencia_suplementaria_con_huellas_de_rueda_y_texto(sources, tmp_path, altered):
    """086:RF-44 — el permiso obtenido del origen versionado se entrega y no puede alterarse."""
    source, cache, freeze, provenance = sources
    wheel = _wheel(cache, 'peft', license='')
    text = tmp_path / 'LICENSE.txt'
    text.write_text('Permiso externo del titular, versión evaluada.\n', encoding='utf-8')
    licenses = tmp_path / 'licenses.json'
    licenses.write_text(json.dumps({'packages': [{'name': 'peft', 'version': '1.0',
        'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'license': 'MIT',
        'texts': [{'path': text.name, 'sha256': hashlib.sha256(text.read_bytes()).hexdigest(),
                   'source_url': 'https://example.org/version/1.0/LICENSE', 'source_sha256': hashlib.sha256(text.read_bytes()).hexdigest()}]}]}), encoding='utf-8')
    if altered:
        text.write_text('Alterado', encoding='utf-8')
        with pytest.raises(CC.CE.EntregaError, match='licencia|huella'):
            CC.construir_complemento_ia(source, tmp_path / 'output', cache=cache, version='1.0rc6',
                capacidades='integrales', versiones=freeze, procedencias=provenance, licencias=licenses)
    else:
        output = tmp_path / 'output'
        manifest = CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
            capacidades='integrales', versiones=freeze, procedencias=provenance, licencias=licenses)
        assert 'Permiso externo del titular' in (output / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8')
        assert manifest['capacidades'] == 'integrales'


@pytest.mark.parametrize('case', ['missing', 'constraint', 'license', 'source', 'abi', 'remote', 'digest', 'commit', 'core', 'python', 'duplicate'])
def test_integral_falla_cerrado_sin_publicar_manifest(sources, tmp_path, case):
    """086:RF-39/44 — una rueda o procedencia insegura impide publicar el complemento."""
    source, cache, freeze, provenance = sources
    match = {'missing': 'Falta|falta', 'constraint': 'incompatible', 'license': 'licencia',
             'source': 'procedencia|commit', 'abi': 'compatible|plataforma', 'remote': 'URL|remot',
             'digest': 'Huella|huella', 'commit': 'commit', 'core': 'incompatible', 'python': 'Python incompatible',
             'duplicate': 'única'}[case]
    if case == 'missing':
        (cache / 'peft-1.0-py3-none-any.whl').unlink()
    elif case == 'constraint':
        _wheel(cache, 'peft', ['comun>=2'])
    elif case == 'license':
        _wheel(cache, 'peft', license='')
    elif case == 'source':
        provenance.write_text('[]', encoding='utf-8')
    elif case == 'abi':
        (cache / 'peft-1.0-py3-none-any.whl').unlink()
        _wheel(cache, 'peft', tag='cp313-cp313-win_amd64')
    elif case == 'remote':
        _wheel(cache, 'peft', ['comun @ https://example.org/untrusted.whl'])
    elif case in ('digest', 'commit'):
        origins = json.loads(provenance.read_text(encoding='utf-8'))
        origins[0]['sha256' if case == 'digest' else 'commit_id'] = 'b' * (64 if case == 'digest' else 40)
        provenance.write_text(json.dumps(origins), encoding='utf-8')
    elif case == 'core':
        (source / 'requirements-nucleo.lock').write_text('comun==2.0\n', encoding='utf-8')
    elif case == 'python':
        path = cache / 'peft-1.0-py3-none-any.whl'
        with zipfile.ZipFile(path) as z:
            entries = {n: z.read(n) for n in z.namelist()}
        name = 'peft-1.0.dist-info/METADATA'
        entries[name] += b'Requires-Python: >=3.13\n'
        with zipfile.ZipFile(path, 'w') as z:
            for n, data in entries.items():
                z.writestr(n, data)
    elif case == 'duplicate':
        _wheel(cache, 'peft', tag='py312-none-any')
    output = tmp_path / 'output'
    with pytest.raises(CC.CE.EntregaError, match=match):
        CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
            capacidades='integrales', versiones=freeze, procedencias=provenance)
    assert not (output / 'manifiesto_candidato.json').exists()
