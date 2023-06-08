# splunk_enable_disable_saved_searches.py 

## Synopsis

```bash

./splunk_enable_disable_saved_searches.py [OPTIONS]

```
# -------------------------------------------------------------------------------

## Description
splunk_enable_disable_saved_searches.py is a script written to disable all reports (saved searches) in a Splunk environment that are both enabled and have an active schedule and then later, use the output from the first run to reenable those searches at a later time.   This is useful for migrations to new Splunk environments where the ask is to get a large number of saved searches loaded in advance, but not have them actively run before the scheduled cutover.   This could also be useful for setting up active / passive search heads.

Note:  There are three runtypes available, 

   - listonly -- A dry run of the application that builds the csv output to the file identified as --csvlist, but won't actually do any disabling
   - disable  -- Runs through all apps in the Splunk environment, loops through each search that is_scheduled=1 and disabled=0, and disables them, logging its work to the file located as --csvlist
   - enable   -- Takes --csvlist as an input, which is the output file from a previous run of the tool in disable mode and enables each of the reports identified in the file

# -------------------------------------------------------------------------------

## Options

###### -h, --help
Print a usage message briefly summarizing these command-line options, then exit.

###### -r, --runtype  [ disable | enable | listonly ]   REQUIRED
Specifies what type of run this is.    Disable will disable all 

###### -s, –-splunkmgmt  [https://uri:port]   REQUIRED
Provide the URL for the management port of the Splunk instance 

###### -u, --username  [string]     Default: admin   REQUIRED
Username of a user that can view, enable and disable all reports in the environment (usually someone with admin / sc_admin role)

###### -p, --password  [string]
Password of the Splunk user.   If not entered, the script will prompt for the password.

###### -c, --csvlist   [relative_path]    Default: ./searchlist/searchlist.csv
CSV List of searches.  

If run type is listonly, then this list is filled with the list of searches that are enabled and have a schedule.
If the runtype is disable, then this list is a full list of searches that were disabled in the last run.
If the run type is reenable, then this points to a list of searches that were previously disabled and the script enables each search. 

CSV must have the following field names:  search_name, app

###### -i, --ignoreapps   [ app1,app2,...,appX ] 
Comma separated list of applications that will be ignored.   Searches in this list will not be included on the csv or disabled / enabled.     

# -------------------------------------------------------------------------------

## Examples

```bash

# disable all currently enabled scheduled searches (will use default ./searchlist/searchlist.csv as -c is not specified)
./splunk_bulk_report_enable_disable.py -r disable -s https://splunkinstance.splunkcloud.com:8089 -u username -p password 

# reenable previously disabled scheduled searches from list at ./searches.csv
./splunk_bulk_report_enable_disable.py -r enable -s https://splunkinstance.splunkcloud.com:8089 -u username -p password -c ./searches.csv

# list all enabled scheduled searches and save to default ./searchlist/searchlist.csv.   Password is not supplied so this will be prompted.
./splunk_bulk_report_enable_disable.py -r listonly -s https://splunkinstance.splunkcloud.com:8089 -u username

```
# -------------------------------------------------------------------------------

## Known issues

I have noticed that a small percentage of reports fail to disable and I am as yet unsure why.    These will be noted in the csvlist file with a status of "FAILED" and will need to be disabled manually.


