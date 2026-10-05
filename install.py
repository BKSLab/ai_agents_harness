"""Bootstrap dependencies into a repository-local virtualenv, then run the installer."""

from pathlib import Path
import subprocess
import sys
import venv


def main():
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent
    directory = root / ".venv"
    python = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(directory)
    subprocess.run([str(python), "-m", "pip", "install", "-e", str(root), "--disable-pip-version-check"], check=True)
    return subprocess.run([str(python), str(root / "manage.py"), "install", *sys.argv[1:]], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
