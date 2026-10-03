from helpers.extension import Extension

from usr.plugins.subagent_resume.helpers import runtime


class ReconcileOnMonologueStart(Extension):
    async def execute(self, **kwargs):
        try:
            runtime.on_monologue_start(self.agent)
        except Exception:
            pass
