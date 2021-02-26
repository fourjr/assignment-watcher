import flask
import uuid

def attach_session(func):
    def wrapper():
        session_id = flask.request.cookies.get('session')
        if session_id:
            session = flask.current_app.db.web_sessions.find_one({'id': session_id})
            if session is None:
                session_id = None

        if session_id is None:
            session_id = uuid.uuid4().hex
            session = {'id': session_id, 'google': {}, 'sls': {}}
            flask.current_app.db.web_sessions.insert_one(session)

        return func(session)
    wrapper.__name__ = func.__name__
    return wrapper
