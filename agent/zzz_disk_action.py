from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


@AgentServer.custom_action("ScanDiskInventory")
class ScanDiskInventoryAction(CustomAction):
    """MaaFW entry point reserved for the real ZZZ disk scanner.

    The desktop backend still owns persistence and optimization. This action is
    intentionally thin until real templates/OCR regions are available.
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        print(f"ScanDiskInventory placeholder param: {argv.action_param}")
        return True
