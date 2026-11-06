import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "apps" / "worker" / "src"))

from mistralai.workflows.core.config.config import config

config.worker.versioning.enabled = True
config.worker.versioning.deployment_name = "test-deployment"
config.worker.versioning.build_id = "test-build"

pytest_plugins = ["mistralai.workflows.testing.fixtures"]
