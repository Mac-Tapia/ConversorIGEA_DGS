"""086:RF-34/37/39/44: capacidades opcionales offline, con cierre y procedencia; modelos, avisos e instalador del complemento."""
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from apoyo import cargar_herramienta

CC = cargar_herramienta('construir_candidato.py')
IC = cargar_herramienta('instalar_candidato.py')


def _wheel(cache, name, requires=(), version='1.0', license='MIT', tag='py3-none-any', provides=('mapa',)):
    path = cache / f'{name.replace("-", "_")}-{version}-{tag}.whl'
    info = f'{name.replace("-", "_")}-{version}.dist-info'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(f'{info}/METADATA', f'Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n'
                   f'License-Expression: {license}\n' + ''.join(f'Provides-Extra: {e}\n' for e in provides)
                   + ''.join(f'Requires-Dist: {r}\n' for r in requires))
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
    names = ['torch', 'peft', 'bitsandbytes', 'git-model', 'mapa', 'motor', 'madrl', 'mcp', 'driver', 'comun', 'extra-mapa', 'pytest']
    for name in names:
        _wheel(cache, name, ['extra-mapa; extra == "mapa"', 'ausente; sys_platform == "linux"'] if name == 'mapa' else ['comun>=1'] if name == 'peft' else [])
    # El lock es una autoridad independiente: su SHA precede a cualquier alteración del ensayo.
    digest = hashlib.sha256((cache / 'comun-1.0-py3-none-any.whl').read_bytes()).hexdigest()
    (source / 'requirements-nucleo.lock').write_text('comun==1.0 ' + chr(92) + '\n    --hash=sha256:' + digest + '\n', encoding='utf-8')
    freeze = tmp_path / 'freeze.txt'
    freeze.write_text('\n'.join(f'{n}==1.0' for n in names) + '\n', encoding='utf-8')
    provenance = tmp_path / 'origins.json'
    git = cache / 'git_model-1.0-py3-none-any.whl'
    provenance.write_text(json.dumps([{'name': 'git-model', 'version': '1.0', 'url': 'https://example.org/model.git',
        'commit_id': 'a' * 40, 'wheel': git.name, 'sha256': hashlib.sha256(git.read_bytes()).hexdigest()}]), encoding='utf-8')
    return source, cache, freeze, provenance


def _suplemento(tmp_path, cache, filename='LICENSE.txt'):
    text = tmp_path / filename
    text.parent.mkdir(parents=True, exist_ok=True)
    text.write_text('Aviso sintético para verificar conservación de la licencia.\n', encoding='utf-8')
    digest = hashlib.sha256(text.read_bytes()).hexdigest()
    manifest = tmp_path / 'licencias_input.json'
    manifest.write_text(json.dumps({'packages': [{'name': 'peft', 'version': '1.0',
        'wheel_sha256': hashlib.sha256((cache / 'peft-1.0-py3-none-any.whl').read_bytes()).hexdigest(),
        'license': 'MIT', 'texts': [{'path': filename, 'sha256': digest,
            'source_url': 'https://example.org/v1/LICENSE', 'source_sha256': digest}]}]}), encoding='utf-8')
    return manifest


@pytest.mark.parametrize('relative_receipt', [False, True])
def test_procedencia_exportada_es_portatil_y_conserva_autoridad_real(sources, tmp_path, monkeypatch, relative_receipt):
    """086:RF-39/44: dos raíces privadas distintas no viajan dentro del paquete."""
    original_source, original_cache, original_freeze, original_provenance = sources
    exported = []
    for label in ('private_user_alpha', 'private_user_beta'):
        private = tmp_path / label
        private.mkdir()
        source, cache = private / 'source', private / 'cache'
        shutil.copytree(original_source, source)
        shutil.copytree(original_cache, cache)
        freeze = private / 'freeze.txt'
        freeze.write_bytes(original_freeze.read_bytes())
        receipt = private / 'private_receipt.json'
        receipt.write_text('{"origin":"authorized"}\n', encoding='utf-8')
        receipt_digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
        origins = json.loads(original_provenance.read_text(encoding='utf-8'))
        origins[0].update(receipt=receipt.name if relative_receipt else str(receipt),
                          receipt_sha256=receipt_digest, source_cache=str(cache), username=label)
        provenance = private / 'origins.json'
        provenance.write_text(json.dumps(origins), encoding='utf-8')
        original_receipt = receipt.read_bytes()
        original_provenance_bytes = provenance.read_bytes()
        cwd = private / 'different_working_directory'
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        monkeypatch.setenv('USERNAME', label)
        monkeypatch.setenv('CSG_CACHE_HOME', str(private / 'different_environment_cache'))
        output = tmp_path / ('delivery_' + label)
        CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
            capacidades='integrales', versiones=freeze, procedencias=provenance)
        coverage = json.loads((output / 'cobertura.json').read_text(encoding='utf-8'))
        public = coverage['procedencias'][0]
        for field in ('name', 'version', 'url', 'commit_id', 'wheel', 'sha256', 'receipt_sha256'):
            assert public[field] == origins[0][field]
        assert public['receipt'] == {'kind': 'external-file', 'sha256': receipt_digest}
        assert coverage['procedencias_sha256'] == hashlib.sha256(original_provenance_bytes).hexdigest()
        texts = '\n'.join(path.read_text(encoding='utf-8') for path in output.rglob('*')
                          if path.is_file() and path.suffix != '.whl')
        assert label not in texts and str(private) not in texts and 'source_cache' not in texts
        assert receipt.read_bytes() == original_receipt and provenance.read_bytes() == original_provenance_bytes
        assert IC.verificar_candidato(output)['capacidades'] == 'integrales'
        exported.append(public)
    assert exported[0] == exported[1]


