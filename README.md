# cripto-bot

Bot de compra/venta automatica en Binance (spot). Estrategia de ejemplo:
cruce de medias moviles + filtro RSI, con stop-loss / take-profit y limite de
perdida diaria.

> ⚠️ Software educativo. El trading automatico puede perder dinero. Usa la
> **testnet** y `DRY_RUN=true` hasta validar tu estrategia con backtest y
> semanas de paper trading.

## Estructura

```
config.py                carga .env
src/exchange.py          wrapper de Binance (testnet/prod)
src/data.py              OHLCV -> DataFrame
src/indicators.py        SMA, RSI (agrega aca EMA, MACD, Bollinger...)
src/strategy.py          DEFINICION UNICA de estrategias (bot + backtest)
src/risk.py              tamano de posicion, SL/TP, limite diario
src/executor.py          senal -> orden (o simulacion si DRY_RUN)
src/bot.py               loop principal
src/notify.py            alertas Telegram (opcional)
backtest/run_backtest.py         backtest de cualquier estrategia de src/strategy.py (CLI con flags)
backtest/ejemplo_parametros.csv  plantilla de ejemplo para el modo lote (CSV)
interactive_backtest.py          backtest guiado por consola, pregunta cripto/parametros/fechas
batch_backtest.py                corre varios backtests desde un CSV y junta todo en un .txt
tests/                           pytest
```

## Estrategias

Todas viven en `src/strategy.py`. Cada una implementa `compute(df)`, que agrega
indicadores y dos columnas booleanas `entry` / `exit`. El bot y el backtest usan
exactamente la misma definicion.

Incluidas:
- `sma_cross_rsi` : cruce de medias moviles + filtro de RSI
- `rsi_reversion` : compra sobrevendido (RSI < 30), vende al recuperar (RSI > 55)

Elegir cual usa el bot: variable `STRATEGY` en `.env`.

Probar en backtest sin tocar `.env`:
```powershell
python -m backtest.run_backtest --strategy rsi_reversion --interval 4h
python -m backtest.run_backtest --strategy sma_cross_rsi --params "fast_ma=50,slow_ma=200"
```

Agregar una nueva: subclase de `Strategy` con `key`, `defaults` y `compute`,
y sumarla a `STRATEGIES`. Queda disponible en el bot y el backtest al instante.

## Puesta en marcha (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# edita .env con tus claves de https://testnet.binance.vision
```

## Backtest

Un backtest es probar una estrategia sobre datos historicos, para ver que
hubiera pasado si la hubieras usado en el pasado, sin arriesgar plata real.

### Modo interactivo: el asistente que te va preguntando (recomendado)

Es la forma mas facil de usar el bot si no sos programador: abris una consola,
escribis un comando, y el programa te va preguntando todo paso a paso. No hace
falta saber nada de codigo ni recordar ningun flag.

**Paso a paso:**

1. Abri PowerShell en la carpeta del proyecto.
2. Si es la primera vez, segui la seccion ["Puesta en marcha"](#puesta-en-marcha-windows--powershell)
   de mas arriba (una sola vez).
3. Ejecuta:

   ```powershell
   python interactive_backtest.py
   ```

4. Contesta lo que te pregunta. En cada pregunta aparece un valor entre
   corchetes, por ejemplo `[BTCUSDT]`: ese es el valor "por defecto", ya
   probado, así que si apretas **Enter sin escribir nada** el programa lo usa
   tal cual. Solo escribi algo si queres cambiarlo.
5. Al final te muestra los resultados (cuanto hubiera ganado o perdido esa
   estrategia en el periodo elegido) y deja un grafico en
   `backtest\report.html` que podes abrir haciendo doble clic (se abre en el
   navegador).

**¿No sabes que cripto poner?** En la primera pregunta (Simbolo) escribi
`lista` y Enter: te muestra todas las criptos disponibles para elegir. Tambien
podes pedir la lista sin entrar al asistente:

```powershell
python interactive_backtest.py --list-symbols
```

El simbolo siempre es el nombre de la cripto seguido de `USDT` (la moneda
contra la que se compara), por ejemplo: `BTCUSDT` (Bitcoin), `ETHUSDT`
(Ethereum), `SOLUSDT` (Solana). Copialo tal cual aparece en la lista.

> Algunos simbolos de la lista no son criptomonedas sino acciones
> tokenizadas (por ejemplo `AAPLBUSDT` es Apple, `TSLABUSDT` es Tesla) — se
> reconocen porque terminan en una `B` antes de `USDT`. Evitalos si queres
> operar solo criptomonedas.

**Ejemplo real de una sesion completa** (lo que escribis vos esta despues de
cada `:`; donde no escribis nada, quedas apretando Enter):

```
> python interactive_backtest.py
=== Backtest interactivo ===

Simbolo (ej. BTCUSDT, ETHUSDT; escribi 'lista' para ver las disponibles) [BTCUSDT]: ETHUSDT
Intervalo de vela (1m,5m,15m,1h,4h,1d...) [1h]:

Estrategias disponibles:
  1) sma_cross_rsi (actual en .env)
  2) rsi_reversion
Elegi una estrategia [1-2] [1]: 2

Parametros de 'rsi_reversion' (Enter = usar el valor precargado):
  rsi_period [14]:
  rsi_buy [30.0]: 25
  rsi_exit [55.0]:

