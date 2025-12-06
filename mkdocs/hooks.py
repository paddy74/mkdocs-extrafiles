from mkdocs.config.defaults import MkDocsConfig  # pyright: ignore[reportMissingImports]

from mkdocs_extrafiles import _version as md


def on_config(config: MkDocsConfig):
    config.site_name = f"{md.__title__} {md.__version__}"
    config.site_author = md.__author__
    config.copyright = f"Copyright &copy; {md.__copyright__}"

    return config
