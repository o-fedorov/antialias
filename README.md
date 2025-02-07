# antialias
Invoke your bash functions from one place.

## Quickstart

### Prerequisites
The simplest way to use antialias is to install it using `uv` or `pipx`.

First ensure that you have `uv` or `pipx` installed.  Refer to the following
pages to figure out how to install one of these tools:

- `uv`: <https://docs.astral.sh/uv/getting-started/installation/>
- `pipx`: <https://pipx.pypa.io/latest/installation/>

### Installation
Use this repository's URL as a source for the installation.
For `uv` the command will look like this:

```bash
uv tool install --from git+https://github.com/o-fedorov/antialias@main antialias
```

For `pipx` the command will look like this:

```bash
pipx install git+https://github.com/o-fedorov/antialias@main
```

If you are contributing to the project, you can install it in the editable
mode.  For `uv` navigate to the root directory of the repo and run:

```bash
uv tool install --from file://. antialias --editable
```

Check that `antialias` is installed by running:

```bash
antialias --help
```

### Configuration
When the tool is installed, add the following lines to your
`~/.bashrc`, `~/.bash_profile` or `~/.zshrc`:

```bash
als() {
  eval "$(antialias eval -- "$@")"
}
```

Also, add one of the following lines to setup commands completion.
For zsh:

```bash
eval "$(antialias completion --zsh --name als)"
```

For bash:

```bash
eval "$(antialias completion --bash --name als)"
```

Feel free to replace `als` in the examples above with
any other name you prefer.

Restart your shell or run `source ~/.bashrc`, `source ~/.bash_profile`
or `source ~/.zshrc` to apply the changes.  Now you can generate
the configuration file by running:

```bash
als --dump-config
```

Open the printed-out path in your editor and add your source files to
the list.

Finally, run `als --list` to see the list of the available functions.

## Usage

Refer to [.config/](./.config) for the advanced example of the
configuration.  This is how the tool itself is tested, and how the
functions in [scripts/](./scripts) are invoked.

The file [.config/bashrc](./.config/bashrc) shows how the tool can be
configured in a portable way.  You probably do not need it, but it is
useful to know that you can use environment variables to override the
config path.  You can also do `antialias.py --config .config/...` to
override the config path.

Also, while you can use relative source file paths, and define the root
with `ANTIALIAS_FILES_ROOT` environment variable or `--files-root` option,
it is recommended to use absolute paths in your config.

The file [.config/config.json](./.config/config.json) shows how the
configuration file can be structured.

```json
{
  "source_files": [
    "scripts/ops.sh",
    "scripts/test_source1.sh",
    "scripts/test_source2.sh"
  ],
  ,
  "script_directories": [
    "scripts/executable"
  ],
  "underscore_to_dash": true,
  "keep_original_name": false,
  "function_regexp": "^\\s*(?:function\\s+)?(?P<function_name>\\w+)\\s*(?:\\(\\))?\\s*\\{\\s*(?:#\\s*(?P<comment>.*))?$"
}
```

The options are as follows:

- `source_files` is a list of source files to parse.
- `script_directories` is a list of directories to search for executable
  scripts.
- `underscore_to_dash` is a boolean flag to replace underscores with dashes in
  the function names.
- `keep_original_name` allows to use both the original function name and the
  name with underscores replaced with dashes.
- `function_regexp` is a regular expression to match the function definition.
  It should have two named groups: `function_name` and `comment`.

## Example
Below are the examples of the tool in action.  It has `a` alias, as
configured in [.config/bashrc](./.config/bashrc).

```bash
$ a --dump-config
Config file updated: .config/config.json

$ a --list
Special Functions:
  --dump-config: Dump config to a file.
  --list: List all available functions.

File: scripts/test_source1.sh

  f-1 (original: f_1)

File: scripts/test_source2.sh

  f-2 (original: f_2)

File: scripts/ops.sh

  fix: format and fix the codebase
  fmt: format the codebase
  lint: lint the codebase

$ a f-2 arg1 arg2 --option1
Hello from f_1 with args: arg1 arg2 --option1
Called f_2 with args: arg1 arg2 --option1

$ a f-3
Error: function f-3 not found.
```