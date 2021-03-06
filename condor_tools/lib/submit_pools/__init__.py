import cms_global_pool

def presubmit(cluster_ad, proc_ads):
    if not cms_global_pool.check_cms_global_pool(cluster_ad, proc_ads):
        return 'CMS Global Pool'

    return ''

def postsubmit(proc_ads):
    cms_global_pool.dashboard_postsubmit(proc_ads)

def postexecute(proc_ad, db):
    cms_global_pool.dashboard_postexecute(proc_ad, db)

__all__ = [
    'presubmit',
    'postsubmit',
    'postexecute'
]
