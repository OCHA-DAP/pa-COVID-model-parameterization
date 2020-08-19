import os
import json
import logging
import math

import networkx as nx

from covid_model_parametrization.config import Config

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
    # First look at edges
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
    try:
        assert non_diag['weight'].max() == scaling_factor
    except AssertionError:
        logger.error('Mobility matrix not scaled to scaling factor')
    try:
        assert non_diag['weight'].min() > 0
    except AssertionError:
        logger.error('Mobility matrix has negative values')
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
                logger.error(f'{node["name"]} Not between 0 and 1: {fraction}: {node[fraction]}')
        # Check that infected and dead are increasing (warning only)
        for quantity in ['infected_confirmed', 'infected_dead']:
            try:
                assert non_decreasing(node[quantity])
            except AssertionError:
                logger.warning(f'{node["name"]} Non-increasing: {quantity}')
        # Check that the populations add up
        sum_disag = sum(node['group_pop_f']) + sum(node['group_pop_m'])
        try:
            assert  math.isclose(sum_disag, node['population'])
        except AssertionError:
            logger.error(f'{node["name"] }Disaggregated pop inconsistent with total pop: '
                         f'{sum_disag}, {node["population"]}')
    pass


def read_in_graph(config, country_iso3, main_dir):
    filepath = os.path.join(main_dir, config.GRAPH_OUTPUT_DIR,
                            config.GRAPH_OUTPUT_FILE.format(country_iso3))
    with open(filepath, 'r') as read_file:
        data = json.load(read_file)
    return nx.readwrite.json_graph.node_link_graph(data)


def non_decreasing(L):
    return all(x<=y for x, y in zip(L, L[1:]))


def check_npis(config, country_iso3, main_dir):
    pass
