import streamlit as st
import pandas as pd
import pyodbc
from langchain_community.utilities.sql_database import SQLDatabase
from langchain.agents import create_sql_agent
from langchain.agents.agent_toolkits import SQLDatabaseToolkit
from langchain.llms import GooglePalm
from langchain.agents.agent_types import AgentType
from langchain.callbacks import StreamlitCallbackHandler
from langchain.prompts import PromptTemplate
import os
import google.generativeai as genai
from langchain_google_genai import GoogleGenerativeAI
import sqlalchemy
from urllib.parse import quote_plus
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="SQL AI Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    .sql-query {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.markdown('<h1 class="main-header">🤖 Chat With Your Azure SQL Database</h1>', unsafe_allow_html=True)
st.markdown("---")

class DatabaseManager:
    def __init__(self):
        self.db = None
        self.connection_string = None
    
    def get_available_drivers(self):
        """Get list of available ODBC drivers"""
        try:
            drivers = pyodbc.drivers()
            sql_drivers = [driver for driver in drivers if 'SQL Server' in driver]
            return sql_drivers
        except Exception as e:
            logger.error(f"Error getting drivers: {str(e)}")
            return []
    
    def create_connection_string(self, server, database, username, password, driver=None):
        """Create Azure SQL Database connection string with driver detection"""
        if not driver:
            # Try to find the best available driver
            available_drivers = self.get_available_drivers()
            
            if not available_drivers:
                raise Exception("No SQL Server ODBC drivers found. Please install Microsoft ODBC Driver for SQL Server.")
            
            # Prefer newer drivers
            preferred_drivers = [
                "ODBC Driver 18 for SQL Server",
                "ODBC Driver 17 for SQL Server",
                "ODBC Driver 13 for SQL Server",
                "SQL Server Native Client 11.0",
                "SQL Server"
            ]
            
            driver = None
            for preferred in preferred_drivers:
                if preferred in available_drivers:
                    driver = preferred
                    break
            
            if not driver:
                driver = available_drivers[0]  # Use the first available driver
        
        # Create connection string with proper parameters for Azure SQL
        connection_string = (
            f"mssql+pyodbc://{quote_plus(username)}:{quote_plus(password)}"
            f"@{server}/{database}?"
            f"driver={quote_plus(driver)}&"
            f"TrustServerCertificate=yes&"
            f"Connection+Timeout=30&"
            f"Encrypt=yes"
        )
        
        return connection_string, driver
    
    def test_connection(self, connection_string):
        """Test database connection"""
        try:
            engine = sqlalchemy.create_engine(connection_string)
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            return True, "Connection successful!"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
def connect_to_database(self, server, database, username, password):
    """Connect to Azure SQL Database with driver auto-detection"""
    try:
        # First, check available drivers
        available_drivers = self.get_available_drivers()
        if not available_drivers:
            return False, "No SQL Server ODBC drivers found. Please install Microsoft ODBC Driver for SQL Server."
        
        self.connection_string, used_driver = self.create_connection_string(server, database, username, password)
        success, message = self.test_connection(self.connection_string)
        
        if success:
            # Load ALL schemas instead of default
            self.db = SQLDatabase.from_uri(
                self.connection_string,
                include_tables=None,         # None = include all tables
                sample_rows_in_table_info=3, # optional: include sample rows for better context
                schema="%"                   # <-- this ensures ALL schemas are included
            )
            return True, f"Successfully connected using driver: {used_driver}"
        else:
            return False, message
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return False, f"Connection error: {str(e)}"

    
    def get_table_info(self):
        """Get information about database tables"""
        if self.db:
            try:
                return self.db.get_table_info()
            except Exception as e:
                return f"Error getting table info: {str(e)}"
        return "No database connection"

