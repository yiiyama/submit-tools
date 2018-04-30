import sys
import pwd
import logging
import MySQLdb

LOG = logging.getLogger(__name__)

class HistoryDB(object):
    """Interface to condor_history DB"""

    CONDOR_INSTANCE = 1
    DB = 'condor_history'
    READ_ONLY = False

    def __init__(self, params = None):
        if params is None:
            with open('/var/spool/condor/history_db.passwd') as pfile:
                passwd = pfile.read().strip()
            
            self.connection_parameters = {'host': 'localhost', 'user': 'condor_write', 'passwd': passwd, 'db': HistoryDB.DB}
        else:
            self.connection_parameters = dict(params)

        self.connection = MySQLdb.connect(**self.connection_parameters)

        # cached dictionary ({str: id})
        self._users = None
        self._sites = None
        self._frontends = None

    def query(self, sql, *args):
        if HistoryDB.READ_ONLY:
            sql_lower = sql.lower().strip()
            if sql_lower.startswith('insert') or sql_lower.startswith('delete') or \
                    sql_lower.startswith('update') or sql_lower.startswith('truncate') or \
                    sql_lower.startswith('drop'):

                return 0

        cursor = self.connection.cursor()
    
        try:
            for attempt in range(10):
                try:
                    cursor.execute(sql, args)
                except MySQLdb.OperationalError:
                    LOG.error(str(sys.exc_info()[1]))
                    last_except = sys.exc_info()[1]
                    # reconnect to server
                    cursor.close()
                    self.connection = MySQLdb.connect(**self.connection_parameters)
                    cursor = self.connection.cursor()
                else:
                    break
    
            else: # 10 failures
                LOG.error('Too many OperationalErrors. Last exception:')
                raise last_except
    
        except:
            LOG.error('There was an error executing the following statement:')
            LOG.error(sql[:10000])
            LOG.error(sys.exc_info()[1])
            raise
    
        result = cursor.fetchall()
    
        if cursor.description is None:
            if cursor.lastrowid != 0:
                # insert query
                return cursor.lastrowid
            else:
                return cursor.rowcount
    
        elif len(result) != 0 and len(result[0]) == 1:
            # single column requested
            return [row[0] for row in result]
    
        else:
            return list(result)
    
    def cluster_exists(self, instance, cluster_id):
        return self.query('SELECT COUNT(*) FROM `job_clusters` WHERE (`instance`, `cluster_id`) = (%s, %s)', instance, cluster_id)[0] != 0

    def get_user(self, uname):
        if self._users is None:
            self._users = dict(self.query('SELECT `name`, `user_id` FROM `users`'))

        try:
            return self._users[uname]
        except KeyError:
            try:
                user_id = pwd.getpwnam(uname).pw_uid
            except KeyError:
                # User unknown to system password database
                LOG.warning('Unknown user %s', uname)
                return 0
    
            LOG.info('Inserting user %s(%d)', uname, user_id)
            self.query('INSERT INTO `users` VALUES (%s, %s)', user_id, uname)
            self._users[uname] = user_id
    
            return user_id

    def get_site(self, sname, pool, frontend_name):
        if self._sites is None:
            self._sites = dict()
            sql = 'SELECT `site_id`, `site_name`, `site_pool` FROM `sites`'
            for site_id, site_name, site_pool in self.query(sql):
                self._sites[(site_name, site_pool)] = site_id

        try:
            return self._sites[(sname, pool)]
        except KeyError:
            LOG.info('Inserting site %s/%s (frontend %s)', site_name, site_pool, frontend_name)

            frontend_id = self.get_frontend(frontend_name)
    
            site_id = self.query('INSERT INTO `sites` (`site_name`, `site_pool`, `frontend_id`) VALUES (%s, %s, %s)', site_name, site_pool, frontend_id)
            self._sites[(site_name, site_pool)] = site_id

            return site_id

    def get_frontend(self, frontend_name):
        if self._frontends is None:
            self._frontends = dict(self.query('SELECT `frontend_name`, `frontend_id` FROM `frontends`'))

        try:
            return self._frontends[frontend_name]
        except KeyError:
            LOG.info('Inserting frontend %s', frontend_name)

            frontend_id = self.query('INSERT INTO `frontends` (`frontend_name`) VALUES (%s)', frontend_name)
            self._frontends[frontend_name] = frontend_id

            return frontend_id
