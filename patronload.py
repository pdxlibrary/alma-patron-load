#! /usr/bin/env python2.7
# -*- coding: utf-8 -*-

import codecs
import getopt
import logging
import os
import sys
import re
import unicodecsv
import csv
import smtplib

from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from itertools import islice
from jinja2 import Environment, FileSystemLoader
from xml.sax.saxutils import escape


# Input
CURRENT_PATRON_DATA_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), 
                                        "tmp", 
                                        "patrondata-" + date.today().strftime("%Y%m%d") + ".csv")
DEPARTMENTS_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                "tmp", "departments.csv")
ZIP_CODES_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                              "tmp", "non-distance-zipcodes.txt")

# Templates
TEMPLATES_FOLDER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates")
TEMPLATE_FILENAME = "userdata-template.xml"

# Ouptut
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "tmp")
OUTPUT_FILENAME_BASE = "-userdata.xml"
GROUP_CHANGE_FILENAME = "group-changes.csv"
NEW_DEPARTMENTS_FILENAME = "new-departments.csv"
RETURN_ADDRESS = 'Patron Load <patronload@www.lib.pdx.edu>'
SMTP_HOST = "mailhost.pdx.edu"

class Patron:
    campus_phone_prefix = '503-725-'
    campus_email_domain = 'pdx.edu'
    patron_types = {
        'FACULTY': 'faculty',
        'ENROLLED-FACULTY': 'enrolled-faculty',
        'EMERITUS': 'emeritus',
        'GRADASSISTANT': 'gradasst',
        'GRADUATE': 'grad',
        'HONOR': 'honors',
        'UNDERGRADUATE': 'undergrad',
        'HIGHSCHOOL': 'highschool',
        'STAFF': 'staff'
    }
    coadmits = {
        "Coadmit - Clackamas CC": "COAD - CLCC",
        "Coadmit - Mt Hood CC": "COAD - MHCC",
        "Coadmit - Portland CC": "COAD - PCC",
        "Coadmit - Chemeketa CC": "COAD - CHMK CC",
        "Coadmit - Clatsop CC": "COAD - CCC",
        "Coadmit - Clark College": "COAD - CLARK",
        "Coadmit - PostBac": "COAD - PostBac"
    }

    @staticmethod
    def get_expiration_date(patron_type):
        if patron_type in ['staff', 'staff-distance']:
            if date.today() < datetime.strptime(str(date.today().year) + "0601", "%Y%m%d").date():
                expdate = datetime.strptime(str(date.today().year + 2) + "0630", "%Y%m%d")
            else:
                expdate = datetime.strptime(str(date.today().year + 1) + "0630", "%Y%m%d")
        elif patron_type in ['faculty', 'gradasst', 'emeritus', 'enrolled-faculty',
                             'faculty-distance', 'gradasst-distance', 'emeritus-distance']:
            expdate = datetime.strptime(str(date.today().year + 2) + "0630", "%Y%m%d")
        elif patron_type in ['grad', 'undergrad', 'honors', 'highschool',
                             'grad-distance', 'undergrad-distance', 'highschool-distance']:
            # 1/1 - 3/14
            if date.today() < datetime.strptime(str(date.today().year) + "0315", "%Y%m%d").date():
                expdate = datetime.strptime(str(date.today().year) + "1020", "%Y%m%d")
            # 3/15 - 6/14
            elif date.today() < datetime.strptime(str(date.today().year) + "0615", "%Y%m%d").date():
                expdate = datetime.strptime(str(date.today().year) + "1020", "%Y%m%d")
            # 6/15 - 8/31
            elif date.today() < datetime.strptime(str(date.today().year) + "0901", "%Y%m%d").date():
                expdate = datetime.strptime(str(date.today().year + 1) + "0131", "%Y%m%d")
            # 9/1 - 12/14
            elif date.today() < datetime.strptime(str(date.today().year) + "1215", "%Y%m%d").date():
                expdate = datetime.strptime(str(date.today().year + 1) + "0425", "%Y%m%d")
            # 12/15 - 12/31
            else:
                expdate = datetime.strptime(str(date.today().year + 1) + "1020", "%Y%m%d")
        else:
            expdate = datetime.strptime(str(date.today().year + 2) + "0630", "%Y%m%d")

        return expdate.date()

    def __init__(self, patron_data, is_distance=False):
        """
        Patron Data Fields
        patron
        per_pidm
        id_number
        last_name
        first_name
        middle_name
        street_line1
        street_line2
        street_line3
        city_1
        state_1
        zip_1
        phone
        alt_phone
        email
        stu_major
        stu_major_desc
        orgn_code_home
        orgn_desc
        coadmit
        honor_prog
        stu_username
        udc_id
        pref_first_name
        termination_dt
        """

        if patron_data['pref_first_name']:
            self.first_name = patron_data['pref_first_name'] 
        else:
            self.first_name = patron_data['first_name']

        self.barcode = patron_data['id_number']
        self.middle_name = patron_data['middle_name']
        self.last_name = patron_data['last_name']

        if is_distance and patron_data['patron'] != 'HIGHSCHOOL':
            self.patron_type = self.patron_types[patron_data['patron']] + "-distance"
        else:
            self.patron_type = self.patron_types[patron_data['patron']]

        if patron_data['coadmit']:
            self.coadmit_code = self.coadmits[patron_data['coadmit']]

        self.address_line1 = escape(patron_data['street_line1'])
        self.city = patron_data['city_1']
        self.state = patron_data['state_1']
        self.zip_code = patron_data['zip_1'][:5]

        if self.patron_type == 'faculty' or self.patron_type == 'enrolled-faculty':
            self.address_type = 'work'
        elif is_distance:
            self.address_type = 'home'
        else:
            self.address_type = 'school'

        self.expdate = self.get_expiration_date(self.patron_type)
        self.purge_date = self.expdate + timedelta(days=180)

        self.email = patron_data['email']
        if self.email.endswith(self.campus_email_domain):
            self.email_address_type = 'work'
        else:
            self.email_address_type = 'personal'

        # Sanitize phone numbers by stripping non-numeric characters and adding hyphens to the first 10 numbers
        phone_numbers = re.compile(r'[^\d]+')
        if patron_data['phone']:
            clean_phone = phone_numbers.sub("", patron_data['phone'])
            self.telephone = '-'.join([clean_phone[:3], clean_phone[3:6], clean_phone[6:10]])
            if self.campus_phone_prefix in self.telephone:
                self.telephone_type = 'office'
            else:
                self.telephone_type = 'home'
        if patron_data['alt_phone']:
            if patron_data['alt_phone'] != patron_data['phone']:
                clean_phone = phone_numbers.sub("", patron_data['alt_phone'])
                self.telephone2 = '-'.join([clean_phone[:3], clean_phone[3:6], clean_phone[6:10]])
                if self.campus_phone_prefix in self.telephone2:
                    self.telephone2_type = 'office'
                else:
                    self.telephone2_type = 'home'

        if patron_data['stu_username'] == '':
            raise ValueError('Username missing for patron record %s' % self.barcode)
        else:
            self.username = patron_data['stu_username']

        if patron_data['orgn_desc']:
            self.department_code = patron_data['orgn_desc'].split(" ")[0]

        self.start_date = date.today().strftime("%Y%m%d")

