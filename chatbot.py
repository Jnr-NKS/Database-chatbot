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

# Enhanced Custom CSS for better styling and alignment
st.markdown("""
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global styles */
    .main-header {
        font-family: 'Inter', sans-serif;
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1.5rem;
        padding: 1rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .sub-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.5rem;
        font-weight: 600;
        color: #2c3e50;
        margin: 1.5rem 0 1rem 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Sidebar styling */
    .sidebar-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.2rem;
        font-weight: 600;
        color: #2c3e50;
        margin-bottom: 1rem;
        padding: 0.5rem 0;
        border-bottom: 2px solid #e74c3c;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Card-like containers */
    .card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        border: 1px solid #e0e6ed;
        margin-bottom: 1.5rem;
    }
    
    /* Alert styling */
    .stAlert {
        margin: 1rem 0;
        border-radius: 8px;
    }
    
    /* SQL query display */
    .sql-query {
        background: #f8f9fa;
        padding: 1.2rem;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 0.9rem;
        line-height: 1.4;
        margin: 1rem 0;
    }
    
    /* Chat history styling */
    .chat-question {
        background: #e3f2fd;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #2196f3;
        margin-bottom: 1rem;
        font-weight: 500;
    }
    
    .chat-answer {
        background: #f1f8e9;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #4caf50;
        margin-bottom: 1rem;
    }
    
    /* Button styling */
    .stButton > button {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Input field styling */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        font-family: 'Inter', sans-serif;
        border-radius: 8px;
        border: 1px solid #ddd;
    }
    
    /* Connection status */
    .connection-status {
        padding: 0.8rem;
        border-radius: 8px;
        text-align: center;
        font-weight: 600;
        margin: 1rem 0;
    }
    
    .connected {
        background: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    
    .disconnected {
        background: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }
    
    /* Example questions */
    .example-question {
        background: #fff3cd;
        padding: 0.8rem;
        border-radius: 6px;
        border-left: 3px solid #ffc107;
        margin: 0.5rem 0;
        font-family: 'Inter', sans-serif;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    
    .example-question:hover {
        background: #fff8dc;
        transform: translateX(5px);
    }
    
    /* Footer */
    .footer {
        text-align: center;
        color: #6c757d;
        font-style: italic;
        margin-top: 3rem;
        padding: 2rem 0;
        border-top: 1px solid #e9ecef;
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .main-header {
            font-size: 2rem;
        }
        .card {
            padding: 1rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# Title with better formatting
st.markdown('<h1 class="main-header">🤖 Chat With Your Azure SQL Database</h1>', unsafe_allow_html=True)
st.markdown("""
<div style="text-align: center; color: #6c757d; font-size: 1.1rem; margin-bottom: 2rem;">
    Ask questions in natural language and get insights from your database
</div>
""", unsafe_allow_html=True)

class DatabaseManager:
    def __init__(self):
        self.db = None
        self.connection_string = None
        self.engine = None
    
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
            available_drivers = self.get_available_drivers()
            if not available_drivers:
                raise Exception("No SQL Server ODBC drivers found.")
            
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
                driver = available_drivers[0]
        
        # Enhanced connection string with better timeout and SSL settings
        connection_string = (
            f"mssql+pyodbc://{quote_plus(username)}:{quote_plus(password)}"
            f"@{server}:1433/{database}?"
            f"driver={quote_plus(driver)}&"
            f"Encrypt=yes&"
            f"TrustServerCertificate={'yes' if getattr(self, 'trust_cert', False) else 'no'}&"
            f"Connection+Timeout={getattr(self, 'timeout', 60)}&"
            f"Login_Timeout={getattr(self, 'timeout', 60)}&"
            f"ConnectRetryCount=3&"
            f"ConnectRetryInterval=10"
        )
        return connection_string, driver
    
    def test_connection(self, connection_string):
        """Test database connection with enhanced error handling"""
        try:
            # Create engine with additional pool settings
            self.engine = sqlalchemy.create_engine(
                connection_string,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={
                    "timeout": 60,
                    "autocommit": True
                }
            )
            
            with self.engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            return True, "Connection successful!"
        except Exception as e:
            error_msg = str(e)
            
            # Provide specific troubleshooting based on error type
            if "timeout" in error_msg.lower():
                troubleshooting = """
                
**Troubleshooting Timeout Issues:**
1. Check if your server name is correct (should end with .database.windows.net)
2. Verify firewall settings allow your IP address
3. Ensure you're using port 1433
4. Check if the database is online and accessible
                """
            elif "login" in error_msg.lower():
                troubleshooting = """
                
**Troubleshooting Login Issues:**
1. Verify username and password are correct
2. Check if the user has permission to access the database
3. Ensure the database name is correct
                """
            elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                troubleshooting = """
                
**Troubleshooting SSL/Certificate Issues:**
1. Try connecting with TrustServerCertificate=yes
2. Update your ODBC driver to the latest version
                """
            else:
                troubleshooting = ""
            
            return False, f"Connection failed: {error_msg}{troubleshooting}"
    
    def get_all_tables_and_schemas(self):
        """Get all tables and schemas from the database"""
        try:
            if not self.engine:
                return []
            
            # Query to get all tables with their schemas
            query = """
            SELECT 
                TABLE_SCHEMA as schema_name,
                TABLE_NAME as table_name,
                TABLE_SCHEMA + '.' + TABLE_NAME as full_table_name
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(query))
                tables = result.fetchall()
                
            return [dict(row._mapping) for row in tables]
            
        except Exception as e:
            logger.error(f"Error getting tables: {str(e)}")
            return []
    
    def get_table_columns(self, schema_name, table_name):
        """Get column information for a specific table"""
        try:
            if not self.engine:
                return []
            
            query = """
            SELECT 
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(query), (schema_name, table_name))
                columns = result.fetchall()
                
            return [dict(row._mapping) for row in columns]
            
        except Exception as e:
            logger.error(f"Error getting columns for {schema_name}.{table_name}: {str(e)}")
            return []
    
    def connect_to_database(self, server, database, username, password, trust_cert=False, timeout=60):
        """Connect to Azure SQL Database with enhanced configuration"""
        try:
            available_drivers = self.get_available_drivers()
            if not available_drivers:
                return False, "No SQL Server ODBC drivers found."
            
            # Store timeout for use in connection string
            self.timeout = timeout
            self.trust_cert = trust_cert
            
            self.connection_string, used_driver = self.create_connection_string(
                server, database, username, password
            )
            success, message = self.test_connection(self.connection_string)
            
            if success:
                # Get all tables first
                all_tables = self.get_all_tables_and_schemas()
                table_names = [table['full_table_name'] for table in all_tables]
                
                # Create SQLDatabase with specific tables and better configuration
                self.db = SQLDatabase.from_uri(
                    self.connection_string,
                    include_tables=table_names if table_names else None,
                    sample_rows_in_table_info=3,
                    custom_table_info=self.get_custom_table_info(all_tables)
                )
                
                return True, f"Successfully connected using driver: {used_driver}. Found {len(table_names)} tables."
            else:
                return False, message
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            return False, f"Connection error: {str(e)}"
    
    def get_custom_table_info(self, all_tables):
        """Create custom table info with proper schema information"""
        custom_info = {}
        
        for table in all_tables:
            schema_name = table['schema_name']
            table_name = table['table_name']
            full_name = table['full_table_name']
            
            # Get column information
            columns = self.get_table_columns(schema_name, table_name)
            
            # Create table description
            column_descriptions = []
            for col in columns:
                col_desc = f"[{col['COLUMN_NAME']}] {col['DATA_TYPE']}"
                if col['IS_NULLABLE'] == 'NO':
                    col_desc += " NOT NULL"
                column_descriptions.append(col_desc)
            
            table_description = f"""
