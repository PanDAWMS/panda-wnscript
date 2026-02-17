#!/bin/bash

"exec" "python" "-u" "-Wignore" "$0" "$@"

"""
Run Athena

Usage:

$ source $SITEROOT/setup.sh
$ source $T_DISTREL/AtlasRelease/*/cmt/setup.sh -tag_add=???
$ runAthena -l [libraries] -r [rundir] -j [jobOs] -i [inputs] -o [optputs] -c \
            -p [pool_refs] -u [lrc_url]

-l [libraries] : an archive which contains libraries
-r [rundir]    : relative path to the directory where Athena runs
-j [jobOs]     : job options passed to athena. format: 'options'
-i [inputs]    : list of input files. format: ['in1',...'inN']
-o [outputs]   : map of output files. format: {'type':'name',..}
                  type:'hist','ntuple','ESD','AOD','TAG','AANT','Stream1','THIST'
-b             : bytestream
-c             : event collection
-p [pool_refs] : list of POOL refs
-u [lrc_url]   : URL of LRC
-f [fragment]  : jobO fragment
-a [jobO files]: archive name of jobOs
-m [minbias]   : list of minimum bias files
-n [cavern]    : list of cavern files
--debug        : debug
--directIn     : read input files from SE
--oldPrefix    : old prefix to be replaced when converting TURL
--newPrefix    : new prefix to be used when converting TURL

Example:

runAthena \
  -l libraries.tgz \
  -r PhysicsAnalysis/AnalysisCommon/UserAnalysis/UserAnalysis-00-03-03/run \
  -j "-c 'EvtMax=10' opt.py RecExCommon.py" \
  -i ['input1.AOD.pool.root','input2.AOD.pool.root','input3.AOD.pool.root'] \
  -o ['hist':'hist.root','ntuple':'ntuple.root','log':'athena.log']

Procedure:

* expand libraries
* make PoolFileCatalog.xml
* create post-jobO which overwrites some parameters
* get PDGTABLE.MeV
* run athena

"""

import re
import os
import sys
import ast
import glob
import getopt
import datetime
try:
    import urllib.request as urllib
except ImportError:
    import urllib
try:
    from urllib.request import urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import urlopen, HTTPError
import xml.dom.minidom
import uuid
try:
    long
    basestring
except NameError:
    long = int
    basestring = str
from pandawnutil.wnmisc.misc_utils import commands_get_status_output, get_file_via_http, record_exec_directory,\
    propagate_missing_sandbox_error, make_log_tarball_in_sub_dirs, tweak_job_options
from pandawnutil.wnmisc.error_codes import ErrorCodes
from pandawnutil.build_timestamp import build_timestamp

print ("=== start with build timestamp: %s" % build_timestamp)
print(datetime.datetime.utcnow())
print("")

# error code
EC = ErrorCodes('runAthena')
EC_PoolCatalog  = EC.BAD_POLL_FILE_CATALOG
EC_MissingArg   = EC.MISSING_ARGUMENT
EC_AthenaFail   = EC.ATHENA_FAILURE
EC_NoInput      = EC.ALL_INPUT_UNAVAILABLE
EC_MissingInput = EC.SOME_INPUT_UNAVAILABLE
EC_Tarball      = EC.CORRUPTED_TARBALL
EC_DBRelease    = EC.DB_RELEASE_FAILURE
EC_WGET         = EC.FAILED_TO_GET_TARBALL
EC_MissingOutput = EC.OUTPUT_MISSING

# command-line parameters
eventColl  = False
byteStream = False
backNavi   = False
debugFlag  = False
poolRefs = []
urlLRC = ''
libraries    = ''
fragmentJobO = ''
archiveJobO  = ''
minbiasFiles = []
cavernFiles  = []
beamHaloFiles= []
beamGasFiles = []
oldPrefix    = ''
newPrefix    = ''
directIn     = False
lfcHost      = ''
inputGUIDs   = []
minbiasGUIDs = []
cavernGUIDs  = []
shipInput    = False
addPoolFC    = []
corCheck     = False
sourceURL    = 'https://gridui07.usatlas.bnl.gov:25443'
mcData       = ''
notSkipMissing = False
givenPFN     = False
runTrf       = False
envvarFile   = ''
runAra       = False
dbrFile      = ''
generalInput = False
guidBoundary = []
collRefName  = ''
useNextEvent = False
liveLog      = ''
dbrRun       = -1
useLocalIO   = False
codeTrace    = False
useFileStager= False
usePFCTurl   = False
copyTool     = ''
eventPickTxt = ''
eventPickSt  = 0
eventPickNum = -1
skipInputByRetry = []
tagFileList  = []
noExpandDBR  = False
useCMake = False
useAthenaMT = False
preprocess = False
postprocess = False

opts, args = getopt.getopt(sys.argv[1:], "l:r:j:i:o:bcp:u:f:a:m:n:e",
                           ["pilotpars","debug","oldPrefix=","newPrefix=",
                            "directIn","lfcHost=","inputGUIDs=","minbiasGUIDs=",
                            "cavernGUIDs=","shipInput","addPoolFC=","corCheck",
                            "sourceURL=","mcData=","notSkipMissing","givenPFN",
                            "beamHalo=","beamGas=","trf","envvarFile=","ara",
                            "dbrFile=","generalInput","guidBoundary=",
                            "collRefName=","useNextEvent","liveLog=",
                            "dbrRun=","useLocalIO","codeTrace","useFileStager",
                            "usePFCTurl",
                            "accessmode=","copytool=",
                            "eventPickTxt=","eventPickSt=","eventPickNum=",
                            "skipInputByRetry=","tagFileList=",
                            "enable-jem","jem-config=",
                            "mergeOutput","mergeType=","mergeScript=",
                            "noExpandDBR","useCMake","useAthenaMT",
                            "preprocess", "postprocess"
                            ])
