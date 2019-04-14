from sqlalchemy.exc import IntegrityError

from common.models import *


from typing import NamedTuple
import pygsheets


class ProjectTuple(NamedTuple):
    project_id: int
    title: str
    customer: str
    project_code: str
    leader: str


class SheetParser:
    def __init__(self, service_file_path, sheet_url):
        self._gs = pygsheets.authorize(service_file=service_file_path)
        self._wrk = self._gs.open_by_url(sheet_url)[0]

    async def parse(self):
        active_projects = []

        for row in self._wrk.get_all_values(include_tailing_empty=False, include_tailing_empty_rows=False)[1:]:
            try:
                row[1] = int(row[1])
                active_projects.append(row[1])

                project = ProjectTuple(*row[1:6])
                if project.title == '':
                    continue

                db_project = await Project.get(project.project_id)
                leader_last, leader_first = project.leader.split(' ')
                leader = await Employee.query.where(db.and_(Employee.first_name == leader_first,
                                                            db.and_(Employee.last_name == leader_last,
                                                                    Employee.employee_role == 'leader'))).gino.first()
                upd_leader_id = leader.employee_id if leader else db_project.leader_id
                if db_project is not None:
                    await db_project.update(project_code=project.project_code,
                                            leader_id=upd_leader_id,
                                            active=True).apply()
                    continue

                if not leader:
                    continue

                await Project.create(project_id=project.project_id, leader_id=leader.employee_id,
                                     title=project.title, customer=project.customer, project_code=project.project_code,
                                     active=True)

            except (TypeError, IndexError, ValueError, IntegrityError):
                continue

        await Project.update.values(active=False).where(~Project.project_id.in_(active_projects)).gino.status()






