import os
import logging
from pathlib import Path
import argparse
import ast
from datetime import datetime

import pandas as pd
import geopandas as gpd
import xarray as xr
import numpy as np

from covid_model_parametrization import utils
from covid_model_parametrization.hdx_api import query_api
from covid_model_parametrization.utils import config_logger

CONFIG_FILE = 'config.yml'

ACAPS_HDX_ADDRESS = 'acaps-covid19-government-measures-dataset'
INPUT_DIR = 'Inputs'
OUTPUT_DIR = 'Outputs'

RAW_DATA_DIR = os.path.join(INPUT_DIR, 'ACAPS_NPIs')
RAW_DATA_FILENAME = 'ACAPS_npis_raw_data.xlsx'
RAW_DATA_FILEPATH = os.path.join(RAW_DATA_DIR, RAW_DATA_FILENAME)

OUTPUT_DATA_DIR = 'NPIs'
INTERMEDIATE_OUTPUT_FILENAME = '{}_NPIs_input.xlsx'
TRIAGED_INTERMEDIATE_OUTPUT_FILENAME = '{}_NPIs_triaged.csv'
FINAL_OUTPUT_FILENAME = '{}_NPIs.csv'

MEASURE_EQUIVALENCE_FILENAME = 'NPIs - ACAPS NPIs.csv'

SHAPEFILE_DIR = 'Shapefiles'

config_logger()
logger = logging.getLogger()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--update-npi-list', action='store_true',
                        help='Download the latest ACAPS data and update NPI list')
    parser.add_argument('-c', '--create-final-list', action='store_true',
                        help='Create the final list of NPIs')
    return parser.parse_args()


def main(update_npi_list_arg, create_final_list_arg):
    config = utils.parse_yaml(CONFIG_FILE)
    countries = list(config.keys())
    countries.remove('HTI')
    if update_npi_list_arg:
        update_npi_list(config, countries)
    if create_final_list_arg:
        create_final_list(config, countries)


def update_npi_list(config, countries):
    logger.info('Getting ACAPS data')
    download_acaps()
    df_acaps = get_df_acaps(countries)
    # Loop through countries
    for country_iso3 in countries:
        add_new_acaps_data(country_iso3, df_acaps[df_acaps['ISO3'] == country_iso3], config)


def download_acaps():
    # Get the ACAPS data from HDX
    Path(RAW_DATA_DIR).mkdir(parents=True, exist_ok=True)
    filename = list(query_api(ACAPS_HDX_ADDRESS, RAW_DATA_DIR).values())[0]
    os.rename(os.path.join(RAW_DATA_DIR, filename), RAW_DATA_FILEPATH)


def get_df_acaps(countries):
    # Open the file
    df_acaps =  pd.read_excel(RAW_DATA_FILEPATH, sheet_name='Database')
    # Take only the countries of concern
    df_acaps = df_acaps[df_acaps['ISO'].isin(countries)]
    # rename columns
    column_name_dict = {
        'ID': 'ID',
        'ISO': 'ISO3',
        'LOG_TYPE': 'add_or_remove',
        'CATEGORY': 'acaps_category',
        'MEASURE': 'acaps_measure',
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
    df_acaps['bucky_measure'] = df_acaps['acaps_measure'].str.lower().map(get_measures_equivalence_dictionary())
    df_acaps = df_acaps[df_acaps['bucky_measure'].notnull()]
    df_acaps['bucky_category'] = df_acaps['bucky_measure'].map(get_measures_category_dictionary())
    # Keep only some columns, moving start date to end
    cnames_to_keep = list(column_name_dict.values()) + ['bucky_measure', 'bucky_category']
    cnames_to_keep.append(cnames_to_keep.pop(cnames_to_keep.index('start_date')))
    df_acaps = df_acaps[cnames_to_keep]
    return df_acaps


def get_measures_equivalence_dictionary():
    df = pd.read_csv(os.path.join(RAW_DATA_DIR, MEASURE_EQUIVALENCE_FILENAME),
                     usecols=['ACAPS NPI', 'Our equivalent'])
    return df.set_index('ACAPS NPI').to_dict()['Our equivalent']


def get_measures_category_dictionary():
    df = pd.read_csv(os.path.join(RAW_DATA_DIR, MEASURE_EQUIVALENCE_FILENAME),
                     usecols=['Our NPIs', 'Category']).dropna()
    return df.set_index('Our NPIs').to_dict()['Category']


def get_boundaries_file(country_iso3, config):
    # Get input boundary shape file, for the admin regions
    input_dir = os.path.join(INPUT_DIR, country_iso3)
    input_shp = os.path.join(input_dir, SHAPEFILE_DIR, config['admin']['directory'],
                             f'{config["admin"]["directory"]}.shp')
    # Read in and rename columns for Somalia
    return gpd.read_file(input_shp).rename(columns={
        'admin0Pcod': 'ADM0_PCODE',
        'admin1Pcod': 'ADM1_PCODE',
        'admin2Pcod': 'ADM2_PCODE',
    })


def add_new_acaps_data(country_iso3, df_country, config):
    logger.info(f'Getting info for {country_iso3}')
    # Check if JSON file already exists, if so read it in
    output_dir = os.path.join(INPUT_DIR, country_iso3, OUTPUT_DATA_DIR)
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
    if 'NPIs' in config[country_iso3]:
        df_manual = get_triaged_csv(config, country_iso3)
        # Fix the columns that are lists
        for col in ['affected_pcodes']:
            df_manual[col] = df_manual[col].apply(lambda x: literal_eval(x))
        for col in ['start_date', 'end_date']:
            df_manual[col] = df_manual[col].apply(pd.to_datetime)
        # Join the pcode info
        for df in [df_country, df_manual]:
            df['ID'] = df['ID'].astype(str)
        df_country = df_country[old_cols].merge(df_manual[['ID', 'bucky_measure', 'start_date'] + new_cols],
                                                how='outer', on='ID')
        # Prioritize start date and bukcy measure from df_manual
        for q in ['bucky_measure', 'start_date']:
            df_country = df_country.rename(columns={f'{q}_y': q})
            df_country[q] = df_country[q].fillna(df_country[f'{q}_x'])
            df_country = df_country.drop(f'{q}_x', axis=1)
    else:
        # If it doesn't exist, add empty columns
        logger.info(f'No input URL in config, creating new file')
        for col in new_cols:
            df_country[col] = None
    # Write out
    for col in ['start_date', 'end_date']:
        df_country[col] = df_country[col].dt.date
    filename = os.path.join(output_dir, INTERMEDIATE_OUTPUT_FILENAME.format(country_iso3))
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f'Writing to {filename}')
    df_country.to_excel(filename, index=False)
    return df_country


