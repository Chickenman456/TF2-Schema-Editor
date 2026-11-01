import importlib.metadata
import platform
import shutil
import sys
from pathlib import Path


if platform.machine().lower() not in ("amd64", "x86_64"):
    raise RuntimeError("Build the Windows x64 release with 64-bit x86 Python.")

ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT / "dist" / "TF2SchemaWorkshop"

for filename in ("PORTABLE_README.txt", "THIRD_PARTY_NOTICES.md"):
    shutil.copy2(ROOT / filename, PACKAGE_DIR / filename)

pyinstaller = importlib.metadata.distribution("PyInstaller")
pyinstaller_license = next(
    path for path in pyinstaller.files or ()
    if str(path).endswith("licenses/COPYING.txt")
)
shutil.copy2(
    pyinstaller.locate_file(pyinstaller_license),
    PACKAGE_DIR / "PyInstaller-COPYING.txt",
)

python_license = Path(sys.base_prefix) / "LICENSE.txt"
if not python_license.is_file():
    raise FileNotFoundError("The bundled Python runtime license was not found.")
shutil.copy2(python_license, PACKAGE_DIR / "Python-LICENSE.txt")
