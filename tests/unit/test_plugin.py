"""Unit tests exercising the ExtraFilesPlugin behaviors."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest
from mkdocs.structure.files import File, Files
from pytest import MonkeyPatch

from mkdocs_extrafiles.plugin import ExtraFilesPlugin


class DummyPluginConfig(dict):
    """Minimal plugin configuration exposing mapping access and an enabled flag."""

    def __init__(
        self, *, files: Iterable[dict[str, str]] | None = None, enabled: bool = True
    ):
        super().__init__()
        self["files"] = list(files or [])
        self.enabled = enabled


class DummyMkDocsConfig(dict):
    """MkDocs configuration stub supporting key and attribute access."""

    def __init__(self, *, docs_dir: Path, config_file_path: Path | None = None):
        super().__init__()
        self["docs_dir"] = str(docs_dir)
        if config_file_path is not None:
            self.config_file_path = str(config_file_path)


class DummyPlugins:
    """Container mimicking MkDocs' plugin registry state."""

    def __init__(self, current: str = "extrafiles"):
        self._current_plugin = current


class DummyMkDocsBuildConfig:
    """MkDocs build configuration stub required when generating files."""

    def __init__(self, *, site_dir: Path, use_directory_urls: bool = False):
        self.site_dir = str(site_dir)
        self.use_directory_urls = use_directory_urls
        self.plugins = DummyPlugins()


def make_plugin(
    tmp_path: Path,
    *,
    files: Iterable[dict[str, str]] | None = None,
    enabled: bool = True,
) -> ExtraFilesPlugin:
    """Instantiate the plugin with a deterministic configuration directory."""
    plugin = ExtraFilesPlugin()
    plugin.config = DummyPluginConfig(files=files, enabled=enabled)
    plugin.config_dir = Path(tmp_path)
    return plugin


def test_plugin_enabled_property(tmp_path: Path) -> None:
    """Ensure plugin_enabled mirrors the configuration flag."""
    plugin = make_plugin(tmp_path, enabled=True)
    assert plugin.plugin_enabled is True
    plugin_disabled = make_plugin(tmp_path, enabled=False)
    assert plugin_disabled.plugin_enabled is False


def test_on_config_returns_early_when_disabled(tmp_path: Path) -> None:
    """Verify on_config short-circuits when the plugin is disabled."""
    plugin = ExtraFilesPlugin()
    plugin.config = DummyPluginConfig(enabled=False)
    config = DummyMkDocsConfig(docs_dir=tmp_path / "docs")
    result = plugin.on_config(config)
    assert result is config
    assert not hasattr(plugin, "config_dir")


def test_on_config_sets_config_dir_from_config_file(tmp_path: Path) -> None:
    """Ensure on_config stores the directory containing the mkdocs.yml file."""
    plugin = ExtraFilesPlugin()
    plugin.config = DummyPluginConfig()
    mkdocs_yml = tmp_path / "mkdocs.yml"
    config = DummyMkDocsConfig(docs_dir=tmp_path / "docs", config_file_path=mkdocs_yml)
    plugin.on_config(config)
    assert plugin.config_dir == tmp_path


