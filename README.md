# COVID model parameterization

[Methodology (Google Doc)](https://docs.google.com/document/d/1Izusop2liq3bvcDEG3l-ttQnt0a-fw037fBId2Y6fRw/edit?usp=sharing)

## General
 - how to run update
 - use config of previous country as guide

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

Once you've downloaded these files, you can run without the `-d` flag. 


### Vulnerability

#### Setup

1. Check [GHS](https://ghsl.jrc.ec.europa.eu/download.php) for the grid square numbers that cover the country
  and add these to the config file under the `ghs` section
2. Download food security data from [IPC](http://www.ipcinfo.org/ipc-country-analysis/population-tracking-tool/en/):
   1. Select the country and only data from 2020, save the excel file to `Inputs/$COUNTRY_ISO3/IPC`
   2. Add the filename, last row number, and admin level to the config file in the `ipc` section
   3. In the `replace_dict`, add any region names that have a different format than in the admin regions file
     (the script will also warn you about any mismatches so you can fill this part in iteratively)
   4. Commit the excel file to the repository
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

Once you've downloaded these files, you can run without the `-d` flag. 


### Graph
The graph collects the COVID-19 case data, mobility data, contact matrix, population data, and vulnerability data
into a single file.

#### Running 

To run, execute:
```bash
python Generate_graph.py [Country ISO code]
```
