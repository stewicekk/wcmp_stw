"""
Sestaví STW WoofMC do standalone Windows .exe pomocí PyInstalleru.
Spustit na Windows (výsledný binární .exe funguje jen na platformě, na které
se builduje -- PyInstaller nedělá cross-compile).

Použití:
    python build_exe.py

Výstup: dist/STW_WoofMC/STW_WoofMC.exe
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SPEC = ROOT / "woofmc.spec"


def main():
    if sys.platform != "win32":
        print("VAROVÁNÍ: Nejsi na Windows. Výsledný .exe bude fungovat jen na")
        print("platformě, na které tenhle skript reálně poběží (PyInstaller")
        print("nedělá cross-compile). Pokračuji, ale build nebude spustitelný.")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller není nainstalovaný. Instaluji...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    for junk in ("build", "dist"):
        junk_path = ROOT / junk
        if junk_path.exists():
            shutil.rmtree(junk_path)

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm"],
        cwd=str(ROOT),
        check=True,
    )

    exe_path = ROOT / "dist" / "STW_WoofMC" / "STW_WoofMC.exe"
    print()
    if exe_path.exists():
        print(f"Hotovo: {exe_path}")
    else:
        print("Build proběhl, ale STW_WoofMC.exe se nenašel na očekávaném místě.")
        print("Zkontroluj dist/STW_WoofMC/ ručně.")


if __name__ == "__main__":
    main()
