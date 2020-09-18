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


SESSION = requests.Session()

TODAY = datetime.today().strftime ('%b-%d-%Y')

CREDENTIALS = pathlib.Path.cwd().joinpath('Files', 'Credentials')

DATA_SOURCES = pathlib.Path.cwd().joinpath('Files', 'Data Sources')

SCRIPT_RESULTS = pathlib.Path.cwd().joinpath('Files', 'Script Results')

#Main Function - Set setup the session to use the API

# TODO: Add method to check last time a function was run (i.e. config check) and skip if within a specific time range.

# TODO: Add Ownership workaround (with local file import per inc0311091)



def main():

    # sets up the session using credentials from the credentials.json file
    auth = json.loads((CREDENTIALS / 'credentials.json').read_text())
    SESSION.auth = (auth['user'], auth['pass'])

    #Prerequisites

    spaces = get_spaces()
    mi_devices = (get_devices(spaces))
    mi_device_configs = (get_configs(mi_devices))

    #Health Check - macOS
    config_clear_results = (clear_configs(mi_device_configs))
    export_results(config_clear_results)


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
        if i["name"] not in ("Shared Devices"):
        #Limit spaces for testing
        # if i['name'] in ('Bleeding Edge'):
            spaces.append(i)
            bar_spaces.next()
        bar_spaces.next()
    bar_spaces.finish()

    print(f"Retrieved {len(spaces)} Spaces (Shared Devices is excluded).")

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

def get_configs(mi_devices):

    print('---')
    print('Getting Configs for Active macOS Devices')

    mi_device_configs = []

    bar_get_configs = Bar('Working...', suffix='%(index)d')

    for i in mi_devices:
        if str(i['platformType']).upper() in ('OSX') and i['lastCheckin'] != None and str(i['registrationState']).upper() in ('ACTIVE'):

            if datetime.today() - datetime.fromtimestamp(i['lastCheckin']/1000) > timedelta(days=30):
                continue
            else:

                mi_device_configs.append(i)
                response = SESSION.get(f"{API_BASE}/device/{i['id']}/configs")
                if response.status_code !=200:
                    continue
                configs = response.json()
                mi_device_configs[mi_device_configs.index(i)].update({'configs': configs['result']['searchResults']})
            bar_get_configs.next()
    bar_get_configs.finish()

    if len(mi_device_configs) > 0:
        print (f"Retrieved {len(mi_device_configs)} macOS devices and appended config status.")

    return mi_device_configs

def clear_configs(mi_device_configs):
        
    print('---')
    print("Sending the 'Clear Configuration' command to pending configs")

    config_clear_results = []
    count_success = 0
    count_failed = 0

    bar_configs = Bar('Sending...', suffix='%(index)d')

    # Iterate through devices in mi_devices
    for i in mi_device_configs:
        #Grab config data and iterate through each

        stuck_configs = [] 

        for i2 in i['configs']:
        # Filter out functioning config statuses
            if str.upper(i2['status']) not in ('INSTALLED', 'ACTIVE', 'UNINSTALLED'):
            #sends a clearconfigerror message to pending and error configs
                response = SESSION.put(f"{API_BASE}/device/clearConfigError?deviceId={i['id']}&policyUuid={i2['id']}")
                
                if response.status_code !=200:
                    count_failed +=1
                else:
                    count_success +=1
                #Add non active configs to stuck config list of dictionaries
                stuck_configs.append({'name':i2['name'], 'status':i2['status'], 'clear_config_results':response.status_code})
        # Add device info to new object and append stuck configs
        if len(stuck_configs) > 0:
            config_clear_results.append(i)
            config_clear_results[config_clear_results.index(i)].update({'stuck_configs':stuck_configs})
            config_clear_results[config_clear_results.index(i)].update({'total_stuck_configs':len(stuck_configs)})
        bar_configs.next()
    bar_configs.finish()

    if len(config_clear_results) > 0:
        print (f"Sent 'Clear Configuration' command to {len(config_clear_results)} devices.")

    if count_failed > 0:
        print (f"Some 'Clear Configuration' commands failed. Check output.")

    return config_clear_results

def export_results(config_clear_results):
    
    print("---")
    print("Exporting results")

    csv_columns = ['id', 'mi_Last_Checkin', 'deviceModel', 'prettyModel', 'deviceName', 'serialNumber', 'uid', 'total_stuck_configs', 'stuck_configs']

    if len(config_clear_results) > 0:
        with open(SCRIPT_RESULTS / f'clear_config_results_{TODAY}.csv', 'w', newline='') as outFile:
            writer = csv.DictWriter(outFile, fieldnames=csv_columns)
            writer.writeheader()
            for i in config_clear_results:
                    writer.writerow({'id':i['id'], 'mi_Last_Checkin':datetime.today() - datetime.fromtimestamp(i['lastCheckin']/1000), 'deviceModel':i['deviceModel'], 'prettyModel':i['prettyModel'], 'deviceName':i['deviceName'], 'serialNumber':i['serialNumber'], 'uid':i['serialNumber'], 'total_stuck_configs':i['total_stuck_configs'], 'stuck_configs':i['stuck_configs']})

    # if len(config_clear_start) > 0:
    #     with open(SCRIPT_RESULTS / f'clear_config_start_{TODAY}.csv', 'w', newline='') as outFile:
    #         writer = csv.DictWriter(outFile, fieldnames=csv_columns)
    #         writer.writeheader()
    #         for i in config_clear_start:
    #                 writer.writerow({'id':i['id'], 'deviceModel':i['deviceModel'], 'prettyModel':i['prettyModel'], 'deviceName':i['deviceName'], 'serialNumber':i['serialNumber'], 'uid':i['serialNumber'], 'stuck_configs':i['stuck_configs']})



#Run that ish
if __name__ == '__main__':
    main()
