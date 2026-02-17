#!/bin/bash

"exec" "python" "-u" "$0" "$@"
import json
import os
import re
import sys
import ast
import base64
import getopt
import glob
import uuid
import datetime
import shutil
import gzip
import xml.dom.minidom
try:
    import urllib.request as urllib
except ImportError:
    import urllib
from pandawnutil.wnmisc.misc_utils import commands_get_status_output, get_file_via_http, record_exec_directory,\
    propagate_missing_sandbox_error
from pandawnutil.root import root_utils
from pandawnutil.wnmisc.error_codes import ErrorCodes
from pandawnutil.build_timestamp import build_timestamp

# error code
EC = ErrorCodes('runGen')
EC_MissingArg  = EC.MISSING_ARGUMENT
EC_NoInput     = EC.ALL_INPUT_UNAVAILABLE
EC_Tarball     = EC.CORRUPTED_TARBALL
EC_DBRelease   = EC.DB_RELEASE_FAILURE
EC_WGET        = EC.FAILED_TO_GET_TARBALL
EC_MissingOutput = EC.OUTPUT_MISSING
EC_PayloadFailure = EC.PAYLOAD_FAILURE

print ("=== start with build timestamp: %s" % build_timestamp)
print(datetime.datetime.utcnow())

debugFlag    = False
libraries    = ''
outputFiles  = {}
jobParams    = ''
inputFiles   = []
inputGUIDs   = []
oldPrefix    = ''
newPrefix    = ''
directIn     = False
usePFCTurl   = False
lfcHost      = ''
givenPFN     = False
envvarFile   = ''
liveLog      = ''
sourceURL    = 'https://gridui07.usatlas.bnl.gov:25443'
inMap        = {}
archiveJobO  = ''
useAthenaPackages = False
dbrFile      = ''
dbrRun       = -1
notExpandDBR = False
skipInputByRetry = []
writeInputToTxt = ''
rootVer   = ''
cmtConfig = ''
useRootCore = False
useMana   = False
manaVer   = ''
useCMake  = False
preprocess = False
postprocess = False
execWithRealFileNames = False
fileToSave = ''
fileToLoad = ''

# command-line parameters
opts, args = getopt.getopt(sys.argv[1:], "i:o:r:j:l:p:u:a:",
                           ["pilotpars","debug","oldPrefix=","newPrefix=",
                            "directIn","sourceURL=","lfcHost=","envvarFile=",
                            "inputGUIDs=","liveLog=","inMap=",
                            "useAthenaPackages",
                            "dbrFile=","dbrRun=","notExpandDBR",
                            "useFileStager", "usePFCTurl", "accessmode=",
                            "skipInputByRetry=","writeInputToTxt=",
                            "rootVer=", "enable-jem", "jem-config=", "cmtConfig=",
                            "mergeOutput","mergeType=","mergeScript=",
                            "useRootCore","givenPFN","useMana","manaVer=",
                            "useCMake", "preprocess", "postprocess", "execWithRealFileNames",
                            "fileToSave=", "fileToLoad="
                            ])
