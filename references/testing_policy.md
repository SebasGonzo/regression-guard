# Testing policy

The CLI reads Git state and Python source. `check` executes selected pytest files inside the analyzed repository. Test code itself can write files, use credentials, or call services; inspect unknown suites before running. The engine disables pytest plugin autoload, bytecode writes, and pytest cache, but cannot constrain effects inside user tests or child processes spawned by tests.

`UNKNOWN` means the dependency or verification strategy is insufficient. `INCOMPLETE` means selected tests did not all finish. `FAIL` means at least one selected test file failed. `PASS` means all selected test files passed with no known mapping uncertainty. No state proves absence of all regressions.

Configuration changes, dynamic imports, generated tests, indirect imports, and JavaScript/TypeScript dependencies need manual review. JS package test scripts are displayed but never executed automatically because package scripts can run arbitrary commands.
