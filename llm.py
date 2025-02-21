import os
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_community.chat_models import ChatOpenAI
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
from langchain.schema import AIMessage  # Import the AIMessage class

# Load environment variables (ensure OPENAI_API_KEY is set in your .env file)
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

# Connect to the SQLite database (ensure gmail_info.db is in your current directory)
db = SQLDatabase.from_uri("sqlite:///gmail_info.db")

# Initialize the chat model with the new ChatOpenAI class
llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0, openai_api_key=openai_api_key)

# Create a SQLDatabaseToolkit instance which provides tools for SQL operations
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# Setup conversation memory so the agent can maintain context.
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Initialize the conversational agent with the tools from the SQL toolkit.
agent = initialize_agent(
    tools=toolkit.get_tools(),
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    memory=memory,
    verbose=True
)

# Start a conversational loop.
print("Type 'exit' to quit.")
while True:
    user_input = input("You: ")
    if user_input.lower() == "exit":
        break
    response = agent.invoke(user_input)  # Using .invoke() as recommended instead of .run()

    # Filter the conversation memory to get only AIMessage instances.
    ai_messages = [msg for msg in memory.chat_memory.messages if isinstance(msg, AIMessage)]
    
    # Print the latest AIMessage content if available.
    if ai_messages:
        print("Agent:", ai_messages[-1].content)
