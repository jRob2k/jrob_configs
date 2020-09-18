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
DEVICE = f"{API_BASE}/device"
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
DEVICE_APP = f"{API_BASE}/device?q=&fq=version!%3D%270%27+AND+"

SESSION = requests.Session()
MOTH_SESSION = requests.Session()

#Moth api call to get a list of all machines
MOTH_MACHINES = "https://moth.na.sas.com/api/machines/"

TODAY = datetime.today().strftime ('%b-%d-%Y')
TODAY_MONTH = datetime.today().strftime ('%h_%Y')

CREDENTIALS = pathlib.Path.cwd().joinpath('Files', 'Credentials')

DATA_SOURCES = pathlib.Path.cwd().joinpath('Files', 'Data Sources')

MOTH_CERT = pathlib.Path.cwd().joinpath('Files', 'Certificates', 'sas_certs.pem')

SCRIPT_RESULTS = pathlib.Path.cwd().joinpath('Files', 'Script Results', TODAY_MONTH, 'Details')
pathlib.Path(SCRIPT_RESULTS).mkdir(parents=True, exist_ok=True)

#Main Function - Sets up the session to use the APIs, then runs the functions to grab spaces, grab devices, evaluate devices and then take action.

def main():

    # sets up the session using credentials from the credentials.json file
    auth = json.loads((CREDENTIALS / 'mi_credentials.json').read_text())
    SESSION.auth = (auth['user'], auth['pass'])

    moth_auth = json.loads((CREDENTIALS / 'moth_credentials.json').read_text())
    MOTH_SESSION.auth = (moth_auth['user'], moth_auth['pass'])
    MOTH_SESSION.verify = MOTH_CERT

    #function gets spaces
    spaces = (get_spaces())

    #function gets all machines
    mi_devices = get_devices(spaces)

    #function gets all macs from moth
    moth_devices, moth_serials = get_moth_devices()

    #function adds a MobileIron attribute to devices not in Moth
    ownership_results = update_mac_ownership(mi_devices, moth_serials)

    #function exports change results to a csv
    export_results(ownership_results)

def get_spaces():

    print(f"---{TODAY}---")
    print("---")
    print("Getting Spaces from MobileIron")

    spaces = []
    response = SESSION.get(FIND_SPACES)
    if response.status_code != 200:
        print("didn't work")


    bar_spaces = Bar('Spaces', max=response.json()['result']['totalCount'], suffix='%(index)d')

    for i in response.json()["result"]["searchResults"]:
        #Limit to macOS and Bleeding Edge Spaces
        if i['name'] in ('macOS', 'Bleeding Edge'):
        # Limit spaces for testing
        # if i['name'] in ('Bleeding Edge'):
            spaces.append(i)
            bar_spaces.next()
        bar_spaces.next()
    bar_spaces.finish()

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

        bar_devices = Bar(f'{space_Name} Devices', max=response.json()['result']['totalCount'], suffix='%(index)d')
        #Grabs device info from MobileIron, then appends space info
        for i2 in results["result"]["searchResults"]:
            mi_devices.append(i2)                
            if response.status_code !=200:
                continue
            mi_devices[mi_devices.index(i2)].update({'space_Name': i['name'], 'space_Id': i['id']})
            bar_devices.next()

        #Repeating for each page
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
                if response.status_code !=200:
                    continue
                mi_devices[mi_devices.index(i2)].update({'space_Name': i['name'], 'space_Id': i['id']})
                bar_devices.next()

        bar_devices.finish()

    print(f"Retrieved {len(mi_devices)} devices from {len(spaces)} Spaces.")

    return mi_devices