Table: {full_name} (Schema: {schema_name})
Columns: {', '.join(column_descriptions)}
            """.strip()
            
            custom_info[full_name] = table_description
        
        return custom_info
    
    def get_table_info(self):
        """Get information about database tables"""
        if self.db:
            try:
                # Get basic table info from SQLDatabase
                basic_info = self.db.get_table_info()
                
                # Add our custom schema information
                all_tables = self.get_all_tables_and_schemas()
                
                enhanced_info = f"""
DATABASE SCHEMA INFORMATION:
============================

Available Tables:
{chr(10).join([f"• {table['full_table_name']}" for table in all_tables])}

DETAILED TABLE INFORMATION:
==========================
{basic_info}

IMPORTANT NOTES:
- Always use fully qualified table names (e.g., SalesLT.Customer, not just Customer)
- Schema names are case-sensitive
- Use square brackets around column names with spaces: [Column Name]
                """
                
                return enhanced_info
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
        """Create SQL agent with enhanced prompt"""
        try:
            # Create SQL toolkit
            toolkit = SQLDatabaseToolkit(db=db, llm=self.llm)
            
            # Enhanced custom prompt for better SQL generation
            enhanced_prompt = """
You are an expert SQL assistant for Azure SQL Database. Your job is to answer questions by writing and executing SQL queries.