for o, a in opts:
    if o == "-l":
        libraries=a
    if o == "-j":
        scriptName=a
    if o == "-r":
        runDir=a
    if o == "-p":
        jobParams=urllib.unquote(a)
    if o == "-i":
        inputFiles = ast.literal_eval(a)
    if o == "-o":
        outputFiles = ast.literal_eval(a)
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
    if o == "--lfcHost":
        lfcHost = a
    if o == "--liveLog":
        liveLog = a
    if o == "--sourceURL":
        sourceURL = a
    if o == "--inMap":
        inMap = ast.literal_eval(a)
    if o == "-a":
        archiveJobO = a
    if o == "--useAthenaPackages":
        useAthenaPackages = True
    if o == "--dbrFile":
        dbrFile = a
    if o == "--dbrRun":
        dbrRun = a
    if o == "--notExpandDBR":
        notExpandDBR = True
    if o == "--usePFCTurl":
        usePFCTurl = True
    if o == "--skipInputByRetry":
        skipInputByRetry = a.split(',')
    if o == "--writeInputToTxt":
        writeInputToTxt = a
    if o == "--rootVer":
        rootVer = a
    if o == "--cmtConfig":
        cmtConfig = a
    if o == "--useRootCore":
        useRootCore = True
    if o == "--givenPFN":
        givenPFN = True
    if o == "--useMana":
        useMana = True
    if o == "--manaVer":
        manaVer = a
    if o == "--useCMake":
        useCMake = True
    if o == "--preprocess":
        preprocess = True
    if o == "--postprocess":
        postprocess = True
    if o == "--execWithRealFileNames":
        execWithRealFileNames = True
    if o == '--fileToLoad':
        fileToLoad = a
    if o == '--fileToSave':
        fileToSave = a

# dump parameter
try:
    print ("=== parameters ===")
    print ("libraries",libraries)
    print ("runDir",runDir)
    print ("jobParams",jobParams)
    print ("inputFiles",inputFiles)
    print ("scriptName",scriptName)
    print ("outputFiles",outputFiles)
    print ("inputGUIDs",inputGUIDs)
    print ("oldPrefix",oldPrefix)
    print ("newPrefix",newPrefix)
    print ("directIn",directIn)
    print ("usePFCTurl",usePFCTurl)
    print ("lfcHost",lfcHost)
    print ("debugFlag",debugFlag)
    print ("liveLog",liveLog)
    print ("sourceURL",sourceURL)
    print ("inMap",inMap)
    print ("useAthenaPackages",useAthenaPackages)
    print ("archiveJobO",archiveJobO)
    print ("dbrFile",dbrFile)
    print ("dbrRun",dbrRun)
    print ("notExpandDBR",notExpandDBR)
    print ("skipInputByRetry",skipInputByRetry)
    print ("writeInputToTxt",writeInputToTxt)
    print ("rootVer",rootVer)
    print ("cmtConfig",cmtConfig)
    print ("useRootCore",useRootCore)
    print ("givenPFN",givenPFN)
    print ("useMana",useMana)
    print ("manaVer",manaVer)
    print ("useCMake",useCMake)
    print ("preprocess", preprocess)
    print ("postprocess", postprocess)
    print ("execWithRealFileNames", execWithRealFileNames)
    print ("fileToLoad", fileToLoad)
    print ("fileToSave", fileToSave)
    print ("===================")
except Exception as e:
    print ('ERROR: missing parameters : %s' % str(e))
    EC_MissingArg.exit("Failed to parse command-line arguments. Please check the input parameters.")

# save current dir
currentDir = record_exec_directory()
currentDirFiles = os.listdir('.')

# work dir
workDir = currentDir+"/workDir"

# create work dir
if not postprocess:
    commands_get_status_output('rm -rf %s' % workDir)
    os.makedirs(workDir)

    # collect GUIDs from PoolFileCatalog
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
            # append
            directTmpTurl[id] = pfn
    except Exception as e:
        print ('ERROR : Failed to collect GUIDs : %s' % str(e))

os.chdir(workDir)

