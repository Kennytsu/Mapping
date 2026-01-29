"""Compliance Mapping Tool - Streamlit Application."""

import streamlit as st
import pandas as pd
from database import (
    init_db, 
    get_frameworks, 
    get_controls, 
    get_mappings_for_control,
    get_connection
)
from document_parser import parse_uploaded_file

st.set_page_config(
    page_title="Compliance Mapping Tool",
    page_icon="shield",
    layout="wide"
)

init_db()


def main():
    st.title("Compliance Framework Mapping Tool")
    st.caption("Map controls between ISO 27001, BSI IT-Grundschutz, and C5 frameworks")
    
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Page",
        ["Control Lookup", "Upload Documents"]
    )
    
    if page == "Control Lookup":
        control_lookup_page()
    else:
        upload_documents_page()


def upload_documents_page():
    """Upload and parse compliance documents."""
    st.header("Upload Compliance Documents")
    st.write("Upload BSI mapping documents (PDF or Excel) to add new controls and mappings.")
    
    # Document type selection
    doc_type = st.selectbox(
        "Document Type",
        [
            "BSI Zuordnungstabelle (ISO to BSI mapping)",
            "C5 Cross-Reference Table (ISO to C5 mapping)",
            "BSI Kompendium (new controls)",
            "Custom Mapping Table"
        ]
    )
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload Document",
        type=["pdf", "xlsx", "xls", "csv"],
        help="Supported formats: PDF, Excel, CSV"
    )
    
    if uploaded_file:
        st.write(f"Uploaded: **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")
        
        # Parse the document
        with st.spinner("Parsing document..."):
            result = parse_uploaded_file(uploaded_file, doc_type)
        
        if result["success"]:
            st.success(f"Successfully parsed document")
            
            # Show extracted data
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Extracted Controls")
                if result["controls"]:
                    df_controls = pd.DataFrame(result["controls"])
                    st.dataframe(df_controls, height=300)
                    st.write(f"Total: {len(result['controls'])} controls")
                else:
                    st.info("No new controls found")
            
            with col2:
                st.subheader("Extracted Mappings")
                if result["mappings"]:
                    df_mappings = pd.DataFrame(result["mappings"])
                    st.dataframe(df_mappings, height=300)
                    st.write(f"Total: {len(result['mappings'])} mappings")
                else:
                    st.info("No mappings found")
            
            # Import button
            st.divider()
            if st.button("Import to Database", type="primary"):
                with st.spinner("Importing..."):
                    import_result = import_parsed_data(result, doc_type)
                
                if import_result["success"]:
                    st.success(f"Imported {import_result['controls_added']} controls and {import_result['mappings_added']} mappings")
                else:
                    st.error(f"Import failed: {import_result['error']}")
        else:
            st.error(f"Parsing failed: {result['error']}")
            
            # Show raw text for debugging
            if result.get("raw_text"):
                with st.expander("Show extracted text (for debugging)"):
                    st.text(result["raw_text"][:5000])


def import_parsed_data(result: dict, doc_type: str) -> dict:
    """Import parsed data into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    controls_added = 0
    mappings_added = 0
    
    try:
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
        
        # Get ISO framework ID for mappings
        cursor.execute("SELECT id FROM frameworks WHERE short_name = 'ISO27001'")
        iso_fw_id = cursor.fetchone()[0]
        
        # Import controls
        for ctrl in result.get("controls", []):
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO controls (framework_id, control_id, title, category) VALUES (?, ?, ?, ?)",
                    (target_fw_id, ctrl["control_id"], ctrl.get("title", ""), ctrl.get("category", ""))
                )
                if cursor.rowcount > 0:
                    controls_added += 1
            except Exception as e:
                pass  # Skip duplicates
        
        # Build control lookup
        cursor.execute("SELECT id, control_id, framework_id FROM controls")
        ctrl_lookup = {(row[1], row[2]): row[0] for row in cursor.fetchall()}
        
        # Import mappings
        for mapping in result.get("mappings", []):
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


def control_lookup_page():
    """Control lookup and mapping page."""
    st.header("Control Lookup")
    st.write("Search for a control to see its mappings across frameworks.")
    
    frameworks = get_frameworks()
    fw_options = {f["short_name"]: f["id"] for f in frameworks}
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        search_query = st.text_input(
            "Search by Control ID or Title",
            placeholder="e.g., A.5.1 or access control"
        )
    
    with col2:
        selected_fw = st.selectbox(
            "Filter by Framework",
            ["All Frameworks"] + list(fw_options.keys())
        )
    
    framework_id = fw_options.get(selected_fw) if selected_fw != "All Frameworks" else None
    
    if search_query:
        controls = get_controls(framework_id=framework_id, search_query=search_query)
        
        if controls:
            st.subheader(f"Found {len(controls)} controls")
            
            for ctrl in controls[:20]:
                with st.expander(f"{ctrl['control_id']} ({ctrl['framework_short_name']}) - {ctrl['title'][:60]}..."):
                    st.write(f"**Framework:** {ctrl['framework_short_name']}")
                    st.write(f"**Category:** {ctrl['category'] or 'N/A'}")
                    st.write(f"**Description:** {ctrl['description'] or 'N/A'}")
                    
                    if st.button(f"Show Mappings", key=f"btn_{ctrl['id']}"):
                        st.session_state['selected_control'] = ctrl['control_id']
                        st.session_state['selected_fw_id'] = ctrl['framework_id']
        else:
            st.info("No controls found matching your search.")
    
    if 'selected_control' in st.session_state:
        st.divider()
        show_control_mappings(
            st.session_state['selected_control'],
            st.session_state.get('selected_fw_id')
        )


def show_control_mappings(control_id, framework_id=None):
    """Display mappings for a control."""
    source_control, mappings = get_mappings_for_control(control_id, framework_id)
    
    if not source_control:
        st.error(f"Control {control_id} not found")
        return
    
    st.subheader(f"Mappings for {control_id}")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Framework", source_control['framework_short_name'])
    with col2:
        st.write(f"**{source_control['title']}**")
    
    if mappings:
        st.success(f"Found {len(mappings)} mappings across frameworks")
        
        df = pd.DataFrame(mappings)
        
        for fw in df['framework_short_name'].unique():
            st.write(f"### {fw}")
            fw_mappings = df[df['framework_short_name'] == fw]
            
            for _, m in fw_mappings.iterrows():
                source_label = "Official" if m['source_type'] == 'official' else "Manual"
                primary_label = " (Primary)" if m['is_primary'] else ""
                
                st.write(f"**{m['control_id']}** - {source_label}{primary_label}")
                st.caption(m['title'])
    else:
        st.warning("No mappings found for this control")


if __name__ == "__main__":
    main()
