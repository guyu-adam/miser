"""
setup_wizard.py — First-run setup wizard for Miser v1.4 (Phase 1 #7).
Detects Ollama, pulls the default model, and guides the user through setup.
"""

import subprocess, sys, time, os

# Windows: force UTF-8 to prevent GBK encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def check_ollama() -> bool:
    """Check if Ollama is installed and running."""
    try:
        r = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except FileNotFoundError:
        return False

def check_ollama_running() -> bool:
    """Check if Ollama server is reachable."""
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def pull_model(model: str = "qwen3.5:4b") -> bool:
    """Pull the default model via Ollama CLI with progress display."""
    print(f"\n  Pulling model: {model}...")
    print("  This may take a few minutes on first run.\n")
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            check=False, capture_output=False
        )
        return result.returncode == 0
    except Exception:
        return False

def wizard():
    """Interactive first-run setup wizard."""
    print("=" * 56)
    print("  ⚡ Miser v1.4 — First Run Setup Wizard")
    print("=" * 56)
    print()

    # Step 1: Check Python
    print(f"  [1/3] Python {sys.version_info.major}.{sys.version_info.minor} ✓")

    # Step 2: Check/install Ollama
    if check_ollama():
        print("  [2/3] Ollama detected ✓")
    else:
        print("  [2/3] Ollama not found!")
        print()
        print("  Please install Ollama from: https://ollama.com")
        print("  Then re-run: python setup_wizard.py")
        return False

    if not check_ollama_running():
        print("  Starting Ollama...")
        try:
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            if check_ollama_running():
                print("  Ollama started ✓")
            else:
                print("  Warning: Ollama may not be running. Start it manually:")
                print("    ollama serve")
        except Exception:
            print("  Warning: Could not start Ollama automatically.")
            print("  Run 'ollama serve' in another terminal.")

    # Step 3: Pull model
    model = os.environ.get("MISER_MODEL", "qwen3.5:4b")
    print(f"  [3/3] Default model: {model}")

    # Check if already pulled
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if model.split(":")[0] in r.stdout:
            print("  Model already installed ✓")
        else:
            if not pull_model(model):
                print(f"  Warning: Could not pull {model}.")
                print(f"  Run manually: ollama pull {model}")
    except Exception:
        pass

    print()
    print("  Setup complete! Start Miser:")
    print("    python miser.py")
    print()
    return True

if __name__ == "__main__":
    wizard()
