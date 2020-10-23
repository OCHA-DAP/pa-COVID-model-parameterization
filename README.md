# COVID model parameterization

The main output of this repository are an Input Graph and a NPI file, which can be used as input for the [COVID projection model](https://github.com/OCHA-DAP/pa-ocha-bucky/) which has been developed in partnership between UN OCHA and the Johns Hopkins University Applied Physics Laboratory (JHU/APL). 
The parametrization has been tested for six countries, of which the required files will also be downloaded during the setup. These countries are Afghanistan, the Democratic Republic of Congo, Iraq, Somalia, Sudan and South Sudan. Simultaneously, we encourage users to add their own countries of interest with the given instructions. 

The methodology and reasoning behind the parameterization implemented in this repository can be found [here](https://docs.google.com/document/d/1Izusop2liq3bvcDEG3l-ttQnt0a-fw037fBId2Y6fRw/edit?usp=sharing).

## General

### Running for the first time

1. Install all packages from `requirements.txt`.
     ``` bash
     pip install -r requirements.txt
     ```
   
   If using Anaconda, set-up an environment and install the packages from `environment.yml`. 
   ``` bash
   conda env create --file environment.yml --name covid_param
   conda activate covid_param
     ```
   
2. Run `make setup` (downloads several large files, may take some time)

### Updating the NPI and graph output files

1. Run `make update_npi`
2. Triage the resulting NPIs:
    1. Copy and paste the output Excel file to the Google sheet
    2. Indicate if any of the new NPIs can be modelled, and if so, if they should be included
       in the final input
    3. For any new measures that are to be included, fill in the Bucky measurement type, affected pcodes, and 
       and compliance level
3. Run `make update`

### Adding a new country

1. Make a new country config file in `config/`, start by 
   using `config/template.yml` as a guide
2. Go through each of the **Setup** and **Running** steps for the individual components

## Individual components

### Exposure

#### Setup

1. Download the admin level 2 country boundaries shapefile from HDX and place in `Inputs/$COUNTRY_ISO3/Shapefile/`. 
2. Unzip the contents into a directory with the same name as the shapefile, and add this name to the config file 
  under the `admin` section 
3. Also add the language suffix of the primary region name (e.g. EN) 
4. Commit the shapefile to the repository.

#### Running
The first time you run, execute:
```bash
python Generate_SADD_exposure_from_tiff.py [Country ISO code] -d
```
The `-d ` flag is for downloading the WolrdPop files (they are large). 


### Vulnerability

#### Setup

1. Check [GHS](https://ghsl.jrc.ec.europa.eu/download.php) for the grid square numbers that cover the country
  and add these to the config file under the `ghs` section. It helps to double check that the grid squares
  fully cover the country by displaying the admin regions file over the GHS rasters using QGIS.
2. Download food security data from [IPC](http://www.ipcinfo.org/ipc-country-analysis/population-tracking-tool/en/):
   1. Select the country from the dropdown menu, use the date slider to select
      only data from 2020, and export using the "Excel" button
   2. Save the excel file to `Inputs/$COUNTRY_ISO3/IPC`
   3. Add the filename, last row number, and admin level to the config file in the `ipc` section
   4. In the `replace_dict`, add any region names that have a different format than in the admin regions file
     (the script will also warn you about any mismatches so you can fill this part in iteratively)
   5. Commit the Excel file to the repository
3. If available, add the following to the config file:
   1. [solid fuels](https://apps.who.int/gho/data/node.main.135?lang=en)
   2. [raised blood pressure](https://www.who.int/nmh/countries)
   3. diabetes (from [WHO](https://www.who.int/nmh/countries) or [GHDX](http://ghdx.healthdata.org/countries))
   4. [handwashing facilities](https://washdata.org/data/downloads#WLD)
   5. [smoking](https://vizhub.healthdata.org/tobacco/) 
 
#### Running 

Make sure you have successfully run the exposure script for the country.

To run, execute:
```bash
python Generate_vulnerability_file.py [Country ISO code] -d
```
The `-d ` flag is for downloading and mosaicing the GHS data the first time you run.


### Mobility

#### Setup

1. Add the car ownership fraction from 
  [WHO](https://www.who.int/violence_injury_prevention/road_safety_status/country_profiles/en/)
  and household size from the [UN](https://population.un.org/Household/index.html#/countries/)
2. If either or both sources are missing, set the household size to 1 and the car ownership fraction
  to some reasonable final maximum value (like 0.2)

#### Running

Make sure you have downloaded the country shapefile as described in the **Exposure** step. 

To run for the first time, execute:
``` bash
python Generate_mobility_matrix [Country ISO code]
```
The script automatically caches the distances between regions, and the road intersection information.
Since the shapefile should rarely be updated you can usually run using the cached distances by using the `-d` flag:
```bash
python Generate_mobility_matrix [Country ISO code] -d
```
HOTOSM occasionally refreshes the roads file, so it's good to update it every so often. However, 
if you're in a hurry you can also run with the cached road intersections using the `-c` flag:
```bash
python Generate_mobility_matrix [Country ISO code] -d -c
```

### COVID cases

#### Setup
1. Find the COVID-19 dataset file for the country on HDX, and add the URL for the direct download to the config file under `covid:url`
2. Set the different parameters according to the description in the config file template
3. Make sure the `replace_dict` field is accurate to match the admin names in the covid file and in the exposure file

#### Running
To run, execute: 
```bash
python Generate_COVID_file.py [Country ISO code] -d
```
The `-d ` flag is for downloading the latest COVID data. 
A common warning is given when the admin names in the covid file don't match teh exposure. The following warning is printed on the terminal: `missing PCODE for the following admin units:` and the list is provided. To fix that, add the missing units in the `replace_dict` dictionary in the config file. 

### Graphs
The graph collects the COVID-19 case data, mobility data, contact matrix, population data, and vulnerability data
into a single file.

#### Setup
1. Under the `contact_matrix` section of the config file, add the country name of the country used for 
   the contact matrix, and whether it falls alphabetically in file 1 (_Albania_ to _Morocco_) or
   file 2 (_Mozambique_ to _Zimbabwe_)

#### Running 
To run, execute:
```bash
python Generate_graph.py [Country ISO code]
```

### NPIs

#### Setup

1. Run first with the `-u` flag to create the Excel file (and with the `-d` flag to get the latest
  ACAPS file)
2. Copy and paste the contents into a new Google sheet, and publish it as a csv
3. Add the URL of the published sheet to the config file under `NPIs`  
4. Run with the `-f` flag to create the final csv file for bucky, and commit this file to the repository

#### Running

Make sure you have downloaded the country shapefile as described in the **Exposure** step. 

There are two modes to run the NPI script:
1. `--update-npi-list` or `-u`: This mode uses the local ACAPS data file (use the `-d` flag do download
     the latest version), and creates an Excel file 
    (located in `Inputs/[Country ISO code]/NPIs/[Country ISO code]_NPIs_input.xlsx`)
    for each country containing the ACAPS measures and, if it exists, any additional parameters / measures
    from the country's Google sheet
    - After running, you should copy and paste the cells of the Excel file to the 'Published' tab
      on the country's Google sheet, which should then be triaged
2. `--create-final-list` or `f`: Generate a csv file of NPI results to be read in by Bucky 

To run in update mode:
```bash
python Generate_NPIs.py [Country ISO code] -u -d
```
The `-d ` flag is for downloading the latest ACAPS data.

To run in final file creation mode: 
```bash
python Generate_NPIs.py  [Country ISO code] -f 
```

### Output Quality

This script checks the two final output files (the graph and NPIs) for any missing or unexpected values.

#### Running
Make sure you have generated the graph and NPI files.
```bash
python Check_output_quality.py [Country ISO code]
```
To do an extra-thorough check and run with warnings, use the `-w` flag:
```bash
python Check_output_quality.py [Country ISO code] -w
```
