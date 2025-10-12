import logging
from glob import glob
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from mkdocs.config import Config
from mkdocs.config import config_options as opt
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.livereload import LiveReloadServer
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files

logger = logging.getLogger(__name__)

_GLOB_CHARS = ("*", "?", "[")  # glob detection


class PluginConfig(Config):
    """
    The configuration options of `mkdocs_extrafiles`, written in `mkdocs.yml`

    Provide a list of source file paths relative to the MkDocs config directory and the destination they will resolve against (relative to the docs directory).

    ```yaml
    plugins:
      - extrafiles:
          files:
            - src: README.md              # file
              dest: external/README.md
            - src: LICENSE                # file -> rename/relocate
              dest: external/LICENSE.txt
            - src: assets/**              # glob (copies all matches)
              dest: external/assets/      # must end with '/' to indicate a directory
    ```
    """

    files = opt.Type(list, default=[])
    enabled = opt.Type(bool, default=True)


class ExtraFilesPlugin(BasePlugin[PluginConfig]):
    """
    An `mkdocs` plugin.

    This plugin defines the following event hooks:

    - `on_config`
    - `on_files`
    - `on_serve`

    Check the [Developing Plugins](https://www.mkdocs.org/user-guide/plugins/#developing-plugins) page of `mkdocs` for more information about its plugin system.
    """

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig | None:
        """
        Instantiate our Markdown extension.

        Hook for the [`on_config` event](https://www.mkdocs.org/user-guide/plugins/#on_config).
        """
        if not self.plugin_enabled:
            logger.debug("extrafiles: plugin disabled, skipping.")
            return config

        config_path = getattr(config, "config_file_path", None)
        if config_path:
            self.config_dir = Path(config_path).resolve().parent
        else:
            self.config_dir = Path.cwd()

        logger.debug(
            f"extrafiles: docs_dir={Path(config['docs_dir']).resolve()} config_dir={self.config_dir}"
        )

        return config

    @property
    def plugin_enabled(self) -> bool:
        """
        Tell if the plugin is enabled or not.

        :return: Whether the plugin is enabled.
        :rtype: bool
        """
        return self.config.enabled

    def _glob_base_dir(self, pattern: str) -> Path:
        """
        Determine the base directory for a glob so relative paths are preserved.

        The base is derived from the leading non-glob path segments. For relative patterns it is anchored to the plugin's config directory. For absolute patterns the resolved absolute segments are used directly.
        """
        path_obj = Path(pattern)
        base_parts: list[str] = []
        for part in path_obj.parts:
            if any(ch in part for ch in ("*", "?", "[")):
                break
            base_parts.append(part)

        if path_obj.is_absolute():
            if base_parts:
                base_path = Path(*base_parts)
            else:
                base_path = Path(path_obj.anchor or path_obj.root or "/")
            return base_path.resolve()

        base_path = self.config_dir.joinpath(*base_parts)
        return base_path.resolve()

    def _expand_items(self):
        """
        Yields (src_path, dest_uri) pairs. Supports:
          - single file -> file
          - glob -> directory (dest must end with '/')
        """
        if not self.plugin_enabled:
            logger.debug("extrafiles: plugin disabled, skipping item expansion.")
            return

        config_dir = self.config_dir

        for item in self.config["files"]:
            src = item["src"]
            dest = item["dest"]

            if Path(dest).is_absolute():
                raise ValueError(f"extrafiles: dest must be relative, got {dest!r}")

            if any(ch in src for ch in _GLOB_CHARS):
                # glob mode: dest must be a directory (end with '/')
                if not dest.endswith(("/", "\\")):
                    raise ValueError(
                        f"When using glob in src='{src}', dest must be a directory (end with '/')."
                    )

                pattern_path = Path(src)
                if pattern_path.is_absolute():
                    pattern = str(pattern_path)
                else:
                    pattern = str((config_dir / pattern_path).resolve())

                dest_root = PurePosixPath(dest.rstrip("/\\"))
                base_dir = self._glob_base_dir(src)
                for match in glob(pattern, recursive=True):
                    s = Path(match).resolve()
                    if s.is_file():
                        try:
                            rel_path = s.relative_to(base_dir)
                        except ValueError:
                            rel_path = Path(s.name)
                        if rel_path == Path("."):
                            rel_path = Path(s.name)
                        relative_posix = PurePosixPath(*rel_path.parts)
                        dest_uri = dest_root / relative_posix
                        yield s, dest_uri.as_posix()
            else:
                s = Path(src)
                if not s.is_absolute():
                    s = config_dir / s
                s = s.resolve()
                dest_uri = PurePosixPath(dest.replace("\\", "/")).as_posix()
                yield s, dest_uri

    def _iter_watch_paths(self) -> set[Path]:
        """
        Collect paths to monitor for changes while serving with auto-resolve, so that newly added sources are watched witout requiring a restart.
        """
        if not self.plugin_enabled:
            return set()

        watch_paths: set[Path] = set()
        for item in self.config["files"]:
            src = item["src"]

            p = Path(src)
            if any(ch in src for ch in _GLOB_CHARS):
                watch_paths.add(self._glob_base_dir(src))
            else:
                if not p.is_absolute():
                    p = self.config_dir / p
                watch_paths.add(p.resolve())

        return watch_paths

    @staticmethod
    def _nearest_existing_path(path: Path) -> Path | None:
        """
        Return the path if it exists, otherwise return the nearest existing parent.

        This ensures directories are watched even if the given path does not yet exist.
        """
        for p in (path, *path.parents):
            if p.exists():
                return p.resolve()
        return None

    def on_files(self, files: Files, *, config: MkDocsConfig) -> Files:
        if not self.plugin_enabled:
            logger.debug("extrafiles: plugin disabled, skipping file staging.")
            return files

        staged = 0
        for src, dest_uri in self._expand_items():
            if not src.exists():
                raise FileNotFoundError(f"extrafiles: source not found: {src}")

            existing = files.get_file_from_path(dest_uri)
            if existing is not None:
                files.remove(existing)

            generated = File.generated(config, dest_uri, abs_src_path=str(src))
            files.append(generated)
            staged += 1

        logger.debug(
            "extrafiles: staged %s file(s) for build into %s",
            staged,
            config.site_dir,
        )
        return files

    def on_serve(
        self,
        server: LiveReloadServer,
        /,
        *,
        config: MkDocsConfig,
        builder: Callable[..., Any],
    ) -> LiveReloadServer | None:
        """Make MkDocs monitor the source files when serving auto-reload."""
        if not self.plugin_enabled:
            logger.debug(
                "extrafiles: plugin disabled, skipping live reload registration."
            )
            return server

        watched: set[Path] = set()

        for p in self._iter_watch_paths():
            watch_path = self._nearest_existing_path(p)

            if watch_path is None:
                continue
            if watch_path not in watched:
                try:
                    server.watch(str(watch_path))
                    watched.add(watch_path)
                except Exception:
                    logger.exception("extrafiles: failed to watch %s", watch_path)

        try:
            for src, _ in self._expand_items():
                if not src.exists():
                    continue

                resolved = src.resolve()
                if resolved in watched:
                    continue

                try:
                    server.watch(str(resolved))
                    watched.add(resolved)
                except Exception:
                    logger.exception("extrafiles: failed to watch %s", resolved)
        except Exception:
            logger.exception("extrafiles: failed while expanding items for watch")

        return server
