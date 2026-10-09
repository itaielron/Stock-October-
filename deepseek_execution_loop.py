import os
import sys
import json
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

load_dotenv()
deepseek_key = os.getenv("DEEPSEEK_API_KEY")

os.environ["OPENAI_API_KEY"] = deepseek_key
os.environ["OPENAI_API_BASE"] = "https://api.deepseek.com"

llm = LLM(
    model="deepseek/deepseek-chat",
    api_key=deepseek_key,
    base_url="https://api.deepseek.com"
)

# --- TOOLS ---
@tool("Read File Tool")
def read_file(filepath: str) -> str:
    """Reads a file from the disk."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return str(e)

@tool("Write Code Tool")
def write_code(filepath_and_content: str) -> str:
    """Writes corrected code back to disk. Format input as 'filepath|||content'"""
    try:
        filepath, content = filepath_and_content.split('|||', 1)
        with open(filepath.strip(), 'w') as f:
            f.write(content.strip())
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Failed to write: {str(e)}"

@tool("Update Kanban Tool")
def update_kanban(dummy: str) -> str:
    """Moves Task T1 to Done in kanban.json"""
    try:
        with open('kanban.json', 'r') as f:
            board = json.load(f)
        
        t1_task = None
        for t in board['To Do']:
            if t['id'] == 'T1':
                t1_task = t
                break
        
        if t1_task:
            board['To Do'].remove(t1_task)
            board['Done'].append(t1_task)
            with open('kanban.json', 'w') as f:
                json.dump(board, f, indent=4)
        return "Kanban updated successfully."
    except Exception as e:
        return str(e)

# --- LOAD MEMORY ---
def load_memory(role):
    try:
        with open(f"agent_memory/{role}.md", "r") as f:
            return f.read()
    except:
        return ""

# --- AGENTS ---
math_engine = Agent(
    role="Math Engine / Coder",
    goal="Fix the 5 critical defects flagged by QA in the 5-minute data feed fix.",
    backstory=f"You are the strictly logical Math Engine. Your previous fix was rejected by QA. Fix it.\n{load_memory('evaluator_team')}",
    verbose=True,
    allow_delegation=False,
    tools=[read_file, write_code],
    llm=llm
)

qa_manager = Agent(
    role="QA Manager",
    goal="Verify the Math Engine's new fix against the 5 defects.",
    backstory=f"You are the gatekeeper. Your core directive:\n{load_memory('qa_evaluator')}",
    verbose=True,
    allow_delegation=False,
    tools=[read_file, update_kanban],
    llm=llm
)

# --- TASKS ---
task_fix_data = Task(
    description=(
        "1. Read 'generate_charts_alpaca.py'.\n"
        "2. Fix these 5 defects flagged by QA on the previous attempt:\n"
        "   - The `ffill` on reindexed bars across the 16:00 to 09:30 gap re-inserts synthetic flat bars, corrupting ATR/EMA windows. Replace blind ffill with session-aware reindexing.\n"
        "   - The API fallback logic is inverted (checking 401 instead of 403 for feed entitlement).\n"
        "   - Timezone filter lacks re-localization safety (DST straddle risk).\n"
        "   - The Regex `([\d]+\.[\d]+)` drops whole-dollar entries. Fix it.\n"
        "   - Unverified assumption about naive timestamps in hub.db.\n"
        "3. Rewrite the function to pull clean, verified 5m data using Alpaca.\n"
        "4. Use 'Write Code Tool' to save the patched file (format: generate_charts_alpaca.py|||def get_data...)."
    ),
    expected_output="The patched Python file saved to disk with the 5 defects resolved.",
    agent=math_engine
)

task_verify = Task(
    description=(
        "1. Review the changes made by the Math Engine.\n"
        "2. Ensure all 5 defects are explicitly handled.\n"
        "3. If mathematically sound, use 'Update Kanban Tool' to move T1 to Done.\n"
        "4. Output a final summary of the fix."
    ),
    expected_output="A summary of the fix and the Kanban board updated.",
    agent=qa_manager
)

execution_crew = Crew(
    agents=[math_engine, qa_manager],
    tasks=[task_fix_data, task_verify],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    print("Initiating DeepSeek Execution Loop: Phase 1.2 (Fixing QA Defects)")
    result = execution_crew.kickoff()
    print("Loop iteration complete.")
