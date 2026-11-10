# Other editors and terminal workflows

All editor integrations call the same CLI:
python <checkout>/scripts/run.py check --repo <repository> --mode targeted --timeout 120

Runner selection depends on Git changes and repository configuration, never the editor name. analyze/report provide read-only static plans. To integrate a lifecycle that you control, send {"session_id":"stable-task-id","cwd":"absolute-repo-path"} on stdin to integrations/hooks/auto_check.py --agent generic --phase start before edits and --phase stop afterward. Stop returns {"report":"..."}; the caller is responsible for displaying it.

Use one stable ID and the same repository between phases. The wrapper preserves once-per-task claims, timeout and disable controls. Do not call start again after continuation in the same task. A real host must provide and verify its own lifecycle contract; do not assume that an arbitrary editor has these events.

A plain terminal CLI check does not require a lifecycle baseline. Do not copy or reimplement selection logic in an editor wrapper.
