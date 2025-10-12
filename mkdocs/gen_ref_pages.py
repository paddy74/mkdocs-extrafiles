"""Generate the code reference pages."""

import logging
from pathlib import Path, PurePosixPath

import mkdocs_gen_files

logger = logging.getLogger(__name__)


def gen_ref_pages(root_dir: Path, source_dir: Path, output_dir: str | Path) -> None:
    """Emit mkdocstrings-compatible reference pages and navigation entries.

    :param root_dir: Project root directory used to resolve edit links
    :type root_dir: Path
    :param source_dir: Directory containing the Python packages to document
    :type source_dir: Path
    :param output_dir: Output directory for the generated files; must be relative (non-escaping) to the docs directory.
    :type output_dir: str | Path
    :raises ValueError: If `output_dir` is absolute, escapes the docs directory, or no Python modules are found
    """

    # output_dir must be a relative, non-escaping path
    output_dir = Path(output_dir)
    if output_dir.is_absolute():
        raise ValueError("output_dir must be relative to the docs directory")
    if any(part == ".." for part in output_dir.parts):
        raise ValueError("output_dir must not traverse outside the docs directory")

    root_dir = root_dir.resolve()
    source_dir = source_dir.resolve()

    # Exit early if source_dir has no .py files
    py_files = sorted(source_dir.rglob("*.py"))
    if not py_files:
        raise ValueError(f"no Python modules found under {source_dir}")

    nav = mkdocs_gen_files.Nav()

    for path in py_files:
        module_path = path.relative_to(source_dir).with_suffix("")
        doc_path = path.relative_to(source_dir).with_suffix(".md")
        full_doc_path = output_dir / doc_path

        module_parts = module_path.parts

        if module_parts[-1] == "__main__":
            logger.debug("skip __main__ module: %s", path)
            continue
        if module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
            doc_path = doc_path.with_name("index.md")
            full_doc_path = full_doc_path.with_name("index.md")

        full_parts = (source_dir.name,) + module_parts
        doc_uri = PurePosixPath(doc_path).as_posix()  # normalize nav entries
        nav[full_parts] = doc_uri

        if not module_parts:
            identifier = source_dir.name
        else:
            identifier = ".".join(full_parts)

        with mkdocs_gen_files.open(full_doc_path, "w") as fd:
            print("::: " + identifier, file=fd)
        logger.debug("generated doc for %s -> %s", identifier, full_doc_path)

        mkdocs_gen_files.set_edit_path(full_doc_path, path.relative_to(root_dir))

    with mkdocs_gen_files.open("ref/NAV_REF.md", "w") as nav_file:
        nav_file.writelines(nav.build_literate_nav())


root = Path(__file__).parent.parent
src = root / "mkdocs_extrafiles"
gen_ref_pages(root, src, "ref")
