import os
import logging
from pathlib import Path
import ast
from datetime import datetime
import sys

import pandas as pd
import geopandas as gpd
import xarray as xr
import numpy as np

from covid_model_parametrization.utils import utils
from covid_model_parametrization.config import Config
from covid_model_parametrization.utils.hdx_api import query_api


# Reduction parameters
MEASURES_DICT = {
    'school closure': 'school',
    'shielding elderly': 'elderly_shielding',
    'closing borders': 'mobility_reduction',
    'restricting inter-regional movement': 'mobility_reduction',
    'social distancing':'r0_reduction',
    'face mask wearing': 'r0_reduction',
    'hand washing stations': 'r0_reduction',
    'reduction of size of gatherings': 'r0_reduction',
    'closing businesses': 'r0_reduction',
    'partial lockdown': 'r0_reduction',
    'awareness campaign': 'r0_reduction'
}
R0_REDUCTION_AMOUNTS = [0.0, 0.4, 0.2, 0.1, 0.05]
MOBILITY_REDUCTION_AMOUNT = 0.6
SCHOOL_REDUCTION_VALUES = {
       'home': 1.05,
       'other_locations': 0.85,
       'school': 0.05,
       'work': 1.0
    }
ELDERLY_SHIELDING_MULTIPLIER = 1.0

logger = logging.getLogger()
pd.options.mode.chained_assignment = None  # default='warn'


def npis(country_iso3, update_npi_list_arg, create_final_list_arg, download_acaps_arg=False, config=None):

    # Get config file
    if config is None:
        config = Config()
    parameters = config.parameters(country_iso3)

    #  Get NPIs for each country
    if update_npi_list_arg:
        update_npi_list(config, parameters, country_iso3, download_acaps_arg)
    if create_final_list_arg:
        create_final_list(config, parameters, country_iso3)


def update_npi_list(config, parameters, country_iso3, download_acaps_arg):
    if download_acaps_arg:
        logger.info('Getting latest ACAPS data')
        download_acaps(config)
    df_acaps = get_df_acaps(config, country_iso3)
    add_new_acaps_data(config, country_iso3, df_acaps[df_acaps['ISO3'] == country_iso3], parameters)


def download_acaps(config):
    # Get the ACAPS data from HDX
    acaps_dir = os.path.join(config.INPUT_DIR, config.ACAPS_DIR)
    Path(acaps_dir).mkdir(parents=True, exist_ok=True)
    filename = list(query_api(config.ACAPS_HDX_ADDRESS, acaps_dir).values())[0]
    os.rename(os.path.join(acaps_dir, filename), os.path.join(acaps_dir, config.ACAPS_FILENAME))


def get_df_acaps(config, country_iso3):
    # Open the file
    df_acaps =  pd.read_excel(os.path.join(config.INPUT_DIR,
                                           config.ACAPS_DIR,
                                           config.ACAPS_FILENAME),
                              sheet_name='Dataset')
    # Take only the country of concern
    df_acaps = df_acaps[df_acaps['_ISO'] == country_iso3]
    # rename columns
    column_name_dict = {
        'ID': 'ID',
        '_ISO': 'ISO3',
        'LOG_TYPE': 'add_or_remove',
        'CATEGORY': 'acaps_category',
        '_MEASURE': 'acaps_measure',
        'COMMENTS': 'acaps_comments',
        'DATE_IMPLEMENTED': 'start_date',
        'SOURCE': 'source',
    }
    df_acaps = df_acaps.rename(columns=column_name_dict)
    # Combine columns
    columns_to_combine = {
        'acaps_comments': ['ADMIN_LEVEL_NAME', 'PCODE', 'TARGETED_POP_GROUP', 'NON_COMPLIANCE'],
        'source': ['SOURCE_TYPE', 'LINK', 'Alternative source']
    }
    for main_column, cnames in columns_to_combine.items():
        for cname in cnames:
            prefix = cname.lower().replace('_', ' ')
            df_acaps[cname] = df_acaps[cname].apply(lambda x: f'{prefix}: {x}' if isinstance(x, str) else x)
        df_acaps[main_column] = df_acaps[[main_column] + cnames].fillna('').agg(' | '.join, axis=1)
    # Simplify add_or_remove
    df_acaps['add_or_remove'] = df_acaps['add_or_remove'].replace({'Introduction / extension of measures': 'add',
                                'Phase-out measure': 'remove'})
    # Get our measures equivalent, and drop any that we don't use
    df_acaps['bucky_measure'] = df_acaps['acaps_measure'].str.lower().map(get_measures_equivalence_dictionary(config))
    df_acaps = df_acaps[df_acaps['bucky_measure'].notnull()]
    df_acaps['bucky_category'] = df_acaps['bucky_measure'].map(get_measures_category_dictionary(config))
    # Keep only some columns, moving start date to end
    # cnames_to_keep = list(column_name_dict.values()) + ['bucky_measure', 'bucky_category']
    cnames_to_keep = list(column_name_dict.values()) + ['bucky_measure']
    cnames_to_keep.append(cnames_to_keep.pop(cnames_to_keep.index('start_date')))
    df_acaps = df_acaps[cnames_to_keep]
    return df_acaps


