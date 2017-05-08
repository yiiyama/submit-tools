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
    ('JobStatus', int)
]

open_clusters = db_query('SELECT `cluster_id` FROM `open_clusters`')
open_clusters.extend(list(current_open_clusters))

## old implementation using htcondor python binding for schedd
#open_clusters.sort()
#all_ads = []
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
# The command-line version of condor_history will always iterate through the full history regardless of the constraint passed.
# Better to fetch everything and sift them here.
p = subprocess.Popen(['condor_history', '-autoformat'] + [a[0] for a in classad_attrs], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
(out, err) = p.communicate()

# where in the list of returned values does the cluster id appear?
cluster_id_idx = classad_attrs.index(('ClusterId', int))

# make a set for faster search
cluster_ids = set(open_clusters)

all_ads = []
for line in out.split("\n"):
    values = line.split(" ")

    if len(values) != len(classad_attrs):
        # ill-formatted line
        continue

    if int(values[cluster_id_idx]) not in cluster_ids:
        # this is not an open cluster
        continue

    line_dict = {}

    for (name, typ), value in zip(classad_attrs, values):
        if name == 'ExitCode' and value == 'undefined':
            line_dict[name] = -1
            continue

        try:
            line_dict[name] = typ(value)
        except:
            logger.error(' ERROR == Exception: Attribute: %s  Type: %s  Value: %s' % (name, str(typ), value))
            logger.error(line)

    all_ads.append(line_dict)

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
                user = jobads['SubMITOwner']
            except KeyError:
                try:
                    user = jobads['Owner']
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
        # HACK -- Estonia has too many site_pools
        if site_name == 'Estonia':
            site_pool = 'glidein'

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
