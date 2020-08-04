import os
import itertools
import argparse
import logging
import ast
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

from covid_model_parametrization import utils, exposure
from covid_model_parametrization.config import Config

INPUT_DIR = os.path.join('Inputs')
OUTPUT_DIR = os.path.join('Outputs')
OUTPUT_FILENAME = '{country_iso3}_mobility_matrix.csv'
OUTPUT_FIGNAME = '{country_iso3}_mobility_matrix_hist.png'

CONFIG_FILE = 'parameters.yml'

FILENAME_ROADS = 'hotosm_{country_iso3}_roads_gpkg.zip'
SHAPEFILE_ROADS = 'hotosm_{country_iso3}_roads.gpkg'

FILENAME_CROSSINGS = 'crossings.gpkg'
FILENAME_DISTANCES = 'distances.csv'

# How much to weight each road type
ROAD_MFACTOR = {
    1: 2**8,
    2: 2**7,
    3: 2**6,
    4: 2**5,
    5: 2**4,
    6: 2**3,
    7: 2**2,
    8: 2**1,
}

OSM_ROAD_TYPES = {
    'motorway': 1,
    'trunk': 2,
    'trunk_link': 2,
    'primary': 3,
    'primary_link': 3,
    'secondary': 4,
    'secondary_link': 4,
    'tertiary': 5,
    'tertiary_link': 5,
    'unclassified': 6,
    'residential': 7,
    'service': 8,
    'track': 8,
    'path': 8,
    'footway': 8,
    'living_street': 8,
    'pedestrian': 8,
    'road': 8,
    'construction': 8,
    'no': 8
}

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
pd.options.mode.chained_assignment = None  # default='warn'


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('country_iso3',
                        help='Country ISO3')
    parser.add_argument('-p', '--population-file', help='Path to population geojson', default=None)
    parser.add_argument('-c', '--crossings', action='store_true',
                        help='Read in road border crossings from file')
    parser.add_argument('-d', '--distances', action='store_true',
                        help='Read in distances between region centroids from file')
    return parser.parse_args()


def main(country_iso3, population_file=None, read_in_crossings=True, read_in_distances=True, config=None):
    # Read in the files
    logger.info(f'Running for country {country_iso3}')
    # Get config and parameters
    if config is None:
        config = Config()
    parameters = config.parameters[country_iso3]
    # Make the output directory if it doesn't exist
    output_dir = os.path.join(OUTPUT_DIR, country_iso3, 'mobility')
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    # Load admin regions
    df_adm = load_adm(country_iso3, config, parameters['admin'])
    # Read in population file
    df_pop = gpd.read_file(exposure.get_output_filename(country_iso3, config))
    if read_in_crossings:
        logger.info('Reading in saved roads file')
        df_roads = gpd.read_file(os.path.join(output_dir, FILENAME_CROSSINGS))
        for cname in ['crossings', 'crossing_pairs']:
            df_roads[cname] = df_roads[cname].apply(ast.literal_eval)
    else:
        df_borders = get_borders(df_adm)
        df_roads = load_roads(country_iso3, parameters['mobility'], df_borders)
        df_roads = get_road_crossings(df_roads, df_adm)
        df_roads_out = df_roads.copy()
        for cname in ['crossings', 'crossing_pairs']:
            df_roads_out[cname] = df_roads_out[cname].apply(str)
        df_roads_out.to_file(os.path.join(output_dir, FILENAME_CROSSINGS), driver='GPKG')
    # Get centroid dist
    if read_in_distances:
        logger.info('Reading in saved distances file')
        df_dist = pd.read_csv(os.path.join(output_dir, FILENAME_DISTANCES))
    else:
        df_dist = get_centroid_dist(df_adm)
        df_dist.to_csv(os.path.join(output_dir, FILENAME_DISTANCES))
    # Count the number of crossings
    df_dist = count_crossings(df_dist, df_roads)
    # Create matrix and plot
    df_matrix = create_matrix(df_adm, df_dist, parameters['mobility']['scaling_factor'], df_pop)
    fig = plot_final_hist(df_matrix, country_iso3)
    # Save matrix and plot
    df_matrix.to_csv(os.path.join(output_dir, OUTPUT_FILENAME.format(country_iso3=country_iso3)))
    fig.savefig(os.path.join(output_dir, OUTPUT_FIGNAME.format(country_iso3=country_iso3)), format='png')


def load_adm(country_iso3, config, parameters, level=2):
    logger.info(f'Reading in admin {level} file')
    input_dir = os.path.join(config.DIR_PATH, config.INPUT_DIR, country_iso3)
    input_shp = os.path.join(
        input_dir,
        config.SHAPEFILE_DIR,
        parameters["directory"],
        f'{parameters["directory"]}.shp',
    )
    df_adm = gpd.read_file(input_shp)
    # Somalia has weird column names
    df_adm = df_adm.rename(columns={
        'admin0Pcod': 'ADM0_PCODE',
        'admin1Pcod': 'ADM1_PCODE',
        'admin2Pcod': 'ADM2_PCODE',
    })
    # Modify admin 2 files to contain admin 1 name
    df_adm.loc[:, 'ADM'] = df_adm[f'ADM{level}_PCODE']
    df_adm = df_adm.sort_values(by='ADM').reset_index(drop=True)
    return df_adm


def get_borders(df_adm):
    df_borders = df_adm.copy()
    df_borders['geometry'] = df_borders['geometry'].boundary
    return df_borders


