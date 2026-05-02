import sys

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

idx1 = text.find('st.dataframe(streak_display, use_container_width=True, hide_index=True)')
if idx1 == -1:
    print('idx1 not found')
    sys.exit(1)

# Find the next fill="tozeroy" AFTER idx1
idx2 = text.find('fill="tozeroy", fillcolor="rgba(176,176,176,0.07)",', idx1)
if idx2 == -1:
    print('idx2 not found')
    sys.exit(1)

with open('fix2.py', 'r', encoding='utf-8') as f:
    fix2 = f.read()

missing_code = fix2.split('missing_code = """')[1].split('"""')[0]

new_text = text[:idx1 + len('st.dataframe(streak_display, use_container_width=True, hide_index=True)')] + '\n\n' + missing_code + '\n                ' + text[idx2:]

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

print('Fixed!')