@pytest.mark.parametrize('mutation', ['content_same_stat', 'digest', 'missing'])
def test_recibo_de_procedencia_mutado_no_publica_paquete(sources, tmp_path, mutation):
    """086:RF-39/44: el SHA publicado sigue siendo el del recibo externo efectivamente leído."""
    source, cache, freeze, provenance = sources
    receipt = tmp_path / 'origin.json'
    receipt.write_text('{"origin":"ok"}\n', encoding='utf-8')
    stat = receipt.stat()
    origins = json.loads(provenance.read_text(encoding='utf-8'))
    origins[0].update(receipt=str(receipt), receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
    if mutation == 'content_same_stat':
        receipt.write_text('{"origin":"no"}\n', encoding='utf-8')
        os.utime(receipt, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert receipt.stat().st_size == stat.st_size and receipt.stat().st_mtime_ns == stat.st_mtime_ns
    elif mutation == 'digest':
        origins[0]['receipt_sha256'] = 'b' * 64
    else:
        receipt.unlink()
    provenance.write_text(json.dumps(origins), encoding='utf-8')
    output = tmp_path / 'output'
    with pytest.raises(CC.CE.EntregaError, match='[Rr]ecibo|[Pp]rocedencia'):
        CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
            capacidades='integrales', versiones=freeze, procedencias=provenance)
    assert not (output / 'manifiesto_candidato.json').exists()


@pytest.mark.parametrize('commit', [{'builder_path': r'C:\Users\PRIVATE_USER\cache'}, r'C:\Users\PRIVATE_USER\commit'])
def test_commit_cuda_declarado_no_admite_objeto_ni_ruta_privada(sources, tmp_path, commit):
    """086:RF-39/44: un origen CUDA no presta commit_id arbitrario al descriptor o al SBOM."""
    source, cache, freeze, provenance = sources
    (cache / 'torch-1.0-py3-none-any.whl').unlink()
    wheel = _wheel(cache, 'torch', version='1.0+cu126')
    freeze.write_text(freeze.read_text(encoding='utf-8').replace('torch==1.0\n', 'torch==1.0+cu126\n'), encoding='utf-8')
    origins = json.loads(provenance.read_text(encoding='utf-8'))
    origins.append({'name': 'torch', 'version': '1.0+cu126', 'wheel': wheel.name,
        'url': f'https://download-r2.pytorch.org/whl/cu126/{wheel.name}', 'commit_id': commit,
        'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()})
    provenance.write_text(json.dumps(origins), encoding='utf-8')
    output = tmp_path / 'output'
    with pytest.raises(CC.CE.EntregaError, match='commit'):
        CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
            capacidades='integrales', versiones=freeze, procedencias=provenance)
    assert not output.exists()


@pytest.mark.parametrize('url', ['file:///C:/Users/PRIVATE_USER/private.whl', 'file:///home/PRIVATE_USER/private.whl'])
def test_requisito_declarado_inactivo_no_publica_fuente_local(sources, tmp_path, url):
    """086:RF-39/44: un marker ajeno a Windows no autoriza filtrar rutas en grupos/README."""
    source, cache, freeze, provenance = sources
    requirements = source / 'requirements-drivers.txt'
    requirements.write_text(requirements.read_text(encoding='utf-8')+
        f"irrelevant @ {url} ; sys_platform == 'linux'\n", encoding='utf-8')
    output = tmp_path / 'output'
    with pytest.raises(CC.CE.EntregaError, match='[Ff]uente|URL|declarad'):
        CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
            capacidades='integrales', versiones=freeze, procedencias=provenance)
    assert not output.exists()


def test_requisito_git_publico_fijado_inactivo_conserva_su_declaracion(sources, tmp_path):
    """086:RF-37/39: validar la fuente exportada no elimina un requisito legítimo inactivo."""
    source, cache, freeze, provenance = sources
    declaration = "irrelevant @ git+https://example.org/public.git@"+'b'*40+" ; sys_platform == 'linux'"
    requirements = source / 'requirements-drivers.txt'
    requirements.write_text(requirements.read_text(encoding='utf-8')+declaration+'\n', encoding='utf-8')
    output = tmp_path / 'output'
    CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
        capacidades='integrales', versiones=freeze, procedencias=provenance)
    published = json.loads((output / 'cobertura.json').read_text(encoding='utf-8'))
    assert declaration in published['grupos']['drivers']
    assert declaration in (output / 'requisitos-declarados.txt').read_text(encoding='utf-8')
    assert not any(row['name']=='irrelevant' for row in published['ruedas'])


@pytest.mark.parametrize('capacidades', ['integrales', 'inferencia'])
def test_no_acepta_rueda_del_nucleo_con_hash_distinto(sources, tmp_path, monkeypatch, capacidades):
    """086:RF-39 — mismo nombre/versión no autoriza otro binario después de fijar el núcleo."""
    source, cache, freeze, provenance = sources
    with zipfile.ZipFile(cache / 'comun-1.0-py3-none-any.whl', 'a') as wheel:
        wheel.writestr('payload_posterior.txt', 'El lock precede a esta alteración.\n')
    if capacidades == 'inferencia':
        (source / 'requirements-complemento-ia.txt').write_text('torch==1.0\ncomun==1.0\n', encoding='utf-8')
        def transporte_local(*args):
            destino = Path(args[args.index('-d') + 1])
            for name in ('torch', 'comun'):
                path = cache / f'{name}-1.0-py3-none-any.whl'
                shutil.copyfile(path, destino / path.name)
        # Solo se controla el transporte de dos ruedas propias; la validación de sus bytes es real.
        monkeypatch.setattr(CC, '_pip', transporte_local)
    with pytest.raises(CC.CE.EntregaError, match='[Hh]uella|hash'):
        CC.construir_complemento_ia(source, tmp_path / 'output', cache=cache, version='1.0rc7',
            capacidades=capacidades, versiones=freeze, procedencias=provenance)
    assert not (tmp_path / 'output/manifiesto_candidato.json').exists()