def get_measures_equivalence_dictionary(config):
    df = pd.read_csv(os.path.join(config.INPUT_DIR, config.ACAPS_DIR, config.MEASURE_EQUIVALENCE_FILENAME),
                     usecols=['ACAPS NPI', 'Our equivalent'])
    return df.set_index('ACAPS NPI').to_dict()['Our equivalent']


def get_measures_category_dictionary(config):
    df = pd.read_csv(os.path.join(config.INPUT_DIR, config.ACAPS_DIR, config.MEASURE_EQUIVALENCE_FILENAME),
                     usecols=['Our NPIs', 'Category']).dropna()
    return df.set_index('Our NPIs').to_dict()['Category']


def add_new_acaps_data(config, country_iso3, df_country, parameters):
    logger.info(f'Getting info for {country_iso3}')
    # Check if JSON file already exists, if so read it in
    output_dir = os.path.join(config.INPUT_DIR, country_iso3, config.NPI_DIR)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    new_cols = [
                'end_date',
                'affected_pcodes',
                'compliance_level',
                'can_be_modelled',
                'final_input',
                'npis_linked',
                'ocha_comments'
    ]
    old_cols = [
        'ID',
        'ISO3',
        'add_or_remove',
        'acaps_category',
        'acaps_measure',
        'acaps_comments',
        'source',
        'bucky_measure',
        'start_date'
    ]
    if 'NPIs' in parameters:
        df_manual = get_triaged_csv(config, parameters, country_iso3)
        # Fix the columns that are lists
        for col in ['affected_pcodes']:
            df_manual.loc[:, col] = df_manual[col].apply(lambda x: literal_eval(x))
        for col in ['start_date', 'end_date']:
            df_manual.loc[:, col] = df_manual[col].apply(pd.to_datetime)
        # Join the pcode info
        for df in [df_country, df_manual]:
            df.loc[:, 'ID'] = df.astype(str)
        df_country = df_country[old_cols].merge(df_manual[['ID', 'bucky_measure', 'start_date'] + new_cols],
                                                how='outer', on='ID')
        # Prioritize start date and bukcy measure from df_manual
        for q in ['bucky_measure', 'start_date']:
            df_country = df_country.rename(columns={f'{q}_y': q})
            df_country.loc[:, q] = df_country[q].fillna(df_country[f'{q}_x'])
            df_country = df_country.drop(f'{q}_x', axis=1)
    else:
        # If it doesn't exist, add empty columns
        logger.info(f'No input URL in parameters, creating new file')
        for col in new_cols:
            df_country.loc[:, col] = None
    # Write out
    for col in ['start_date', 'end_date']:
        df_country[col] = pd.to_datetime(df_country[col])
        df_country.loc[:, col] = df_country[col].dt.date
    filename = os.path.join(output_dir, config.NPI_INTERMEDIATE_OUTPUT_FILENAME.format(country_iso3))
    logger.info(f'Writing to {filename}')
    df_country.to_excel(filename, index=False)
    return df_country


