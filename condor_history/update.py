#!/usr/bin/env python

"""
update.py - Collect job information from schedd and save into database.
"""

# increment this number whenever ClusterId counter is reset
CONDOR_INSTANCE = 1

import os
import pwd
import time
import subprocess
import htcondor
import classad
import logging

logging.basicConfig()

from db import db_query

users = dict(db_query('SELECT `name`, `user_id` FROM `users`'))
sites = {}
for site_id, site_name, site_pool in db_query('SELECT `site_id`, `site_name`, `site_pool` FROM `sites`'):
    sites[(site_name, site_pool)] = site_id

last_cluster_id = db_query('SELECT MAX(`cluster_id`) FROM `job_clusters` WHERE `instance` = %s', CONDOR_INSTANCE)[0]

if last_cluster_id is None:
    last_cluster_id = 0

last_cluster_id = 0

schedd = htcondor.Schedd()

new_cluster_ids = set()
is_nobody = set()

classad_attrs = ['GlobalJobId', 'ClusterId', 'ProcId', 'User', 'Cmd', 'MATCH_GLIDEIN_SiteWMS_Queue', 'LastRemoteHost', 'MATCH_GLIDEIN_SiteWMS_Slot', 'MATCH_GLIDEIN_Site', 'LastMatchTime', 'RemoteWallClockTime', 'RemoteUserCpu', 'JobStatus']

for jobads in schedd.history(classad.ExprTree('ClusterId >= %d' % last_cluster_id), classad_attrs, -1):
    try:
        match_time = time.gmtime(jobads['LastMatchTime'])
    except KeyError:
        # this job was not matched; we will not record it
        continue

    if jobads['ClusterId'] not in new_cluster_ids and db_query('SELECT COUNT(*) FROM `job_clusters` WHERE (`instance`, `cluster_id`) = (%s, %s)', CONDOR_INSTANCE, jobads['ClusterId'])[0] == 0:
        # Find user id first
        try:
            full_user_name = jobads['User']
            user = full_user_name[:full_user_name.find('@')]

            if user == '' or user in is_nobody:
                user_id = 0

            else:
                try:
                    user_id = users[user]
                except KeyError:
                    # User unknown to database
                    try:
                        user_id = pwd.getpwnam(user).pw_uid
                        db_query('INSERT INTO `users` VALUES (%s, %s)', user_id, user)
                        users[user] = user_id
    
                    except KeyError:
                        # User unknown to system password database
                        is_nobody.add(user)
                        user_id = 0
    
        except KeyError:
            # No User classad found
            user_id = 0

        # this is the submit time of this particular process and not of the cluster
        # but we are not interested in seconds-precision here; is a good enough approximation
        global_jobid = jobads['GlobalJobId']
        submit_time = time.gmtime(int(global_jobid[global_jobid.rfind('#') + 1:]))

        # Now insert the cluster information
        db_query('INSERT INTO `job_clusters` VALUES (%s, %s, %s, %s, %s)', CONDOR_INSTANCE, jobads['ClusterId'], user_id, time.strftime('%Y-%m-%d %H:%M:%S', submit_time), os.path.basename(jobads['Cmd'])[:16])

        # remember this cluster
        new_cluster_ids.add(jobads['ClusterId'])

    if db_query('SELECT COUNT(*) FROM `jobs` WHERE (`instance`, `cluster_id`, `proc_id`) = (%s, %s, %s)', CONDOR_INSTANCE, jobads['ClusterId'], jobads['ProcId'])[0] == 0:
        try:
            site_name = str(jobads['MATCH_GLIDEIN_Site'])
        except KeyError:
            site_name = ''

        try:
            site_pool = str(jobads['MATCH_GLIDEIN_SiteWMS_Queue'])
        except KeyError:
            site_pool = 'Unknown'

        if site_pool == 'Unknown':
            try:
                remote_slot = str(jobads['LastRemoteHost'])
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
            site_id = db_query('INSERT INTO `sites` (`site_name`, `site_pool`) VALUES (%s, %s)', site_name, site_pool)
            sites[(site_name, site_pool)] = site_id

        if jobads['JobStatus'] == 4:
            success = 1
        else:
            success = 0

        try:
            cpu_time = jobads['RemoteUserCpu']
        except KeyError:
            cpu_time = -1

        try:
            wall_time = jobads['RemoteWallClockTime']
        except KeyError:
            wall_time = -1
        
        db_query('INSERT INTO `jobs` VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                 CONDOR_INSTANCE,
                 jobads['ClusterId'],
                 jobads['ProcId'],
                 site_id,
                 time.strftime('%Y-%m-%d %H:%M:%S', match_time),
                 success,
                 cpu_time,
                 wall_time)
