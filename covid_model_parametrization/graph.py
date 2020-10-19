import os
import logging
import json
from pathlib import Path

import pandas as pd
import geopandas as gpd
import networkx as nx
import numpy as np
import fiona
import re
import pickle

from covid_model_parametrization.config import Config
from covid_model_parametrization.utils.who import get_WHO_data

logger = logging.getLogger(__name__)

CONTACT_MATRIX_SIZE = 16


def graph(country_iso3, config=None):

    if config is None:
        config = Config()
    parameters = config.parameters(country_iso3)

    logger.info(f"Creating graph for {country_iso3}")
    main_dir = os.path.join(config.MAIN_OUTPUT_DIR, country_iso3)

    # Initialize graph with mobility edges
    mobility_csv = os.path.join(main_dir,
                                config.MOBILITY_DIR,
                                config.MOBILITY_FILENAME.format(country_iso3=country_iso3))
    G = initialize_with_mobility(mobility_csv)
    G.graph["country"] = country_iso3

    # Add exposure
    G = add_exposure(G, main_dir, country_iso3, parameters["admin"], config)

    # Add COVID cases
    G = add_covid(G, main_dir, country_iso3, config)

    # Add WHO data
    G = add_WHO_data(G, country_iso3, config)

    # Add vulnerability
    G = add_vulnerability(G, main_dir, country_iso3, config)

    # Add contact matrix
    add_contact_matrix(G, parameters["contact_matrix"], config)

    input_shp = os.path.join(
        config.INPUT_DIR,
        country_iso3,
        config.SHAPEFILE_DIR,
        parameters["admin"]["directory"],
        f'{parameters["admin"]["directory"]}.shp',
    )
    # Add general attributes to ensure compatibility with Bucky requirements
    G=add_general_attributes(G, country_iso3,input_shp)

    # Write out
    data = nx.readwrite.json_graph.node_link_data(G)
    outdir = os.path.join(main_dir, config.GRAPH_OUTPUT_DIR)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    outfile_json = os.path.join(
        main_dir, config.GRAPH_OUTPUT_DIR, config.GRAPH_OUTPUT_FILE_JSON.format(country_iso3)
    )
    outfile_pickle = os.path.join(
        main_dir, config.GRAPH_OUTPUT_DIR, config.GRAPH_OUTPUT_FILE_PICKLE.format(country_iso3)
    )

    with open(outfile_json, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Wrote out to {outfile_json}")

    with open(outfile_pickle, 'wb') as f:
        pickle.dump(G, f)

def initialize_with_mobility(filename):
    logger.info(f"Reading in mobility from {filename}")
    mobility = pd.read_csv(filename)
    mobility.set_index("ADM", inplace=True)
    G = nx.from_pandas_adjacency(mobility, nx.DiGraph)
    return G

def add_general_attributes(G, country_iso3, shape_path):
    # update graph attributes to be compatible with Bucky model
    start_date = G.graph['dates'][-1]
    G.graph['start_date'] = start_date
    G.graph['adm1_key'] = 'adm1_int'
    G.graph['adm2_key'] = 'adm2_int'
    G.graph['adm0_name'] = country_iso3
    G.graph['adm2_name'] = 'adm2_name'

    shape = fiona.open(shape_path)
    adm1_to_str = {}
    for obj in shape:
        #remove the letters from the pcode
        pcode=re.findall(r'\d+', str(obj['properties']['ADM1_PCODE']))[0]
        name = obj['properties'].get('ADM1_EN', 'ADM1_FR').lower()
        adm1_to_str[pcode] = name
    G.graph['adm1_to_str'] = adm1_to_str

    num_dates = len(G.graph['dates'])
    # update node attributes
    for n in G.nodes.values():
        if 'case_hist' not in n:
            n['case_hist'] = [0] * num_dates
        if 'death_hist' not in n:
            n['death_hist'] = [0] * num_dates
        n['N_age_init'] = [x + y for x, y in zip(n['group_pop_f'], n['group_pop_m'])]
        n['adm1_int'] = re.findall(r'\d+', n['ADM1_PCODE'])[0]
        n['adm2_int'] = re.findall(r'\d+', n['ADM2_PCODE'])[0]
        del n['group_pop_f']
        del n['group_pop_m']

    # already stored as "ADM2_PCODE"
    G = nx.convert_node_labels_to_integers(G)
    return G

def add_exposure(G, main_dir, country_iso3, parameters, config):
    # Read in exposure file
    filename = os.path.join(
        main_dir, config.SADD_OUTPUT_DIR, config.EXPOSURE_GEOJSON.format(country_iso3)
    )
    logger.info(f"Reading in exposure from {filename}")
    exposure = gpd.read_file(filename)
    # Turn disag pop columns into lists
    for gender in ["f", "m"]:
        # to match contact matrix, combine gender_0 with gender_1 and gender_75 with gender_80
        exposure[f"{gender}_0"] = exposure[f"{gender}_0"] + exposure[f"{gender}_1"]
        exposure[f"{gender}_75"] = exposure[f"{gender}_75"] + exposure[f"{gender}_80"]
        exposure.drop([f"{gender}_1", f"{gender}_80"], axis=1, inplace=True)

        columns = [c for c in exposure.columns if f"{gender}_" in c]
        exposure[f"group_pop_{gender}"] = exposure[columns].values.tolist()
        # Get the age groups
        age_groups = [s.split("_")[-1] for s in columns]
    # Add pop -- recalculate for now until exposure script updated
    exposure["population"] = exposure[
        [c for c in exposure.columns if "f_" in c or "m_" in c]
    ].sum(axis=1)
    # Project to pseudo mercator to get meter units: https://epsg.io/3857
    exposure["population_density"] = np.round(exposure["population"] / exposure[
        "geometry"
    ].to_crs(config.PSEUDO_MERCATOR_CRS).apply(lambda x: x.area / 10 ** 6), 8)
    exposure['adm1_int'] = exposure['ADM1_PCODE'].str.extract('(\d+)')
    exposure['adm2_int'] = exposure['ADM2_PCODE'].str.extract('(\d+)')
    # Only keep necessary columns
    columns = [
        "ADM2_{}".format(parameters["language"]),
        "ADM1_PCODE",
        "ADM2_PCODE",
        "group_pop_f",
        "group_pop_m",
        "population",
        "population_density",
        "adm1_int",
        "adm2_int",
    ]
    exposure = exposure[columns]
    # Rename some
    rename_dict = {
        "ADM2_{}".format(parameters["language"]): "adm2_name",
    }
    exposure = exposure.rename(columns=rename_dict)

    # Add the exposure info to graph
    G.graph["age_groups"] = age_groups
    for row in exposure.to_dict(orient="records"):
        G.add_node(row["ADM2_PCODE"], **row)
    return G


def add_covid(G, main_dir, country_iso3, config):
    # Read in COVID file
    filename = os.path.join(
        main_dir, config.COVID_OUTPUT_DIR, config.COVID_OUTPUT_CSV.format(country_iso3)
    )
    logger.info(f"Reading in COVID cases from {filename}")
    covid = pd.read_csv(filename)
    date_range = pd.date_range(covid["#date"].min(), covid["#date"].max())
    #mapping of covid column names to the key values bucky requires as input for historical numbers
    bucky_dict={"confirmed":"case", "dead":"death"}
    for cname in ["confirmed", "dead"]:
        # Do some pivoting
        covid_out = covid.pivot(
            index="#date",
            values=f"#affected+infected+{cname}+total",
            columns="#adm2+pcode",
        )
        # Add any missing dates
        covid_out.index = pd.DatetimeIndex(covid_out.index)
        covid_out = covid_out.reindex(date_range)
        # Interpolate the missing values
        covid_out = covid_out.interpolate(
            method="linear", axis="rows", limit_direction="forward"
        ).fillna(0)
        # Add to the graph
        G.graph["dates"] = list(covid_out.index.astype(str))
        for admin2 in covid_out.columns:
            G.add_node(
                admin2, **{f"{bucky_dict[cname]}_hist": covid_out[admin2].values.tolist()}
            )
    return G


def add_WHO_data(G, country_iso3, config):
    df_WHO = get_WHO_data(config, country_iso3, hxlize=True)
    # convert ot datetime
    df_WHO['#date'] = pd.to_datetime(df_WHO['#date']).dt.date
    # keep only columns that we need
    df_WHO = df_WHO[['#date',
                     '#affected+infected+confirmed+total',
                     '#affected+infected+dead+total']]
    # Index by date and fill missing vals
    date_range = pd.date_range(df_WHO["#date"].min(), df_WHO["#date"].max())
    df_WHO.index = df_WHO['#date']
    df_WHO = df_WHO.drop('#date', axis=1)
    df_WHO.reindex(date_range)
    df_WHO = df_WHO.interpolate(
        method="linear", axis="rows", limit_direction="forward"
    ).fillna(0)
    df_WHO['#date'] = df_WHO.index.astype(str)
    # Add to the graph
    G.graph['data_WHO'] = df_WHO.to_dict(orient='list')
    return G


def add_vulnerability(G, main_dir, country_iso3, config):
    # Read in vulnerability file
    filename = os.path.join(
        main_dir,
        config.VULNERABILITY_OUTPUT_DIR,
        config.VULNERABILITY_FILENAME.format(country_iso3=country_iso3),
    )
    logger.info(f"Reading in vulnerability from {filename}")
    vulnerability = gpd.read_file(filename)
    # Only keep necessary columns
    columns = [
        "ADM2_PCODE",
        "frac_urban",
        "Phase 3+",
        "fossil_fuels",
        "handwashing_facilities",
        "raised_blood_pressure",
        "diabetes",
        "smoking",
    ]
    vulnerability = vulnerability[columns]
    # Rename some
    rename_dict = {
        "Phase 3+": "food_insecurity",
    }
    vulnerability = vulnerability.rename(columns=rename_dict)
    # convert the vulnerability factors to numeric
    vulnerability["food_insecurity"] = pd.to_numeric(vulnerability["food_insecurity"])
    vulnerability["fossil_fuels"] = pd.to_numeric(vulnerability["fossil_fuels"])
    # Take the maximum between food security and fossil fuels as vulnerability
    vulnerability["vulnerable_frac"] = vulnerability[
        ["food_insecurity", "fossil_fuels"]
    ].max(axis=1)
    # Take the handwashing facilties factor as proxy for high_beta_fraction
    vulnerability["high_beta_frac"] = vulnerability["handwashing_facilities"]
    # Add the exposure info to graph
    for row in vulnerability.to_dict(orient="records"):
        G.add_node(row["ADM2_PCODE"], **row)
    return G


def add_contact_matrix(G, parameters, config):
    G.graph["contact_mats"] = {}
    logger.info(f'Reading in contact matrices for {parameters["country"]}')
    for contact_matrix_type in config.CONTACT_MATRIX_TYPES:
        filename = os.path.join(
            config.CONTACT_MATRIX_DIR,
            config.CONTACT_MATRIX_FILENAME.format(
                contact_matrix_type=contact_matrix_type,
                file_number=parameters["file_number"],
            ),
        )
        if parameters["file_number"] == 1:
            column_names = None
            header = 0
        elif parameters["file_number"] == 2:
            column_names = [f"X{i}" for i in range(CONTACT_MATRIX_SIZE)]
            header = None
        contact_matrix = pd.read_excel(
            filename,
            sheet_name=parameters["country"],
            header=header,
            names=column_names,
        )
        # Add as metadata
        G.graph["contact_mats"][contact_matrix_type] = contact_matrix.values.tolist()
    # Add elderly shielding contact matrix
    # TODO: populate these values
    elderly_shielding_matrix = np.zeros((CONTACT_MATRIX_SIZE, CONTACT_MATRIX_SIZE))
    G.graph["contact_mats"]["elderly_shielding"] = elderly_shielding_matrix.tolist()
    return G
