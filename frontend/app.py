import json
import os

import flask
import pymongo
import google.oauth2.credentials
import google_auth_oauthlib.flow
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googleapiclient.discovery import build

from .utils import attach_session


load_dotenv()

app = flask.Flask(__name__)
app.db = pymongo.MongoClient(os.environ['MONGO_URI']).assignment_watcher
if app.env == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


@app.route('/dashboard')
@attach_session
def dashboard(session):
    if session.get('google'):
        service = build('oauth2', 'v2', credentials=google.oauth2.credentials.Credentials(**session['google']))
        userinfo = service.userinfo().get().execute()

        user_data = app.db.users.find_one({'email': session['email']})
        event_listeners = {
            'google': user_data.get('google', {}),
            'sls': user_data.get('sls', {})
        }
        return flask.render_template(
            'dashboard.html',
            googleLogin={'name': userinfo['name']},
            slsLogin=session.get('sls', {}),
            slsLoginStr=json.dumps(session.get('sls', {})),
            rsaPublicKey=os.environ['SLS_RSAPUBKEY'],
            eventListeners=event_listeners
        )
    else:
        return flask.redirect('/login/google')


@app.route('/logout')
@attach_session
def logout(session):
    app.db.web_sessions.find_one_and_update({'id': session['id']}, {'$unset': {'google': '', 'sls': ''}})
    return 'Logged out'


@app.route('/logoutsls')
@attach_session
def logoutsls(session):
    app.db.web_sessions.find_one_and_update({'id': session['id']}, {'$unset': {'sls': ''}})
    return flask.redirect('/dashboard')


@app.route('/login/google')
def login_google():    
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        'client_secret.json',
        scopes=[
            'openid',
            'https://www.googleapis.com/auth/drive.activity.readonly',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
    )

    # TODO: change uri
    flow.redirect_uri = 'http://localhost:8000/callback'

    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    return flask.redirect(authorization_url)


@app.route('/callback')
@attach_session
def callback(session):
    state = flask.request.args['state']
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        'client_secret.json',
        scopes=[
            'openid',
            'https://www.googleapis.com/auth/drive.activity.readonly',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ],
        state=state)
    flow.redirect_uri = flask.url_for('callback', _external=True)

    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials
    session['google'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    service = build('oauth2', 'v2', credentials=google.oauth2.credentials.Credentials(**session['google']))
    userinfo = service.userinfo().get().execute()

    app.db.users.insert_one({'email': userinfo['email'], 'google_credentials': session['google']})
    app.db.web_sessions.find_one_and_update({'id': session['id']}, {'$set': {'google': session['google'], 'email': userinfo['email']}})

    resp = flask.make_response(flask.redirect('/dashboard'))
    resp.set_cookie('session', session['id'])
    return resp


@app.route('/login/sls', methods=['POST'])
@attach_session
def login_sls(session):
    sess = requests.Session()
    sess.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36'

    r = sess.get('https://vle.learning.moe.edu.sg/login')
    soup = BeautifulSoup(r.content, 'html.parser')

    data = {
        'username': flask.request.json['username'],
        'password': flask.request.json['password'],
        '_csrf': soup.select_one('input[name=_csrf]')['value']
    }

    r = sess.post('https://vle.learning.moe.edu.sg/login', headers={'Host': 'vle.learning.moe.edu.sg'}, data=data, allow_redirects=False)
    if r.headers['Location'] == '/':
        service = build('oauth2', 'v2', credentials=google.oauth2.credentials.Credentials(**session['google']))
        userinfo = service.userinfo().get().execute()

        del data['_csrf']
        app.db.users.find_one_and_update(
            {'email': userinfo['email']},
            {'$set': {'sls_credentials': data, 'google_credentials': session['google']}},
            upsert=True
        )
        app.db.web_sessions.find_one_and_update({'id': session['id']}, {'$set': {'sls': data}})

        sess.post('https://vle.learning.moe.edu.sg/logout', allow_redirects=False)
        return '', 204
    else:
        # invalid
        return '', 403


@app.route('/save', methods=['POST'])
@attach_session
def save(session):
    data = {
        'sls': flask.request.json['sls'],
        'google': flask.request.json['google']
    }

    app.db.users.find_one_and_update({'email': session['email']}, {'$set': data})
    return '', 204
