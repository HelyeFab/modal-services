"""Helper script to run modal deploy with proper encoding on Windows."""
import subprocess
import sys
import os
import io

# Force UTF-8 mode
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

script_dir = os.path.dirname(os.path.abspath(__file__))
deploy_script = os.path.join(script_dir, 'deploy_whisper.py')

print(f"Deploying: {deploy_script}")
print("=" * 50)

proc = subprocess.Popen(
    [sys.executable, '-m', 'modal', 'deploy', deploy_script],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
    encoding='utf-8',
    errors='replace',
)

# Stream output, replacing any bad chars
for line in proc.stdout:
    # Replace any chars that might cause issues
    clean_line = line.encode('ascii', errors='replace').decode('ascii')
    print(clean_line, end='')

proc.wait()
print("=" * 50)
print(f"Exit code: {proc.returncode}")
sys.exit(proc.returncode)
