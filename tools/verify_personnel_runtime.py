"""Compatibility entry point for the current crew-list and Final-plan check.

The former passenger-execution UI is historical. This alias keeps the old
command usable and runs the same current acceptance workflow.
"""
from verify_crew_final_runtime import main

if __name__ == '__main__':
    main()
