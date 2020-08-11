country_list = AFG COD SDN SSD SOM

update:
	for iso3 in ${country_list} ; do \
  	    #python Generate_mobility_matrix.py -d $$iso3 ; \
		python Generate_COVID_file.py -d $$iso3 ; \
		python Generate_graph.py $$iso3 ; \
		if [ $$iso3 = "AFG" ] ; then \
			python Generate_NPIs.py -u -d $$iso3 ; \
		else \
			python Generate_NPIs.py -u $$iso3 ; \
		fi \
	done

update_npi:
	for iso3 in ${country_list} ; do \
  		if [ $$iso3 = "AFG" ] ; then \
			python Generate_NPIs.py -u -d $$iso3 ; \
		else \
			python Generate_NPIs.py -u $$iso3 ; \
		fi \
	done

setup:
	for iso3 in $country_list ; do \
		python Generate_SADD_exposure_from_tiff.py $$iso3
		python Generate_vulnerability_file.py $$iso3
		python Generate_mobility_matrix.py $$iso3
		python Generate_COVID_file.py -d $$iso3
		python Generate_graph.py $$iso3
		python Generate_NPIs.py -u -d $$iso3
	done
