"""Resource Remover sub-tool package.

Provides automated scanning and deletion of Princess Connect Re:Dive original
resource assets after successful extraction, freeing up local disk space while
protecting critical system and tool directories.
"""

from .gui import ResourceRemoverApp

__all__ = ["ResourceRemoverApp"]
