# mkdocs-extrafiles

[![PyPI][pypi-img]][pypi-lnk]
[![License][license-img]][license-lnk]
[![Tests][tests-img]][tests-lnk]
[![Code Style][codestyle-img]][codestyle-lnk]
[![Coverage Status][codecov-img]][codecov-lnk]

`mkdocs-extrafiles` is a lightweight [MkDocs](https://www.mkdocs.org/) plugin that allows you to add files and directories from outside MkDocs document directory (`docs_dir`) to your MkDocs site build.

## Features

- Pull individual files or glob patterns from anywhere outside your `docs_dir`.
- Resolve relative paths against the MkDocs configuration directory.
- Create real source `File` objects at build time.
- Automatically watch added sources during [live reload](https://www.mkdocs.org/user-guide/configuration/#live-reloading) (`mkdocs serve`).

## Installation

### From PyPI

```bash
pip install mkdocs-extrafiles
```

or, with [astral-uv](https://docs.astral.sh/uv/):

```bash
uv add mkdocs-extrafiles
```

### From source

```bash
git clone https://github.com/your-username/mkdocs-extrafiles.git
cd mkdocs-extrafiles
pip install .
```

## Quickstart

- `src` accepts absolute paths or paths relative to the MkDocs config file.
- `dest` accepts relative paths to the `docs_dir`; during a build they are created in `site_dir`.

Glob patterns (`*`, `?`, `[]`) require `dest` to end with `/` to indicate a directory target.

### Configuration

Enable the plugin and list the external sources inside `mkdocs.yml`:

```yaml
plugins:
  - search
  - extrafiles:
      files:
        - src: README.md # file
          dest: external/README.md
        - src: LICENSE # file -> rename/relocate
          dest: external/LICENSE.txt
        - src: assets/** # glob (copies all matches)
          dest: external/assets/ # must end with '/' to indicate a directory
```

### Behavior

- `mkdocs serve`: Sources are streamed directly; nothing is copied into `docs_dir`, but live reload will watch the resolved absolute paths.
- `mkdocs build`: Virtual files are materialized into `site_dir`, so deployments that publish only the build output still include the added sources.
- Missing sources will result in a `FileNotFoundError` exception.

## Troubleshooting

If you are using [`mkdocs-gen-files`](https://github.com/oprypin/mkdocs-gen-files) then you _must_ place `extrafiles` after `mkdocs-gen-files` in your plugin settings.

```yaml
plugins:
  - search
  - gen-files:
      scripts:
        - gen_ref_pages.py
  - extrafiles:
      files:
        - src: ../README.md
          dest: extras/README.md
```

## Developer Guide

Set up a development environment with [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --all-extras --all-groups
uv run pytest tests
uv run ruff check
uv run ruff format
```

### Key Development Principles

- Maintain 100% passing tests, at least 80% test coverage, formatting, and linting before opening a pull request.
- Update docstrings alongside code changes to keep the generated reference accurate.

### Document Generation

Documentation is generated using [MkDocs](https://www.mkdocs.org/). The technical reference surfaces the reStructuredText style docstrings from the package's source code.

```bash
uv sync --group docs

# Run the development server
uv run mkdocs serve -f mkdocs/mkdocs.yaml
# Build the static site
uv run mkdocs build -f mkdocs/mkdocs.yaml
```

## Contributing

Contributions are welcome! To get started:

1. Fork the repository and create a new branch.
2. Install development dependencies (see the [developer guide](#developer-guide)).
3. Add or update tests together with your change.
4. Run the full test, linting, and formatting suite locally.
5. Submit a pull request describing your changes and referencing any relevant issues.

For major changes, open an issue first to discuss your proposal.

## License

Distributed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html). See [LICENSE](LICENSE) for details.

## Contact

Questions or issues? Please open an issue on the repository's issue tracker.

<!-- Badges -->

[pypi-lnk]: https://pypi.org/p/mkdocs-extrafiles
[pypi-img]: https://img.shields.io/pypi/v/mkdocs-extrafiles.svg
[tests-lnk]: https://github.com/paddy74/mkdocs-extrafiles/actions/workflows/ci.yaml
[tests-img]: https://img.shields.io/github/actions/workflow/status/paddy74/mkdocs-extrafiles/ci.yaml?logo=github&label=tests&branch=main
[codecov-lnk]: https://codecov.io/github/paddy74/mkdocs-extrafiles
[codecov-img]: https://codecov.io/github/paddy74/mkdocs-extrafiles/graph/badge.svg?token=2J3G1C9BCX
[codestyle-lnk]: https://docs.astral.sh/ruff
[codestyle-img]: https://img.shields.io/badge/code%20style-ruff-000000.svg
[license-lnk]: ./LICENSE
[license-img]: https://img.shields.io/pypi/l/mkdocs-extrafiles?color=light-green&logo=gplv3&logoColor=white