options = {
    u'-d, --debug': u'Debug mode',
    u'-h, --help': u'Display help',
    u'-r, --recipients': u'Comma-separated list of email notice ecipient(s)',
}


def usage():
    print(u'\nUsage: patronload.py [options]\n')
    print(u'Options:')
    for key, value in sorted(options.iteritems()):
        print(u'\t%s\t%s' % (key, value))
    print(u'\n')


def load_department_codes_file(file_path):
    file_contents = {}

    csv_file = open(file_path)
    csv_reader = csv.DictReader(csv_file, delimiter=',')
    for row in csv_reader:
        file_contents[row['code']] = row['label']
    csv_file.close()

    return file_contents


def load_zip_codes_file(file_path):
    file_contents = []

    text_file = open(file_path)
    file_contents = text_file.read().splitlines()
    text_file.close()

    return file_contents


def load_patron_data_file(file_path, non_distance_zip_codes):
    patron_data = {}

    csv_file = open(file_path, 'rb')
    csv_reader = unicodecsv.DictReader(csv_file, delimiter=',', encoding='ISO-8859-1') 
    for row in csv_reader:
        distance = False
    
        if row['zip_1'] and row['zip_1'][:5] not in non_distance_zip_codes:
            distance = True
        try:
            if row['street_line1'] == '':
                logging.warn("Mandatory field street_line1 is not present in record %s" % row['id_number'])
            elif row['email'] == '':
                logging.warn("Mandatory field email is not present in record %s" % row['id_number'])
            else:
                patron_data[row['id_number']] = Patron(row, distance)
        except ValueError as error:
            logging.warn(error.args)

    csv_file.close()

    return patron_data


