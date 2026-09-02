import streamlit as st
import os
import time
import threading
from pathlib import Path
from sqlalchemy.orm import Session

# Import backend modules
from src.api.db import init_db, new_session
from src.api.models.jobs import PipelineJob, SttJob
from src.api.services import stt_service
from src.api.routes.pipeline import _run_pipeline, cleanup_empty_job_folders, _AUDIO_EXTENSIONS

# Ensure DB is initialized on startup
init_db()

st.set_page_config(page_title="Sales QA Pipeline", layout="wide")

# --- UI Setup ---
with st.sidebar:
    st.header("Pipeline Inputs")
    recording = st.file_uploader("Upload Recording/Transcript", type=['mp3', 'mp4', 'm4a', 'flac', 'wav', 'ogg', 'srt', 'vtt', 'json', 'txt', 'opus', 'webm'])
    course_data = st.file_uploader("Upload Course Data (CSV)", type=['csv'])
    customer_name = st.text_input("Customer Name (Optional)")
    sales_rep_name = st.text_input("Sales Rep Name (Optional)")
    sales_pitch = st.file_uploader("Upload Sales Pitch (Markdown, Optional)", type=['md'])
    
    start_pipeline = st.button("Run Pipeline", type="primary", use_container_width=True)

# Main Screen
st.title("Sales Call Quality Assurance")

if start_pipeline:
    if not course_data or not recording:
        st.error("Please upload both Course Data and a Recording/Transcript to proceed.")
    else:
        # Create input directory
        input_dir = Path("data/input")
        input_dir.mkdir(parents=True, exist_ok=True)
        
        # Save files to disk
        course_path = input_dir / course_data.name
        with open(course_path, "wb") as f:
            f.write(course_data.getbuffer())
            
        recording_path = input_dir / recording.name
        with open(recording_path, "wb") as f:
            f.write(recording.getbuffer())
            
        sales_pitch_path_str = None
        if sales_pitch:
            sales_pitch_path = input_dir / sales_pitch.name
            with open(sales_pitch_path, "wb") as f:
                f.write(sales_pitch.getbuffer())
            sales_pitch_path_str = str(sales_pitch_path.absolute())

        course_path_str = str(course_path.absolute())
        recording_path_str = str(recording_path.absolute())
        
        # Identify if audio or transcript
        ext = recording_path.suffix.lower()
        is_audio = ext in _AUDIO_EXTENSIONS

        model = os.environ.get("OPENROUTER_DEFAULT_MODEL", "").strip() or "google/gemma-3-27b-it"

        # Initialize DB session to create jobs
        db = new_session()
        stt_job_id = None
        pipeline_job_id = None
        
        try:
            with st.spinner("Initializing pipeline..."):
                if is_audio:
                    stt_job = SttJob(audio_path=recording_path_str, status="PENDING")
                    db.add(stt_job)
                    db.commit()
                    db.refresh(stt_job)

                    # Submit to STT Provider
                    try:
                        operation_name, gcs_uri = stt_service.submit_stt(recording_path_str)
                    except Exception as exc:
                        stt_job.status = "FAILED"
                        stt_job.error = str(exc)
                        db.commit()
                        st.error(f"Failed to submit audio to STT: {exc}")
                        st.stop()

                    stt_job.operation_name = operation_name
                    stt_job.gcs_uri = gcs_uri
                    stt_job.status = "SUBMITTED"
                    db.commit()
                    stt_job_id = stt_job.id
                    
                    pipeline_input_path = recording_path_str
                else:
                    pipeline_input_path = recording_path_str

                # Create pipeline job
                pipeline_job = PipelineJob(
                    stt_job_id=stt_job_id,
                    input_path=pipeline_input_path,
                    course_path=course_path_str,
                    sales_pitch_path=sales_pitch_path_str,
                    model=model,
                    rep_id=None,
                    call_id=None,
                    sales_rep_name=sales_rep_name if sales_rep_name else None,
                    customer_name=customer_name if customer_name else None,
                    current_step="STT_SUBMITTED" if stt_job_id else "PENDING",
                    status="STT_SUBMITTED" if stt_job_id else "PENDING",
                )
                db.add(pipeline_job)
                db.commit()
                db.refresh(pipeline_job)
                pipeline_job_id = pipeline_job.id

                # Cleanup and output dirs
                cleanup_empty_job_folders()
                job_out_dir = Path("data/output") / pipeline_job_id
                (job_out_dir / "report").mkdir(parents=True, exist_ok=True)
                (job_out_dir / "transcript").mkdir(parents=True, exist_ok=True)
                (job_out_dir / "stt_result").mkdir(parents=True, exist_ok=True)

        finally:
            db.close()

        st.success(f"Pipeline started! ID: {pipeline_job_id}")

        # Run pipeline in a background thread
        thread = threading.Thread(target=_run_pipeline, args=(pipeline_job_id,), daemon=True)
        thread.start()

        # Polling status
        status_placeholder = st.empty()
        
        while True:
            time.sleep(3)
            db = new_session()
            try:
                job = db.get(PipelineJob, pipeline_job_id)
                if not job:
                    status_placeholder.error("Pipeline job disappeared.")
                    break
                
                state = job.status
                step = job.current_step
                error = job.error
                html_report_path = job.report_html_path
            finally:
                db.close()

            if state == "DONE":
                status_placeholder.success("Pipeline processing completed!")
                
                if html_report_path and os.path.exists(html_report_path):
                    with open(html_report_path, "r", encoding="utf-8") as f:
                        st.session_state["html_content"] = f.read()
                        st.session_state["pipeline_id"] = pipeline_job_id
                else:
                    st.warning("Report generated, but HTML file could not be found.")
                break
            elif state == "FAILED":
                status_placeholder.error(f"Pipeline failed: {error}")
                break
            else:
                status_placeholder.info(f"Processing... Current Step: {step}")

if "html_content" in st.session_state:
    st.subheader("QA Report")
    st.components.v1.html(st.session_state["html_content"], height=800, scrolling=True)
    
    st.download_button(
        label="Download HTML Report",
        data=st.session_state["html_content"],
        file_name=f"report_{st.session_state.get('pipeline_id', 'output')}.html",
        mime="text/html"
    )
