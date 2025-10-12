# plugins/external_files.py
import logging
from glob import glob
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from mkdocs.config import config_options as c
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.livereload import LiveReloadServer
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files

logger = logging.getLogger(__name__)


class extrafilesPlugin(BasePlugin):
    """
    Copy files that live outside docs_dir into docs_dir before the build.

    Config:
      * Relative src paths resolve against the MkDocs config directory.
      files:
        - src: README.md              # file
          dest: external/README.md
        - src: LICENSE                # file -> rename/relocate
          dest: external/LICENSE.txt
        - src: assets/**              # glob (copies all matches)
          dest: external/assets/      # must end with '/' to indicate a directory
    """

    config_scheme = (
        ("files", c.Type(list, default=[])),  # list of {src: str, dest: str}
    )

    def on_config(self, config):
        self.docs_dir = Path(config["docs_dir"]).resolve()

        config_path = getattr(config, "config_file_path", None)
        if config_path:
            self.config_dir = Path(config_path).resolve().parent
        else:
            self.config_dir = Path.cwd()

        logger.debug(
            "external-files: docs_dir=%s config_dir=%s", self.docs_dir, self.config_dir
        )

        return config

    def _expand_items(self):
        """
        Yields (src_path, dest_uri) pairs. Supports:
          - single file -> file
          - glob -> directory (dest must end with '/')
        """
        for item in self.config["files"]:
            src = item["src"]
            dest = item["dest"]
            if Path(dest).is_absolute():
                raise ValueError(f"external-files: dest must be relative, got {dest!r}")
            if any(ch in src for ch in ["*", "?", "["]):
                # glob mode: dest must be a directory (end with '/')
                if not dest.endswith(("/", "\\")):
                    raise ValueError(
                        f"When using glob in src='{src}', dest must be a directory (end with '/')."
                    )
                pattern = src
                if not Path(pattern).is_absolute():
                    pattern = str((self.config_dir / pattern).resolve())
                matched = [Path(p).resolve() for p in glob(pattern, recursive=True)]
                for s in matched:
                    if s.is_file():
                        rel_name = s.name
                        dest_uri = PurePosixPath(dest.rstrip("/\\")) / rel_name
                        yield s, dest_uri.as_posix()
            else:
                s = Path(src)
                if not s.is_absolute():
                    s = self.config_dir / s
                s = s.resolve()
                dest_uri = PurePosixPath(dest.replace("\\", "/")).as_posix()
                yield s, dest_uri

    def on_files(self, files: Files, *, config: MkDocsConfig) -> Files:
        staged = 0
        for src, dest_uri in self._expand_items():
            if not src.exists():
                raise FileNotFoundError(f"external-files: source not found: {src}")

            existing = files.get_file_from_path(dest_uri)
            if existing is not None:
                files.remove(existing)

            generated = File.generated(config, dest_uri, abs_src_path=str(src))
            files.append(generated)
            staged += 1

        logger.debug(
            "external-files: staged %s file(s) for build into %s",
            staged,
            config.site_dir,
        )
        return files

    # Make mkdocs serve auto-reload when source files change
    def on_serve(
        self,
        server: LiveReloadServer,
        /,
        *,
        config: MkDocsConfig,
        builder: Callable[..., Any],
    ) -> LiveReloadServer | None:
        try:
            for src, _ in self._expand_items():
                if src.exists():
                    server.watch(str(src))
        except Exception:
            pass
        return server