for o, a in opts:
    if o == "-l":
        libraries=a
    if o == "-r":
        runDir=a
    if o == "-j":
        jobO=urllib.unquote(a)
    if o == "-i":
        inputFiles = ast.literal_eval(a)
    if o == "-o":
        outputFiles = ast.literal_eval(a)
    if o == "-m":
        minbiasFiles = ast.literal_eval(a)
    if o == "-n":
        cavernFiles = ast.literal_eval(a)
    if o == "--beamHalo":
        beamHaloFiles = ast.literal_eval(a)
    if o == "--beamGas":
        beamGasFiles = ast.literal_eval(a)
    if o == "-b":
        byteStream = True
    if o == "-c":
        eventColl = True
    if o == "-p":
        poolRefs = ast.literal_eval(a)
    if o == "-u":
        urlLRC=a
    if o == "-f":
        fragmentJobO=a
    if o == "-a":
        archiveJobO=a
    if o == "-e":
        backNavi = True
    if o == "--debug":
        debugFlag = True
    if o == "--oldPrefix":
        oldPrefix = a
    if o == "--newPrefix":
        newPrefix = a
    if o == "--directIn":
        directIn = True
    if o == "--lfcHost":
        lfcHost = a
    if o == "--inputGUIDs":
        inputGUIDs = ast.literal_eval(a)
    if o == "--minbiasGUIDs":
        minbiasGUIDs = ast.literal_eval(a)
    if o == "--cavernGUIDs":
        cavernGUIDs = ast.literal_eval(a)
    if o == "--shipInput":
        shipInput = True
    if o == "--addPoolFC":
        addPoolFC = a.split(',')
    if o == "--corCheck":
        corCheck = True
    if o == "--sourceURL":
        sourceURL = a
    if o == "--mcData":
        mcData = a
    if o == "--notSkipMissing":
        notSkipMissing = True
    if o == "--givenPFN":
        givenPFN = True
    if o == "--trf":
        runTrf = True
    if o == "--envvarFile":
        envvarFile = a
    if o == "--ara":
        runAra = True
    if o == "--dbrFile":
        dbrFile = a
    if o == "--generalInput":
        generalInput = True
    if o == "--guidBoundary":
        guidBoundary = ast.literal_eval(a)
    if o == "--collRefName":
        collRefName = a
    if o == "--useNextEvent":
        useNextEvent = True
    if o == "--liveLog":
        liveLog = a
    if o == "--dbrRun":
        dbrRun = a
    if o == "--useLocalIO":
        useLocalIO = True
    if o == "--codeTrace":
        codeTrace = True
    if o == "--useFileStager":
        useFileStager = True
    if o == "--usePFCTurl":
        usePFCTurl = True
    if o == "--copytool":
        copyTool = a
    if o == "--eventPickTxt":
        eventPickTxt = a
    if o == "--eventPickSt":
        eventPickSt = int(a)
    if o == "--eventPickNum":
        eventPickNum = int(a)
    if o == "--skipInputByRetry":
        skipInputByRetry = a.split(',')
    if o == "--tagFileList":
        tagFileList = a.split(',')
    if o == "--noExpandDBR":
        noExpandDBR = True
    if o == "--useCMake":
        useCMake = True
    if o == "--useAthenaMT":
        useAthenaMT = True
    if o == "--preprocess":
        preprocess = True
    if o == "--postprocess":
        postprocess = True

# save current dir
currentDir = record_exec_directory()

# change full path
if envvarFile != '':
    envvarFile = '%s/%s' % (currentDir,envvarFile)

# dump parameter
try:
    print ("=== parameters ===")
    print ("libraries",libraries)
    print ("runDir",runDir)
    print ("jobO",jobO)
    print ("inputFiles",inputFiles)
    print ("outputFiles",outputFiles)
    print ("byteStream",byteStream)
    print ("eventColl",eventColl)
    print ("backNavi",backNavi)
    print ("debugFlag",debugFlag)
    print ("poolRefs",poolRefs)
    print ("urlLRC",urlLRC)
    print ("fragmentJobO",fragmentJobO)
    print ("minbiasFiles",minbiasFiles)
    print ("cavernFiles",cavernFiles)
    print ("beamHaloFiles",beamHaloFiles)
    print ("beamGasFiles",beamGasFiles)
    print ("oldPrefix",oldPrefix)
    print ("newPrefix",newPrefix)
    print ("directIn",directIn)
    print ("lfcHost",lfcHost)
    print ("inputGUIDs",inputGUIDs)
    print ("minbiasGUIDs",minbiasGUIDs)
    print ("cavernGUIDs",cavernGUIDs)
    print ("addPoolFC",addPoolFC)
    print ("corCheck",corCheck)
    print ("sourceURL",sourceURL)
    print ("mcData",mcData)
    print ("notSkipMissing",notSkipMissing)
    print ("givenPFN",givenPFN)
    print ("runTrf",runTrf)
    print ("envvarFile",envvarFile)
    print ("runAra",runAra)
    print ("dbrFile",dbrFile)
    print ("generalInput",generalInput)
    print ("liveLog",liveLog)
    print ("dbrRun",dbrRun)
    print ("useLocalIO",useLocalIO)
    print ("codeTrace",codeTrace)
    print ("useFileStager",useFileStager)
    print ("usePFCTurl",usePFCTurl)
    print ("copyTool",copyTool)
    print ("eventPickTxt",eventPickTxt)
    print ("eventPickSt",eventPickSt)
    print ("eventPickNum",eventPickNum)
    print ("skipInputByRetry",skipInputByRetry)
    print ("tagFileList",tagFileList)
    print ("noExpandDBR",noExpandDBR)
    print ("useCMake",useCMake)
    print ("useAthenaMT",useAthenaMT)
    print ("preprocess", preprocess)
    print ("postprocess", postprocess)
    print ("===================")
except Exception:
    EC_MissingArg.exit("Failed to parse command-line arguments. Please check the input parameters.")

origNumInputFiles = len(inputFiles)

