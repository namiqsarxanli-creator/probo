"""Sübut Agentliyi — the project's main entry point. PyCharm: Run main.py → http://127.0.0.1:8830

The earlier Research Studio still runs with research_studio.py (port 8812);
see agentlik.py for the replay and recording options.
"""
from agency.server import serve

if __name__ == '__main__':
    serve()
