import argparse

from covid_model_parametrization.utils import utils
from covid_model_parametrization import mobility

utils.config_logger()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('country_iso3',
                        help='Country ISO3')
    parser.add_argument('-c', '--crossings', action='store_true',
                        help='Read in road border crossings from file')
    parser.add_argument('-d', '--distances', action='store_true',
                        help='Read in distances between region centroids from file')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    mobility.mobility(country_iso3=args.country_iso3.upper(),
                      read_in_crossings=args.crossings,
                      read_in_distances=args.distances)
