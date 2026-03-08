"""Verify pix.html structural integrity after session edits."""
import sys

with open("app/templates/pix.html", encoding="utf-8") as f:
    content = f.read()

lines = content.splitlines()
print(f"total lines: {len(lines)}")

checks = {
    "pixInputStep occurrences": content.count("pixInputStep"),
    "recipientCard occurrences": content.count("recipientCard"),
    "comprovanteCard occurrences": content.count("comprovanteCard"),
    "novaTransferencia occurrences": content.count("novaTransferencia"),
    "showComprovante occurrences": content.count("showComprovante"),
    "lookupRecipient occurrences": content.count("lookupRecipient"),
    # handlers use getElementById pattern, not variable name prefix
    "pixForm getElementById handler": content.count("getElementById('pixForm').addEventListener"),
    "cobrarForm getElementById handler": content.count("getElementById('cobrarForm').addEventListener"),
    "endblock occurrences": content.count("{% endblock %}"),
    # 3 occurrences expected: confirmarRecebimento + pixForm handler + cobrarForm handler
    "if (response.ok) occurrences": content.count("if (response.ok)"),
    "old #result div": content.count('id="result"'),
}

all_ok = True
for name, val in checks.items():
    print(f"  {name}: {val}")

# Assertions
errors = []
if checks["pixInputStep occurrences"] < 1:
    errors.append("FAIL: pixInputStep missing")
if checks["recipientCard occurrences"] < 1:
    errors.append("FAIL: recipientCard missing")
if checks["comprovanteCard occurrences"] < 1:
    errors.append("FAIL: comprovanteCard missing")
if checks["novaTransferencia occurrences"] < 1:
    errors.append("FAIL: novaTransferencia missing")
if checks["showComprovante occurrences"] < 1:
    errors.append("FAIL: showComprovante missing")
if checks["lookupRecipient occurrences"] < 1:
    errors.append("FAIL: lookupRecipient missing")
if checks["pixForm getElementById handler"] < 1:
    errors.append("FAIL: pixForm submit handler missing")
if checks["cobrarForm getElementById handler"] < 1:
    errors.append("FAIL: cobrarForm handler missing")
if checks["endblock occurrences"] < 1:
    errors.append("FAIL: endblock missing")
# 3 expected: confirmarRecebimento() + pixForm handler + cobrarForm handler
if checks["if (response.ok) occurrences"] != 3:
    errors.append(f"FAIL: expected 3 'if (response.ok)', found {checks['if (response.ok) occurrences']}")
if checks["old #result div"] > 0:
    errors.append("FAIL: old #result div still present")

if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
