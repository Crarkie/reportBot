from gino.ext.sanic import Gino

db = Gino()


class Employee(db.Model):
    __tablename__ = 'employees'

    employee_id = db.Column(db.Integer, primary_key=True)
    leader_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id'))
    chat_id = db.Column(db.Integer)
    first_name = db.Column(db.Unicode(128), nullable=False, default='')
    middle_name = db.Column(db.Unicode(128), nullable=False, default='')
    last_name = db.Column(db.Unicode(128), nullable=False, default='')
    phone_number = db.Column(db.BigInteger)
    employee_role = db.Column(db.Unicode(32), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=False)

    _chat_id_idx = db.Index('employees_chat_id_idx', 'chat_id', unique=True)
    _leader_id_idx = db.Index('employees_leader_id_idx', 'leader_id')

    def __str__(self):
        return '{} {} {} - {}'.format(self.last_name, self.first_name, self.middle_name, self.phone_number)


class Invite(db.Model):
    __tablename__ = 'invites'

    invite_code = db.Column(db.Unicode(64), primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))


class Project(db.Model):
    __tablename__ = 'projects'

    project_id = db.Column(db.Integer, primary_key=True)
    leader_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    title = db.Column(db.Unicode(128), nullable=False)
    customer = db.Column(db.Unicode(128), nullable=False, default='')
    project_code = db.Column(db.Unicode(128), nullable=False, default='')
    active = db.Column(db.Boolean, nullable=False, default=True)


class Report(db.Model):
    __tablename__ = 'reports'

    report_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    report_date = db.Column(db.Date, nullable=False)


class ReportProject(db.Model):
    __tablename__ = 'report_projects'

    project_id = db.Column(db.Integer, db.ForeignKey('projects.project_id', ondelete='CASCADE'), primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('reports.report_id', ondelete='CASCADE'))
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.employee_id', ondelete='CASCADE'))
    hours = db.Column(db.Float, nullable=False, default=0.0)

    _employee_idx = db.Index('report_projects_employee_idx', 'employee_id')

