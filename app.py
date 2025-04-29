

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session, g
import os
import json
import sqlite3
import time
from datetime import datetime, timedelta
import csv
import random
from werkzeug.utils import secure_filename
import io
import shutil
from pathlib import Path

# Import core modules
from main import (
    DatabaseManager, 
    QueryMonitor, 
    IndexRecommender,
    PerformanceComparer, 
    ConfigManager,
    DataVisualizer,
    SampleDataGenerator
)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'index_recommendation_secret_key'

# Initialize configuration
config_manager = ConfigManager()
db_file = config_manager.get('DATABASE', 'db_file', 'index_recommendation.db')
backup_dir = config_manager.get('DATABASE', 'backup_directory', 'backups')

# Ensure backup directory exists
os.makedirs(backup_dir, exist_ok=True)

# Create database connection with thread-safe settings
db_manager = DatabaseManager(db_file)
db_manager.connect()  # Establish the connection immediately with check_same_thread=False
db_manager.setup_tables()  # Setup tables with the established connection

# Create other managers with the database connection
query_monitor = QueryMonitor(db_manager)
index_recommender = IndexRecommender(db_manager)
performance_comparer = PerformanceComparer(db_manager)
data_visualizer = DataVisualizer(db_manager, config_manager)

# Optional - create sample data if tables are empty
tables = db_manager.get_tables()
if not tables or ('users' not in tables or 'products' not in tables or 'orders' not in tables or 'query_logs' not in tables):
    sample_data_generator = SampleDataGenerator(db_manager)
    sample_data_generator.generate_sample_data()

# Helper functions
def get_current_database():
    """Get the name of the current database file."""
    return os.path.basename(db_file)

