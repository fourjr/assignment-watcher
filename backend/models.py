from datetime import datetime
from enum import Enum


class Activity:
    def __init__(self, data):
        self._data = data
        self.timestamp = datetime.strptime(data['timestamp'], r'%Y-%m-%dT%H:%M:%S.%fZ')
        self.actors = [Actor(i) for i in data['actors']]
        self.targets = [Target(i) for i in data['targets']]
        self.actions = [Action(i, self) for i in data['actions']]
        self.key_action = next(i for i in self.actions if i == data['primaryActionDetail'])

    @property
    def action_types(self):
        for i in self.actions:
            yield i.type


class Action:
    def __init__(self, data, parent):
        # data['detail'] will only have 1 kv
        self._data = data
        self.parent = parent

        self.type = list(data['detail'].keys())[0]
        self.details = list(data['detail'].values())[0]
        self.actor = data.get('actor', parent.actors[0])
        self.target = data.get('target', parent.targets[0])
        self.timestamp = parent.timestamp


class Actor:
    def __init__(self, data):
        # will only have 1 kv
        self._data = data
        self.type = list(data.keys())[0]
        self.details = list(data.values())[0]

    def get_info(self):
        raise NotImplementedError
        if self.type == 'User':
            user_type = list(self.details.keys())[0]
            if user_type == 'knownUser':
                vals = self.details.values()
                return vals['personName']  # https://developers.google.com/people/


class Target:
    def __init__(self, data):
        # will only have 1 kv
        self._data = data
        self.type = list(data.keys())[0]
        self.details = list(data.values())[0]

        # set all fields to None first
        self.name = self.details.get('name')  # drive/driveItem
        self.title = self.details.get('title')  # drive/driveItem

        root = self.details.get('root', self.details.get('parent'))
        self.root = Target({'driveItem': root}) if root else None

        self.url = self.details.get('linkToDiscussion')
        self.mime_type = self.details.get('mimeType')
        self.owner = self.details.get('owner')

        possible_types = ('driveFolder', 'driveFile')
        try:
            self.file_type = next(i for i in self.details.keys() if i in possible_types)
        except StopIteration:
            self.file_type = None


# SLS

class Assignment:
    def __init__(self, data):
        self.id = data['id']
        self.student_id = data['studentId']
        self.start_date = datetime.strptime(data['startDate'], '%Y%m%d%H%M%S')
        self.start_date_ui = data['startDateUI']
        if data['endDate']:
            self.end_date = datetime.strptime(data['endDate'], '%Y%m%d%H%M%S')
        else:
            self.end_date = None
        self.end_date_ui = data['endDateUI']
        self.overdue = data['overdue']
        self.title = data['title']
        self.resource_type = data['resourceType']
        self.lesson_uuid = data['lessonUuid']
        self.assignment_uuid = data['assignmentUuid']
        self.status = AssignmentStatus[data['status']]

    def __repr__(self):
        return '<Assignment id={0.id} title={0.title} status={0.status}>'.format(self)

    @property
    def url(self):
        return 'https://vle.learning.moe.edu.sg/assignment/attempt/' + self.assignment_uuid


class AssignmentStatus(Enum):
    NEW = 0
    IN_PROGRESS = 1
    COMPLETED = 2
