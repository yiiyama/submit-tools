#!/usr/bin/env python
"""
Query schedds and write data to text dumps and RRDs.
Configuration
  FIND_SCHEDDS: If True, go through COLLECTOR_LOCATIONS and gather the list of schedds talking to the collectors. If False, schedds can be manually specified through SCHEDD_ADS.
  SCHEDD_CONSTRAINTS: Used to find schedds matching the constraint (in HTCondor classad language).
  COLLECTOR_LOCATIONS: Used when FIND_SCHEDDS = True or ADD_MAX_SLOTS = True.
  SCHEDD_ADS: If FIND_SCHEDDS = False, set to None or a list of ClassAds. If None, only the local schedd will be used.
  JOB_COUNTERS: Names of job counters used in RRD.
  COUNTER_TITLES: A list of tuple that matches the JOB_COUNTERS list. [(title, color)]
  COUNTER_MAP: A function that takes a JobData object as an argument and returns the counter name to increment.
  ADD_MAX_SLOTS: If True, A line indicating the maximum number of available slots is shown on RRD graphs.
  STARTD_CONSTRAINTS: Constraints for startds that count towards MAX_SLOTS.
  INTERVAL: Interval for RRD records.
"""

import sys
import os
import socket
import smtplib
import time
import re
import collections
from argparse import ArgumentParser
from email.mime.text import MIMEText
import htcondor

# Simple class to hold job data
JobData = collections.namedtuple('JobData', ['schedd', 'user', 'submitHost', 'jobId', 'startTime', 'frontend', 'site', 'remoteHost', 'status', 'command', 'arguments'])

### LOCAL CONFIG ###
FIND_SCHEDDS = False
SCHEDD_CONSTRAINTS = ''
COLLECTOR_LOCATIONS = []
SCHEDD_ADS = None

# RRD config

JOB_COUNTERS = ['running-t2', 'running-t3', 'running-eaps', 'running-osg', 'running-cms', 'idle', 'held']
COUNTER_TITLES = [('T2_US_MIT', '789e5b'), ('T3_US_MIT', 'deaa39'), ('EAPS', '72c2d6'), ('OSG', 'db773b'), ('CMS', 'c8493d'), ('Idle', '2665b0'), ('Held', '9a4299')]
ADD_MAX_SLOTS = False
STARTD_CONSTRAINTS = 'True'

def sortJob(job):
    if job.status == 2:
        if job.site == 'MIT_CampusFactory/cmsaf.mit.edu':
            return 'running-t2'
        elif job.site == 'MIT_CampusFactory/mit.edu':
            return 'running-t3'
        elif job.site == 'MIT_CampusFactory/eth.cluster':
            return 'running-eaps'
        elif job.frontend == 'osg-flock.grid.iu.edu':
            return 'running-osg'
        elif job.frontend == 'cmsgwms-collector-global.cern.ch:9620' or job.frontend == 'vocms0808.cern.ch:9620' or job.frontend == 'cmssrv221.fnal.gov:9620':
            return 'running-cms'

    elif job.status == 5 or job.status == 6:
        return 'held'
    elif job.status == 0 or job.status == 1:
        return 'idle'
    else:
        return None

COUNTER_MAP = sortJob

INTERVAL = 300
####################

argParser = ArgumentParser(description = 'Monitor condor jobs currently in the queue.')
argParser.add_argument('--threshold', '-t', metavar = 'TMAX', dest = 'threshold', type = float, default = 0., help = 'Threshold time for action in hours.')
argParser.add_argument('--user', '-u', metavar = 'USER', dest = 'users', nargs = '+', help = 'Limit to specific users.')
argParser.add_argument('--exclude-user', '-X', action = 'store_true', dest = 'excludeUsers', help = '(With --user) Limit to all users except for ones specified by --user.')
argParser.add_argument('--pool', '-p', metavar = 'DOMAIN', dest = 'pools', nargs = '+', default = [], help = 'Limit to specific remote pools. Default is cmsaf.mit.edu. Use "all" to match all remote pools.')
argParser.add_argument('--email', '-m', metavar = 'ADDR', dest = 'email', help = 'Address to send reports to.')
argParser.add_argument('--kill', '-K', action = 'store_true', dest = 'kill', help = 'Kill jobs.')
argParser.add_argument('--rrd-dir', '-d', metavar = 'DIR', dest = 'rrdDir', help = 'Directory for RRD databases.')
argParser.add_argument('--graph-dir', '-g', metavar = 'DIR', dest = 'graphDir', help = '(With --rrd-dir) Directory for RRDTool graphs.')
argParser.add_argument('--joblist-dir', '-j', metavar = 'DIR', dest = 'joblistDir', help = 'Directory for job list files (one file per user).')

