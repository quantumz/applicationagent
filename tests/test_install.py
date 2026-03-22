"""
Tests for install.sh behavior.

Runs isolated shell blocks via subprocess against a controlled tmp directory
tree — no real $HOME, no pip, no Playwright. Each test sets up the exact
filesystem state the installer expects and asserts on the outcome.
"""

import stat
import subprocess
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

FAKE_DESKTOP_FILE = """\
[Desktop Entry]
Version=1.0
Type=Application
Name=ApplicationAgent
Exec=/fake/launch.sh
Icon=applications-internet
Terminal=false
"""


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(['bash', '-c', script], capture_output=True, text=True)


def _fake_local_apps(tmp_path: Path) -> Path:
    """Create ~/.local/share/applications with a pre-built .desktop file."""
    local_apps = tmp_path / '.local' / 'share' / 'applications'
    local_apps.mkdir(parents=True)
    (local_apps / 'applicationagent.desktop').write_text(FAKE_DESKTOP_FILE)
    return local_apps


# ── Launch script generation ───────────────────────────────────────────────────

class TestLaunchScript:
    """Desktop launch.sh heredoc generation."""

    def _gen_launch(self, install_dir: Path, launcher: Path) -> str:
        venv_dir = install_dir / '.venv'
        return f"""
INSTALL_DIR="{install_dir}"
VENV_DIR="{venv_dir}"
PORT=8080
LAUNCHER="{launcher}"
LOG_FILE="{install_dir}/logs/ui.log"
mkdir -p "{install_dir}"
cat > "$LAUNCHER" << 'LAUNCHEOF'
#!/bin/bash
INSTALL_DIR="{install_dir}"
VENV_DIR="{venv_dir}"
PORT=8080
URL="http://localhost:${{PORT}}"
LOG="{install_dir}/logs/ui.log"
mkdir -p "$(dirname "${{LOG}}")"
export APPLICATIONAGENT_ROOT="${{INSTALL_DIR}}"
"${{VENV_DIR}}/bin/python" "${{INSTALL_DIR}}/ui/app.py" >> "${{LOG}}" 2>&1 &
LAUNCHEOF
chmod +x "$LAUNCHER"
"""

    def test_launch_script_created(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        launcher = install_dir / 'launch.sh'
        result = _run(self._gen_launch(install_dir, launcher))
        assert result.returncode == 0
        assert launcher.exists()

    def test_launch_script_is_executable(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        launcher = install_dir / 'launch.sh'
        _run(self._gen_launch(install_dir, launcher))
        mode = launcher.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_launch_script_exports_applicationagent_root(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        launcher = install_dir / 'launch.sh'
        _run(self._gen_launch(install_dir, launcher))
        content = launcher.read_text()
        assert 'export APPLICATIONAGENT_ROOT' in content

    def test_launch_script_root_points_to_install_dir(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        launcher = install_dir / 'launch.sh'
        _run(self._gen_launch(install_dir, launcher))
        content = launcher.read_text()
        assert str(install_dir) in content

    def test_launch_script_venv_inside_install_dir(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        launcher = install_dir / 'launch.sh'
        _run(self._gen_launch(install_dir, launcher))
        content = launcher.read_text()
        assert str(install_dir / '.venv') in content

    def test_launch_script_starts_flask(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        launcher = install_dir / 'launch.sh'
        _run(self._gen_launch(install_dir, launcher))
        content = launcher.read_text()
        assert 'ui/app.py' in content


# ── CLI wrapper generation ─────────────────────────────────────────────────────

class TestCliWrappers:
    """CLI wrapper and applicationagent-ui generation."""

    def _gen_cli_wrappers(self, install_dir: Path, bin_dir: Path,
                          venv_dir: Path = None) -> str:
        # Default: venv inside install dir. Power users may pass a custom path.
        if venv_dir is None:
            venv_dir = install_dir / '.venv'
        return f"""
INSTALL_DIR="{install_dir}"
VENV_DIR="{venv_dir}"
BIN_DIR="{bin_dir}"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/applicationagent" << CLIEOF
#!/bin/bash
source "{venv_dir}/bin/activate"
cd "{install_dir}"
python applicationagent.py "\\$@"
CLIEOF
chmod +x "$BIN_DIR/applicationagent"

cat > "$BIN_DIR/applicationagent-ui" << UIEOF
#!/bin/bash
export APPLICATIONAGENT_ROOT="{install_dir}"
cd "{install_dir}"
"{venv_dir}/bin/python" ui/app.py
UIEOF
chmod +x "$BIN_DIR/applicationagent-ui"
"""

    def test_cli_wrapper_created(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        assert (bin_dir / 'applicationagent').exists()

    def test_cli_wrapper_is_executable(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        mode = (bin_dir / 'applicationagent').stat().st_mode
        assert mode & stat.S_IXUSR

    def test_ui_wrapper_created(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        assert (bin_dir / 'applicationagent-ui').exists()

    def test_ui_wrapper_is_executable(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        mode = (bin_dir / 'applicationagent-ui').stat().st_mode
        assert mode & stat.S_IXUSR

    def test_ui_wrapper_exports_applicationagent_root(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        content = (bin_dir / 'applicationagent-ui').read_text()
        assert 'export APPLICATIONAGENT_ROOT' in content

    def test_ui_wrapper_root_points_to_install_dir(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        content = (bin_dir / 'applicationagent-ui').read_text()
        assert str(install_dir) in content

    def test_ui_wrapper_default_venv_inside_install_dir(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        content = (bin_dir / 'applicationagent-ui').read_text()
        assert str(install_dir / '.venv') in content

    def test_ui_wrapper_custom_venv_path(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        custom_venv = tmp_path / '.venv' / 'myapp'
        _run(self._gen_cli_wrappers(install_dir, bin_dir, venv_dir=custom_venv))
        content = (bin_dir / 'applicationagent-ui').read_text()
        assert str(custom_venv) in content

    def test_cli_wrapper_invokes_applicationagent_py(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        content = (bin_dir / 'applicationagent').read_text()
        assert 'applicationagent.py' in content

    def test_ui_wrapper_uses_venv_python(self, tmp_path):
        """applicationagent-ui must invoke ${VENV_DIR}/bin/python — no bare 'python'."""
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        venv_dir = install_dir / '.venv'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        content = (bin_dir / 'applicationagent-ui').read_text()
        assert f'{venv_dir}/bin/python' in content

    def test_ui_wrapper_does_not_source_activate(self, tmp_path):
        """applicationagent-ui runs without activating venv — uses absolute python path."""
        install_dir = tmp_path / 'applicationagent'
        bin_dir = tmp_path / 'bin'
        _run(self._gen_cli_wrappers(install_dir, bin_dir))
        content = (bin_dir / 'applicationagent-ui').read_text()
        assert 'source' not in content


# ── Runtime directory creation ─────────────────────────────────────────────────

class TestRuntimeDirs:
    """Installer creates required runtime directories."""

    def _mkdir_block(self, install_dir: Path) -> str:
        return f"""
INSTALL_DIR="{install_dir}"
mkdir -p \
    "$INSTALL_DIR/data" \
    "$INSTALL_DIR/output/pdf" \
    "$INSTALL_DIR/output/excel" \
    "$INSTALL_DIR/logs"
"""

    def test_data_dir_created(self, tmp_path):
        _run(self._mkdir_block(tmp_path))
        assert (tmp_path / 'data').is_dir()

    def test_pdf_output_dir_created(self, tmp_path):
        _run(self._mkdir_block(tmp_path))
        assert (tmp_path / 'output' / 'pdf').is_dir()

    def test_excel_output_dir_created(self, tmp_path):
        _run(self._mkdir_block(tmp_path))
        assert (tmp_path / 'output' / 'excel').is_dir()

    def test_logs_dir_created(self, tmp_path):
        _run(self._mkdir_block(tmp_path))
        assert (tmp_path / 'logs').is_dir()


# ── .env setup ─────────────────────────────────────────────────────────────────

class TestEnvSetup:
    """.env created from sample on first install; not overwritten on reinstall."""

    def _env_block(self, install_dir: Path) -> str:
        return f"""
INSTALL_DIR="{install_dir}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.sample" "$INSTALL_DIR/.env"
fi
"""

    def test_env_created_from_sample(self, tmp_path):
        (tmp_path / '.env.sample').write_text('ANTHROPIC_API_KEY=\n')
        _run(self._env_block(tmp_path))
        assert (tmp_path / '.env').exists()

    def test_env_contains_sample_content(self, tmp_path):
        (tmp_path / '.env.sample').write_text('ANTHROPIC_API_KEY=\n')
        _run(self._env_block(tmp_path))
        assert 'ANTHROPIC_API_KEY' in (tmp_path / '.env').read_text()

    def test_existing_env_not_overwritten(self, tmp_path):
        (tmp_path / '.env.sample').write_text('ANTHROPIC_API_KEY=\n')
        (tmp_path / '.env').write_text('ANTHROPIC_API_KEY=sk-ant-existing\n')
        _run(self._env_block(tmp_path))
        assert 'sk-ant-existing' in (tmp_path / '.env').read_text()


# ── PATH entry in shell rc ─────────────────────────────────────────────────────

class TestPathEntry:
    """BIN_DIR is added to PATH in rc files exactly once."""

    def _path_block(self, home: Path, bin_dir: Path) -> str:
        return f"""
HOME="{home}"
BIN_DIR="{bin_dir}"
PATH_UPDATED=0
for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$RC" ] && ! grep -q "$BIN_DIR" "$RC" 2>/dev/null; then
        echo "export PATH=\\"{bin_dir}:\\$PATH\\"" >> "$RC"
        PATH_UPDATED=1
    fi
done
"""

    def test_path_added_to_bashrc(self, tmp_path):
        (tmp_path / '.bashrc').write_text('# existing\n')
        bin_dir = tmp_path / '.local' / 'bin'
        _run(self._path_block(tmp_path, bin_dir))
        assert str(bin_dir) in (tmp_path / '.bashrc').read_text()

    def test_path_not_duplicated_in_bashrc(self, tmp_path):
        bin_dir = tmp_path / '.local' / 'bin'
        (tmp_path / '.bashrc').write_text(f'export PATH="{bin_dir}:$PATH"\n')
        _run(self._path_block(tmp_path, bin_dir))
        content = (tmp_path / '.bashrc').read_text()
        assert content.count(str(bin_dir)) == 1

    def test_path_skipped_if_no_zshrc(self, tmp_path):
        (tmp_path / '.bashrc').write_text('# existing\n')
        bin_dir = tmp_path / '.local' / 'bin'
        result = _run(self._path_block(tmp_path, bin_dir))
        assert result.returncode == 0
        assert not (tmp_path / '.zshrc').exists()


# ── Desktop shortcut creation ─────────────────────────────────────────────────

class TestDesktopShortcut:

    def _shortcut_block(self, desktop_dir: Path, local_apps: Path) -> str:
        """The exact shell block from install.sh, parameterised for testing."""
        return f"""
DESKTOP_SHORTCUT="{desktop_dir}"
DESKTOP_DIR="{local_apps}"
if [ -d "$DESKTOP_SHORTCUT" ]; then
    cp "$DESKTOP_DIR/applicationagent.desktop" "$DESKTOP_SHORTCUT/"
    chmod +x "$DESKTOP_SHORTCUT/applicationagent.desktop"
    gio set "$DESKTOP_SHORTCUT/applicationagent.desktop" metadata::trusted true 2>/dev/null || true
fi
"""

    def test_shortcut_created_when_desktop_exists(self, tmp_path):
        desktop = tmp_path / 'Desktop'
        desktop.mkdir()
        local_apps = _fake_local_apps(tmp_path)

        result = _run(self._shortcut_block(desktop, local_apps))

        assert result.returncode == 0
        assert (desktop / 'applicationagent.desktop').exists()

    def test_shortcut_is_executable(self, tmp_path):
        desktop = tmp_path / 'Desktop'
        desktop.mkdir()
        local_apps = _fake_local_apps(tmp_path)

        _run(self._shortcut_block(desktop, local_apps))

        mode = (desktop / 'applicationagent.desktop').stat().st_mode
        assert mode & stat.S_IXUSR, 'Desktop shortcut must be owner-executable'

    def test_shortcut_content_matches_source(self, tmp_path):
        desktop = tmp_path / 'Desktop'
        desktop.mkdir()
        local_apps = _fake_local_apps(tmp_path)

        _run(self._shortcut_block(desktop, local_apps))

        content = (desktop / 'applicationagent.desktop').read_text()
        assert 'ApplicationAgent' in content
        assert '[Desktop Entry]' in content

    def test_no_error_when_desktop_dir_absent(self, tmp_path):
        """No Desktop dir — block must exit 0 and not create any file."""
        local_apps = _fake_local_apps(tmp_path)
        desktop = tmp_path / 'Desktop'  # intentionally not created

        result = _run(self._shortcut_block(desktop, local_apps))

        assert result.returncode == 0
        assert not (desktop / 'applicationagent.desktop').exists()

    def test_gio_failure_does_not_abort(self, tmp_path):
        """gio set is best-effort — failure must not stop the block."""
        desktop = tmp_path / 'Desktop'
        desktop.mkdir()
        local_apps = _fake_local_apps(tmp_path)

        # Override gio with a command that always fails
        script = f"""
gio() {{ return 1; }}
export -f gio
{self._shortcut_block(desktop, local_apps)}
"""
        result = _run(script)

        assert result.returncode == 0
        assert (desktop / 'applicationagent.desktop').exists()


# ── rsync file exclusions ──────────────────────────────────────────────────────

class TestRsyncExcludes:
    """
    Install copies source to install dir via rsync.
    tests/ must be excluded; scripts/ and docs/ must be included.
    """

    def _rsync_block(self, src: Path, dst: Path) -> str:
        return f"""
mkdir -p "{dst}"
rsync -a \
    --exclude='.git/' \
    --exclude='data/' \
    --exclude='*.db' \
    --exclude='output/' \
    --exclude='logs/' \
    --exclude='venv/' \
    --exclude='.venv/' \
    --exclude='tests/' \
    --exclude='*.pyc' \
    --exclude='__pycache__/' \
    --exclude='.env' \
    "{src}/" "{dst}/"
"""

    def _make_source(self, src: Path) -> None:
        """Create a minimal fake source tree."""
        for d in ('tests', 'scripts', 'docs', 'core', 'ui'):
            (src / d).mkdir(parents=True)
            (src / d / 'placeholder.txt').write_text(d)

    def test_tests_dir_not_copied(self, tmp_path):
        src = tmp_path / 'src'
        dst = tmp_path / 'dst'
        self._make_source(src)
        result = _run(self._rsync_block(src, dst))
        assert result.returncode == 0
        assert not (dst / 'tests').exists()

    def test_scripts_dir_copied(self, tmp_path):
        src = tmp_path / 'src'
        dst = tmp_path / 'dst'
        self._make_source(src)
        _run(self._rsync_block(src, dst))
        assert (dst / 'scripts').exists()

    def test_docs_dir_copied(self, tmp_path):
        src = tmp_path / 'src'
        dst = tmp_path / 'dst'
        self._make_source(src)
        _run(self._rsync_block(src, dst))
        assert (dst / 'docs').exists()

    def test_core_dir_copied(self, tmp_path):
        src = tmp_path / 'src'
        dst = tmp_path / 'dst'
        self._make_source(src)
        _run(self._rsync_block(src, dst))
        assert (dst / 'core').exists()

    def test_venv_dir_not_copied(self, tmp_path):
        src = tmp_path / 'src'
        dst = tmp_path / 'dst'
        self._make_source(src)
        (src / '.venv').mkdir()
        (src / '.venv' / 'pyvenv.cfg').write_text('home = /usr/bin\n')
        _run(self._rsync_block(src, dst))
        assert not (dst / '.venv').exists()

    def test_data_dir_not_copied(self, tmp_path):
        src = tmp_path / 'src'
        dst = tmp_path / 'dst'
        self._make_source(src)
        (src / 'data').mkdir()
        (src / 'data' / 'applicationagent.db').write_text('sqlite')
        _run(self._rsync_block(src, dst))
        assert not (dst / 'data').exists()

    def test_db_files_not_copied(self, tmp_path):
        """*.db files at root level (outside data/) are also excluded."""
        src = tmp_path / 'src'
        dst = tmp_path / 'dst'
        self._make_source(src)
        (src / 'applicationagent.db').write_text('sqlite')
        _run(self._rsync_block(src, dst))
        assert not (dst / 'applicationagent.db').exists()


# ── Reinstall guard ────────────────────────────────────────────────────────────

class TestReinstallGuard:
    """
    If install dir already exists, installer must warn and prompt [y/N].
    'N' (or Enter) aborts. 'y' continues.
    --clean wipes install dir without prompting.
    """

    def _guard_block(self, install_dir: Path, clean: bool = False) -> str:
        clean_val = "true" if clean else "false"
        return f"""
INSTALL_DIR="{install_dir}"
CLEAN_INSTALL={clean_val}
if [ -d "$INSTALL_DIR" ]; then
    if [ "$CLEAN_INSTALL" = "true" ]; then
        rm -rf "$INSTALL_DIR"
        echo "WIPED"
    else
        read -rp "  Reinstall over existing installation? [y/N]: " REINSTALL
        if [[ ! "$REINSTALL" =~ ^[Yy]$ ]]; then
            echo "ABORTED"
            exit 0
        fi
    fi
fi
echo "CONTINUING"
"""

    def test_guard_aborts_on_n(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        install_dir.mkdir()
        result = _run(f'echo "n" | bash -c \'{self._guard_block(install_dir)}\'')
        assert result.returncode == 0
        assert 'ABORTED' in result.stdout
        assert 'CONTINUING' not in result.stdout

    def test_guard_aborts_on_empty_enter(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        install_dir.mkdir()
        result = _run(f'echo "" | bash -c \'{self._guard_block(install_dir)}\'')
        assert result.returncode == 0
        assert 'ABORTED' in result.stdout

    def test_guard_continues_on_y(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        install_dir.mkdir()
        result = _run(f'echo "y" | bash -c \'{self._guard_block(install_dir)}\'')
        assert result.returncode == 0
        assert 'CONTINUING' in result.stdout
        assert 'ABORTED' not in result.stdout

    def test_guard_continues_on_capital_y(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        install_dir.mkdir()
        result = _run(f'echo "Y" | bash -c \'{self._guard_block(install_dir)}\'')
        assert result.returncode == 0
        assert 'CONTINUING' in result.stdout

    def test_guard_skipped_when_no_existing_install(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        # directory does NOT exist
        result = _run(f'echo "n" | bash -c \'{self._guard_block(install_dir)}\'')
        assert result.returncode == 0
        assert 'CONTINUING' in result.stdout
        assert 'ABORTED' not in result.stdout

    def test_clean_flag_wipes_install_dir(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        install_dir.mkdir()
        (install_dir / 'data').mkdir()
        (install_dir / 'data' / 'applicationagent.db').write_text('sqlite')
        result = _run(self._guard_block(install_dir, clean=True))
        assert result.returncode == 0
        assert 'WIPED' in result.stdout
        assert not install_dir.exists()

    def test_clean_flag_continues_after_wipe(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        install_dir.mkdir()
        result = _run(self._guard_block(install_dir, clean=True))
        assert result.returncode == 0
        assert 'CONTINUING' in result.stdout

    def test_clean_flag_no_prompt(self, tmp_path):
        """--clean must not hang waiting for user input."""
        install_dir = tmp_path / 'applicationagent'
        install_dir.mkdir()
        # No echo pipe — would hang if it hit read
        result = subprocess.run(
            ['bash', '-c', self._guard_block(install_dir, clean=True)],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0

    def test_clean_flag_noop_when_no_existing_install(self, tmp_path):
        install_dir = tmp_path / 'applicationagent'
        # no existing dir — --clean is a no-op, install proceeds
        result = _run(self._guard_block(install_dir, clean=True))
        assert result.returncode == 0
        assert 'CONTINUING' in result.stdout
