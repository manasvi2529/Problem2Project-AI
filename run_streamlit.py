"""
Streamlit Launcher for Problem2Project AI.
Starts Streamlit on port 8501 with browser auto-opening.
"""
import sys
import subprocess

if __name__ == "__main__":
    cmd = [sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.port", "8501"]
    print("Starting Problem2Project AI Streamlit Data Science Studio on http://localhost:8501...")
    subprocess.run(cmd)