args = argParser.parse_args()
sys.argv = []

if len(args.pools) == 1 and args.pools[0] == 'all':
    args.pools = []

if args.users is None:
    usersLimit = None
    usersExclude = None
elif args.excludeUsers:
    usersLimit = None
    usersExclude = args.users
else:
    usersLimit = args.users
    usersExclude = None

schedds = []
if FIND_SCHEDDS:
    for loc in COLLECTOR_LOCATIONS:
        collector = htcondor.Collector(loc)
        for ad in collector.query(htcondor.AdTypes.Schedd, SCHEDD_CONSTRAINTS, ['MyAddress']):
            # remote schedd specified by the ClassAd object containing the ip address
            schedds.append(htcondor.Schedd(ad))

else:
    if SCHEDD_ADS is None:
        schedds.append(htcondor.Schedd())
    else:
        for ad in SCHEDD_ADS:
            if ad is None:
                schedds.append(htcondor.Schedd())
            else:
                schedds.append(htcondor.Schedd(ad))

# STEP 1: condor_q
jobData = []

for schedd in schedds:
    jobAds = schedd.query('True', ['User', 'ClusterId', 'ProcId', 'GlobalJobId', 'JobStartDate', 'RemoteHost', 'LastRemoteHost', 'RemotePool', 'LastRemotePool', 'JobStatus', 'Cmd', 'Arguments', 'Args', 'MATCH_GLIDEIN_Site', 'BOSCOCluster'])

    for jobAd in jobAds:
        try:
            startTime = jobAd['JobStartDate']
        except KeyError:
            startTime = -1

        try:
            remoteHost = jobAd['RemoteHost']
        except KeyError:
            try:
                remoteHost = jobAd['LastRemoteHost']
            except KeyError:
                remoteHost = 'unknown'

        if '@' in remoteHost:
            remoteHost = remoteHost[remoteHost.find('@') + 1:]

        try:
            arguments = jobAd['Arguments']
        except KeyError:
            try:
                arguments = jobAd['Args']
            except KeyError:
                arguments = ''

        try:
            site_name = str(jobAd['MATCH_GLIDEIN_Site'])
        except KeyError:
            site_name = ''
    
        try:
            remote_slot = str(jobAd['RemoteHost']).lower()
        except KeyError:
            try:
                remote_slot = str(jobAd['MATCH_GLIDEIN_SiteWMS_Slot'])
            except KeyError:
                remote_slot = ''

        remote_node = remote_slot[remote_slot.find('@') + 1:]
        site_pool = remote_node[remote_node.find('.') + 1:]

        try:
            frontend_name = str(jobAd['RemotePool'])
        except KeyError:
            try:
                frontend_name = str(jobAd['LastRemotePool'])
            except KeyError:
                frontend_name = 'Unknown'

        jobDatum = JobData(
            schedd = schedd,
            user = jobAd['User'][:jobAd['User'].find('@')],
            submitHost = jobAd['GlobalJobId'][:jobAd['GlobalJobId'].find('#')],
            jobId = '%d.%d' % (jobAd['ClusterId'], jobAd['ProcId']),
            startTime = startTime,
            frontend = frontend_name,
            site = site_name + '/' + site_pool,
            remoteHost = remoteHost,
            status = jobAd['JobStatus'],
            command = jobAd['Cmd'],
            arguments = arguments
        )

        jobData.append(jobDatum)


# STEP 2: select jobs that are running for more than THRESHOLD hours and gather data by user

