#!/usr/bin/env python3
# Automated Index Recommendation System
# Core functionality for database monitoring and index recommendation

import sqlite3
import os
import time
import configparser
import json
from datetime import datetime, timedelta
import random
import logging
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("index_recommendation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, db_file):
        """Initialize with database file path."""
        self.db_file = db_file
        # We'll use check_same_thread=False to avoid thread issues
        # But we'll be careful to only use the connection from one thread at a time
        self.conn = None
        self.cursor = None
            
    def connect(self):
        """Establish a database connection that can be used across threads."""
        try:
            self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            return True
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            return False
            
    def ensure_connected(self):
        """Ensure we have a valid connection."""
        if self.conn is None:
            return self.connect()
        return True

    def close(self):
        """Close the database connection."""
        if hasattr(self, 'conn') and self.conn is not None:
            self.conn.close()
            self.conn = None
            self.cursor = None
            
    def commit(self):
        """Commit changes to the database."""
        if self.ensure_connected():
            self.conn.commit()
            
    def setup_tables(self):
        """Set up necessary tables if they don't exist."""
        try:
            self.ensure_connected()
            # Table to store query logs
            self.execute('''
                CREATE TABLE IF NOT EXISTS query_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    execution_time REAL NOT NULL,
                    execution_plan TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table to store index recommendations
            self.execute('''
                CREATE TABLE IF NOT EXISTS index_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    index_type TEXT,
                    create_statement TEXT NOT NULL,
                    applied INTEGER DEFAULT 0,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table to store performance comparison results
            self.execute('''
                CREATE TABLE IF NOT EXISTS performance_comparisons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id INTEGER,
                    original_time REAL,
                    optimized_time REAL,
                    improvement_percent REAL,
                    index_id INTEGER,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(query_id) REFERENCES query_logs(id),
                    FOREIGN KEY(index_id) REFERENCES index_recommendations(id)
                )
            ''')
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error setting up tables: {e}")
            return False
            
    def execute(self, query, params=()):
        """Execute a SQL query with parameters."""
        try:
            self.ensure_connected()
            return self.cursor.execute(query, params)
        except sqlite3.Error as e:
            logger.error(f"Error executing query: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise e
            
    def execute_and_fetch(self, query, params=(), fetch_all=True):
        """Execute a query and fetch results."""
        try:
            self.execute(query, params)
            if fetch_all:
                return self.cursor.fetchall()
            else:
                return self.cursor.fetchone()
        except sqlite3.Error as e:
            logger.error(f"Error executing and fetching query: {e}")
            raise e
            
    def get_tables(self):
        """Get a list of all tables in the database."""
        try:
            tables = self.execute_and_fetch("SELECT name FROM sqlite_master WHERE type='table'")
            return [table['name'] for table in tables]
        except sqlite3.Error as e:
            logger.error(f"Error getting tables: {e}")
            return []
            
    def get_table_structure(self, table_name):
        """Get the structure of a table."""
        try:
            return self.execute_and_fetch(f"PRAGMA table_info({table_name})")
        except sqlite3.Error as e:
            logger.error(f"Error getting table structure: {e}")
            return []
            
    def get_table_indexes(self, table_name):
        """Get all indexes for a table."""
        try:
            return self.execute_and_fetch(f"PRAGMA index_list({table_name})")
        except sqlite3.Error as e:
            logger.error(f"Error getting table indexes: {e}")
            return []
            
    def get_index_columns(self, index_name):
        """Get columns included in an index."""
        try:
            return self.execute_and_fetch(f"PRAGMA index_info({index_name})")
        except sqlite3.Error as e:
            logger.error(f"Error getting index columns: {e}")
            return []
            
    def get_row_count(self, table_name):
        """Get the number of rows in a table."""
        try:
            result = self.execute_and_fetch(f"SELECT COUNT(*) as count FROM {table_name}", fetch_all=False)
            return result['count']
        except sqlite3.Error as e:
            logger.error(f"Error getting row count: {e}")
            return 0


class QueryMonitor:
    """Monitors queries and their execution plans."""
    
    def __init__(self, db_manager):
        """Initialize with a database manager."""
        self.db_manager = db_manager
        
    def capture_query(self, query):
        """Capture a query, its execution plan and execution time."""
        try:
            if query.strip().upper().startswith(('EXPLAIN', 'PRAGMA')):
                # We don't log EXPLAIN or PRAGMA queries
                self.db_manager.execute(query)
                return None, None, None
                
            # Get execution plan
            plan_query = f"EXPLAIN QUERY PLAN {query}"
            self.db_manager.execute(plan_query)
            plan_rows = self.db_manager.cursor.fetchall()
            execution_plan = "\n".join([f"{row['id']}|{row['parent']}|{row['notused']}|{row['detail']}" for row in plan_rows])
            
            # Execute query and measure performance
            start_time = time.time()
            self.db_manager.execute(query)
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Log query
            self.db_manager.execute(
                "INSERT INTO query_logs (query, execution_time, execution_plan) VALUES (?, ?, ?)",
                (query, execution_time, execution_plan)
            )
            self.db_manager.commit()
            query_id = self.db_manager.cursor.lastrowid
            
            return execution_time, execution_plan, query_id
        except Exception as e:
            logger.error(f"Error capturing query: {e}")
            return None, str(e), None
            
    def get_query_logs(self, limit=100, order_by="timestamp DESC"):
        """Retrieve query logs."""
        try:
            logs = self.db_manager.execute_and_fetch(
                f"SELECT * FROM query_logs ORDER BY {order_by} LIMIT ?",
                (limit,)
            )
            return [dict(log) for log in logs]
        except sqlite3.Error as e:
            logger.error(f"Error getting query logs: {e}")
            return []
            
    def get_slow_queries(self, threshold=1.0, limit=20):
        """Retrieve slow queries above threshold execution time."""
        try:
            logs = self.db_manager.execute_and_fetch(
                "SELECT * FROM query_logs WHERE execution_time > ? ORDER BY execution_time DESC LIMIT ?",
                (threshold, limit)
            )
            return [dict(log) for log in logs]
        except sqlite3.Error as e:
            logger.error(f"Error getting slow queries: {e}")
            return []
            
    def get_frequent_queries(self, limit=20):
        """Retrieve the most frequent queries."""
        try:
            logs = self.db_manager.execute_and_fetch(
                """
                SELECT query, COUNT(*) as count, AVG(execution_time) as avg_time
                FROM query_logs 
                GROUP BY query 
                ORDER BY count DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(log) for log in logs]
        except sqlite3.Error as e:
            logger.error(f"Error getting frequent queries: {e}")
            return []


class IndexRecommender:
    """Recommends indexes based on query patterns."""
    
    def __init__(self, db_manager):
        """Initialize with a database manager."""
        self.db_manager = db_manager
        
    def analyze(self):
        """Analyze query patterns and recommend indexes."""
        try:
            # Get query logs for analysis
            query_logs = self.db_manager.execute_and_fetch(
                "SELECT * FROM query_logs ORDER BY timestamp DESC LIMIT 100"
            )
            
            if not query_logs:
                return []
                
            # Analyze each query and collect potential indexes
            potential_indexes = []
            for log in query_logs:
                query = log['query']
                execution_plan = log['execution_plan']
                
                # Skip non-SELECT queries for simplicity
                if not query.strip().upper().startswith('SELECT'):
                    continue
                    
                # Find tables, conditions and indexable fields
                tables, columns = self._parse_query(query)
                if not tables:
                    continue
                    
                # Look for full table scans
                if execution_plan and 'SCAN' in execution_plan and 'INDEX' not in execution_plan:
                    # This query is likely doing a full table scan
                    for table in tables:
                        indexed_columns = self._get_indexed_columns(table)
                        for column in columns:
                            # Check if this is a column from this table
                            if '.' in column:
                                # Format: table.column
                                parts = column.split('.')
                                if parts[0] != table and parts[0] != table[0]:  # Handle table aliases
                                    continue
                                column_name = parts[1]
                            else:
                                column_name = column
                                
                            if column_name not in indexed_columns:
                                potential_indexes.append({
                                    'table': table,
                                    'column': column_name,
                                    'query_id': log['id'],
                                    'execution_time': log['execution_time']
                                })
                
                # Look for opportunities for composite indexes
                if len(columns) > 1:
                    # Find tables with multiple conditions
                    table_columns = {}
                    for column in columns:
                        if '.' in column:
                            table_alias, col_name = column.split('.')
                            if table_alias in table_columns:
                                table_columns[table_alias].append(col_name)
                            else:
                                table_columns[table_alias] = [col_name]
                    
                    # For each table with multiple conditions, suggest a composite index
                    for alias, cols in table_columns.items():
                        if len(cols) > 1:
                            # Find the actual table name from alias
                            table_name = None
                            for t in tables:
                                if t == alias or (isinstance(t, tuple) and t[1] == alias):
                                    table_name = t if not isinstance(t, tuple) else t[0]
                                    break
                            
                            if table_name:
                                composite_key = "_".join(sorted(cols))
                                potential_indexes.append({
                                    'table': table_name,
                                    'column': composite_key,
                                    'is_composite': True,
                                    'composite_columns': cols,
                                    'query_id': log['id'],
                                    'execution_time': log['execution_time']
                                })
            
            # Score and rank potential indexes
            recommendations = self._score_indexes(potential_indexes)
            
            # Return top recommendations
            return recommendations[:10]  # Return top 10 recommendations
        except Exception as e:
            logger.error(f"Error analyzing for index recommendations: {e}")
            return []
            
    def _parse_query(self, query):
        """Parse a SQL query to extract tables and WHERE conditions.
        Returns a tuple of (tables, columns) where:
        - tables is a list of table names or (table_name, alias) tuples
        - columns is a list of column names (potentially with table prefixes)
        """
        try:
            # Normalize query - remove extra whitespace and convert to uppercase for parsing
            query = re.sub(r'\s+', ' ', query).strip()
            
            # Extract tables and their aliases from FROM and JOIN clauses
            tables = []
            
            # Find the FROM clause and everything after it
            from_match = re.search(r'FROM\s+(.*?)(?:WHERE|GROUP BY|HAVING|ORDER BY|LIMIT|;|$)', query, re.IGNORECASE)
            if not from_match:
                return [], []
                
            from_clause = from_match.group(1).strip()
            
            # Handle multiple tables in FROM clause (t1, t2, t3)
            tables_parts = re.split(r',\s*', from_clause)
            
            for part in tables_parts:
                # Handle JOIN syntax
                join_parts = re.split(r'\s+(?:JOIN|INNER JOIN|LEFT JOIN|RIGHT JOIN|FULL JOIN|OUTER JOIN)\s+', part, flags=re.IGNORECASE)
                
                for join_part in join_parts:
                    # Remove ON clause if present
                    join_part = re.sub(r'\s+ON\s+.*', '', join_part).strip()
                    
                    # Extract table name and potential alias
                    if re.search(r'\s+(?:AS\s+)?(\w+)$', join_part, re.IGNORECASE):
                        # Has an alias
                        table_alias_match = re.search(r'(\w+)\s+(?:AS\s+)?(\w+)$', join_part, re.IGNORECASE)
                        if table_alias_match:
                            table_name = table_alias_match.group(1)
                            alias = table_alias_match.group(2)
                            tables.append((table_name, alias))
                    else:
                        # No alias
                        tables.append(join_part.strip())
            
            # Extract all potential indexable conditions from various clauses
            indexable_columns = []
            
            # From WHERE clause
            where_match = re.search(r'WHERE\s+(.*?)(?:GROUP BY|HAVING|ORDER BY|LIMIT|;|$)', query, re.IGNORECASE)
            if where_match:
                where_clause = where_match.group(1).strip()
                # Extract column names from conditions, handling complex expressions
                where_columns = self._extract_columns_from_conditions(where_clause)
                indexable_columns.extend(where_columns)
            
            # From JOIN conditions
            for join_match in re.finditer(r'(?:JOIN|INNER JOIN|LEFT JOIN|RIGHT JOIN)\s+\w+\s+(?:AS\s+)?(\w+)\s+ON\s+(.*?)(?:JOIN|WHERE|GROUP BY|HAVING|ORDER BY|LIMIT|;|$)', query, re.IGNORECASE):
                join_condition = join_match.group(2).strip()
                join_columns = self._extract_columns_from_conditions(join_condition)
                indexable_columns.extend(join_columns)
            
            # From ORDER BY clause
            order_by_match = re.search(r'ORDER BY\s+(.*?)(?:LIMIT|;|$)', query, re.IGNORECASE)
            if order_by_match:
                order_clause = order_by_match.group(1).strip()
                # Split by commas to handle multiple ORDER BY columns
                order_parts = re.split(r',\s*', order_clause)
                for part in order_parts:
                    # Remove ASC/DESC specification
                    column = re.sub(r'\s+(?:ASC|DESC)$', '', part, flags=re.IGNORECASE).strip()
                    indexable_columns.append(column)
            
            # From GROUP BY clause
            group_by_match = re.search(r'GROUP BY\s+(.*?)(?:HAVING|ORDER BY|LIMIT|;|$)', query, re.IGNORECASE)
            if group_by_match:
                group_clause = group_by_match.group(1).strip()
                group_parts = re.split(r',\s*', group_clause)
                indexable_columns.extend([part.strip() for part in group_parts])
            
            # From HAVING clause
            having_match = re.search(r'HAVING\s+(.*?)(?:ORDER BY|LIMIT|;|$)', query, re.IGNORECASE)
            if having_match:
                having_clause = having_match.group(1).strip()
                having_columns = self._extract_columns_from_conditions(having_clause)
                indexable_columns.extend(having_columns)
            
            # Look for subqueries - recursively parse them
            for subquery_match in re.finditer(r'\(\s*SELECT\s+.*?\)', query, re.IGNORECASE | re.DOTALL):
                subquery = subquery_match.group(0)
                # Remove the outer parentheses
                subquery = subquery[1:-1].strip()
                # Parse the subquery
                sub_tables, sub_columns = self._parse_query(subquery)
                tables.extend(sub_tables)
                indexable_columns.extend(sub_columns)
            
            # Remove duplicates while preserving order
            unique_columns = []
            for col in indexable_columns:
                if col not in unique_columns:
                    unique_columns.append(col)
            
            return tables, unique_columns
        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            return [], []
    
    def _extract_columns_from_conditions(self, condition_str):
        """Extract column names from a condition string."""
        columns = []
        
        # Handle AND, OR, and parentheses
        # First, break the condition into parts
        condition_parts = []
        current_part = ""
        paren_level = 0
        
        for char in condition_str:
            if char == '(':
                paren_level += 1
                current_part += char
            elif char == ')':
                paren_level -= 1
                current_part += char
            elif char == ' ' and paren_level == 0 and current_part.upper().endswith(' AND'):
                condition_parts.append(current_part[:-4].strip())
                current_part = ""
            elif char == ' ' and paren_level == 0 and current_part.upper().endswith(' OR'):
                condition_parts.append(current_part[:-3].strip())
                current_part = ""
            else:
                current_part += char
        
        if current_part:
            condition_parts.append(current_part.strip())
        
        # If we couldn't break it down, treat the whole string as one condition
        if not condition_parts:
            condition_parts = [condition_str]
        
        # Extract column names from each part
        for part in condition_parts:
            # Handle comparison operators: =, <>, !=, >, <, >=, <=
            for op in ['=', '<>', '!=', '>=', '<=', '>', '<']:
                if op in part:
                    sides = part.split(op, 1)
                    left = sides[0].strip()
                    
                    # Check if left side is a column reference
                    if re.match(r'^[a-zA-Z0-9_.]+$', left) and not left.isdigit():
                        columns.append(left)
                    break
            
            # Handle IN conditions
            in_match = re.search(r'(\w+(?:\.\w+)?)\s+IN\s*\(', part, re.IGNORECASE)
            if in_match:
                columns.append(in_match.group(1))
            
            # Handle BETWEEN conditions
            between_match = re.search(r'(\w+(?:\.\w+)?)\s+BETWEEN\s+', part, re.IGNORECASE)
            if between_match:
                columns.append(between_match.group(1))
            
            # Handle LIKE conditions
            like_match = re.search(r'(\w+(?:\.\w+)?)\s+LIKE\s+', part, re.IGNORECASE)
            if like_match:
                columns.append(like_match.group(1))
            
            # Handle IS NULL/IS NOT NULL
            null_match = re.search(r'(\w+(?:\.\w+)?)\s+IS\s+(?:NOT\s+)?NULL', part, re.IGNORECASE)
            if null_match:
                columns.append(null_match.group(1))
        
        return columns
            
    def _get_indexed_columns(self, table_name):
        """Get already indexed columns for a table."""
        try:
            # If table_name is a tuple (table, alias), use the actual table name
            if isinstance(table_name, tuple):
                table_name = table_name[0]
                
            indexed_columns = set()
            
            # Get all indexes for the table
            indexes = self.db_manager.get_table_indexes(table_name)
            
            for index in indexes:
                index_name = index['name']
                index_columns = self.db_manager.get_index_columns(index_name)
                
                for col in index_columns:
                    # Get the column position from table schema
                    table_schema = self.db_manager.get_table_structure(table_name)
                    if col['seqno'] < len(table_schema):
                        column_name = table_schema[col['seqno']]['name']
                        indexed_columns.add(column_name)
            
            return indexed_columns
        except Exception as e:
            logger.error(f"Error getting indexed columns: {e}")
            return set()
            
    def _score_indexes(self, potential_indexes):
        """Score potential indexes based on various factors."""
        if not potential_indexes:
            return []
            
        scores = {}
        for idx in potential_indexes:
            # For composite indexes, use a unique key
            if idx.get('is_composite', False):
                key = f"{idx['table']}_composite_{idx['column']}"
            else:
                key = f"{idx['table']}_{idx['column']}"
            
            # Initialize if this is the first time we see this table/column combination
            if key not in scores:
                scores[key] = {
                    'table': idx['table'],
                    'column': idx['column'],
                    'score': 0,
                    'count': 0,
                    'avg_execution_time': 0,
                    'total_execution_time': 0,
                    'is_composite': idx.get('is_composite', False),
                    'composite_columns': idx.get('composite_columns', [])
                }
                
            # Update metrics
            scores[key]['count'] += 1
            scores[key]['total_execution_time'] += idx['execution_time']
            scores[key]['avg_execution_time'] = scores[key]['total_execution_time'] / scores[key]['count']
            
            # Scoring: frequency + execution time impact + bonus for composite indexes
            base_score = (scores[key]['count'] * 0.6) + (scores[key]['avg_execution_time'] * 0.4 * 10)
            if scores[key]['is_composite']:
                # Give extra weight to composite indexes with multiple conditions
                base_score *= (1 + 0.2 * len(scores[key]['composite_columns']))
                
            scores[key]['score'] = base_score
        
        # Convert to list and sort by score
        recommendations = []
        for key, data in scores.items():
            # Generate appropriate index name and statement based on whether it's composite
            if data['is_composite']:
                # For composite indexes, use all columns
                index_name = f"idx_{data['table']}_{'_'.join(data['composite_columns'])}"
                column_list = ', '.join(data['composite_columns'])
                create_statement = f"CREATE INDEX {index_name} ON {data['table']} ({column_list})"
                column_display = ', '.join(data['composite_columns'])
                index_type = 'COMPOSITE'
            else:
                # For regular single-column indexes
                index_name = f"idx_{data['table']}_{data['column']}"
                create_statement = f"CREATE INDEX {index_name} ON {data['table']} ({data['column']})"
                column_display = data['column']
                index_type = ''
            
            # Add to recommendations
            recommendations.append({
                'table': data['table'],
                'column': column_display,
                'score': round(data['score'], 2),
                'count': data['count'],
                'avg_execution_time': round(data['avg_execution_time'], 4),
                'index_name': index_name,
                'create_statement': create_statement,
                'index_type': index_type,
                'estimated_impact': round(min(data['score'] * 5, 95), 1)  # Capped at 95%
            })
            
        # Sort by score (descending)
        return sorted(recommendations, key=lambda x: x['score'], reverse=True)


class PerformanceComparer:
    """Compares query performance with and without indexes."""
    
    def __init__(self, db_manager):
        """Initialize with a database manager."""
        self.db_manager = db_manager
        
    def compare_with_index(self, query, create_index_statement):
        """Compare query performance with and without an index."""
        try:
            # Sanitize the query to ensure it's properly formatted for SQLite
            query = query.strip()
            
            # 1. Measure original performance
            start_time = time.time()
            try:
                self.db_manager.execute(query)
                end_time = time.time()
                original_time = end_time - start_time
            except sqlite3.Error as e:
                logger.error(f"Error executing original query: {e}")
                return {'error': f"Original query execution failed: {str(e)}", 'success': False}
            
            # Extract index name for later removal
            index_name_match = re.search(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)", create_index_statement, re.IGNORECASE)
            if not index_name_match:
                return {'error': 'Invalid CREATE INDEX statement'}
                
            index_name = index_name_match.group(1)
            
            # 2. Create the index
            try:
                self.db_manager.execute(create_index_statement)
            except sqlite3.Error as e:
                logger.error(f"Error creating index: {e}")
                return {'error': f"Failed to create index: {str(e)}", 'success': False}
            
            try:
                # 3. Measure performance with index
                start_time = time.time()
                self.db_manager.execute(query)
                end_time = time.time()
                optimized_time = end_time - start_time
                
                # Calculate improvement
                if original_time > 0:
                    improvement = ((original_time - optimized_time) / original_time) * 100
                else:
                    improvement = 0
                    
                result = {
                    'original_time': round(original_time * 1000, 2),  # Convert to ms
                    'optimized_time': round(optimized_time * 1000, 2),  # Convert to ms
                    'improvement': round(improvement, 2),
                    'success': True
                }
            except sqlite3.Error as e:
                logger.error(f"Error executing query with index: {e}")
                result = {'error': f"Query with index failed: {str(e)}", 'success': False}
            finally:
                # 4. Drop the index to restore original state
                try:
                    self.db_manager.execute(f"DROP INDEX IF EXISTS {index_name}")
                except sqlite3.Error as e:
                    logger.warning(f"Error dropping index: {e}")
                
            return result
        except Exception as e:
            logger.error(f"Error comparing performance: {e}")
            return {'error': str(e), 'success': False}


class ConfigManager:
    """Manages configuration settings."""
    
    def __init__(self, config_file='config.ini'):
        """Initialize with configuration file path."""
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load()
        
    def load(self):
        """Load configuration from file, creating default if needed."""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            # Set default configuration
            self.config['DATABASE'] = {
                'db_file': 'index_recommendation.db',
                'backup_directory': 'backups',
                'auto_backup': 'false'
            }
            
            self.config['UI'] = {
                'theme': 'default',
                'table_format': 'grid',
                'show_execution_plan': 'ask',
                'max_results': '100'
            }
            
            self.config['ANALYSIS'] = {
                'min_index_score': '2',
                'consider_query_frequency': 'true',
                'log_retention_days': '30'
            }
            
            self.save()
            
    def save(self):
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
            
    def get(self, section, key, default=None):
        """Get a configuration value."""
        try:
            return self.config[section][key]
        except (KeyError, configparser.NoSectionError):
            return default
            
    def set(self, section, key, value):
        """Set a configuration value."""
        if section not in self.config:
            self.config[section] = {}
            
        self.config[section][key] = str(value)
        self.save()


class DataVisualizer:
    """Generates data for visualization."""
    
    def __init__(self, db_manager, config_manager):
        """Initialize with database and config managers."""
        self.db_manager = db_manager
        self.config_manager = config_manager
        
    def get_query_performance_data(self, period='daily'):
        """Get query performance data for visualizations."""
        try:
            if period == 'daily':
                # Data for the last 7 days
                days = 7
                interval = 'day'
                format_str = '%Y-%m-%d'
            elif period == 'weekly':
                # Data for the last 4 weeks
                days = 28
                interval = 'week'
                format_str = '%Y-W%W'
            elif period == 'monthly':
                # Data for the last 6 months
                days = 180
                interval = 'month'
                format_str = '%Y-%m'
            else:
                return {'error': 'Invalid period'}
                
            # Calculate date ranges
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Get query logs within the date range
            logs = self.db_manager.execute_and_fetch(
                "SELECT * FROM query_logs WHERE timestamp >= ? ORDER BY timestamp",
                (start_date.strftime('%Y-%m-%d'),)
            )
            
            # Group by interval
            data = {}
            for log in logs:
                timestamp = datetime.strptime(log['timestamp'], '%Y-%m-%d %H:%M:%S')
                interval_key = timestamp.strftime(format_str)
                
                if interval_key not in data:
                    data[interval_key] = {
                        'count': 0,
                        'total_time': 0,
                        'avg_time': 0
                    }
                    
                data[interval_key]['count'] += 1
                data[interval_key]['total_time'] += log['execution_time']
                data[interval_key]['avg_time'] = data[interval_key]['total_time'] / data[interval_key]['count']
                
            # Format for charts
            labels = list(data.keys())
            values = [round(data[label]['avg_time'] * 1000, 2) for label in labels]  # Convert to ms
            
            return {
                'labels': labels,
                'values': values
            }
        except Exception as e:
            logger.error(f"Error getting query performance data: {e}")
            return {'error': str(e)}
            
    def get_index_impact_data(self):
        """Get data showing the impact of indexes."""
        try:
            # Get performance comparison data
            comparisons = self.db_manager.execute_and_fetch(
                """
                SELECT pc.*, ir.table_name, ir.column_name, ir.index_name
                FROM performance_comparisons pc
                JOIN index_recommendations ir ON pc.index_id = ir.id
                ORDER BY pc.timestamp DESC
                LIMIT 20
                """
            )
            
            result = []
            for comp in comparisons:
                result.append({
                    'table': comp['table_name'],
                    'column': comp['column_name'],
                    'index_name': comp['index_name'],
                    'original_time': round(comp['original_time'] * 1000, 2),  # Convert to ms
                    'optimized_time': round(comp['optimized_time'] * 1000, 2),  # Convert to ms
                    'improvement_percent': round(comp['improvement_percent'], 2)
                })
                
            return result
        except Exception as e:
            logger.error(f"Error getting index impact data: {e}")
            return []


class SampleDataGenerator:
    """Generates sample data for testing."""
    
    def __init__(self, db_manager):
        """Initialize with a database manager."""
        self.db_manager = db_manager
        
    def generate_sample_data(self):
        """Generate sample tables and data for testing."""
        try:
            # Create sample tables if they don't exist
            self._create_sample_tables()
            
            # Check if we need to insert data
            if self.db_manager.get_row_count('users') == 0:
                self._insert_sample_users()
                
            if self.db_manager.get_row_count('products') == 0:
                self._insert_sample_products()
                
            if self.db_manager.get_row_count('orders') == 0:
                self._insert_sample_orders()
                
            # Generate some sample queries
            if self.db_manager.get_row_count('query_logs') == 0:
                self._generate_sample_queries()
                
            self.db_manager.commit()
            logger.info("Sample data generated successfully")
            return True
        except Exception as e:
            logger.error(f"Error generating sample data: {e}")
            return False
            
    def _create_sample_tables(self):
        """Create sample tables for a mock e-commerce database."""
        # Users table
        self.db_manager.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                registration_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Products table
        self.db_manager.execute('''
            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY,
                product_name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                category TEXT,
                stock_quantity INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Orders table
        self.db_manager.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                order_date TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                total_amount REAL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Order Items table
        self.db_manager.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                item_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(order_id),
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        ''')
        
    def _insert_sample_users(self):
        """Insert sample user data."""
        users = [
            (1, 'john_doe', 'john@example.com', 'password123', 'John', 'Doe', '2023-01-15'),
            (2, 'jane_smith', 'jane@example.com', 'password456', 'Jane', 'Smith', '2023-02-20'),
            (3, 'bob_johnson', 'bob@example.com', 'password789', 'Bob', 'Johnson', '2023-03-10'),
            (4, 'alice_brown', 'alice@example.com', 'passwordabc', 'Alice', 'Brown', '2023-03-15'),
            (5, 'charlie_davis', 'charlie@example.com', 'passworddef', 'Charlie', 'Davis', '2023-04-01')
        ]
        
        self.db_manager.execute('DELETE FROM users')
        for user in users:
            self.db_manager.execute(
                'INSERT INTO users (user_id, username, email, password, first_name, last_name, registration_date) VALUES (?, ?, ?, ?, ?, ?, ?)',
                user
            )
            
    def _insert_sample_products(self):
        """Insert sample product data."""
        products = [
            (1, 'Laptop', 'High-performance laptop for professionals', 1299.99, 'Electronics', 25, '2023-01-10'),
            (2, 'Smartphone', 'Latest model with advanced features', 799.99, 'Electronics', 50, '2023-01-15'),
            (3, 'T-shirt', 'Cotton t-shirt in various colors', 19.99, 'Clothing', 100, '2023-02-01'),
            (4, 'Coffee Maker', 'Automatic coffee maker with timer', 89.99, 'Home Appliances', 30, '2023-02-15'),
            (5, 'Running Shoes', 'Comfortable shoes for runners', 129.99, 'Footwear', 40, '2023-03-01'),
            (6, 'Monitor', '27-inch 4K monitor for great visuals', 349.99, 'Electronics', 20, '2023-03-15'),
            (7, 'Desk Chair', 'Ergonomic chair for office or home', 199.99, 'Furniture', 15, '2023-04-01'),
            (8, 'Headphones', 'Noise-canceling wireless headphones', 149.99, 'Electronics', 35, '2023-04-15')
        ]
        
        self.db_manager.execute('DELETE FROM products')
        for product in products:
            self.db_manager.execute(
                'INSERT INTO products (product_id, product_name, description, price, category, stock_quantity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                product
            )
            
    def _insert_sample_orders(self):
        """Insert sample order data."""
        orders = [
            (1, 1, '2023-05-10 10:23:45', 'completed', 1299.99),
            (2, 2, '2023-05-12 14:30:22', 'completed', 839.98),
            (3, 3, '2023-05-15 09:15:10', 'processing', 149.99),
            (4, 1, '2023-05-20 16:45:33', 'completed', 269.98),
            (5, 4, '2023-05-25 11:20:15', 'pending', 199.99)
        ]
        
        order_items = [
            (1, 1, 1, 1, 1299.99),
            (2, 2, 2, 1, 799.99),
            (3, 2, 4, 1, 39.99),
            (4, 3, 3, 5, 99.95),
            (5, 3, 8, 1, 149.99),
            (6, 4, 4, 2, 179.98),
            (7, 4, 3, 1, 19.99),
            (8, 4, 5, 1, 129.99),
            (9, 5, 7, 1, 199.99)
        ]
        
        self.db_manager.execute('DELETE FROM order_items')
        self.db_manager.execute('DELETE FROM orders')
        
        for order in orders:
            self.db_manager.execute(
                'INSERT INTO orders (order_id, user_id, order_date, status, total_amount) VALUES (?, ?, ?, ?, ?)',
                order
            )
            
        for item in order_items:
            self.db_manager.execute(
                'INSERT INTO order_items (item_id, order_id, product_id, quantity, price) VALUES (?, ?, ?, ?, ?)',
                item
            )
            
    def _generate_sample_queries(self):
        """Generate sample queries for testing."""
        queries = [
            "SELECT * FROM users WHERE username = 'john_doe'",
            "SELECT * FROM products WHERE category = 'Electronics'",
            "SELECT * FROM products WHERE price < 200",
            "SELECT * FROM orders WHERE user_id = 1",
            "SELECT * FROM order_items WHERE order_id = 2",
            "SELECT u.username, COUNT(o.order_id) AS order_count FROM users u JOIN orders o ON u.user_id = o.user_id GROUP BY u.username",
            "SELECT p.product_name, SUM(oi.quantity) AS total_sold FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_name",
            "SELECT * FROM products WHERE stock_quantity < 30",
            "SELECT * FROM users WHERE registration_date > '2023-03-01'",
            "SELECT o.order_id, SUM(oi.quantity * oi.price) AS actual_total FROM orders o JOIN order_items oi ON o.order_id = oi.order_id GROUP BY o.order_id"
        ]
        
        # Generate query logs with mock execution times and plans
        for query in queries:
            execution_time = random.uniform(0.01, 2.0)
            execution_plan = f"QUERY PLAN\n{'=' * 40}\nMOCK EXECUTION PLAN FOR: {query}\n"
            
            if "WHERE" in query and random.random() < 0.7:
                execution_plan += "SCAN TABLE users\nSCAN TABLE products\n"
            else:
                execution_plan += "SEARCH TABLE users USING INDEX idx_username\nSEARCH TABLE products USING INDEX idx_category\n"
                
            self.db_manager.execute(
                "INSERT INTO query_logs (query, execution_time, execution_plan, timestamp) VALUES (?, ?, ?, ?)",
                (query, execution_time, execution_plan, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )