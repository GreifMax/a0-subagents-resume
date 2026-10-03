from helpers.extension import Extension

from usr.plugins.subagent_resume.helpers import runtime


class InjectPreservedSubordinatesHint(Extension):
    async def execute(self, loop_data=None, **kwargs):
        try:
            runtime.on_message_loop_start(self.agent, loop_data)
        except Exception:
            pass
