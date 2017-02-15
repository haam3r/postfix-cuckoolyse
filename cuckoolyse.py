#!/usr/bin/python
## Cuckoolyse
## Extract attachments from email and submit to remote cuckoo instance
## Initially a Postfix filter, but can be used with any email message Python is happy with.
##
## Author: Thomas White <thomas@tribalchicken.com.au>
## https://tribalchicken.com.au


# TODO: Configurable logging location
# TODO: Probably needs a sanity check on the file size
# TODO: Write out to staging file rather than keeping object in-memory? Maybe?

import email
import sys
import magic
import requests
import logging
import hashlib
import json

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
url = "http://YOUR_CUCKOO_ADDR:8090"

# Prefix to prepend to filename in submission
prefix = "CUCKOOLYSE-"

def upload_to_cuckoo(filename, attachment, mode=None):
    """
        Cuckoo upload helper
    """
    logging.info("Got file: %s", filename)
    office = ['.doc', '.docx', '.docm', '.xls', '.xlsm', '.xlt', '.xltm', '.ppt', '.pptx']
    for extension in office:
        if filename.endswith(extension):
            mode = "office"
            logging.info("Changing to Office mode")

    # Check if file has already been analysed
    try:
        shasum = hashlib.sha256(attachment).hexdigest()
        logging.debug("Checking if %s has already been analysed...", shasum)

        # Request file info from Cuckoo
        response = requests.get("{0}/files/view/sha256/{1}".format(url, shasum))

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
                files = {"file":(prefix +filename, attachment)}
                payload = {'options': "mode=%s" % mode}
                logging.info("mode = %s %s", mode, files)
            else:
                files = {"file":(prefix +filename, attachment)}
                payload = {}

            response = requests.post("{0}/tasks/create/file".format(url), files=files, data=payload)
            json_decoder = json.JSONDecoder()
            task_id = json_decoder.decode(response.text)["task_id"]
            logging.debug("ADDED TASK: %s", task_id)

            if task_id is None:
                raise Exception("No Task ID from Cuckoo. Assuming submission failure")

            logging.info("SUCCESS: Submitted to Cuckoo as task ID %s", task_id)
            return 0
        else:
            raise Exception("Unexpected response code whilst requesting file details")

    except Exception as e:
        logging.error("Unable to submit file to Cuckoo: %s", e)
        return 1


# Submit the sample to cuckoo
def cuckoolyse(msg):
    """
        Parse email for attachment
    """
    logging.debug("Received email with subject %s from %s", msg['subject'], msg['from'].encode('utf-8').strip())
    # Check if multipart
    if not msg.is_multipart():
        #Not multipart? Then we don't care, pass it back
        logging.debug("Returning non-multipart message to queue.")
        return

    # Cycle through multipart message
    # Find attachments (application/octet-stream?)
    for part in msg.walk():
        if part.get('Content-Disposition') is None:
            logging.debug("Email Content-Disposition is None")
            continue
        if not part.get_content_type().strip() in mtypes:
            logging.debug("Processing mail part of type: %s", part.get_content_type())
            attachment = part.get_payload(decode=True)
            filename = part.get_filename().encode('utf-8').strip()
            logging.info("Found attachment %s from %s", filename, msg['from'])

            upload_to_cuckoo(filename, attachment)

# Get email from STDIN
input = sys.stdin.readlines()
msg = email.message_from_string(''.join(input))

# Cuckoolyse!
cuckoolyse(msg)
