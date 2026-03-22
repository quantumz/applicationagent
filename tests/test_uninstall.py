"""
Tests for uninstall.sh behavior.

Runs isolated shell blocks via subprocess against controlled tmp directories.
No real $HOME touched. Each test sets up exactly the filesystem state
uninstall.sh expects and asserts on the outcome.
"""

import subprocess
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(['bash', '-c', script], capture_output=True, text=True)


def _make_install(tmp_path: Path) -> Path:
    """Create a minimal installed app directory."""
    install_dir = tmp_path / '.local' / 'applicationagent'
    (install_dir / '.venv' / 'bin').mkdir(parents=True)
    (install_dir / 'ui' / 'app.py').parent.mkdir(parents=True)
    (install_dir / 'ui' / 'app.py').write_text('# app')
    (install_dir / 'data').mkdir()
    (install_dir / 'logs').mkdir()
    return install_dir


def _make_bin_wrappers(tmp_path: Path, install_dir: Path,
                       venv_dir: Path = None) -> Path:
    """Create CLI wrappers referencing install_dir."""
    if venv_dir is None:
        venv_dir = install_dir / '.venv'
    bin_dir = tmp_path / '.local' / 'bin'
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / 'applicationagent').write_text(
        f'#!/bin/bash\nsource "{venv_dir}/bin/activate"\ncd "{install_dir}"\npython applicationagent.py "$@"\n'
    )
    (bin_dir / 'applicationagent-ui').write_text(
        f'#!/bin/bash\nexport APPLICATIONAGENT_ROOT="{install_dir}"\nsource "{venv_dir}/bin/activate"\ncd "{install_dir}"\npython ui/app.py\n'
    )
    return bin_dir


def _make_desktop(tmp_path: Path) -> Path:
    """Create .desktop file in ~/.local/share/applications."""
    desktop_dir = tmp_path / '.local' / 'share' / 'applications'
    desktop_dir.mkdir(parents=True)
    (desktop_dir / 'applicationagent.desktop').write_text('[Desktop Entry]\nName=ApplicationAgent\n')
    return desktop_dir


# ── Install dir removal ────────────────────────────────────────────────────────

class TestInstallDirRemoval:

    def _remove_block(self, install_dir: Path) -> str:
        return f"""
INSTALL_DIR="{install_dir}"
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
fi
"""

    def test_install_dir_removed(self, tmp_path):
        install_dir = _make_install(tmp_path)
        _run(self._remove_block(install_dir))
        assert not install_dir.exists()

    def test_internal_venv_removed_with_install_dir(self, tmp_path):
        install_dir = _make_install(tmp_path)
        venv_dir = install_dir / '.venv'
        assert venv_dir.exists()
        _run(self._remove_block(install_dir))
        assert not venv_dir.exists()

    def test_no_error_when_install_dir_absent(self, tmp_path):
        install_dir = tmp_path / '.local' / 'applicationagent'
        result = _run(self._remove_block(install_dir))
        assert result.returncode == 0


# ── External venv detection ────────────────────────────────────────────────────

class TestVenvDetection:
    """Uninstaller reads venv path from CLI wrapper for power-user installs."""

    def _detect_block(self, bin_dir: Path, install_dir: Path) -> str:
        return f"""
BIN_DIR="{bin_dir}"
INSTALL_DIR="{install_dir}"
DEFAULT_VENV="$INSTALL_DIR/.venv"
DETECTED_VENV=""
if [ -f "$BIN_DIR/applicationagent-ui" ]; then
    DETECTED_VENV=$(grep -oP 'source "\\K[^"]+(?=/bin/activate)' "$BIN_DIR/applicationagent-ui" 2>/dev/null || true)
fi
if [ -z "$DETECTED_VENV" ] && [ -f "$BIN_DIR/applicationagent" ]; then
    DETECTED_VENV=$(grep -oP 'source "\\K[^"]+(?=/bin/activate)' "$BIN_DIR/applicationagent" 2>/dev/null || true)
fi
VENV_DIR="${{DETECTED_VENV:-$DEFAULT_VENV}}"
echo "$VENV_DIR"
"""

    def test_detects_internal_venv(self, tmp_path):
        install_dir = _make_install(tmp_path)
        bin_dir = _make_bin_wrappers(tmp_path, install_dir)
        result = _run(self._detect_block(bin_dir, install_dir))
        assert result.stdout.strip() == str(install_dir / '.venv')

    def test_detects_custom_external_venv(self, tmp_path):
        install_dir = _make_install(tmp_path)
        custom_venv = tmp_path / '.venv' / 'myapp'
        bin_dir = _make_bin_wrappers(tmp_path, install_dir, venv_dir=custom_venv)
        result = _run(self._detect_block(bin_dir, install_dir))
        assert result.stdout.strip() == str(custom_venv)

    def test_falls_back_to_default_when_no_wrappers(self, tmp_path):
        install_dir = _make_install(tmp_path)
        bin_dir = tmp_path / '.local' / 'bin'
        bin_dir.mkdir(parents=True, exist_ok=True)
        result = _run(self._detect_block(bin_dir, install_dir))
        assert result.stdout.strip() == str(install_dir / '.venv')

    def test_venv_is_internal_when_inside_install_dir(self, tmp_path):
        install_dir = _make_install(tmp_path)
        bin_dir = _make_bin_wrappers(tmp_path, install_dir)
        detect = self._detect_block(bin_dir, install_dir)
        script = detect + f"""
case "$VENV_DIR" in
    "{install_dir}/"*) echo "internal" ;;
    *) echo "external" ;;
esac
"""
        result = _run(script)
        assert 'internal' in result.stdout

    def test_venv_is_external_when_outside_install_dir(self, tmp_path):
        install_dir = _make_install(tmp_path)
        custom_venv = tmp_path / '.venv' / 'myapp'
        bin_dir = _make_bin_wrappers(tmp_path, install_dir, venv_dir=custom_venv)
        detect = self._detect_block(bin_dir, install_dir)
        script = detect + f"""
case "$VENV_DIR" in
    "{install_dir}/"*) echo "internal" ;;
    *) echo "external" ;;
esac
"""
        result = _run(script)
        assert 'external' in result.stdout


