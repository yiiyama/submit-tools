"""
db.py - Utility wrapper for MySQLdb
"""

import sys
import logging
import MySQLdb

logger = logging.getLogger(__name__)

with open('/var/spool/condor/history_db.passwd') as pfile:
    passwd = pfile.read().strip()

connection_parameters = {'host': 'localhost', 'user': 'condor_write', 'passwd': passwd, 'db': 'condor_history'}
connection = MySQLdb.connect(**connection_parameters)

def db_query(sql, *args):
    global connection

    cursor = connection.cursor()

    try:
        for attempt in range(10):
            try:
                cursor.execute(sql, args)
                break
            except MySQLdb.OperationalError:
                logger.error(str(sys.exc_info()[1]))
                last_except = sys.exc_info()[1]
                # reconnect to server
                cursor.close()
                connection = MySQLdb.connect(**connection_parameters)
                cursor = connection.cursor()

        else: # 10 failures
            logger.error('Too many OperationalErrors. Last exception:')
            raise last_except

    except:
        logger.error('There was an error executing the following statement:')
        logger.error(sql[:10000])
        logger.error(sys.exc_info()[1])
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
