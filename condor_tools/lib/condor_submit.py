#!/usr/bin/env python

import os
import sys
import time
import subprocess
import threading
import Queue

import htcondor
import classad

class RCException(Exception):
    pass

def read_stdin(queue):
    # Wait for stdin input until EOF and write back in the queue
    text = sys.stdin.read()
    queue.put(text)

def call_executable(args):
    EXECUTABLE = '/usr/bin/condor_submit'
    TIMEOUT = 30

    proc = subprocess.Popen([EXECUTABLE] + args, stdout = subprocess.PIPE, stderr = subprocess.PIPE, stdin = subprocess.PIPE)
    time.sleep(0.5)

    wait_start = time.time()
    input_thread = None

    while proc.poll() is None:
        # condor_submit has not returned. Maybe it's waiting for input to stdin.

        if input_thread is None:
            # stdin.read() is blocking. Use a separate thread to wait for input.
            queue = Queue.Queue()
            input_thread = threading.Thread(target = read_stdin, args = (queue,))
            input_thread.daemon = True
            input_thread.start()

        try:
            stdin_text = queue.get(block = False)
        except Queue.Empty:
            pass
        else:
            input_thread.join()
            input_thread = None
            proc.stdin.write(stdin_text)

            wait_start = time.time()

        time.sleep(0.5)

        if time.time() - wait_start > TIMEOUT:
            sys.stderr.write('condor_submit timed out. Did you forget a "queue" line?\n')
            sys.stderr.flush()
            raise RuntimeError('condor_submit timeout')

    return proc.returncode, proc.stdout.read(), proc.stderr.read()

def parse_classad(classad_file):
    all_ads = []

    current_cluster_id = 0

    while True:
        try:
            ad = classad.parseNext(classad_file)
        except StopIteration:
            # We are done
            break
        
        if 'ClusterId' in ad and ad['ClusterId'] != current_cluster_id:
            current_cluster_id = ad['ClusterId']

            # create ad objects, add to the output, and keep updating the objects
            cluster_ad = classad.ClassAd()
            proc_ads = []
            all_ads.append((cluster_ad, proc_ads))

        # Adjust ad contents
        del ad['ClusterId']
        del ad['ProcId']

        if 'x509userproxy' in ad:
            # condor_submit dry-run / dump do not evaluate the proxy contents
            set_x509_attributes(ad)

        if len(cluster_ad) == 0:
            cluster_ad.update(ad)

        proc_ads.append((ad, 1))

    return all_ads

def set_x509_attributes(ad):
    def voms_proxy_info(arg):
        # call voms-proxy-info -file <proxy> -<arg>
        proc = subprocess.Popen(['voms-proxy-info', '-file', ad['x509userproxy'], '-' + arg], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        out, err = proc.communicate()
            
        if proc.returncode != 0:
            sys.stdout.write(out)
            sys.stdout.flush()
            sys.stderr.write(err)
            sys.stderr.flush()
    
            raise RCException(proc.returncode, '')

        return out.strip().split('\n')

    # I don't think there is a way to get this information from voms client command line tools
    ad['x509UserProxyEmail'] = 'submit@mit.edu'
    
    timeleft = int(voms_proxy_info('timeleft')[0])
    ad['x509UserProxyExpiration'] = int(time.time()) + timeleft

    # Cerficate subject is the issuer of the proxy
    subject = voms_proxy_info('issuer')[0]
    ad['x509userproxysubject'] = subject

    vo = voms_proxy_info('vo')[0]
    ad['x509UserProxyVOName'] = vo

    fqans = voms_proxy_info('fqan')
    ad['x509UserProxyFirstFQAN'] = fqans[0]
    ad['x509UserProxyFQAN'] = ','.join([subject] + fqans)

def submit(cluster_ad, proc_ads):
    schedd = htcondor.Schedd()
    sys.stdout.write('Submitting job(s)')
    sys.stdout.flush()

    result_ads = []

    cluster_id = schedd.submitMany(cluster_ad, proc_ads, ad_results = result_ads)
    
    sys.stdout.write('.' * len(proc_ads) + '\n')
    sys.stdout.write('%d job(s) submitted to cluster %d.\n' % (len(proc_ads), cluster_id))
    sys.stdout.flush()

    return result_ads
