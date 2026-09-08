from pathlib import Path
import ast, re

p=Path('source/gph_central.py')
text=p.read_text(encoding='utf-8')
lines=text.splitlines()
tree=ast.parse(text)

print('VERSION', re.search(r'APP_VERSION\s*=\s*"([^"]+)"',text).group(1))
print('LINES',len(lines))

wanted_exact={
    'decision_contextual_evidence','build_decision_reading','freeze_decision_snapshot',
    'audit_decision_snapshots','_decision_row_to_dict','_decision_audited_rows',
    '_decision_performance_from_rows','show_decision_page','_decision_build_contextual',
    '_auto_decision_cycle','sync_decision_snapshots_from_rows',
}
for n in ast.walk(tree):
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and (
        n.name in wanted_exact or 'decision_snapshot' in n.name or n.name.startswith('_decision_')
    ):
        print(f'\n### FUNCTION {n.name} {n.lineno}-{n.end_lineno}')
        print('\n'.join(lines[n.lineno-1:n.end_lineno]))

print('\n### DECISION TABLE / MIGRATIONS')
for i,line in enumerate(lines,1):
    if 'decision_snapshots' in line or 'contextual' in line.lower() and ('ALTER TABLE' in line or 'CREATE TABLE' in line):
        a=max(1,i-8); b=min(len(lines),i+18)
        print(f'\n--- around {i} ---')
        print('\n'.join(lines[a-1:b]))

print('\n### RESULT AUDIT CALL SITES')
for i,line in enumerate(lines,1):
    if 'audit_decision_snapshots' in line and not line.lstrip().startswith('def '):
        a=max(1,i-12); b=min(len(lines),i+12)
        print(f'\n--- around {i} ---')
        print('\n'.join(lines[a-1:b]))

print('\n### SYNC DECISION REFERENCES')
for i,line in enumerate(lines,1):
    if 'decision_snapshots' in line and ('sync' in line.lower() or 'cols_allowed' in line or 'export' in line.lower()):
        a=max(1,i-12); b=min(len(lines),i+20)
        print(f'\n--- around {i} ---')
        print('\n'.join(lines[a-1:b]))