def test_on_config_without_config_file_uses_cwd(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Verify on_config falls back to the current working directory when needed."""
    plugin = ExtraFilesPlugin()
    plugin.config = DummyPluginConfig()
    expected_dir = tmp_path / "cwd"
    monkeypatch.setattr("mkdocs_extrafiles.plugin.Path.cwd", lambda: expected_dir)
    config = DummyMkDocsConfig(docs_dir=tmp_path / "docs")
    plugin.on_config(config)
    assert plugin.config_dir == expected_dir


def test_expand_items_rejects_absolute_destination(tmp_path: Path) -> None:
    """Absolute destination paths should be rejected to keep MkDocs paths relative."""
    plugin = make_plugin(
        tmp_path, files=[{"src": "source.txt", "dest": "/absolute/path.txt"}]
    )
    with pytest.raises(ValueError):
        list(plugin._expand_items())


def test_expand_items_requires_directory_for_glob_dest(tmp_path: Path) -> None:
    """Globs require the destination to end with a slash indicating a directory."""
    plugin = make_plugin(tmp_path, files=[{"src": "*.txt", "dest": "external"}])
    with pytest.raises(ValueError):
        list(plugin._expand_items())


def test_expand_items_handles_single_file(tmp_path: Path) -> None:
    """Single-file entries resolve relative sources and normalize the destination URI."""
    src = tmp_path / "notes.txt"
    src.write_text("content")
    plugin = make_plugin(
        tmp_path, files=[{"src": "notes.txt", "dest": "external\\notes.txt"}]
    )
    items = list(plugin._expand_items())
    assert items == [(src.resolve(), "external/notes.txt")]


def test_expand_items_expands_glob_sources(tmp_path: Path) -> None:
    """Glob sources expand all files and map them into the destination directory."""
    data_dir = tmp_path / "assets"
    data_dir.mkdir()
    (data_dir / "first.txt").write_text("a")
    sub_dir = data_dir / "nested"
    sub_dir.mkdir()
    (sub_dir / "second.txt").write_text("b")
    (sub_dir / "ignore.bin").write_bytes(b"\x00")
    plugin = make_plugin(
        tmp_path, files=[{"src": "assets/**/*.txt", "dest": "external/"}]
    )
    items = list(plugin._expand_items())
    resolved = {dest for _, dest in items}
    assert resolved == {"external/first.txt", "external/nested/second.txt"}


def test_expand_items_preserves_relative_structure(tmp_path: Path) -> None:
    """Files with the same name under different folders should maintain structure."""
    data_dir = tmp_path / "assets"
    nested_dir = data_dir / "nested"
    nested_dir.mkdir(parents=True)
    (data_dir / "shared.txt").write_text("root")
    (nested_dir / "shared.txt").write_text("child")
    plugin = make_plugin(
        tmp_path, files=[{"src": "assets/**/*.txt", "dest": "external/"}]
    )
    dest_map = {dest: src for src, dest in plugin._expand_items()}
    assert dest_map["external/shared.txt"] == (data_dir / "shared.txt").resolve()
    assert (
        dest_map["external/nested/shared.txt"] == (nested_dir / "shared.txt").resolve()
    )


def test_on_files_raises_when_source_missing(tmp_path: Path) -> None:
    """Ensure missing sources produce a FileNotFoundError during staging."""
    plugin = make_plugin(
        tmp_path, files=[{"src": "missing.txt", "dest": "external/missing.txt"}]
    )
    files = Files([])
    config = DummyMkDocsBuildConfig(site_dir=tmp_path / "site")
    with pytest.raises(FileNotFoundError):
        plugin.on_files(files, config=config)


def test_on_files_replaces_existing_entries(tmp_path: Path) -> None:
    """Existing files targeting the same destination should be replaced by generated entries."""
    src = tmp_path / "README.md"
    src.write_text("# docs")
    plugin = make_plugin(
        tmp_path, files=[{"src": "README.md", "dest": "external/README.md"}]
    )
    config = DummyMkDocsBuildConfig(site_dir=tmp_path / "site")
    existing = File(
        "external/README.md",
        src_dir="src",
        dest_dir=config.site_dir,
        use_directory_urls=False,
    )
    files = Files([existing])
    result = plugin.on_files(files, config=config)
    generated = result.get_file_from_path("external/README.md")
    assert generated is not existing
    assert generated.abs_src_path == str(src.resolve())


def test_on_serve_registers_existing_sources(tmp_path: Path) -> None:
    """Existing source files should be registered with the live reload server."""
    src = tmp_path / "example.txt"
    src.write_text("data")
    plugin = make_plugin(
        tmp_path, files=[{"src": "example.txt", "dest": "external/example.txt"}]
    )
    server_calls: list[str] = []

    class DummyServer:
        """Capture watch registrations from the plugin."""

        def watch(self, path: str) -> None:
            server_calls.append(path)

    server = DummyServer()
    config = DummyMkDocsBuildConfig(site_dir=tmp_path / "site")
    plugin.on_serve(server, config=config, builder=lambda: None)
    assert server_calls == [str(src.resolve())]


def test_on_serve_skips_missing_sources(tmp_path: Path) -> None:
    """Missing glob matches should not register watchers or raise an error."""
    plugin = make_plugin(
        tmp_path, files=[{"src": "not-there.txt", "dest": "external/not-there.txt"}]
    )
    server_calls: list[str] = []

    class DummyServer:
        """Capture watch registrations from the plugin."""

        def watch(self, path: str) -> None:
            server_calls.append(path)

    server = DummyServer()
    config = DummyMkDocsBuildConfig(site_dir=tmp_path / "site")
    plugin.on_serve(server, config=config, builder=lambda: None)
    assert server_calls == []


def test_on_serve_swallows_internal_errors(tmp_path: Path) -> None:
    """Any unexpected exception while expanding sources should be ignored."""
    plugin = make_plugin(tmp_path)
    plugin._expand_items = lambda: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[assignment]
    server_calls: list[str] = []

    class DummyServer:
        """Capture watch registrations from the plugin."""

        def watch(self, path: str) -> None:
            server_calls.append(path)

    server = DummyServer()
    config = DummyMkDocsBuildConfig(site_dir=tmp_path / "site")
    plugin.on_serve(server, config=config, builder=lambda: None)
    assert server_calls == []
