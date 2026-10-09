#!/bin/bash
export STREAMLIT_CREDENTIALS_EMAIL=""
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
source venv/bin/activate
echo "" | streamlit run kanban_app.py --server.port 8502 --server.fileWatcherType none
