import sqlite3
from crewai.tools import BaseTool
import os
from src.database import DB_PATH

class LogConstructiveFeedbackTool(BaseTool):
    name: str = "Log Constructive Feedback"
    description: str = "Log constructive feedback for an agent to improve its future runs. Pass inputs as 'AgentName|FeedbackText'."
    
    def _run(self, input_str: str) -> str:
        try:
            agent_name, feedback = input_str.split("|", 1)
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS feedback_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_name TEXT, feedback TEXT, timestamp TEXT)")
            from datetime import datetime
            cursor.execute("INSERT INTO feedback_memory (agent_name, feedback, timestamp) VALUES (?, ?, ?)", (agent_name, feedback, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return f"Successfully logged feedback for {agent_name}."
        except Exception as e:
            return f"Error logging feedback: {str(e)}"
