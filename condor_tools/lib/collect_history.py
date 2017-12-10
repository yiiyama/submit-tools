import sys
import time
import logging
import subprocess

import classad

from history_db import HistoryDB

LOG = logging.getLogger(__name__)

def get_clusters_in_queue(schedd):
   
    clusters_in_queue = set()
    
    for jobads in schedd.xquery('True', ['ClusterId']):
        clusters_in_queue.add(jobads['ClusterId'])

    return clusters_in_queue

def get_open_clusters(db):
    return set(db.query('SELECT `cluster_id` FROM `open_clusters`'))

def get_history_ads(cluster_ids):
    """Return a list of history classads from given cluster ids"""

    classad_attrs = [
        ('GlobalJobId', str),
        ('ClusterId', int),
        ('ProcId', int),
        ('Owner', str),
        ('SubMITOwner', str),
        ('Cmd', str),
        ('MATCH_GLIDEIN_SiteWMS_Queue', str),
        ('LastRemoteHost', str),
        ('MATCH_GLIDEIN_SiteWMS_Slot', str),
        ('BOSCOCluster', str),
        ('MATCH_GLIDEIN_Site', str),
        ('LastRemotePool', str),
        ('LastMatchTime', int),
        ('RemoteWallClockTime', float),
        ('RemoteUserCpu', float),
        ('ExitCode', int),
        ('JobStatus', int),
        ('MATCH_GLIDEIN_CMSSite', str),
        ('Dashboard_TaskId', str),
        ('Dashboard_Id', int)
    ]

    all_ads = []

    ## old implementation using htcondor python binding for schedd
    #
    #open_clusters = sorted(cluster_ids)
    #while len(open_clusters) != 0:
    #    # ExprTree override of __or__ is buggy; need to concatenate by hand
    #    # Construct a list of (begin, end) tuples
    #    ranges = []
    #    while len(open_clusters) != 0:
    #        cluster_id = open_clusters.pop(0)
    #
    #        if len(ranges) == 0 or cluster_id != ranges[-1][1] + 1:
    #            # This cluster id is disconnected from the previous range (or this is the first entry)
    #            ranges.append((cluster_id, cluster_id))
    #
    #            # empirically; condor_history fails when the constraint string is too long
    #            if len(ranges) == 20:
    #                break
    #        else:
    #            # This cluster id is one next the end of the last entry -> update last entry
    #            ranges[-1] = (ranges[-1][0], cluster_id)
    #
    #    constraints = []
    #    for begin, end in ranges:
    #        if begin == end:
    #            constraints.append('ClusterId == %d' % begin)
    #        else:
    #            constraints.append('(ClusterId >= %d && ClusterId <= %d)' % (begin, end))
    #
    #    # exhausted the list of open clusters; append "everything beyond"
    #    if len(open_clusters) == 0:
    #        constraints.append('ClusterId > %d' % ranges[-1][1])
    #
    #    constraint = classad.ExprTree('||'.join(constraints))
    #
    #    all_ads.extend(schedd.history(constraint, classad_attrs, -1))

    ## new implementation using system call to condor_history
    ## python binding somehow stopped working since version 8.6.
    ## The command-line version of condor_history will always iterate through the full history
    ## regardless of the constraint passed. Better to fetch everything and sift them here.
    LOG.info('Fetching full condor_history.')
    proc = subprocess.Popen(['condor_history', '-autoformat'] + [a[0] for a in classad_attrs], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    (out, err) = proc.communicate()

    if proc.returncode != 0:
        sys.stdout.write(out)
        sys.stdout.flush()
        sys.stderr.write(err)
        sys.stderr.flush()
        
        sys.exit(proc.returncode)
    
    # where in the list of returned values does the cluster id appear?
    cluster_id_idx = classad_attrs.index(('ClusterId', int))
    
    for line in out.split("\n"):
        values = line.split(" ")
    
        if len(values) != len(classad_attrs):
            # ill-formatted line
            continue
    
        if int(values[cluster_id_idx]) not in cluster_ids:
            # this is not an open cluster
            continue
    
        line_dict = dict()
    
        for (name, typ), value in zip(classad_attrs, values):
            if value == 'undefined':
                if name == 'ExitCode':
                    line_dict[name] = -1
    
                # otherwise we don't fill the dictionary and let KeyErrors be thrown
                continue
    
            try:
                line_dict[name] = typ(value)
            except:
                LOG.error(' ERROR == Exception: Attribute: %s  Type: %s  Value: %s' % (name, str(typ), value))
                LOG.error(line)
    
        all_ads.append(line_dict)

    return all_ads

def get_cluster_jobs(jobads, db):
    """Return a set of proc ids of cluster_id."""

    cluster_id = jobads['ClusterId']

    if not db.cluster_exists(HistoryDB.CONDOR_INSTANCE, cluster_id):
        # This is a new cluster

        # Find the user id first
        user = ''
        try:
            user = jobads['SubMITOwner']
        except KeyError:
            try:
                user = jobads['Owner']
            except KeyError:
                # No User classad found
                pass

        if user == '':
            user_id = 0
        else:
            user_id = db.get_user(user)

        # This is the submit time of this particular process and not of the cluster
        # but we are not interested in seconds-precision here; is a good enough approximation
        global_jobid = jobads['GlobalJobId']
        submit_time = time.localtime(int(global_jobid[global_jobid.rfind('#') + 1:]))

        LOG.info('Inserting cluster (%d, %s, %s, %s)', cluster_id, user, time.strftime('%Y-%m-%d %H:%M:%S', submit_time), os.path.basename(jobads['Cmd'])[:16])

        # Now insert the cluster information
        db.query('INSERT INTO `job_clusters` VALUES (%s, %s, %s, %s, %s)', HistoryDB.CONDOR_INSTANCE, cluster_id, user_id, time.strftime('%Y-%m-%d %H:%M:%S', submit_time), os.path.basename(jobads['Cmd'])[:16])

    # Fetch the list of proc_ids already recorded
    return set(db.query('SELECT `proc_id` FROM `jobs` WHERE (`instance`, `cluster_id`) = (%s, %s)', HistoryDB.CONDOR_INSTANCE, cluster_id))

def insert_one_job(jobads, db):
    cluster_id = jobads['ClusterId']
    proc_id = jobads['ProcId']
    match_time = time.localtime(jobads['LastMatchTime'])

    try:
        site_name = str(jobads['MATCH_GLIDEIN_Site'])
    except KeyError:
        site_name = ''

    try:
        site_pool = str(jobads['MATCH_GLIDEIN_SiteWMS_Queue']).lower()
    except KeyError:
        site_pool = 'unknown'

    if site_pool == 'unknown':
        try:
            remote_slot = str(jobads['LastRemoteHost']).lower()
        except KeyError:
            try:
                remote_slot = str(jobads['MATCH_GLIDEIN_SiteWMS_Slot'])
            except KeyError:
                remote_slot = ''

        remote_node = remote_slot[remote_slot.find('@') + 1:]
        site_pool = remote_node[remote_node.find('.') + 1:]

    # HACK -- Estonia has too many site_pools
    if site_name == 'Estonia':
        site_pool = 'glidein'

    frontend_name = str(jobads['LastRemotePool'])

    site_id = db.get_site(site_name, site_pool, frontend_name)

    if jobads['JobStatus'] == 4:
        success = 1
    else:
        success = 0

    try:
        exit_code = jobads['ExitCode']
    except KeyError:
        exit_code = None

    try:
        cpu_time = jobads['RemoteUserCpu']
    except KeyError:
        cpu_time = -1

    try:
        wall_time = jobads['RemoteWallClockTime']
    except KeyError:
        wall_time = -1

    LOG.debug('Inserting job %d.%d (success: %d)', cluster_id, proc_id, success)

    sql = 'INSERT INTO `jobs`'
    sql += ' (`instance`, `cluster_id`, `proc_id`, `site_id`, `match_time`, `success`, `cputime`, `walltime`, `exitcode`)'
    sql += ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)'

    db.query(sql,
        HistoryDB.CONDOR_INSTANCE,
        cluster_id,
        proc_id,
        site_id,
        time.strftime('%Y-%m-%d %H:%M:%S', match_time),
        success,
        cpu_time,
        wall_time,
        exit_code
    )

    return proc_id