class SQLAgent:
    def __init__(self, gemini_api_key):
        self.gemini_api_key = gemini_api_key
        self.llm = None
        self.agent = None
        self.setup_llm()
    
    def setup_llm(self):
        """Setup Gemini LLM"""
        try:
            genai.configure(api_key=self.gemini_api_key)
            self.llm = GoogleGenerativeAI(
                model="gemini-1.5-flash",
                google_api_key=self.gemini_api_key,
                temperature=0,
                convert_system_message_to_human=True
            )
        except Exception as e:
            st.error(f"Error setting up Gemini LLM: {str(e)}")
    
    def create_agent(self, db):
        """Create SQL agent"""
        try:
            # Create SQL toolkit
            toolkit = SQLDatabaseToolkit(db=db, llm=self.llm)
            
            # Custom prompt for better SQL generation
            custom_prompt = """
            You are an expert SQL assistant. Given an input question, create a syntactically correct SQL query to run.
            
            Unless the user specifies in the question a specific number of examples to obtain, query for at most 10 results using LIMIT or TOP clause.
            Never query for all columns from a table. You must query only the columns that are needed to answer the question.
            Wrap each column name in square brackets like [column_name] to handle spaces and special characters.
            Pay attention to use only the column names you can see in the tables below. Be careful to not query for columns that do not exist.
            Also, pay attention to which column is in which table.
            
            Use the following format:
            
            Question: "Question here"
            SQLQuery: "SQL Query to run"
            SQLResult: "Result of the SQLQuery"
            Answer: "Final answer here"
            
            Only use the following tables:
            {table_info}
            
            Question: {input}
            {agent_scratchpad}
            """
            
            # Create agent
            self.agent = create_sql_agent(
                llm=self.llm,
                toolkit=toolkit,
                verbose=True,
                agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                handle_parsing_errors=True,
                max_iterations=3,
                early_stopping_method="generate"
            )
            
            return True, "SQL Agent created successfully!"
        except Exception as e:
            logger.error(f"Error creating SQL agent: {str(e)}")
            return False, f"Error creating agent: {str(e)}"
    
    def query_database(self, question, callback_handler=None):
        """Query database using natural language"""
        try:
            if not self.agent:
                return "Agent not initialized", None, None
            
            # Execute query with callback handler for streaming
            if callback_handler:
                response = self.agent.run(question, callbacks=[callback_handler])
            else:
                response = self.agent.run(question)
            
            return response, None, None
        except Exception as e:
            logger.error(f"Query execution error: {str(e)}")
            return f"Error executing query: {str(e)}", None, None

# Initialize session state
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()
if 'sql_agent' not in st.session_state:
    st.session_state.sql_agent = None
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# Sidebar for configuration
with st.sidebar:
    st.header("🔧 Configuration")
    
    # Gemini API Key
    gemini_api_key = st.text_input(
        "Gemini API Key",
        type="password",
        help="Enter your Google Gemini API key"
    )
    
    st.markdown("---")
    st.header("🔗 Database Connection")
    
    # Database connection parameters
    server = st.text_input(
        "Server Name",
        placeholder="your-server.database.windows.net",
        help="Azure SQL Server name"
    )
    
    database = st.text_input(
        "Database Name",
        placeholder="your-database-name",
        help="Name of your Azure SQL database"
    )
    
    username = st.text_input(
        "Username",
        placeholder="your-username",
        help="Database username"
    )
    
    password = st.text_input(
        "Password",
        type="password",
        help="Database password"
    )
    
    # Connect button
    if st.button("🔗 Connect to Database"):
        if not all([gemini_api_key, server, database, username, password]):
            st.error("Please fill in all required fields!")
        else:
            # First check available drivers
            available_drivers = st.session_state.db_manager.get_available_drivers()
            if available_drivers:
                st.info(f"Available ODBC drivers: {', '.join(available_drivers)}")
            else:
                st.error("❌ No SQL Server ODBC drivers found! Please install one first.")
                st.markdown("""
                **To install ODBC drivers:**
                
                **Windows:**
                - Download from [Microsoft](https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
                
                **macOS:**
                ```bash
                brew install microsoft/mssql-release/msodbcsql18
                ```
                
                **Linux:**
                ```bash
                curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
                curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
                sudo apt-get update
                sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
                ```
                """)
                st.stop()
            
            with st.spinner("Connecting to database..."):
                success, message = st.session_state.db_manager.connect_to_database(
                    server, database, username, password
                )
                
                if success:
                    # Initialize SQL agent
                    st.session_state.sql_agent = SQLAgent(gemini_api_key)
                    agent_success, agent_message = st.session_state.sql_agent.create_agent(
                        st.session_state.db_manager.db
                    )
                    
                    if agent_success:
                        st.session_state.connected = True
                        st.success("✅ Connected successfully!")
                        st.info(message)  # Show which driver was used
                    else:
                        st.error(f"❌ {agent_message}")
                else:
                    st.error(f"❌ {message}")
    
    # Show available drivers button
    if st.button("🔍 Check Available Drivers"):
        drivers = st.session_state.db_manager.get_available_drivers()
        if drivers:
            st.success("Available SQL Server ODBC drivers:")
            for driver in drivers:
                st.write(f"- {driver}")
        else:
            st.error("No SQL Server ODBC drivers found!")
            st.info("You need to install Microsoft ODBC Driver for SQL Server.")
    
    # Connection status
    if st.session_state.connected:
        st.success("✅ Database Connected")
        
        # Show table information
        if st.button("📊 Show Table Info"):
            table_info = st.session_state.db_manager.get_table_info()
            st.text_area("Table Information", table_info, height=200)
    
    st.markdown("---")
    st.header("ℹ️ How to Use")
    st.markdown("""
    1. **Enter your Gemini API key**
    2. **Fill in database connection details**
    3. **Click 'Connect to Database'**
    4. **Start asking questions about your data!**
    
    **Example questions:**
    - "Show me all customers"
    - "What are the top 5 products by sales?"
    - "How many orders were placed last month?"
    """)

