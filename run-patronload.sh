#! /usr/bin/env bash

# Run the patron load.

APPHOME=${PWD}

## Load process configuration files
. config/patronload.config

if [ ! -d $config_tempfolder ]; then
	mkdir $config_tempfolder
fi

# Retrieve patron data file from the Banner SFTP server.
# Using sshpass is not ideal, but key-based ssh auth wasn't a possibility.
cd $config_tempfolder
sshpass \
	-p $config_banner_sftppass sftp -oStrictHostKeyChecking=no -oBatchMode=no -b - \
	$config_banner_sftpuser@$config_banner_sftphost << EOF
	cd $config_banner_path
	get $config_banner_filename	
	bye
EOF

# Retrieve the non-distance ZIP codes file from DFS
smbclient -U $config_ad_user -c "cd $config_ad_path; get $config_ad_zipcodefilename; get $config_ad_deptcodefilename; exit" //$config_ad_fileserver/$config_ad_share "$config_ad_pass"

# Sanitize the patron data file
cd $APPHOME

## Patron load - Generate Alma XML files
if [[ $config_debug ]]; then
        echo "Running the patron load (`date`)..."
fi
./venv/bin/python patronload.py -r "cgeib@pdx.edu"

# Generate the ZIP file in the SFTP location
cd $config_tempfolder
zip -q $config_sftplocation/$config_zipfilename *-${config_xmlfilenamebase}

# Archive the files used for this load
zip $config_archivelocation/$config_archivefilename $config_ad_zipcodefilename $config_banner_filename

if [[ $config_debug ]]; then
        echo "Finished patron load (`date`)."
fi

# Clean up
cd $APPHOME
if [[ ! $config_debug ]]; then
        rm -f $config_tempfolder/*
fi

