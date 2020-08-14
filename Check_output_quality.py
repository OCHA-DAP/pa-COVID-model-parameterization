import argparse

from covid_model_parametrization import utils, qc


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("country_iso3", help="Country ISO3")
    parser.add_argument('-w', '--warnings', action='store_true', help='Show warnings')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    level='error'
    if args.warnings:
        level='warning'
    utils.config_logger(level=level)
    qc.qc(args.country_iso3)
