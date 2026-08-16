import subprocess
import sys
import time
import os

def main():
    print("🚀 Initializing Universal Trading Dashboard Setup...")
    print("Checking dependencies...")
    
    # Check if necessary files exist
    if not os.path.exists("tv_monitor_daemon.py"):
        print("Error: tv_monitor_daemon.py not found in the current directory.")
        sys.exit(1)
        
    if not os.path.exists("streamlit_app.py"):
        print("Error: streamlit_app.py not found in the current directory.")
        sys.exit(1)

    print("✅ Files verified.")
    print("📡 Starting TradingView Monitor Daemon in the background...")
    
    # Start the daemon
    daemon_process = subprocess.Popen([sys.executable, "-u", "tv_monitor_daemon.py"], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE)
    
    # Wait a bit for the daemon to create the initial JSON
    time.sleep(3)
    
    print("🖥️ Starting Streamlit Dashboard...")
    
    # Start streamlit
    try:
        subprocess.run(["uv", "run", "streamlit", "run", "streamlit_app.py"])
    except KeyboardInterrupt:
        print("\nShutting down services...")
        daemon_process.terminate()
        print("✅ Shutdown complete.")

if __name__ == "__main__":
    main()
