#!/usr/bin/env python

import os
import sys
import subprocess
import pwd
from argparse import ArgumentParser
import classad

thisdir = os.path.dirname(__file__)

FRONTENDS = {
    'Campus': 't3serv007.mit.edu:11000?sock=collector',
    'OSG': 'osg-flock.grid.iu.edu',
    'CMS': 'glidein-collector.t2.ucsd.edu'
}
GROUPS = ['cms', 'cmshi']
OPSYSES = ['RHEL6']

argParser = ArgumentParser(description = 'Generate requirements string for subMIT')
commandHelp = ''
argParser.add_argument('user', metavar = 'USER', help = 'User name.')
argParser.add_argument('--group', '-g', metavar = 'GROUP', dest = 'group', help = 'Submission group for resource accesses with higher priorities. Options: ' + ', '.join(GROUPS))
argParser.add_argument('--frontends', '-f', metavar = 'FRONTEND', dest = 'frontends', nargs = '+', default = [], help = 'Job submission frontends to use. Options: ' + ', '.join(sorted(FRONTENDS.keys())))
argParser.add_argument('--osg-project', '-r', metavar = 'PROJECTNAME', dest = 'osg_project', help = 'Project name for OSG job submission.')
argParser.add_argument('--cvmfs', '-v', metavar = 'REPO', dest = 'cvmfs_repos', nargs = '+', help = 'Required CVMFS repositories.')
argParser.add_argument('--os', '-o', metavar = 'OS', dest = 'os', help = 'Required OS name. Options: ' + ', '.join(OPSYSES))
argParser.add_argument('--exclude-sites', '-s', metavar = 'SITE', dest = 'excluded_sites', nargs = '+', default = [], help = 'GLIDEIN_Sites to be excluded.')
argParser.add_argument('--exclude-pools', '-p', metavar = 'POOL', dest = 'excluded_pools', nargs = '+', default = [], help = 'GLIDEIN_Entry_Names or BOSCOClusters to be excluded.')
argParser.add_argument('--custom', '-c', metavar = 'REQUIREMENTS', dest = 'custom_requirements', help = 'Custom requirements string to be ANDed.')

args = argParser.parse_args()
sys.argv = []

is_cms = False
try:
    with open('/var/run/vomsinfo.dat') as volist:
        for line in volist:
            try:
                user, vo = line.split()
            except:
                user = line.strip()
                vo = ''

            if user == args.user and vo == 'cms':
                is_cms = True

except OSError:
    pass

if len(args.frontends) == 0:
    args.frontends.append('Campus')
    if args.osg_project:
        args.frontends.append('OSG')
    if is_cms:
        args.frontends.append('CMS')

else:
    if 'CMS' in args.frontends and not is_cms:
        print 'CMS frontend is requested but no valid proxy was found. Please create a proxy or drop CMS.'
        sys.exit(1)

    if 'OSG' in args.frontends and not args.osg_project:
        print 'OSG frontend is requested but no project name was given. Please specify a project name or drop OSG.'
        sys.exit(1)

site_requirements = []
other_ads = []

if 'Campus' in args.frontends and 'MIT_CampusFactory' not in args.excluded_sites:
    reqs = ['GLIDEIN_Site == "MIT_CampusFactory"']

    # CVMFS
    if args.cvmfs_repos is not None:
        reqs_cvmfs = []
        for repo in args.cvmfs_repos:
            reqs_cvmfs.append('HAS_CVMFS_' + repo.replace('.', '_'))
        
        reqs.append('(' + ' || '.join(reqs_cvmfs) + ')')

    # OS
    if args.os:
        if args.os == 'RHEL6':
            reqs.append('(OpSysAndVer == "SL6" || OpSysAndVer == "CentOS6")')

    # Extract excluded pools specific to Campus
    pools = set(['eofe4.mit.edu', 't3serv007.mit.edu', 'ce03.cmsaf.mit.edu'])
    excluded_pools = set(args.excluded_pools) & pools

    # Exclusion by BOSCOGroup
    reqs_groups = []
    if 'eofe4.mit.edu' not in excluded_pools:
        if is_cms:
            reqs_groups.append('BOSCOGroup == "paus"')
        else:
            reqs_groups.append('BOSCOGroup == "boj"')

    if 't3serv007.mit.edu' not in excluded_pools or 'ce03.cmsaf.mit.edu' not in excluded_pools:
        if is_cms and args.group == 'cms':
            reqs_groups.append('BOSCOGroup == "bosco_cms"')
        elif is_cms and args.group == 'cmshi':
            reqs_groups.append('BOSCOGroup == "bosco_cmshi"')
        else:
            reqs_groups.append('BOSCOGroup == "bosco_lns"')

    reqs.append('(' + ' || '.join(reqs_groups) + ')')

    # Exclusion by BOSCOCluster
    if len(excluded_pools) != 0:
        reqs.append('!stringListMember(BOSCOCluster, "' + ','.join(excluded_pools) + '", ",")')

    for pool in excluded_pools:
        args.excluded_pools.remove(pool)

    try:
        args.excluded_sites.remove('MIT_CampusFactory')
    except:
        pass

    site_requirements.append(' && '.join(reqs))

if 'OSG' in args.frontends:
    other_ads.append('+ProjectName = ' + args.osg_project)
    reqs = ['stringListMember("' + FRONTENDS['OSG'] + '", COLLECTOR_HOST_STRING, ",")']

    # CVMFS
    if args.cvmfs_repos is not None:
        reqs_cvmfs = []
        for repo in args.cvmfs_repos:
            reqs_cvmfs.append('HAS_CVMFS_' + repo.replace('.', '_'))
        
        reqs.append('(' + ' || '.join(reqs_cvmfs) + ')')

    # OS
    if args.os:
        if args.os == 'RHEL6':
            reqs.append('OSGVO_OS_STRING == "RHEL 6"')

    site_requirements.append(' && '.join(reqs))

if 'CMS' in args.frontends:
    with open(thisdir + '/cms_sites.list') as cms_sites:
        other_ads.append('+DESIRED_Sites = "' + ','.join(cms_sites.read().split()) + '"')

    reqs = ['stringListMember("' + FRONTENDS['CMS'] + '", COLLECTOR_HOST_STRING, ",")']

    # OS
    if args.os:
        if args.os == 'RHEL6':
            reqs.append('GLIDEIN_REQUIRED_OS == "rhel6"')

    site_requirements.append(' && '.join(reqs))

requirements = '(' + ' || '.join(['(%s)' % r for r in site_requirements]) + ')'

if len(args.excluded_sites) != 0:
    requirements += ' && (isUndefined(GLIDEIN_Site) || !stringListMember(GLIDEIN_Site, "' + ','.join(args.excluded_sites) + '", ","))'

if len(args.excluded_pools) != 0:
    requirements += ' && (isUndefined(GLIDEIN_Entry_Name) || !stringListMember(GLIDEIN_Entry_Name, "' + ','.join(args.excluded_pools) + '", ","))'

if args.custom_requirements:
    requirements += ' && (' + args.custom_requirements + ')'

for ad in other_ads:
    print ad

print 'requirements = ' + requirements
