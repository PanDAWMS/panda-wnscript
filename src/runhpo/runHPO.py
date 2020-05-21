#!/bin/bash

"exec" "python" "-u" "$0" "$@"

import os
import re
import sys
import ast
import time
import getopt
import uuid
import json
import xml.dom.minidom
try:
    import urllib.request as urllib
except ImportError:
    import urllib
from pandawnutil.wnmisc.misc_utils import commands_get_status_output, get_file_via_http, record_exec_directory, \
    get_hpo_sample, update_hpo_sample, update_events

# error code
EC_MissingArg  = 10
EC_NoInput     = 11
EC_Tarball     = 143
EC_WGET        = 146
EC_EVENT       = 147

print ("=== start ===")
print (time.ctime())

debugFlag    = False
libraries    = ''
outputFile   = 'out.json'
inSampleFile = 'input_sample.json'
jobParams    = ''
inputFiles   = []
inputGUIDs   = []
runDir       = './'
oldPrefix    = ''
newPrefix    = ''
directIn     = False
usePFCTurl   = False
sourceURL    = 'https://gridui07.usatlas.bnl.gov:25443'
inMap        = {}
archiveJobO  = ''
writeInputToTxt = ''
scriptName = None
preprocess = False
postprocess = False
pandaID = os.environ.get('PandaID')
taskID = os.environ.get('PanDA_TaskID')
pandaURL = 'https://pandaserver.cern.ch:25443'
iddsURL = 'https://aipanda182.cern.ch:443'

# command-line parameters
opts, args = getopt.getopt(sys.argv[1:], "i:o:j:l:p:a:",
                           ["pilotpars", "debug", "oldPrefix=", "newPrefix=",
                            "directIn", "sourceURL=",
                            "pandaURL=", "iddsURL=",
                            "inputGUIDs=", "inMap=",
                            "usePFCTurl", "accessmode=",
                            "writeInputToTxt=",
                            "pandaID=", "taskID=",
                            "inSampleFile=",
                            "preprocess", "postprocess"
                            ])
for o, a in opts:
    if o == "-l":
        libraries=a
    if o == "-j":
        scriptName=a
    if o == "-p":
        jobParams=urllib.unquote(a)
    if o == "-i":
        inputFiles = ast.literal_eval(a)
    if o == "-o":
        outputFile = a
    if o == "--debug":
        debugFlag = True
    if o == "--inputGUIDs":
        inputGUIDs = ast.literal_eval(a)
    if o == "--oldPrefix":
        oldPrefix = a
    if o == "--newPrefix":
        newPrefix = a
    if o == "--directIn":
        directIn = True
    if o == "--sourceURL":
        sourceURL = a
    if o == "--inMap":
        inMap = ast.literal_eval(a)
    if o == "-a":
        archiveJobO = a
    if o == "--usePFCTurl":
        usePFCTurl = True
    if o == "--writeInputToTxt":
        writeInputToTxt = a
    if o == "--preprocess":
        preprocess = True
    if o == "--postprocess":
        postprocess = True
    if o == '--pandaID':
        pandaID = int(a)
    if o == '--taskID':
        taskID = int(a)
    if o == '--pandaURL':
        pandaURL = a
    if o == '--iddsURL':
        iddsURL = a
    if o == '--inSampleFile':
        inSampleFile = a

# dump parameter
try:
    print ("=== parameters ===")
    print ("PandaID", pandaID)
    print ("taskID", taskID)
    print ("libraries",libraries)
    print ("runDir",runDir)
    print ("jobParams",jobParams)
    print ("inputFiles",inputFiles)
    print ("scriptName",scriptName)
    print ("outputFile",outputFile)
    print ("inputGUIDs",inputGUIDs)
    print ("oldPrefix",oldPrefix)
    print ("newPrefix",newPrefix)
    print ("directIn",directIn)
    print ("usePFCTurl",usePFCTurl)
    print ("debugFlag",debugFlag)
    print ("sourceURL",sourceURL)
    print ("inMap",inMap)
    print ("archiveJobO",archiveJobO)
    print ("writeInputToTxt",writeInputToTxt)
    print ("preprocess", preprocess)
    print ("postprocess", postprocess)
    print ("===================\n")
except Exception as e:
    print ('ERROR: missing parameters : %s' % str(e))
    sys.exit(EC_MissingArg)

# save current dir
currentDir = record_exec_directory()
currentDirFiles = os.listdir('.')

# work dir
workDir = currentDir+"/workDir"