if not postprocess:
    # disable direct input for unsupported cases
    if directIn:
        if useLocalIO:
            # use local IO
            directIn = False
            print ("disabled directIn due to useLocalIO")
        elif byteStream and newPrefix.startswith('root://'):
            # BS on xrootd
            directIn = False
            print ("disabled directIn for xrootd/RAW")

    # remove duplication while keeping order
    seen = set()
    unique = []
    for x in inputFiles:
        if x not in seen:
            seen.add(x)
            unique.append(x)
    inputFiles = unique

    # remove skipped files
    if skipInputByRetry != []:
        tmpInputList = []
        for tmpLFN in inputFiles:
            if not tmpLFN in skipInputByRetry:
                tmpInputList.append(tmpLFN)
        inputFiles = tmpInputList
        print ("removed skipped files -> %s" % str(inputFiles))

    # add "" in envvar
    try:
        newString = '#!/bin/bash\n'
        if envvarFile != '':
            tmpEnvFile = open(envvarFile)
            for line in tmpEnvFile:
                # remove \n
                line = line[:-1]
                match = re.search('([^=]+)=(.*)',line)
                if match is not None:
                    # add ""
                    newString += '%s="%s"\n' % (match.group(1),match.group(2))
                else:
                    newString += '%s\n' % line
            tmpEnvFile.close()
            # overwrite
            tmpEnvFile = open(envvarFile,'w')
            tmpEnvFile.write(newString)
            tmpEnvFile.close()
    except Exception as e:
        print ('WARNING: changing envvar : %s' % str(e))


    # collect GUIDs from PoolFileCatalog
    guidMapFromPFC = {}
    directTmpTurl = {}
    try:
        print ("===== PFC from pilot =====")
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
            lfn = pfn.split('/')[-1]
            lfn = re.sub('__DQ2-\d+$','',lfn)
            lfn = re.sub('^([^:]+:)','', lfn)
            lfn = re.sub('\?GoogleAccessId.*$','', lfn)
            lfn = re.sub('\?X-Amz-Algorithm.*$', '', lfn)
            # append
            guidMapFromPFC[lfn] = id
            directTmpTurl[id] = pfn
    except Exception as e:
        print ('ERROR : Failed to collect GUIDs : %s' % str(e))

    print ("===== GUIDs in PFC =====")
    print (guidMapFromPFC)

    # check input files
    directPfnMap = {}
    directMetaMap = {}
    directPFNs = {}
    if directIn:
        # Use the TURLs from PoolFileCatalog.xml created by pilot
        print ("===== GUIDs and TURLs in PFC =====")
        print (directTmpTurl)
        directTmp = directTmpTurl
        # set newPrefix to set copy tool in FileStager
        if directTmp != {}:
            # one PFN is enough since only the prefix is checked
            newPrefix = list(directTmp.values())[0]
        # collect LFNs
        curFiles   = []
        for id in directTmp.keys():
            lfn = directTmp[id].split('/')[-1]
            lfn = re.sub('^([^:]+:)','',lfn)
            curFiles.append(lfn)
            directPFNs[lfn] = directTmp[id]
        directPfnMap = directTmp
    elif givenPFN:
        # collect LFNs
        curFiles   = []
        for lfn in inputFiles+minbiasFiles+cavernFiles+beamHaloFiles+beamGasFiles:
            curFiles.append(lfn)
    else:
        curFiles = os.listdir('.')

    flagMinBias = False
    flagCavern  = False
    flagBeamGas = False
    flagBeamHalo= False

    if len(inputFiles) > 0 and (not shipInput):
        tmpFiles = tuple(inputFiles)
        for tmpF in tmpFiles:
            findF = False
            findName = ''
            for curF in curFiles:
                if re.search('^'+tmpF,curF) is not None:
                    findF = True
                    findName = curF
                    break
            # remove if not exist
            if not findF:
                print ("%s not exist" % tmpF)
                inputFiles.remove(tmpF)
            # use URL
            if directIn and findF:
                inputFiles.remove(tmpF)
                inputFiles.append(directPFNs[findName])
        if len(inputFiles) == 0:
            print ("No input file is available")
            EC_NoInput.exit()
        if notSkipMissing and len(inputFiles) != len(tmpFiles):
            print ("Some input files are missing")
            EC_MissingInput.exit()


    if len(minbiasFiles) > 0:
        flagMinBias = True
        tmpFiles = tuple(minbiasFiles)
        for tmpF in tmpFiles:
            findF = False
            findName = ''
            for curF in curFiles:
                if re.search('^'+tmpF,curF) is not None:
                    findF = True
                    findName = curF
                    break
            # remove if not exist
            if not findF:
                print ("%s not exist" % tmpF)
                minbiasFiles.remove(tmpF)
            # use URL
            if directIn and findF:
                minbiasFiles.remove(tmpF)
                minbiasFiles.append(directPFNs[findName])
        if len(minbiasFiles) == 0:
            print ("No input file is available for Minimum-bias")
            EC_NoInput.exit()
        if notSkipMissing and len(minbiasFiles) != len(tmpFiles):
            print ("Some input files are missing")
            EC_MissingInput.exit()


    if len(cavernFiles) > 0:
        flagCavern = True
        tmpFiles = tuple(cavernFiles)
        for tmpF in tmpFiles:
            findF = False
            findName = ''
            for curF in curFiles:
                if re.search('^'+tmpF,curF) is not None:
                    findF = True
                    findName = curF
                    break
            # remove if not exist
            if not findF:
                print ("%s not exist" % tmpF)
                cavernFiles.remove(tmpF)
            # use URL
            if directIn and findF:
                cavernFiles.remove(tmpF)
                cavernFiles.append(directPFNs[findName])
        if len(cavernFiles) == 0:
            print ("No input file is available for Cavern")
            EC_NoInput.exit()
        if notSkipMissing and len(cavernFiles) != len(tmpFiles):
            print ("Some input files are missing")
            EC_MissingInput.exit()


    if len(beamHaloFiles) > 0:
        flagBeamHalo = True
        tmpFiles = tuple(beamHaloFiles)
        for tmpF in tmpFiles:
            findF = False
            findName = ''
            for curF in curFiles:
                if re.search('^'+tmpF,curF) is not None:
                    findF = True
                    findName = curF
                    break
            # remove if not exist
            if not findF:
                print ("%s not exist" % tmpF)
                beamHaloFiles.remove(tmpF)
            # use URL
            if directIn and findF:
                beamHaloFiles.remove(tmpF)
                beamHaloFiles.append(directPFNs[findName])
        if len(beamHaloFiles) == 0:
            print ("No input file is available for BeamHalo")
            EC_NoInput.exit()
        if notSkipMissing and len(beamHaloFiles) != len(tmpFiles):
            print ("Some input files are missing")
            EC_MissingInput.exit()


    if len(beamGasFiles) > 0:
        flagBeamGas = True
        tmpFiles = tuple(beamGasFiles)
        for tmpF in tmpFiles:
            findF = False
            findName = ''
            for curF in curFiles:
                if re.search('^'+tmpF,curF) is not None:
                    findF = True
                    findName = curF
                    break
            # remove if not exist
            if not findF:
                print ("%s not exist" % tmpF)
                beamGasFiles.remove(tmpF)
            # use URL
            if directIn and findF:
                beamGasFiles.remove(tmpF)
                beamGasFiles.append(directPFNs[findName])
        if len(beamGasFiles) == 0:
            print ("No input file is available for BeamGas")
            EC_NoInput.exit()
        if notSkipMissing and len(beamGasFiles) != len(tmpFiles):
            print ("Some input files are missing")
            EC_MissingInput.exit()


    print ("=== New inputFiles ===")
    print (inputFiles)
    if flagMinBias:
        print ("=== New minbiasFiles ===")
        print (minbiasFiles)
    if flagCavern:
        print ("=== New cavernFiles ===")
        print (cavernFiles)
    if flagBeamHalo:
        print ("=== New beamHaloFiles ===")
        print (beamHaloFiles)
    if flagBeamGas:
        print ("=== New beamGasFiles ===")
        print (beamGasFiles)


# crate work dir
workDir = currentDir+"/workDir"
if not postprocess:
    commands_get_status_output('rm -rf %s' % workDir)
    os.makedirs(workDir)
os.chdir(workDir)


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
        EC_Tarball.exit("tarball %s is corrupted" % libraries)

    # get and expand jobOs if needed
    if archiveJobO != "":
        isOK = False
        errStr = None
        url = '%s/cache/%s' % (sourceURL, archiveJobO)
        tmpStat, tmpOut = get_file_via_http(full_url=url)
        if not tmpStat:
            propagate_missing_sandbox_error()
            EC_WGET.exit(tmpOut)
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s' % archiveJobO)
        print (tmpOut)
        if tmpStat != 0:
            EC_Tarball.exit("tarball %s is corrupted" % archiveJobO)


    # make rundir just in case
    commands_get_status_output('mkdir %s' % runDir)
# go to run dir
os.chdir(runDir)

if not postprocess:
    # make cmt dir
    cmtDir = '%s/%s/cmt' % (workDir, str(uuid.uuid4()))
    commands_get_status_output('mkdir -p %s' % cmtDir)


