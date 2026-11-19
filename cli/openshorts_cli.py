"""OpenShorts CLI (compatibility wrapper for CREOVIS CLI)."""
from creovis_cli import *  # noqa: F401, F403
import creovis_cli

main = creovis_cli.main

if __name__ == "__main__":
    main()
