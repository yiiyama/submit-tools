#!/usr/bin/env python

import os
import sys
import time
import socket
import hashlib
import subprocess
import threading
import Queue
import json
import urllib2
import httplib

import htcondor
import classad

# Local module for access to condor_history DB
from db import db_query

class RCException(Exception):
    pass

def read_stdin(queue):
    # Wait for stdin input until EOF and write back in the queue
    text = sys.stdin.read()
    queue.put(text)

def call_executable(args):
    EXECUTABLE = '/usr/bin/condor_submit'
    TIMEOUT = 30

    proc = subprocess.Popen([EXECUTABLE] + args, stdout = subprocess.PIPE, stderr = subprocess.PIPE, stdin = subprocess.PIPE)
    time.sleep(0.5)

    wait_start = time.time()
    input_thread = None

    while proc.poll() is None:
        # condor_submit has not returned. Maybe it's waiting for input to stdin.

        if input_thread is None:
            # stdin.read() is blocking. Use a separate thread to wait for input.
            queue = Queue.Queue()
            input_thread = threading.Thread(target = read_stdin, args = (queue,))
            input_thread.daemon = True
            input_thread.start()

        try:
            stdin_text = queue.get(block = False)
        except Queue.Empty:
            pass
        else:
            input_thread.join()
            input_thread = None
            proc.stdin.write(stdin_text)

            wait_start = time.time()

        time.sleep(0.5)

        if time.time() - wait_start > TIMEOUT:
            sys.stderr.write('condor_submit timed out. Did you forget a "queue" line?\n')
            sys.stderr.flush()
            raise RuntimeError('condor_submit timeout')

    return proc.returncode, proc.stdout.read(), proc.stderr.read()

def parse_classad(classad_file):
    all_ads = []

    current_cluster_id = 0

    while True:
        try:
            ad = classad.parseNext(classad_file)
        except StopIteration:
            # We are done
            break
        
        if 'ClusterId' in ad and ad['ClusterId'] != current_cluster_id:
            current_cluster_id = ad['ClusterId']

            # create ad objects, add to the output, and keep updating the objects
            cluster_ad = classad.ClassAd()
            proc_ads = []
            all_ads.append((cluster_ad, proc_ads))

        # Adjust ad contents
        del ad['ClusterId']
        del ad['ProcId']

        if 'x509userproxy' in ad:
            # condor_submit dry-run / dump do not evaluate the proxy contents
            set_x509_attributes(ad)

        if len(cluster_ad) == 0:
            cluster_ad.update(ad)

        proc_ads.append((ad, 1))

    return all_ads

