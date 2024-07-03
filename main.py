import subprocess
import sys
import os
import threading

# Copy current environment variables
env = os.environ.copy()

def stream_output(pipe, script_name):
    """Stream the output from the pipe."""
    try:
        for line in iter(pipe.readline, ''):
            if line:  # Ensure the line is not empty
                print(f"[{script_name}]: {line.strip()}")
    except Exception as e:
        print(f"Error streaming output from {script_name}: {e}")

def run_script(script_name):
    """Run a script concurrently and stream its output."""
    try:
        process = subprocess.Popen(
            [sys.executable, script_name],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line-buffered
        )

        # Create threads to stream stdout and stderr
        stdout_thread = threading.Thread(target=stream_output, args=(process.stdout, script_name))
        stderr_thread = threading.Thread(target=stream_output, args=(process.stderr, script_name))

        stdout_thread.start()
        stderr_thread.start()

        # Ensure the threads have finished
        stdout_thread.join()
        stderr_thread.join()

        process.stdout.close()
        process.stderr.close()
        return process.wait()

    except Exception as e:
        print(f"Error running script {script_name}: {e}")
        return -1

# List of scripts to run
scripts = [
    'bots/pbe_bank_bot.py',
    'bots/pbe_bot.py',
    'bots/sim_league_scraper.py'
]

# Run each script concurrently and print their output
threads = []
for script in scripts:
    thread = threading.Thread(target=run_script, args=(script,))
    thread.start()
    threads.append(thread)

# Ensure all threads have finished
for thread in threads:
    thread.join()
