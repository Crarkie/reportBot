from gino.ext.sanic import Gino
from datetime import datetime

db = Gino()


class Employee(db.Model):
    __tablename__ = 'employees'

    employee_id = db.Column(db.Integer, primary_key=True)
    leader_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id'))
    chat_id = db.Column(db.Integer)
    first_name = db.Column(db.Unicode(128), nullable=False, default='')
    last_name = db.Column(db.Unicode(128), nullable=False, default='')
    phone_number = db.Column(db.BigInteger)
    employee_role = db.Column(db.Unicode(32), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=False)
    vacation_from = db.Column(db.Date)
    vacation_to = db.Column(db.Date)

    _chat_id_idx = db.Index('employees_chat_id_idx', 'chat_id', unique=True)
    _leader_id_idx = db.Index('employees_leader_id_idx', 'leader_id')

    def __str__(self):
        return '{} {}'.format(self.last_name, self.first_name)


class Invite(db.Model):
    __tablename__ = 'invites'

    invite_code = db.Column(db.Unicode(64), primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    created_at = db.Column(db.DateTime, default=datetime.now)


class Project(db.Model):
    __tablename__ = 'projects'

    project_id = db.Column(db.Integer, primary_key=True)
    leader_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    title = db.Column(db.Unicode(128), nullable=False)
    customer = db.Column(db.Unicode(128), nullable=False, default='')
    project_code = db.Column(db.Unicode(128), nullable=False, default='')
    active = db.Column(db.Boolean, nullable=False, default=True)


class ReportStatistics(db.Model):
    __tablename__ = 'report_statistics'

    statistics_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.project_id', ondelete='CASCADE'))
    year = db.Column(db.Integer)
    month = db.Column(db.Integer)
    hours = db.Column(db.Float, default=0)
    count = db.Column(db.Integer, default=0)

    _employee_idx = db.Index('report_statistics_employee_idx', 'employee_id')
    _project_idx = db.Index('report_statistics_project_idx', 'project_id')


class Report(db.Model):
    __tablename__ = 'reports'

    report_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    report_date = db.Column(db.Date, nullable=False)


class ReportProject(db.Model):
    __tablename__ = 'report_projects'

    report_project_id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.project_id', ondelete='CASCADE'))
    report_id = db.Column(db.Integer, db.ForeignKey('reports.report_id', ondelete='CASCADE'))
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    hours = db.Column(db.Float, nullable=False, default=0.0)

    _employee_idx = db.Index('report_projects_employee_idx', 'employee_id')

