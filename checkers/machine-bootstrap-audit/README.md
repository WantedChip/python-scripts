# Machine Bootstrap Audit Tool

`machine-bootstrap-audit` performs static and dry-run analysis on setup/bootstrap scripts (`.sh`, `.bash`, `.py`, `.ps1`) to detect hidden assumptions, risky patterns, interactive blocks, and unverified system dependencies.

## Usage

```bash
python main.py setup.sh install.py --strict
```

## Audit Checks Performed

1. **Interactive Prompts**: Flags blocking `read -p`, `input()`, or direct `stdin` calls that break non-interactive CI/CD execution.
2. **Privilege Escalation**: Highlights implicit `sudo`, `su`, or `runas` commands.
3. **Hardcoded Stale Paths**: Identifies hardcoded user home directories (`/home/user`, `C:\Users\dev`) or system binary paths.
4. **Un-checked Binary Dependencies**: Flags direct invocations of external tools (`docker`, `npm`, `brew`, `pip`) lacking pre-flight binary check validations.