# preprocess or single-step execution
if not postprocess:
    # add secondary files if missing
    for tmpToken in inMap:
        tmpList = inMap[tmpToken]
        for inputFile in tmpList:
            if not inputFile in inputFiles:
                inputFiles.append(inputFile)
    # remove duplication while keeping order
    seen = set()
    unique = []
    for x in inputFiles:
        if x not in seen:
            seen.add(x)
            unique.append(x)
    inputFiles = unique
    print ('')
    print ("===== inputFiles with inMap =====")
    print ("inputFiles",inputFiles)
    print ('')

    # remove skipped files
    if skipInputByRetry != []:
        tmpInputList = []
        for tmpLFN in inputFiles:
            if not tmpLFN in skipInputByRetry:
                tmpInputList.append(tmpLFN)
        inputFiles = tmpInputList
        print ("removed skipped files -> %s"% str(inputFiles))

    # scan LFC/LRC for direct reading
    if (directIn or preprocess) and not givenPFN:
        # Use the TURLs from PoolFileCatalog.xml created by pilot
        print ("===== GUIDs and TURLs in PFC =====")
        print (directTmpTurl)
        directTmp = directTmpTurl
        # collect LFNs
        directPFNs = {}
        for id in directTmp.keys():
            lfn = directTmp[id].split('/')[-1]
            lfn = re.sub('__DQ2-\d+$','',lfn)
            lfn = re.sub('^([^:]+:)','', lfn)
            lfn = re.sub('\?site.*$','', lfn)
            lfn = re.sub('\?select.*$','', lfn)
            lfn = re.sub('\?GoogleAccessId.*$','', lfn)
            lfn = re.sub('\?X-Amz-Algorithm.*$', '', lfn)
            directPFNs[lfn] = directTmp[id]

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
        EC_Tarball.exit("tarball {0} is corrupted".format(libraries))

    # expand jobOs if needed
    if archiveJobO != "" and (useAthenaPackages or libraries == ''):
        print ('')
        print ("=== getting sandbox ===")
        url = '%s/cache/%s' % (sourceURL, archiveJobO)
        tmpStat, tmpOut = get_file_via_http(full_url=url)
        if not tmpStat:
            print ("ERROR : " + tmpOut)
            propagate_missing_sandbox_error()
            EC_WGET.exit("Failed to download tarball from %s" % url)
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s' % archiveJobO)
        print (tmpOut)
        if tmpStat != 0:
            print ("ERROR : {0} is corrupted".format(archiveJobO))
            EC_Tarball.exit("tarball {0} is corrupted".format(archiveJobO))

    # create cmt dir to setup Athena
    setupEnv = ''
    if useAthenaPackages:
        if not useCMake:
            tmpDir = '%s/%s/cmt' % (workDir, str(uuid.uuid4()))
            print ("Making tmpDir",tmpDir)
            os.makedirs(tmpDir)
            # create requirements
            oFile = open(tmpDir+'/requirements','w')
            oFile.write('use AtlasPolicy AtlasPolicy-*\n')
            oFile.close()
            # setup command
            setupEnv  = 'export CMTPATH=%s:$CMTPATH; ' % workDir
            setupEnv += 'cd %s; cmt config; source ./setup.sh; cd -; ' % tmpDir
        else:
            cmakeSetupDir = 'usr/*/*/InstallArea/*'
            print ("CMake setup dir : {0}".format(cmakeSetupDir))
            if len(glob.glob(cmakeSetupDir)) > 0:
                setupEnv = 'source {0}/setup.sh;'.format(cmakeSetupDir)
            else:
                print ('WARNING: CMake setup dir not found')
                setupEnv = ''
            setupEnv += 'env;'

    # setup root
    if rootVer != '':
        rootBinDir = workDir + '/pandaRootBin'
        # use setup script if available
        if os.path.exists('%s/pandaUseCvmfSetup.sh' % rootBinDir):
            with open('%s/pandaUseCvmfSetup.sh' % rootBinDir) as iFile:
                tmpSetupEnvStr = iFile.read()
        else:
            rootCVMFS, tmpSetupEnvStr = root_utils.get_version_setup_string(rootVer, cmtConfig)
        setupEnv += tmpSetupEnvStr
        setupEnv += ' root.exe -q;'

    # RootCore
    if useRootCore:
        pandaRootCoreWD = os.path.abspath(runDir+'/__panda_rootCoreWorkDir')
        setupEnv += 'source %s/RootCore/scripts/grid_run.sh %s; ' % (pandaRootCoreWD,pandaRootCoreWD)

    # TestArea
    setupEnv += "export TestArea=%s; " % workDir