# for input
directTmpTurl = {}
directPFNs = {}
if not postprocess:
    # create work dir
    commands_get_status_output('rm -rf %s' % workDir)
    os.makedirs(workDir)

    # collect GUIDs from PoolFileCatalog
    try:
        print ("\n===== PFC from pilot =====")
        tmpPcFile = open("PoolFileCatalog.xml")
        print (tmpPcFile.read())
        tmpPcFile.close()
        # parse XML
        root  = xml.dom.minidom.parse("PoolFileCatalog.xml")
        files = root.getElementsByTagName('File')
        for file in files:
            # get ID
            id = str(file.getAttribute('ID'))
            # get PFN node
            physical = file.getElementsByTagName('physical')[0]
            pfnNode  = physical.getElementsByTagName('pfn')[0]
            # convert UTF8 to Raw
            pfn = str(pfnNode.getAttribute('name'))
            # LFN
            lfn = pfn.split('/')[-1]
            # append
            directTmpTurl[id] = pfn
            directPFNs[lfn] = pfn
    except Exception as e:
        print ('ERROR : Failed to collect GUIDs : %s' % str(e))

    # add secondary files if missing
    for tmpToken in inMap:
        tmpList = inMap[tmpToken]
        for inputFile in tmpList:
            if not inputFile in inputFiles:
                inputFiles.append(inputFile)
    print ('')
    print ("===== inputFiles with inMap =====")
    print ("inputFiles",inputFiles)
    print ('')

# move to work dir
os.chdir(workDir)

# preprocess or single-step execution
if not postprocess:
    # expand libraries
    if libraries == '':
        tmpStat, tmpOut = 0, ''
    elif libraries.startswith('/'):
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s' % libraries)
        print (tmpOut)
    else:
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s/%s' % (currentDir,libraries))
        print (tmpOut)
    if tmpStat != 0:
        print ("ERROR : {0} is corrupted".format(libraries))
        sys.exit(EC_Tarball)

    # expand jobOs if needed
    if archiveJobO != "" and libraries == '':
        url = '%s/cache/%s' % (sourceURL, archiveJobO)
        tmpStat, tmpOut = get_file_via_http(full_url=url)
        if not tmpStat:
            print ("ERROR : " + tmpOut)
            sys.exit(EC_WGET)
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s' % archiveJobO)
        print (tmpOut)
        if tmpStat != 0:
            print ("ERROR : {0} is corrupted".format(archiveJobO))
            sys.exit(EC_Tarball)

# make run dir just in case
commands_get_status_output('mkdir %s' % runDir)
# go to run dir
os.chdir(runDir)

# preprocess or single-step execution
eventFileName = '__panda_events.json'
sampleFileName = '__hpo_sample.txt'
if 'X509_USER_PROXY' in os.environ:
    certfile = os.environ['X509_USER_PROXY']
else:
    certfile = '/tmp/x509up_u{0}'.format(os.getuid())
