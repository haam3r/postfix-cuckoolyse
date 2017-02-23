#!/usr/bin/python
## Cuckoolyse
## Extract attachments from email and submit to remote cuckoo instance
## Initially a Postfix filter, but can be used with any email message Python is happy with.
##
## Author: Thomas White <thomas@tribalchicken.com.au>
## https://tribalchicken.com.au

## Modifcations by haam3r (https://github.com/haam3r)
## To install sflock, simply do pip install sflock

# TODO: Configurable logging location
# TODO: Probably needs a sanity check on the file size
# TODO: Write out to staging file rather than keeping object in-memory? Maybe?

import email
import sys
import logging
import json
import requests
from sflock.main import unpack

logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(levelname)s %(message)s',filename='/home/cuckoolyse/cuckoolyse.log',filemode='a')

### CONFIG OPTIONS ###
# MIME Types to ignore in the email aka extract and submit everything else.

mtypes = [
            'multipart/mixed',
            'multipart/alternative',
            'multipart/report',
            'multipart/html',
            'multipart/related',
            'message/rfc822',
            'message/delivery-status',
            'text/plain',
            'text/rfc822-headers',
            'text/html'
]

#REST URL for Cuckoo submission
url = "http://cuckoo.url.com:8090"

# Prefix to prepend to filename in submission
prefix = "CUCKOOLYSE-"

def upload_to_cuckoo(f, mode=None):
    """
        Cuckoo upload helper
    """
    logging.info("Got file: %s", f.filename)
    office = ['.doc', '.docx', '.docm', '.xls', '.xlsm', '.xlt', '.xltm', '.ppt', '.pptx']
    for extension in office:
        if f.filename.endswith(extension):
            mode = "office"
            logging.info("Changing to Office mode")

    # Check if file has already been analysed
    try:
        logging.debug("Checking if %s has already been analysed...", f.sha256)
        # Request file info from Cuckoo
        response = requests.get("{0}/files/view/sha256/{1}".format(url, f.sha256))
    except requests.exceptions.RequestException as check_err:
        logging.error("Unable to check if unique: %s", check_err)
        return 1

    try:
        # 404 Response indicates hash does not exist
        # 200 indicates file already exists
        if response.status_code == 200:
            finfo = response.json()
            logging.info("File has already been analysed, not submitting")
            logging.debug("Response was: %s", finfo)
        elif response.status_code == 404:
            logging.info("Submitting to cuckoo via %s", url)
            # Send request
            if mode:
                files = {"file": (prefix +f.filename, f.contents)}
                payload = {'options': "mode=%s" % mode}
                logging.info("Setting mode = %s for file %s", mode, f.filename)
            else:
                files = {"file": (prefix +f.filename, f.contents)}
                payload = {}

            response = requests.post("{0}/tasks/create/file".format(url), files=files, data=payload)
            json_decoder = json.JSONDecoder()
            task_id = json_decoder.decode(response.text)["task_id"]

            if task_id is None:
                raise Exception("No Task ID from Cuckoo. Assuming submission failure")

            logging.info("SUCCESS: Submitted to Cuckoo as task ID %s", task_id)
            return 0
        else:
            raise Exception("Unexpected response code whilst requesting file details")

    except requests.exceptions.RequestException as submit_err:
        logging.error("Unable to submit file to Cuckoo: %s", submit_err)
        return 1


# Submit the sample to cuckoo
def cuckoolyse(msg):
    """
        Parse email for attachment(s)
    """
    logging.debug("Received email with subject %s from %s", msg['subject'], msg['from'])

    # Check if multipart
    if not msg.is_multipart():
        #Not multipart? Then we don't care, pass it back
        logging.info("Returning non-multipart message to queue.")
        return

    # Cycle through multipart message for attachments to analyse
    for part in msg.walk():
        if part.get('Content-Disposition') is None:
            logging.debug("Email Content-Disposition is None")
            continue
        if not part.get_content_type().strip() in mtypes:
            logging.debug("Processing mail part of type: %s", part.get_content_type())
            attachment = part.get_payload(decode=True)
            filename = part.get_filename().encode('utf-8').strip()
            logging.debug("Found attachment %s from %s", filename, msg['from'])
            # Hand it over to sflock for parsing
            f = unpack(filename=filename, contents=attachment)

            try:
                if f.astree().get('children'):
                    for child in f.children:
                        logging.debug("Extracted file: %s", child.filename)
                        upload_to_cuckoo(child)
                else:
                    upload_to_cuckoo(f)
            except Exception as e:
                logging.error(e)
                logging.error("Caught exception while submitting for upload %s", f)

# Get email from STDIN
input = sys.stdin.readlines()
msg = email.message_from_string(''.join(input))

# Cuckoolyse!
cuckoolyse(msg)
