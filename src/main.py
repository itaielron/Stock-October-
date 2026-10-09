import os
from crewai import Crew, Process, Agent, Task
from src.agents.stock_agent import create_stock_agent
from src.agents.flight_agent import create_flight_agent

def run_system():
    # Use native CrewAI format for local Ollama
    print("Initializing Local Llama 3.1 Model...")
    llm_string = "ollama/llama3.1"

    # Create the Manager Agent (The Supervisor)
    manager = Agent(
        role='Chief Intelligence Officer',
        goal='Coordinate sub-agents, verify their findings, and present a final, actionable alert to the user.',
        backstory='You are a highly analytical manager. You do not just pass on raw data; you ensure that the Stock Analyst and Travel Agent have done their jobs correctly, and you compile their findings into a clean, executive summary.',
        verbose=True,
        allow_delegation=True, # Critical for a manager
        llm=llm_string
    )

    # Create Sub-Agents
    stock_agent = create_stock_agent(llm_string)
    flight_agent = create_flight_agent(llm_string)

    # Define the overarching task for the manager to coordinate
    master_task = Task(
        description='''
        1. Ask the 'Senior Technical Stock Analyst' to evaluate the mock technical data for AAPL (Current: 170.50, EMA50: 175.20, Support: 170.0).
        2. Ask the 'Vacation Deal Finder' to evaluate if a flight to Japan for $500 is a good deal compared to a historical average of $1200.
        3. Compile their findings, verify if they make sense, and create a final Executive Alert for the user.
        ''',
        agent=manager,
        expected_output="A structured Executive Alert containing a Stock Market section and a Travel Deals section, with clear YES/NO recommendations."
    )

    # Create the Crew with a hierarchical process
    crew = Crew(
        agents=[manager, stock_agent, flight_agent],
        tasks=[master_task],
        process=Process.hierarchical,
        manager_llm=llm_string
    )

    print("\nStarting the Autonomous Agent System...\n")
    result = crew.kickoff()
    
    print("\n==============================================")
    print("FINAL EXECUTIVE ALERT TO USER")
    print("==============================================\n")
    print(result)

if __name__ == "__main__":
    run_system()
