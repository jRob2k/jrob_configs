#!/usr/bin/python3


import json
import pathlib
import platform
from datetime import datetime, timedelta
import urllib.parse
import csv
from pkg_resources import parse_version
from progress.bar import Bar

import requests


API_BASE = "https://na2.mobileiron.com/api/v1"
DELETE_DEVICE = f"{API_BASE}/device"
DELETE_USER = f"{API_BASE}/account"
FIND_SPACES = f"{API_BASE}/tenant/partition/device"
FIND_DEVICES = f"{API_BASE}/device?"
SEND_MESSAGE = f"{API_BASE}/device/message"
FIND_USERS = f"{API_BASE}/account?q=&rows=30000&fq="
WIPE_CANCEL = f"{API_BASE}/device/wipeCancel"
RETIRE_DEVICES = f"{API_BASE}/device/retire"
MODIFY_OWNERSHIP = f"{API_BASE}/device/ownership"
MODIFY_DEVICES = f"{API_BASE}/device"


MODIFY_DEVICE_ATTRIBUTE = f"{API_BASE}/device"
MODIFY_USER_ATTRIBUTE = f"{API_BASE}/account"

#Moth api call to get a list of all machines
MOTH_MACHINES = "https://moth.na.sas.com/api/machines/"

#Set global session variables
SESSION = requests.Session()
MOTH_SESSION = requests.Session()

#Grab today, for use later in the script
TODAY = datetime.today().strftime ('%b-%d-%Y')
TODAY_MONTH = datetime.today().strftime ('%h_%Y')

#Create global variables that point to various files for use later in the script
CREDENTIALS = pathlib.Path.cwd().joinpath('Files', 'Credentials')

DATA_SOURCES = pathlib.Path.cwd().joinpath('Files', 'Data Sources')

MOTH_CERT = pathlib.Path.cwd().joinpath('Files', 'Certificates', 'sas_certs.pem')

SCRIPT_RESULTS = pathlib.Path.cwd().joinpath('Files', 'Script Results', TODAY_MONTH, 'Details')
pathlib.Path(SCRIPT_RESULTS).mkdir(parents=True, exist_ok=True)

def main():

    # sets up the session using credentials from the credentials.json file
    mi_auth = json.loads((CREDENTIALS / 'mi_credentials.json').read_text())
    SESSION.auth = (mi_auth['user'], mi_auth['pass'])

    moth_auth = json.loads((CREDENTIALS / 'moth_credentials.json').read_text())
    MOTH_SESSION.auth = (moth_auth['user'], moth_auth['pass'])
    MOTH_SESSION.verify = MOTH_CERT

    #Get Spaces, MI Devices and Moth devices
    spaces = get_spaces()
    mi_devices = (get_devices(spaces))
    moth_phase_testers, moth_not_phase_testers = get_moth_devices()

    #Update attributes for phase testers
    attribute_results = assign_attributes(mi_devices, moth_phase_testers, moth_not_phase_testers)
    
    #Exports results to csv
    export_results(attribute_results)

def get_spaces():

    print("---")
    print("Getting Spaces from MobileIron")

    spaces = []

    response = SESSION.get(FIND_SPACES)
    if response.status_code != 200:
        print("Didn't work. Check your credentials, roles or connection!")

    for i in response.json()["result"]["searchResults"]:
        #Limited to macOS
        if i['name'] in ('macOS'):
        #Limited to dev for testing
        # if i['name'] in ('Bleeding Edge'):
            spaces.append(i)

    print(f"Retrieved {len(spaces)} Spaces.")

    return spaces

def get_devices(spaces):

    print("---")
    print(f"Getting Devices from {len(spaces)} Space(s).")

    mi_devices = []

    for i in spaces:
        space_Name = i['name']
        query_dict = {
            "dmPartitionId": i["id"],
            "start": 0,
            "rows": 500}
        query = urllib.parse.urlencode(query_dict)
        response = SESSION.get(f"{FIND_DEVICES}{query}")
        if response.status_code != 200:
            continue
        results = response.json()

        for i2 in results["result"]["searchResults"]:
            mi_devices.append(i2)
            mi_devices[mi_devices.index(i2)].update({'space_Name': i['name'], 'space_Id': i['id'], 'space_DeviceCount': i['deviceCount']})

        count = results["result"]["totalCount"] // query_dict["rows"]
        if results["result"]["totalCount"] % query_dict["rows"]:
            count += 1
        for _ in range(count):
            query_dict["start"] = results["result"]["offset"] + query_dict["rows"]
            query = urllib.parse.urlencode(query_dict)
            response = SESSION.get(f"{FIND_DEVICES}{query}")
            if response.status_code != 200:
                continue
            results = response.json()

            for i2 in results["result"]["searchResults"]:
                mi_devices.append(i2)
                mi_devices[mi_devices.index(i2)].update({'space_Name': i['name'], 'space_Id': i['id'], 'space_DeviceCount': i['deviceCount']})

    return mi_devices

