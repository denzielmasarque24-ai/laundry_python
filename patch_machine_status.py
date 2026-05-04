with open("templates/admin_base.html", "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1: normalizeMachineStatus — remove the enabled===false override, just return the actual status
old1 = """    function normalizeMachineStatus(machine) {

      if (!machine) return "Disabled";
      const baseStatus = machine.status_display || machine.status || "Available";
      if (["Maintenance", "Disabled", "Unavailable"].includes(baseStatus)) return baseStatus;
      if (machine.enabled === false || machine.effective_enabled === false) return "Disabled";
      return baseStatus;
    }"""

new1 = """    function normalizeMachineStatus(machine) {
      if (!machine) return "Disabled";
      return machine.status_display || machine.status || "Available";
    }"""

# Fix 2: normalizeMachine — status_display should always equal the actual status
old2 = '        status_display: effectiveEnabled || inactiveStatuses.includes(baseStatus) ? baseStatus : "Disabled",'
new2 = '        status_display: baseStatus,'

if old1 in content:
    content = content.replace(old1, new1)
    print("Fix 1 applied: normalizeMachineStatus")
else:
    print("Fix 1 NOT FOUND — checking variant...")
    # Try without the blank lines
    import re
    content = re.sub(
        r'function normalizeMachineStatus\(machine\) \{.*?return baseStatus;\s*\}',
        'function normalizeMachineStatus(machine) {\n      if (!machine) return "Disabled";\n      return machine.status_display || machine.status || "Available";\n    }',
        content, flags=re.DOTALL
    )
    print("Fix 1 applied via regex")

if old2 in content:
    content = content.replace(old2, new2)
    print("Fix 2 applied: normalizeMachine status_display")
else:
    print("Fix 2 NOT FOUND")

with open("templates/admin_base.html", "w", encoding="utf-8") as f:
    f.write(content)

print("Done.")