def get_triaged_csv(config, parameters, country_iso3):
    logger.info(f'Getting triaged csv for {country_iso3}')
    filename = os.path.join(config.INPUT_DIR, country_iso3, config.NPI_DIR,
                            config.NPI_TRIAGED_INTERMEDIATE_OUTPUT_FILENAME.format(country_iso3))
    utils.download_url(parameters['NPIs']['url'], filename)
    df_country = pd.read_csv(filename, header=0, skiprows=[1])
    df_country['affected_pcodes'] = df_country['affected_pcodes'].apply(lambda x: literal_eval(x))
    return df_country


def literal_eval(val):
    if type(val) == list:
        return val
    try:
        return ast.literal_eval(val)
    except ValueError as e:
        return None


def get_admin_regions(boundaries):
    # Get list of admin 0, 1 and 2 regions
    return {
        'admin0': boundaries['ADM0_PCODE'].unique().tolist(),
        'admin1': boundaries['ADM1_PCODE'].unique().tolist(),
        'admin2': boundaries['ADM2_PCODE'].unique().tolist()
    }


def create_final_list(config, parameters, country_iso3):
    logger.info(f'Creating final NPI list for {country_iso3}')
    boundaries = utils.read_in_admin_boundaries(config, parameters, country_iso3)
    df_country = get_triaged_csv(config, parameters, country_iso3)
    format_final_output(config, country_iso3, df_country, boundaries)


