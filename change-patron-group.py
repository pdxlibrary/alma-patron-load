#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Change group of an Alma user.
# Argument is the user's primary identifier.
#

import os, requests, sys
from bs4 import BeautifulSoup
from optparse import OptionParser


ALMA_API_BASE_URL = 'https://api-na.hosted.exlibrisgroup.com'
ALMA_USERS_API_PATH = '/almaws/v1/users'

# Mandatory fields that are not primary identifiers
MANDATORY_ADDRESS_FIELDS = [ 'line1', 'email' ]

def main(argv):
    usage = "usage: %prog [options] barcode"

    parser = OptionParser(usage=usage)
    parser.add_option(
            '-g', '--group-name',
            help='Assign the account to GROUP_NAME',
            default='expired',
            dest='group_name'
    )
    parser.add_option(
            '-k', '--api-key', 
            help='Alma API key', 
            dest='api_key'
    )
    parser.add_option(
            '-v', '--verbose',
            help='Verbose mode: display actions taken on the account',
            action='store_true',
            default=False,
            dest='verbose'
    )

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error('Incorrect number of arguments.')

    barcode = args[0]
    headers = { 'Authorization': 'apikey ' + options.api_key }
    request_url = ALMA_API_BASE_URL + ALMA_USERS_API_PATH + '/' + barcode + '?override=user_group'
    r = requests.get(request_url, headers=headers)

    if options.verbose:
        print("HTTP Headers: %s" % headers)
        print("HTTP Request: %s" % request_url)

    soup = BeautifulSoup(r.text, features='xml')
    user_group = soup.find('user_group').string

    addresses = soup.find_all("address")
    for address in addresses:
        for field in MANDATORY_ADDRESS_FIELDS:
            if field not in address.children:
                if options.verbose:
                    print("Field %s does not exist for %s. Adding it and assigning a filler value." % (field, barcode))
                new_field = soup.new_tag(field)
                new_field.string = "FILLER"
                address.append(new_field)

    if options.verbose:
        print("Reassigning patron with barcode '%s' to group '%s'" % (barcode, options.group_name))

    tag = soup.new_tag('user_group')
    tag.string = options.group_name
    soup.find('user_group').replace_with(tag)

    xml = str(soup)
    if options.verbose:
        print("XML string to send: %s" % soup.prettify())

    headers = { 'Authorization': 'apikey ' + options.api_key, 'Content-Type': 'application/xml' }
    r = requests.put(request_url, data=xml, headers=headers).text
    if options.verbose:
        print(r)


if __name__ == "__main__":
    main(sys.argv)

