import re
import sys
import zipfile

p = sys.argv[1]
z = zipfile.ZipFile(p)
print("==== files in trace ====")
for n in z.namelist():
    if n.endswith((".trace", ".network")):
        print(n, z.getinfo(n).file_size)

print()
print("==== url-like strings from 0-trace.network (first 50) ====")
if "0-trace.network" in z.namelist():
    n = z.read("0-trace.network").decode(errors="replace")
    seen = set()
    for m in re.finditer(r'https?://[^\s"\\]+', n):
        u = m.group(0).rstrip('",:;)')
        if u not in seen:
            seen.add(u)
        if len(seen) >= 50:
            break
    for u in sorted(seen):
        print(u)

print()
print("==== url-like strings from 0-trace.trace (first 50) ====")
if "0-trace.trace" in z.namelist():
    n = z.read("0-trace.trace").decode(errors="replace")
    seen = set()
    for m in re.finditer(r'https?://[^\s"\\]+', n):
        u = m.group(0).rstrip('",:;)')
        if u not in seen:
            seen.add(u)
        if len(seen) >= 50:
            break
    for u in sorted(seen):
        print(u)