userJobs = collections.defaultdict(list)

for datum in jobData:
    if len(args.pools) != 0:
        for domain in args.pools:
            if domain in datum.remoteHost:
                break
        else:
            continue

    if args.threshold > 0. and (datum.startTime < 0 or (time.time() - datum.startTime) / 3600. < args.threshold):
        continue

    if usersLimit is not None and datum.user not in usersLimit:
        continue

    if usersExclude is not None and datum.user in usersExclude:
        continue

    userJobs[datum.user].append(datum)


# STEP 3: Action (publish, kill, send emails)

if args.rrdDir:
    import rrdtool
    import selinux

    class JobCounts(object):
        def __init__(self):
            self._counts = dict((c, 0) for c in JOB_COUNTERS)

        def __getitem__(self, key):
            return self._counts[key]

        def __setitem__(self, key, value):
            if key not in self._counts:
                raise KeyError(key)

            self._counts[key] = value

        def __str__(self):
            return ':'.join('%d' % self._counts[c] for c in JOB_COUNTERS)

        def __iadd__(self, rhs):
            for c in JOB_COUNTERS:
                self._counts[c] += rhs._counts[c]

            return self

    totalCounts = JobCounts()
    dataForRRD = [('Total', totalCounts)]

    for user, jobs in userJobs.items():
        counts = JobCounts()

        for job in jobs:
            targ = COUNTER_MAP(job)
            if targ is None:
                continue

            counts[targ] += 1

        dataForRRD.append((user, counts))
        
        totalCounts += counts

    # collect information of users that are not in any condor queue at the moment but have rrds

    nullRow = tuple([None] * len(JOB_COUNTERS))

    for rrd in os.listdir(args.rrdDir):
        user = rrd.replace('.rrd', '')
        if user == 'Total':
            continue

        if user in userJobs:
            continue

        rrdFile = args.rrdDir + '/' + rrd
        timeDef, varDef, dataPoints = rrdtool.fetch(rrdFile, 'LAST')
        for dp in dataPoints:
            # if at least one data point is non-null, use it
            if dp != nullRow and sum(dp) != 0:
                break

        else:
            # otherwise - this RRD contains null entries only. Remove.
            os.remove(rrdFile)
            continue

        dataForRRD.append((user, JobCounts()))

    timestamp = int(time.time()) / INTERVAL * INTERVAL

    for user, counts in dataForRRD:
        rrdFile = args.rrdDir + '/' + user + '.rrd'

        if not os.path.exists(rrdFile):
            # RRD does not exist yet
            # data source
            #  DS:<name>:<type>:<heartbeat>:<min>:<max>
            #  type = GAUGE: quantity that has a value at each time point
            #  heartbeat: "maximum number of seconds that may pass between two updates of this data source before the value of the data source is assumed to be *UNKNOWN*"
            #  min/max = U: unknown
            # round robin archive (RRA)
            #  RRA:<type>:<xff>:<nsteps>:<nrows>
            #  type = LAST: just use the last value, no averaging etc.
            #  xff: fraction of <nsteps> that can have UNKNOWN as the value
            #  nsteps: number of steps used for calculation
            #  nrows: number of records to keep

            start = (int(time.time()) / INTERVAL - 1) * INTERVAL

            dataDefs = [rrdFile, '--start', str(start), '--step', str(INTERVAL)]
            for c in JOB_COUNTERS:
                dataDefs.append('DS:' + c + ':GAUGE:600:0:U')
            dataDefs.append('RRA:LAST:0:1:' + str(3600 / INTERVAL * 24 * 7))

            rrdtool.create(*tuple(dataDefs))

            try:
                # change selinux context of the RRD so that it can be read by a apache-invoked PHP script
                selinux.chcon(rrdFile, 'unconfined_u:object_r:httpd_var_run_t:s0')
            except:
                pass

        try:
            rrdtool.update(rrdFile, str(timestamp) + ':' + str(counts))
        except:
            pass

    if args.graphDir:
        if ADD_MAX_SLOTS:
            maxSlots = len(collector.query(htcondor.AdTypes.Startd, STARTD_CONSTRAINTS, ['Machine']))

        for user, counts in dataForRRD:
            rrdFile = args.rrdDir + '/' + user + '.rrd'

            graphDefs = [
                '--width=400', '--height=300', '--full-size-mode',
                '--vertical-label=jobs',
                '--lower-limit=0']
            for c in JOB_COUNTERS:
                graphDefs.append('DEF:' + c + '=' + rrdFile + ':' + c + ':LAST')

            if ADD_MAX_SLOTS:
                graphDefs.append('HRULE:{maxSlots}#0000FF:Max slots ({maxSlots})'.format(maxSlots = maxSlots))

            for c, (title, color) in zip(JOB_COUNTERS, COUNTER_TITLES):
                graphDefs.append('AREA:' + c + '#' + color + ':' + title + ':STACK')

            try:
                rrdtool.graph(args.graphDir + '/' + user + '_1w.png', '--start=%d' % (timestamp - 3600 * 24 * 7), '--end=%d' % timestamp, *tuple(['--title=1W'] + graphDefs))
                rrdtool.graph(args.graphDir + '/' + user + '_1d.png', '--start=%d' % (timestamp - 3600 * 24), '--end=%d' % timestamp, *tuple(['--title=1D'] + graphDefs))
                rrdtool.graph(args.graphDir + '/' + user + '_2h.png', '--start=%d' % (timestamp - 3600 * 2), '--end=%d' % timestamp, *tuple(['--title=2H'] + graphDefs))
            except:
                pass

