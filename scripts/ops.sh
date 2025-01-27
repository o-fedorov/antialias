lint() {  # lint the codebase
  uvx ruff check "$@"
}

fmt() {  # format the codebase
  uvx ruff format "$@"
}

fix() {  # format and fix the codebase
  fmt
  lint --fix
}