def get_triaged_csv(config, country_iso3):
    logger.info(f'Getting triaged csv for {country_iso3}')
    filename = os.path.join(INPUT_DIR, country_iso3, OUTPUT_DATA_DIR,
                            TRIAGED_INTERMEDIATE_OUTPUT_FILENAME.format(country_iso3))
    utils.download_url(config[country_iso3]['NPIs']['url'], filename)
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


def create_final_list(config, countries):
    for country_iso3 in countries:
        logger.info(f'Creating final NPI list for {country_iso3}')
        boundaries = get_boundaries_file(country_iso3, config[country_iso3])
        df_country = get_triaged_csv(config, country_iso3)
        format_final_output(country_iso3, df_country, boundaries)



def format_final_output(country_iso3, df, boundaries):
    logger.info(f'Formatting final output for {country_iso3}')
    # Only take rows with final_input is Yes
    df = df[(df['final_input'] == 'Yes')]
    # Fill empty end dates with today's date
    df['end_date'] = df['end_date'].fillna(datetime.today())
    # Add Bucky category
    df['bucky_category'] = df['bucky_measure'].map(get_measures_category_dictionary())
    # fix compliance level
    try:
        df['compliance_level'] = df['compliance_level'].str.rstrip('%').astype('float')
    except AttributeError:
        pass
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
        date_range = pd.date_range(row['start_date'], row['end_date'])
        affected_pcodes = [r[2:] for r in row['affected_pcodes']]
        measure = measures_dict[row['bucky_category']]
        # Amend the compliance level
        previous_num_npis = da.loc[affected_pcodes, date_range, measure, 'num_npis']
        previous_compliance_level =  da.loc[affected_pcodes, date_range, measure, 'compliance_level']
        new_compliance_level = (previous_num_npis * previous_compliance_level + row['compliance_level']/100 ) \
                                / (previous_num_npis + 1)
        da.loc[affected_pcodes, date_range, measure, 'compliance_level'] = new_compliance_level
        # Track the new number of NPIs
        da.loc[affected_pcodes, date_range, measure, 'num_npis'] += 1
    # Compute R0 reduction
    # First value should really be 0, but that will mess up the multiplication.
    # Setting the dictionary value manually to 0 also doesn't work because somehow
    # the vectorization command makes all values 0, So after vectorizing, manually
    # set all 0s to 1.
    R0_reduction_amounts = [1.0, 0.4, 0.2, 0.1, 0.05]
    num_R0_npis = da.sel(measure='r0_reduction', quantity='num_npis').astype(int)
    R0_reduction_dict = {i: np.prod(R0_reduction_amounts[:i+1])
                        for i in range(num_R0_npis.values.max() + 1)}
    reduction_amount = np.vectorize(R0_reduction_dict.get)(num_R0_npis)
    reduction_amount = np.where(reduction_amount == 1, 0, reduction_amount)
    R0_compliance_level = da.sel(measure='r0_reduction', quantity='compliance_level')
    da.loc[:, :, 'r0_reduction', 'reduction'] = 1 - reduction_amount * R0_compliance_level
    # Compute mobility reduction
    da.loc[:, :, 'mobility_reduction', 'reduction'] = np.where(
        da.sel(measure='mobility_reduction', quantity='num_npis') > 0, 0.4,
        da.sel(measure='mobility_reduction', quantity='reduction'))
    # Compute contact reduction for schools closing
    # TODO: distinguish between schools closing and elderly shielding
    school_reduction_values = {
       'home': 1.05,
       'other_locations': 0.85,
       'school': 0.05,
    }
    for key, value in school_reduction_values.items():
        da.loc[:, :, key, 'reduction'] = np.where(
            da.sel(measure='school', quantity='num_npis') > 0, value,
            da.sel(measure=key, quantity='reduction'))
    # Convert to dataframe and write out
    df_out = da.sel(quantity='reduction').drop('quantity').to_dataframe('result').unstack().droplevel(0, axis=1)
    output_dir = os.path.join(OUTPUT_DIR, country_iso3, 'NPIs')
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = os.path.join(output_dir, FINAL_OUTPUT_FILENAME.format(country_iso3))
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

if __name__ == '__main__':
    args = parse_args()
    main(args.update_npi_list, args.create_final_list)