# create PoolFC
def _createPoolFC(pfnMap):
    outFile = open('PoolFileCatalog.xml','w')
    # write header
    header = \
    """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
    <!-- Edited By POOL -->
    <!DOCTYPE POOLFILECATALOG SYSTEM "InMemory">
    <POOLFILECATALOG>
    """
    outFile.write(header)
    # write files
    item = \
    """
      <File ID="%s">
        <physical>
          <pfn filetype="ROOT_All" name="%s"/>
        </physical>
        <logical/>
      </File>
    """
    for guid in pfnMap:
        pfn = pfnMap[guid]
        outFile.write(item % (guid.upper(),pfn))
    # write trailer
    trailer = \
    """
    </POOLFILECATALOG>
    """
    outFile.write(trailer)
    outFile.close()
    

if not postprocess:
    # build pool catalog
    print ("\n=== build pool catalog ===")
    commands_get_status_output('rm -f PoolFileCatalog.xml')
    if len(inputFiles+minbiasFiles+cavernFiles+beamHaloFiles+beamGasFiles) > 0:
        # POOL or BS files
        filesToPfcMap = {}
        for fileName in inputFiles+minbiasFiles+cavernFiles+beamHaloFiles+beamGasFiles:
            if (not directIn) and (not givenPFN):
                targetName = fileName
                # for rome data
                if re.search(fileName,'\.\d+$')==None and (not fileName in curFiles):
                    for cFile in curFiles:
                        if re.search('^'+fileName,cFile) is not None:
                            targetName = cFile
                            break
                # form symlink to input file
                try:
                    os.symlink('%s/%s' % (currentDir,targetName),fileName)
                except:
                    pass
            if (not byteStream) and mcData == '' and (not generalInput) and not (runTrf and not runAra):
                # insert it to pool catalog
                tmpLFNforPFC = fileName.split('/')[-1]
                tmpLFNforPFC = re.sub('__DQ2-\d+$','',tmpLFNforPFC)
                tmpLFNforPFC = re.sub('^([^:]+:)','', tmpLFNforPFC)
                tmpLFNforPFC = re.sub('\?GoogleAccessId.*$','', tmpLFNforPFC)
                tmpLFNforPFC = re.sub('\?X-Amz-Algorithm.*$', '', tmpLFNforPFC)
                if tmpLFNforPFC in guidMapFromPFC:
                    filesToPfcMap[guidMapFromPFC[tmpLFNforPFC]] = fileName
                elif not givenPFN:
                    print ("ERROR : %s not found in the pilot PFC" % fileName)
            # create PFC for directIn + trf
            if directIn and (runTrf and not runAra):
                _createPoolFC(directPfnMap)
                # form symlink to input file mainly for DBRelease
                for tmpID in directPfnMap.keys():
                    lfn = directPfnMap[tmpID].split('/')[-1]
                    try:
                        targetName = '%s/%s' % (currentDir,lfn)
                        if os.path.exists(targetName):
                            os.symlink(targetName,lfn)
                    except:
                        pass
        # create PFC for local files
        if filesToPfcMap != {}:
            _createPoolFC(filesToPfcMap)
        elif givenPFN:
            # insert using pool_insertFTC since GUIDs are unavailable from the pilot
            for fileName in inputFiles+minbiasFiles+cavernFiles+beamHaloFiles+beamGasFiles:
                com = 'pool_insertFileToCatalog %s' % fileName
                print (com)
                os.system(com)

        # read PoolFileCatalog.xml
        pLines = ''
        try:
            pFile = open('PoolFileCatalog.xml')
            for line in pFile:
                pLines += line
            pFile.close()
        except Exception:
            if mcData == '' and not (runTrf and not runAra):
                print ("ERROR : cannot open PoolFileCatalog.xml")
        if origNumInputFiles > 0 and len(inputFiles) == 0:
            print ("No input file is available after corruption check")
            EC_NoInput.exit()

    # for user specified files
    if addPoolFC != []:
        print ("=== adding user files to PoolFileCatalog.xml ===")
        for fileName in addPoolFC:
            # insert it to pool catalog
            com = 'pool_insertFileToCatalog %s' % fileName
            print (com)
            status,output = commands_get_status_output(com)
            print (output)
            if status != 0:
                print ('trying coolHist_insertFileToCatalog.py since pool_insertFileToCatalog failed')
                com = 'coolHist_insertFileToCatalog.py %s' % fileName
                print (com)
                status,output = commands_get_status_output(com)
                print (output)


    # print PoolFC
    print ('')
    print ("=== PoolFileCatalog.xml ===")
    print (commands_get_status_output('cat PoolFileCatalog.xml')[-1])
    print ('')

    # create symlink for MC
    if mcData != '' and len(inputFiles) != 0:
        print ("=== make symlink for %s ===" % mcData)
        # expand mcdata.tgz
        commands_get_status_output('rm -f %s' % mcData)
        status,output = commands_get_status_output('tar xvfzm %s' % inputFiles[0])
        print (output)
        if status != 0:
            print ("ERROR : MC data corrupted")
            EC_NoInput.exit()
        # look for .dat
        foundMcData = False
        for line in output.split('\n'):
            if line.endswith('.dat'):
                status,output = commands_get_status_output('ln -fs %s %s' %
                                                           (line.split()[-1],mcData))
                if status != 0:
                    print (output)
                    print ("ERROR : failed to create symlink for MC data")
                    EC_NoInput.exit()
                foundMcData = True
                break
        if not foundMcData:
            print ("ERROR : cannot find *.dat in %s" % inputFiles[0])
            EC_NoInput.exit()

    # setup DB/CDRelease
    if dbrFile != '':
        if noExpandDBR:
            # make symlink
            print (commands_get_status_output('ln -fs %s/%s %s' % (currentDir,dbrFile,dbrFile))[-1])
        else:
            if dbrRun == -1:
                print ("=== setup DB/CDRelease (old style) ===")
                # expand
                status,out = commands_get_status_output('tar xvfzm %s/%s' % (currentDir,dbrFile))
                print (out)
                # remove
                print (commands_get_status_output('rm %s/%s' % (currentDir,dbrFile))[-1])
            else:
                print ("=== setup DB/CDRelease (new style) ===")
                # make symlink
                print (commands_get_status_output('ln -fs %s/%s %s' % (currentDir,dbrFile,dbrFile))[-1])
                # run Reco_trf and set env vars
                dbCom = 'Reco_trf.py RunNumber=%s DBRelease=%s' % (dbrRun,dbrFile)
                print (dbCom)
                status,out = commands_get_status_output(dbCom)
                print (out)
                # remove
                print (commands_get_status_output('rm %s/%s' % (currentDir,dbrFile))[-1])
            # look for setup.py
            tmpSetupDir = None
            for line in out.split('\n'):
                if line.endswith('setup.py'):
                    tmpSetupDir = re.sub('setup.py$','',line)
                    break
            # check
            if tmpSetupDir == None:
                print ("ERROR : cound not find setup.py in %s" % dbrFile)
                EC_DBRelease.exit()
            # run setup.py
            dbrSetupStr  = "import os\nos.chdir('%s')\nexec(open('setup.py').read())\nprint ('DBR setup finished')\nos.chdir('%s')\n" % \
                           (tmpSetupDir,os.getcwd())
            dbrSetupStr += "import sys\nsys.stdout.flush()\nsys.stderr.flush()\n"


    # create post-jobO file which overwrites some parameters
    postOpt = 'post_' + str(uuid.uuid4()) + '.py'
    oFile = open(postOpt,'w')
    oFile.write("""
try:
    EventSelectorAthenaPool.__getattribute__ = orig_ESAP__getattribute
except:
    pass

def _Service(str):
    try:
        svcMgr = theApp.serviceMgr()
        return getattr(svcMgr,str)
    except:
        return Service(str)
""")
    if len(inputFiles) != 0 and mcData == '' and not runAra:
        if (re.search('theApp.EvtMax',fragmentJobO) is None) and \
           (re.search('EvtMax',jobO) is None):
            oFile.write('theApp.EvtMax = -1\n')
        if byteStream:
            # BS
            oFile.write('ByteStreamInputSvc = _Service( "ByteStreamInputSvc" )\n')
            oFile.write('try:\n')
            oFile.write('    ByteStreamInputSvc.FullFileName = %s\n' % inputFiles)
            oFile.write('except:\n')
            oFile.write('    EventSelector = _Service( "EventSelector" )\n')
            oFile.write('    EventSelector.Input = %s\n' % inputFiles)
        else:
            oFile.write('EventSelector = _Service( "EventSelector" )\n')
            # normal POOL
            oFile.write('EventSelector.InputCollections = %s\n' % inputFiles)
    elif len(inputFiles) != 0 and runAra:
        for tmpInput in inputFiles:
            oFile.write("CollectionTree.Add('%s')\n" % tmpInput)
    if flagMinBias:
        oFile.write('minBiasEventSelector = _Service( "minBiasEventSelector" )\n')
        oFile.write('minBiasEventSelector.InputCollections = %s\n' % minbiasFiles)
    if flagCavern:
        oFile.write('cavernEventSelector = _Service( "cavernEventSelector" )\n')
        oFile.write('cavernEventSelector.InputCollections = %s\n' % cavernFiles)
    if flagBeamHalo:
        oFile.write('BeamHaloEventSelector = _Service( "BeamHaloEventSelector" )\n')
        oFile.write('BeamHaloEventSelector.InputCollections = %s\n' % beamHaloFiles)
    if flagBeamGas:
        oFile.write('BeamGasEventSelector = _Service( "BeamGasEventSelector" )\n')
        oFile.write('BeamGasEventSelector.InputCollections = %s\n' % beamGasFiles)
    if 'hist' in outputFiles:
        oFile.write('HistogramPersistencySvc=_Service("HistogramPersistencySvc")\n')
        oFile.write('HistogramPersistencySvc.OutputFile = "%s"\n' % outputFiles['hist'])
    if 'ntuple' in outputFiles:
        oFile.write('NTupleSvc = _Service( "NTupleSvc" )\n')
        firstFlag = True
        for sName,fName in outputFiles['ntuple']:
            if firstFlag:
                firstFlag = False
                oFile.write('NTupleSvc.Output=["%s DATAFILE=\'%s\' OPT=\'NEW\'"]\n' % (sName,fName))
            else:
                oFile.write('NTupleSvc.Output+=["%s DATAFILE=\'%s\' OPT=\'NEW\'"]\n' % (sName,fName))
    oFile.write("""
_configs = []
seqList = []
pTmpStreamList = []
try:
    from AthenaCommon.AlgSequence import AlgSequence
    tmpKeys = AlgSequence().allConfigurables.keys()
    # get AlgSequences
    seqList = [AlgSequence()]
    try:
        for key in tmpKeys:
            # check if it is available via AlgSequence
            if not hasattr(AlgSequence(),key.split('/')[-1]):
                continue
            # get full name
            tmpConf = getattr(AlgSequence(),key.split('/')[-1])
            if hasattr(tmpConf,'getFullName'):
                tmpFullName = tmpConf.getFullName()
                # append AthSequencer
                if tmpFullName.startswith('AthSequencer/'):
                    seqList.append(tmpConf)
    except:
        pass
    # loop over all sequences
    for tmpAlgSequence in seqList:
        for key in tmpKeys:
            if key.find('/') != -1:
                key = key.split('/')[-1]
            if hasattr(tmpAlgSequence,key):    
                _configs.append(key)
except:
    pass

def _getConfig(key):
    if seqList == []:
        from AthenaCommon.AlgSequence import AlgSequence
        return getattr(AlgSequence(),key)
    else:
        for tmpAlgSequence in seqList:
            if hasattr(tmpAlgSequence,key):
                return getattr(tmpAlgSequence,key)

""")
    if 'RDO' in outputFiles:
        oFile.write("""
key = "StreamRDO"    
if key in _configs:
    StreamRDO = _getConfig( key )
else:
    StreamRDO = Algorithm( key )
""")
        oFile.write('StreamRDO.OutputFile = "%s"\n' % outputFiles['RDO'])
        oFile.write('pTmpStreamList.append(StreamRDO)\n')
    if 'ESD' in outputFiles:
        oFile.write("""
key = "StreamESD"    
if key in _configs:
    StreamESD = _getConfig( key )
else:
    StreamESD = Algorithm( key )
""")
        oFile.write('StreamESD.OutputFile = "%s"\n' % outputFiles['ESD'])
        oFile.write('pTmpStreamList.append(StreamESD)\n')
    if 'AOD' in outputFiles:
        oFile.write("""
key = "StreamAOD"    
if key in _configs:
    StreamAOD = _getConfig( key )
else:
    StreamAOD = Algorithm( key )
""")
        oFile.write('StreamAOD.OutputFile = "%s"\n' % outputFiles['AOD'])
        oFile.write('pTmpStreamList.append(StreamAOD)\n')
    if 'TAG' in outputFiles:
        oFile.write("""
key = "StreamTAG"    
if key in _configs:
    StreamTAG = _getConfig( key )
else:
    StreamTAG = Algorithm( key )
""")
        oFile.write('StreamTAG.OutputCollection = "%s"\n' % re.sub('\.root\.*\d*$','',outputFiles['TAG']))
    if 'AANT' in outputFiles:
        firstFlag = True
        oFile.write('THistSvc = _Service ( "THistSvc" )\n')
        sNameList = []
        for aName,sName,fName in outputFiles['AANT']:
            if not sName in sNameList:
                sNameList.append(sName)
                if firstFlag:
                    firstFlag = False
                    oFile.write('THistSvc.Output = ["%s DATAFILE=\'%s\' OPT=\'UPDATE\'"]\n' % (sName,fName))
                else:
                    oFile.write('THistSvc.Output += ["%s DATAFILE=\'%s\' OPT=\'UPDATE\'"]\n' % (sName,fName))
            oFile.write("""
key = "%s"
if key in _configs:
    AANTupleStream = _getConfig( key )
else:
    AANTupleStream = Algorithm( key )
""" % aName)
            oFile.write('AANTupleStream.StreamName = "%s"\n' % sName)
            oFile.write('AANTupleStream.OutputName = "%s"\n' % fName)
        if 'THIST' in outputFiles:
            for sName,fName in outputFiles['THIST']:
                oFile.write('THistSvc.Output += ["%s DATAFILE=\'%s\' OPT=\'UPDATE\'"]\n' % (sName,fName))
    else:
        if 'THIST' in outputFiles:
            oFile.write('THistSvc = _Service ( "THistSvc" )\n')
            firstFlag = True
            for sName,fName in outputFiles['THIST']:
                if firstFlag:
                    firstFlag = False
                    oFile.write('THistSvc.Output = ["%s DATAFILE=\'%s\' OPT=\'UPDATE\'"]\n' % (sName,fName))
                else:
                    oFile.write('THistSvc.Output+= ["%s DATAFILE=\'%s\' OPT=\'UPDATE\'"]\n' % (sName,fName))
    if 'Stream1' in outputFiles:
        oFile.write("""
key = "Stream1"    
if key in _configs:
    Stream1 = _getConfig( key )
else:
    try:
        Stream1 = getattr(theApp._streams,key)
    except:
        Stream1 = Algorithm( key )
""")
        oFile.write('Stream1.OutputFile = "%s"\n' % outputFiles['Stream1'])
        oFile.write('pTmpStreamList.append(Stream1)\n')
    if 'Stream2' in outputFiles:
        oFile.write("""
key = "Stream2"    
if key in _configs:
    Stream2 = _getConfig( key )
else:
    try:
        Stream2 = getattr(theApp._streams,key)
    except:
        Stream2 = Algorithm( key )
""")
        oFile.write('Stream2.OutputFile = "%s"\n' % outputFiles['Stream2'])
        oFile.write('pTmpStreamList.append(Stream2)\n')
        oFile.write("""
key = "%s_FH" % key
Stream2_FH = None
if key in _configs:
    Stream2_FH = _getConfig( key )
else:
    try:
        Stream2_FH = getattr(theApp._streams,key)
    except:
        pass
""")
        oFile.write("""
if Stream2_FH != None:
    Stream2_FH.OutputFile = "%s"
""" % outputFiles['Stream2'])

    if 'StreamG' in outputFiles:
        for stName,stFileName in outputFiles['StreamG']:
            oFile.write("""
key = "%s"    
if key in _configs:
    StreamX = _getConfig( key )
else:
    try:
        StreamX = getattr(theApp._streams,key)
    except:
        StreamX = Algorithm( key )
""" % stName)
            oFile.write('StreamX.OutputFile = "%s"\n' % stFileName)
            oFile.write('pTmpStreamList.append(StreamX)\n')
    if 'Meta' in outputFiles:
        for stName,stFileName in outputFiles['Meta']:
            oFile.write("""
key = "%s"    
if key in _configs:
    StreamX = _getConfig( key )
else:
    try:
        StreamX = getattr(theApp._streams,key)
    except:
        StreamX = Algorithm( key )
""" % stName)
            oFile.write('StreamX.OutputFile = "ROOTTREE:%s"\n' % stFileName)

    if 'UserData' in outputFiles:
        for stFileName in outputFiles['UserData']:
            oFile.write("""
try:
    # try new style
    userDataSvc = None
    try:
        for typeNameExtSvc in theApp.ExtSvc:
            if typeNameExtSvc.startswith('UserDataSvc/'):
                nameExtSvc = typeNameExtSvc.split('/')[-1]
                userDataSvc = getattr(theApp.serviceMgr(),nameExtSvc)
    except:
        pass
    # use old style
    if userDataSvc == None: 
        userDataSvc = _Service('UserDataSvc')
    # delete existing stream
    try:
       THistSvc = _Service ('THistSvc')
       tmpStreams = tuple(THistSvc.Output)
       newStreams = []
       for tmpStream in tmpStreams:
            # skip userstream since it is set by userDataSvc.OutputStream later
            if not userDataSvc.name() in tmpStream.split()[0]: 
                newStreams.append(tmpStream)
       THistSvc.Output = newStreams
    except:
        pass
    for tmpStream in pTmpStreamList:
        try:
            if tmpStream.OutputFile == '%s':
                userDataSvc.OutputStream = tmpStream
                break
        except:
            pass
except:
    pass
""" % stFileName)

    uniqueTag = str(uuid.uuid4())
    if 'BS' in outputFiles:
        oFile.write('ByteStreamEventStorageOutputSvc = _Service("ByteStreamEventStorageOutputSvc")\n')
        oFile.write('ByteStreamEventStorageOutputSvc.FileTag = "%s"\n' % uniqueTag)
        oFile.write("""
try:
    ByteStreamEventStorageOutputSvc.AppName = "%s"
except:
    pass
""" % uniqueTag)
        oFile.write('ByteStreamEventStorageOutputSvc.OutputDirectory = "./"\n')
    if fragmentJobO != "":
        oFile.write('%s\n' % fragmentJobO)

    # event picking
    if eventPickTxt != '':
        epRunEvtList = []
        epFH = open(eventPickTxt)
        iepNum = 0
        for epLine in epFH:
            items = epLine.split()
            if len(items) != 2 and len(items) != 3:
                continue
            # check range
            epSkipFlag = False
            if eventPickNum > 0:
                if iepNum < eventPickSt:
                    epSkipFlag = True
                if iepNum >= eventPickSt+eventPickNum:
                    epSkipFlag = True
            iepNum += 1
            if epSkipFlag:
                continue
            # append
            epRunEvtList.append((long(items[0]),long(items[1])))
        oFile.write("""
from AthenaCommon.AlgSequence import AthSequencer
seq = AthSequencer('AthFilterSeq')
from GaudiSequencer.PyComps import PyEvtFilter
seq += PyEvtFilter(
    'alg',
    evt_info='',
    )
seq.alg.evt_list = %s
seq.alg.filter_policy = 'accept'
for tmpStream in theApp._streams.getAllChildren():
    fullName = tmpStream.getFullName()
    if fullName.split('/')[0] == 'AthenaOutputStream':
        tmpStream.AcceptAlgs = [seq.alg.name()]
""" % str(epRunEvtList))

    oFile.close()

    # overwrite EventSelectorAthenaPool.InputCollections and AthenaCommon.AthenaCommonFlags.FilesInput for jobO level metadata extraction
    preOpt = 'pre_' + str(uuid.uuid4()) + '.py'
    oFile = open(preOpt,'w')
    if len(inputFiles) != 0 and mcData == '':
        if not byteStream:
            oFile.write("""      
try:
    from EventSelectorAthenaPool.EventSelectorAthenaPoolConf import EventSelectorAthenaPool
    orig_ESAP__getattribute =  EventSelectorAthenaPool.__getattribute__

    def _dummy(self,attr):
        if attr == 'InputCollections':
            return %s
        else:
            return orig_ESAP__getattribute(self,attr)

    EventSelectorAthenaPool.__getattribute__ = _dummy
    print ('Overwrite InputCollections')
except:
    try:
        EventSelectorAthenaPool.__getattribute__ = orig_ESAP__getattribute
    except:
        pass
""" % inputFiles)
        oFile.write("""      
try:
    import AthenaCommon.AthenaCommonFlags

    def _dummyFilesInput(*argv):
        return %s

    AthenaCommon.AthenaCommonFlags.FilesInput.__call__ = _dummyFilesInput
except:
    pass

try:
    import AthenaCommon.AthenaCommonFlags

    def _dummyGet_Value(*argv):
        return %s

    for tmpAttr in dir (AthenaCommon.AthenaCommonFlags):
        import re
        if re.search('^(Pool|BS).*Input$',tmpAttr) != None:
            try:
                getattr(AthenaCommon.AthenaCommonFlags,tmpAttr).get_Value = _dummyGet_Value
            except:
                pass
except:
    pass
""" % (inputFiles,inputFiles))
    # filter for verbose expansion
    try:
        oFile.write("""
try:
    from AthenaCommon.Include import excludeTracePattern
    excludeTracePattern.append('*/CLIDComps/clidGenerator.py')
    excludeTracePattern.append('*/PyUtils/decorator.py')
    excludeTracePattern.append('*/PyUtils/Decorators.py')
    excludeTracePattern.append('*/PyUtils/Helper*.py')
except:
    pass
""")
    except Exception:
        pass
    # for SummarySvc
    oFile.write("""      
try:
    from AthenaServices.SummarySvc import *
    useAthenaSummarySvc()
except:
    pass
""")

    oFile.close()

    # dump

    print ("=== pre jobO ===")
    oFile = open(preOpt)
    lines = ''
    for line in oFile:
        lines += line
    print (lines)
    oFile.close()
    print ('')

    print ("=== post jobO ===")
    oFile = open(postOpt)
    lines = ''
    for line in oFile:
        lines += line
    print (lines)
    oFile.close()

    # replace theApp.initialize when using theApp.nextEvent
    if useNextEvent:
        initOpt = 'init_' + str(uuid.uuid4()) + '.py'
        initFile = open(initOpt,'w')
        initFile.write("""
origTheAppinitialize = theApp.initialize                   
def fakeTheAppinitialize():
    include('%s')
    origTheAppinitialize()
theApp.initialize = fakeTheAppinitialize    
""" % postOpt)
        initFile.close()

        print ("=== init jobO ===")
        iFile = open(initOpt)
        lines = ''
        for line in iFile:
            lines += line
        print (lines)
        iFile.close()

        # modify jobO
        print ("=== change jobO ===")
        newJobO = ''
        startPy = False
        for item in jobO.split():
            if (not startPy) and item.endswith('.py'):
                newJobO += (" " + initOpt)
                startPy = True
            newJobO += (" " + item)
        print ("  Old : " + jobO)
        print ("  New : " + newJobO)
        jobO = newJobO

    # change %IN for TRF with TAGs
    if runTrf and directIn:
        print ("=== change jobO for TRF + directIn ===")
        newJobO = jobO
        for tmpName in inputFiles:
            newJobO = re.sub('(?P<term> |=|\'|\"|,){0}'.format(os.path.basename(tmpName)),
                             '\g<term>{0}'.format(tmpName), newJobO)
        print ("  Old : " + jobO)
        print ("  New : " + newJobO)
        print ("")
        jobO = newJobO

    # change output names
    if runTrf and 'IROOT' in outputFiles:
        print("=== change jobO for TRF outputs ===")
        newJobO = jobO
        newList = []
        for src_name, dst_name in outputFiles['IROOT']:
            if '*' not in src_name:
                oldJobO = newJobO
                newJobO = re.sub(r'(?P<term1>=| |"|\')'+src_name+r'(?P<term2> |"|\'|,|;|$)',
                                 r'\g<term1>'+dst_name+r'\g<term2>', oldJobO)
                if newJobO != oldJobO:
                    src_name = dst_name
            newList.append((src_name, dst_name))
        outputFiles['IROOT'] = newList
        print("          Old : " + jobO)
        print("          New : " + newJobO)
        print("  outputFiles : {0}".format(str(outputFiles)))
        print("")
        jobO = newJobO

    # get PDGTABLE.MeV
    commands_get_status_output('get_files PDGTABLE.MeV')

    # temporary output to avoid MemeoryError
    tmpOutput = 'tmp.stdout.%s' % str(uuid.uuid4())
    tmpStderr = 'tmp.stderr.%s' % str(uuid.uuid4())

    # construct command
    if not useCMake:
        # append workdir to CMTPATH
        env = 'CMTPATH=%s:$CMTPATH' % workDir
        com = 'export %s;' % env
    else:
        com = ''
    # local RAC
    if 'ATLAS_CONDDB' not in os.environ or os.environ['ATLAS_CONDDB']=='to.be.set':
        if 'OSG_HOSTNAME' in os.environ:
            com += 'export ATLAS_CONDDB=%s;' % os.environ['OSG_HOSTNAME']
        elif 'GLOBUS_CE' in os.environ:
            tmpCE = os.environ['GLOBUS_CE'].split('/')[0]
            # remove port number
            tmpCE = re.sub(':\d+$','',tmpCE)
            com += 'export ATLAS_CONDDB=%s;' % tmpCE
        elif 'PBS_O_HOST' in os.environ:
            com += 'export ATLAS_CONDDB=%s;' % os.environ['PBS_O_HOST']
    if not useCMake:
        com += 'cd %s;' % cmtDir
        com += 'echo -e "use AtlasPolicy AtlasPolicy-*\nuse PathResolver PathResolver-* Tools\n" > requirements;'
        com += 'cmt config;'
        com += 'source ./setup.sh;'
        com += 'export TestArea=%s;' % workDir
        com += 'cd -;env;'
    else:
        cmakeSetupDir = 'usr/*/*/InstallArea/*'
        print("=== CMake setup ===")
        print ("setup dir : {0}".format(cmakeSetupDir))
        if len(glob.glob(cmakeSetupDir)) > 0:
            com += 'source {0}/setup.sh;'.format(cmakeSetupDir)
        else:
            print ('WARNING: CMake setup dir not found')
        com += 'env;'
    thrStr = ''
    if useAthenaMT:
        if 'ATHENA_PROC_NUMBER' in os.environ:
            thrStr = '--threads={0} '.format(os.environ['ATHENA_PROC_NUMBER'])
        else:
            thrStr = '--threads=1 '
    if (not runTrf) and dbrFile == '':
        # unset ATHENA_PROC_NUMBER for AthenaMT
        if useAthenaMT:
            com += 'unset ATHENA_PROC_NUMBER; '
        # run Athena
        com += 'athena.py '
        if codeTrace:
            com += '-s '
        if useAthenaMT:
            com += thrStr
        com += tweak_job_options(jobO, preOpt, postOpt)
    elif dbrFile != '' and not noExpandDBR:
        # run setup.py and athena.py in a python
        tmpTrfName = 'trf.%s.py' % str(uuid.uuid4())
        tmpTrfFile = open(tmpTrfName,'w')
        tmpTrfFile.write(dbrSetupStr)
        if not runTrf:
            tmpTrfFile.write('import os\n')
            if useAthenaMT:
                tmpTrfFile.write("""if 'ATHENA_PROC_NUMBER' in os.environ:
    del os.environ['ATHENA_PROC_NUMBER']\n""")
            tmpTrfFile.write('import sys\nstatus=os.system("""athena.py ')
            if codeTrace:
                tmpTrfFile.write('-s ')
            if useAthenaMT:
                tmpTrfFile.write(thrStr)
            tmpTrfFile.write('%s""")\n' % tweak_job_options(jobO, preOpt, postOpt))
        else:
            tmpTrfFile.write("""if 'DBRELEASE' in os.environ:
    os.environ['DBRELEASE_REQUESTED'] = os.environ['DBRELEASE']\n""")
            tmpTrfFile.write('import sys\nstatus=os.system("""%s""")\n' % jobO)
        tmpTrfFile.write('status %= 255\nsys.exit(status)\n\n')
        tmpTrfFile.close()
        com += 'echo;echo ==== TRF BEGIN ====;cat %s;echo ===== TRF END ====;echo;python -u %s' % (tmpTrfName,tmpTrfName)
    else:
        # replace core counts
        jobO = re.sub("%PROC_NUMBER", str(os.environ.get("ATHENA_PROC_NUMBER", 1)), jobO)
        jobO = re.sub("%CORE_NUMBER", str(os.environ.get("ATHENA_CORE_NUMBER", 1)), jobO)
        # run transformation
        com += '%s' % jobO

