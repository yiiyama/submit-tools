import os
import sys
import time
import socket
import hashlib
import json
import logging
import urllib2
import httplib

# Local module for access to condor_history DB
from condor_tools.history_db import HistoryDB

CRABLIBS = '/cvmfs/cms.cern.ch/crab/CRAB_2_11_1_patch1/python/'
if CRABLIBS not in sys.path:
    sys.path.insert(0, CRABLIBS)

from DashboardAPI import apmonSend, apmonFree

LOG = logging.getLogger(__name__)

# global dictionary for cluster_id -> taskid mapping
_taskids = dict()

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

    if cluster_ad['JobUniverse'] != 5: # 5: vanilla universe
        return True

    LOG.debug('Checking CMS Global Pool conformity')

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

    LOG.debug('Retrieving CMS user name from SiteDB')

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

    LOG.debug('CMS user name %s' % cms_user_name)

    if cluster_ad['Owner'] != cms_user_name or cluster_ad['AccountingGroup'] != ('analysis.%s' % cms_user_name):
        sys.stderr.write('User LNS user account, CMS user account, and <user> in AccountingGroup = analysis.<user> must all match.\n')
        sys.stderr.flush()
        return False

    return True


def dashboard_postsubmit(proc_ads):
    # Called in postsubmit.
    # Report to Dashboard about the cluster. Individual job reports are sent by history_update.py

    if len(proc_ads) == 0:
        return

    if 'DESIRED_Sites' not in proc_ads[0]:
        # This cluster will not match any CMS resource
        return

    try:
        if proc_ads[0]['JobUniverse'] != 5: # 5: vanilla universe
            return
    except KeyError:
        return

    LOG.debug('Postsubmit for CMS Global Pool')

    db = HistoryDB()

    for proc_ad in proc_ads:
        cluster_id = proc_ad['ClusterId']

        try:
            taskid = _taskids[cluster_id]

            LOG.debug('Using task id %s for cluster id %d' % (taskid, cluster_id))

        except KeyError:
            result = db.query('SELECT `task_id` FROM `cms_tasks` WHERE `instance` = %s AND `cluster_id` = %s', HistoryDB.CONDOR_INSTANCE, cluster_id)
    
            if len(result) == 0:
                # First time encountering this cluster id -> report to dashboard and record in DB
                taskid = report_master_submission(proc_ad)

                LOG.debug('New task id %s for cluster id %d' % (taskid, cluster_id))

                sql = 'INSERT INTO `cms_tasks` (`instance`, `cluster_id`, `task_id`) VALUES (%s, %s, %s)'
                db.query(sql, HistoryDB.CONDOR_INSTANCE, cluster_id, taskid)

            else:
                taskid = result[0]

                LOG.debug('Found task id %s for cluster id %d in DB' % (taskid, cluster_id))

            _taskids[cluster_id] = taskid

        # In CMSConnect, each dashboard task is allowed to have multiple clusters (Dashboard_Id is the full
        # serial ID of the jobs)
        # Here we are simplifying it by making 1:1 correspondence between clusters and tasks
        proc_ad['Dashboard_TaskId'] = taskid
        proc_ad['Dashboard_Id'] = proc_ad['ProcId']

        report_task_submission(proc_ad, taskid)

        LOG.debug('Reported task submission to Dashboard')

    for proc_ad in proc_ads:
        taskid = _taskids[proc_ad['ClusterId']]

        report_task_status(proc_ad, taskid, 'Pending')

    apmonFree()

    LOG.debug('Reported all tasks as Pending')


def dashboard_postexecute(proc_ad, db):
    # Called in postsubmit for each job.
    # Existence of ad attributes are not guaranteed by collect_history -> check for each one

    if 'DESIRED_Sites' not in proc_ad:
        return

    try:
        if proc_ad['JobUniverse'] != 5: # 5: vanilla universe
            return
    except KeyError:
        return

    try:
        cluster_id = proc_ad['ClusterId']
    except KeyError:
        return

    try:
        taskid = _taskids[cluster_id]
    except KeyError:
        result = db.query('SELECT `task_id` FROM `cms_tasks` WHERE `instance` = %s AND `cluster_id` = %s', HistoryDB.CONDOR_INSTANCE, cluster_id)
    
        if len(result) == 0:
            # cluster not known to history DB for some reason
            taskid = None
        else:
            taskid = result[0]

        _taskids[cluster_id] = taskid

    LOG.debug('Postexecute for CMS Global Pool: taskid for cluster id %d is %s' % (cluster_id, taskid))

    if taskid is None:
        return

    report_remote_host(proc_ad, taskid)

    try:
        cmssite = proc_ad['MATCH_GLIDEIN_CMSSite']
    except KeyError:
        cmssite = 'Unknown'

    if proc_ad['JobStatus'] != 4 or cmssite == 'Unknown':
        # JobStatus = 4 -> failed
        # CMSSite unknown -> didn't run on a CMS resource
        # In both cases, report as Aborted

        LOG.debug('Reporting cluster id %d process id %d as Aborted' % (cluster_id, proc_ad['ProcId']))
        report_task_status(proc_ad, taskid, 'Aborted')
        
    else:
        LOG.debug('Reporting cluster id %d process id %d as Done' % (cluster_id, proc_ad['ProcId']))
        report_task_status(proc_ad, taskid, 'Done')

    report_exit_code(proc_ad, taskid)

    apmonFree()
    

