"""065:RF-15, RF-24 — cierre de metadatos y versión reproducible por destino."""

import importlib.util
from importlib import metadata
from pathlib import Path

import pytest


def herramienta():
    ruta = Path(__file__).parents[1] / "tools" / "fijar_entorno.py"
    assert ruta.is_file(), "Falta la herramienta del cierre de instalación"
    spec = importlib.util.spec_from_file_location("fijar_entorno", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def inventario(tmp_path, paquetes):
    for nombre, (version, dependencias, origen) in paquetes.items():
        info = tmp_path / f"{nombre.replace('-', '_')}-{version}.dist-info"
        info.mkdir()
        texto = f"Metadata-Version: 2.1\nName: {nombre}\nVersion: {version}\n"
        texto += "".join(f"Requires-Dist: {dep}\n" for dep in dependencias)
        (info / "METADATA").write_text(texto, encoding="utf-8")
        if origen:
            (info / "direct_url.json").write_text(origen, encoding="utf-8")
    return {d.metadata["Name"]: d for d in metadata.distributions(path=[str(tmp_path)])}


def test_cierre_marcadores_extras_y_determinismo(tmp_path):
    """065:RF-15 — extras transitivos y markers respetan Python/Windows sin ML."""
    m = herramienta()
    paquetes = inventario(tmp_path, {
        "servidor": ("1.2", ["base>=2", 'win; sys_platform == "win32"',
                             'unix; sys_platform != "win32"',
                             'extra[rapido]; extra == "standard"'], None),
        "base": ("2.4", [], None), "win": ("1.0", [], None),
        "extra": ("3.0", ['hijo; extra == "rapido"'], None),
        "hijo": ("4.0", [], None), "torch": ("2.9", [], None),
    })
    esperado = {"base": "2.4", "extra": "3.0", "hijo": "4.0", "servidor": "1.2", "win": "1.0"}
    assert m.resolver_cierre(["servidor", "servidor[standard]"], paquetes) == esperado
    assert m.resolver_cierre(["servidor[standard]", "servidor"], dict(reversed(list(paquetes.items())))) == esperado
    assert m.texto_constraints(esperado, "3.12.10") == m.texto_constraints(dict(reversed(list(esperado.items()))), "3.12.10")
    assert "torch" not in m.texto_constraints(esperado, "3.12.10")


@pytest.mark.parametrize("dependencias,paquetes,error", [
    (["ausente>=1"], {}, "ausente"),
    (["base>=3"], {"base": ("2.0", [], None)}, "incompatible"),
    (["base"], {"base": ("", [], None)}, "versión"),
    (["base @ https://example.org/base.whl"], {}, "directa"),
    (["base"], {"base": ("1.0", [], '{"url":"file:///privado/base.whl"}')}, "origen"),
    (["base"], {"base": ("1.0+local", [], None)}, "local"),
])
def test_cierre_rechaza_faltantes_y_procedencia_no_reproducible(tmp_path, dependencias, paquetes, error):
    """065:RF-15 — no emite un lock parcial o que pierda el origen de un wheel/VCS."""
    m = herramienta()
    with pytest.raises(ValueError, match=error):
        m.resolver_cierre(dependencias, inventario(tmp_path, paquetes))


def test_lectura_unica_requisitos_y_extras_del_proyecto(tmp_path):
    """065:RF-15 — el editable toma dependencias del candidato y conserva extras."""
    m = herramienta()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="producto"\ndependencies=["base>=1"]\n'
        '[project.optional-dependencies]\nweb=["servidor[standard]>=1"]\nml=["torch"]\n', encoding="utf-8")
    (tmp_path / "requirements.txt").write_text('-c constraints-python312-win.txt\n-e .[web]\n-r adicional.txt\n', encoding="utf-8")
    (tmp_path / "adicional.txt").write_text('windows>=2 ; sys_platform == "win32" # comentario\n', encoding="utf-8")
    assert m.leer_requisitos(tmp_path / "requirements.txt") == ["base>=1", "servidor[standard]>=1", 'windows>=2 ; sys_platform == "win32"']


