#!/usr/bin/env python

"""
update.py - Collect job information from schedd and save into database.
"""

# Increment this number whenever ClusterId counter is reset
CONDOR_INSTANCE = 1

import sys
import os
import pwd
import time
import subprocess
import collections
import logging
import htcondor
import classad

logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)

from db import db_query

schedd = htcondor.Schedd()

# First fetch the list of cluster ids that are still in the queue
current_open_clusters = set()

for jobads in schedd.xquery('True', ['ClusterId']):
    current_open_clusters.add(jobads['ClusterId'])

# Prepare python -> mysql id mappings
users = dict(db_query('SELECT `name`, `user_id` FROM `users`'))
sites = {}
for site_id, site_name, site_pool in db_query('SELECT `site_id`, `site_name`, `site_pool` FROM `sites`'):
    sites[(site_name, site_pool)] = site_id
frontends = dict(db_query('SELECT `frontend_name`, `frontend_id` FROM `frontends`'))

# Form the constraint expression for condor_history:
# 1. All new clusters
# 2. All clusters tagged open in the last iteration

classad_attrs = ['GlobalJobId', 'ClusterId', 'ProcId', 'User', 'Cmd', 'MATCH_GLIDEIN_SiteWMS_Queue', 'LastRemoteHost', 'MATCH_GLIDEIN_SiteWMS_Slot', 'BOSCOCluster', 'MATCH_GLIDEIN_Site', 'LastRemotePool', 'LastMatchTime', 'RemoteWallClockTime', 'RemoteUserCpu', 'ExitCode', 'JobStatus']

open_clusters = db_query('SELECT `cluster_id` FROM `open_clusters`')
open_clusters.extend(list(current_open_clusters))
open_clusters.sort()

all_ads = []

while len(open_clusters) != 0:
    # ExprTree override of __or__ is buggy; need to concatenate by hand
    ranges = []
    while len(open_clusters) != 0:
        cluster_id = open_clusters.pop(0)

        if len(ranges) == 0 or cluster_id != ranges[-1][1] + 1:
            ranges.append((cluster_id, cluster_id))

            # empirically; condor_history fails when the constraint string is too long
            if len(ranges) == 2000:
                break
        else:
            ranges[-1] = (ranges[-1][0], cluster_id)

    constraints = []
    for begin, end in ranges:
        if begin == end:
            constraints.append('ClusterId == %d' % begin)
        else:
            constraints.append('(ClusterId >= %d && ClusterId <= %d)' % (begin, end))

    # exhausted the list of open clusters; append "everything beyond"
    if len(open_clusters) == 0:
        constraints.append('ClusterId > %d' % ranges[-1][1])

    constraint = classad.ExprTree('||'.join(constraints))

    ## old implementation                                                                                                                                                                                #all_ads.extend(schedd.history(constraint, classad_attrs, -1))
    ## new implementation and ugly long implementation (python bindings broken)
    action = 'condor_history -constraint \"%s\" -autoformat %s'%("True"," ".join(classad_attrs))
    p = subprocess.Popen(action,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)
    (out, err) = p.communicate()
    rc = p.returncode

    results = []
    for line in out.split("\n"):
        values = line.split(" ")
        line_dict = {}                                     # print " Line: %d (Class: %d)"%(len(values),len(classad_attrs))
        if len(values) == len(classad_attrs):

            for k,t,v in zip(classad_attrs,classad_attrs_type,values):
                try:
                    if   t == 's':
                        line_dict[k] = v
                    elif t == 'd':
                        line_dict[k] = int(v)
                    elif t == 'f':
                        line_dict[k] = float(v)
                    else:
                        line_dict[k] = v
                except:
                   if k == 'ExitCode' and v == 'undefined':
                        line_dict[k] = -1
                    else:
                        print ' ERROR == Exception: Attribute: %s  Type: %s  Value: %s'%(k,t,v)
                        print line

            results.append(line_dict)

    # add all results to the all_adds array
    #print " append more RESULTS"
    all_ads.extend(results)



# Some efficiency measures
cluster_jobs = dict()
is_nobody = set()

