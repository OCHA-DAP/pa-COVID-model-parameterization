import zipfile
from urllib.request import urlretrieve
import logging
import os
from datetime import timedelta

import requests
import yaml
import coloredlogs
import geopandas as gpd


logger = logging.getLogger(__name__)


def config_logger(level='INFO'):
    # Colours selected from here:
    # http://humanfriendly.readthedocs.io/en/latest/_images/ansi-demo.png
    coloredlogs.install(
        level=level,
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        field_styles={
            'name': {'color': 8 },
            'asctime': {'color': 248},
            'levelname': {'color': 8, 'bold': True},
        },
    )


def download_url(url, save_path, chunk_size=128):
    # Remove file if already exists
    try:
        os.remove(save_path)
    except OSError:
        pass
    # Download
    r = requests.get(url, stream=True)
    with open(save_path, "wb") as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            fd.write(chunk)
    logger.info(f'Downloaded "{url}" to "{save_path}"')


def download_ftp(url, save_path):
    logger.info(f'Downloading "{url}" to "{save_path}"')
    urlretrieve(url, filename=save_path)


def unzip(zip_file_path, save_path):
    logger.info(f"Unzipping {zip_file_path}")
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(save_path)


def parse_yaml(filename):
    with open(filename, "r") as stream:
        config = yaml.safe_load(stream)
    return config


def write_to_geojson(filename, geodataframe):
    try:
        os.remove(filename)
    except OSError:
        pass
    geodataframe.to_file(filename, driver="GeoJSON")


def non_decreasing(L):
    return all(x <= y for x, y in zip(L, L[1:]))


def strictly_increasing(L):
    return all(x<y for x, y in zip(L, L[1:]))


def create_date_set(date_min, date_max):
    return set(date_min + timedelta(days=x) for x in range((date_max - date_min).days))


def read_in_admin_boundaries(config, parameters, country_iso3):
    input_dir = os.path.join(config.DIR_PATH, config.INPUT_DIR, country_iso3)
    input_shp = os.path.join(
        input_dir,
        config.SHAPEFILE_DIR,
        parameters["admin"]["directory"],
        f'{parameters["admin"]["directory"]}.shp',
    )
    # Read in and rename columns for Somalia
    return gpd.read_file(input_shp).rename(columns={
        'admin0Pcod': 'ADM0_PCODE',
        'admin1Pcod': 'ADM1_PCODE',
        'admin2Pcod': 'ADM2_PCODE',
    })

def remove_chars(seq):
    seq_type = type(seq)
    if seq_type != str:
        return seq
    else:
        return seq_type().join(filter(seq_type.isdigit, seq))
