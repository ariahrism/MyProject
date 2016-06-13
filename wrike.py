import logging
import os
import requests
import time
from datetime import datetime, timedelta

my_env = os.getenv('my_env')

logging.captureWarnings(True)

client_id = os.environ.get('wrike_client_id')
client_secret = os.environ.get('wrike_client_secret')

pjm_folder = 'IEAAYQ33I4CX7X5T'


class new_creds:
    access_token = ''
    refresh_token = ''
    token_type = ''
    expire_date = datetime.now()

    rate_limit_track = 0
    last_api_call = datetime.now()
    time_diffs = []

    def __init__(self):
        pass

    def init(self, (new_token, new_renew, token_type)):
        self.access_token = new_token
        self.refresh_token = new_renew
        self.token_type = token_type
        self.expire_date = datetime.now() + timedelta(seconds=3600)

    def new_auth(self, auth_code):
        """ example response:
            {
                u'access_token': u'jAq9UQ-N-RWEFHIJKVU',
                u'refresh_token': u'T3kr-A-RWEFHIJKVU'
                u'token_type': u'bearer',
                u'expires_in': 3600,
            }
        """
        r = requests.post('https://www.wrike.com/oauth2/token',
                          data={'client_id': client_id,
                                'client_secret': client_secret,
                                'grant_type': 'authorization_code',
                                'code': auth_code})
        self.api_call()
        if r.status_code != 200:
            return False
        else:
            self.access_token, self.refresh_token, self.token_type = r.json()['access_token'], r.json()['refresh_token'], r.json()['token_type']
            return True

    def refresh(self):
        r = requests.post('https://www.wrike.com/oauth2/token', data={'client_id': client_id,
                                                                      'client_secret': client_secret,
                                                                      'grant_type': 'refresh_token',
                                                                      'refresh_token': self.refresh_token})
        self.api_call()
        if r.status_code != 200:
            return False
        else:
            self.access_token, self.refresh_token, self.token_type = r.json()['access_token'], r.json()['refresh_token'], r.json()['token_type']
            self.expire_date = datetime.now() + timedelta(seconds=3600)  # should change this to the json field
            return True

    def api_call(self):
        new_time = datetime.now()
        self.time_diffs.append((new_time - self.last_api_call).microseconds / 1000000.0)
        self.last_api_call = new_time

        if len(self.time_diffs) > 100:
            self.time_diffs = self.time_diffs[-100:]

        self.rate_limit_track = len(self.time_diffs) / (sum(self.time_diffs) if sum(self.time_diffs) is not 0 else 0.00001)
        if self.rate_limit_track > 10:
            print '%.2f' % self.rate_limit_track
        return self.rate_limit_track


def get_data(call, params=None):
    no_success = True
    tries = 3
    base_url = 'https://www.wrike.com/api/v3'
    while no_success and tries != 0:
        headers = {'Authorization': creds.token_type + ' ' + creds.access_token}
        r = requests.get(base_url + call, headers=headers, params=params)
        creds.api_call()
        print r.url
        if r.status_code != 200:
            print 'error, response: ', r.status_code
            print r.json()
        else:
            no_success = False  # means succeeded
        if r.status_code == 401:
            if not creds.refresh():
                return False
        tries -= 1
    return r.json()['data']


creds = new_creds()


def get_timelog_table():
    """
    First, make unique lists to iterate through (to save on API calls) then iterate though the unique lists, and attach them to "timelogs" json/dictionary
    :return:
    """

    timelogs = get_data('/timelogs')
    print len(timelogs)
    task_list = []
    user_list = []

    for log in timelogs:
        task_list.append(log['taskId'])
        user_list.append(log['userId'])

    unique_tasks = list(set(task_list))
    unique_users = list(set(user_list))

    unique_tasks_csv = ','.join(map(str, unique_tasks))
    task_details = get_data('/tasks/' + unique_tasks_csv)  # todo need to batch if its over 100 tasks

    super_task_dictionary = []  # create a dictionary of super task details
    task_details_copy = task_details
    for task in task_details_copy:
        dictionary_payload = {}
        if 'superTaskIds' in task and len(task['superTaskIds']) > 0:  # add custom id from parent task
            super_task_id = str(task['superTaskIds'][0])  # for readability

            if super_task_dictionary and next((super_task for super_task in super_task_dictionary if super_task['id'] == super_task_id), None):
                # if this super task id is already in the dictionary, just skip
                continue

            super_task_details = get_data('/tasks/' + super_task_id)[0]
            task_details.append(super_task_details)

            if 'customFields' in super_task_details and len(super_task_details['customFields']) > 0:
                if super_task_details['customFields'][0]['id'] == 'IEAAYQ33JUAACWWV':
                    dictionary_payload['opp_id'] = super_task_details['customFields'][0]['value']

            if 'opp_id' not in dictionary_payload:
                dictionary_payload['opp_id'] = ''
            dictionary_payload['super_task_title'] = super_task_details['title']
            dictionary_payload['id'] = super_task_details['id']
            super_task_dictionary.append(dictionary_payload)

    user_dictionary = []  # create a dictionary of user data (first name for now)
    for user in unique_users:
        user_details = get_data('/users/' + user)
        user_dictionary.append({'id': user, 'user_name': user_details[0]['firstName']})

    for log in timelogs:  # for each log, add the task data, then user data (first name)
        for task in task_details:
            if log['taskId'] == task['id']:
                log['task_title'] = task['title']
                log['super_task_title'] = ''
                task_opp_id = ''
                if 'customFields' in task and len(task['customFields']) > 0:  # add custom id from task if it exists
                    if task['customFields'][0]['id'] == 'IEAAYQ33JUAACWWV':
                        task_opp_id = task['customFields'][0]['value']

                # if there is a super task id in the task, fetch the details from the dictionary
                if 'superTaskIds' in task and len(task['superTaskIds']) > 0:
                    super_task_id = str(task['superTaskIds'][0])  # for readability

                    def get_parent_id(child_id):
                        # we know its a super task, but first we want to know if this super task has a super task
                        working_id = child_id
                        parent_id = next((item['superTaskIds'][0] for item in task_details if
                                          item['id'] == working_id and 'superTaskIds' in task and len(item['superTaskIds']) > 0), None)

                        if parent_id:
                            return get_parent_id(parent_id)
                        else:
                            return working_id

                    super_task_parent_id = get_parent_id(super_task_id)
                    super_task_simple_json = next((item for item in super_task_dictionary if item['id'] == super_task_parent_id), None)
                    if super_task_simple_json:
                        log['super_task_title'], task_opp_id = super_task_simple_json['super_task_title'], super_task_simple_json['opp_id']
                else:
                    log['super_task_title'] = task['title']
                log['task_opp_id'] = task_opp_id
                log['task_url'] = task['permalink']

        # add the user name
        user = next((item for item in user_dictionary if item['id'] == log['userId']), None)
        log['user_name'] = user['user_name']

    output = []
    for log in timelogs:  # log
        output.append(
            [str(datetime.fromtimestamp(time.mktime(time.strptime(log['createdDate'][:19], "%Y-%m-%dT%H:%M:%S"))) + timedelta(hours=9)), log['user_name'],
             log['task_opp_id'], log['super_task_title'], log['task_title'], '%.2f' % log['hours'], log['comment'], log['task_url']])

    return output


def get_project_details():
    print get_data('/accounts/IEAAYQ33/folders', params={'project': 'true'})
    pass
