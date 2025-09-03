import argparse
import os.path
import sys

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from stock import COL_STOCK_ID  # noqa: E402

conf.parse_config()


def filter_stocks(input_file, filter_file, output_file):
    # Read input stocks
    input_df = pd.read_csv(input_file)
    input_stocks = set(input_df[COL_STOCK_ID])

    # Read filter stocks
    filter_df = pd.read_csv(filter_file)
    filter_stocks = set(filter_df[COL_STOCK_ID])

    # Filter stocks
    result_stocks = input_stocks - filter_stocks

    # Create output dataframe and sort
    output_df = pd.DataFrame({COL_STOCK_ID: sorted(result_stocks)})

    # Write output
    output_df.to_csv(output_file, index=False, encoding="utf_8_sig")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Filter stocks based on input and filter lists."
    )
    parser.add_argument(
        "-i", required=True, help="Input CSV file containing list of stocks"
    )
    parser.add_argument(
        "-f", required=True, help="Filter CSV file containing list of stocks to exclude"
    )
    parser.add_argument(
        "-o", default="output.csv", help="Output CSV file (default: output.csv)"
    )

    args = parser.parse_args()

    filter_stocks(args.i, args.f, args.o)
