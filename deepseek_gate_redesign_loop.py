import os
import sys
import json
import time
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

load_dotenv()
deepseek_key = os.getenv("DEEPSEEK_API_KEY")
os.environ["OPENAI_API_KEY"] = deepseek_key
os.environ["OPENAI_API_BASE"] = "https://api.deepseek.com"

llm = LLM(model="deepseek/deepseek-chat", api_key=deepseek_key, base_url="https://api.deepseek.com")

def change_task_status(task_id, new_status):
    try:
        with open('kanban.json', 'r') as f:
            board = json.load(f)
        target_task = None
        for status in list(board.keys()):
            for t in board[status]:
                if t['id'] == task_id:
                    target_task = t
                    board[status].remove(t)
                    break
            if target_task: break
                
        if target_task:
            if new_status not in board: board[new_status] = []
            board[new_status].append(target_task)
            with open('kanban.json', 'w') as f:
                json.dump(board, f, indent=4)
    except:
        pass

@tool("Read Tools File")
def read_tools(dummy: str) -> str:
    """Reads patch_stock_tools.py and other relevant gate files."""
    try:
        with open('patch_stock_tools.py', 'r') as f:
            return f.read()
    except Exception as e:
        return str(e)

@tool("Finish Task Tool")
def finish_tasks(dummy: str) -> str:
    """Marks the gate redesign tasks as Done."""
    for t_id in ["T3-B", "T3-C", "T3-D", "T3-E", "T3-F", "T3-G"]:
        change_task_status(t_id, "Done")
    return "Phase 2 Tasks marked as Done."

def load_memory(role):
    try:
        with open(f"agent_memory/{role}.md", "r") as f:
            return f.read()
    except:
        return ""

math_engine = Agent(
    role="Math Engine",
    goal="Implement the 6 critical gate parameter fixes (Cooldown, Brackets, ATR, EMA Ext, S/R, GEX).",
    backstory=load_memory('evaluator_team'),
    verbose=True,
    allow_delegation=False,
    tools=[read_tools, finish_tasks],
    llm=llm
)

task_redesign = Task(
    description=(
        "1. Read the existing gate parameters using 'Read Tools File'.\n"
        "2. Formulate the mathematical logic for the 6 new rules:\n"
        "   - T3-B: 15-30m cooldown per ticker/direction.\n"
        "   - T3-C: Bracket sanity validator (TP1/SL must not be inverted).\n"
        "   - T3-D: ATR stop scaling floor.\n"
        "   - T3-E: EMA extension/distance filter.\n"
        "   - T3-F: S/R buffer zone.\n"
        "   - T3-G: GEX recalibration.\n"
        "3. Output the exact Python functions needed to implement these gates.\n"
        "4. Use 'Finish Task Tool' to mark them as Done on the Kanban board."
    ),
    expected_output="A full Python logic block for the redesigned >80% gate.",
    agent=math_engine
)

if __name__ == "__main__":
    for t_id in ["T3-B", "T3-C", "T3-D", "T3-E", "T3-F", "T3-G"]:
        change_task_status(t_id, "In Progress")
        time.sleep(0.5)
    
    print("Initiating DeepSeek Phase 2: Gate Redesign (Tracing Enabled)")
    
    # TRACING = TRUE ADDED HERE
    crew = Crew(
        agents=[math_engine], 
        tasks=[task_redesign], 
        process=Process.sequential, 
        verbose=True,
        output_log_file=True # CrewAI logging integration
    )
    crew.kickoff()
    print("Phase 2 Complete.")
