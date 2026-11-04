# El programa instalado no encontraba nada fuera del repositorio

## Síntoma
Construida la rueda de `c79013c2` e instalada en una carpeta aparte, `project_root()` era esa carpeta: no existían `tools/`, `config/pide_universal_2017.json`, los costes de referencia ni `frontend/dist`, y `perfiles_disponibles()` daba una lista vacía. Importar, calibrar o abrir la web habría fallado en casa del cliente, en la primera orden.

## Causa
Comprobada, con una prueba antes de tocar nada. El código calculaba rutas con `Path(__file__).parents[n]`, que en un árbol de desarrollo es el repositorio y en un paquete instalado es `site-packages`. Y lo que se lee y lo que se escribe estaban en el mismo sitio: el perfil de la empresa y los catálogos vivían junto a los guiones, en la carpeta que una actualización sustituye.

Al probarlo de verdad, con el Python embebido y sin nada en `PATH`, salieron tres más que ninguna prueba sintética habría visto:

- `tools/powerfactory_acceptance.py`, el que importa en DIgSILENT, estaba excluido de `config/entrega.json`, y tres guiones entregados lo importan.
- Sin `._pth`, el Python embebido añade a su ruta las carpetas de cualquier Python del registro de Windows, antes que las suyas. Con `._pth`, en cambio, no lee `PYTHONPATH`, que es como un guion encuentra la API de DIgSILENT. Se resuelve con `PYTHONHOME` en el lanzador.
- En una carpeta larga, `pyproj` y `shapely` daban «nombre demasiado largo» solo al importarlos; el doctor lo trataba como un aviso porque esas capacidades no eran obligatorias.

## Comprobación permanente
`runtime_paths.raiz_programa()` y `raiz_local()` son las dos únicas respuestas: lo que se lee, en `_programa/` dentro del paquete, con la forma del repositorio; lo que se escribe, en la carpeta de datos. `tools/construir_candidato.py` rellena `_programa/` con lo que dice `config/entrega.json`. El doctor da por no instalado un paquete cuya librería no carga. Instalar comprueba la longitud de las rutas.

## Prueba
- `tests/test_instalacion_programa.py::test_fuera_del_repositorio_encuentra_lo_suyo`
- `tests/test_instalacion_programa.py::test_la_rueda_da_los_mismos_dgs_que_el_arbol`
- `tests/test_instalacion_programa.py::test_lo_que_lanza_la_web_entra_en_la_entrega`
- `tests/test_instalacion_programa.py::test_los_guiones_entregados_no_importan_uno_excluido`
- `tests/test_instalacion_programa.py::test_lanzador_del_programa_no_lee_otro_python`
- `tests/test_instalacion_programa.py::test_ruta_demasiado_larga_se_dice_al_instalar`
- `tests/test_instalacion_programa.py::test_quitar_cada_libreria_dice_que_funcion_afecta`
