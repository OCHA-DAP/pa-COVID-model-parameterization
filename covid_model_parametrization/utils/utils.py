import zipfile
from urllib.request import urlretrieve
import logging
import os
from datetime import timedelta

import requests
import yaml


logger = logging.getLogger(__name__)


def config_logger(level='INFO'):
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=vars(logging)[level.upper()],
        datefmt="%Y-%m-%d %H:%M:%S",
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
