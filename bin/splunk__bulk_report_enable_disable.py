#!/usr/bin/env python3

## Imports
import argparse
import csv
import re
import requests
import shutil
import splunklib.client as splunkclient
import splunklib.results as results
import sys
import urllib.parse
from collections import OrderedDict
from datetime import datetime
from tempfile import NamedTemporaryFile
from time import sleep
from urllib3.exceptions import InsecureRequestWarning

# disable certificate verification errors on requests (for when running against a local splunk instance or an instance that does not have updated certificates on Splunk Management port. 
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Login to Splunk 
def splunk_login(USERNAME, PASSWORD, URI):
    HOST, PORT = URI.split(':')
    try:
        service = splunkclient.connect(host=HOST, port=PORT, username=USERNAME, password=PASSWORD)
        return service
    except Exception as e:
        print(e)
        print( "Failed login to Splunk management port using username: " + username )
        quit()

# List all apps in the Splunk instance
def list_apps(IGNORE_APPS, SPLUNKSERVICE):
    
    print ("Retrieving list of Apps from Splunk")
    IGNORELIST = APPLIST = []
    
    if IGNORE_APPS is not None:
        IGNORELIST = IGNORE_APPS.split(',')
    
    # added 2 second sleep...  without it...  splunkservice.apps was throwing an error on binding.py...?   not sure why
    sleep(3)
    
    for APP in SPLUNKSERVICE.apps:
        if not APP.name in IGNORELIST:
            APPLIST.append(APP.name)
    return APPLIST                
    
# List all the searches in the app that are enabled and that have an active schedule
def list_searches(APP, SPLUNKSERVICE):
    
    print ("    Looping through searches in app: " + APP + "...")
    SEARCHSTRING = "| rest /servicesNS/-/" + APP + "/saved/searches | search is_scheduled=1 disabled=0 | table id title cron_schedule disabled owner | rex field=id \"^https:\/\/[^:]+:\d+(?<searchnamespace>.+)$\" | rex field=id \"(?<appname>[^\/]+)\/[^\/]+\/[^\/]+\/[^\/]+$\" | search appname=" + APP + "| fields - id"
    SEARCHLIST = []
    JOBS = SPLUNKSERVICE.jobs
    kwargs_normalsearch = {"exec_mode": "normal"}
    SEARCHLISTQUERY = JOBS.create(SEARCHSTRING, **kwargs_normalsearch)
    
    while True:
        while not SEARCHLISTQUERY.is_ready():
            pass

        stats = {"isDone": SEARCHLISTQUERY["isDone"],
                 "doneProgress": float(SEARCHLISTQUERY["doneProgress"])*100,
                 "resultCount": int(SEARCHLISTQUERY["resultCount"])}
        
        status = ("        %(doneProgress)03.1f%%  %(resultCount)d enabled searches with schedules ") % stats
    
        sys.stdout.write(status)
        sys.stdout.flush()
        if stats["isDone"] == "1":
            sys.stdout.write("\n")
            break
        sleep(2)
    
    for searchresult in results.ResultsReader(SEARCHLISTQUERY.results()):
        searchresult["app"] = APP
        SEARCHLIST.append(dict(searchresult))
    
    return SEARCHLIST    

# Send a post request to the rest API to disable the search
def disable_search(SEARCHDICT, SPLUNKSERVICE, SPLUNKMGMT, USERNAME, PASSWORD):
    try:
        print ("            - Disabling search: " + SEARCHDICT["app"] + " : " + SEARCHDICT["title"])
        url = "https://" + SPLUNKMGMT + "/servicesNS/nobody/" + SEARCHDICT["app"] + "/saved/searches/" + urllib.parse.quote_plus(SEARCHDICT["title"]) + "/disable"
        disable_search_request = requests.post(url, auth = (USERNAME, PASSWORD), verify=False)
        if disable_search_request.status_code == 200:
            return True
        else:
            print("                Error disabling search.  Return code: " + disable_search_request.status_code)
            return False
                
    except Exception as ex:
        print("                Failed to disable search: " + SEARCHDICT["app"] + ":" + SEARCHDICT["title"] + "\n\n    " + str(ex))
        return False

# Send a post request to the rest API to enable the search
def enable_search(SEARCHDICT, SPLUNKSERVICE, SPLUNKMGMT, USERNAME, PASSWORD):
    try:
        print ("            - Enabling search: " + SEARCHDICT["app"] + " : " + SEARCHDICT["searchname"])
        
        url = "https://" + SPLUNKMGMT + "/servicesNS/nobody/" + SEARCHDICT["app"] + "/saved/searches/" + urllib.parse.quote_plus(SEARCHDICT["searchname"]) + "/disable"
        disable_search_request = requests.post(url, auth = (USERNAME, PASSWORD), verify=False)
        if disable_search_request.status_code == 200:
            return True
        else:
            print("                Error enabling search.  Return code: " + disable_search_request.status_code)
            return False
                
    except Exception as ex:
        print("                Failed to enable search: " + SEARCHDICT["app"] + ":" + SEARCHDICT["searchname"] + "\n\n    " + ex)
        return False

