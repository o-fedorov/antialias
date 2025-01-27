# antialias
Invoke your bash functions from one place.

## Quickstart

The simplest way to use antialias is to execute it with `uv run`.

First, ensure that you have `uv` installed.  Refer to the following
page to figure out how to install `uv`:

<https://docs.astral.sh/uv/getting-started/installation/>

Next, place [./antialias.py](./antialias.py) in your `PATH`
to ensure that you can execute it from anywhere.

Then, add the folowing line to your `~/.bashrc`, `~/.bash_profile`
or `~/.zshrc`:

```bash
als() {
  eval "$(antialias.py eval -- "$@")"
}
```

Feel free to replace `als` with any other name you prefer.

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
  "underscore_to_dash": true,
  "keep_original_name": false,
  "function_regexp": "^\\s*(?:function\\s+)?(?P<function_name>\\w+)\\s*(?:\\(\\))?\\s*\\{\\s*(?:#\\s*(?P<comment>.*))?$"
}
```

The options are as follows:

- `source_files` is a list of source files to parse.
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