def find_patron_data_diffs(patron_data, previous_file, non_distance_zip_codes):
    group_changes = {}
    previous_patron_data = load_patron_data_file(previous_file, non_distance_zip_codes)

    for barcode, patron in patron_data.items():
        if hasattr(patron, 'department_code'):
            if barcode in previous_patron_data.keys():
                if hasattr(previous_patron_data[barcode], 'department_code'):
                    logging.debug("User with barcode %s changed from %s to %s." % (barcode, patron.department_code, previous_patron_data[barcode].department_code))
                    if patron.department_code != previous_patron_data[barcode].department_code:
                        group_changes[barcode] = patron.department_code 
                else:
                    logging.debug("Record for user with barcode %s has no department. Not updating this account." % (barcode, patron.department_code))
            else:
                logging.debug("User with barcode %s is was added today. Department code should be correct." % barcode)

    return group_changes


def find_new_department_codes(department_codes, patron_data):
    new_department_codes = []

    for barcode, patron in patron_data.items():
        if hasattr(patron, 'department_code'):
            if patron.department_code not in department_codes and patron.department_code not in new_department_codes:
                if hasattr(patron, 'department_name'):
                    logging.debug("New department code %s \"%s\" found in record %s" % (patron.department_code,
                                                                                        patron.department_name,
                                                                                        patron.barcode))
                else:
                    logging.debug("New department code %s found in record %s" % (patron.department_code,
                                                                                 patron.barcode))
                new_department_codes.append(patron.department_code)

    return new_department_codes


def dict_chunks(dict_data, chunk_size=10000):
    # based on http://stackoverflow.com/questions/22878743/how-to-split-dictionary-into-multiple-dictionaries-fast
    iterator = iter(dict_data)
    for i in xrange(0, len(dict_data), chunk_size):
        yield {key: dict_data[key] for key in islice(iterator, chunk_size)}


def find_fn_ln_issue(patron_data):
    issues = []

    for barcode, patron in patron_data.items():
        if patron.first_name == patron.last_name:
            issues.append(barcode)

    return issues


def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'dhr:', ['help', 'debug', 'recipients'])
    except getopt.GetoptError as error:
        print(str(error))
        usage()
        sys.exit(2)

    option_missing = False
    debug = False
    notice_recipients = []

    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage()
            sys.exit(2)
        if opt in ('-d', '--debug'):
            debug = True
        if opt in ('-r', '--recipients'):
            notice_recipients = arg.split(',')

    if len(notice_recipients) == 0:
        print('Email notice recipients missing')
        option_missing = True

    if option_missing:
        usage()
        sys.exit(2)

    if debug:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARN)

    department_codes = load_department_codes_file(DEPARTMENTS_FILE)
    non_distance_zip_codes = sorted(load_zip_codes_file(ZIP_CODES_FILE))
    patron_data = load_patron_data_file(CURRENT_PATRON_DATA_FILE, non_distance_zip_codes)
    new_department_codes = find_new_department_codes(department_codes, patron_data)
    fn_ln_issues = find_fn_ln_issue(patron_data)

    if len(new_department_codes) > 0:
        message_text = "New department codes were found in the patron load\n\n"
        for department_code in new_department_codes:
            message_text += "\n" + str(department_code)

        message = MIMEText(message_text)
        message['Subject'] = 'New department codes found in the patron load'
        message['From'] = RETURN_ADDRESS
        message['To'] = ', '.join(notice_recipients)

        s = smtplib.SMTP(SMTP_HOST)
        s.sendmail(re.findall(r'<(.*)>', RETURN_ADDRESS)[0], notice_recipients, message.as_string())
        s.quit()

    if len(fn_ln_issues) > 0:
        for barcode in fn_ln_issues:
            logging.warn("First name - last name issue with %s" % barcode)

    env = Environment(loader=FileSystemLoader(TEMPLATES_FOLDER), trim_blocks=True)
    template = env.get_template(TEMPLATE_FILENAME)
    file_iterator = 1

    logging.info("%s records found." % len(patron_data))

    for patron_list in dict_chunks(patron_data, 10000):
        result = template.render(patron_data=patron_list)
        filename = str(file_iterator) + OUTPUT_FILENAME_BASE

        logging.info("Writing %s records to %s." % (len(patron_list), filename))

        with codecs.open(os.path.join(OUTPUT_FOLDER, filename), 'w', encoding="utf-8") as f:
            f.write(result)
            f.close()
        file_iterator += 1
        logging.info("Data written to " + filename + ".")


if __name__ == '__main__':
    main()

