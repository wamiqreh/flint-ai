"""Example: Using Flint with CrewAI.

Prerequisites::

    pip install 'flint-ai[crewai]'

Make sure the orchestrator server is running on http://localhost:5156.
"""

from crewai import Agent, Crew, Process, Task

from flint_ai.crewai_adapter import OrchestratorTool

# ── Create orchestrator-backed tools ────────────────────────────────────────

code_tool = OrchestratorTool(
    base_url="http://localhost:5156",
    agent_type="openai",
    name="code_generator",
    description="Generates Python code for the given specification.",
)

review_tool = OrchestratorTool(
    base_url="http://localhost:5156",
    agent_type="claude",
    name="code_reviewer",
    description="Reviews Python code and suggests improvements.",
)

# ── Define agents ───────────────────────────────────────────────────────────

developer = Agent(
    role="Python Developer",
    goal="Write clean, well-tested Python code.",
    backstory="You are a senior Python developer with 10 years of experience.",
    tools=[code_tool],
    verbose=True,
)

reviewer = Agent(
    role="Code Reviewer",
    goal="Ensure code quality and adherence to best practices.",
    backstory="You are a meticulous code reviewer who values clarity.",
    tools=[review_tool],
    verbose=True,
)

# ── Define tasks ────────────────────────────────────────────────────────────

write_task = Task(
    description="Write a Python function that calculates the Fibonacci sequence up to n terms.",
    expected_output="A Python function with docstring and type hints.",
    agent=developer,
)

review_task = Task(
    description="Review the code produced in the previous step and suggest improvements.",
    expected_output="A list of review comments and an improved version of the code.",
    agent=reviewer,
)

# ── Assemble and run crew ──────────────────────────────────────────────────

crew = Crew(
    agents=[developer, reviewer],
    tasks=[write_task, review_task],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    result = crew.kickoff()
    print("\n── Final Result ──")
    print(result)