def generate_dashboard_ids(proc_ad, taskid):
    try:
        dashboard_id = proc_ad['Dashboard_Id']
    except KeyError:
        dashboard_id = -1

    # What are these parameters?
    monitorid = '{0}_https://login.uscms.org/{1}/{0}'.format(dashboard_id, hashlib.sha1(taskid).hexdigest()[-16:])
    syncid = 'https://login.uscms.org//{0}//12345.{0}'.format(taskid, dashboard_id)

    return monitorid, syncid


def report_master_submission(cluster_ad):
    # taskid apparently can be anything
    executable = os.path.basename(cluster_ad['Cmd'])
    taskid = 'mit_%s_%s_%d' % (cluster_ad['Owner'], executable, int(time.time() * 1.e+6))

    try:
        cert_dn = cluster_ad['x509userproxysubject']
        cn_begin = cert_dn.rfind('/CN=') + 4
        cn_end = cert_dn.find('/', cn_begin)
        if cn_end == -1:
            user_fullname = cert_dn[cn_begin:]
        else:
            user_fullname = cert_dn[cn_begin:cn_end]
    except KeyError:
        user_fullname = 'unknown'
        user_cn = 'unknown'

    apmonSend(taskid, 'TaskMeta', {
        'taskId': taskid,
        'jobId': 'TaskMeta',
        'tool': 'cmsconnect',
        'tool_ui': socket.gethostname(),
        'SubmissionType': 'direct',
        'JSToolVersion': '3.2.1',
        'scheduler': 'condor',
        'GridName': user_fullname,
        'GridCertificate': cert_dn,
        'ApplicationVersion': 'unknown',
        'taskType': 'analysis',
        'vo': 'cms',
        'user': cluster_ad['Owner'],
        'CMSUser': cluster_ad['Owner'],
        'datasetFull': '',
        'resubmitter': 'user',
        'exe': executable
    })

    return taskid


def report_task_submission(proc_ad, taskid):
    monitorid, syncid = generate_dashboard_ids(proc_ad, taskid)

    executable = os.path.basename(proc_ad['Cmd'])

    try:
        cert_dn = proc_ad['x509userproxysubject']
        cn_begin = cert_dn.rfind('/CN=') + 4
        cn_end = cert_dn.find('/', cn_begin)
        if cn_end == -1:
            user_fullname = cert_dn[cn_begin:]
        else:
            user_fullname = cert_dn[cn_begin:cn_end]
    except KeyError:
        cert_dn = 'unknown'
        user_fullname = 'unknown'

    try:
        dashboard_id = proc_ad['Dashboard_Id']
    except KeyError:
        dashboard_id = -1

    apmonSend(taskid, monitorid, {
        'taskId': taskid,
        'jobId': monitorid,
        'sid': syncid,
        'broker': 'condor',
        'bossId': dashboard_id,
        'SubmissionType': 'Direct',
        'TargetSE': 'se01.cmsaf.mit.edu',
        'localId': '',
        'tool': 'institutionalschedd',
        'JSToolVersion': '3.2.1',
        'tool_ui': socket.gethostname(),
        'scheduler': 'condor',
        'GridName': user_fullname,
        'GridCertificate': cert_dn,
        'ApplicationVersion': 'unknown',
        'taskType': 'analysis',
        'vo': 'cms',
        'user': proc_ad['Owner'],
        'CMSUser': proc_ad['Owner'],
        'resubmitter': 'user',
        'exe': executable
    })


def report_task_status(proc_ad, taskid, status):
    monitorid, syncid = generate_dashboard_ids(proc_ad, taskid)

    try:
        destination = proc_ad['MATCH_Glidein_Gatekeeper']
    except KeyError:
        destination = "unknown"

    apmonSend(taskid, monitorid, {
        'taskId': taskid,
        'jobId': monitorid,
        'sid': syncid,
        'StatusValueReason': '',
        'StatusValue': status,
        'StatusEnterTime': time.strftime('%Y-%m-%d_%H:%M:%S', time.gmtime()),
        'StatusDestination': destination,
        'RBname': 'condor'
    })


def report_remote_host(proc_ad, taskid):
    monitorid, syncid = generate_dashboard_ids(proc_ad, taskid)
    executable = os.path.basename(proc_ad['Cmd'])

    try:
        destination = proc_ad['MATCH_Glidein_Gatekeeper']
    except KeyError:
        destination = "unknown"

    apmonSend(taskid, monitorid, {
        'ExeStart': executable,
        'SyncCE': destination,
        'SyncGridJobId': syncid,
        'WNHostName': proc_ad['LastRemoteHost']
    })


def report_exit_code(proc_ad, taskid):
    monitorid, syncid = generate_dashboard_ids(proc_ad, taskid)

    # Report end of job execution
    apmonSend(taskid, monitorid, {
        'ExeTime': proc_ad['RemoteWallClockTime'],
        'ExeExitCode': proc_ad['ExitCode'],
        'JobExitCode': proc_ad['ExitCode'],
        'JobExitReason': '',
        'StageOutSE': 'unknown',
        'StageOutExitStatus': 0,
        'StageOutExitStatusReason': '',
        'CrabUserCpuTime': proc_ad['RemoteUserCpu'],
        'CrabWrapperTime': proc_ad['RemoteWallClockTime'],
        'CrabStageoutTime': 0,
        'WCCPU': proc_ad['RemoteWallClockTime'],
        'NEventsProcessed': 0
    })