@pytest.mark.parametrize('posicion', [0, 1])
def test_lock_de_nucleo_admite_cualquiera_de_sus_hashes_legitimos(sources, posicion):
    """086:RF-39 — una lista de hashes autorizados no se reduce a su primer elemento."""
    source, cache, freeze, provenance = sources
    digest = hashlib.sha256((cache / 'comun-1.0-py3-none-any.whl').read_bytes()).hexdigest()
    hashes = ['a' * 64]
    hashes.insert(posicion, digest)
    (source / 'requirements-nucleo.lock').write_text(
        (' ' + chr(92) + '\n    ').join(['comun==1.0', *(f'--hash=sha256:{h}' for h in hashes)]) + '\n', encoding='utf-8')
    selected, _ = CC.seleccionar_capacidades_integrales(source, [cache], freeze, provenance)
    assert (cache / 'comun-1.0-py3-none-any.whl').resolve() in selected


@pytest.mark.parametrize('extra', ['BIG__MAP', 'big.map', 'big-map'])
def test_extra_legitimo_normalizado_pep685_resuelve_su_dependencia(sources, extra):
    """086:RF-37/39 — alias válidos de extra conservan sus transitivas, también con mayúsculas/puntos."""
    source, cache, freeze, provenance = sources
    path = source / 'pyproject.toml'
    path.write_text(path.read_text(encoding='utf-8').replace('mapa[mapa]', f'mapa[{extra}]'), encoding='utf-8')
    _wheel(cache, 'mapa', ['extra-mapa; extra == "big-map"'], provides=('big-map',))
    selected, _ = CC.seleccionar_capacidades_integrales(source, [cache], freeze, provenance)
    assert (cache / 'extra_mapa-1.0-py3-none-any.whl').resolve() in selected


@pytest.mark.parametrize('dependency', [
    'nunca @ https://example.invalid/nunca.whl ; sys_platform == "linux"',
    'mapa[inexistente]; sys_platform == "linux"',
])
def test_dependencia_transitiva_inactiva_no_exige_extra_ni_red(sources, dependency):
    """086:RF-37/39 — se evalúa el marker antes de exigir la capacidad o rechazar su URL."""
    source, cache, freeze, provenance = sources
    _wheel(cache, 'peft', ['comun>=1', dependency])
    selected, _ = CC.seleccionar_capacidades_integrales(source, [cache], freeze, provenance)
    assert (cache / 'peft-1.0-py3-none-any.whl').resolve() in selected


def test_extra_de_raiz_inactiva_no_se_exige(sources):
    """086:RF-37/39 — el marker de una raíz ajena a Windows impide exigir su paquete y extra."""
    source, cache, freeze, provenance = sources
    path = source / 'pyproject.toml'
    path.write_text(path.read_text(encoding='utf-8').replace('mapa[mapa]>=1',
        "mapa[inexistente]>=1; sys_platform == 'linux'"), encoding='utf-8')
    selected, _ = CC.seleccionar_capacidades_integrales(source, [cache], freeze, provenance)
    assert (cache / 'mapa-1.0-py3-none-any.whl').resolve() not in selected


@pytest.mark.parametrize('via', ['raiz', 'transitiva'])
def test_extra_solicitado_no_declarado_se_rechaza(sources, tmp_path, via):
    """086:RF-37/39 — el warning de pip con retorno 0 no acredita una capacidad inexistente."""
    source, cache, freeze, provenance = sources
    if via == 'raiz':
        path = source / 'pyproject.toml'
        path.write_text(path.read_text(encoding='utf-8').replace('mapa[mapa]', 'mapa[inexistente]'), encoding='utf-8')
    else:
        _wheel(cache, 'peft', ['comun>=1', 'mapa[inexistente]'])
    with pytest.raises(CC.CE.EntregaError, match='[Ee]xtra.*inexistente'):
        CC.construir_complemento_ia(source, tmp_path / 'output', cache=cache, version='1.0rc7',
            capacidades='integrales', versiones=freeze, procedencias=provenance)
    assert not (tmp_path / 'output/manifiesto_candidato.json').exists()


@pytest.mark.parametrize('filename', ['MANIFEST.JSON', 'manifest.json.', 'manifest.json ', 'LICENSE.txt:oculto'])
def test_alias_windows_de_licencia_no_publica_paquete(sources, tmp_path, filename):
    """086:RF-39/44 — NTFS real: el alias/ADS no debe sobrescribir ni eludir las huellas de la entrega."""
    source, cache, freeze, provenance = sources
    licenses = _suplemento(tmp_path, cache, filename)
    with pytest.raises(CC.CE.EntregaError, match='[Rr]uta|[Ll]icencia|Windows'):
        CC.construir_complemento_ia(source, tmp_path / 'output', cache=cache, version='1.0rc7',
            capacidades='integrales', versiones=freeze, procedencias=provenance, licencias=licenses)
    assert not (tmp_path / 'output/manifiesto_candidato.json').exists()


def test_colision_casefold_de_textos_se_rechaza_antes_de_copiar(sources, tmp_path):
    """086:RF-39/44 — dos grafías de un destino NTFS no producen un inventario ambiguo."""
    source, cache, freeze, provenance = sources
    licenses = _suplemento(tmp_path, cache)
    data = json.loads(licenses.read_text(encoding='utf-8'))
    data['packages'][0]['texts'].append({**data['packages'][0]['texts'][0], 'path': 'license.TXT'})
    licenses.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(CC.CE.EntregaError, match='[Cc]olisi|[Ll]icencia'):
        CC.construir_complemento_ia(source, tmp_path / 'output', cache=cache, version='1.0rc7',
            capacidades='integrales', versiones=freeze, procedencias=provenance, licencias=licenses)
    assert not (tmp_path / 'output/manifiesto_candidato.json').exists()


