import argparse

from covid_model_parametrization import npis
from covid_model_parametrization.utils import utils

utils.config_logger()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("country_iso3", help="Country ISO3")
    parser.add_argument('-u', '--update-npi-list', action='store_true',
                        help='Update the NPI list with the local ACAPS data file')
    parser.add_argument('-d', '--download-acaps', action='store_true',
                        help='Download the latest ACAPS data')
    parser.add_argument('-f', '--create-final-list', action='store_true',
                        help='Create the final list of NPIs')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    npis.npis(args.country_iso3.upper(), args.update_npi_list, args.create_final_list,
              download_acaps_arg=args.download_acaps)
