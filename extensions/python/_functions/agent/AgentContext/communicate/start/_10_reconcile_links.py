from helpers.extension import Extension

from usr.plugins.subagent_resume.helpers import runtime


class ReconcileSubordinateLinks(Extension):
    def execute(self, data: dict = {}, **kwargs):
        try:
            runtime.on_communicate_start(data)
        except Exception:
            pass