if not postprocess:
    if preprocess:
        runExecName = os.path.join(currentDir, '__run_main_exec.sh')
        with open(runExecName, 'w') as f:
            f.write(com)
        commands_get_status_output('chmod +x {0}'.format(runExecName))
        print ("\n==== Result ====")
        print ("produced {0}\n".format(runExecName))
        with open(runExecName) as f:
            print (f.read())
        print ("preprocessing successfully done")
        sys.exit(0)

    print ("\n=== execute ===")
    print (com)
    # run athena
    if not debugFlag:
        # write stdout to tmp file
        com += ' > %s 2> %s' % (tmpOutput,tmpStderr)
        status,out = commands_get_status_output(com)
        print (out)
        statusChanged = False
        try:
            tmpOutFile = open(tmpOutput)
            for line in tmpOutFile:
                print (line[:-1])
                # set status=0 for AcerMC
                if re.search('ACERMC TERMINATES NORMALY: NO MORE EVENTS IN FILE',line) != None:
                    status = 0
                    statusChanged = True
            tmpOutFile.close()
        except Exception:
            pass
        if statusChanged:
            print ("\n\nStatusCode was overwritten for AcerMC\n")
        try:
            tmpErrFile = open(tmpStderr)
            for line in tmpErrFile:
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

print ('')
print ("=== list in run dir ===")
print (commands_get_status_output('ls -l')[-1])