keyfile = certfile
if not postprocess:
    commands_get_status_output('rm -rf {0}'.format(eventFileName))
    commands_get_status_output('rm -rf {0}'.format(sampleFileName))
    # check input files
    inputFileMap = {}
    if inputFiles != []:
        print ("=== check input files ===")
        newInputs = []
        for inputFile in inputFiles:
            # direct reading
            foundFlag = False
            if directIn:
                if inputFile in directPFNs:
                    newInputs.append(directPFNs[inputFile])
                    foundFlag = True
                    inputFileMap[inputFile] = directPFNs[inputFile]
            else:
                # make symlinks to input files
                if inputFile in currentDirFiles:
                    os.symlink('%s/%s' % (currentDir,inputFile),inputFile)
                    newInputs.append(inputFile)
                    foundFlag = True
                    inputFileMap[inputFile] = inputFile
            if not foundFlag:
                print ("%s not exist" % inputFile)
        inputFiles = newInputs
        if len(inputFiles) == 0:
            print ("ERROR : No input file is available")
            sys.exit(EC_NoInput)
        print ("=== New inputFiles ===")
        print (inputFiles)

    # add current dir to PATH
    os.environ['PATH'] = '.:'+os.environ['PATH']

    print ("=== ls in run dir : %s (%s) ===" % (runDir, os.getcwd()))
    print (commands_get_status_output('ls -l')[-1])
    print ('')

    # chmod +x just in case
    commands_get_status_output('chmod +x %s' % scriptName)
    if scriptName == '':
        commands_get_status_output('chmod +x %s' % jobParams.split()[0])

    # replace input files
    newJobParams = jobParams
    if inputFiles != []:
        # decompose to stream and filename
        writeInputToTxtMap = {}
        if writeInputToTxt != '':
            for tmpItem in writeInputToTxt.split(','):
                tmpItems = tmpItem.split(':')
                if len(tmpItems) == 2:
                    tmpStream,tmpFileName = tmpItems
                    writeInputToTxtMap[tmpStream] = tmpFileName
        if writeInputToTxtMap != {}:
            print ("=== write input to file ===")
        if inMap == {}:
            inStr = ','.join(inputFiles)
            # replace
            newJobParams = newJobParams.replace('%IN',inStr)
            # write to file
            tmpKeyName = 'IN'
            if tmpKeyName in writeInputToTxtMap:
                commands_get_status_output('rm -f %s' % writeInputToTxtMap[tmpKeyName])
                with open(writeInputToTxtMap[tmpKeyName],'w') as f:
                    json.dump(inputFiles, f)
                print ("%s to %s : %s" % (tmpKeyName, writeInputToTxtMap[tmpKeyName], str(inputFiles)))
        else:
            # multiple inputs
            for tmpToken in inMap:
                tmpList = inMap[tmpToken]
                inStr = ','.join(tmpList) + ' '
                # replace
                newJobParams = re.sub('%'+tmpToken+'(?P<sname> |$|\"|\')',inStr+'\g<sname>',newJobParams)
                # write to file
                tmpKeyName = tmpToken
                if tmpKeyName in writeInputToTxtMap:
                    commands_get_status_output('rm -f %s' % writeInputToTxtMap[tmpKeyName])
                    with open(writeInputToTxtMap[tmpKeyName], 'w') as f:
                        json.dump(tmpList, f)
                    print ("%s to %s : %s" % (tmpKeyName, writeInputToTxtMap[tmpKeyName], str(tmpList)))
        if writeInputToTxtMap != {}:
            print ('')
    # fetch an event
    print ("=== getting events from PanDA ===")
    for iii in range(10):
        data = dict()
        data['pandaID'] = pandaID
        data['jobsetID'] = 0
        data['taskID'] = taskID
        data['nRanges'] = 1
        url = pandaURL + '/server/panda/getEventRanges'
        tmpStat, tmpOut = get_file_via_http(file_name=eventFileName, full_url=url, data=data,
                                            headers={'Accept': 'application/json'},
                                            certfile=certfile, keyfile=keyfile)
        if not tmpStat:
            print ("ERROR : " + tmpOut)
            sys.exit(EC_WGET)
        with open(eventFileName) as f:
            print(f.read())
        print ('')
        # convert to dict
        try:
            with open(eventFileName) as f:
                event_dict = json.load(f)
                # no events
                if not event_dict['eventRanges']:
                    break
                event = event_dict['eventRanges'][0]
                event_id = event['eventRangeID']
                sample_id = event_id.split('-')[3]
                print (" got eventID={0} sampleID={1}\n".format(event_id, sample_id))
                # check with iDDS
                print ("\n=== getting HP samples from iDDS ===")
                tmpStat, tmpOut = get_hpo_sample(iddsURL, taskID, sample_id)
                if not tmpStat:
                    raise RuntimeError(tmpOut)
                print ("\n got {0}".format(str(tmpOut)))
                if tmpOut['loss'] is not None:
                    print ("\n already evaluated")
                    print ("\n=== updating events in PanDA ===")
                    update_events(pandaURL, event_id, 'finished', certfile, keyfile)
                    print ('')
                else:
                    print ("\n to evaluate")
                    with open(sampleFileName, 'w') as wf:
                        wf.write('{0},{1}'.format(event_id, sample_id))
                    with open(inSampleFile, 'w') as wf:
                        json.dump(tmpOut['parameters'], wf)
                    break
        except RuntimeError as e:
            print ("ERROR: failed to get a HP sample from iDDS. {0}".format(e.message))
        except Exception as e:
            print ("ERROR: failed to get an event from PanDA. {0}".format(str(e)))
            sys.exit(EC_EVENT)
    # no event
    if not os.path.exists(sampleFileName):
        print ("\n==== Result ====")
        print ("exit due to no event")
        sys.exit(0)

    # construct command
    com = ''
    if preprocess:
        tmpTrfName = os.path.join(currentDir, '__run_main_exec.sh')
    else:
        tmpTrfName = 'trf.%s.py' % str(uuid.uuid4())
    tmpTrfFile = open(tmpTrfName,'w')
    if preprocess:
        tmpTrfFile.write('cd {0}\n'.format(os.path.relpath(os.getcwd(), currentDir)))
        tmpTrfFile.write('export PATH=$PATH:.\n')
        tmpTrfFile.write('{0} {1}\n'.format(scriptName,newJobParams))
    else:
        # wrap commands to invoke execve even if preload is removed/changed
        tmpTrfFile.write('import os,sys\nstatus=os.system(r"""%s %s""")\n' % (scriptName,newJobParams))
        tmpTrfFile.write('status %= 255\nsys.exit(status)\n\n')
    tmpTrfFile.close()

    # return if preprocess
    if preprocess:
        commands_get_status_output('chmod +x {0}'.format(tmpTrfName))
        print ("\n==== Result ====")
        print ("prepossessing successfully done")
        print ("produced {0}".format(tmpTrfName))
        sys.exit(0)

    com += 'cat %s;python -u %s' % (tmpTrfName,tmpTrfName)

    # temporary output to avoid MemeoryError
    tmpOutput = 'tmp.stdout.%s' % str(uuid.uuid4())
    tmpStderr = 'tmp.stderr.%s' % str(uuid.uuid4())


    print ("\n=== execute ===")
    print (com)
    # run athena
    if not debugFlag:
        # write stdout to tmp file
        com += ' > %s 2> %s' % (tmpOutput,tmpStderr)
        status,out = commands_get_status_output(com)
        print (out)
        status %= 255
        try:
            tmpOutFile = open(tmpOutput)
            for line in tmpOutFile:
                print (line[:-1])
            tmpOutFile.close()
        except:
            pass
        try:
            stderrSection = True
            tmpErrFile = open(tmpStderr)
            for line in tmpErrFile:
                if stderrSection:
                    stderrSection = False
                    print ("\n=== stderr ===")
                print (line[:-1])
            tmpErrFile.close()
        except:
            pass
        # print 'sh: line 1:  8278 Aborted'
        try:
            if status != 0:
                print (out.split('\n')[-1])
        except:
            pass
    else:
        status = os.system(com)
