import subprocess
import sys

def get_all_commits():
    # Get all commit hashes
    result = subprocess.run(['git', 'rev-list', '--all'], capture_output=True, text=True)
    return result.stdout.splitlines()

def inspect_commit(commit_hash):
    # Get raw commit content
    result = subprocess.run(['git', 'cat-file', '-p', commit_hash], capture_output=True, text=True)
    content = result.stdout
    
    # Check for "Claude" case-insensitive
    if "claude" in content.lower():
        print(f"FOUND in {commit_hash}:")
        for line in content.splitlines():
            if "claude" in line.lower():
                print(f"  Line: {line}")
        return True
    return False

commits = get_all_commits()
print(f"Scanning {len(commits)} commits...")
found_count = 0
for commit in commits:
    if inspect_commit(commit):
        found_count += 1

print(f"Total commits with 'Claude': {found_count}")