# rename or archive iROOT files
if 'IROOT' in outputFiles:
    for iROOT in outputFiles['IROOT']:
        if iROOT[0].find('*') != -1:
            # archive *
            commands_get_status_output('tar cvfz %s %s' % (iROOT[-1],iROOT[0]))
        else:
            src_name, dst_name = iROOT
            if src_name == dst_name:
                continue
            # rename 
            commands_get_status_output('mv %s %s' % iROOT)
        # modify PoolFC.xml
        pfcName = 'PoolFileCatalog.xml'
        try:
            pLines = ''
            pFile = open(pfcName)
            for line in pFile:
                # replace file name
                line = re.sub('"%s"' % iROOT[0],'"%s"' % iROOT[-1],line)
                pLines += line
            pFile.close()
            # overwrite
            pFile = open(pfcName,'w')
            pFile.write(pLines)
            pFile.close()
        except:
            pass
        # modify jobReport.json
        jsonName = 'jobReport.json'
        try:
            pLines = ''
            pFile = open(jsonName)
            for line in pFile:
                # replace file name
                line = re.sub('"%s"' % iROOT[0],'"%s"' % iROOT[-1],line)
                pLines += line
            pFile.close()
            # overwrite
            pFile = open(jsonName,'w')
            pFile.write(pLines)
            pFile.close()
        except:
            pass

