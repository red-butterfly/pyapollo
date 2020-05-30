#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2019/
# @Author  : Lin Luo/ Bruce Liu
# @Email   : 15869300264@163.com
import hashlib
import json
import logging
import os
import threading
import time
import base64
import hmac
from hashlib import sha1
from urllib.parse import quote

import requests


class ApolloClient(object):
    """
    this module is modified from the project: https://github.com/filamoon/pyapollo
    and had commit the merge request to the original repo
    thanks for the contributors
    since the contributors had stopped to commit code to the original repo, please submit issue or commit to https://github.com/BruceWW/pyapollo
    """

    def __init__(self, app_id, cluster='default', config_server_url='http://localhost:8080', timeout=60, ip=None,
                 cycle_time=300, cache_file_path=None, secret=None):
        """

        :param app_id:
        :param cluster:
        :param config_server_url:
        :param timeout:
        :param ip: the deploy ip for grey release
        :param cycle_time: the cycle time to update configuration content from server
        :param cache_file_path: local cache file store path
        "param secret: after Apollo 1.6.0, if config secret, should use secret
        """
        self.config_server_url = config_server_url
        self.app_id = app_id
        self.cluster = cluster
        self.timeout = timeout
        self.secret = secret
        self.stopped = False
        self.ip = self.init_ip(ip)

        self._stopping = False
        self._cache = {}
        self._notification_map = {'application': -1}
        self._cycle_time = cycle_time
        self._hash = {}
        if cache_file_path is None:
            self._cache_file_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config')
        else:
            self._cache_file_path = cache_file_path
        self._path_checker()

    @staticmethod
    def init_ip(ip):
        """
        for grey release
        :param ip:
        :return:
        """
        if ip is None:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 53))
                ip = s.getsockname()[0]
            finally:
                s.close()
        return ip

    @staticmethod
    def hash_hmac(data, key, sha1):
        '''
        encrypt by HMACSHA1
        :param data: encrypt data;
        :param key: encrypt key;
        :param sha
        '''
        hmac_code = hmac.new(key.encode(), data.encode(), sha1).digest()
        return base64.b64encode(hmac_code).decode()

    def get_headers(self, base_url):
        timestamp = str(int(time.time()*1000))
        authorization = self.hash_hmac('{}\n{}'.format(timestamp, base_url), self.secret, sha1)
        headers = {
            'Authorization': 'Apollo {}:{}'.format(self.app_id, authorization),
            'Timestamp': timestamp
        }

        return headers

    def get_value(self, key, default_val=None, namespace='application', auto_fetch_on_cache_miss=False):
        """
        get the configuration value
        :param key:
        :param default_val:
        :param namespace:
        :param auto_fetch_on_cache_miss:
        :return:
        """
        if namespace not in self._notification_map:
            self._notification_map[namespace] = -1
            logging.getLogger(__name__).info("Add namespace '%s' to local notification map", namespace)

        if namespace not in self._cache:
            self._cache[namespace] = {}
            logging.getLogger(__name__).info("Add namespace '%s' to local cache", namespace)
            # This is a new namespace, need to do a blocking fetch to populate the local cache
            self._long_poll()

        if key in self._cache[namespace]:
            return self._cache[namespace][key]
        else:
            if auto_fetch_on_cache_miss:
                return self._cached_http_get(key, default_val, namespace)
            else:
                return default_val

    def start(self, use_event_let=False, event_let_monkey_patch=False, catch_signals=True):
        """
        Start the long polling loop. Two modes are provided:
        1: thread mode (default), create a worker thread to do the loop. Call self.stop() to quit the loop
        2: event_let mode (recommended), no need to call the .stop() since it is async
        First do a blocking long poll to populate the local cache, otherwise we may get racing problems
        :param use_event_let:
        :param event_let_monkey_patch:
        :param catch_signals:
        :return:
        """
        if len(self._cache) == 0:
            self._long_poll()
        if use_event_let:
            import eventlet
            if event_let_monkey_patch:
                eventlet.monkey_patch()
            eventlet.spawn(self._listener)
        else:
            if catch_signals:
                import signal
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
                signal.signal(signal.SIGABRT, self._signal_handler)
            t = threading.Thread(target=self._listener)
            t.setDaemon(True)
            t.start()

    def stop(self):
        """
        stop the client
        :return:
        """
        self._stopping = True
        logging.getLogger(__name__).info("Stopping listener...")

    def _cached_http_get(self, key, default_val, namespace='application'):
        """
        get the configuration content from server with cache
        :param key:
        :param default_val:
        :param namespace:
        :return:
        """
        base_url = '/configfiles/json/{}/{}/{}?ip={}'.format(
            self.app_id, self.cluster, namespace, self.ip
        )

        data = {}
        try:
            r = requests.get(
                '{}{}'.format(self.config_server_url, base_url), 
                headers = self.get_headers(base_url) if self.secret else None
            )
            if r.ok:
                data = r.json()
                self._cache[namespace] = data
                logging.getLogger(__name__).info('Updated local cache for namespace %s', namespace)
                self._update_local_cache(data, namespace)
            else:
                if self._cache[namespace] is None or len(self._cache[namespace]) == 0:
                    logging.getLogger(__name__).info('cached http get configuration from local cache file')
                    data = self._get_local_cache(namespace)
                else:
                    data = self._cache[namespace]
        except BaseException as e:
            logging.getLogger(__name__).warning(str(e))
            data = self._get_local_cache(namespace)
        finally:
            if key in data:
                return data[key]
            else:
                return default_val

    def _uncached_http_get(self, namespace='application'):
        """
        get thr configuration content from server without cache
        :param namespace:
        :return:
        """
        base_url = '/configs/{}/{}/{}?ip={}'.format(self.app_id, self.cluster, namespace, self.ip)

        try:
            r = requests.get(
                '{}{}'.format(self.config_server_url, base_url),
                headers = self.get_headers(base_url) if self.secret else None
            )
            if r.status_code == 200:
                data = r.json()
                self._cache[namespace] = data['configurations']
                logging.getLogger(__name__).info('Updated local cache for namespace %s release key %s: %s',
                                                 namespace, data['releaseKey'],
                                                 repr(self._cache[namespace]))
                self._update_local_cache(data, namespace)
            else:
                data = self._get_local_cache(namespace)
                logging.getLogger(__name__).info('uncached http get configuration from local cache file')
                self._cache[namespace] = data['configurations']
        except BaseException as e:
            logging.getLogger(__name__).warning(str(e))
            data = self._get_local_cache(namespace)
            self._cache[namespace] = data['configurations']

    def _signal_handler(self):
        logging.getLogger(__name__).info('You pressed Ctrl+C!')
        self._stopping = True

    def _path_checker(self):
        """
        create configuration cache file directory if not exits
        :return:
        """
        if not os.path.isdir(self._cache_file_path):
            os.mkdir(self._cache_file_path)

    def _update_local_cache(self, data, namespace='application'):
        """
        if local cache file exits, update the content
        if local cache file not exits, create a version
        :param data: new configuration content
        :param namespace::s
        :return:
        """
        new_string = json.dumps(data)
        new_hash = hashlib.md5(new_string.encode('utf-8')).hexdigest()
        if self._hash.get(namespace) == new_hash:
            pass
        else:
            with open(os.path.join(self._cache_file_path, '%s_configuration_%s.txt' % (self.app_id, namespace)),
                      'w') as f:
                f.write(new_string)
            self._hash[namespace] = new_hash

    def _get_local_cache(self, namespace='application'):
        """
        get configuration from local cache file
        if local cache file not exits than return empty dict
        :param namespace:
        :return:
        """
        cache_file_path = os.path.join(self._cache_file_path, '%s_configuration_%s.txt' % (self.app_id, namespace))
        if os.path.isfile(cache_file_path):
            with open(cache_file_path, 'r') as f:
                result = json.loads(f.readline())
            return result
        return {}

    def _long_poll(self):
        notifications = []
        for key in self._notification_map:
            notification_id = self._notification_map[key]
            notifications.append({
                'namespaceName': key,
                'notificationId': notification_id
            })

        base_url = '/notifications/v2?appId={}&cluster={}&notifications={}'.format(
            self.app_id, self.cluster, quote(json.dumps(notifications, ensure_ascii=False), 'utf-8')
        )
        
        try:
            r = requests.get(url='{}{}'.format(self.config_server_url, base_url), 
                timeout=self.timeout,
                headers = self.get_headers(base_url) if self.secret else None
            )

            logging.getLogger(__name__).debug('Long polling returns %d: url=%s', r.status_code, r.request.url)

            if r.status_code == 304:
                # no change, loop
                logging.getLogger(__name__).debug('No change, loop...')
                return

            if r.status_code == 200:
                data = r.json()
                for entry in data:
                    ns = entry['namespaceName']
                    nid = entry['notificationId']
                    logging.getLogger(__name__).info("%s has changes: notificationId=%d", ns, nid)
                    self._uncached_http_get(ns)
                    self._notification_map[ns] = nid
                    return
            else:
                logging.getLogger(__name__).warning('Sleep...')
                time.sleep(self.timeout)
                return
        except requests.exceptions.ReadTimeout as e:
            logging.getLogger(__name__).warning(str(e))
        except requests.exceptions.ConnectionError as e:
            logging.getLogger(__name__).warning(str(e))
            self._load_local_cache_file()

    def _load_local_cache_file(self):
        """
        load all cached files from local path
        is only used while apollo server is unreachable
        :return:
        """
        for file_name in os.listdir(self._cache_file_path):
            file_path = os.path.join(self._cache_file_path, file_name)
            if os.path.isfile(file_path):
                file_simple_name, file_ext_name = os.path.splitext(file_name)
                if file_ext_name == '.swp':
                    continue
                namespace = file_simple_name.split('_')[-1]
                with open(file_path) as f:
                    self._cache[namespace] = json.loads(f.read())['configurations']
        return True

    def _listener(self):
        """

        :return:
        """
        logging.getLogger(__name__).info('Entering listener loop...')
        while not self._stopping:
            self._long_poll()
            time.sleep(self._cycle_time)

        logging.getLogger(__name__).info("Listener stopped!")
        self.stopped = True