# ── Desktop entry removal ──────────────────────────────────────────────────────

class TestDesktopEntryRemoval:

    def _remove_desktop_block(self, desktop_dir: Path, home: Path) -> str:
        return f"""
DESKTOP_DIR="{desktop_dir}"
HOME="{home}"
if [ -f "$DESKTOP_DIR/applicationagent.desktop" ]; then
    rm -f "$DESKTOP_DIR/applicationagent.desktop"
fi
if [ -f "$HOME/Desktop/applicationagent.desktop" ]; then
    rm -f "$HOME/Desktop/applicationagent.desktop"
fi
"""

    def test_desktop_entry_removed(self, tmp_path):
        desktop_dir = _make_desktop(tmp_path)
        _run(self._remove_desktop_block(desktop_dir, tmp_path))
        assert not (desktop_dir / 'applicationagent.desktop').exists()

    def test_desktop_shortcut_removed(self, tmp_path):
        desktop_dir = _make_desktop(tmp_path)
        shortcut = tmp_path / 'Desktop' / 'applicationagent.desktop'
        shortcut.parent.mkdir()
        shortcut.write_text('[Desktop Entry]\nName=ApplicationAgent\n')
        _run(self._remove_desktop_block(desktop_dir, tmp_path))
        assert not shortcut.exists()

    def test_no_error_when_desktop_entry_absent(self, tmp_path):
        desktop_dir = tmp_path / '.local' / 'share' / 'applications'
        desktop_dir.mkdir(parents=True)
        result = _run(self._remove_desktop_block(desktop_dir, tmp_path))
        assert result.returncode == 0


# ── CLI wrapper removal ────────────────────────────────────────────────────────

class TestCliWrapperRemoval:

    def _remove_wrappers_block(self, bin_dir: Path) -> str:
        return f"""
BIN_DIR="{bin_dir}"
for WRAPPER in applicationagent applicationagent-ui; do
    if [ -f "$BIN_DIR/$WRAPPER" ]; then
        rm -f "$BIN_DIR/$WRAPPER"
    fi
done
"""

    def test_cli_wrapper_removed(self, tmp_path):
        install_dir = _make_install(tmp_path)
        bin_dir = _make_bin_wrappers(tmp_path, install_dir)
        _run(self._remove_wrappers_block(bin_dir))
        assert not (bin_dir / 'applicationagent').exists()

    def test_ui_wrapper_removed(self, tmp_path):
        install_dir = _make_install(tmp_path)
        bin_dir = _make_bin_wrappers(tmp_path, install_dir)
        _run(self._remove_wrappers_block(bin_dir))
        assert not (bin_dir / 'applicationagent-ui').exists()

    def test_no_error_when_wrappers_absent(self, tmp_path):
        bin_dir = tmp_path / '.local' / 'bin'
        bin_dir.mkdir(parents=True)
        result = _run(self._remove_wrappers_block(bin_dir))
        assert result.returncode == 0


# ── PATH entry removal ────────────────────────────────────────────────────────

class TestPathEntryRemoval:

    def _remove_path_block(self, home: Path, bin_dir: Path) -> str:
        return f"""
HOME="{home}"
BIN_DIR="{bin_dir}"
for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$RC" ] && grep -q "$BIN_DIR" "$RC" 2>/dev/null; then
        sed -i "\\|export PATH=\\"$BIN_DIR:\\\\\\$PATH\\"|d" "$RC"
    fi
done
"""

    def test_path_entry_removed_from_bashrc(self, tmp_path):
        bin_dir = tmp_path / '.local' / 'bin'
        (tmp_path / '.bashrc').write_text(
            f'# shell config\nexport PATH="{bin_dir}:$PATH"\n# end\n'
        )
        _run(self._remove_path_block(tmp_path, bin_dir))
        content = (tmp_path / '.bashrc').read_text()
        assert str(bin_dir) not in content

    def test_other_bashrc_content_preserved(self, tmp_path):
        bin_dir = tmp_path / '.local' / 'bin'
        (tmp_path / '.bashrc').write_text(
            f'# shell config\nexport PATH="{bin_dir}:$PATH"\n# end\n'
        )
        _run(self._remove_path_block(tmp_path, bin_dir))
        content = (tmp_path / '.bashrc').read_text()
        assert '# shell config' in content
        assert '# end' in content

    def test_no_error_when_no_path_entry(self, tmp_path):
        bin_dir = tmp_path / '.local' / 'bin'
        (tmp_path / '.bashrc').write_text('# nothing here\n')
        result = _run(self._remove_path_block(tmp_path, bin_dir))
        assert result.returncode == 0

    def test_no_error_when_no_rc_files(self, tmp_path):
        bin_dir = tmp_path / '.local' / 'bin'
        result = _run(self._remove_path_block(tmp_path, bin_dir))
        assert result.returncode == 0
