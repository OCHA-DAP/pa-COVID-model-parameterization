import argparse

from covid_model_parametrization import utils, npis

utils.config_logger()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--update-npi-list', action='store_true',
                        help='Download the latest ACAPS data and update NPI list')
    parser.add_argument('-c', '--create-final-list', action='store_true',
                        help='Create the final list of NPIs')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    npis.npis(args.update_npi_list, args.create_final_list)
