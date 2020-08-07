#!/bin/bash
for iso3 in AFG SSD SDN COD SOM
do
    # python Generate_SADD_exposure_from_tiff.py $iso3
    # python Generate_vulnerability_file.py $iso3

    # Mobility
    # Running the first time:
    # python Generate_mobility_matrix
    # Updating roads file:
    # python Generate_mobility_matrix -d
    # No updates (runs the fastest):
    # python Generate_mobility_matrix -d -c

    python Generate_COVID_file.py -d $iso3
    python Generate_NPIs.py -c
    python Generate_graph.py $iso3
done