Fechas del backtest (formato libre, ej. '1 Jan 2024' o '2024-01-01'):
  Desde [1 Jan 2024]: 1 Jun 2024
  Hasta (vacio = hoy) []:

Capital y gestion de riesgo:
  Capital inicial (USDT) [10000.0]:
  Stop-loss (fraccion, ej 0.02 = 2%) [0.03]:
  Take-profit (fraccion, ej 0.04 = 4%) [0.03]:

Descargando datos y corriendo backtest...
... (aca aparecen las estadisticas y las operaciones) ...
Listo. Reporte en backtest/report.html
```

En este ejemplo se eligio Ethereum, la estrategia `rsi_reversion` cambiando
solo el parametro `rsi_buy` a 25, y un periodo desde junio de 2024 hasta hoy.
Todo lo demas quedo con el valor precargado.

### Por linea de comandos, con flags (para uso avanzado / automatizado)

```powershell
python -m backtest.run_backtest --symbol BTCUSDT --interval 1h --start "1 Jan 2023"
python -m backtest.run_backtest --strategy rsi_reversion --interval 4h --end "1 Jun 2024"
python -m backtest.run_backtest --strategy sma_cross_rsi --params "fast_ma=50,slow_ma=200"
```

Genera `backtest/report.html`, igual que el modo interactivo.

### Modo lote (CSV): probar varias combinaciones de una sola vez

Si queres comparar varias criptos, estrategias o periodos sin tener que abrir
el asistente una y otra vez, arma una planilla (CSV) con una fila por cada
backtest que queras correr, y el programa los corre todos seguidos y te deja
un solo archivo de texto con los resultados.

**Paso a paso:**

1. Abri `backtest/ejemplo_parametros.csv` con Excel, Google Sheets o el
   Bloc de notas — ya viene armado con un ejemplo de Bitcoin, Ethereum y
   Solana. Usalo como plantilla: copialo, edita las filas o agrega nuevas, y
   guardalo (manteniendo el formato CSV).
2. Corre:

   ```powershell
   python batch_backtest.py backtest/ejemplo_parametros.csv
   ```

3. Al terminar te deja un archivo como
   `backtest\resultados_20260916_143000.txt` (la fecha y hora del momento en
   que lo corriste) con:
   - un **cuadro resumen** arriba, con una fila por cada backtest y sus
     resultados principales (retorno %, cantidad de operaciones, etc.), para
     comparar todo de un vistazo;
   - y mas abajo, el **detalle completo** de cada backtest (lo mismo que
     verias en pantalla si lo corrieras uno por uno).

   Abrilo con el Bloc de notas o cualquier editor de texto.

**Columnas de la planilla** (las columnas van en la primera fila; dejar una
celda vacia usa el valor precargado de `.env`, igual que en el asistente):

| Columna       | Que va                                  | Obligatoria |
|---------------|------------------------------------------|:-----------:|
| `simbolo`     | ej. `BTCUSDT`, `ETHUSDT`, `SOLUSDT`       | si          |
| `intervalo`   | ej. `1h`, `4h`, `1d`                      | no          |
| `estrategia`  | `sma_cross_rsi` o `rsi_reversion`         | no          |
| `parametros`  | ej. `fast_ma=50,slow_ma=200`              | no          |
| `desde`       | ej. `1 Jan 2024`                          | no          |
| `hasta`       | ej. `1 Jun 2024` (vacio = hasta hoy)      | no          |
| `capital`     | capital inicial, ej. `10000`              | no          |
| `stop_loss`   | fraccion, ej. `0.02` = 2%                 | no          |
| `take_profit` | fraccion, ej. `0.04` = 4%                 | no          |

Ejemplo (contenido de `backtest/ejemplo_parametros.csv`, con Bitcoin,
Ethereum y Solana):

```csv
simbolo,intervalo,estrategia,parametros,desde,hasta,capital,stop_loss,take_profit
BTCUSDT,1h,sma_cross_rsi,,1 Jan 2024,1 Jun 2024,10000,0.02,0.04
ETHUSDT,4h,rsi_reversion,"rsi_buy=25,rsi_exit=60",1 Jan 2024,,10000,0.03,0.05
SOLUSDT,1h,sma_cross_rsi,"fast_ma=10,slow_ma=30",1 Mar 2024,1 Jun 2024,5000,0.02,0.04
```

Si una fila falla (por ejemplo un simbolo mal escrito), no frena a las demas:
queda marcada como `ERROR` en el cuadro resumen y el resto sigue corriendo.

Tambien podes elegir vos el nombre del archivo de salida:

```powershell
python batch_backtest.py backtest/ejemplo_parametros.csv --out backtest/mi_comparativa.txt
```

## Ejecutar el bot (testnet, sin ordenes reales)

Con `BINANCE_TESTNET=true` y `DRY_RUN=true` en `.env`:

```powershell
python -m src.bot
```

El bot loguea que compraria/venderia sin enviar nada. Pon `DRY_RUN=false`
(seguido en testnet) para que mande ordenes a la testnet. Solo pasa a
`BINANCE_TESTNET=false` cuando confies en los resultados y con capital minimo.

## Tests

```powershell
pytest
```

## Siguientes pasos sugeridos

- Persistir operaciones y PnL en SQLite.
- Reconciliar la posicion real desde el balance al arrancar (hoy asume flat).
- Anadir mas estrategias y comparar por backtest (Sharpe, max drawdown).
- Reintentos/backoff ante errores de red o rate limit de Binance.