def set_x509_attributes(ad):
    def voms_proxy_info(arg):
        # call voms-proxy-info -file <proxy> -<arg>
        proc = subprocess.Popen(['voms-proxy-info', '-file', ad['x509userproxy'], '-' + arg], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        out, err = proc.communicate()
            
        if proc.returncode != 0:
            sys.stdout.write(out)
            sys.stdout.flush()
            sys.stderr.write(err)
            sys.stderr.flush()
    
            raise RCException(proc.returncode, '')

        return out.strip().split('\n')

    # I don't think there is a way to get this information from voms client command line tools
    ad['x509UserProxyEmail'] = 'submit@mit.edu'
    
    timeleft = int(voms_proxy_info('timeleft')[0])
    ad['x509UserProxyExpiration'] = int(time.time()) + timeleft

    # Cerficate subject is the issuer of the proxy
    subject = voms_proxy_info('issuer')[0]
    ad['x509userproxysubject'] = subject

    vo = voms_proxy_info('vo')[0]
    ad['x509UserProxyVOName'] = vo

    fqans = voms_proxy_info('fqan')
    ad['x509UserProxyFirstFQAN'] = fqans[0]
    ad['x509UserProxyFQAN'] = ','.join([subject] + fqans)

def submit(cluster_ad, proc_ads):
    schedd = htcondor.Schedd()
    sys.stdout.write('Submitting job(s)')
    sys.stdout.flush()

    cluster_id = schedd.submitMany(cluster_ad, proc_ads)
    
    sys.stdout.write('.' * len(proc_ads) + '\n')
    sys.stdout.write('%d job(s) submitted to cluster %d.\n' % (len(proc_ads), cluster_id))
    sys.stdout.flush()

################ Pool-specific checks & adjustments ################

CRABLIBS = '/cvmfs/cms.cern.ch/crab/CRAB_2_11_1_patch1/python/'
if CRABLIBS not in sys.path:
    sys.path.insert(0, CRABLIBS)

import DashboardAPI

class HTTPSCertKeyHandler(urllib2.HTTPSHandler):
    """
    HTTPS handler authenticating by x509 user key and certificate.
    """

    def __init__(self, proxy_path = None):
        urllib2.HTTPSHandler.__init__(self)

        if proxy_path is None:
            try:
                proxy_path = os.environ['X509_USER_PROXY']
            except KeyError:
                proxy_path = '/tmp/x509up_u%d' % os.getuid()

        self.key = proxy_path
        self.cert = proxy_path

    def https_open(self, req):
        return self.do_open(self.create_connection, req)

    def create_connection(self, host, timeout = 300):
        return httplib.HTTPSConnection(host, key_file = self.key, cert_file = self.cert)


def check_cms_global_pool(cluster_ad, proc_ads):
    if 'DESIRED_Sites' not in cluster_ad:
        # This cluster will not match any CMS resource
        return True

    if 'T2_UK_London_Brunel' in cluster_ad['DESIRED_Sites']:
        # Brunel is IPv6-only and causes communication errors (segfault!)
        sys.stderr.write('T2_UK_London_Brunel cannot be in the list of desired sites.\n')
        return False

    if 'AccountingGroup' not in cluster_ad:
        sys.stderr.write("+AccountingGroup = analysis.<owner> is required to submit to CMS global pool.\n")
        return False

    if 'MaxWallTimeMins' not in cluster_ad:
        sys.stderr.write('+MaxWallTimeMins = <expected wall time (min)> is required to submit to CMS global pool.\n')
        return False

    if 'x509userproxysubject' not in cluster_ad:
        # attribute x509userproxy can be set by hand even when there is no proxy -> use auto-generated proxysubject etc.
        sys.stderr.write("use_x509userproxy = True; x509userproxy = <your proxy> is required to submit to CMS global pool.\n")
        return False

    # Check the proxy and CMS account name mapping
    sitedb_request = urllib2.Request('https://cmsweb.cern.ch/sitedb/data/prod/whoami')

    https_handler = HTTPSCertKeyHandler(cluster_ad['x509userproxy'])
    opener = urllib2.build_opener(https_handler)
    opener.addheaders.append(('Accept', 'application/json'))

    try:
        response = opener.open(sitedb_request)
    except:
        sys.stderr.write('Failed to retrieve user mapping from SiteDB using grid proxy %s.\n' % https_handler.cert)
        return False

    mapping = json.loads(response.read())
    cms_user_name = str(mapping['result'][0]['login'])

    if cluster_ad['Owner'] != cms_user_name or cluster_ad['AccountingGroup'] != ('analysis.%s' % cms_user_name):
        sys.stderr.write('User LNS user account, CMS user account, and <user> in AccountingGroup = analysis.<user> must all match.\n')
        sys.stderr.flush()
        return False

    if cluster_ad['JobUniverse'] == 5: # vanilla universe
        # Report to Dashboard about the cluster. Individual job reports are sent by history_update.py
    
        # taskid apparently can be anything
        executable = os.path.basename(cluster_ad['Cmd'])
        taskid = 'mit_%s_%s_%d' % (cluster_ad['Owner'], executable, int(time.time() * 1.e+6))
        cert_dn = cluster_ad['x509userproxysubject']
        cn_begin = cert_dn.rfind('/CN=')
        cn_end = cert_dn.find('/', cn_begin + 1)
        if cn_end == -1:
            user_cn = cert_dn[cn_begin:]
        else:
            user_cn = cert_dn[cn_begin:cn_end]

        DashboardAPI.apmonSend(taskid, 'TaskMeta', {
            'taskId': taskid,
            'jobId': 'TaskMeta',
            'tool': 'cmsconnect',
            'tool_ui': socket.gethostname(),
            'SubmissionType': 'direct',
            'JSToolVersion': '3.2.1',
            'scheduler': 'condor',
            'GridName': user_cn,
            'ApplicationVersion': 'unknown',
            'taskType': 'analysis',
            'vo': 'cms',
            'user': cms_user_name,
            'CMSUser': cms_user_name,
            'datasetFull': '',
            'resubmitter': 'user',
            'exe': executable
        })

        def generate_ids(proc_ad):
            # What are these parameters?
            monitorid = '{0}_https://login.uscms.org/{1}/{0}'.format(proc_ad['Dashboard_Id'], hashlib.sha1(taskid).hexdigest()[-16:])
            syncid = 'https://login.uscms.org//{0}//12345.{0}'.format(taskid, proc_ad['Dashboard_Id'])

            return monitorid, syncid

        # Add Dashboard_Id attr to individual jobs
        for iproc, (proc_ad, _) in enumerate(proc_ads):
            # In CMSConnect, each dashboard task is allowed to have multiple clusters (Dashboard_Id is the full
            # serial ID of the jobs)
            # Here we are simplifying it by making 1:1 correspondence between clusters and tasks
            proc_ad['Dashboard_Id'] = iproc

            monitorid, syncid = generate_ids(proc_ad)

            DashboardAPI.apmonSend(taskid, monitorid, {
                'taskId': taskid,
                'jobId': monitorid,
                'sid': syncid,
                'broker': 'condor',
                'bossId': str(proc_ad['Dashboard_Id']),
                'SubmissionType': 'Direct',
                'TargetSE': 'se01.cmsaf.mit.edu',
                'localId': '',
                'tool': 'institutionalschedd',
                'JSToolVersion': '3.2.1',
                'tool_ui': socket.gethostname(),
                'scheduler': 'condor',
                'GridName': user_cn,
                'ApplicationVersion': 'unknown',
                'taskType': 'analysis',
                'vo': 'cms',
                'user': cms_user_name,
                'CMSUser': cms_user_name,
                'resubmitter': 'user',
                'exe': executable
            })

        # Why here?
        DashboardAPI.apmonFree()

        for proc_ad, _ in proc_ads:
            monitorid, syncid = generate_ids(proc_ad)

            DashboardAPI.apmonSend(self._taskid, monitorid, {
                'taskId': taskid,
                'jobId': monitorid,
                'sid': syncid,
                'StatusValueReason': '',
                'StatusValue': 'Pending',
                'StatusEnterTime': time.strftime('%Y-%m-%d_%H:%M:%S', time.gmtime()),
                'StatusDestination': 'unknown',
                'RBname': 'condor'
            })

    return True