# rename TAG files
if 'TAG' in outputFiles:
    woAttrNr = re.sub('\.\d+$','',outputFiles['TAG'])
    if woAttrNr != outputFiles['TAG']:
        print (commands_get_status_output('mv %s %s' % (woAttrNr,outputFiles['TAG']))[-1])
    # since 13.0.30 StreamTAG doesn't append .root automatically
    woRootAttrNr = re.sub('\.root\.*\d*$','',outputFiles['TAG'])
    if woRootAttrNr != outputFiles['TAG']:
        print (commands_get_status_output('mv %s %s' % (woRootAttrNr,outputFiles['TAG']))[-1])

# rename BS file
if 'BS' in outputFiles:
    bsS,bsO = commands_get_status_output('mv daq.%s* %s' % (uniqueTag,outputFiles['BS']))
    print (bsS,bsO)
    if bsS != 0:
        print (commands_get_status_output('mv data_test.*%s* %s' % (uniqueTag,outputFiles['BS']))[-1])
    
# copy results
missing_output_msg = None
for file in outputFiles.values():
    if not isinstance(file, basestring):
        # for AANT
        for aaT in file:
            tmp_file_name = aaT[-1]
            if not os.path.exists(tmp_file_name):
                err_msg = "expected output {0} is missing".format(tmp_file_name)
                missing_output_msg = err_msg
                if missing_output_msg is not None:
                    break
            commands_get_status_output('mv %s %s' % (tmp_file_name,currentDir))
    else:
        if not os.path.exists(file):
            err_msg = "expected output {0} is missing".format(file)
            missing_output_msg = err_msg
            break
        commands_get_status_output('mv %s %s' % (file,currentDir))

