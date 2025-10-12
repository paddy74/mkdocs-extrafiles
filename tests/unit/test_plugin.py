"""Unit tests exercising the ExtraFilesPlugin behaviors."""

from __future__ import annotations

from collections.abc import Callable
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


class DummyServer:
    """Capture watch registrations from the plugin."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def watch(self, path: str) -> None:
        self.calls.append(path)


@pytest.fixture
def plugin_factory(tmp_path: Path) -> Callable[..., ExtraFilesPlugin]:
    """Return a factory for building a plugin bound to the temporary config directory."""

    def factory(
        *,
        files: Iterable[dict[str, str]] | None = None,
        enabled: bool = True,
    ) -> ExtraFilesPlugin:
        plugin = ExtraFilesPlugin()
        plugin.config = DummyPluginConfig(files=files, enabled=enabled)
        plugin.config_dir = Path(tmp_path)
        return plugin

    return factory


@pytest.fixture
def build_config(tmp_path: Path) -> DummyMkDocsBuildConfig:
    """Provide a build configuration rooted at the temporary site directory."""
    return DummyMkDocsBuildConfig(site_dir=tmp_path / "site")


def test_plugin_enabled_property(plugin_factory) -> None:
    """Ensure plugin_enabled mirrors the configuration flag."""
    plugin = plugin_factory(enabled=True)
    assert plugin.plugin_enabled is True
    plugin_disabled = plugin_factory(enabled=False)
    assert plugin_disabled.plugin_enabled is False


def test_disabled_plugin_is_noop(plugin_factory, build_config) -> None:
    """Disabled plugin must not yield items, stage files, or watch sources."""
    plugin = plugin_factory(
        files=[{"src": "notes.txt", "dest": "external/notes.txt"}],
        enabled=False,
    )
    assert plugin.plugin_enabled is False
    assert list(plugin._expand_items() or []) == []
    files = Files([])
    result = plugin.on_files(files, config=build_config)
    assert result is files
    assert list(result) == []
    server = DummyServer()
    plugin.on_serve(server, config=build_config, builder=lambda: None)
    assert server.calls == []


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


def test_expand_items_rejects_absolute_destination(plugin_factory) -> None:
    """Absolute destination paths should be rejected to keep MkDocs paths relative."""
    plugin = plugin_factory(files=[{"src": "source.txt", "dest": "/absolute/path.txt"}])
    with pytest.raises(ValueError):
        list(plugin._expand_items())


def test_expand_items_requires_directory_for_glob_dest(plugin_factory) -> None:
    """Globs require the destination to end with a slash indicating a directory."""
    plugin = plugin_factory(files=[{"src": "*.txt", "dest": "external"}])
    with pytest.raises(ValueError):
        list(plugin._expand_items())


def test_expand_items_handles_single_file(plugin_factory, tmp_path: Path) -> None:
    """Single-file entries resolve relative sources and normalize the destination URI."""
    src = tmp_path / "notes.txt"
    src.write_text("content")
    plugin = plugin_factory(files=[{"src": "notes.txt", "dest": "external\\notes.txt"}])
    items = list(plugin._expand_items())
    assert items == [(src.resolve(), "external/notes.txt")]


def test_expand_items_glob_preserves_structure(plugin_factory, tmp_path: Path) -> None:
    """Glob sources expand all matching files while preserving their relative structure."""
    data_dir = tmp_path / "assets"
    nested_dir = data_dir / "nested"
    nested_dir.mkdir(parents=True)
    (data_dir / "first.txt").write_text("a")
    (nested_dir / "second.txt").write_text("b")
    (data_dir / "shared.txt").write_text("root")
    (nested_dir / "shared.txt").write_text("child")
    (nested_dir / "ignore.bin").write_bytes(b"\x00")
    plugin = plugin_factory(files=[{"src": "assets/**/*.txt", "dest": "external/"}])
    dest_map = {dest: src for src, dest in plugin._expand_items()}
    assert dest_map == {
        "external/first.txt": (data_dir / "first.txt").resolve(),
        "external/nested/second.txt": (nested_dir / "second.txt").resolve(),
        "external/shared.txt": (data_dir / "shared.txt").resolve(),
        "external/nested/shared.txt": (nested_dir / "shared.txt").resolve(),
    }


def test_on_files_raises_when_source_missing(plugin_factory, build_config) -> None:
    """Ensure missing sources produce a FileNotFoundError during staging."""
    plugin = plugin_factory(
        files=[{"src": "missing.txt", "dest": "external/missing.txt"}]
    )
    files = Files([])
    with pytest.raises(FileNotFoundError):
        plugin.on_files(files, config=build_config)


def test_on_files_replaces_existing_entries(
    plugin_factory, build_config, tmp_path: Path
) -> None:
    """Existing files targeting the same destination should be replaced by generated entries."""
    src = tmp_path / "README.md"
    src.write_text("# docs")
    plugin = plugin_factory(files=[{"src": "README.md", "dest": "external/README.md"}])
    existing = File(
        "external/README.md",
        src_dir="src",
        dest_dir=build_config.site_dir,
        use_directory_urls=False,
    )
    files = Files([existing])
    result = plugin.on_files(files, config=build_config)
    generated = result.get_file_from_path("external/README.md")
    assert generated is not existing
    assert generated.abs_src_path == str(src.resolve())


def test_on_serve_registers_existing_sources(
    plugin_factory, build_config, tmp_path: Path
) -> None:
    """Existing source files should be registered with the live reload server."""
    src = tmp_path / "example.txt"
    src.write_text("data")
    plugin = plugin_factory(
        files=[{"src": "example.txt", "dest": "external/example.txt"}]
    )
    server = DummyServer()
    plugin.on_serve(server, config=build_config, builder=lambda: None)
    assert server.calls == [str(src.resolve())]


def test_on_serve_skips_missing_sources(
    plugin_factory, build_config, tmp_path: Path
) -> None:
    """Missing glob matches should not register watchers or raise an error."""
    plugin = plugin_factory(
        files=[{"src": "not-there.txt", "dest": "external/not-there.txt"}]
    )
    server = DummyServer()
    plugin.on_serve(server, config=build_config, builder=lambda: None)
    assert server.calls == [str(tmp_path)]


def test_on_serve_swallows_internal_errors(
    plugin_factory, build_config, tmp_path: Path
) -> None:
    """Any unexpected exception while expanding sources should be ignored."""
    plugin = plugin_factory()
    plugin._expand_items = lambda: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[assignment]
    server = DummyServer()
    plugin.on_serve(server, config=build_config, builder=lambda: None)
    assert server.calls == []