def format_final_output(config, country_iso3, df, boundaries):
    logger.info(f'Formatting final output for {country_iso3}')
    # Only take rows with final_input is Yes
    df = df[(df['final_input'] == 'Yes')]
    # Fill empty end dates with today's date
    df.loc[:, 'end_date'] = df['end_date'].fillna(datetime.today()).apply(pd.to_datetime)
    # Add Bucky category
    df.loc[:, 'bucky_category'] = df['bucky_measure'].map(get_measures_category_dictionary(config))
    # fix compliance level
    try:
        df.loc[:, 'compliance_level'] = df['compliance_level'].str.rstrip('%').astype('float')
    except AttributeError:
        pass
    df.loc[:, 'compliance_level'] = df['compliance_level'].fillna(100) /  100
    if any((df['compliance_level'] < 0.01) | (df['compliance_level'] > 1)):
        logger.error(f'One of the compliance levels for {country_iso3} is not between 1% and 100%,'
                     f'check the spreadsheet')
        print(df['compliance_level'])
        logger.error('Exiting')
        sys.exit()
    # Convert location lists to admin 2
    df = expand_admin_regions(df, boundaries)
    # Create 3d xarray
    clist = [
             'r0_reduction',
             'home',
             'other_locations',
             'school',
             'work',
             'mobility_reduction',
             'elderly_shielding'
             ]
    coords = {
        'admin2': sorted([b[2:] for b in boundaries['ADM2_PCODE'].unique()]),
        'date': pd.date_range(df['start_date'].min(), datetime.today()),
        'measure': clist,
        'quantity': ['num_npis', 'compliance_level', 'reduction']
    }
    da = xr.DataArray(np.zeros([len(val) for val in coords.values()]),
                      dims=coords.keys(), coords=coords)
    # Set defaults for reduction and compliance
    da.loc[:, :, :, ['reduction', 'compliance_level']] = 1.0
    # Populate it by looping through the dataframe
    measures_dict = {
        'contact-based': 'school',  # works for now because only have school closures
        'mobility-based': 'mobility_reduction',
        'reproduction number-based': 'r0_reduction'
    }
    for _, row in df.iterrows():
        # TODO: use the real end date if we are extending the NPI file to the future
        date_range = pd.date_range(row['start_date'], min(row['end_date'].to_pydatetime(), datetime.today()))
        affected_pcodes = [r[2:] for r in row['affected_pcodes']]
        measure = MEASURES_DICT[row['bucky_measure']]
        # Amend the compliance level
        previous_num_npis = da.loc[affected_pcodes, date_range, measure, 'num_npis']
        previous_compliance_level =  da.loc[affected_pcodes, date_range, measure, 'compliance_level']
        new_compliance_level = (previous_num_npis * previous_compliance_level + row['compliance_level'] ) \
                                / (previous_num_npis + 1)
        da.loc[affected_pcodes, date_range, measure, 'compliance_level'] = new_compliance_level
        # Track the new number of NPIs
        da.loc[affected_pcodes, date_range, measure, 'num_npis'] += 1
    # Compute R0 reduction
    num_R0_npis = da.sel(measure='r0_reduction', quantity='num_npis').astype(int)
    R0_reduction_dict = {i: np.sum(R0_REDUCTION_AMOUNTS[:i + 1])
                        for i in range(num_R0_npis.values.max() + 1)}
    reduction_amount = np.vectorize(R0_reduction_dict.get)(num_R0_npis)
    R0_compliance_level = da.sel(measure='r0_reduction', quantity='compliance_level')
    da.loc[:, :, 'r0_reduction', 'reduction'] = 1 - reduction_amount * R0_compliance_level
    # Compute mobility reduction
    da.loc[:, :, 'mobility_reduction', 'reduction'] = np.where(
        da.sel(measure='mobility_reduction', quantity='num_npis') > 0,
        1 - MOBILITY_REDUCTION_AMOUNT * da.sel(measure='mobility_reduction', quantity='compliance_level'),
        da.sel(measure='mobility_reduction', quantity='reduction'))
    # Compute contact reduction for schools closing
    for key, value in SCHOOL_REDUCTION_VALUES.items():
        da.loc[:, :, key, 'reduction'] = np.where(
            da.sel(measure='school', quantity='num_npis') > 0, value,
            da.sel(measure=key, quantity='reduction'))
    # Compute elderly shielding
    da.loc[:, :, 'elderly_shielding', 'reduction'] = np.where(
        da.sel(measure='elderly_shielding', quantity='num_npis') > 0,
        ELDERLY_SHIELDING_MULTIPLIER * da.sel(measure='elderly_shielding', quantity='compliance_level'),
        da.sel(measure='elderly_shielding', quantity='reduction'))
    # Convert to dataframe and write out
    df_out = (da.sel(quantity='reduction')
              .drop('quantity')
              .to_dataframe('result')
              .unstack()
              .droplevel(0, axis=1))
    output_dir = os.path.join(config.MAIN_OUTPUT_DIR, country_iso3, 'NPIs')
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = os.path.join(output_dir, config.NPI_FINAL_OUTPUT_FILENAME.format(country_iso3))
    logger.info(f'Writing final results to {filename}')
    df_out.to_csv(filename)


def expand_admin_regions(df, boundaries):
    # Convert all region levels to admin 2
    # If admin 0, just add all of admin 2 directly
    admin_regions = get_admin_regions(boundaries)
    admin1_to_2_dict = boundaries.groupby('ADM1_PCODE')['ADM2_PCODE'].apply(lambda x: x.tolist()).to_dict()
    df['affected_pcodes'] = df['affected_pcodes'].apply(
        lambda x: admin_regions['admin2'] if x == admin_regions['admin0'] else x)
    # For the rest, check if any items in the list are admin 1. If they are, expand them and add them back in
    for row in df.itertuples():
        loc_list = df.at[row.Index, 'affected_pcodes']
        final_loc_list = []
        for loc in loc_list:
            if loc in admin_regions['admin1']:
                final_loc_list += admin1_to_2_dict[loc]
            elif loc in admin_regions['admin2']:
                final_loc_list.append(loc)
            else:
                logger.error(f'Found incorrect pcode {loc}')
        df.at[row.Index, 'affected_pcodes'] = final_loc_list
    return df
