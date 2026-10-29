"""La interfaz recuerda los ficheros de la última sesión, y los nuevos sustituyen.

Cada entrega de la distribuidora trae ficheros distintos, en otra carpeta y con otro
nombre. Si la interfaz vuelve siempre a los TXT de ejemplo, hay que buscar los tres a
mano cada vez, y es fácil convertir sin darse cuenta con la entrega del mes pasado.

Lo hacía ``settings.py`` para la GUI Tkinter, que se retiró (spec 001, RF-16). En la web
lo hace cada espacio de trabajo, que guarda sus entradas y opciones en su carpeta.

Spec 034: 034:RF-30.
"""

from __future__ import annotations

from pathlib import Path


def _txt(tmp_path, nombre: str) -> str:
    ruta = tmp_path / nombre
    ruta.write_text('[GENERAL]\n', encoding='utf-8')
    return str(ruta)


class TestEnLaInterfazWeb:
    def test_el_espacio_guarda_al_elegir_un_fichero(self, tmp_path):
        from igea_dgs.web.workspace import Workspace

        red = Path(_txt(tmp_path, 'red_web.txt'))
        root = tmp_path / 'workspace'
        workspace = Workspace(id='abcdef12', root=root)
        workspace.set_input('red', red, origin='server')

        reloaded = Workspace.load(root)
        assert reloaded.inputs['red']['path'] == str(red)

    def test_la_seleccion_mas_reciente_manda(self, tmp_path):
        """El caso que se pidió: la entrega nueva desplaza a la vieja."""
        from igea_dgs.web.workspace import Workspace

        vieja = Path(_txt(tmp_path, 'red_vieja.txt'))
        nueva = Path(_txt(tmp_path, 'red_nueva.txt'))
        root = tmp_path / 'workspace'
        workspace = Workspace(id='abcdef12', root=root)
        workspace.set_input('red', vieja, origin='server')
        workspace.set_input('red', nueva, origin='server')

        assert Workspace.load(root).inputs['red']['path'] == str(nueva)

    def test_opciones_y_entradas_sobreviven_al_reinicio(self, tmp_path):
        from igea_dgs.web.workspace import WorkspaceStore

        store = WorkspaceStore(tmp_path / 'web')
        workspace = store.create()
        red = Path(_txt(tmp_path, 'red_reinicio.txt'))
        workspace.set_input('red', red, origin='server')
        workspace.options['source_crs'] = 'EPSG:32717'
        workspace.save()

        reloaded = WorkspaceStore(store.root).get(workspace.id)
        assert reloaded is not None
        assert reloaded.inputs['red']['path'] == str(red)
        assert reloaded.options['source_crs'] == 'EPSG:32717'
