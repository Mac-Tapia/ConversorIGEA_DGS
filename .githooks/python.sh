# El intérprete del proyecto para los ganchos: CSG_PYTHON, el .venv del clon o el del árbol principal.
raiz="$(git rev-parse --show-toplevel)"
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