# use tracer only for single-step execution
rTracer = None
if not preprocess and not postprocess and 'unset LD_PRELOAD' not in jobParams:
    # Tracer On
    try:
        from pandawnutil.tracer import RunTracer
        rTracer = RunTracer.RunTracer()
        rTracer.make()
        setupEnv += rTracer.getEnvVar()
    except:
        pass

# make rundir just in case
commands_get_status_output('mkdir %s' % runDir)
# go to run dir
os.chdir(runDir)

# preprocess or single-step execution
secrets_source = None
if not postprocess:
    # move secrets
    secrets_name = 'panda_secrets.json'
    secrets_path = os.path.join(currentDir, secrets_name)
    if os.path.exists(secrets_path):
        # parse secrets
        try:
            try:
                with open(secrets_path) as f:
                    secrets_data = json.load(f)
            except Exception as e:
                print("\nWARNING: json.load secrets failed with {0}\n".format(str(e)))
                try:
                    with open(secrets_path) as f:
                        secrets_data = ast.literal_eval(f.read())
                except Exception as e:
                    print("\nWARNING: ast.literal_eval secrets failed with {0}\n".format(str(e)))
                    raise Exception('parsing failures')
            if secrets_data:
                secrets_source = os.path.join(runDir, 'panda_secrets.sh')
                set_secret_env = False
                with open(secrets_source, 'w') as secrets_source_file:
                    for k in secrets_data:
                        v = secrets_data[k]
                        # secret file
                        if k.startswith('___file___:'):
                            k = re.sub('^___file___:', '', k)
                            with open(k, 'wb') as f:
                                f.write(base64.b64decode(v))
                        else:
                            # export key-value as an env variable
                            v = v.replace(r'"', r'\"')
                            secrets_source_file.write('export {0}="{1}"\n'.format(k, v))
                            set_secret_env = True
                # not use source if no env variable is set
                if not set_secret_env:
                    secrets_source = None
        except Exception as e:
            print("\nERROR: failed to parse secrets with {0}\n".format(str(e)))
        os.rename(secrets_path, os.path.join(runDir, secrets_name))
    # customize .rootrc in the current dir and HOME
    rootRcDirs = [runDir]
    if 'HOME' in os.environ:
        #rootRcDirs.append(os.environ['HOME'])
        pass
    # the number of PROOF workers
    numProofWokers = 1
    if 'ATHENA_PROC_NUMBER' in os.environ:
        numProofWokers = os.environ['ATHENA_PROC_NUMBER']
    for rootRcDir in rootRcDirs:
        try:
            from pandawnutil.root import RootRC
            RootRC.customizeRootRC(rootRcDir,numProofWokers)
            print ("\n=== dump %s/.rootrc ===" % rootRcDir)
            print (RootRC.dumpRootRC(rootRcDir))
        except:
            pass

    # check input files
    inputFileMap = {}
    if inputFiles != [] and not givenPFN:
        print ("=== check input files ===")
        newInputs = []
        for inputFile in inputFiles:
            # direct reading
            foundFlag = False
            if directIn or (preprocess and not os.path.exists(os.path.join(currentDir,inputFile))):
                if inputFile in directPFNs:
                    newInputs.append(directPFNs[inputFile])
                    foundFlag = True
                    inputFileMap[inputFile] = directPFNs[inputFile]
            else:
                # make symlinks to input files
                if inputFile in currentDirFiles:
                    if preprocess:
                        os.symlink(os.path.relpath(os.path.join(currentDir, inputFile), os.getcwd()), inputFile)
                    else:
                        os.symlink('%s/%s' % (currentDir, inputFile), inputFile)
                    newInputs.append(inputFile)
                    foundFlag = True
                    inputFileMap[inputFile] = inputFile
            if not foundFlag:
                print ("%s not exist" % inputFile)
        inputFiles = newInputs
        if len(inputFiles) == 0:
            print ("ERROR : No input file is available")
            EC_NoInput.exit()
        print ("=== New inputFiles ===")
        print (inputFiles)


    # setup DB/CDRelease
    dbrSetupStr = ''
    if dbrFile != '':
        if notExpandDBR:
            # just make a symlink
            if preprocess:
                os.symlink(os.path.relpath(os.path.join(currentDir, dbrFile), os.getcwd()), dbrFile)
            else:
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
                print ("ERROR : could not find setup.py in %s" % dbrFile)
                EC_DBRelease.exit()
            # run setup.py
            dbrSetupStr  = "import os\nos.chdir('%s')\nexecfile('setup.py',{})\nos.chdir('%s')\n" % \
                           (tmpSetupDir,os.getcwd())
            dbrSetupStr += "import sys\nsys.stdout.flush()\nsys.stderr.flush()\n"


    # add current dir to PATH
    os.environ['PATH'] = '.:'+os.environ['PATH']

    print ("\n=== env variables ===")
    if dbrFile != '' and dbrSetupStr != '':
        # change env by DBR
        tmpTrfName = 'trf.%s.py' % str(uuid.uuid4())
        tmpTrfFile = open(tmpTrfName,'w')
        tmpTrfFile.write(dbrSetupStr)
        tmpTrfFile.write('import sys\nstatus=os.system("""env""")\n')
        tmpTrfFile.close()
        print (commands_get_status_output(setupEnv+'python -u '+tmpTrfName)[-1])
    else:
        print (commands_get_status_output(setupEnv+'env')[-1])
    print ('')

    # put ROOT.py to avoid a crash caused by long argument at direct access site
    commands_get_status_output('rm ROOT.py')

    # load file
    if fileToLoad:
        print("\n=== loading file ===")
        fileToLoadDst, fileToLoadSrc = fileToLoad.split(':')
        print('{0} -> {1}'.format(fileToLoadSrc, fileToLoadDst))
        url = '%s/cache/%s' % (sourceURL, fileToLoadSrc)
        tmpStat, tmpOut = get_file_via_http(full_url=url, force_access=True)
        if not tmpStat:
            print("ERROR: failed to load {0} : {1}".format(fileToLoadDst, tmpOut))
        else:
            with gzip.open(fileToLoadSrc, 'rb') as f_in, open(fileToLoadDst, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print('')

    print ("=== ls %s ===" % runDir)
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
            inStr = ''
            for inputFile in inputFiles:
                inStr += "%s," % inputFile
            inStr = inStr[:-1]
            # replace
            newJobParams = newJobParams.replace('%IN',inStr)
            # write to file
            tmpKeyName = 'IN'
            if tmpKeyName in writeInputToTxtMap:
                commands_get_status_output('rm -f %s' % writeInputToTxtMap[tmpKeyName])
                tmpInFile = open(writeInputToTxtMap[tmpKeyName],'w')
                tmpInFile.write(inStr)
                tmpInFile.close()
                print ("%s to %s : %s" % (tmpKeyName,writeInputToTxtMap[tmpKeyName],inStr))
        else:
            # multiple inputs
            for tmpToken in inMap:
                tmpList = inMap[tmpToken]
                inStr = ''
                for inputFile in tmpList:
                    if inputFile in inputFileMap:
                        inStr += "%s," % inputFileMap[inputFile]
                inStr = inStr[:-1]
                # replace
                newJobParams = re.sub('%'+tmpToken+'(?P<sname> |$|\"|\'|,)',inStr+'\g<sname>',newJobParams)
                # write to file
                tmpKeyName = tmpToken
                if tmpKeyName in writeInputToTxtMap:
                    commands_get_status_output('rm -f %s' % writeInputToTxtMap[tmpKeyName])
                    tmpInFile = open(writeInputToTxtMap[tmpKeyName],'w')
                    tmpInFile.write(inStr)
                    tmpInFile.close()
                    print ("%s to %s : %s" % (tmpKeyName,writeInputToTxtMap[tmpKeyName],inStr))
        if writeInputToTxtMap != {}:
            print ('')
    # replace core counts
    newJobParams = re.sub("%CORE_NUMBER", str(os.environ.get("ATHENA_CORE_NUMBER", 1)), newJobParams)
    newJobParams = re.sub("%PROC_NUMBER", str(os.environ.get("ATHENA_PROC_NUMBER", 1)), newJobParams)
    # replace output filenames
    if execWithRealFileNames:
        newOutputFiles = {}
        # use real output filenames
        for src_name in outputFiles:
            dst_name = outputFiles[src_name]
            if '*' not in src_name:
                oldJobO = newJobParams
                newJobParams = re.sub(r'(?P<term1>=| |"|\'|>)'+src_name+r'(?P<term2> |"|\'|,|;|$)',
                                      r'\g<term1>'+dst_name+r'\g<term2>', oldJobO)
                if newJobParams != oldJobO:
                    src_name = dst_name
            newOutputFiles[src_name] = dst_name
        outputFiles = newOutputFiles
        print("=== change exec with real outputs ===")
        print("          New : " + newJobParams)
        print("  outputFiles : {}\n".format(str(outputFiles)))

    # construct command
    com = setupEnv
    if preprocess:
        tmpTrfName = os.path.join(currentDir, '__run_main_exec.sh')
    else:
        tmpTrfName = 'trf.%s.py' % str(uuid.uuid4())
    tmpTrfFile = open(tmpTrfName,'w')
    if dbrFile != '' and dbrSetupStr != '':
        tmpTrfFile.write(dbrSetupStr)
    if preprocess:
        tmpTrfFile.write('cd {0}\n'.format(os.path.relpath(os.getcwd(), currentDir)))
        tmpTrfFile.write(setupEnv)
        if 'X509_USER_PROXY' in os.environ:
            tmpTrfFile.write('\nif [ -z "$X509_USER_PROXY" ]\nthen\n  export X509_USER_PROXY={0}\nfi\n'.format(
                os.path.join('/scratch/', os.path.basename(os.environ['X509_USER_PROXY']))))
        if 'X509_CERT_DIR' in os.environ:
            tmpTrfFile.write('\nif [ -z "$X509_CERT_DIR" ]\nthen\n  export X509_CERT_DIR={0}\nfi\n'.format(
                os.environ['X509_CERT_DIR']))
        tmpTrfFile.write('export PATH=$PATH:.\n')
        tmpTrfFile.write('echo\necho ==== env ====\nenv\necho\necho ==== start ====\n')
        if secrets_source:
            tmpTrfFile.write('source {0}\n'.format(secrets_source))
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
        print ("produced {0}\n".format(tmpTrfName))
        with open(tmpTrfName) as f:
            print (f.read())
        print ("preprocessing successfully done")
        sys.exit(0)

    if secrets_source:
        com += 'source {0}\n'.format(secrets_source)
    com += 'cat %s;python -u %s' % (tmpTrfName,tmpTrfName)

    # temporary output to avoid MemeoryError
    tmpOutput = 'tmp.stdout.%s' % str(uuid.uuid4())
    tmpStderr = 'tmp.stderr.%s' % str(uuid.uuid4())

    print ("=== execute ===")
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
    # set 0 for postprocess
    status = 0

print ('')
print ("=== ls in run dir : %s ===" % runDir)
print (commands_get_status_output('ls -l')[-1])
print ('')

if fileToSave:
    print("\n=== saving file ===")
    fileToSaveSrc, fileToSaveDst = fileToSave.split(':')
    if not os.path.exists(fileToSaveSrc):
        print('skip since {0} is missing'.format(fileToSaveSrc))
    else:
        print('{0} -> {1} on {2}'.format(fileToSaveSrc, fileToSaveDst, sourceURL))
        with open(fileToSaveSrc, 'rb') as f_in, gzip.open(fileToSaveDst, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        if 'X509_USER_PROXY' in os.environ:
            certfile = os.environ['X509_USER_PROXY']
        else:
            certfile = '/tmp/x509up_u{0}'.format(os.getuid())
        url = sourceURL + '/server/panda/putFile'
        tmpDump = '__saveDump.out'
        tmpStat, tmpOut = get_file_via_http(file_name=tmpDump, full_url=url,
                                            filename_to_upload=fileToSaveDst, force_access=True,
                                            certfile=certfile, keyfile=certfile)
        print('status={0} {1}'.format(tmpStat, tmpOut))
        if not tmpStat:
            print('ERROR: failed to save {0}'.format(fileToSaveSrc))
        with open(tmpDump) as f:
            print('out=' + str(f.read()))
        print('')

# rename output files
missing_output_msg = None
for oldName in outputFiles:
    newName = outputFiles[oldName]
    if oldName.startswith('regex|'):
        continue
    elif oldName.find('*') != -1:
        # archive *
        print (commands_get_status_output('tar cvfz %s %s' % (newName,oldName))[-1])
    else:
        if not os.path.exists(oldName):
            err_msg = "expected output {0} is missing".format(oldName)
            missing_output_msg = err_msg
            break
        if oldName != newName:
            print (commands_get_status_output('mv %s %s' % (oldName,newName))[-1])
    # modify PoolFC.xml
    pfcName = 'PoolFileCatalog.xml'
    pfcSt,pfcOut = commands_get_status_output('ls %s' % pfcName)
    if pfcSt == 0:
        try:
            pLines = ''
            pFile = open(pfcName)
            for line in pFile:
                # replace file name
                if oldName != newName:
                    line = re.sub('"%s"' % oldName, '"%s"' % newName, line)
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
        if os.path.exists(jsonName):
            pLines = ''
            pFile = open(jsonName)
            for line in pFile:
                # replace file name
                if oldName != newName:
                    line = re.sub('"%s"' % oldName, '"%s"' % newName, line)
                pLines += line
            pFile.close()
            # overwrite
            pFile = open(jsonName,'w')
            pFile.write(pLines)
            pFile.close()
    except:
        pass

# add user job metadata
try:
    from pandawnutil.wnmisc import misc_utils
    misc_utils.add_user_job_metadata()
except Exception:
    pass

# copy results
local_files = os.listdir('.')
for file_name in outputFiles.values():
    if file_name.startswith('regex|'):
        file_name_list = []
        # look for file with regex
        target = re.sub(r'^[^|]+\|', '', file_name)
        for local_file in local_files:
            if re.search(target, local_file):
                file_name_list.append(local_file)
    else:
        file_name_list = [file_name]
    for tmp_name in file_name_list:
        commands_get_status_output('mv %s %s' % (tmp_name, currentDir))


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

# copy tracer log
if not postprocess and rTracer:
    commands_get_status_output('mv %s %s' % (rTracer.getLogName(),currentDir))

# copy useful files
for patt in ['runargs.*','runwrapper.*','jobReport.json','log.*']:
    commands_get_status_output('mv -f %s %s' % (patt,currentDir))

# go back to current dir
os.chdir(currentDir)

print ('')
print ("=== ls in work dir : %s ===" % os.getcwd())
print (commands_get_status_output('ls -l')[-1])

# remove work dir
if not debugFlag:
    commands_get_status_output('rm -rf %s' % workDir)

# return
print ("\n==== Result ====")
print(datetime.datetime.utcnow())
if status:
    err_msg = "payload execution failed with {0}".format(status)
    print ("execute script: Running script failed : StatusCode=%d" % status)
    EC_PayloadFailure.exit(err_msg)
elif missing_output_msg is not None:
    print("payload execution succeeded, but some output files are missing")
    EC_MissingOutput.exit(missing_output_msg)
else:
    print ("execute script: Running script was successful")
    sys.exit(0)
