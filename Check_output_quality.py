import argparse

from covid_model_parametrization import utils, qc

utils.config_logger()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("country_iso3", help="Country ISO3")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    qc.qc(args.country_iso3)
