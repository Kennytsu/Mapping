"""Compliance Mapping Tool - Flask Backend API."""

import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from database import (
    init_db,
    get_frameworks,
    get_controls,
    get_mappings_for_control,
    get_connection
)
from document_parser import parse_uploaded_file

app = Flask(__name__, static_folder='static')
CORS(app)

# Initialize database on startup
init_db()


# Serve frontend
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)


# API Routes
@app.route('/api/frameworks', methods=['GET'])
def api_frameworks():
    """Get all frameworks."""
    frameworks = get_frameworks()
    return jsonify(frameworks)


@app.route('/api/controls', methods=['GET'])
def api_controls():
    """Search controls."""
    query = request.args.get('q', '')
    framework_id = request.args.get('framework_id')
    
    if framework_id:
        framework_id = int(framework_id)
    
    controls = get_controls(framework_id=framework_id, search_query=query)
    return jsonify(controls)


@app.route('/api/mappings/<control_id>', methods=['GET'])
def api_mappings(control_id):
    """Get mappings for a control."""
    framework_id = request.args.get('framework_id')
    
    if framework_id:
        framework_id = int(framework_id)
    
    source_control, mappings = get_mappings_for_control(control_id, framework_id)
    
    if not source_control:
        return jsonify({"error": "Control not found"}), 404
    
    return jsonify({
        "source": source_control,
        "mappings": mappings
    })


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Upload and parse a document."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    
    file = request.files['file']
    doc_type = request.form.get('doc_type', 'BSI Zuordnungstabelle')
    
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    result = parse_uploaded_file(file, doc_type)
    return jsonify(result)


@app.route('/api/import', methods=['POST'])
def api_import():
    """Import parsed data into database."""
    data = request.json
    
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    result = import_parsed_data(data)
    return jsonify(result)


def import_parsed_data(data: dict) -> dict:
    """Import parsed controls and mappings into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    controls_added = 0
    mappings_added = 0
    
    try:
        doc_type = data.get('doc_type', 'BSI')
        
        # Determine target framework
        if "BSI" in doc_type or "Grundschutz" in doc_type:
            cursor.execute("SELECT id FROM frameworks WHERE short_name = 'BSI'")
        elif "C5" in doc_type:
            cursor.execute("SELECT id FROM frameworks WHERE short_name = 'C5'")
        else:
            cursor.execute("SELECT id FROM frameworks WHERE short_name = 'ISO27001'")
        
        row = cursor.fetchone()
        if not row:
            return {"success": False, "error": "Target framework not found"}
        target_fw_id = row[0]
        
        # Get ISO framework ID
        cursor.execute("SELECT id FROM frameworks WHERE short_name = 'ISO27001'")
        iso_fw_id = cursor.fetchone()[0]
        
        # Import controls
        for ctrl in data.get("controls", []):
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO controls (framework_id, control_id, title, category) VALUES (?, ?, ?, ?)",
                    (target_fw_id, ctrl["control_id"], ctrl.get("title", ""), ctrl.get("category", ""))
                )
                if cursor.rowcount > 0:
                    controls_added += 1
            except Exception:
                pass
        
        # Build control lookup
        cursor.execute("SELECT id, control_id, framework_id FROM controls")
        ctrl_lookup = {(row[1], row[2]): row[0] for row in cursor.fetchall()}
        
        # Import mappings
        for mapping in data.get("mappings", []):
            source_id = ctrl_lookup.get((mapping["source"], iso_fw_id))
            target_id = ctrl_lookup.get((mapping["target"], target_fw_id))
            
            if source_id and target_id:
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO mappings (source_control_id, target_control_id, confidence, source_type, is_primary) VALUES (?, ?, 1.0, 'official', 1)",
                        (source_id, target_id)
                    )
                    if cursor.rowcount > 0:
                        mappings_added += 1
                except Exception:
                    pass
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "controls_added": controls_added,
            "mappings_added": mappings_added
        }
    
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
