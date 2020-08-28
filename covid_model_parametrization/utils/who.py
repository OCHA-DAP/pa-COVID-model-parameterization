import os
from pathlib import Path
import logging

import pandas as pd
from hdx.location.country import Country

from covid_model_parametrization.utils.hdx_api import query_api

logger = logging.getLogger(__name__)

HXL_DICT = {
    'Date_reported': '#date',
    ' Cumulative_cases': '#affected+infected+confirmed+total',
    ' Cumulative_deaths': '#affected+infected+dead+total'
}


def get_WHO_data(config, country_iso3, hxlize=False):
    # Download the file and move it to a local directory
    logger.info('Downloading WHO data from HDX')
    WHO_dir = os.path.join(config.INPUT_DIR, config.WHO_DIR)
    Path(WHO_dir).mkdir(parents=True, exist_ok=True)
    download_filename = list(query_api(config.WHO_HDX_ADDRESS, WHO_dir, resource_format='CSV').values())[0]
    final_filepath = os.path.join(WHO_dir, config.WHO_FILENAME)
    os.rename(os.path.join(WHO_dir, download_filename), final_filepath)
    # Get the data for the country based on ISO3
    logger.info(f'Returning WHO data for {country_iso3}')
    df_WHO = pd.read_csv(final_filepath)
    df_WHO = df_WHO.loc[df_WHO[' Country_code'] == Country.get_iso2_from_iso3(country_iso3)]
    if hxlize:
       df_WHO = df_WHO.rename(columns=HXL_DICT)
    return df_WHO
