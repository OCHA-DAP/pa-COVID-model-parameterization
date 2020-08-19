import os
import json
import logging
import math
from datetime import datetime, timedelta

import networkx as nx
import pandas as pd
import numpy as np

from covid_model_parametrization.config import Config
from covid_model_parametrization import npis

logger = logging.getLogger(__name__)


def qc(country_iso3, config=None):
    if config is None:
        config = Config()
    parameters = config.parameters(country_iso3)
    main_dir = os.path.join(config.MAIN_OUTPUT_DIR, country_iso3)
    check_graph(config, parameters, country_iso3, main_dir)
    check_npis(config, country_iso3, main_dir)


def check_graph(config, parameters, country_iso3, main_dir):
    G = read_in_graph(config, country_iso3, main_dir)
    check_graph_edges(G, parameters)
    check_graph_nodes(G)
    # TODO: check COVID dates


def read_in_graph(config, country_iso3, main_dir):
    filepath = os.path.join(main_dir, config.GRAPH_OUTPUT_DIR,
                            config.GRAPH_OUTPUT_FILE.format(country_iso3))
    with open(filepath, 'r') as read_file:
        data = json.load(read_file)
    return nx.readwrite.json_graph.node_link_graph(data)


def check_graph_edges(G, parameters):
    edges = nx.convert_matrix.to_pandas_edgelist(G)
    # Check that diagonal is 1
    try:
        assert all(edges.loc[edges['source'] == edges['target'], 'weight'] == 1)
    except AssertionError:
        logger.error('Mobility matrix diagonal values are not all 1')
    # Check that the rest of the values go from 0 to the scaling factor
    non_diag = edges.loc[edges['source'] != edges['target']]
    scaling_factor = parameters['mobility']['scaling_factor']['household_size'] * \
                     parameters['mobility']['scaling_factor']['motor_vehicle_fraction']
    non_diag_max = non_diag['weight'].max()
    try:
        assert math.isclose(non_diag_max, scaling_factor)
    except AssertionError:
        logger.error(f'Mobility matrix max ({non_diag_max}) not scaled to scaling factor ({scaling_factor})')
    try:
        assert non_diag['weight'].min() > 0
    except AssertionError:
        logger.error('Mobility matrix has negative values')


def check_graph_nodes(G):
    # Loop through nodes
    for node in list(G.nodes(data=True)):
        # Need to take second part of tuple
        node = node[1]
        # Check that the fraction are all between 0 and 1
        fractions = [ # TODO: maybe move this quantity to the config file
            'frac_urban',
            'food_insecurity',
            'fossil_fuels',
            'handwashing_facilities',
            'raised_blood_pressure',
            'diabetes',
            'smoking',
            'vulnerable_frac',
            'high_beta_frac'
        ]
        for fraction in fractions:
            try:
                assert node[fraction] <= 1
                assert node[fraction] >= 0
            except AssertionError:
                logger.error(f'{node["name"]}: Not between 0 and 1: {fraction}: {node[fraction]}')
        # Check that infected and dead are increasing (warning only)
        for quantity in ['infected_confirmed', 'infected_dead']:
            try:
                assert non_decreasing(node[quantity])
            except AssertionError:
                logger.warning(f'{node["name"]}: Non-increasing: {quantity}')
            except KeyError:
                logger.error(f'{node["name"]}: Missing quantity: {quantity}')
        # Check that the populations add up
        sum_disag = sum(node['group_pop_f']) + sum(node['group_pop_m'])
        try:
            assert  math.isclose(sum_disag, node['population'])
        except AssertionError:
            logger.error(f'{node["name"]}: Disaggregated pop inconsistent with total pop: '
                         f'{sum_disag}, {node["population"]}')


def non_decreasing(L):
    return all(x<=y for x, y in zip(L, L[1:]))


def check_npis(config, country_iso3, main_dir):
    df_npi = pd.read_csv(os.path.join(main_dir, config.NPI_DIR,
                                      config.NPI_FINAL_OUTPUT_FILENAME.format(country_iso3)))
    check_npi_dates(df_npi)
    check_npi_values(df_npi)


def check_npi_dates(df_npi):
    df_npi['date'] = pd.to_datetime(df_npi['date'])
    date_min = df_npi['date'].min()
    date_max = df_npi['date'].max()
    date_set = set(date_min + timedelta(days=x) for x in range((date_max - date_min).days))
    for admin in df_npi['admin2'].unique():
        dates = df_npi.loc[df_npi['admin2'] == admin, 'date']
        missing = date_set - set(dates)
        try:
            assert missing
        except AssertionError:
            logger.error(f'Admin pcode {admin} missing NPI dates: {missing}')


def check_npi_values(df_npi):
    # Check that contact matrix values are reasonable
    contact_matrix_possible_values = {contact_matrix_name: [1.0, npis.SCHOOL_REDUCTION_VALUES[contact_matrix_name]]
                                      for contact_matrix_name in ['home', 'school', 'work', 'other_locations']}
    for contact_matrix_name, possible_values in contact_matrix_possible_values.items():
        try:
            assert all(i in possible_values for i in df_npi[contact_matrix_name])
        except AssertionError:
            logger.error(f'Contact matrix scaling for {contact_matrix_name} has value(s) not in {possible_values}')
    # Check that mobility has reasonable values
    mobility_min = 1 - npis.MOBILITY_REDUCTION_AMOUNT
    try:
        assert all(i <= 1.0 and i >= mobility_min for i in  df_npi['mobility_reduction'])
    except AssertionError:
        logger.error(f'Mobility scaling has value not between {mobility_min} and 1')
    # Check R0 reduction has reasonable values
    r0_min = 1 - np.sum(npis.R0_REDUCTION_AMOUNTS)
    try:
        assert all(i <= 1.0 and i >= r0_min for i in  df_npi['r0_reduction'])
    except AssertionError:
        logger.error(f'R0 scaling has value not between {r0_min} and 1')