CRITICAL RULES:
1. ALWAYS use fully qualified table names with schema (e.g., SalesLT.Customer, SalesLT.Product)
2. NEVER use just table names without schema (e.g., don't use "Customer", use "SalesLT.Customer")
3. When asked to "list all tables", query INFORMATION_SCHEMA.TABLES to show all available tables
4. Use square brackets around column names that might have spaces: [Column Name]
5. For Azure SQL, use TOP instead of LIMIT for row limiting
6. Be careful about case sensitivity in schema and table names

AVAILABLE SCHEMAS AND TABLES:
The database contains tables in the SalesLT schema including:
- SalesLT.Address
- SalesLT.Customer  
- SalesLT.CustomerAddress
- SalesLT.Product
- SalesLT.ProductCategory
- SalesLT.ProductDescription
- SalesLT.ProductModel
- SalesLT.ProductModelProductDescription
- SalesLT.SalesOrderDetail
- SalesLT.SalesOrderHeader
- SalesLT.SalesPerson
- SalesLT.ShoppingCart

QUERY EXAMPLES:
- To list all tables: "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
- To count customers: "SELECT COUNT(*) FROM SalesLT.Customer"
- To show table structure: "SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'SalesLT' AND TABLE_NAME = 'Customer'"

When you need to explore the database structure:
1. First check INFORMATION_SCHEMA.TABLES to see available tables
2. Use INFORMATION_SCHEMA.COLUMNS to understand table structure  
3. Then write your query using the correct schema.table format

IMPORTANT: If a query fails because of table name issues, try checking the exact table names first using INFORMATION_SCHEMA queries.

Use this format for responses:
Question: [the user's question]
Thought: [your reasoning about what query to write]
Action: [the tool to use]
Action Input: [the query or command]
Observation: [the result]
Thought: [your analysis of the result]
Final Answer: [your answer to the user]

{table_info}

Question: {input}
{agent_scratchpad}
            """
            
            # Create agent with enhanced prompt
            self.agent = create_sql_agent(
                llm=self.llm,
                toolkit=toolkit,
                verbose=True,
                agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                handle_parsing_errors=True,
                max_iterations=10,
                early_stopping_method="force"
            )
            
            # Override the agent's prompt template
            self.agent.agent.llm_chain.prompt.template = enhanced_prompt
            
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

# Enhanced Sidebar with better formatting
with st.sidebar:
    st.markdown('<div class="sidebar-header">🔧 Configuration</div>', unsafe_allow_html=True)
    
    # Gemini API Key section
    with st.container():
        st.markdown("**🔑 API Configuration**")
        gemini_api_key = st.text_input(
            "Gemini API Key",
            type="password",
            help="Enter your Google Gemini API key",
            placeholder="Enter your API key..."
        )
    
    st.markdown("---")
    
    # Database connection section
    st.markdown('<div class="sidebar-header">🔗 Database Connection</div>', unsafe_allow_html=True)
    
    with st.container():
        server = st.text_input(
            "🖥️ Server Name",
            placeholder="your-server.database.windows.net",
            help="Azure SQL Server name (must end with .database.windows.net)"
        )
        
        database = st.text_input(
            "🗄️ Database Name",
            placeholder="your-database-name",
            help="Name of your Azure SQL database"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input(
                "👤 Username",
                placeholder="username",
                help="Database username"
            )
        with col2:
            password = st.text_input(
                "🔒 Password",
                type="password",
                help="Database password"
            )
    
    # Connection troubleshooting tips
    with st.expander("🔧 Connection Troubleshooting", expanded=False):
        st.markdown("""
        **Common Issues & Solutions:**
        
        **🔥 Firewall Issues:**
        - Add your IP address to Azure SQL firewall rules
        - Enable "Allow Azure services" in firewall settings
        
        **🌐 Server Name Format:**
        - Must be: `your-server.database.windows.net`
        - Don't include `tcp:` prefix or port number
        
        **🔐 Authentication:**
        - Use SQL Server authentication (not Windows/AAD)
        - Ensure user has `db_datareader` permission
        
        **📊 Database Access:**
        - Verify database name is correct
        - Ensure database is online and accessible
        
        **🔗 Network:**
        - Try from different network if corporate firewall blocks
        - Check if port 1433 is open
        """)
    
    # Advanced connection options
    with st.expander("⚙️ Advanced Options", expanded=False):
        trust_cert = st.checkbox(
            "Trust Server Certificate", 
            value=False,
            help="Enable if you have certificate issues"
        )
        
        connection_timeout = st.slider(
            "Connection Timeout (seconds)", 
            min_value=15, 
            max_value=120, 
            value=60,
            help="Increase if getting timeout errors"
        )
    
    # Connect button with better styling
    st.markdown("<br>", unsafe_allow_html=True)
    connect_button = st.button(
        "🔗 Connect to Database",
        type="primary",
        use_container_width=True
    )
    
    if connect_button:
        if not all([gemini_api_key, server, database, username, password]):
            st.error("⚠️ Please fill in all required fields!")
        else:
            # First check available drivers
            available_drivers = st.session_state.db_manager.get_available_drivers()
            if available_drivers:
                with st.expander("Available ODBC Drivers", expanded=False):
                    for driver in available_drivers:
                        st.write(f"✓ {driver}")
            else:
                st.error("❌ No SQL Server ODBC drivers found!")
                with st.expander("Installation Instructions", expanded=True):
                    st.markdown("""
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
            
            with st.spinner("🔄 Connecting to database..."):
                # Get advanced options
                trust_cert_option = locals().get('trust_cert', False)
                timeout_option = locals().get('connection_timeout', 60)
                
                success, message = st.session_state.db_manager.connect_to_database(
                    server, database, username, password, trust_cert_option, timeout_option
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
                        st.info(f"🔧 {message}")  # Show which driver was used
                    else:
                        st.error(f"❌ {agent_message}")
                else:
                    st.error(f"❌ {message}")
    
    # Connection status with better styling
    st.markdown("---")
    if st.session_state.connected:
        st.markdown("""
        <div class="connection-status connected">
            ✅ Database Connected
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="connection-status disconnected">
            ❌ Database Disconnected
        </div>
        """, unsafe_allow_html=True)
    
    # Help section
    st.markdown("---")
    st.markdown('<div class="sidebar-header">ℹ️ How to Use</div>', unsafe_allow_html=True)
    
    with st.expander("📋 Step-by-step Guide", expanded=False):
        st.markdown("""
        1. **🔑 Enter your Gemini API key**
        2. **🔗 Fill in database connection details**
        3. **🚀 Click 'Connect to Database'**
        4. **💬 Start asking questions about your data!**
        """)
    
    with st.expander("💡 Example Questions", expanded=False):
        examples = [
            "List all tables in the database",
            "Show me all customers from SalesLT.Customer",
            "What are the top 5 products by sales?",
            "How many customers are there?",
            "Show table structure for SalesLT.Product"
        ]
        for example in examples:
            st.markdown(f"• {example}")

# Enhanced Main content area
if st.session_state.connected:
    # Chat interface with better formatting
    st.markdown('<div class="sub-header">💬 Chat with Your Database</div>', unsafe_allow_html=True)
    
    # Query input with enhanced styling
    with st.container():
        col1, col2 = st.columns([4, 1])
        
        with col1:
            user_question = st.text_input(
                "",
                placeholder="💭 Ask a question about your data... (e.g., List all tables in the database)",
                key="user_input",
                label_visibility="collapsed"
            )
        
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            query_button = st.button("🚀 Query", type="primary", use_container_width=True)
    
    # Action buttons
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🗑️ Clear History", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
    
    with col2:
        if st.button("📊 Table Info", use_container_width=True):
            with st.expander("Database Table Information", expanded=True):
                table_info = st.session_state.db_manager.get_table_info()
                st.text_area("", table_info, height=400, label_visibility="collapsed")

    # Process query
    if query_button and user_question:
        with st.spinner("🔍 Querying database..."):
            # Create callback handler for streaming
            callback_container = st.container()
            callback_handler = StreamlitCallbackHandler(callback_container)

            # Execute query
            response, sql_query, results = st.session_state.sql_agent.query_database(
                user_question, callback_handler
            )

            # Add to chat history
            st.session_state.chat_history.append({
                'question': user_question,
                'response': response,
                'sql_query': sql_query,
                'results': results,
                'timestamp': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            })

    # Enhanced Chat history display
    if st.session_state.chat_history:
        st.markdown("---")
        st.markdown('<div class="sub-header">💭 Chat History</div>', unsafe_allow_html=True)

        for i, chat in enumerate(reversed(st.session_state.chat_history)):
            with st.expander(
                f"🔍 {chat['question'][:60]}{'...' if len(chat['question']) > 60 else ''}", 
                expanded=(i == 0)
            ):
                # Timestamp
                st.caption(f"🕒 {chat.get('timestamp', 'Unknown time')}")
                
                # Question
                st.markdown(f"""
                <div class="chat-question">
                    <strong>❓ Question:</strong><br>
                    {chat['question']}
                </div>
                """, unsafe_allow_html=True)
                
                # Answer
                st.markdown(f"""
                <div class="chat-answer">
                    <strong>💡 Answer:</strong><br>
                    {chat['response']}
                </div>
                """, unsafe_allow_html=True)

                if chat.get('sql_query'):
                    st.markdown("**🔧 SQL Query:**")
                    st.code(chat['sql_query'], language='sql')

                if chat.get('results') is not None:
                    st.markdown("**📊 Results:**")
                    st.dataframe(chat['results'], use_container_width=True)

else:
    # Welcome screen with better formatting
    st.markdown("""
    <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                border-radius: 10px; color: white; margin: 2rem 0;">
        <h2>👋 Welcome to SQL AI Agent</h2>
        <p>Configure your API key and database connection in the sidebar to get started</p>
    </div>
    """, unsafe_allow_html=True)

    # Enhanced example questions
    st.markdown('<div class="sub-header">📝 Example Questions You Can Ask</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    examples_left = [
        "List all tables in the database",
        "Show me the structure of SalesLT.Customer table",
        "How many customers are in the database?",
        "Show me the top 5 customers by customer ID"
    ]
    
    examples_right = [
        "What products are in SalesLT.Product?",
        "Show me all sales orders from SalesLT.SalesOrderHeader",
        "Calculate the total number of products",
        "List all schemas and their tables"
    ]
    
    with col1:
        for example in examples_left:
            st.markdown(f"""
            <div class="example-question">
                💡 {example}
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        for example in examples_right:
            st.markdown(f"""
            <div class="example-question">
                💡 {example}
            </div>
            """, unsafe_allow_html=True)

# Enhanced Footer
st.markdown("---")
st.markdown("""
<div class="footer">
    <p>Built with ❤️ using <strong>Streamlit</strong>, <strong>LangChain</strong>, and <strong>Google Gemini</strong></p>
    <p>🚀 Transform your data queries with the power of AI</p>
</div>
""", unsafe_allow_html=True)
