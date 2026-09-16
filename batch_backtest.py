"""Corre varios backtests desde un CSV y junta todo en un .txt (resumen + detalle).

Ejecutar:
    python batch_backtest.py mis_backtests.csv
    python batch_backtest.py mis_backtests.csv --out resultados/comparativa.txt

El CSV necesita una fila de encabezados con estas columnas (todas opcionales
salvo que se indique lo contrario; si se dejan vacias se usa el valor
precargado de `.env`, igual que en el asistente interactivo):

    simbolo       (ej. BTCUSDT) - obligatoria
    intervalo     (ej. 1h, 4h, 1d) - default: INTERVAL de .env
    estrategia    (sma_cross_rsi o rsi_reversion) - default: STRATEGY de .env
    parametros    (ej. "fast_ma=50,slow_ma=200") - default: los de .env
    desde         (ej. "1 Jan 2024") - default: "1 Jan 2024"
    hasta         (ej. "1 Jun 2024"; vacio = hasta hoy) - default: vacio
    capital       (ej. 10000) - default: 10000
    stop_loss     (ej. 0.02 = 2%) - default: STOP_LOSS_PCT de .env
    take_profit   (ej. 0.04 = 4%) - default: TAKE_PROFIT_PCT de .env

Ver `backtest/ejemplo_parametros.csv` para un ejemplo listo para copiar.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from contextlib import redirect_stdout
from datetime import datetime

from config import settings
from backtest.run_backtest import _parse_params, run_backtest

COLUMNAS_RESUMEN = [
    ("Simbolo", "symbol"),
    ("Estrategia", "strategy_key"),
    ("Desde", "start"),
    ("Hasta", "end"),
    ("Capital final", "equity_final"),
    ("Retorno %", "return_pct"),
    ("Operaciones", "trades"),
    ("Win rate %", "win_rate"),
    ("Max drawdown %", "max_dd"),
]


def leer_filas(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("El CSV esta vacio o no tiene encabezados.")
        # Normalizamos encabezados: minusculas y sin espacios.
        reader.fieldnames = [c.strip().lower() for c in reader.fieldnames]
        return [row for row in reader if any((v or "").strip() for v in row.values())]


def _valor(row: dict, clave: str, default):
    v = (row.get(clave) or "").strip()
    return v if v else default


def _valor_float(row: dict, clave: str, default: float) -> float:
    v = (row.get(clave) or "").strip()
    return float(v) if v else default


def procesar_fila(n: int, row: dict) -> dict:
    """Corre un backtest para una fila del CSV. Devuelve datos para el resumen + salida completa."""
    symbol = _valor(row, "simbolo", settings.symbol).upper()
    if not symbol:
        raise ValueError("La columna 'simbolo' es obligatoria y esta vacia en esta fila.")

    interval = _valor(row, "intervalo", settings.interval)
    strategy_key = _valor(row, "estrategia", settings.strategy)
    params = _parse_params(_valor(row, "parametros", ""))
    start = _valor(row, "desde", "1 Jan 2024")
    end = _valor(row, "hasta", "") or None
    cash = _valor_float(row, "capital", 10_000.0)
    sl = _valor_float(row, "stop_loss", settings.stop_loss_pct)
    tp = _valor_float(row, "take_profit", settings.take_profit_pct)

    buffer = io.StringIO()
    encabezado = f"=== Fila {n}: {symbol} | {strategy_key} | {start} -> {end or 'hoy'} ==="
    try:
        with redirect_stdout(buffer):
            stats = run_backtest(
                strategy_key=strategy_key,
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
                cash=cash,
                sl=sl,
                tp=tp,
                strategy_params=params,
                plot=False,
            )
        print(f"{encabezado} -> OK")
        return {
            "ok": True,
            "encabezado": encabezado,
            "detalle": buffer.getvalue(),
            "symbol": symbol,
            "strategy_key": strategy_key,
            "start": start,
            "end": end or "hoy",
            "equity_final": round(stats["Equity Final [$]"], 2),
            "return_pct": round(stats["Return [%]"], 2),
            "trades": int(stats["# Trades"]),
            "win_rate": round(stats["Win Rate [%]"], 2) if stats["# Trades"] else "--",
            "max_dd": round(stats["Max. Drawdown [%]"], 2),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"{encabezado} -> ERROR: {exc}")
        return {
            "ok": False,
            "encabezado": encabezado,
            "detalle": f"{buffer.getvalue()}\nERROR: {exc}\n",
            "symbol": symbol,
            "strategy_key": strategy_key,
            "start": start,
            "end": end or "hoy",
            "equity_final": "--",
            "return_pct": "--",
            "trades": "--",
            "win_rate": "--",
            "max_dd": "--",
        }


def armar_cuadro_resumen(resultados: list[dict]) -> str:
    encabezados = [titulo for titulo, _ in COLUMNAS_RESUMEN]
    filas = [[str(r[clave]) for _, clave in COLUMNAS_RESUMEN] for r in resultados]
    anchos = [
        max(len(encabezados[i]), *(len(f[i]) for f in filas)) if filas else len(encabezados[i])
        for i in range(len(encabezados))
    ]

    def fila_fmt(vals: list[str]) -> str:
        return " | ".join(v.ljust(anchos[i]) for i, v in enumerate(vals))

    linea = "-+-".join("-" * a for a in anchos)
    out = [fila_fmt(encabezados), linea]
    out.extend(fila_fmt(f) for f in filas)
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Corre varios backtests desde un CSV.")
    ap.add_argument("csv", help="Ruta al CSV con las columnas (ver el encabezado del archivo)")
    ap.add_argument(
        "--out",
        default=None,
        help="Ruta del .txt de salida (default: backtest/resultados_<fecha_hora>.txt)",
    )
    args = ap.parse_args()

    filas = leer_filas(args.csv)
    if not filas:
        print("El CSV no tiene filas con datos.")
        sys.exit(1)

    print(f"Corriendo {len(filas)} backtest(s) desde '{args.csv}'...\n")
    resultados = [procesar_fila(i, row) for i, row in enumerate(filas, start=1)]

    out_path = args.out or datetime.now().strftime("backtest/resultados_%Y%m%d_%H%M%S.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=== CUADRO RESUMEN ===\n\n")
        f.write(armar_cuadro_resumen(resultados))
        f.write("\n\n=== DETALLE POR BACKTEST ===\n")
        for r in resultados:
            f.write(f"\n{r['encabezado']}\n")
            f.write(r["detalle"])
            f.write("\n")

    ok = sum(1 for r in resultados if r["ok"])
    print(f"\nListo: {ok}/{len(resultados)} backtests OK. Resultado guardado en {out_path}")


if __name__ == "__main__":
    main()
