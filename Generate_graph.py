import argparse
import logging

from covid_model_parametrization.utils import utils
from covid_model_parametrization.graph import graph


utils.config_logger()
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("country_iso3", help="Country ISO3")
    parser.add_argument(
        "--end_date",
        default=None,
        type=str,
        help="Last date to include in graph, equals start date of Bucky simulation. Passed in as string, formatted as YYYY-MM-DD. If not passed in, will take max date in covid data"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        graph(args.country_iso3.upper(), args.end_date)
    except Exception as err:
        logger.error(
            f"Cannot generate graph file, check log for details"
        )
        raise err

