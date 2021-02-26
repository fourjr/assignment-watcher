import os
import time

import pymongo
from dotenv import load_dotenv

from api import LoginFailure, MailOAuth, SLSHandler, GoogleHandler
from models import AssignmentStatus


load_dotenv()

db = pymongo.MongoClient(os.environ['MONGO_URI']).assignment_watcher
mail = MailOAuth()

while True:
    cursor = db.users.find({'$where': '(this.google && this.google.length > 1) || (this.sls && this.sls.length > 1)'})
    for u in cursor:
        # SCHEMA:
        # {
        #   email,
        #   sls_credentials: {username, password}
        #   google_credentials: {token, refresh_token, token_uri, client_id, client_secret, scopes}
        #   sls: [{event}]
        #   google: [{event, folder_id}],
        #   seen_sls: [],
        #   seen_google: []
        # }
        if 'NEW_ASSIGNMENT' in [i['event'] for i in u.get('sls', [])] and u.get('sls_credentials'):
            try:
                with SLSHandler(**u['sls_credentials']) as sls:
                    assignments = sls.get_assignments()
                    assignments = list(filter(lambda x: x.status != AssignmentStatus.COMPLETED and x.id not in u.get('seen_sls', []), assignments))
                    for i in assignments:
                        mail.notify(u['email'], 'sls', i)

                    if assignments:
                        db.users.find_one_and_update(u, {'$addToSet': {'seen_sls': {'$each': [i.id for i in assignments]}}})
            except LoginFailure:
                db.users.find_one_and_update(u, {'$unset': {'sls_credentials': ''}})

        with GoogleHandler(**u['google_credentials']) as ggle:
            new_ids = []
            for item in u.get('google', []):
                activites = ggle.get_activities(item['folder_id'])
                print(activites)
                for a in activites:
                    print(a)
                    id_ = f'{a.timestamp}-{item["folder_id"]}'
                    if id_ not in u.get('seen_google', []):
                        if any(i.type == item['event'] for i in a):
                            mail.notify(u['email'], 'google', i)
                        
                        new_ids.append(id_)
            
            if new_ids:
                db.users.find_one_and_update(u, {'$addToSet': {'seen_google': {'$each': new_ids}}})

    break
    time.sleep(60)
