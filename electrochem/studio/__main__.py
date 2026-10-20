import sys

from .app import main

# The guard matters: reading runs in spawned child processes, which import this
# module again; without it each child would open a second window.
if __name__ == "__main__":
    sys.exit(main())