# copy PoolFC.xml
commands_get_status_output('mv -f PoolFileCatalog.xml %s' % currentDir)

# copy AthSummary.txt
commands_get_status_output('mv -f AthSummary.txt %s' % currentDir)

# copy useful files
for patt in ['runargs.*','runwrapper.*','jobReport.json','log.*']:
    commands_get_status_output('mv -f %s %s' % (patt,currentDir))

# make tarball of log files in sub-dirs
make_log_tarball_in_sub_dirs(os.path.join(currentDir, 'log.in_subdirs.tgz'))

# go back to current dir
os.chdir(currentDir)

print ('')
print ("=== list in top dir ===")
print (commands_get_status_output('pwd')[-1])
print (commands_get_status_output('ls -l')[-1])

# remove work dir
if not debugFlag:
    commands_get_status_output('rm -rf %s' % workDir)

# return
print ('')
print ("=== result ===")
print(datetime.datetime.utcnow())
if status:
    err_msg = "athena execution failed with {0}".format(status)
    print ("execute script: Running athena failed : %d" % status)
    EC_AthenaFail.exit(err_msg)
elif missing_output_msg is not None:
    print("payload execution succeeded, but some output files are missing")
    EC_MissingOutput.exit(missing_output_msg)
else:
    print ("execute script: Running athena was successful")
    sys.exit(0)