if args.joblistDir:
    status = {
        0: 'Unexpanded',
        1: 'Idle',
        2: 'Running',
        3: 'Removed',
        4: 'Completed',
        5: 'Held',
        6: 'SubmissionErr'
    }

    for fname in os.listdir(args.joblistDir):
        os.remove(args.joblistDir + '/' + fname)

    for user, jobs in userJobs.items():
        with open(args.joblistDir + '/' + user + '.txt', 'w') as joblist:
            joblist.write('%-17s %-10s %-17s %-13s %s\n' % ('Submit host', 'Job ID', 'Execution host', 'Status', 'Command'))
            for datum in jobs:
                joblist.write('%17s %10s %17s %13s %s %s\n' % (datum.submitHost[:17], datum.jobId[:10], datum.remoteHost[:17], status[datum.status], datum.command, datum.arguments))

if args.kill:
    for user, jobs in userJobs.items():
        for datum in sorted(jobs, cmp = lambda x, y: cmp(x.jobId, y.jobId)):
            response = datum.schedd.act(htcondor.JobAction.Remove, 'ClusterId == %s && ProcId == %s' % tuple(datum.jobId.split('.')))
            if response['TotalSuccess'] == 1:
                print 'Removed ' + datum.jobId
            else:
                print 'Failed to remove ' + datum.jobdId

if args.email:
    smtp = smtplib.SMTP('localhost')

    for user, jobs in userJobs.items():
        plural = len(jobs) > 1
    
        body = str(len(jobs)) + ' job'
        if plural:
            body += 's'
        body += ' submitted by user ' + user + ' on node ' + socket.gethostname()
        if args.kill:
            if plural:
                body += ' were'
            else:
                body += ' was'
            body += ' killed.\n\n'
        else:
            if plural:
                body += ' are'
            else:
                body += ' is'
            body += ' running for more than ' + str(THRESHOLD) + ' hours.\n\n'
    
        body += 'Details:\n'
        body += '-----------------------------------------------------------\n'
    
        for datum in sorted(jobs, cmp = lambda x, y: cmp(x.jobId, y.jobId)):
            body += jobId + ': ' + command + (' (%.1f hr)\n' % elapsed)
    
        msg = MIMEText(body)

        if args.kill:
            msg['Subject'] = 'Jobs killed on ' + socket.gethostname()
        else:
            msg['Subject'] = 'Jobs running for > ' + str(THRESHOLD) + ' hours on ' + socket.gethostname()

        msg['From'] = args.email
        msg['To'] = args.email
    
        smtp.sendmail(args.email, [args.email], msg.as_string())
    
    smtp.quit()
