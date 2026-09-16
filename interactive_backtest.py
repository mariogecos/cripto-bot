"""Backtest interactivo por consola: pide cripto, parametros (precargados) y fechas.

Ejecutar:
    python interactive_backtest.py

Ver las criptos disponibles sin correr el backtest:
    python interactive_backtest.py --list-symbols

Compilar a .exe (Windows, con PyInstaller instalado en el venv):
    pyinstaller --onefile --name backtest_bot interactive_backtest.py
El .exe queda en dist/backtest_bot.exe
"""
from __future__ import annotations

import argparse

from config import settings
from src.strategy import STRATEGIES


def listar_simbolos() -> list[str]:
    """Trae de Binance los pares que se pueden operar contra USDT (ej. BTCUSDT)."""
    import requests

    resp = requests.get("https://api.binance.com/api/v3/exchangeInfo", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    simbolos = [
        s["symbol"]
        for s in data["symbols"]
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    ]
    return sorted(simbolos)


def _print_seguro(texto: str) -> None:
    """Imprime sin romper en consolas Windows que no soportan ciertos caracteres."""
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode("ascii", errors="replace").decode("ascii"))


def mostrar_simbolos() -> None:
    print("\nBuscando en Binance las criptos disponibles contra USDT...\n")
    try:
        simbolos = listar_simbolos()
    except Exception as exc:  # noqa: BLE001
        print(f"No se pudo consultar Binance: {exc}")
        return

    columnas = 6
    for i in range(0, len(simbolos), columnas):
        fila = simbolos[i : i + columnas]
        _print_seguro("  " + "".join(s.ljust(14) for s in fila))

    print(f"\nTotal: {len(simbolos)} criptos disponibles (pares contra USDT).")
    print(
        "Ojo: algunos simbolos son acciones tokenizadas, no criptomonedas "
        "(por ej. terminan en 'B' antes de USDT, como AAPLBUSDT o TSLABUSDT)."
    )
    print("Para usar una: copia el simbolo tal cual aparece, ej. 'SOLUSDT'.\n")


def ask(prompt: str, default):
    """Pide un valor por consola. Enter vacio = usa el default."""
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "s", "si", "y", "yes")
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError:
            return float(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


def elegir_estrategia() -> str:
    claves = list(STRATEGIES)
    print("\nEstrategias disponibles:")
    for i, k in enumerate(claves, start=1):
        marca = " (actual en .env)" if k == settings.strategy else ""
        print(f"  {i}) {k}{marca}")
    default_idx = claves.index(settings.strategy) + 1 if settings.strategy in claves else 1
    while True:
        raw = input(f"Elegi una estrategia [1-{len(claves)}] [{default_idx}]: ").strip()
        if not raw:
            return claves[default_idx - 1]
        if raw.isdigit() and 1 <= int(raw) <= len(claves):
            return claves[int(raw) - 1]
        if raw in claves:
            return raw
        print("Opcion invalida, proba de nuevo.")


def pedir_parametros_estrategia(key: str) -> dict:
    cls = STRATEGIES[key]
    print(f"\nParametros de '{key}' (Enter = usar el valor precargado):")
    params = {}
    for nombre, default in cls.defaults.items():
        actual = getattr(settings, nombre, default)
        params[nombre] = ask(f"  {nombre}", actual)
    return params


def pedir_simbolo() -> str:
    while True:
        symbol = ask(
            "Simbolo (ej. BTCUSDT, ETHUSDT; escribi 'lista' para ver las disponibles)",
            settings.symbol,
        ).upper()
        if symbol == "LISTA":
            mostrar_simbolos()
            continue
        return symbol


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest interactivo por consola.")
    ap.add_argument(
        "--list-symbols",
        action="store_true",
        help="Muestra las criptos que se pueden operar (pares contra USDT) y sale.",
    )
    args = ap.parse_args()

    if args.list_symbols:
        mostrar_simbolos()
        return

    print("=== Backtest interactivo ===\n")

    symbol = pedir_simbolo()
    interval = ask("Intervalo de vela (1m,5m,15m,1h,4h,1d...)", settings.interval)

    strategy_key = elegir_estrategia()
    strategy_params = pedir_parametros_estrategia(strategy_key)

    print("\nFechas del backtest (formato libre, ej. '1 Jan 2024' o '2024-01-01'):")
    start = ask("  Desde", "1 Jan 2024")
    end = ask("  Hasta (vacio = hoy)", "")
    end = end or None

    print("\nCapital y gestion de riesgo:")
    cash = ask("  Capital inicial (USDT)", 10_000.0)
    sl = ask("  Stop-loss (fraccion, ej 0.02 = 2%)", settings.stop_loss_pct)
    tp = ask("  Take-profit (fraccion, ej 0.04 = 4%)", settings.take_profit_pct)

    print("\nDescargando datos y corriendo backtest...\n")
    from backtest.run_backtest import run_backtest  # import tardio: pesado (binance/backtesting)

    try:
        run_backtest(
            strategy_key=strategy_key,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            cash=cash,
            sl=sl,
            tp=tp,
            strategy_params=strategy_params,
        )
        print("\nListo. Reporte en backtest/report.html")
    except Exception as exc:  # noqa: BLE001
        print(f"\nError corriendo el backtest: {exc}")

    input("\nPresiona Enter para salir...")


if __name__ == "__main__":
    main()