# Main content area
col1, col2 = st.columns([2, 1])

with col1:
    if st.session_state.connected:
        st.header("💬 Chat with Your Database")
        
        # Chat interface
        user_question = st.text_input(
            "Ask a question about your data:",
            placeholder="e.g., Show me the top 10 customers by total sales",
            key="user_input"
        )
        
        col_query, col_clear = st.columns([3, 1])
        
        with col_query:
            query_button = st.button("🚀 Query Database", type="primary")
        
        with col_clear:
            if st.button("🗑️ Clear"):
                st.session_state.chat_history = []
                st.rerun()
        
        # Process query
        if query_button and user_question:
            with st.spinner("Querying database..."):
                # Create callback handler for streaming
                callback_handler = StreamlitCallbackHandler(st.container())
                
                # Execute query
                response, sql_query, results = st.session_state.sql_agent.query_database(
                    user_question, callback_handler
                )
                
                # Add to chat history
                st.session_state.chat_history.append({
                    'question': user_question,
                    'response': response,
                    'sql_query': sql_query,
                    'results': results
                })
        
        # Display chat history
        if st.session_state.chat_history:
            st.markdown("---")
            st.header("💭 Chat History")
            
            for i, chat in enumerate(reversed(st.session_state.chat_history)):
                with st.expander(f"Q: {chat['question']}", expanded=(i == 0)):
                    st.markdown("**Answer:**")
                    st.write(chat['response'])
                    
                    if chat.get('sql_query'):
                        st.markdown("**SQL Query:**")
                        st.code(chat['sql_query'], language='sql')
                    
                    if chat.get('results') is not None:
                        st.markdown("**Results:**")
                        st.dataframe(chat['results'])
    
    else:
        st.info("👈 Please configure your API key and database connection in the sidebar to get started.")
        
        # Show example questions
        st.header("📝 Example Questions You Can Ask")
        examples = [
            "Show me all tables in the database",
            "What are the column names in the customers table?",
            "How many records are in each table?",
            "Show me the top 5 customers by total purchase amount",
            "What products were sold last month?",
            "Calculate the average order value",
            "Show me sales by region",
            "List all orders from the last 30 days"
        ]
        
        for example in examples:
            st.code(example, language=None)

with col2:
    if st.session_state.connected:
        st.header("📊 Database Overview")
        
        # Quick stats (you can customize this based on your database)
        try:
            if st.button("📈 Refresh Stats"):
                with st.spinner("Loading database statistics..."):
                    # You can customize these queries based on your database structure
                    stats_query = "SELECT name FROM sys.tables WHERE type = 'U'"
                    response, _, _ = st.session_state.sql_agent.query_database(
                        "How many tables are in this database?"
                    )
                    st.info(response)
        except Exception as e:
            st.warning(f"Could not load stats: {str(e)}")
    
    else:
        st.header("🚀 Getting Started")
        st.markdown("""
        This application allows you to chat with your Azure SQL database using natural language!
        
        **Features:**
        - 🤖 AI-powered SQL generation
        - 💬 Natural language queries
        - 📊 Visual data display
        - 🔒 Secure connections
        - 📝 Query history
        
        **Requirements:**
        - Google Gemini API key
        - Azure SQL Database access
        - Network connectivity to Azure
        """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666;">
        Built with ❤️ using Streamlit, LangChain, and Google Gemini
    </div>
    """,
    unsafe_allow_html=True
)