def test_texto_legitimo_se_entrega_y_relee_desde_su_copia(sources, tmp_path):
    """086:RF-39/44 — texto anidado/UTF-8 válido, inventariado con su SHA y verificable sin el origen."""
    source, cache, freeze, provenance = sources
    licenses = _suplemento(tmp_path, cache, 'permisos/Permiso ñ.txt')
    output = tmp_path / 'output'
    m = CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc7',
        capacidades='integrales', versiones=freeze, procedencias=provenance, licencias=licenses)
    delivered = output / 'licencias/permisos/Permiso ñ.txt'
    digest = hashlib.sha256(delivered.read_bytes()).hexdigest()
    assert {'ruta': 'licencias/permisos/Permiso ñ.txt', 'sha256': digest, 'bytes': delivered.stat().st_size} in m['ficheros']
    # El recibo y los textos de la copia bastan sin la ruta desde la que se construyó.
    licenses.unlink()
    (tmp_path / 'permisos/Permiso ñ.txt').unlink()
    _, texts = CC.leer_metadatos_de_rueda(output / 'wheels/peft-1.0-py3-none-any.whl', licencias=output / 'licencias/manifest.json')
    assert any('Aviso sintético' in text for _, text in texts)
    assert IC.verificar_candidato(output)['tipo'] == 'complemento-ia'


@pytest.mark.parametrize('filename', [
    'C:/LICENSE.txt', 'C:LICENSE.txt', '/LICENSE.txt', '../LICENSE.txt', 'sub/../LICENSE.txt',
    './LICENSE.txt', '//servidor/recurso/LICENSE.txt', 'NUL.txt', 'aux', 'COM1.txt', 'LPT9',
    'manifest.json/LICENCE.txt', 'dir./LICENSE.txt', 'dir /LICENSE.txt', 'LICENSE?.txt', 'LICENSE\x00.txt',
])
def test_ruta_de_licencia_no_transportable_se_rechaza_al_leer(sources, tmp_path, filename):
    """086:RF-39/44 — ni rutas ambiguas Windows ni escapes llegan a abrir/copiar un texto ajeno."""
    _, cache, _, _ = sources
    licenses = _suplemento(tmp_path, cache)
    data = json.loads(licenses.read_text(encoding='utf-8'))
    data['packages'][0]['texts'][0]['path'] = filename
    licenses.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(CC.CE.EntregaError, match='[Ll]icencia'):
        CC.leer_metadatos_de_rueda(cache / 'peft-1.0-py3-none-any.whl', licencias=licenses)


def test_texto_compartido_identico_se_copia_una_sola_vez(sources, tmp_path):
    """086:RF-44 — varias ruedas pueden referir el mismo texto sin crear duplicados ni un alias."""
    source, cache, freeze, provenance = sources
    licenses = _suplemento(tmp_path, cache)
    data = json.loads(licenses.read_text(encoding='utf-8'))
    data['packages'].append({**data['packages'][0], 'name': 'bitsandbytes',
        'wheel_sha256': hashlib.sha256((cache / 'bitsandbytes-1.0-py3-none-any.whl').read_bytes()).hexdigest()})
    licenses.write_text(json.dumps(data), encoding='utf-8')
    output = tmp_path / 'output'
    m = CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc7',
        capacidades='integrales', versiones=freeze, procedencias=provenance, licencias=licenses)
    assert [f['ruta'] for f in m['ficheros']].count('licencias/LICENSE.txt') == 1
    assert IC.verificar_candidato(output)['tipo'] == 'complemento-ia'


def test_copia_de_licencia_alterada_falla_antes_de_publicar(sources, tmp_path, monkeypatch):
    """086:RF-39/44 — releer el origen no sirve: la entrega comprueba el texto que realmente copió."""
    source, cache, freeze, provenance = sources
    licenses = _suplemento(tmp_path, cache)
    antes = (tmp_path / 'LICENSE.txt').read_bytes()
    copiar = CC.shutil.copyfile
    def copia_alterada(src, dst, *args, **kwargs):
        res = copiar(src, dst, *args, **kwargs)
        if Path(dst).name == 'LICENSE.txt' and Path(dst).parent.name == 'licencias':
            Path(dst).write_text('Alterado en la copia, sin cambiar el origen.\n', encoding='utf-8')
        return res
    monkeypatch.setattr(CC.shutil, 'copyfile', copia_alterada)
    with pytest.raises(CC.CE.EntregaError, match='[Ll]icencia.*huella|huella.*licencia'):
        CC.construir_complemento_ia(source, tmp_path / 'output', cache=cache, version='1.0rc7',
            capacidades='integrales', versiones=freeze, procedencias=provenance, licencias=licenses)
    assert not (tmp_path / 'output/manifiesto_candidato.json').exists()
    assert (tmp_path / 'LICENSE.txt').read_bytes() == antes


@pytest.mark.parametrize('lock', ['comun==1.0', 'comun==1.0 --hash=sha256:base',
    'comun>=1 --hash=sha256:' + 'a' * 64, 'comun==1.0 --hash=sha512:' + 'a' * 128])
def test_lock_del_nucleo_sin_autoridad_sha256_no_se_admite(sources, lock):
    """086:RF-39 — un lock mal formado no se transforma en autoridad desde las ruedas recibidas."""
    source, cache, freeze, provenance = sources
    (source / 'requirements-nucleo.lock').write_text(lock + '\n', encoding='utf-8')
    with pytest.raises(CC.CE.EntregaError, match='[Ll]ock.*incompatible|SHA256'):
        CC.seleccionar_capacidades_integrales(source, [cache], freeze, provenance)


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


