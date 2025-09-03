import logging
from luistervink.client import LuistervinkClient
from luistervink.dto import Task
from luistervink.handler import DetectionSoundHandler
from utils.helpers import get_settings
import sys

log = logging.getLogger('task_processor')
formatter = logging.Formatter("[%(name)s][%(levelname)s] %(message)s")
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
log.addHandler(handler)


class TasksProcessor:
    def __init__(self, client: LuistervinkClient):
        self.client = client
        self.handlers = [DetectionSoundHandler]

    def process_tasks(self):
        """Process tasks from the Luistervink API."""
        tasks = self.collect()
        log.info(f'{len(tasks)} task{"s" if len(tasks) == 1 else ""} collected')
        for task in tasks:
            log.info(
                f"[Luistervink] Processing task: {task.type} with spec: {task.spec}"
            )
            try:
                self.process(task)
                log.info(f"[Luistervink] Task processed successfully")
            except Exception as e:
                log.error(f"[Luistervink] Failed to process task: {task.type}: {e}")

    def process(self, task: Task):
        for handler in self.handlers:
            if handler.type == task.type:
                return handler(self.client, task.spec).handle()
        log.warning(f"[Luistervink] No handler found for task type: {task.type}")

    def collect(self) -> list[Task]:
        """Collect tasks from the Luistervink API."""
        try:
            response = self.client.get("tasks")
            if response.status_code != 200:
                log.error(
                    f"[Luistervink] Failed to fetch tasks: {response.status_code} {response.text}"
                )
            tasks = response.json()
            return [Task(**task) for task in tasks]
        except Exception as e:
            log.error(f"[Luistervink] Error collecting tasks: {e}")
            return []


if __name__ == "__main__":
    client = LuistervinkClient(get_settings())
    processor = TasksProcessor(client)
    processor.process_tasks()
