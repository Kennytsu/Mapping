"""SQLite database setup and models."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "compliance.db"


def get_connection():
    """Get database connection."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Frameworks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS frameworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            short_name TEXT NOT NULL UNIQUE,
            version TEXT NOT NULL,
            description TEXT
        )
    """)
    
    # Controls table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_id INTEGER NOT NULL,
            control_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT,
            FOREIGN KEY (framework_id) REFERENCES frameworks(id),
            UNIQUE(framework_id, control_id)
        )
    """)
    
    # Mappings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_control_id INTEGER NOT NULL,
            target_control_id INTEGER NOT NULL,
            confidence REAL DEFAULT 1.0,
            source_type TEXT DEFAULT 'official',
            is_primary INTEGER DEFAULT 0,
            FOREIGN KEY (source_control_id) REFERENCES controls(id),
            FOREIGN KEY (target_control_id) REFERENCES controls(id)
        )
    """)
    
    # Version changes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS version_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_short_name TEXT NOT NULL,
            old_version TEXT NOT NULL,
            new_version TEXT NOT NULL,
            change_type TEXT NOT NULL,
            old_control_id TEXT,
            new_control_id TEXT,
            description TEXT,
            category TEXT
        )
    """)
    
    conn.commit()
    conn.close()


def get_frameworks():
    """Get all frameworks."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.*, COUNT(c.id) as control_count 
        FROM frameworks f 
        LEFT JOIN controls c ON f.id = c.framework_id 
        GROUP BY f.id
    """)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]


def get_controls(framework_id=None, search_query=None):
    """Get controls with optional filtering."""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT c.*, f.short_name as framework_short_name 
        FROM controls c 
        JOIN frameworks f ON c.framework_id = f.id
        WHERE 1=1
    """
    params = []
    
    if framework_id:
        query += " AND c.framework_id = ?"
        params.append(framework_id)
    
    if search_query:
        query += " AND (c.control_id LIKE ? OR c.title LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    
    cursor.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]


def get_mappings_for_control(control_id_str, source_framework_id=None):
    """Get all mappings for a control."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # First find the control
    query = "SELECT id, framework_id FROM controls WHERE control_id = ?"
    params = [control_id_str]
    if source_framework_id:
        query += " AND framework_id = ?"
        params.append(source_framework_id)
    
    cursor.execute(query, params)
    source = cursor.fetchone()
    
    if not source:
        conn.close()
        return None, []
    
    source_id, source_fw_id = source
    
    # Get source control details
    cursor.execute("""
        SELECT c.*, f.short_name as framework_short_name 
        FROM controls c JOIN frameworks f ON c.framework_id = f.id 
        WHERE c.id = ?
    """, [source_id])
    columns = [desc[0] for desc in cursor.description]
    source_control = dict(zip(columns, cursor.fetchone()))
    
    # Get mappings (bidirectional)
    cursor.execute("""
        SELECT 
            c.control_id, c.title, c.description, c.category,
            f.short_name as framework_short_name,
            m.confidence, m.source_type, m.is_primary
        FROM mappings m
        JOIN controls c ON (
            (m.source_control_id = ? AND m.target_control_id = c.id) OR
            (m.target_control_id = ? AND m.source_control_id = c.id)
        )
        JOIN frameworks f ON c.framework_id = f.id
        WHERE c.id != ?
    """, [source_id, source_id, source_id])
    
    columns = [desc[0] for desc in cursor.description]
    mappings = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    
    return source_control, mappings


def get_coverage_analysis(source_framework_id, target_framework_id):
    """Analyze coverage between two frameworks."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get framework names
    cursor.execute("SELECT short_name, version FROM frameworks WHERE id IN (?, ?)", 
                   [source_framework_id, target_framework_id])
    fw_info = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Get source controls
    cursor.execute("SELECT id, control_id FROM controls WHERE framework_id = ?", [source_framework_id])
    source_controls = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Get target controls
    cursor.execute("SELECT id, control_id FROM controls WHERE framework_id = ?", [target_framework_id])
    target_controls = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Find mapped source controls
    cursor.execute("""
        SELECT DISTINCT 
            CASE 
                WHEN m.source_control_id IN (SELECT id FROM controls WHERE framework_id = ?) 
                THEN m.source_control_id 
                ELSE m.target_control_id 
            END as source_ctrl,
            CASE 
                WHEN m.source_control_id IN (SELECT id FROM controls WHERE framework_id = ?) 
                THEN m.target_control_id 
                ELSE m.source_control_id 
            END as target_ctrl
        FROM mappings m
        WHERE (m.source_control_id IN (SELECT id FROM controls WHERE framework_id = ?) 
               AND m.target_control_id IN (SELECT id FROM controls WHERE framework_id = ?))
           OR (m.target_control_id IN (SELECT id FROM controls WHERE framework_id = ?) 
               AND m.source_control_id IN (SELECT id FROM controls WHERE framework_id = ?))
    """, [source_framework_id, source_framework_id, 
          source_framework_id, target_framework_id,
          source_framework_id, target_framework_id])
    
    mapped_pairs = cursor.fetchall()
    mapped_source_ids = set(row[0] for row in mapped_pairs)
    mapped_target_ids = set(row[1] for row in mapped_pairs)
    
    conn.close()
    
    # Calculate coverage
    total = len(source_controls)
    mapped = len(mapped_source_ids)
    unmapped_source = [source_controls[id] for id in source_controls if id not in mapped_source_ids]
    gap_target = [target_controls[id] for id in target_controls if id not in mapped_target_ids]
    
    return {
        "source_framework": list(fw_info.keys())[0] if fw_info else "Unknown",
        "target_framework": list(fw_info.keys())[1] if len(fw_info) > 1 else "Unknown",
        "total_source_controls": total,
        "mapped_controls": mapped,
        "unmapped_controls": total - mapped,
        "coverage_percentage": round((mapped / total * 100) if total > 0 else 0, 1),
        "unmapped_control_ids": unmapped_source,
        "gap_controls": gap_target
    }


def get_version_changes(framework, old_version, new_version):
    """Get version changes between two versions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM version_changes 
        WHERE framework_short_name = ? AND old_version = ? AND new_version = ?
    """, [framework, old_version, new_version])
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]