def load_roads(country_iso3, parameters, df_borders):
    logger.info('Downloading roads file')
    save_path = os.path.join(INPUT_DIR, country_iso3, 'mobility',
                             FILENAME_ROADS.format(country_iso3=country_iso3.lower()))
    utils.download_ftp(parameters['roads']['url'], save_path)
    logger.info('Reading in roads file')
    df_roads = gpd.read_file(
        f'zip://{save_path}!{SHAPEFILE_ROADS.format(country_iso3=country_iso3.lower())}',
        mask=df_borders)
    df_roads = df_roads.loc[~df_roads['geometry'].isna()]
    logger.info(f'Read in {len(df_roads)} roads')
    return df_roads


def get_road_crossings(df_roads, df_adm):
    logger.info(f'Getting road intersections with borders for {len(df_roads)} roads')
    # For each road, get provinces that it intersects with
    # !!! This takes awhile to run
    df_roads['crossings'] = df_roads['geometry'].apply(lambda x:
                                                       [y['ADM']
                                                        for _, y in df_adm.iterrows()
                                                        if x.intersects(y['geometry'])
                                                        ])
    # Drop rows with no crossings
    df_roads = df_roads.loc[df_roads['crossings'].apply(len) > 1]
    logger.info(f'{len(df_roads)} roads with crossings found')
    # Turn crossings into list of pairs
    df_roads['crossing_pairs'] = df_roads['crossings'].apply(lambda x:
                                                             list(itertools.combinations(sorted(x), 2)))

    return df_roads


def get_centroid_dist(df_adm):
    # Create a df with every possible province pair, and find the
    # distance between the centroids
    df_centroids = df_adm.copy()
    df_centroids['geometry'] = df_centroids['geometry'].apply(lambda x:
                                                              x.centroid)

    df_dist = pd.DataFrame(list(itertools.combinations(df_adm['ADM'], 2)),
                           columns=['ADM_A', 'ADM_B'])
    logger.info(f'Getting centroid distances for {len(df_dist)} region pairs')
    df_dist['dist'] = df_dist.apply(lambda x: (
        df_centroids.loc[df_centroids['ADM'] == x['ADM_A'], 'geometry'].values[0]
            .distance(df_centroids.loc[df_centroids['ADM'] == x['ADM_B'], 'geometry'].values[0])
    ), axis=1)

    # Add class columns to df_dist
    df_dist = df_dist.join(pd.DataFrame({f'class_{i}': 0 for i in ROAD_MFACTOR.keys()}, index=df_dist.index))

    return df_dist


def count_crossings(df_dist, df_roads):
    logger.info('Counting road crossings')
    # For each road, add the crossings to the distance matrix
    for _, row in df_roads.iterrows():
        for crossing_pair in row['crossing_pairs']:
            df_dist.loc[(df_dist['ADM_A'] == crossing_pair[0]) &
                        (df_dist['ADM_B'] == crossing_pair[1]),
                        f'class_{OSM_ROAD_TYPES[row["highway"]]}'
            ] += 1
    # Drop any rows that have no road crossings
    df_dist = df_dist[(df_dist['class_1'] != 0) | (df_dist['class_2'] != 0) | (df_dist['class_3'] != 0)]

    # Calculate weight -- roads weighted by mfactor, divided by distance
    df_dist.loc[:, 'weight'] = df_dist.apply(lambda x:
                                             sum([ROAD_MFACTOR[i] * x[f'class_{i}'] for i in [1, 2, 3]]) / x['dist'],
                                             axis=1)

    return df_dist


def create_matrix(df_adm2, df_dist, parameters, df_pop, scale_by_pop=False):
    if scale_by_pop:
        # sum to get total pop
        df_pop["total_pop"] = df_pop[[c for c in df_pop.columns if "f_" in c or "m_" in c]].sum(axis=1)
        # Change any 0 values to 1 for DRC
        df_pop["total_pop"] = np.where(df_pop["total_pop"] == 0, 1, df_pop["total_pop"])
    logger.info('Creating matrix')
    df_matrix = pd.DataFrame(columns=df_adm2['ADM'], index=df_adm2['ADM'])
    for _, row in df_dist.iterrows():
        df_matrix.loc[row['ADM_A'], row['ADM_B']] = row['weight']
        df_matrix.loc[row['ADM_B'], row['ADM_A']] = row['weight']
        if scale_by_pop:
            df_matrix.loc[row['ADM_A'], row['ADM_B']] /= \
                df_pop.loc[df_pop['ADM2_PCODE'] == row['ADM_A'], 'total_pop'].iloc[0]
            df_matrix.loc[row['ADM_B'], row['ADM_A']] /= \
                df_pop.loc[df_pop['ADM2_PCODE'] == row['ADM_B'], 'total_pop'].iloc[0]
    df_matrix = df_matrix.fillna(0)

    # Normalize
    df_matrix *= parameters['household_size'] * parameters['motor_vehicle_fraction'] / df_matrix.values.max()
    # Set diagonals to 1
    np.fill_diagonal(df_matrix.values, 1.0)

    return df_matrix


def plot_final_hist(df_matrix, country_iso3):
    # Get all non 0 and 1 values
    matrix = df_matrix.values.flatten()
    matrix = matrix[np.where((matrix > 0) & (matrix < 1))[0]]
    # Plot a hist
    fig, ax = plt.subplots()
    logbins = np.logspace(np.floor(np.log10(matrix.min())), 0, 100)
    ax.hist(matrix, bins=logbins)
    ax.set_xscale('log')
    ax.set_ylabel('number')
    ax.set_xlabel('P')
    ax.set_title(f'{country_iso3.upper()} mobility values distribution')
    return fig


if __name__ == '__main__':
    args = parse_args()
    main(country_iso3=args.country_iso3.upper(), population_file=args.population_file,
         read_in_crossings=args.crossings, read_in_distances=args.distances)
