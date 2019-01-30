# Example HFT-ish Algorithm for Alpaca Trading API

The aim of this algorithm is to capture slight moves in the bid/ask spread
as they happen. It is only intended to work for high-volume stocks where there
are frequent moves of 1 cent exactly.  It is one of the trading strategies
based on order book imbalance. For more details about it, please refer to
[Darryl Shen, 2015](http://eprints.maths.ox.ac.uk/1895/1/Darryl%20Shen%20%28for%20archive%29.pdf)
or other online articles.

This algorithm will make many trades on the same security each day, so any
account running it will quickly encounter PDT rules. Please make sure your
account balance is well above $25,000 before running this script in a live
environment.

This script also presents a basic framework for streaming-based algorithms.
You can learn how to write your algorithm based on the real-time price updates.

## Setup

This algorithm runs with Python 3.6 or above. It uses
[Alpaca Python SDK](https://pypi.org/project/alpaca-trade-api/) so make
sure install it beforehand, or if you have [pipenv](https://pipenv.readthedocs.io),
you can install it by

```sh
$ pipenv install
```

in this directory.

## API Key

In order to run this algorithm, you have to have Alpaca Trading API key.
Please obtain it from the dashboard and set it in enviroment variables.

```sh
export APCA_API_KEY_ID=<your key id>
export APCA_API_SECRET_KEY=<your secret key>
```

## Run

```
$ python ./tick_taker.py
```

The parameters are following.

- `--symbol`: the stock to trade (defaults to "SNAP")
- `--quantity`: the maximum number of shares to hold at once. Note that this does not account for any existing position; the algorithm only tracks what is bought as part of its execution. (Default 500, minimum 100.)
- `--key-id`: your API key ID. (Can also be set via the APCA_API_KEY_ID environment variable.)
- `--secret-key`: your API key secret. (Can also be set via the APCA_API_SECRET_KEY environment variable.)
- `--base-url`: the URL to connect to. (Can also be set via the APCA_API_BASE_URL environment variable. Defaults to "https://paper-api.alpaca.markets" if using a paper account key, "https://api.alpaca.markets" otherwise.)

The algorithm can be stopped at any time by sending a keyboard interrupt `CTRL+C` to the console. (You may need to send two `CTRL+C` commands to kill the process depending where in the execution you catch it.)

## Note

Please also note that this algorithm uses the Polygon streaming API with Alpaca API key,
so you have to have a live trading account setup. For more details about the data
requirements, please see
[Alpaca documentation](https://docs.alpaca.markets/web-api/market-data/).