def test_torch_cuda_del_cdn_del_indice_oficial(sources, tmp_path):
    """086:RF-39 — el índice oficial de PyTorch enlaza también su CDN download-r2."""
    source, cache, freeze, provenance = sources
    (cache / 'torch-1.0-py3-none-any.whl').unlink()
    wheel = _wheel(cache, 'torch', version='1.0+cu126')
    freeze.write_text(freeze.read_text(encoding='utf-8').replace('torch==1.0\n', 'torch==1.0+cu126\n'), encoding='utf-8')
    origins = json.loads(provenance.read_text(encoding='utf-8'))
    origins.append({'name': 'torch', 'version': '1.0+cu126', 'wheel': wheel.name,
        'url': f'https://download-r2.pytorch.org/whl/cu126/{wheel.name}',
        'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'official_index_hash_verified': True})
    provenance.write_text(json.dumps(origins), encoding='utf-8')
    selected, coverage = CC.seleccionar_capacidades_integrales(source, [cache], freeze, provenance)
    assert wheel.resolve() in selected
    assert len(coverage['procedencias']) == 2
    output = tmp_path / 'cuda_provenance_export'
    CC.construir_complemento_ia(source, output, cache=cache, version='1.0rc6',
        capacidades='integrales', versiones=freeze, procedencias=provenance)
    published = json.loads((output / 'cobertura.json').read_text(encoding='utf-8'))
    torch_origin = next(origin for origin in published['procedencias'] if origin['name'] == 'torch')
    assert torch_origin['official_index_hash_verified'] is True
    assert torch_origin['url'] == origins[-1]['url'] and torch_origin['sha256'] == origins[-1]['sha256']


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
        lock = source / 'requirements-nucleo.lock'
        lock.write_text(lock.read_text(encoding='utf-8').replace('comun==1.0', 'comun==2.0'), encoding='utf-8')
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


# --------------------------------------------------------------------------- 086 L3/L4/L8: modelos, avisos e instalador
REPO = Path(__file__).resolve().parents[1]


def _rueda_con(cache, name, version, dlls):
    """Una rueda con DLL nativas dentro, como shapely.libs o torch/lib."""
    path = _wheel(cache, name, version=version)
    with zipfile.ZipFile(path, 'a') as z:
        for dll in dlls:
            z.writestr(dll, b'MZ')
    return path


def test_textos_de_terceros_se_comprueban_por_sus_bytes(tmp_path):
    """086:RF-44 — cada texto de modelo, Ollama, NVIDIA y vcruntime con su huella; uno alterado o que no se puede
    redistribuir no entra en ningún paquete."""
    textos = CC.textos_de_terceros(REPO)
    assert {'multilingual-e5-base', 'qwen3', 'ollama', 'ggml', 'nvidia-cuda', 'nvidia-cudnn', 'vcruntime'} <= set(textos)
    assert all(t['redistribuir'] is True and t['fuente'].startswith('https://') for t in textos.values())
    assert 'Copyright (c) Microsoft Corporation' in textos['multilingual-e5-base']['texto']
    assert 'Apache License' in textos['qwen3']['texto'] and 'Attachment A' in textos['nvidia-cuda']['texto']
    copia = tmp_path / 'repo'
    shutil.copytree(REPO / 'config' / 'licencias_terceros', copia / 'config' / 'licencias_terceros')
    texto = copia / 'config' / 'licencias_terceros' / 'MIT_Ollama.txt'
    texto.write_bytes(texto.read_bytes() + b' ')
    with pytest.raises(CC.CE.EntregaError, match='huella'):
        CC.textos_de_terceros(copia)
    texto.write_bytes((REPO / 'config' / 'licencias_terceros' / 'MIT_Ollama.txt').read_bytes())
    manifiesto = copia / 'config' / 'licencias_terceros' / 'manifest.json'
    datos = json.loads(manifiesto.read_text(encoding='utf-8'))
    datos['textos'][0]['redistribuir'] = False
    manifiesto.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(CC.CE.EntregaError, match='no permite redistribuir'):
        CC.textos_de_terceros(copia)


def test_fuentes_lgpl_de_las_dll_que_van_y_ninguna_sin_declarar(tmp_path):
    """086:RF-44 — GEOS de shapely y pyogrio, iconv, libpq, moocore y FFmpeg con el enlace a su fuente; una DLL LGPL en
    una rueda o versión no declarada impide armar el paquete."""
    cache = tmp_path / 'cache'
    cache.mkdir()
    ruedas = [_rueda_con(cache, 'shapely', '2.1.2', ['shapely.libs/geos-ae6e.dll', 'shapely.libs/geos_c-072b.dll']),
              _rueda_con(cache, 'pyogrio', '0.13.0', ['pyogrio.libs/iconv-2-ec64.dll', 'pyogrio.libs/geos-bda2.dll']),
              _rueda_con(cache, 'opencv-python', '5.0.0.93', ['cv2/opencv_videoio_ffmpeg500_64.dll']),
              _rueda_con(cache, 'psycopg2-binary', '2.9.13', ['psycopg2_binary.libs/libpq-57ae.dll']),
              _rueda_con(cache, 'moocore', '0.3.2', ['moocore/_libmoocore.pyd'])]
    texto = CC.fuentes_lgpl(REPO, ruedas)
    for esperado in ('GEOS 3.13.1', 'GEOS 3.14.1', 'libiconv 1.18', 'FFmpeg 7.1', 'psycopg2 2.9.13', 'moocore 0.3.2',
                     'https://github.com/libgeos/geos/releases/tag/3.13.1', 'petición escrita'):
        assert esperado in texto
    otra = _rueda_con(tmp_path, 'shapely', '9.9.9', ['shapely.libs/geos-0000.dll'])
    with pytest.raises(CC.CE.EntregaError, match='LGPL sin su fuente'):
        CC.fuentes_lgpl(REPO, [otra])
    assert CC.fuentes_lgpl(REPO, [_wheel(tmp_path, 'pura')]) == ''


def test_texto_de_nvidia_para_las_dll_de_cuda_y_cudnn(tmp_path):
    """086:RF-44 — las DLL de CUDA y cuDNN de torch llevan el texto de NVIDIA, con qué rueda las trae."""
    torch = _rueda_con(tmp_path, 'torch', '2.14.1+cu126', ['torch/lib/cudnn64_9.dll', 'torch/lib/cublas64_12.dll',
                                                          'torch/lib/c10.dll'])
    avisos = CC.avisos_nvidia(REPO, {torch.name: CC.dll_de_rueda(torch)})
    assert set(avisos) == {'NVIDIA NVIDIA CUDA Toolkit EULA', 'NVIDIA NVIDIA cuDNN SLA'}
    cuda = avisos['NVIDIA NVIDIA CUDA Toolkit EULA'][0][1]
    assert 'cublas64_12.dll' in cuda and 'c10.dll' not in cuda and 'Attachment A' in cuda
    assert 'cudnn64_9.dll' in avisos['NVIDIA NVIDIA cuDNN SLA'][0][1]
    assert CC.avisos_nvidia(REPO, {'pura': ['c10.dll']}) == {}


def test_avisos_nativos_del_python_propio(tmp_path):
    """086:RF-44 — OpenSSL, SQLite, expat, liblzma y zlib del Python compilado aquí, su procedencia y vcruntime."""
    python = tmp_path / 'python'
    (python / 'native_licenses').mkdir(parents=True)
    for nombre in ('OpenSSL-3.5.9', 'SQLite-3.54.1-public-domain', 'expat-2.9.0', 'liblzma-5.2.5', 'zlib-1.3.1'):
        (python / 'native_licenses' / f'{nombre}.txt').write_text(f'texto de {nombre}\n', encoding='utf-8')
    (python / 'RUNTIME_PROVENANCE.json').write_text('{"build": "local"}', encoding='utf-8')
    (python / 'vcruntime140.dll').write_bytes(b'MZ')
    avisos = CC.avisos_nativos(REPO, python)
    assert {'Python: OpenSSL-3.5.9', 'Python: zlib-1.3.1', 'Python: procedencia del runtime', 'Microsoft vcruntime'} <= set(avisos)
    assert 'visualstudio' in avisos['Microsoft vcruntime'][0][1]


def _git_blob(datos: bytes) -> str:
    return hashlib.sha1(f'blob {len(datos)}\0'.encode() + datos).hexdigest()


@pytest.fixture
def modelos(sources, tmp_path):
    """Dobles de e5-base, qwen3:8b y Ollama con la forma real de sus cachés, y un árbol con su catálogo y entrega."""
    source = sources[0]
    shutil.copytree(REPO / 'config' / 'licencias_terceros', source / 'config' / 'licencias_terceros')
    cache = tmp_path / 'MODELOS_IA'
    rev = 'c' * 40
    snap = cache / 'huggingface' / 'hub' / 'models--org--e5' / 'snapshots' / rev
    snap.mkdir(parents=True)
    peso, config = b'PESOS-E5-DOBLE', b'{"hidden_size": 8}'
    (snap / 'model.safetensors').write_bytes(peso)
    (snap / 'config.json').write_bytes(config)
    licencia = (REPO / 'config' / 'licencias_terceros' / 'APACHE-2.0_Qwen3.txt').read_bytes()
    capas = {'modelo': b'GGUF' + b'\0' * 12, 'licencia': licencia, 'config': b'{}'}
    blobs = cache / 'ollama_modelos' / 'blobs'
    blobs.mkdir(parents=True)
    digest = {k: hashlib.sha256(v).hexdigest() for k, v in capas.items()}
    for k, v in capas.items():
        (blobs / f'sha256-{digest[k]}').write_bytes(v)
    manifiesto = json.dumps({'schemaVersion': 2, 'config': {'digest': f'sha256:{digest["config"]}', 'size': 2},
        'layers': [{'mediaType': 'application/vnd.ollama.image.model', 'digest': f'sha256:{digest["modelo"]}', 'size': 16},
                   {'mediaType': 'application/vnd.ollama.image.license', 'digest': f'sha256:{digest["licencia"]}',
                    'size': len(licencia)}]}).encode()
    m = cache / 'ollama_modelos' / 'manifests' / 'registry.ollama.ai' / 'library' / 'qwen3' / '8b'
    m.parent.mkdir(parents=True)
    m.write_bytes(manifiesto)
    (cache / 'ollama').mkdir()
    with zipfile.ZipFile(cache / 'ollama' / 'ollama-windows-amd64.zip', 'w') as z:
        z.writestr('ollama.exe', b'MZ')
        z.writestr('lib/ollama/cuda_v12/cublas64_12.dll', b'MZ')
        z.writestr('lib/ollama/LLAMA_CPP_LICENSE', 'MIT License\nCopyright (c) The ggml authors\n')
    zsha = hashlib.sha256((cache / 'ollama' / 'ollama-windows-amd64.zip').read_bytes()).hexdigest()
    (source / 'docs').mkdir()
    (source / 'docs' / 'MODELOS_IA_LOCK.json').write_text(json.dumps({'modelos': [
        {'backend': 'huggingface', 'id': 'org/e5', 'revision': rev, 'files': [
            {'path': 'model.safetensors', 'size': len(peso), 'sha256': hashlib.sha256(peso).hexdigest()},
            {'path': 'config.json', 'size': len(config), 'sha256': None, 'git_blob_sha1': _git_blob(config)}]},
        {'backend': 'ollama', 'id': 'qwen3:8b', 'revision': hashlib.sha256(manifiesto).hexdigest()}]}), encoding='utf-8')
    entrega = json.loads((REPO / 'config' / 'entrega.json').read_text(encoding='utf-8'))
    entrega['complemento_ia'] = {'modelos': [{'backend': 'huggingface', 'id': 'org/e5', 'licencia': 'multilingual-e5-base'},
                                             {'backend': 'ollama', 'id': 'qwen3:8b', 'licencia': 'qwen3'}],
                                 'ollama': {**entrega['complemento_ia']['ollama'], 'sha256': zsha}}
    entrega['pesos_permitidos'] = [
        {'ruta': f'modelos/huggingface/hub/models--org--e5/snapshots/{rev}/model.safetensors',
         'sha256': hashlib.sha256(peso).hexdigest(), 'entrenado_con': 'publico'},
        {'ruta': f'modelos/ollama/blobs/sha256-{digest["modelo"]}', 'sha256': digest['modelo'], 'entrenado_con': 'publico'}]
    (source / 'config' / 'entrega.json').write_text(json.dumps(entrega), encoding='utf-8')
    return cache, rev, digest


def test_complemento_trae_modelos_sin_internet_con_sus_licencias(sources, modelos, tmp_path):
    """086:RF-34, RF-37, RF-44 — e5-base en su revisión, qwen3:8b y Ollama en el complemento, verificados por su huella,
    con sus licencias en los avisos, en licencias/modelos y en el SBOM; y un corpus neutro sin términos de empresa."""
    source, cache_ruedas, freeze, provenance = sources
    cache, rev, digest = modelos
    salida = tmp_path / 'complemento'
    m = CC.construir_complemento_ia(source, salida, cache=cache_ruedas, version='1.0rc6', capacidades='integrales',
                                    versiones=freeze, procedencias=provenance, modelos=cache)
    assert (salida / 'modelos/huggingface/hub/models--org--e5/refs/main').read_text(encoding='utf-8') == rev
    assert (salida / f'modelos/ollama/blobs/sha256-{digest["modelo"]}').is_file()
    assert (salida / 'modelos/ollama/manifests/registry.ollama.ai/library/qwen3/8b').is_file()
    assert (salida / 'modelos/ollama_runtime/ollama-windows-amd64.zip').is_file()
    assert [x['id'] for x in m['modelos']] == ['org/e5', 'qwen3:8b', 'ollama'] and m['modelos_activados'] is True
    assert m['pesos_del_proyecto_incluidos'] is False and m['corpus_neutro']['terminos_hallados'] == 0
    avisos = (salida / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8')
    for esperado in ('Copyright (c) Microsoft Corporation', 'Apache License', 'Copyright (c) Ollama',
                     'The ggml authors', 'cuda_v12/cublas64_12.dll', 'Attachment A'):
        assert esperado in avisos
    assert len(list((salida / 'licencias' / 'modelos').iterdir())) >= 4
    bom = json.loads((salida / 'sbom.cdx.json').read_text(encoding='utf-8'))
    tipos = {c['name']: c['type'] for c in bom['components']}
    assert tipos['org/e5'] == tipos['qwen3:8b'] == 'machine-learning-model' and tipos['ollama'] == 'application'
    assert (salida / 'instalador' / 'ComplementoIA.iss').is_file() and (salida / 'version.txt').read_text().strip() == '1.0rc6'
    corpus = json.loads((salida / 'corpus' / 'ordenes_neutras.json').read_text(encoding='utf-8'))
    assert corpus['empresa'] is None and len(corpus['filas']) == m['corpus_neutro']['filas'] > 100
    assert IC.verificar_candidato(salida)['version'] == '1.0rc6'
    (salida / 'modelos' / 'ollama' / 'blobs' / 'sha256-intruso').write_bytes(b'GGUF')
    with pytest.raises(IC.ErrorInstalacion, match='no declara'):
        IC.verificar_candidato(salida)


@pytest.mark.parametrize('caso', ['huella_hf', 'blob_git', 'manifiesto', 'capa', 'ollama', 'peso_no_declarado', 'licencia'])
def test_modelo_alterado_o_sin_declarar_no_se_empaqueta(sources, modelos, tmp_path, caso):
    """086:RF-34, RF-39 — un modelo de otra revisión, una capa cambiada, otro Ollama o un peso sin declarar: no se arma."""
    source, cache_ruedas, freeze, provenance = sources
    cache, rev, digest = modelos
    snap = cache / 'huggingface' / 'hub' / 'models--org--e5' / 'snapshots' / rev
    if caso == 'huella_hf':
        (snap / 'model.safetensors').write_bytes(b'PESOS-E5-OTROS')
    elif caso == 'blob_git':
        (snap / 'config.json').write_bytes(b'{"hidden_size": 9}')
    elif caso == 'manifiesto':
        m = cache / 'ollama_modelos/manifests/registry.ollama.ai/library/qwen3/8b'
        m.write_bytes(m.read_bytes() + b' ')
    elif caso == 'capa':
        (cache / 'ollama_modelos' / 'blobs' / f'sha256-{digest["modelo"]}').write_bytes(b'GGUF' + b'\1' * 12)
    elif caso == 'ollama':
        with zipfile.ZipFile(cache / 'ollama' / 'ollama-windows-amd64.zip', 'a') as z:
            z.writestr('extra.dll', b'MZ')
    else:
        entrega = json.loads((source / 'config' / 'entrega.json').read_text(encoding='utf-8'))
        if caso == 'peso_no_declarado':
            entrega['pesos_permitidos'] = entrega['pesos_permitidos'][:1]
        else:
            entrega['complemento_ia']['modelos'][1]['licencia'] = 'ollama'
        (source / 'config' / 'entrega.json').write_text(json.dumps(entrega), encoding='utf-8')
    with pytest.raises(CC.CE.EntregaError, match='huella|revisión|declarad|licencia|tamaño'):
        CC.construir_complemento_ia(source, tmp_path / 'salida', cache=cache_ruedas, version='1.0rc6',
                                    capacidades='integrales', versiones=freeze, procedencias=provenance, modelos=cache)
    assert not (tmp_path / 'salida' / 'manifiesto_candidato.json').exists()


def test_la_orden_pide_modelos_o_sin_modelos_explicito(sources, capsys):
    """086:RF-37 — el complemento de la 1.0 trae sus modelos; sin ellos hay que decirlo con --sin-modelos."""
    source, cache, _, _ = sources
    assert CC.main(['complemento-ia', '--salida', str(source / 'x'), '--ruedas-cache', str(cache)]) == 1
    assert '--sin-modelos' in capsys.readouterr().err


def _instalado(tmp_path, version='1.0rc6'):
    destino = tmp_path / 'app'
    python = destino / 'versiones' / version / 'python' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.write_text('', encoding='utf-8')
    (destino / 'actual.txt').write_text(version + '\n', encoding='utf-8')
    return destino


def test_el_complemento_se_instala_junto_al_programa_sin_pip_a_mano(sources, modelos, tmp_path, monkeypatch):
    """086:RF-37, RF-39 (auditoría L8) — con el Python del programa: comprueba las huellas, instala las ruedas sin red y
    con huella, deja los modelos y Ollama en complemento_ia, y el lanzador los lee de ahí sin internet."""
    source, cache_ruedas, freeze, provenance = sources
    cache, rev, _ = modelos
    salida = tmp_path / 'complemento'
    CC.construir_complemento_ia(source, salida, cache=cache_ruedas, version='1.0rc6', capacidades='integrales',
                                versiones=freeze, procedencias=provenance, modelos=cache)
    destino = _instalado(tmp_path)
    ordenes = []

    def correr(orden, **kw):
        ordenes.append(orden)
        return type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

    monkeypatch.setattr(IC.subprocess, 'run', correr)
    monkeypatch.setattr(IC, '_web_escuchando', lambda puerto: False)
    r = IC.instalar_complemento(salida, destino)
    assert r['modelos'] == ['org/e5', 'qwen3:8b', 'ollama']
    pip = next(o for o in ordenes if 'pip' in o)
    assert {'--no-index', '--require-hashes'} <= set(pip) and str(salida / 'instalacion.lock') in pip
    ia = destino / 'complemento_ia'
    assert (ia / 'instalado.json').is_file() and (ia / 'ollama' / 'ollama.exe').is_file()
    assert (ia / 'modelos/huggingface/hub/models--org--e5/refs/main').is_file()
    assert not (ia / 'modelos' / 'ollama_runtime').exists(), 'Ollama va descomprimido, no el zip'
    lanzador = (destino / 'ConverterSmartGrid.cmd').read_text(encoding='cp1252')
    assert 'HF_HUB_OFFLINE=1' in lanzador and 'OLLAMA_MODELS=' in lanzador and 'ollama.exe" serve' in lanzador
    assert any('qwen3:8b' in o for o in ordenes if '-c' in o), 'el asistente queda con el modelo de Ollama que trae'


@pytest.mark.parametrize('caso', ['sin_programa', 'otra_version', 'pip_falla'])
def test_el_complemento_no_se_instala_a_medias(sources, modelos, tmp_path, monkeypatch, caso):
    """086:RF-37, RF-39 — sin el programa, con otra versión o si pip falla, el programa queda como estaba."""
    source, cache_ruedas, freeze, provenance = sources
    cache, _, _ = modelos
    salida = tmp_path / 'complemento'
    CC.construir_complemento_ia(source, salida, cache=cache_ruedas, version='1.0rc6', capacidades='integrales',
                                versiones=freeze, procedencias=provenance, modelos=cache)
    destino = tmp_path / 'vacio' if caso == 'sin_programa' else _instalado(tmp_path, '1.0rc5' if caso == 'otra_version' else '1.0rc6')
    monkeypatch.setattr(IC.subprocess, 'run', lambda *a, **k: type('R', (), {'returncode': 1, 'stdout': '', 'stderr': 'no'})())
    monkeypatch.setattr(IC, '_web_escuchando', lambda puerto: False)
    with pytest.raises(IC.ErrorInstalacion, match={'sin_programa': 'instale antes', 'otra_version': 'misma versión',
                                                    'pip_falla': 'pip'}[caso]):
        IC.instalar_complemento(salida, destino)
    assert not (destino / 'complemento_ia').exists() and not (destino / 'complemento_ia.preparando').exists()


def test_el_iss_del_complemento_va_en_la_linea_del_programa():
    """086:RF-37 (auditoría L8) — su propio instalador, por usuario, en la carpeta del programa, sin pip a mano: lo hace
    instalar_candidato.py complemento; con disco partido porque los pesos pasan de 4 GB."""
    iss = (REPO / 'instalador' / 'ComplementoIA.iss').read_text(encoding='utf-8')
    for esperado in ('PrivilegesRequired=lowest', 'DiskSpanning=yes', 'instalar_candidato.py" complemento',
                     '{6F0B1C52-8A3E-4C57-9B0E-6F4C2D7A1E86}_is1', 'version.txt', 'actual.txt'):
        assert esperado in iss
    assert 'pip install' not in iss
    principal = (REPO / 'instalador' / 'ConverterSmartGrid.iss').read_text(encoding='utf-8')
    assert 'Name: "{app}\\complemento_ia"' in principal


def test_086_rf34_una_sintetica_que_coincide_con_un_termino_se_resortea(tmp_path, monkeypatch):
    """086:RF-34 — un código inventado que coincide por azar con un término de la lista (PUERTA3 del 16-11: un código de alimentador real)
    no rechaza la entrega ni entra en el corpus: su orden se sustituye por otra de su tarea con la semilla siguiente,
    y el corpus conserva su tamaño. Una orden fija con un término sí la rechaza."""
    import importlib.util as iu
    from types import SimpleNamespace
    from convertersmartgrid.aplicacion.asistente import ordenes_fijas, sinteticos
    raiz = Path(__file__).resolve().parents[1]
    spec = iu.spec_from_file_location('construir_candidato_resorteo', raiz / 'tools' / 'construir_candidato.py')
    cc = iu.module_from_spec(spec)
    spec.loader.exec_module(cc)
    orden = lambda texto, tarea='t': SimpleNamespace(texto=texto, tarea=tarea, datos=[])  # noqa: E731

    def generar(_vocab, por_tarea, semilla):
        return [orden('mira ZQ999 ahora'), orden('mira AB123 ahora')] if semilla == 0 else [orden(f'mira CD{semilla}00')]
    monkeypatch.setattr(sinteticos, 'generar', generar)
    monkeypatch.setattr(ordenes_fijas, 'generar', lambda _v: [orden('ayuda', 'fija')])
    terminos = cc.CE.Terminos()
    terminos.anadir('ZQ999', 'alimentador')
    assert any(True for _ in cc.CE._buscar('mira ZQ999 ahora', terminos, {}))
    r = cc.corpus_neutro(tmp_path, terminos)
    corpus = json.loads((tmp_path / 'corpus' / 'ordenes_neutras.json').read_text(encoding='utf-8'))
    textos = [f['texto'] for f in corpus['filas']]
    assert r['terminos_hallados'] == 0 and r['sinteticas_resorteadas'] == 1 and r['filas'] == 3
    assert not any('ZQ999' in x for x in textos) and 'mira CD100' in textos
    monkeypatch.setattr(ordenes_fijas, 'generar', lambda _v: [orden('abre ZQ999', 'fija')])
    with pytest.raises(cc.CE.EntregaError):
        cc.corpus_neutro(tmp_path / 'b', terminos)
