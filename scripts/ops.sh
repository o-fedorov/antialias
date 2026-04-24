lint() {  # lint the codebase
  uvx ruff check "$@"
}

typing() {  # type check the codebase
  uvx ty check "$@"
}

fmt() {  # format the codebase
  uvx ruff format "$@"
}

fix() {  # format the codebase and fix fixable issues
  fmt
  lint --fix --exit-zero
  typing --fix --exit-zero
  fmt
}

check-all() {  # fix and check the codebase
  fix
  lint
  typing
}