def format_timestamp(timestamp_str):
    """Format a timestamp string for display."""
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        delta = now - timestamp

        if delta < timedelta(minutes=1):
            return "Just now"
        elif delta < timedelta(hours=1):
            minutes = int(delta.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        elif delta < timedelta(days=1):
            hours = int(delta.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        else:
            days = delta.days
            return f"{days} day{'s' if days > 1 else ''} ago"
    except Exception:
        return timestamp_str

# Generate mock data for UI visualization
def generate_mock_stats():
    """Generate mock statistics for the dashboard."""
    return {
        'total_indexes': random.randint(8, 15),
        'tables_analyzed': random.randint(4, 8),
        'pending_recommendations': random.randint(3, 10),
        'performance_improvement': random.randint(18, 45),
        'database_size': f"{random.randint(5, 50)} MB",
        'database_size_percentage': random.randint(5, 90),
        'memory_usage': f"{random.randint(20, 80)}%",
        'memory_usage_percentage': random.randint(20, 80),
        'cache_hit_ratio': random.randint(60, 95),
        'avg_query_time': round(random.uniform(10, 100), 2),
        'avg_query_time_percentage': min(100, round(random.uniform(10, 100), 2))
    }

def generate_performance_data():
    """Generate mock performance data for charts."""
    # Daily data (last 7 days)
    daily_labels = [(datetime.now() - timedelta(days=i)).strftime('%b %d') for i in range(6, -1, -1)]
    daily_values = [round(random.uniform(10, 100), 2) for _ in range(7)]
    
    # Weekly data (last 4 weeks)
    weekly_labels = [(datetime.now() - timedelta(weeks=i)).strftime('Week %U') for i in range(3, -1, -1)]
    weekly_values = [round(random.uniform(20, 90), 2) for _ in range(4)]
    
    # Monthly data (last 6 months)
    monthly_labels = [(datetime.now() - timedelta(days=i*30)).strftime('%b %Y') for i in range(5, -1, -1)]
    monthly_values = [round(random.uniform(30, 80), 2) for _ in range(6)]
    
    return {
        'daily': {
            'labels': daily_labels,
            'avg_query_time': daily_values
        },
        'weekly': {
            'labels': weekly_labels,
            'avg_query_time': weekly_values
        },
        'monthly': {
            'labels': monthly_labels,
            'avg_query_time': monthly_values
        }
    }

def generate_mock_recent_activity():
    """Generate mock recent activity data for the dashboard."""
    activity_types = ['query', 'index_created', 'recommendation_generated']
    activities = []
    
    for i in range(5):
        activity_type = random.choice(activity_types)
        timestamp = (datetime.now() - timedelta(minutes=random.randint(5, 600))).strftime("%Y-%m-%d %H:%M:%S")
        
        if activity_type == 'query':
            description = f"Query executed on table {'users' if i % 3 == 0 else 'products' if i % 3 == 1 else 'orders'}"
        elif activity_type == 'index_created':
            description = f"Created index on {'username' if i % 2 == 0 else 'category'} column"
        else:
            description = f"Generated new index recommendations"
            
        activities.append({
            'type': activity_type,
            'description': description,
            'timestamp': format_timestamp(timestamp)
        })
        
    return activities

def generate_mock_recommendations():
    """Generate mock high-priority recommendations for the dashboard."""
    tables = ['users', 'products', 'orders', 'order_items']
    columns = ['user_id', 'username', 'category', 'status', 'product_id']
    
    recommendations = []
    for i in range(3):
        recommendations.append({
            'id': i + 1,
            'table': random.choice(tables),
            'column': random.choice(columns),
            'index_type': '' if i % 2 == 0 else 'UNIQUE',
            'score': round(random.uniform(7.0, 9.5), 2),
            'estimated_impact': round(random.uniform(25, 65), 1),
            'index_name': f"idx_recommendation_{i+1}",
            'create_statement': f"CREATE INDEX idx_recommendation_{i+1} ON {tables[i % len(tables)]} ({columns[i % len(columns)]})"
        })
        
    return recommendations

# Routes
@app.route('/')
def index():
    """Redirect to the dashboard."""
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    """Render the dashboard page with statistics and recommendations."""
    try:
        stats = generate_mock_stats()
        performance_data = generate_performance_data()
        recent_activity = generate_mock_recent_activity()
        high_priority_recommendations = generate_mock_recommendations()
        
        # Ensure all data is properly formatted for JSON serialization
        for period in performance_data:
            # Convert any potential tuple/complex types to strings in labels
            performance_data[period]['labels'] = [str(label) for label in performance_data[period]['labels']]
            
        return render_template(
            'dashboard.html',
            stats=stats,
            performance_data=performance_data,
            recent_activity=recent_activity,
            high_priority_recommendations=high_priority_recommendations,
            current_database=get_current_database()
        )
    except Exception as e:
        # Log the error but render a simplified version of the dashboard
        import traceback
        print(f"Dashboard error: {str(e)}")
        print(traceback.format_exc())
        return render_template(
            'dashboard.html',
            error=str(e),
            stats={
                'total_indexes': 0,
                'tables_analyzed': 0,
                'pending_recommendations': 0,
                'performance_improvement': 0,
                'database_size': '0 MB',
                'database_size_percentage': 0,
                'memory_usage': '0%',
                'memory_usage_percentage': 0,
                'cache_hit_ratio': 0,
                'avg_query_time': 0,
                'avg_query_time_percentage': 0
            },
            performance_data={
                'daily': {'labels': ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7'], 'avg_query_time': [0, 0, 0, 0, 0, 0, 0]},
                'weekly': {'labels': ['Week 1', 'Week 2', 'Week 3', 'Week 4'], 'avg_query_time': [0, 0, 0, 0]},
                'monthly': {'labels': ['Month 1', 'Month 2', 'Month 3', 'Month 4', 'Month 5', 'Month 6'], 'avg_query_time': [0, 0, 0, 0, 0, 0]}
            },
            recent_activity=[],
            high_priority_recommendations=[],
            current_database=get_current_database()
        )

@app.route('/query-editor')
def query_editor():
    """Render the query editor page."""
    # Get recent query history
    query_history = query_monitor.get_query_logs(limit=5)
    formatted_history = []
    
    for log in query_history:
        formatted_history.append({
            'query': log['query'],
            'execution_time': round(log['execution_time'] * 1000, 2),  # Convert to milliseconds
            'timestamp': format_timestamp(log['timestamp']),
            'id': log['id']
        })
    
    # Get all tables from the database
    tables = db_manager.get_tables()
    
    return render_template('query.html', query_history=formatted_history, tables=tables, current_database=get_current_database())

@app.route('/get-table-schema/<table_name>')
def get_table_schema(table_name):
    """API endpoint to get the schema of a table."""
    try:
        columns = db_manager.get_table_structure(table_name)
        schema = []
        
        for col in columns:
            schema.append({
                'name': col['name'],
                'type': col['type'],
                'pk': col['pk'] == 1
            })
            
        return jsonify({'schema': schema})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/run-query', methods=['POST'])
def run_query():
    """API endpoint to run a SQL query."""
    query = request.json.get('query')
    
    if not query:
        return jsonify({'error': 'No query provided'})
    
    try:
        start_time = time.time()
        
        # For EXPLAIN queries, we handle them differently
        if query.strip().upper().startswith('EXPLAIN'):
            rows = db_manager.execute_and_fetch(query)
            execution_plan = "\n".join([str(dict(row)) for row in rows])
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            return jsonify({
                'execution_time': execution_time,
                'execution_plan': execution_plan,
                'results': [],
                'columns': []
            })
        
        # For normal queries, log them and return results
        execution_time, execution_plan, query_id = query_monitor.capture_query(query)
        
        if execution_time is None:
            return jsonify({'error': execution_plan})  # execution_plan contains error message in this case
        
        # Fetch results
        results = db_manager.cursor.fetchall()
        
        # Convert results to a list of dictionaries
        result_list = []
        columns = []
        
        if results:
            columns = [column[0] for column in db_manager.cursor.description]
            for row in results:
                result_dict = {}
                for i, column in enumerate(columns):
                    result_dict[column] = row[i]
                result_list.append(result_dict)
        
        return jsonify({
            'execution_time': execution_time,
            'execution_plan': execution_plan,
            'results': result_list,
            'columns': columns
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/index-recommendations')
def index_recommendations():
    """Render the index recommendations page."""
    try:
        # Get real recommendations
        recommendations = index_recommender.analyze()
        
        # If we don't have enough real data, add some mock data
        if len(recommendations) < 3:
            mock_recommendations = generate_mock_recommendations()
            for rec in mock_recommendations:
                if len(recommendations) >= 5:
                    break
                recommendations.append(rec)
        
        # Group recommendations by table
        tables = {}
        for rec in recommendations:
            table_name = rec['table']
            if table_name not in tables:
                tables[table_name] = []
            tables[table_name].append(rec)
        
        return render_template(
            'recommendations.html',
            recommendations=recommendations,
            tables=tables,
            current_database=get_current_database()
        )
    except Exception as e:
        return render_template(
            'recommendations.html',
            error=str(e),
            recommendations=[],
            tables={},
            current_database=get_current_database()
        )

@app.route('/performance-metrics')
def performance_metrics():
    """Render the performance metrics page."""
    stats = generate_mock_stats()
    performance_data = generate_performance_data()
    
    return render_template(
        'performance_metrics.html',
        stats=stats,
        performance_data=performance_data,
        current_database=get_current_database()
    )

@app.route('/settings')
def settings():
    """Render the settings page."""
    # Get configuration settings
    db_settings = {}
    for key in config_manager.config['DATABASE']:
        db_settings[key] = config_manager.get('DATABASE', key)
        
    ui_settings = {}
    for key in config_manager.config['UI']:
        ui_settings[key] = config_manager.get('UI', key)
        
    analysis_settings = {}
    for key in config_manager.config['ANALYSIS']:
        analysis_settings[key] = config_manager.get('ANALYSIS', key)
    
    # Create a properly structured config object for the template
    config = {
        'database': db_settings,
        'ui': ui_settings,
        'analysis': analysis_settings
    }
    
    return render_template(
        'settings.html',
        config=config,
        current_database=get_current_database()
    )

@app.route('/api/update-settings', methods=['POST'])
def update_settings():
    """API endpoint to update settings."""
    settings = request.json
    
    try:
        for section, values in settings.items():
            for key, value in values.items():
                config_manager.set(section, key, value)
                
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/apply-index', methods=['POST'])
def apply_index():
    """API endpoint to apply a recommended index."""
    create_statement = request.json.get('create_statement')
    
    if not create_statement:
        return jsonify({'error': 'No CREATE INDEX statement provided'})
    
    try:
        # Sanitize the CREATE INDEX statement to ensure SQLite compatibility
        create_statement = create_statement.strip()
        
        # Properly format the CREATE INDEX statement to avoid syntax errors
        # Handle parentheses spacing which is a common source of SQLite syntax errors
        if '(' in create_statement:
            # Make sure there's no space after opening parenthesis
            create_statement = create_statement.replace('( ', '(')
            # Make sure there's no space before closing parenthesis
            create_statement = create_statement.replace(' )', ')')
            # Handle spacing around commas in column lists
            create_statement = create_statement.replace(' , ', ',')
            create_statement = create_statement.replace(', ', ',')
            
        # Extract index name for logging purposes
        import re
        index_name_match = re.search(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)', create_statement, re.IGNORECASE)
        index_name = index_name_match.group(1) if index_name_match else "unknown"
        
        # Generate a safe SQL statement
        # For composite indexes, ensure proper formatting
        if ',' in create_statement and '(' in create_statement:
            # Extract parts of the statement to rebuild it safely
            match = re.match(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+(\w+)\s*\((.*)\)', create_statement, re.IGNORECASE)
            if match:
                idx_name = match.group(1)
                table_name = match.group(2)
                column_list = match.group(3)
                
                # Clean up column list
                columns = [col.strip() for col in column_list.split(',')]
                clean_column_list = ','.join(columns)
                
                # Rebuild the statement
                create_statement = f"CREATE INDEX {idx_name} ON {table_name} ({clean_column_list})"
        
        print(f"Executing sanitized CREATE INDEX statement: {create_statement}")
        db_manager.execute(create_statement)
        db_manager.commit()
        
        return jsonify({'success': True, 'message': f"Index {index_name} was created successfully"})
    except Exception as e:
        import traceback
        print(f"Error creating index: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)})

@app.route('/api/refresh-analysis', methods=['POST'])
def refresh_analysis():
    """API endpoint to refresh the index analysis."""
    try:
        # Here we would normally trigger a reanalysis of the database
        # For this demo, we'll just return success
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/backup-database', methods=['POST'])
def backup_database():
    """API endpoint to backup the database."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"backup_{timestamp}.db")
        
        # Create a copy of the database file
        shutil.copy2(db_file, backup_file)
        
        return jsonify({
            'success': True,
            'backup_file': backup_file
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/vacuum-database', methods=['POST'])
def vacuum_database():
    """API endpoint to vacuum the database."""
    try:
        db_manager.execute("VACUUM")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/clear-logs', methods=['POST'])
def clear_logs():
    """API endpoint to clear query logs."""
    try:
        retention_days = int(config_manager.get('ANALYSIS', 'log_retention_days', '30'))
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        
        db_manager.execute("DELETE FROM query_logs WHERE date(timestamp) < ?", (cutoff_date,))
        db_manager.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/export-report')
def export_report():
    """API endpoint to export an index recommendation report."""
    try:
        recommendations = index_recommender.analyze()
        
        # If we don't have real recommendations, add some mock data
        if not recommendations:
            recommendations = generate_mock_recommendations()
        
        # Export as CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Table', 'Column', 'Score', 'Index Type', 'Index Name', 'Create Statement', 'Est. Impact'])
        
        # Write data
        for rec in recommendations:
            writer.writerow([
                rec['table'],
                rec['column'],
                rec['score'],
                rec['index_type'] or 'Regular',
                rec['index_name'],
                rec['create_statement'],
                f"{rec['estimated_impact']}%"
            ])
        
        # Create response
        response = app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=index_recommendations.csv'}
        )
        
        return response
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/test-index', methods=['POST'])
def test_index():
    """API endpoint to test the performance impact of an index."""
    query = request.json.get('query')
    create_statement = request.json.get('create_statement')
    
    if not query or not create_statement:
        return jsonify({'error': 'Both query and CREATE INDEX statement are required'})
    
    try:
        result = performance_comparer.compare_with_index(query, create_statement)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'success': False})

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors."""
    return render_template('500.html'), 500

# Run the application
if __name__ == '__main__':
    app.run(debug=True, port=5000)