def get_moth_devices():
    print("---")
    print(f"Getting Devices from Moth.")


    moth_phase_testers = []
    moth_not_phase_testers = []

    go = 'go'
    moth_machines = MOTH_MACHINES

    response = MOTH_SESSION.get(moth_machines)
    results = response.json()

    #Iterate through pages grabbing serial numbers of devices in Testing munki environment Stops when the next page is "None"
    while go == 'go':
        for i in results['results']:
            if 'TESTING' in (str.upper(i['munki_environment']), str.upper(i['salt_environment']), str.upper(i['mobileiron_environment'])):
                moth_phase_testers.append(i['serial'])
            else:
                moth_not_phase_testers.append(i['serial'])
        if results['next'] != None:
            moth_machines = results['next']
            response = MOTH_SESSION.get(moth_machines)
            results = response.json()
        else:
            go = 'stop'
    print(f"Found {len(moth_not_phase_testers)} non-phase testers in Moth.")
    print(f"Found {len(moth_phase_testers)} phase testers in Moth.")

    return moth_phase_testers, moth_not_phase_testers

def assign_attributes(mi_devices, moth_phase_testers, moth_not_phase_testers):

    print('---')
    print('Updating attributes in MobileIron')

    tag_success = 0
    tag_failed = 0
    attribute_results = []
    add_to_preprod_count = 0
    remove_from_preprod_count = 0
    #Iterate through mi_devices, filter for macs and compare serials with moth to determine phase testing. Add or remove attribute as needed
    for i in mi_devices:
        if i ['platformType'] in ('OSX'):
            na = i['customAttributes']['attrs']
            if i['serialNumber'] in moth_phase_testers:
                if 'releasechannel' in na and 'PreProd' in na['releasechannel']:
                    continue
                else:
                    na['releasechannel'] = ['PreProd']
                    add_to_preprod_count += 1
                    response = SESSION.put(f"{MODIFY_DEVICE_ATTRIBUTE}/{i['id']}/customattributes", json={"attrs":na})
                    if response.status_code == 200:
                        tag_success += 1
                    else:
                        tag_failed += 1
                    attribute_results.append(i)
                    attribute_results[attribute_results.index(i)].update({'action_taken': 'add PreProd', 'action_result': response.status_code})
            if i['serialNumber'] in moth_not_phase_testers:
                if 'releasechannel' in na and 'PreProd' in na['releasechannel']:
                    na = {'ids':[str(i['id'])], 'attrKeys':['releasechannel']}
                    remove_from_preprod_count += 1
                    response2 = SESSION.delete(f"{MODIFY_DEVICE_ATTRIBUTE}/customattributes", json=na)
                    if response2.status_code == 200:
                        tag_success += 1
                    else:
                        tag_failed += 1
                    attribute_results.append(i)
                    attribute_results[attribute_results.index(i)].update({'action_taken': 'remove PreProd', 'action_result': response2.status_code})
    

    if add_to_preprod_count == 0:
        if remove_from_preprod_count == 0:
            print (f"No changes necessary")

    if add_to_preprod_count > 0:
        print (f"Attempted to add PreProd attribute to {add_to_preprod_count} devices")

    if remove_from_preprod_count > 0:
        print (f"Attempted to remove PreProd attribute from {remove_from_preprod_count} devices")

    if tag_success > 0:
        print (f"{tag_success} actions were successful.")

    if tag_failed > 0:
        print (f"{tag_failed} actions were not successful.")

    return attribute_results

def export_results(attribute_results):
    print ("---")
    print ("Exporting results")

    csv_columns = ['uid', 'id', 'deviceModel', 'prettyModel', 'deviceName', 'serialNumber', 'action_taken', 'action_result']

    if len(attribute_results) > 0:
        
        with open(SCRIPT_RESULTS / f"moth_phase_tester_update_{TODAY}.csv", 'w', newline='') as outFile:
            writer = csv.DictWriter(outFile, fieldnames=csv_columns)
            writer.writeheader()
            for i in attribute_results:
                writer.writerow({'uid': i['uid'], 'id':i['id'], 'deviceModel':i['deviceModel'], 'prettyModel':i['prettyModel'], 'deviceName':i['deviceName'], 'serialNumber':i['serialNumber'], 'action_taken':i['action_taken'], 'action_result':i['action_result']})
    

#Run that ish
if __name__ == '__main__':
    main()


