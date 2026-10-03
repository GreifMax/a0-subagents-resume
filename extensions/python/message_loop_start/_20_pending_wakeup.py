from helpers.extension import Extension

from usr.plugins.subagent_resume.helpers import config


class InjectPendingWakeupHint(Extension):
    async def execute(self, loop_data=None, **kwargs):
        if not self.agent or loop_data is None:
            return
        try:
            if not config.get_settings(self.agent).get("wakeup", True):
                return
            from usr.plugins.subagent_resume.helpers import wakeup

            hint = wakeup.pending_hint(self.agent)
            if hint and self.agent.number == 0:
                extras = getattr(loop_data, "extras_temporary", None)
                if extras is not None:
                    extras["subagent_resume_wakeup"] = hint
        except Exception:
            pass
