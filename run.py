from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def show_banner() -> None:
    print("\n" + "=" * 70)
    print(" CRIPTO-BOT - Menú principal")
    print("=" * 70)
    print("1) Correr tests")
    print("2) Inicializar base de datos")
    print("3) Arrancar bot")
    print("4) Abrir backtest interactivo")
    print("5) Salir")
    print("=" * 70)


def run_command(label: str, command: list[str]) -> int:
    print(f"\n--- {label} ---")
    try:
        result = subprocess.run(command, cwd=str(ROOT), check=False)
        print(f"\n[{label}] código de salida: {result.returncode}")
        return result.returncode
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        return 130


def main() -> int:
    while True:
        show_banner()
        try:
            choice = input("Elegí una opción (1-5): ").strip()
        except EOFError:
            print("\nSe recibió EOF del terminal. Saliendo del menú.")
            return 0

        if choice == "1":
            run_command("Correr tests", [sys.executable, "-m", "pytest", "tests", "-q"])
        elif choice == "2":
            run_command("Inicializar base de datos", [sys.executable, "scripts/init_db.py"])
        elif choice == "3":
            run_command("Arrancar bot", [sys.executable, "-m", "src.bot"])
        elif choice == "4":
            run_command("Backtest interactivo", [sys.executable, "interactive_backtest.py"])
        elif choice == "5":
            print("\nChau 👋")
            return 0
        else:
            print("Opción inválida. Elegí una opción del 1 al 5.")

        input("\nPresioná Enter para volver al menú...")


if __name__ == "__main__":
    raise SystemExit(main())
