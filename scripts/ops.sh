lint() {  # lint the codebase
  uvx ruff check "$@"
}

typing() {  # type check the codebase
  uvx ty check "$@"
}

fmt() {  # format the codebase
  uvx ruff format "$@"
}

fix() {  # format and fix the codebase
  fmt
  lint --fix --exit-zero
  typing --fix --exit-zero
}

check-all() {  # fix and check the codebase
  fix
  lint
  typing
}
