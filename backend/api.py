import pickle
from base64 import urlsafe_b64encode
from email.mime.text import MIMEText

import requests
import google.oauth2.credentials
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from models import Assignment, Activity


class LoginFailure(Exception):
    pass


class SLSHandler:
    BASE = 'https://vle.learning.moe.edu.sg'
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36',
    }

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

        self.ready = False

        self.login()

    def login(self):
        r = self.session.get(self.BASE + '/login')
        soup = BeautifulSoup(r.content, 'html.parser')
        csrf_token = soup.select_one('input[name=_csrf]')['value']

        credentials = {'username': self.username, 'password': self.password, '_csrf': csrf_token}

        r = self.session.post(self.BASE + '/login', data=credentials, allow_redirects=False)
        if r.headers['Location'] != '/':
            raise LoginFailure(r.headers['Location'])

        self.ready = True

    def get_assignments(self):
        r = self.session.get(self.BASE + '/pendingaction/ajax/list')
        return [Assignment(i) for i in r.json()['data']]

    def logout(self):
        self.session.post(self.BASE + '/logout', allow_redirects=False)
        self.ready = False

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.logout()


class GoogleHandler:
    def __init__(self, **credentials):
        self.service = build('driveactivity', 'v2', credentials=google.oauth2.credentials.Credentials(**credentials))

    def get_activities(self, folder_id):
        results = self.service.activity().query(body={
            'ancestorName': f'items/{folder_id}'
        }).execute()
        print(results['activities'])
        return list(map(Activity, results.get('activities', [])))

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.service.close()


class MailOAuth:
    def __init__(self):
        with open('service_account.pickle', 'rb') as f:
            creds = pickle.load(f)
            if creds.expired:
                creds.refresh(Request())

        self.service = build('gmail', 'v1', credentials=creds)

    def notify(self, email, caller, item):
        subject = 'Notification: New '
        if caller == 'sls':
            subject += 'SLS Assignment'
            description = f'Hi,\nA new SLS assignment has been created.\n\nTitle: {item.title}\nURL: {item.url}'
            if item.end_date:
                description += f'\nDue Date: {item.end_date_ui}'
        if caller == 'drive':
            subject += ' Drive Activity'
            description = f'Hi,\nA new drive activity has been detected.\n\nType: {item.key_action.type}\nURL: {item.url}'
            if item.end_date:
                description += f'\nDue Date: {item.end_date_ui}'

        message = MIMEText(description)
        message['to'] = email
        message['subject'] = subject
        self.service.users().messages().send(userId='me', body={
            'raw': urlsafe_b64encode(message.as_string().encode()).decode()
        }).execute()
        print(f'{email} - {subject}')
