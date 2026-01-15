"""Version info and update configuration."""

__version__ = "0.3.2"

# GitHub repository for updates
GITHUB_OWNER = "danmerus"  # Change this to your GitHub username
GITHUB_REPO = "berserk_vibe"    # Change this to your repo name

# Update check settings
UPDATE_CHECK_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
