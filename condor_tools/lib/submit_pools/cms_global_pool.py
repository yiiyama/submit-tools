import socket
import hashlib
import json
import urllib2
import httplib

# Local module for access to condor_history DB
from history_db import HistoryDB

CRABLIBS = '/cvmfs/cms.cern.ch/crab/CRAB_2_11_1_patch1/python/'
if CRABLIBS not in sys.path:
    sys.path.insert(0, CRABLIBS)

from DashboardAPI import apmonSend, apmonFree

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

    return True


def generate_dashboard_ids(proc_ad):
    # What are these parameters?
    monitorid = '{0}_https://login.uscms.org/{1}/{0}'.format(proc_ad['Dashboard_Id'], hashlib.sha1(taskid).hexdigest()[-16:])
    syncid = 'https://login.uscms.org//{0}//12345.{0}'.format(taskid, proc_ad['Dashboard_Id'])

    return monitorid, syncid


def report_master_submission(cluster_ad):
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

    apmonSend(taskid, 'TaskMeta', {
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
        'user': cluster_ad['Owner'],
        'CMSUser': cluster_ad['Owner'],
        'datasetFull': '',
        'resubmitter': 'user',
        'exe': executable
    })

    return taskid


def report_to_dashboard(proc_ads):
    # Called in postsubmit.
    # Report to Dashboard about the cluster. Individual job reports are sent by history_update.py

    if len(proc_ads) == 0:
        return

    if 'DESIRED_Sites' not in proc_ads[0]:
        # This cluster will not match any CMS resource
        return

    if proc_ads[0]['JobUniverse'] != 5: # 5: vanilla universe
        return

    db = HistoryDB()

    taskids = dict()

    for proc_ad in proc_ads:
        try:
            taskid = taskids[proc_ad['ClusterId']]
        except KeyError:
            result = db.query('SELECT `task_id` FROM `cms_tasks` WHERE `instance` = %s AND `cluster_id` = %s', HistoryDB.CONDOR_INSTANCE, proc_ad['ClusterId'])
    
            if len(result) == 0:
                # First time encountering this cluster id -> report to dashboard and record in DB
                taskid = report_master_submission(proc_ad)

                sql = 'INSERT INTO `cms_tasks` (`instance`, `cluster_id`, `task_id`) VALUES (%s, %s, %s)'
                db.query(sql, HistoryDB.CONDOR_INSTANCE, proc_ad['ClusterId'], taskid)

            else:
                taskid = result[0]

            taskids[proc_ad['ClusterId']] = taskid

        # In CMSConnect, each dashboard task is allowed to have multiple clusters (Dashboard_Id is the full
        # serial ID of the jobs)
        # Here we are simplifying it by making 1:1 correspondence between clusters and tasks
        proc_ad['Dashboard_TaskId'] = taskid
        proc_ad['Dashboard_Id'] = proc_ad['ProcId']

        monitorid, syncid = generate_dashboard_ids(proc_ad)

        apmonSend(taskid, monitorid, {
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
    apmonFree()

    for proc_ad in proc_ads:
        taskid = taskids[proc_ad['ClusterId']]
        monitorid, syncid = generate_dashboard_ids(proc_ad)

        apmonSend(taskid, monitorid, {
            'taskId': taskid,
            'jobId': monitorid,
            'sid': syncid,
            'StatusValueReason': '',
            'StatusValue': 'Pending',
            'StatusEnterTime': time.strftime('%Y-%m-%d_%H:%M:%S', time.gmtime()),
            'StatusDestination': 'unknown',
            'RBname': 'condor'
        })


def report_job_completion(proc_ad):
    if 'DESIRED_Sites' not in proc_ad:
        return

    if proc_ad['JobUniverse'] != 5: # 5: vanilla universe
        return

    if proc_ad['MATCH_GLIDEIN_CMSSite'] == 'Unknown':
        # report as Aborted
        return

    # get the task id, repeat what the wrapper does
    
