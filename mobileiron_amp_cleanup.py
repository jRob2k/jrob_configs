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

TODAY = datetime.today().strftime ('%b-%d-%Y')
TODAY_MONTH = datetime.today().strftime ('%h_%Y')

CREDENTIALS = pathlib.Path.cwd().joinpath('Files', 'Credentials')

DATA_SOURCES = pathlib.Path.cwd().joinpath('Files', 'Data Sources')

SCRIPT_RESULTS = pathlib.Path.cwd().joinpath('Files', 'Script Results', TODAY_MONTH, 'Details')
pathlib.Path(SCRIPT_RESULTS).mkdir(parents=True, exist_ok=True)

#Main Function - Sets up the session to use the APIs, then runs the functions to grab spaces, grab devices, evaluate devices and then take action.

def main():

    # sets up the session using credentials from the credentials.json file
    auth = json.loads((CREDENTIALS / 'mi_credentials.json').read_text())
    SESSION.auth = (auth['user'], auth['pass'])
    
    #function gets spaces
    spaces = (get_spaces())

    #function gets all machines
    mi_devices, mi_devices_with_amp = (get_devices(spaces))

    #function evaluates machines
    devices_to_change = (evaluate_devices(mi_devices, mi_devices_with_amp))

    #function changes devices
    change_results = (change_devices(devices_to_change))

    #function exports change results to a csv
    export_results(change_results)
    
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
        # Exclude Shared devices for Production
        if i['name'] not in ('Shared Devices', 'macOS'):
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
    mi_devices_with_amp = []

    #Iterates through spaces and gets all devices with amp installed
    for i in spaces:
        space_Name = i['name']
        query_dict = {
            'bundleId': 'com.cisco.amp',
            'type': 'APP_INVENTORY',
            'platformType': 'ANDROID',
            'rows': 500, 
            'start': 0,
            'dmPartitionId': i['id']
        }
        query = urllib.parse.urlencode(query_dict)
        response = SESSION.get(f"{DEVICE_APP}{query}")
        if response.status_code != 200:
            continue
        results = response.json()

        bar_amp_devices = Bar(f'{space_Name} - AMP Devices', max=response.json()['result']['totalCount'], suffix='%(index)d')

        for i2 in results["result"]["searchResults"]:
            mi_devices_with_amp.append(i2['id'])
            bar_amp_devices.next()

        count = results["result"]["totalCount"] // query_dict["rows"]
        if results["result"]["totalCount"] % query_dict["rows"]:
            count += 1
        for _ in range(count):
            query_dict["start"] = results["result"]["offset"] + query_dict["rows"]
            query = urllib.parse.urlencode(query_dict)
            response = SESSION.get(f"{DEVICE_APP}{query}")
            if response.status_code != 200:
                continue
            results = response.json()
            
            for i2 in results["result"]["searchResults"]:
                mi_devices_with_amp.append(i2['id'])
                bar_amp_devices.next()
        bar_amp_devices.finish()

    #Iterates through all spaces and gets all devices.
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
        
        bar_devices = Bar(f'{space_Name} - Devices', max=response.json()['result']['totalCount'], suffix='%(index)d')
    

        for i2 in results["result"]["searchResults"]:
            mi_devices.append(i2)
            mi_devices[mi_devices.index(i2)].update({'space_Name': i['name'], 'space_Id': i['id'], 'space_DeviceCount': i['deviceCount']})
            bar_devices.next()

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
                bar_devices.next()
        bar_devices.finish()
    
    print(f"Retrieved {len(mi_devices)} devices from {len(spaces)} Spaces.")
    print(f"Retrieved {len(mi_devices_with_amp)} devices with AMP installed from {len(spaces)} Spaces.")
    
    return mi_devices, mi_devices_with_amp

def evaluate_devices(mi_devices, mi_devices_with_amp):
    
    devices_to_change = []
    #Iterates through Android MI Devices. If the AMP activation policy has been triggered, flags them to add the exclusion attribute (active).
    #If the AMP activation policy is not active and the attribute has been previously set, changes it so the policy can pick it up again.
    
    for i in mi_devices:
        if i['platformType'] == 'ANDROID':
            #Attempts to get the cisco amp attribute if it exists
            try:
                custom_ciscoamp = i['customAttributes']['attrs']['custom_ciscoamp']
            except:
                custom_ciscoamp = []
                pass
            #If the AMP policy has been triggered and the attribute has been set, skip. If it hasn't been set, flag it to be set.
            if '[Production] Cisco Amp Activation' in i['violatedPolicies']:
                if 'active' in custom_ciscoamp:
                    pass
                else:
                    devices_to_change.append(i)
                    devices_to_change[devices_to_change.index(i)].update({'action': 'add_amp_attribute'}) 
            if '[Dev] Cisco Amp Activation' in i['violatedPolicies']:
                if 'active' in custom_ciscoamp:
                    pass
                else:
                    devices_to_change.append(i)
                    devices_to_change[devices_to_change.index(i)].update({'action': 'add_amp_attribute'}) 
            else:
                #If the AMP policy is not triggered and amp isn't installed and if the attribute is set, remove/change it.
                if 'active' in custom_ciscoamp:
                    if i['id'] in mi_devices_with_amp:
                        pass
                    else:
                        devices_to_change.append(i)
                        devices_to_change[devices_to_change.index(i)].update({'action': 'remove_amp_attribute'})
    print (f"Found {len(devices_to_change)} devices to update.")
 
    return devices_to_change

def change_devices(devices_to_change):
    
    change_results = []
    tag_success = 0
    tag_failed = 0

    for i in devices_to_change:
        action = i['action']
        mi_id = i['id']

        attributes = {}

        #Pulls existing device attributes if they exist
        if 'attrs' in i['customAttributes']:
            attributes.update (i['customAttributes']['attrs'])
        
        #if AMP attribute is to be "removed" set to "inactive"
        if action == 'remove_amp_attribute':
            attributes.update ({'custom_ciscoamp':['removed']})
        
        #if AMP attribute is to be "added" set to "active"
        elif action == 'add_amp_attribute':
            attributes.update ({'custom_ciscoamp':['active']})

        #Use API to make attribute changes
        print (attributes)
        response_patch = SESSION.put(f"{MODIFY_DEVICE_ATTRIBUTE}/{mi_id}/customattributes", json={'attrs':attributes})
        if response_patch.status_code == 200:
            tag_success += 1
        else:
            tag_failed += 1
        change_results.append({'id': i['id'], 'clientDeviceIdentifier': i['clientDeviceIdentifier'], 'space_Id':i['space_Id'], 'change_action': i['action'], 'status_code':response_patch.status_code})

    if tag_success > 0:
        print (f"Successfully updated attributes for {tag_success} devices.")
    if tag_failed > 0:
        print (f"Failed to update attributes for {tag_failed} devices.")

    return change_results
def export_results(change_results):
    
    print("---")
    print("Exporting AMP cleanup results")
    
    csv_columns = ['id', 'clientDeviceIdentifier', 'space_Id', 'change_action', 'status_code']
    
    if len(change_results) == 0:
        print("No changes made. No data to export")

    else:
        with open(SCRIPT_RESULTS / f'AMP_Cleanup_{TODAY}.csv', 'w', newline='') as outFile:
            writer = csv.DictWriter(outFile, fieldnames=csv_columns)
            writer.writeheader()
            for i in change_results:
                writer.writerow({'id':i['id'], 'cleanDeviceIdentifier':i['id'], 'space_Id':i['space_Id'], 'change_action':i['change_action'], 'status_code':i['status_code']})
if __name__ == '__main__':
    main()
