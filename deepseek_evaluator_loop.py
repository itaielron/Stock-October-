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
        # Find and remove from old status
        for status in board.keys():
            for t in board[status]:
                if t['id'] == task_id:
                    target_task = t
                    board[status].remove(t)
                    break
            if target_task:
                break
                
        if target_task:
            if new_status not in board:
                board[new_status] = []
            board[new_status].append(target_task)
            with open('kanban.json', 'w') as f:
                json.dump(board, f, indent=4)
            print(f"KANBAN UPDATE: Moved {task_id} to {new_status}")
    except Exception as e:
        print(f"Failed to update kanban: {e}")

@tool("Read Signals Tool")
def read_signals(dummy: str) -> str:
    """Reads the historical signals from valid_signals.json to analyze them."""
    try:
        import glob
        files = glob.glob("valid_signals*.json")
        if not files: return "No signal files found."
        with open(files[-1], 'r') as f:
            return f.read()[:2000] # Read a sample of the most recent signals
    except Exception as e:
        return str(e)

@tool("Finish Task Tool")
def finish_task(dummy: str) -> str:
    """Marks the evaluation task (T3) as Done."""
    change_task_status("T3", "Done")
    return "Task T3 marked as Done."

def load_memory(role):
    try:
        with open(f"agent_memory/{role}.md", "r") as f:
            return f.read()
    except:
        return ""

evaluator = Agent(
    role="Evaluator Team",
    goal="Analyze past signals vs historical prices to determine if the >80% gate is salvageable.",
    backstory=f"{load_memory('evaluator_team')}",
    verbose=True,
    allow_delegation=False,
    tools=[read_signals, finish_task],
    llm=llm
)

task_evaluate = Task(
    description=(
        "1. Read the historical valid_signals using 'Read Signals Tool'.\n"
        "2. Time-match the signals against general market knowledge or structure rules to see why the >80% gate failed historically.\n"
        "3. Diagnose if the errors were due to the 5m data bug (which is now fixed), or if the parameters themselves (ATR, EMAs, S/R, GEX) need a completely new gate design.\n"
        "4. Output a summary of your findings.\n"
        "5. Use 'Finish Task Tool' to complete the job."
    ),
    expected_output="A full diagnostic report on the gate salvage operation, and the Kanban board updated.",
    agent=evaluator
)

if __name__ == "__main__":
    print("Moving Task T3 to 'In Progress'...")
    change_task_status("T3", "In Progress")
    time.sleep(2)
    print("Initiating DeepSeek Execution Loop: Phase 1.3 (Gate Salvage Analysis)")
    crew = Crew(agents=[evaluator], tasks=[task_evaluate], process=Process.sequential, verbose=True)
    crew.kickoff()
    print("Evaluation Complete.")
