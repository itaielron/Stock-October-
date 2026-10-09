import os
import sys
import json
import glob
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

# Load API keys
load_dotenv()
deepseek_key = os.getenv("DEEPSEEK_API_KEY")

if not deepseek_key:
    print("CRITICAL ERROR: DEEPSEEK_API_KEY not found in .env")
    sys.exit(1)

# Configure LiteLLM for DeepSeek
os.environ["OPENAI_API_KEY"] = deepseek_key
os.environ["OPENAI_API_BASE"] = "https://api.deepseek.com"

# The LLM instance
llm = LLM(
    model="deepseek/deepseek-chat",
    api_key=deepseek_key,
    base_url="https://api.deepseek.com"
)

# ----------------- TOOLS -----------------

@tool("Read Transcripts Tool")
def read_transcripts(dummy_input: str) -> str:
    """Reads the three provided transcripts from previous chats."""
    files = [
        "/Users/itaielron/Documents/antigravity/blissful-carson/conversation_export.md",
        "/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7/conversation_export.md",
        "/Users/itaielron/Documents/antigravity/blissful-carson/chat_export.md"
    ]
    content = ""
    for f in files:
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as file:
                content += f"\n--- File: {f} ---\n"
                # Read first 10000 chars of each to avoid context bloat on first pass
                content += file.read()[:10000] 
        else:
            content += f"\n--- File: {f} NOT FOUND ---\n"
    return content

@tool("Read Codebase Tool")
def read_codebase(dummy_input: str) -> str:
    """Reads dashboard.py and scans the valid_signals JSON files to understand the current build state."""
    content = ""
    if os.path.exists("dashboard.py"):
        with open("dashboard.py", 'r') as file:
            content += "--- dashboard.py ---\n" + file.read()
    
    signals = glob.glob("valid_signals*.json")
    content += f"\nFound {len(signals)} signal JSON files. Example state from first one:\n"
    if signals:
        with open(signals[-1], 'r') as file:
            content += file.read()[:500] # Snippet of the latest
    return content

@tool("Log to Backlog Tool")
def log_to_backlog(content: str) -> str:
    """Logs identified tasks, discrepancies, and action items into a local backlog folder so the top-tier manager can sync it."""
    os.makedirs("github_backlog", exist_ok=True)
    import time
    filename = f"github_backlog/task_log_{int(time.time())}.md"
    with open(filename, 'w') as file:
        file.write(content)
    return f"Logged successfully to {filename}"

# ----------------- AGENTS -----------------

cataloger = Agent(
    role="Critique & Catalog Analyst",
    goal="Ingest transcripts and codebase. Map out what was requested vs what was built. Identify where confusion started.",
    backstory="You are a meticulous technical analyst. Your job is to read historical chat logs and compare them to the current code.",
    verbose=True,
    allow_delegation=False,
    tools=[read_transcripts, read_codebase, log_to_backlog],
    llm=llm
)

dispatcher = Agent(
    role="Task Dispatcher",
    goal="Take the findings from the Cataloger and break them down into actionable backlog items for the Evaluator and Math Engine agents.",
    backstory="You are a strict project manager. You turn analytical findings into step-by-step tasks.",
    verbose=True,
    allow_delegation=False,
    tools=[log_to_backlog],
    llm=llm
)

qa_manager = Agent(
    role="QA & Math Engine Manager",
    goal="Review the dispatched tasks, ensure they adhere to strict mathematical logic with zero hallucinations, and log the final verified action plan.",
    backstory="You enforce the rules. No fake signals, no guesswork. Everything must be mathematically verifiable via Alpaca.",
    verbose=True,
    allow_delegation=False,
    tools=[log_to_backlog],
    llm=llm
)

# ----------------- TASKS -----------------

task_catalog = Task(
    description=(
        "1. Use the 'Read Transcripts Tool' to ingest the 3 historical chat files.\n"
        "2. Use the 'Read Codebase Tool' to see what is currently built.\n"
        "3. Cross-examine the two. What features were requested? What was actually built? Where did the errors pile up?\n"
        "4. Write your findings using the 'Log to Backlog Tool'."
    ),
    expected_output="A detailed markdown report logging the discrepancies between transcripts and codebase, logged to the backlog.",
    agent=cataloger
)

task_dispatch = Task(
    description=(
        "1. Read the output from the Cataloger.\n"
        "2. Break down the missing features or required fixes into 3-5 distinct, actionable tasks.\n"
        "3. Assign which tasks need the 'Evaluator Team' and which need the 'Math Engine'.\n"
        "4. Log these tasks using the 'Log to Backlog Tool'."
    ),
    expected_output="A structured list of actionable tasks assigned to specific sub-teams, logged to the backlog.",
    agent=dispatcher
)

task_qa = Task(
    description=(
        "1. Review the proposed tasks from the Dispatcher.\n"
        "2. Veto any tasks that seem prone to hallucination or lack strict mathematical constraints.\n"
        "3. Produce the final, verified 'Phase 1 Action Plan' and log it using the 'Log to Backlog Tool'.\n"
        "4. Flag any critical items that require the human manager's attention in the final log."
    ),
    expected_output="The final verified action plan, heavily enforcing mathematical rigor, logged to the backlog.",
    agent=qa_manager
)

# ----------------- CREW -----------------

blissful_crew = Crew(
    agents=[cataloger, dispatcher, qa_manager],
    tasks=[task_catalog, task_dispatch, task_qa],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    print("Initializing DeepSeek CrewAI Pipeline...")
    result = blissful_crew.kickoff()
    print("Pipeline Execution Complete. Final Output:")
    print(result)