for jobads in all_ads:
    logger.debug(str(jobads))

    try:
        match_time = time.localtime(jobads['LastMatchTime'])
    except KeyError:
        # This job was not matched; we will not record it
        continue

    cluster_id = jobads['ClusterId']
    proc_id = jobads['ProcId']

    if cluster_id not in cluster_jobs:
        if db_query('SELECT COUNT(*) FROM `job_clusters` WHERE (`instance`, `cluster_id`) = (%s, %s)', CONDOR_INSTANCE, cluster_id)[0] == 0:
            # This is a new cluster

            # Find user id first
            user = ''
            try:
                full_user_name = jobads['User']
                user = full_user_name[:full_user_name.find('@')]
            except KeyError:
                # No User classad found
                pass

            if user == '' or user in is_nobody:
                user_id = 0

            else:
                try:
                    user_id = users[user]
                except KeyError:
                    # User unknown to database
                    try:
                        user_id = pwd.getpwnam(user).pw_uid
                        logger.info('Inserting user %s(%d)', user, user_id)
                        db_query('INSERT INTO `users` VALUES (%s, %s)', user_id, user)
                        users[user] = user_id

                    except KeyError:
                        # User unknown to system password database
                        logger.warning('Unknown user %s', user)

                        is_nobody.add(user)
                        user_id = 0

            # This is the submit time of this particular process and not of the cluster
            # but we are not interested in seconds-precision here; is a good enough approximation
            global_jobid = jobads['GlobalJobId']
            submit_time = time.localtime(int(global_jobid[global_jobid.rfind('#') + 1:]))

            logger.info('Inserting cluster (%d, %s, %s, %s)', cluster_id, user, time.strftime('%Y-%m-%d %H:%M:%S', submit_time), os.path.basename(jobads['Cmd'])[:16])

            # Now insert the cluster information
            db_query('INSERT INTO `job_clusters` VALUES (%s, %s, %s, %s, %s)', CONDOR_INSTANCE, cluster_id, user_id, time.strftime('%Y-%m-%d %H:%M:%S', submit_time), os.path.basename(jobads['Cmd'])[:16])

        # Fetch the list of proc_ids already recorded
        cluster_jobs[cluster_id] = set(db_query('SELECT `proc_id` FROM `jobs` WHERE (`instance`, `cluster_id`) = (%s, %s)', CONDOR_INSTANCE, cluster_id))

    if proc_id in cluster_jobs[cluster_id]:
        continue

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

    try:
        site_id = sites[(site_name, site_pool)]
    except KeyError:
        try:
            frontend_name = str(jobads['LastRemotePool'])
            try:
                frontend_id = frontends[frontend_name]
            except KeyError:
                logger.info('Inserting frontend %s', frontend_name)

                frontend_id = db_query('INSERT INTO `frontends` (`frontend_name`) VALUES (%s)', frontend_name)
                frontends[frontend_name] = frontend_id

        except KeyError:
            frontend_name = 'Unknown'
            frontend_id = 0

        logger.info('Inserting site %s/%s (frontend %s)', site_name, site_pool, frontend_name)

        site_id = db_query('INSERT INTO `sites` (`site_name`, `site_pool`, `frontend_id`) VALUES (%s, %s, %s)', site_name, site_pool, frontend_id)
        sites[(site_name, site_pool)] = site_id

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

    logger.info('Inserting job %d.%d (success: %d)', cluster_id, proc_id, success)

    db_query('INSERT INTO `jobs` VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
             CONDOR_INSTANCE,
             cluster_id,
             proc_id,
             site_id,
             time.strftime('%Y-%m-%d %H:%M:%S', match_time),
             success,
             cpu_time,
             wall_time,
             exit_code)

    cluster_jobs[cluster_id].add(proc_id)

# save currently open clusters
logger.info('Current open clusters: %s', ' '.join('%d' % c for c in current_open_clusters))

db_query('TRUNCATE TABLE `open_clusters`')
if len(current_open_clusters) != 0:
    db_query('INSERT INTO `open_clusters` VALUES %s' % (','.join(['(%d)' % cluster_id for cluster_id in current_open_clusters])))
