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
        self.all_tables = []
    
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
        """Get all tables and schemas from the database with enhanced queries"""
        try:
            if not self.engine:
                return []
            
            # Comprehensive query to get all tables with their schemas, including views
            query = """
            SELECT DISTINCT
                TABLE_SCHEMA as schema_name,
                TABLE_NAME as table_name,
                TABLE_SCHEMA + '.' + TABLE_NAME as full_table_name,
                TABLE_TYPE as table_type,
                (SELECT COUNT(*) 
                 FROM INFORMATION_SCHEMA.COLUMNS c 
                 WHERE c.TABLE_SCHEMA = t.TABLE_SCHEMA 
                 AND c.TABLE_NAME = t.TABLE_NAME) as column_count
            FROM INFORMATION_SCHEMA.TABLES t
            WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            
            UNION ALL
            
            -- Get system tables that might not appear in INFORMATION_SCHEMA
            SELECT DISTINCT
                SCHEMA_NAME(schema_id) as schema_name,
                name as table_name,
                SCHEMA_NAME(schema_id) + '.' + name as full_table_name,
                CASE type 
                    WHEN 'U' THEN 'BASE TABLE'
                    WHEN 'V' THEN 'VIEW'
                    WHEN 'S' THEN 'SYSTEM TABLE'
                    ELSE 'OTHER'
                END as table_type,
                0 as column_count
            FROM sys.tables
            WHERE is_ms_shipped = 0  -- Exclude system tables
            
            ORDER BY schema_name, table_name
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(query))
                tables = result.fetchall()
            
            # Convert to list of dictionaries and remove duplicates
            table_list = []
            seen_tables = set()
            
            for row in tables:
                row_dict = dict(row._mapping)
                table_key = (row_dict['schema_name'], row_dict['table_name'])
                if table_key not in seen_tables:
                    seen_tables.add(table_key)
                    table_list.append(row_dict)
            
            self.all_tables = table_list
            return table_list
            
        except Exception as e:
            logger.error(f"Error getting tables: {str(e)}")
            # Fallback to basic query
            try:
                basic_query = """
                SELECT 
                    TABLE_SCHEMA as schema_name,
                    TABLE_NAME as table_name,
                    TABLE_SCHEMA + '.' + TABLE_NAME as full_table_name,
                    'BASE TABLE' as table_type,
                    0 as column_count
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
                
                with self.engine.connect() as conn:
                    result = conn.execute(sqlalchemy.text(basic_query))
                    tables = result.fetchall()
                
                table_list = [dict(row._mapping) for row in tables]
                self.all_tables = table_list
                return table_list
                
            except Exception as e2:
                logger.error(f"Fallback query also failed: {str(e2)}")
                return []
    
    def get_all_schemas(self):
        """Get all schemas in the database"""
        try:
            if not self.engine:
                return []
            
            query = """
            SELECT DISTINCT 
                SCHEMA_NAME as schema_name,
                COUNT(*) as table_count
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            GROUP BY SCHEMA_NAME
            ORDER BY schema_name
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(query))
                schemas = result.fetchall()
                
            return [dict(row._mapping) for row in schemas]
            
        except Exception as e:
            logger.error(f"Error getting schemas: {str(e)}")
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
                COLUMN_DEFAULT,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE
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
                
                if all_tables:
                    # Get only table names for SQLDatabase (without schema prefix for include_tables)
                    table_names = [table['full_table_name'] for table in all_tables]
                    
                    # Create SQLDatabase with explicit table inclusion
                    self.db = SQLDatabase.from_uri(
                        self.connection_string,
                        sample_rows_in_table_info=2,
                        include_tables=table_names,
                        custom_table_info={
                            table['full_table_name']: f"Schema: {table['schema_name']}, Type: {table['table_type']}"
                            for table in all_tables
                        }
                    )
                    
                    return True, f"Successfully connected using driver: {used_driver}. Found {len(table_names)} tables across {len(set(table['schema_name'] for table in all_tables))} schemas."
                else:
                    # Fallback - create without explicit tables
                    self.db = SQLDatabase.from_uri(
                        self.connection_string,
                        sample_rows_in_table_info=2
                    )
                    return True, f"Successfully connected using driver: {used_driver}. Database connection established."
            else:
                return False, message
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            return False, f"Connection error: {str(e)}"
    
    def get_table_info(self):
        """Get comprehensive information about database tables"""
        if self.db:
            try:
                # Get all tables and schemas
                all_tables = self.get_all_tables_and_schemas()
                schemas = self.get_all_schemas()
                
                # Build comprehensive table info
                info_parts = []
                
                # Schema summary
                info_parts.append("DATABASE SCHEMA SUMMARY:")
                info_parts.append("=" * 50)
                info_parts.append(f"Total Schemas: {len(schemas)}")
                info_parts.append(f"Total Tables: {len(all_tables)}")
                info_parts.append("")
                
                # Schemas and their tables
                info_parts.append("SCHEMAS AND TABLES:")
                info_parts.append("=" * 50)
                
                for schema in schemas:
                    schema_tables = [t for t in all_tables if t['schema_name'] == schema['schema_name']]
                    info_parts.append(f"\n📁 Schema: {schema['schema_name']} ({len(schema_tables)} tables)")
                    
                    for table in schema_tables:
                        table_type_icon = "📊" if table['table_type'] == 'BASE TABLE' else "👁️"
                        info_parts.append(f"  {table_type_icon} {table['full_table_name']} ({table['table_type']})")
                
                # Get basic table info from SQLDatabase
                try:
                    basic_info = self.db.get_table_info()
                    info_parts.append("\n\nDETAILED TABLE INFORMATION:")
                    info_parts.append("=" * 50)
                    info_parts.append(basic_info)
                except Exception as e:
                    logger.warning(f"Could not get detailed table info: {str(e)}")
                
                info_parts.append("\n\nIMPORTANT NOTES:")
                info_parts.append("=" * 50)
                info_parts.append("• Always use fully qualified table names (e.g., SalesLT.Customer, dbo.Users)")
                info_parts.append("• Schema names are case-sensitive in some configurations")
                info_parts.append("• Use square brackets for names with spaces: [Column Name]")
                info_parts.append("• Common schemas: dbo (default), SalesLT (sample), sys (system)")
                
                return "\n".join(info_parts)
                
            except Exception as e:
                logger.error(f"Error getting comprehensive table info: {str(e)}")
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
        """Create SQL agent with enhanced prompt for schema awareness"""
        try:
            # Create SQL toolkit
            toolkit = SQLDatabaseToolkit(db=db, llm=self.llm)
            
            # Enhanced system prompt for better schema awareness
            system_prompt = """
            You are a SQL expert assistant that helps users query their database. 

            IMPORTANT SCHEMA GUIDELINES:
            1. ALWAYS use fully qualified table names with schema (e.g., SalesLT.Customer, dbo.Users)
            2. When listing tables, show ALL tables from ALL schemas
            3. Pay attention to different schemas like: dbo, SalesLT, sys, etc.
            4. Before answering, always consider what schema the tables belong to
            5. When asked about "all tables", make sure to check all schemas, not just the default one

            QUERY BEST PRACTICES:
            1. Use proper SQL syntax for SQL Server/Azure SQL
            2. Include schema names in all table references
            3. When showing table lists, group by schema for clarity
            4. Always double-check that you're querying the correct schema

            If a user asks about tables, make sure to query across all schemas to give a complete picture.
            """
            
            # Create the agent
            agent_executor = create_sql_agent(
                llm=self.llm,
                toolkit=toolkit,
                verbose=True,
                agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                handle_parsing_errors=True,
                max_iterations=10,
                early_stopping_method="force",
                return_intermediate_steps=True,
                agent_executor_kwargs={
                    "system_message": system_prompt
                }
            )
            
            self.agent = agent_executor
            return True, "SQL Agent created successfully with enhanced schema awareness!"
            
        except Exception as e:
            logger.error(f"Error creating SQL agent: {str(e)}")
            return False, f"Error creating agent: {str(e)}"
            
    def query_database(self, question, callback_handler=None):
        """Query database using natural language with enhanced schema context"""
        try:
            if not self.agent:
                return "Agent not initialized", None, None
            
            # Enhance the question with schema context for table listing queries
            enhanced_question = question
            if "table" in question.lower() and ("all" in question.lower() or "list" in question.lower()):
                enhanced_question = f"""
                {question}
                
                IMPORTANT: Please query across ALL schemas in the database, not just the default schema. 
                Use a query like: 
                SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_SCHEMA + '.' + TABLE_NAME as full_name 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE' 
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                
                Make sure to show tables from all schemas (dbo, SalesLT, sys, etc.) if they exist.
                """
            
            # Execute query with callback handler for streaming
            if callback_handler:
                response = self.agent.run(enhanced_question, callbacks=[callback_handler])
            else:
                response = self.agent.run(enhanced_question)
            
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
        
        # Show schema and table summary when connected
        if st.session_state.db_manager.all_tables:
            schemas = list(set(table['schema_name'] for table in st.session_state.db_manager.all_tables))
            st.markdown(f"""
            <div style="background: #e8f4fd; padding: 0.8rem; border-radius: 8px; margin: 0.5rem 0;">
                <strong>📊 Database Summary:</strong><br>
                🏢 Schemas: {len(schemas)}<br>
                📋 Tables: {len(st.session_state.db_manager.all_tables)}
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
            "Show me all tables in all schemas",
            "List all customers from SalesLT.Customer",
            "What tables are in the dbo schema?",
            "Show me all schemas and their table counts",
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
                placeholder="💭 Ask a question about your data... (e.g., Show me all tables in all schemas)",
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
        if st.button("📊 Schema Info", use_container_width=True):
            with st.expander("Complete Database Schema Information", expanded=True):
                table_info = st.session_state.db_manager.get_table_info()
                st.text_area("", table_info, height=600, label_visibility="collapsed")
    
    # Quick schema overview
    if st.session_state.db_manager.all_tables:
        with st.expander("📋 Quick Schema Overview", expanded=False):
            schemas_df = pd.DataFrame(st.session_state.db_manager.all_tables)
            if not schemas_df.empty:
                # Group by schema
                schema_summary = schemas_df.groupby('schema_name').agg({
                    'table_name': 'count',
                    'table_type': lambda x: x.value_counts().to_dict()
                }).reset_index()
                schema_summary.columns = ['Schema', 'Table Count', 'Table Types']
                
                st.markdown("**Schema Summary:**")
                for _, row in schema_summary.iterrows():
                    st.write(f"**{row['Schema']}**: {row['Table Count']} tables")
                
                st.markdown("**All Tables:**")
                # Display tables grouped by schema
                for schema in schemas_df['schema_name'].unique():
                    schema_tables = schemas_df[schemas_df['schema_name'] == schema]
                    st.markdown(f"**📁 {schema}:**")
                    for _, table in schema_tables.iterrows():
                        table_type_icon = "📊" if table['table_type'] == 'BASE TABLE' else "👁️"
                        st.write(f"  {table_type_icon} {table['full_table_name']}")

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
        <h2>👋 Welcome to Enhanced SQL AI Agent</h2>
        <p>Configure your API key and database connection in the sidebar to get started</p>
        <p><strong>🔍 Now with complete schema discovery across all database schemas!</strong></p>
    </div>
    """, unsafe_allow_html=True)

    # Enhanced example questions
    st.markdown('<div class="sub-header">📝 Example Questions You Can Ask</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    examples_left = [
        "Show me all tables in all schemas",
        "List all tables in the SalesLT schema",
        "What schemas exist in this database?",
        "Show me the structure of SalesLT.Customer table",
        "How many customers are in the database?"
    ]
    
    examples_right = [
        "What tables are in the dbo schema?",
        "Show me all views in the database",
        "List all schemas with their table counts",
        "What products are in SalesLT.Product?",
        "Calculate the total number of products"
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

    # Feature highlights
    st.markdown("---")
    st.markdown('<div class="sub-header">🚀 Enhanced Features</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="card">
            <h4>🔍 Complete Schema Discovery</h4>
            <p>Automatically discovers all tables across all schemas in your database, not just the default schema.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="card">
            <h4>🧠 Smart Query Understanding</h4>
            <p>Enhanced AI agent that understands schema context and generates accurate cross-schema queries.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="card">
            <h4>📊 Comprehensive Insights</h4>
            <p>Get detailed information about schemas, tables, views, and their relationships.</p>
        </div>
        """, unsafe_allow_html=True)

# Enhanced Footer
st.markdown("---")
st.markdown("""
<div class="footer">
    <p>Built with ❤️ using <strong>Streamlit</strong>, <strong>LangChain</strong>, and <strong>Google Gemini</strong></p>
    <p>🚀 Transform your data queries with the power of AI - Now with complete schema awareness!</p>
</div>
""", unsafe_allow_html=True)