else:
    # no event
    if not os.path.exists(sampleFileName):
        print ("\n==== Result ====")
        print ("exit due to no event")
        sys.exit(0)
    # set 0 for postprocess
    status = 0

print ('')
print ("=== ls in run dir : {0} ({1}) ===".format(runDir, os.getcwd()))
print (commands_get_status_output('ls -l')[-1])
print ('')

with open(sampleFileName) as f:
    tmp_str = f.read()
    event_id, sample_id = tmp_str.split(',')

# get loss
print ("=== getting loss from {0} ===".format(outputFile))
loss = None
if not os.path.exists(outputFile):
    print ("{0} doesn't exist".format(outputFile))
else:
    with open(outputFile) as f:
        try:
            print (f.read())
            f.seek(0)
            out_dict = json.load(f)
            if out_dict['status'] == 0:
                loss = out_dict['loss']
                print ("got loss={0}".format(loss))
            else:
                print ("ERROR: failed to evaluate. status={0} err={1}".format(out_dict['status'],
                                                                              out_dict['error']))
        except Exception as e:
            print ("ERROR: failed to get loss. {0}".format(str(e)))
print ('')

# report loss
if loss is not None:
    print ("=== reporting loss to iDDS ===")
    tmpStat, tmpOut = update_hpo_sample(iddsURL, taskID, sample_id, loss)
    if not tmpStat:
        print ('ERROR: {0}\n'.format(tmpOut))
    else:
        print ("\n=== updating events in PanDA ===")
        update_events(pandaURL, event_id, 'finished', certfile, keyfile)
        print ('')

# add user job metadata
try:
    from pandawnutil.wnmisc import misc_utils
    misc_utils.add_user_job_metadata()
except Exception:
    pass

# copy results
commands_get_status_output('mv %s %s' % (outputFile, currentDir))


# create empty PoolFileCatalog.xml if it doesn't exist
pfcName = 'PoolFileCatalog.xml'
pfcSt,pfcOut = commands_get_status_output('ls %s' % pfcName)
if pfcSt != 0:
    pfcFile = open(pfcName,'w')
    pfcFile.write("""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<!-- Edited By POOL -->
<!DOCTYPE POOLFILECATALOG SYSTEM "InMemory">
<POOLFILECATALOG>

</POOLFILECATALOG>
""")
    pfcFile.close()

# copy PFC
commands_get_status_output('mv %s %s' % (pfcName,currentDir))

# copy useful files
for patt in ['runargs.*','runwrapper.*','jobReport.json','log.*']:
    commands_get_status_output('mv -f %s %s' % (patt,currentDir))

# go back to current dir
os.chdir(currentDir)

print ("\n=== ls in entry dir : %s ===" % os.getcwd())
print (commands_get_status_output('ls -l')[-1])

# remove work dir
if not debugFlag:
    commands_get_status_output('rm -rf %s' % workDir)

# return
print ("\n==== Result ====")
if status:
    print ("execute script: Running script failed : StatusCode=%d" % status)
    sys.exit(status)
else:
    print ("execute script: Running script was successful")
    sys.exit(0)