# Clear the csv file of data to start new. 
def clear_csv_file(csvlist):
    try:
        csvfile = open(csvlist, "w")
        csvfile.write("app,searchname,searchnamespace,cron_schedule,action,actiontime\n")
        csvfile.close
    except Exception as ex:
        print("ERROR:: cannot clear csvfile " + csvlist)
        quit()

# Write an entry to the CSV of a disabled or listed search
def write_to_csv(SEARCHDICT, ACTION, csvlist):
    try:
        csvfile = open(csvlist, "a")
        outputstring = SEARCHDICT["app"] + ",\"" + SEARCHDICT["title"] + "\"," + SEARCHDICT["searchnamespace"] + "," + SEARCHDICT["cron_schedule"] + "," + ACTION + "," + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") 
        csvfile.write(outputstring.replace('"', '""') + "\n")
    
    except Exception as ex:
        print("ERROR:: Unable to write data to " + csvlist + " for search " + SEARCHDICT["app"] + ":" + SEARCHDICT["title"] + "\n\n    " + ex)
        quit()
    
# Update the csv after a search has been reenabled.     
def update_csv(SEARCHDICT, ACTION, csvlist):
    try:
        fields = ["app", "searchname", "searchnamespace", "cron_schedule", "action", "actiontime"]
        tempfile = NamedTemporaryFile(mode="w", delete=False)
        with open(csvlist, "r") as csvfile, tempfile:
            reader = csv.DictReader(csvfile, fieldnames=fields)
            writer = csv.DictWriter(tempfile, fieldnames=fields)
            for row in reader:
                if row['searchname'] == SEARCHDICT["searchname"]:
                    outrow = {"app" : row["app"], "searchname": row["searchname"], "cron_schedule": row["cron_schedule"], "action": "enabled", "actiontime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S") }
                else:
                    outrow = row
                writer.writerow(row)
        shutil.move(tempfile.name, csvlist)
    except Exception as ex:
        print("error updating csv: \n    " + ex)

# opens the CSV and returns a dict with the contents
def read_from_csv(csvlist):
    try:
        with open(csvlist, "r") as inputfile:
            csvdict = [{k: str(v) for k, v in row.items()}
                for row in csv.DictReader(inputfile, skipinitialspace=True)]
        return csvdict

    except Exception as ex:
        print("ERROR: Unable to open CSV file at " + csvlist + "\n\n    " + ex)
        quit()

# match the management uri format
def splunk_mgmt_type(arg_value, pat=re.compile(r"^([\w\-]+(\.)?([\w\-]+)?(\.)?(\w+)?|\d+\.\d+\.\d+\.\d+):\d+$")):
    if not pat.match(arg_value):
        raise argparse.ArgumentTypeError
    return arg_value

class ARGUMENTS:
    pass

if __name__ == '__main__':
    
    # Parse and validate command line arguments
    arguments = ARGUMENTS()
    parser = argparse.ArgumentParser(description="Script to disable / reenable all saved searches that are enabled and have an active schedule")
    parser.add_argument('-r', '--runtype', type=str, choices=['disable', 'enable', 'listonly'], help="one of disable | enable | listonly", required=True)
    parser.add_argument('-s', '--splunkmgmt', type=splunk_mgmt_type, help="the management port of the target Splunk instance in format thehost.splunkcloud.com:8089", required=True)
    parser.add_argument('-u', '--username', type=str, default="admin", help="username of an admin/sc_admin role user on the target Splunk instance")
    parser.add_argument('-p', '--password', type=str, default="changeme", help="password for the user")
    parser.add_argument('-c', '--csvlist', type=str, default="./searchlist/searchlist.csv", help="location of the searchlist.csv to be populated / parsed")
    parser.add_argument('-i', '--ignoreapps', type=str, help="comma separated list of apps to be ignored in the run in format app1,app2,app3")
    args = parser.parse_args(namespace=arguments)
    print("Starting run.   RUNTYPE: " + arguments.runtype)
    
    # Create the splunklib service object
    splunkservice = splunk_login(arguments.username, arguments.password, arguments.splunkmgmt) 
    
    # listonly or disable run types
    if arguments.runtype == "disable" or arguments.runtype == "listonly":
        
        # Clear the CSV file before starting
        clear_csv_file(arguments.csvlist)
        
        #Retrieve a list of apps in the splunk environment
        applist = list_apps(arguments.ignoreapps, splunkservice)
        
        #Loop through each of the apps
        for app in applist:
            
            #Retrieve a list of enabled searches contained in the app with a schedule
            searchlist = list_searches(app, splunkservice)
            
            # loop through each search
            for searchdict in searchlist:
                
                if arguments.runtype == "disable":
                    if disable_search(searchdict, splunkservice, arguments.splunkmgmt, arguments.username, arguments.password):
                        write_to_csv(searchdict, "disable", arguments.csvlist)
                    else:
                        write_to_csv(searchdict, "FAILED", arguments.csvlist)
                elif arguments.runtype=="listonly":
                    write_to_csv(searchdict, "listonly", arguments.csvlist)
    
    # enable run type
    elif(arguments.runtype == "enable"):
        
        runlist = read_from_csv(arguments.csvlist)
        for enablesearchrow in runlist:
            if enable_search(enablesearchrow, splunkservice, arguments.splunkmgmt, arguments.username, arguments.password):
                update_csv(enablesearchrow, "enable", arguments.csvlist)
                
                
    print ("Done!")