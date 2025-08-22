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
from sqlalchemy import text, inspect

# Custom SQL Database class for better SQL Server schema handling
class SQLServerDatabase(SQLDatabase):
    """Custom SQLDatabase that better handles SQL Server schemas"""
    
    def get_usable_table_names(self):
        """Get all table names including schema prefixes"""
        inspector = inspect(self._engine)
        table_names = []
        
        # Get tables from all schemas
        for schema in inspector.get_schema_names():
            if schema.lower() not in ['information_schema', 'sys']:  # Skip system schemas
                for table in inspector.get_table_names(schema=schema):
                    table_names.append(f"{schema}.{table}")
        
        return table_names
    
    def get_table_info(self, table_names=None):
        """Get table info with proper schema handling"""
        if table_names is None:
            table_names = self.get_usable_table_names()
        
        tables_info = []
        for table_name in table_names:
            if '.' in table_name:
                schema, table = table_name.split('.', 1)
            else:
                schema = 'dbo'
                table = table_name
            
            try:
                inspector = inspect(self._engine)
                columns = inspector.get_columns(table, schema=schema)
                
                table_info = f"Table: {schema}.{table}\n"
                for col in columns:
                    table_info += f"  - {col['name']}: {col['type']}\n"
                
                tables_info.append(table_info)
            except Exception as e:
                tables_info.append(f"Error getting info for {table_name}: {str(e)}")
        
        return "\n".join(tables_info)

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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
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
    
    .query-container {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        margin: 1rem 0;
    }
    
    .action-buttons {
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px solid #e9ecef;
    }
    
    .stAlert {
        margin: 1rem 0;
        border-radius: 8px;
    }
    
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
    
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        font-family: 'Inter', sans-serif;
        border-radius: 8px;
        border: 1px solid #ddd;
    }
    
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
    
    .footer {
        text-align: center;
        color: #6c757d;
        font-style: italic;
        margin-top: 3rem;
        padding: 2rem 0;
        border-top: 1px solid #e9ecef;
    }
    
    @media (max-width: 768px) {
        .main-header {
            font-size: 2rem;
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
        self.timeout = 60
        self.trust_cert = False
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
            f"TrustServerCertificate={'yes' if self.trust_cert else 'no'}&"
            f"Connection+Timeout={self.timeout}&"
            f"Login_Timeout={self.timeout}&"
            f"ConnectRetryCount=3&"
            f"ConnectRetryInterval=10"
        )
        return connection_string, driver
    
    def test_connection(self, connection_string):
        """Test database connection with enhanced error handling"""
        try:
            # Create engine with additional pool settings
            engine = sqlalchemy.create_engine(
                connection_string,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={
                    "timeout": self.timeout,
                    "autocommit": True
                }
            )
            
            with engine.connect() as conn:
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
                # Store the engine for table info queries
                self.engine = sqlalchemy.create_engine(
                    self.connection_string,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    connect_args={
                        "timeout": self.timeout,
                        "autocommit": True
                    }
                )
                
                # Create the database object with explicit schema configuration
                try:
                    # Use our custom SQL Server database class
                    engine = sqlalchemy.create_engine(self.connection_string)
                    self.db = SQLServerDatabase(engine)
                    
                    # Test that the database object works and log what it found
                    test_tables = self.db.get_usable_table_names()
                    logger.info(f"Custom SQLServerDatabase detected tables: {test_tables}")
                    
                except Exception as db_error:
                    logger.error(f"Error creating SQLDatabase object: {str(db_error)}")
                    return False, f"Database object creation failed: {str(db_error)}"
                    
                return True, f"Successfully connected using driver: {used_driver}"
            else:
                return False, message
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            return False, f"Connection error: {str(e)}"
    
    def get_table_info(self, table_name=None):
        """
        Get table information from the database.
        If table_name is provided, get info for that specific table.
        If not provided, get info for all tables.
        """
        try:
            if not self.engine:
                return "❌ Database not connected"
            
            if table_name:
                return self._get_specific_table_info(table_name)
            else:
                return self._get_all_tables_info()
                
        except Exception as e:
            logger.error(f"Error getting table info: {str(e)}")
            return f"❌ Error getting table information: {str(e)}"
    
    def _get_specific_table_info(self, table_name):
        """Get information for a specific table"""
        with self.engine.connect() as conn:
            if "." in table_name:
                schema, tbl = table_name.split(".", 1)
                query = """
                SELECT 
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    COLUMN_NAME,
                    DATA_TYPE,
                    IS_NULLABLE,
                    COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                AND TABLE_NAME = :table
                ORDER BY ORDINAL_POSITION
                """
                result = conn.execute(
                    text(query),
                    {"schema": schema, "table": tbl}
                ).fetchall()
            else:
                # Search all schemas for the table
                query = """
                SELECT 
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    COLUMN_NAME,
                    DATA_TYPE,
                    IS_NULLABLE,
                    COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = :table
                ORDER BY TABLE_SCHEMA, ORDINAL_POSITION
                """
                result = conn.execute(
                    text(query),
                    {"table": table_name}
                ).fetchall()

            if not result:
                return f"❌ Table `{table_name}` not found in any schema."

            # Format the result
            info = f"📊 Table Information for {table_name}:\n\n"
            current_table = None
            
            for row in result:
                schema, tbl, col, dtype, nullable, default = row
                table_full_name = f"{schema}.{tbl}"
                
                if current_table != table_full_name:
                    if current_table is not None:
                        info += "\n"
                    info += f"Table: {table_full_name}\n"
                    info += "-" * 50 + "\n"
                    current_table = table_full_name
                
                nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
                default_str = f" DEFAULT: {default}" if default else ""
                info += f"  • {col} ({dtype}) {nullable_str}{default_str}\n"

            return info
    
    def _get_all_tables_info(self):
        """Get information for all tables in the database"""
        try:
            with self.engine.connect() as conn:
                # Get all tables and views
                query = """
                SELECT 
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    TABLE_TYPE,
                    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                     WHERE COLUMNS.TABLE_SCHEMA = TABLES.TABLE_SCHEMA 
                     AND COLUMNS.TABLE_NAME = TABLES.TABLE_NAME) as COLUMN_COUNT
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
                
                result = conn.execute(text(query)).fetchall()
                
                if not result:
                    return "❌ No tables found in the database."
                
                info = "📊 Database Tables and Views:\n\n"
                current_schema = None
                
                for row in result:
                    schema, table, table_type, column_count = row
                    
                    if current_schema != schema:
                        if current_schema is not None:
                            info += "\n"
                        info += f"Schema: {schema}\n"
                        info += "=" * 50 + "\n"
                        current_schema = schema
                    
                    type_icon = "📋" if table_type == "BASE TABLE" else "👁️"
                    info += f"  {type_icon} {table} ({column_count} columns)\n"
                
                # Add summary
                total_tables = len([r for r in result if r[2] == 'BASE TABLE'])
                total_views = len([r for r in result if r[2] == 'VIEW'])
                info += f"\n📈 Summary: {total_tables} tables, {total_views} views\n"
                
                return info
                
        except Exception as e:
            return f"❌ Error retrieving table information: {str(e)}"
    
    def _get_all_schema_tables(self):
        """Get all tables with their schema prefixes for LangChain"""
        try:
            with self.engine.connect() as conn:
                query = """
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
                result = conn.execute(text(query)).fetchall()
                
                # Return list of fully qualified table names
                return [f"{row[0]}.{row[1]}" for row in result]
        except Exception as e:
            logger.error(f"Error getting schema tables: {str(e)}")
            return []
    
    def _get_custom_table_info(self):
        """Get custom table info for all schemas"""
        try:
            with self.engine.connect() as conn:
                # Get basic table info from all schemas
                query = """
                SELECT 
                    CONCAT(TABLE_SCHEMA, '.', TABLE_NAME) as full_table_name,
                    TABLE_SCHEMA,
                    TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
                result = conn.execute(text(query)).fetchall()
                
                custom_info = {}
                for row in result:
                    full_name, schema, table = row
                    # Get column info for this table
                    col_query = """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table
                    ORDER BY ORDINAL_POSITION
                    """
                    columns = conn.execute(text(col_query), {"schema": schema, "table": table}).fetchall()
                    
                    # Format table info string
                    table_info = f"CREATE TABLE {full_name} (\n"
                    col_lines = []
                    for col_name, col_type in columns:
                        col_lines.append(f"    [{col_name}] {col_type}")
                    table_info += ",\n".join(col_lines)
                    table_info += "\n)"
                    
                    custom_info[full_name] = table_info
                
                return custom_info
        except Exception as e:
            logger.error(f"Error getting custom table info: {str(e)}")
            return {}
    
    def _get_table_schema_info(self, table_name):
        """Get schema info for a specific table"""
        try:
            if '.' not in table_name:
                return None
                
            schema, table = table_name.split('.', 1)
            with self.engine.connect() as conn:
                query = """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table
                ORDER BY ORDINAL_POSITION
                """
                result = conn.execute(text(query), {"schema": schema, "table": table}).fetchall()
                
                if not result:
                    return None
                
                # Format as CREATE TABLE statement
                table_info = f"CREATE TABLE {table_name} (\n"
                col_lines = []
                for col_name, col_type in result:
                    col_lines.append(f"    [{col_name}] {col_type}")
                table_info += ",\n".join(col_lines)
                table_info += "\n)"
                
                return table_info
        except Exception as e:
            logger.error(f"Error getting table schema for {table_name}: {str(e)}")
            return None


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
            
            # Get the actual table list that LangChain detected
            try:
                available_tables = db.get_usable_table_names()
                table_list = ", ".join(available_tables)
            except:
                table_list = "various tables with schemas like SalesLT and dbo"
            
            # Create agent with enhanced system message
            system_message = f"""You are an expert SQL assistant for Azure SQL Database.

IMPORTANT: The database contains tables in multiple schemas including SalesLT and dbo schemas.

Available tables include: {table_list}

Critical guidelines:
1. ALWAYS use fully qualified table names with schema (e.g., SalesLT.Customer, dbo.BuildVersion)
2. When users ask about tables like "Customer", look for "SalesLT.Customer"
3. Use square brackets around column names: [Column Name]
4. For Azure SQL, use TOP instead of LIMIT
5. When listing tables, show the schema prefix

Before writing SQL queries:
1. Use sql_db_list_tables to see all available tables
2. Use sql_db_schema to get table structure
3. Then write your SQL query with proper schema.table format

Examples:
- "customers" likely refers to "SalesLT.Customer"
- "products" likely refers to "SalesLT.Product"
- "orders" likely refers to "SalesLT.SalesOrderHeader"
"""
            
            self.agent = create_sql_agent(
                llm=self.llm,
                toolkit=toolkit,
                verbose=True,
                agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                handle_parsing_errors=True,
                max_iterations=15,  # Increased for better schema exploration
                early_stopping_method="force",
                system_message=system_message
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
            
            # Execute query and capture intermediate steps
            if callback_handler:
                result = self.agent.invoke({"input": question}, {"callbacks": [callback_handler]})
            else:
                result = self.agent.invoke({"input": question})
            
            # Extract the response
            if isinstance(result, dict):
                response = result.get("output", str(result))
                # Try to extract SQL query from intermediate steps or agent scratchpad
                sql_query = self._extract_sql_query(result)
            else:
                response = str(result)
                sql_query = None
            
            return response, sql_query, None
        except Exception as e:
            logger.error(f"Query execution error: {str(e)}")
            return f"Error executing query: {str(e)}", None, None
    
    def _extract_sql_query(self, result):
        """Extract SQL query from agent result"""
        try:
            # Try to find SQL query in intermediate steps
            if "intermediate_steps" in result:
                for step in result["intermediate_steps"]:
                    if isinstance(step, tuple) and len(step) >= 2:
                        action, observation = step[0], step[1]
                        if hasattr(action, 'tool') and 'sql' in action.tool.lower():
                            if hasattr(action, 'tool_input'):
                                return action.tool_input
            
            # Fallback: try to extract from output text
            output = result.get("output", "")
            if "SELECT" in output.upper():
                # Try to extract SQL between common delimiters
                lines = output.split('\n')
                sql_lines = []
                in_sql = False
                for line in lines:
                    if "SELECT" in line.upper() or in_sql:
                        in_sql = True
                        sql_lines.append(line)
                        if line.strip().endswith(';'):
                            break
                if sql_lines:
                    return '\n'.join(sql_lines)
            
            return None
        except Exception as e:
            logger.error(f"Error extracting SQL query: {str(e)}")
            return None

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
                success, message = st.session_state.db_manager.connect_to_database(
                    server, database, username, password, trust_cert, connection_timeout
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
                        
                        # Show detected tables for debugging
                        try:
                            detected_tables = st.session_state.db_manager.db.get_usable_table_names()
                            with st.expander("🔍 Detected Tables", expanded=False):
                                st.write("LangChain detected the following tables:")
                                for table in detected_tables:
                                    st.write(f"✓ {table}")
                        except Exception as e:
                            st.warning(f"Could not list detected tables: {str(e)}")
                            
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
            "Show me all customers",
            "What are the top 5 products by sales?",
            "How many orders were placed last month?",
            "Calculate average order value",
            "Show sales by region"
        ]
        for example in examples:
            st.markdown(f"• {example}")

# Enhanced Main content area
if st.session_state.connected:
    # Chat interface with better formatting
    st.markdown('<div class="sub-header">💬 Chat with Your Database</div>', unsafe_allow_html=True)
    
    # Query input
    user_question = st.text_input(
        "",
        placeholder="💭 Ask a question about your data... (e.g., Show me the top 10 customers by total sales)",
        key="user_input",
        label_visibility="collapsed"
    )
    
    # Centered query button
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        query_button = st.button("🚀 Query", type="primary", use_container_width=True)
    
    # Action buttons section
    st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        if st.button("🗑️ Clear History", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
    
    with col2:
        if st.button("📊 Table Info", use_container_width=True):
            with st.expander("Database Table Information", expanded=True):
                # Fixed: Call get_table_info without arguments to get all tables
                table_info = st.session_state.db_manager.get_table_info()
                st.text_area("", table_info, height=400, label_visibility="collapsed")
    
    with col3:
        if st.button("🔍 Debug Schema", use_container_width=True):
            with st.expander("Schema Debug Information", expanded=True):
                if st.session_state.db_manager.db:
                    st.markdown("**LangChain Detected Tables:**")
                    try:
                        # Show what tables LangChain actually sees
                        available_tables = st.session_state.db_manager.db.get_usable_table_names()
                        for table in available_tables:
                            st.write(f"✓ {table}")
                        
                        st.markdown("**Database Schema Info:**")
                        schema_info = st.session_state.db_manager.db.get_table_info()
                        st.code(schema_info, language="sql")
                        
                    except Exception as e:
                        st.error(f"Error getting debug info: {str(e)}")
                else:
                    st.error("Database not connected")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # Process query
    if query_button and user_question:
        # Add a separator and container for the current query result
        st.markdown("---")
        st.markdown("### 🤖 Current Query Result")
        
        # Create a container for the immediate response
        current_response_container = st.container()
        
        with current_response_container:
            with st.spinner("🔍 Querying database..."):
                # Create callback handler for streaming
                callback_handler = StreamlitCallbackHandler(st.container())

                # Execute query
                response, sql_query, results = st.session_state.sql_agent.query_database(
                    user_question, callback_handler
                )

            # Display the current query and response immediately
            st.markdown("**❓ Your Question:**")
            st.markdown(f"""
            <div class="chat-question">
                {user_question}
            </div>
            """, unsafe_allow_html=True)

            # Display result
            if response and not response.startswith("Error"):
                st.markdown("**🤖 AI Response:**")
                st.markdown(f"""
                <div class="chat-answer">
                    {response}
                </div>
                """, unsafe_allow_html=True)
                
                # Show SQL query if extracted
                if sql_query:
                    st.markdown("**🔧 Generated SQL Query:**")
                    st.code(sql_query, language='sql')
                
                st.success("✅ Query completed successfully!")
                
            else:
                st.error("❌ Query failed!")
                st.error(response)

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

                # Show SQL query if available
                if chat.get('sql_query'):
                    st.markdown("**🔧 Generated SQL Query:**")
                    st.code(chat['sql_query'], language='sql')
                else:
                    # Try to extract SQL from response text
                    response_text = chat.get('response', '')
                    if 'SELECT' in response_text.upper():
                        st.markdown("**🔧 SQL Query (from response):**")
                        # Simple extraction of SQL-like content
                        lines = response_text.split('\n')
                        sql_content = []
                        for line in lines:
                            if any(keyword in line.upper() for keyword in ['SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'INSERT', 'UPDATE', 'DELETE']):
                                sql_content.append(line.strip())
                        if sql_content:
                            st.code('\n'.join(sql_content), language='sql')

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
        "Show me all tables in the database",
        "What are the column names in the customers table?",
        "How many records are in each table?",
        "Show me the top 5 customers by total purchase amount"
    ]
    
    examples_right = [
        "What products were sold last month?",
        "Calculate the average order value",
        "Show me sales by region",
        "List all orders from the last 30 days"
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
