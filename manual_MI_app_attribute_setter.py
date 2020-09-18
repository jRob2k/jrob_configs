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

CREDENTIALS = pathlib.Path.cwd().joinpath('Files', 'Credentials')

DATA_SOURCES = pathlib.Path.cwd().joinpath('Files', 'Data Sources')

SCRIPT_RESULTS = pathlib.Path.cwd().joinpath('Files', 'Script Results')

APP = input("What app are you looking for : ")
SAME = input("Do the iOS and Android bundleIDs match Y/N: ")

if SAME.upper() in ("Y", "YES"):
    BUNDLEID = input ("Enter the BundleID : ")
    IOS_APP = BUNDLEID
    ANDROID_APP = BUNDLEID
else:
    IOS_APP = input("Enter the iOS BundleID : ")
    ANDROID_APP = input("Enter the Android BundleID : ")

SET_ATTRIBUTE = input("Would you like to add a device attribute Y/N : ")

if SET_ATTRIBUTE.upper() in ("Y", "YES"):
    ATTRIBUTE_KEY = input("Enter the existing device attribute key : ")
    ATTRIBUTE_VALUE = input("Enter the desired attribute value : ")

else:
    SET_ATTRIBUTE = "NO"
#Main Function - Sets up the session to use the APIs, then runs the functions to grab spaces, grab devices, evaluate devices and then take action.

def main():
    
# sets up the session using credentials from the credentials.json file
    auth = json.loads((CREDENTIALS / 'credentials.json').read_text())
    SESSION.auth = (auth['user'], auth['pass'])
    
    #function gets spaces
    spaces = (get_spaces())

    #function gets all machines
    mi_device_with_app = (get_devices(spaces))

    #function adds attributes to targeted device
    results = (set_attributes(mi_device_with_app))

    #function exports inventory results to a csv
    export_results(mi_device_with_app)
    
def get_spaces():

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
    print(f"Getting Devices with {APP} installed from {len(spaces)} Space(s).")
    
    mi_device_with_app = []
    ios_total = 0
    android_total = 0

    #Iterates through spaces and gets all iOS devices with the targeted app installed
    for i in spaces:
        space_Name = i['name']
        query_dict = {
            'bundleId': IOS_APP,
            'type': 'APP_INVENTORY',
            'platformType': 'IOS',
            'rows': 500, 
            'start': 0,
            'dmPartitionId': i['id']
        }
        query = urllib.parse.urlencode(query_dict)
        response = SESSION.get(f"{DEVICE_APP}{query}")
        if response.status_code != 200:
            continue
        results = response.json()

        bar_app_devices = Bar(f'{space_Name} - iOS - {APP}', max=response.json()['result']['totalCount'], suffix='%(index)d')

        for i2 in results["result"]["searchResults"]:
            mi_device_with_app.append(i2)
            ios_total += 1
            bar_app_devices.next()

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
                mi_device_with_app.append(i2)
                ios_total += 1
                bar_app_devices.next()
        bar_app_devices.finish()
    print(f"Retrieved {ios_total} iOS devices with {APP} installed from {len(spaces)} Spaces.")
    
    #Iterates through spaces and gets all android devices with the targeted app installed
    for i in spaces:
        space_Name = i['name']
        query_dict = {
            'bundleId': ANDROID_APP,
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

        bar_app_devices = Bar(f'{space_Name} - Android - {APP}', max=response.json()['result']['totalCount'], suffix='%(index)d')

        for i2 in results["result"]["searchResults"]:
            mi_device_with_app.append(i2)
            android_total += 1
            bar_app_devices.next()

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
                mi_device_with_app.append(i2)
                android_total += 1
                bar_app_devices.next()
        bar_app_devices.finish()
    print(f"Retrieved {android_total} Android devices with {APP} installed from {len(spaces)} Spaces.")

    return mi_device_with_app

def set_attributes(mi_device_with_app):
    print ("---")
    results = []
    tag_success = 0
    tag_failed = 0

    if SET_ATTRIBUTE == "NO":
        print ("No attributes to change")
    
    else:
        bar_tagging = Bar('Updating device attributes', max=len(mi_device_with_app), suffix='%(index)d')

        for i in mi_device_with_app:
            attributes = {ATTRIBUTE_KEY:[ATTRIBUTE_VALUE]}
            id = i['id']

            #Get existing attributes if they exist
            try:
                if "attrs" in i['customAttributes']:
                    attributes.update (i['customAttributes']['attrs'])
            except:
                pass

            #Patch new and existing attributes
            response_patch = SESSION.put(f"{MODIFY_DEVICE_ATTRIBUTE}/{id}/customattributes", json={"attrs":attributes})
            if response_patch.status_code == 200:
                tag_success += 1
            else:
                tag_failed += 1
            results.append({'id': i['id'], 'clientDeviceIdentifier': i['clientDeviceIdentifier'], 'status_code':response_patch.status_code})
            bar_tagging.next()
        bar_tagging.finish()

    if tag_success > 0:
        print (f"Successful Attribute Updates - {tag_success}/{len(results)}")
    
    if tag_failed > 0:
        print (f"Failed Attribute Updates - {tag_failed}/{len(results)}")
    return results

def export_results(mi_device_with_app):
    
    print("---")
    print("Exporting app inventory results")
    
    csv_columns = ['id', 'deviceModel', 'deviceName', 'platformType', 'platformVersion', 'registrationState', 'emailAddress', 'serialNumber']
    
    if len(mi_device_with_app) > 0:
        
        with open(SCRIPT_RESULTS / f'{APP}_Inventory_{TODAY}.csv', 'w', newline='') as outFile:
            writer = csv.DictWriter(outFile, fieldnames=csv_columns)
            writer.writeheader()
            for i in mi_device_with_app:
                writer.writerow({'id':i['id'], 'deviceModel':i['deviceModel'], 'platformType':i['platformType'], 'platformVersion':i['platformVersion'], 'registrationState':i['registrationState'], 'emailAddress':i['emailAddress'], 'serialNumber':i['serialNumber']})
if __name__ == '__main__':
    main()
