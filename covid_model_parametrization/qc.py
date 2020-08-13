import os
import json

import networkx as nx

from covid_model_parametrization.config import Config


def qc(country_iso3, config=None):

    if config is None:
        config = Config()
    main_dir = os.path.join(config.MAIN_OUTPUT_DIR, country_iso3)
    check_graph(config, country_iso3, main_dir)
    check_npis(config, country_iso3, main_dir)


def check_graph(config, country_iso3, main_dir):
    G = read_in_graph(config, country_iso3, main_dir)
    pass


def read_in_graph(config, country_iso3, main_dir):
    filepath = os.path.join(main_dir, config.GRAPH_OUTPUT_DIR,
                            config.GRAPH_OUTPUT_FILE.format(country_iso3))
    with open(filepath, 'r') as read_file:
        data = json.load(read_file)
    return nx.readwrite.json_graph.node_link_graph(data)


def check_npis(config, country_iso3, main_dir):
    pass
