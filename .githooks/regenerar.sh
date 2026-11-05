#!/bin/sh
# 090:RF-11 a RF-14: el catálogo de la arquitectura entra en cada commit y en cada fusión, leído del índice:
# en un árbol compartido puede haber cambios sin confirmar de otra sesión. Un documento no para un commit:
# si el generador falla se avisa y lo detiene la suite.
raiz=$(git rev-parse --show-toplevel)
comun=$(git rev-parse --git-common-dir)
case "$comun" in
  /*|?:*) ;;
  *) comun="$raiz/$comun" ;;
esac
python_de_git="${CSG_PYTHON:-}"
if [ -z "$python_de_git" ]; then
  for candidato in "$raiz/.venv/Scripts/python.exe" "$comun/../.venv/Scripts/python.exe" "$raiz/.venv/bin/python"; do
    if [ -x "$candidato" ]; then python_de_git="$candidato"; break; fi
  done
fi
[ -n "$python_de_git" ] || python_de_git=python
if ! "$python_de_git" "$raiz/tools/generar_arquitectura.py" --escribir --desde-indice --anadir --raiz "$raiz"; then
  echo "Aviso: no se pudo regenerar docs/ARQUITECTURA_CATALOGO.md; python tools/generar_arquitectura.py --escribir" >&2
fi
exit 0