def test_metadata_editable_duplicado_ajeno_al_cierre_no_impide_lock(tmp_path, monkeypatch):
    """065:RF-15 — dos metadatos del editable no contaminan el cierre solicitado."""
    m = herramienta()
    for carpeta in (tmp_path / "primera", tmp_path / "segunda"):
        carpeta.mkdir()
        inventario(carpeta, {"producto-editable-ajeno": ("1.0", [], None)})
        monkeypatch.syspath_prepend(str(carpeta))
    inventario(tmp_path / "primera", {"base-cierre-propio": ("1.0", [], None)})
    assert m.resolver_cierre(["base-cierre-propio"]) == {"base-cierre-propio": "1.0"}


@pytest.mark.parametrize("linea", ["-e ../otro", "git+https://example.org/repo.git", "--index-url https://example.org", "-r requirements.txt"])
def test_lector_rechaza_fuentes_ambiguas_y_recursion(tmp_path, linea):
    """065:RF-15 — no acepta opciones o rutas que impidan fijar la procedencia."""
    m = herramienta()
    ruta = tmp_path / "requirements.txt"
    ruta.write_text(linea, encoding="utf-8")
    with pytest.raises(ValueError):
        m.leer_requisitos(ruta)


@pytest.mark.parametrize("version,plataforma,maquina", [("3.13.0", "win32", "AMD64"), ("3.12.10", "linux", "x86_64"), ("3.12.10", "win32", "ARM64")])
def test_destino_ajeno_no_se_publica_como_windows312(version, plataforma, maquina):
    """065:RF-15 — un lock de Windows CPython AMD64 no certifica otros destinos."""
    with pytest.raises(ValueError):
        herramienta().comprobar_destino(version, plataforma, maquina)


@pytest.mark.parametrize("nombre,instalada,minima", [
    ("pillow", "12.3.0", "13.0.0"),
    ("pypdf", "6.21.2", "6.21.4"),
    ("certifi", "2026.7.22", "2026.10.18"),
])
def test_entorno_bajo_minimo_de_seguridad_no_es_apto(tmp_path, nombre, instalada, minima):
    """065:RF-15/24; 086:RF-44 — compatibilidad no sustituye la política de seguridad."""
    m = herramienta()
    with pytest.raises(ValueError, match="seguridad"):
        m.resolver_cierre([nombre], inventario(tmp_path, {nombre: (instalada, [], None)}),
                         minimos_seguridad={nombre: minima})


@pytest.mark.parametrize("instalada", ["13.0.0", "13.0.1"])
def test_minimo_de_seguridad_permite_version_igual_o_superior(tmp_path, instalada):
    """065:RF-15; 086:RF-44 — el mínimo no es un pin oculto ni exige extras ajenos."""
    m = herramienta()
    assert m.resolver_cierre(
        ["pillow"], inventario(tmp_path, {"pillow": (instalada, [], None)}),
        minimos_seguridad={"Pillow": "13.0.0", "extra-no-solicitado": "1.0"},
    ) == {"pillow": instalada}


def test_constraints_no_regresan_bajo_politica_de_seguridad():
    """065:RF-15; 086:RF-44 — instalar desarrollo no debe deshacer la corrección del núcleo."""
    import re
    from packaging.version import Version

    raiz = Path(__file__).parents[1]
    minimos = herramienta().leer_minimos_seguridad(raiz/'config/entrega.json')
    fijadas = dict(re.findall(r'^([a-z0-9._-]+)==(\S+)',
                   (raiz/'constraints-python312-win.txt').read_text(encoding='utf-8'), re.M))
    assert all(n in fijadas and Version(fijadas[n]) >= Version(v) for n,v in minimos.items())


@pytest.mark.parametrize('dato', ['{}', '[]', '{"candidato":{"versiones_de_seguridad":{}}}',
    '{"candidato":{"versiones_de_seguridad":{"pillow":null}}}'])
def test_politica_incompleta_no_se_omite(tmp_path, dato):
    """065:RF-15/24 — la ausencia o corrupción de política no equivale a no tener mínimos."""
    p = tmp_path/'entrega.json';p.write_text(dato,encoding='utf-8')
    with pytest.raises(ValueError, match='seguridad'):
        herramienta().leer_minimos_seguridad(p)