def get_moth_devices():
    print("---")
    print(f"Getting Devices from Moth.")

    moth_devices = []
    moth_serials = []

    go = 'go'
    moth_machines = MOTH_MACHINES

    response = MOTH_SESSION.get(moth_machines)
    results = response.json()

    #Iterate through pages grabbing all devices. Stops when the next page is "None"
    while go == 'go':
        for i in results['results']:
            moth_devices.append(i)
            moth_serials.append(i['serial'])
        if results['next'] != None:
            moth_machines = results['next']
            response = MOTH_SESSION.get(moth_machines)
            results = response.json()
        else:
            go = 'stop'

    print(f"Found {len(moth_devices)} machines in Moth.")

    return moth_devices, moth_serials 

def update_mac_ownership(mi_devices, moth_serials):
    print('---')
    print('Updating mac Ownership in MobileIron')

    tag_success = 0
    tag_failed = 0
    in_moth_count = 0
    not_in_moth_count = 0
    ownership_results = []

    for i in mi_devices:
        #Filter for macs
        if i['platformType'] in ('OSX'):
            new_attributes = i['customAttributes']['attrs']
            if i['serialNumber'] in moth_serials:
                #Increase count
                in_moth_count += 1
                #Check DEP and SAS_Owned attribute
                if 'dep' in new_attributes and 'Yes' in new_attributes['dep']:
                    continue
                if 'sas_owned' in new_attributes and 'Yes' in new_attributes['sas_owned']:
                    continue
                ##Write the attribute
                new_attributes['sas_owned'] = ['Yes']
                response_a = SESSION.put(f"{MODIFY_DEVICE_ATTRIBUTE}/{i['id']}/customattributes", json={"attrs":new_attributes})
                ownership_results.append(i)
                if response_a.status_code == 200:
                    tag_success += 1
                else:
                    tag_failed += 1
                ownership_results[ownership_results.index(i)].update({'in_Moth': 'yes', 'attribute_Update_Results': response_a.status_code})
            #Set attribute if device isn't in MOTH
            else:
                #Increase count
                not_in_moth_count += 1
                #Check DEP and SAS_Owned attribute
                if 'dep' in new_attributes and 'Yes' in new_attributes['dep']:
                    continue
                ##Write the attribute
                new_attributes['sas_owned'] = ['No']
                response_a = SESSION.put(f"{MODIFY_DEVICE_ATTRIBUTE}/{i['id']}/customattributes", json={"attrs":new_attributes})
                ownership_results.append(i)
                if response_a.status_code == 200:
                    tag_success += 1
                else:
                    tag_failed += 1
                ownership_results[ownership_results.index(i)].update({'in_Moth': 'no', 'attribute_Update_Results': response_a.status_code})

        #Skip non-macs
        else:
            continue
    if in_moth_count > 0:
        print (f"Found {in_moth_count} MobileIron macs in Moth.")
    if not_in_moth_count > 0:
        print (f"Found {not_in_moth_count} MobileIron macs NOT in Moth.")

    if tag_success > 0:
        print (f"Successfully updated attributes for {tag_success} devices.")

    if tag_failed > 0:
        print (f"Failed to update attributes for {tag_failed} devices.")

    return ownership_results

def export_results(ownership_results):

    print("---")
    print("Exporting macOS Ownership results")

    csv_columns = ['uid', 'id', 'deviceModel', 'prettyModel', 'deviceName', 'serialNumber', 'in_Moth', 'attribute_Update_Results']

    if len(ownership_results) == 0:
        print("No changes made. No data to export")

    else:
        with open(SCRIPT_RESULTS / f'macOS_Ownership_{TODAY}.csv', 'w', newline='') as outFile:
            writer = csv.DictWriter(outFile, fieldnames=csv_columns)
            writer.writeheader()
            for i in ownership_results:
                writer.writerow({'uid':i['uid'], 'id':i['id'], 'deviceModel':i['deviceModel'], 'prettyModel':i['prettyModel'], 'deviceName':i['deviceName'], 'serialNumber':i['serialNumber'], 'in_Moth':i['in_Moth'], 'attribute_Update_Results':i[attribute_Update_Results]})

if __name__ == '__main__':
    main()
